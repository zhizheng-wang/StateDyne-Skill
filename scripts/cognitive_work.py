#!/usr/bin/env python3
"""Local, standard-library artifact gates; no model calls or external actions.

A passing receipt binds bytes and declared work, not truth, independent identity,
semantic quality, completeness of undiscovered relations, or host message sending.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from datetime import datetime, timezone

SCHEMA = 1
KINDS = {'relation', 'operation', 'challenge', 'reception', 'information', 'point', 'proposal', 'action', 'output'}
ID = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.:-]*\Z')
SHA = re.compile(r'[0-9a-f]{64}\Z')
LIMITS = {'semantic_sufficiency': 'not_checked', 'source_truth': 'not_authenticated',
          'reviewer_identity': 'not_authenticated', 'host_send': 'not_enforced'}


class WorkError(Exception):
    pass


def require(test, message):
    if not test:
        raise WorkError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def integer(value):
    return type(value) is int and value >= 1


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(value).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def read_json(path):
    def bad(value):
        raise WorkError('non-finite JSON number: ' + value)
    try:
        return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=pairs, parse_constant=bad)
    except (ValueError, UnicodeError) as error:
        raise WorkError('invalid JSON: ' + str(error)) from error


def safe_path(root, name):
    require(nonempty(name), 'path must be a nonempty relative string')
    path = Path(name)
    require(not path.is_absolute(), 'absolute artifact path is not allowed')
    resolved = (root / path).resolve()
    require(resolved != root and root in resolved.parents, 'artifact path escapes root: ' + name)
    return resolved


def artifact(root, item, seen):
    require(isinstance(item, dict) and {'path', 'sha256'} <= set(item), 'artifact requires path and sha256')
    require(isinstance(item['sha256'], str) and SHA.fullmatch(item['sha256']), 'invalid artifact SHA-256')
    path = safe_path(root, item['path'])
    require(path.is_file(), 'artifact is not a regular file: ' + item['path'])
    actual = digest(path.read_bytes())
    require(actual == item['sha256'], 'artifact hash mismatch: ' + item['path'])
    require(path not in seen or seen[path] == actual, 'conflicting artifact versions: ' + item['path'])
    seen[path] = actual
    return actual


def input_hash(packet):
    return digest(canonical(packet.get('inputs', [])))


def work_hash(packet):
    """Bind all declared work and completion scope, without a self-referential review."""
    return digest(canonical({k: v for k, v in packet.items() if k != "final_review"}))


def node_index(packet):
    require(isinstance(packet.get('nodes'), list), 'nodes must be an array')
    result = {}
    for node in packet['nodes']:
        require(isinstance(node, dict), 'node must be an object')
        name = node.get('id')
        require(isinstance(name, str) and ID.fullmatch(name), 'invalid node ID')
        require(name not in result, 'duplicate node ID: ' + name)
        require(node.get('kind') in KINDS, 'invalid node kind: ' + name)
        require(integer(node.get('version')), 'invalid node version: ' + name)
        require(isinstance(node.get('depends_on'), dict), 'depends_on must map IDs to versions: ' + name)
        require(isinstance(node.get('data'), dict), 'data must be an object: ' + name)
        result[name] = node
    return result


def descendants(seeds, nodes):
    result = set(seeds)
    while True:
        more = {name for name, node in nodes.items() if set(node['depends_on']) & result}
        if more <= result:
            return result
        result |= more


def ancestors(seeds, nodes):
    result = set(seeds)
    while True:
        more = {dep for name in result if name in nodes for dep in nodes[name]['depends_on']}
        if more <= result:
            return result
        result |= more


def packet_chain(root, packet, seen):
    chain = []
    hashes = set()
    current = packet
    while current.get('previous') is not None:
        require(len(chain) < 256, 'packet lineage exceeds 256 revisions')
        ref = current['previous']
        sha = artifact(root, ref, seen)
        require(sha not in hashes, 'cyclic packet lineage')
        hashes.add(sha)
        previous = read_json(safe_path(root, ref['path']))
        require(type(previous.get('schema')) is int and previous.get('schema') == SCHEMA, 'previous packet has unsupported schema')
        require(previous.get('task_id') == packet.get('task_id'), 'previous packet belongs to another task')
        require(integer(previous.get('revision')) and previous['revision'] + 1 == current['revision'], 'nonconsecutive packet revision')
        chain.append((sha, previous))
        current = previous
    require(current.get('revision') == 1, 'first packet must have revision 1')
    return chain


class Gate:
    def __init__(self, root, packet, stage, validate_history=True):
        self.root, self.packet, self.stage = root.resolve(), packet, stage
        self.blockers, self.seen = [], {}
        self.changed, self.invalidated = set(), set()
        self.chain = []
        self.validate_history = validate_history
        self.nodes = {}

    def block(self, code, message, return_to, ids=()):
        self.blockers.append({'code': code, 'message': message, 'return_to': return_to,
                              'affected_ids': sorted(set(ids))})

    def need(self, test, code, message, where, ids=()):
        if not test:
            self.block(code, message, where, ids)
        return bool(test)

    def evidence(self, value, name):
        try:
            artifact(self.root, value, self.seen)
            return True
        except (WorkError, OSError) as error:
            self.block('artifact', str(error), 'evidence', [name])
            return False

    def texts(self, data, keys, name, where):
        for key in keys:
            self.need(nonempty(data.get(key)), 'missing_work', name + ' requires ' + key, where, [name])

    def references(self, value, name, field, allow_empty=True):
        valid = isinstance(value, list) and all(isinstance(x, str) and x in self.nodes for x in value)
        valid = valid and len(value) == len(set(value)) and (allow_empty or bool(value))
        self.need(valid, 'reference', name + ' has invalid ' + field, 'recompute', [name])
        return value if valid else []

    def meaning_lookup(self, data, name):
        lookup = data.get('lookup', {})
        require(isinstance(lookup, dict), 'meaning lookup must be an object')
        outcome = lookup.get('outcome')
        self.need(outcome in {'located', 'access_blocked', 'locator_unresolved'}, 'lookup_outcome', 'meaning lookup must distinguish located, access-blocked and unresolved locator', 'meaning_location', [name])
        attempts = lookup.get('attempts')
        if not self.need(isinstance(attempts, list) and bool(attempts), 'lookup_attempts', 'meaning lookup needs actual ordered query/read records', 'meaning_location', [name]):
            return
        routes, results = [], []
        for attempt in attempts:
            require(isinstance(attempt, dict), 'lookup attempt must be an object')
            route, result = attempt.get('route'), attempt.get('result_kind')
            self.need(route in {'literal', 'normalized', 'concept_relation', 'context_read'}, 'lookup_route', 'invalid meaning-location route', 'meaning_location', [name])
            self.need(result in {'literal_only', 'incidental', 'candidate', 'verified_context', 'no_result', 'access_denied'}, 'lookup_result', 'classify actual returned relevance, not just tool use', 'meaning_location', [name])
            self.texts(attempt, ['query_or_locator', 'basis', 'observation'], name, 'meaning_location')
            self.evidence(attempt.get('evidence'), name)
            routes.append(route); results.append(result)
        self.lookup_leads(lookup, attempts, name)
        if outcome == 'located':
            self.need(data.get('status') == 'answered' and 'verified_context' in results, 'lookup_unverified', 'located meaning requires answered status and actual contextual-use evidence', 'meaning_location', [name])
            self.texts(lookup, ['referent', 'scope'], name, 'meaning_location')
        else:
            self.need(data.get('status') == 'blocked', 'lookup_status', 'unresolved meaning must remain blocked with evidence, not answered', 'meaning_location', [name])
            self.texts(lookup, ['remaining_unknown'], name, 'meaning_location')
            if outcome == 'access_blocked':
                self.need(results[-1] == 'access_denied', 'lookup_access', 'access blockage requires an actual terminal access denial', 'meaning_location', [name])
            else:
                # A direct concept/relationship search is allowed; no fixed count.
                self.need('concept_relation' in routes, 'lookup_relocation', 'unresolved locator needs an actual de-anchored concept/relationship route, not only literal results', 'meaning_location', [name])
                self.need(results[-1] != 'access_denied', 'lookup_access', 'terminal access denial must be reported as access_blocked', 'meaning_location', [name])
                self.texts(lookup, ['stop_basis', 'minimum_locator_question'], name, 'meaning_location')

    def lookup_leads(self, lookup, attempts, name):
        """Check declared leads only; neither discover omissions nor authenticate relevance."""
        self.evidence(lookup.get('lead_scan'), name)
        leads = lookup.get('leads')
        if not self.need(isinstance(leads, list), 'lookup_leads', 'lookup needs a material-lead scan and lead array', 'meaning_location', [name]):
            return
        if not leads:
            self.texts(lookup, ['no_material_leads'], name, 'meaning_location')
        seen, covered = set(), set()
        for lead in leads:
            require(isinstance(lead, dict), 'lookup lead must be an object')
            lid = lead.get('id')
            require(nonempty(lid) and lid not in seen, 'lookup lead IDs must be nonempty and unique')
            seen.add(lid)
            source = lead.get('source_attempt')
            valid_source = integer(source) and source <= len(attempts)
            self.need(valid_source, 'lead_source', 'lead must bind an actual one-indexed source attempt', 'meaning_location', [name])
            if valid_source:
                covered.add(source)
            self.texts(lead, ['source_locator', 'relation', 'relevance', 'basis'], name, 'meaning_location')
            self.evidence(lead.get('evidence'), name)
            follow = lead.get('followup_attempts', [])
            valid_follow = isinstance(follow, list) and all(integer(i) for i in follow)
            valid_follow = valid_follow and len(follow) == len(set(follow)) and valid_source and all(source < i <= len(attempts) for i in follow)
            self.need(valid_follow, 'lead_followup', 'followups must be distinct actual attempts after the lead source', 'meaning_location', [name])
            actual_follow = follow if valid_follow else []
            disposition = lead.get('disposition')
            self.need(disposition in {'checked', 'excluded', 'blocked', 'no_gain', 'conditional'}, 'lead_unreceived', 'material returned lead needs a supported disposition', 'meaning_location', [name])
            if disposition == 'checked':
                self.need(bool(actual_follow), 'lead_unchecked', 'checked lead requires a later actual query or read', 'meaning_location', [name])
                self.texts(lead, ['result'], name, 'meaning_location')
            elif disposition == 'blocked':
                self.texts(lead, ['constraint'], name, 'meaning_location')
                kind = lead.get('blockage_kind')
                self.need(kind in {'access', 'safety'}, 'lead_blockage', 'blockage must distinguish access from safety', 'meaning_location', [name])
                if kind == 'access':
                    indices = ([source] if valid_source else []) + actual_follow
                    self.need(any(attempts[i - 1].get('result_kind') == 'access_denied' for i in indices), 'lead_access', 'access blockage requires an actual bound access denial', 'meaning_location', [name])
                alternative = lead.get('safe_alternative', {})
                require(isinstance(alternative, dict), 'safe_alternative must be an object')
                self.need(alternative.get('decision') in {'attempted', 'unavailable', 'no_gain'}, 'lead_alternative', 'blocked lead requires a safe-alternative disposition', 'meaning_location', [name])
                self.texts(alternative, ['basis'], name, 'meaning_location')
                if alternative.get('decision') == 'attempted':
                    self.need(bool(actual_follow), 'lead_alternative', 'attempted safe alternative needs an actual later attempt', 'meaning_location', [name])
            elif disposition == 'conditional':
                self.texts(lead, ['remaining_unknown', 'next_condition', 'stop_basis'], name, 'meaning_location')
                self.need(bool(actual_follow) or nonempty(lead.get('constraint')), 'lead_conditional', 'conditional retention needs actual followup or a specific constraint', 'meaning_location', [name])
        for i, attempt in enumerate(attempts, 1):
            if attempt.get('result_kind') == 'candidate':
                self.need(i in covered or nonempty(attempt.get('nonmaterial_basis')), 'lead_coverage', 'candidate-bearing attempt needs lead coverage or a nonmaterial basis', 'meaning_location', [name])

    def question_delivery(self, data, name):
        delivery = data.get('delivery', {})
        require(isinstance(delivery, dict), 'question delivery must be an object')
        self.need(nonempty(delivery.get('text')) and delivery.get('text') == data.get('question'), 'question_text', 'delivery must preserve the exact registered question', 'questions', [name])
        expected = 'current_draft' if data.get('status') == 'ready' else 'prior_asked'
        self.need(delivery.get('mode') == expected, 'question_delivery', 'ready means this draft; asked means an actual prior question', 'questions', [name])
        ref = self.packet.get('draft') if expected == 'current_draft' else delivery.get('record')
        if expected == 'prior_asked' or self.stage == 'finalize':
            if self.evidence(ref, name):
                text = safe_path(self.root, ref['path']).read_text(encoding='utf-8')
                self.need(nonempty(delivery.get('text')) and delivery['text'] in text, 'question_not_delivered', 'exact registered question must appear in the bound draft or prior record', 'questions', [name])

    def transfer_acquisition(self, challenge, fid, disposition, changed, name):
        source = self.nodes.get(challenge, {})
        transfer = source.get('data', {}).get('transfer', {})
        if transfer.get('outcome') != 'candidate' or transfer.get('finding_id') != fid:
            return
        acquisition = disposition.get('acquisition', {})
        require(isinstance(acquisition, dict), 'transfer acquisition must be an object')
        mode = acquisition.get('mode')
        self.need(mode in {'grounded', 'no_gain', 'information'}, 'transfer_acquisition', 'candidate transfer requires explicit acquisition reception', 'information', [name])
        self.texts(acquisition, ['basis'], name, 'information')
        if mode in {'grounded', 'no_gain'}:
            self.evidence(acquisition.get('evidence'), name)
        elif mode == 'information':
            info_id = acquisition.get('information_id')
            info = self.nodes.get(info_id, {}) if isinstance(info_id, str) else {}
            if not self.need(info.get('kind') == 'information' and info_id in changed, 'transfer_information', 'transfer information must be an affected current information node', 'information', [name]):
                return
            data = info['data']
            expected = {'challenge': challenge, 'challenge_version': source['version'], 'finding_id': fid,
                        'transfer_sha256': digest(canonical(transfer))}
            origin = data.get('origin')
            self.need(origin == expected and isinstance(origin, dict) and type(origin.get('challenge_version')) is int, 'transfer_origin', 'information origin must bind this exact challenge, version, finding and full transfer hash', 'information', [info_id])
            distinction = data.get('discrimination', {})
            require(isinstance(distinction, dict), 'discrimination must be an object')
            self.texts(distinction, ['if_present', 'if_absent'], info_id, 'information')
            self.need(distinction.get('if_present') != distinction.get('if_absent'), 'transfer_discriminator', 'discriminator must declare differing consequences', 'information', [info_id])
            self.need(data.get('status') in {'answered', 'ready', 'asked', 'blocked', 'deferred'}, 'transfer_pending', 'received transfer information needs actual acquisition, delivery or evidenced constraints', 'information', [info_id])

    def decision_coverage(self, targets):
        """Bind declared recommendation roles; prose classification remains semantic review."""
        scope = self.packet.get('decision_scope', {})
        require(isinstance(scope, dict), 'decision_scope must be an object')
        roles = scope.get('targets', {})
        require(isinstance(roles, dict), 'decision target roles must be an object')
        self.need(set(roles) == set(targets), 'decision_coverage', 'declare the actual role of every current target', 'selection_review', targets)
        self.texts(scope, ['basis'], '@decision', 'selection_review')
        self.evidence(scope.get('artifact'), '@decision')
        for name in targets:
            role = roles.get(name)
            self.need(role in {'analysis', 'candidate', 'recommendation', 'user_directed'}, 'decision_role', 'invalid target role', 'selection_review', [name])
            node = self.nodes[name]
            if any(self.nodes[x]['kind'] == 'action' for x in ancestors({name}, self.nodes)):
                self.need(role in {'recommendation', 'user_directed'}, 'decision_action', 'an action outcome needs recommendation review or exact user direction', 'selection_review', [name])
            if role == 'user_directed':
                direction = node['data'].get('direction', {})
                require(isinstance(direction, dict), 'direction must be an object')
                self.texts(direction, ['instruction'], name, 'selection_review')
                sources = [x for x in self.packet['inputs'] if x.get('id') == direction.get('input_id')]
                self.need(len(sources) == 1, 'decision_direction', 'user-directed route must bind original input', 'selection_review', [name])
                if len(sources) == 1 and self.evidence(sources[0], name):
                    raw = safe_path(self.root, sources[0]['path']).read_text(encoding='utf-8')
                    self.need(nonempty(direction.get('instruction')) and direction['instruction'] in raw, 'decision_direction', 'exact user instruction must occur in bound input; quoting does not authenticate interpretation', 'selection_review', [name])
            elif role == 'recommendation':
                self.selection_comparison(name, node)

    def selection_comparison(self, name, node):
        data, deps = node['data'], node['depends_on']
        selection = data.get('selection', {})
        require(isinstance(selection, dict), 'recommendation selection must be an object')
        chosen = selection.get('chosen')
        alternatives = self.references(selection.get('alternatives'), name, 'alternatives')
        chosen_valid = isinstance(chosen, str) and chosen in self.nodes and self.nodes[chosen]['kind'] == 'proposal'
        self.need(chosen_valid, 'selection_chosen', 'recommendation must consume an actual candidate outcome', 'selection_review', [name])
        ids = ([chosen] if chosen_valid else []) + alternatives
        self.need(chosen not in alternatives and all(self.nodes[x]['kind'] == 'proposal' and x in deps for x in ids), 'selection_dependencies', 'recommendation consumes distinct current candidates', 'selection_review', [name])
        self.texts(selection, ['basis', 'switch_condition'], name, 'selection_review')
        if not alternatives:
            self.texts(selection, ['no_alternative_basis'], name, 'selection_review')
        mode = selection.get('mode')
        self.need(mode in {'conditional', 'commit'}, 'selection_mode', 'preference must distinguish conditional feasibility from commitment', 'selection_review', [name])
        if mode == 'commit' and chosen_valid:
            self.need(self.nodes[chosen]['data'].get('feasibility') == 'supported', 'selection_unsupported', 'commit requires supported feasibility', 'selection_review', [name])
            chain = ancestors({name}, self.nodes)
            unresolved = {x for x, n in self.nodes.items() if n['kind'] == 'information' and n['data'].get('status') != 'answered' and (x in chain or bool(set(n['data'].get('required_for', [])) & chain))}
            self.need(not unresolved, 'commit_information', 'commit cannot consume unresolved information', 'information', unresolved)
        review = selection.get('comparison', {})
        require(isinstance(review, dict), 'comparison must be an object')
        self.evidence(review.get('artifact'), name)
        self.texts(review, ['criterion', 'preference', 'scope'], name, 'selection_review')
        expected = {x: self.nodes[x]['version'] for x in ids}
        versions = review.get('candidate_versions')
        self.need(isinstance(versions, dict) and versions == expected and all(type(v) is int for v in versions.values()), 'comparison_stale', 'comparison must bind exact chosen and alternative versions', 'selection_review', [name])
        premises = review.get('premises')
        if not self.need(isinstance(premises, list) and bool(premises), 'comparison_premises', 'receive the material comparison basis before preference, including a justified no-acquisition route', 'selection_review', [name]):
            return
        seen = set()
        for premise in premises:
            require(isinstance(premise, dict), 'comparison premise must be an object')
            pid = premise.get('id')
            require(nonempty(pid) and pid not in seen, 'comparison premise IDs must be unique')
            seen.add(pid)
            self.texts(premise, ['claim', 'if_false', 'basis'], name, 'selection_review')
            coverage = self.references(premise.get('candidate_ids'), name, 'candidate_ids', False)
            self.need(set(coverage) <= set(ids), 'comparison_scope', 'premise must concern candidates in this comparison', 'selection_review', [name])
            route = premise.get('route')
            self.need(route in {'information', 'existing', 'derivation', 'no_gain', 'not_material'}, 'comparison_route', 'route the actual comparison premise', 'selection_review', [name])
            self.evidence(premise.get('evidence'), name)
            if route == 'information':
                iid = premise.get('information_id')
                info = self.nodes.get(iid, {}) if isinstance(iid, str) else {}
                valid = info.get('kind') == 'information' and iid in deps
                self.need(valid, 'comparison_information', 'comparison must consume current information, not cite unrelated research', 'selection_review', [name])
                if not valid:
                    continue
                result = premise.get('reception', {})
                require(isinstance(result, dict), 'comparison reception must be an object')
                self.texts(result, ['relevance_basis', 'effect_on_preference', 'remaining_limits'], name, 'selection_review')
                relevance = result.get('relevance')
                self.need(relevance in {'direct', 'partial', 'irrelevant', 'contradictory', 'unavailable'}, 'comparison_relevance', 'classify result against this exact premise', 'selection_review', [name])
                status = info['data'].get('status')
                if info['data'].get('owner') == 'public':
                    self.need(status in {'answered', 'blocked'}, 'comparison_public_pending', 'conditional preference does not waive available public acquisition', 'evidence', [iid])
                if status == 'answered':
                    self.need(relevance in {'direct', 'contradictory'}, 'comparison_insufficient', 'partial or irrelevant research does not close the comparison premise', 'selection_review', [name])
                else:
                    self.texts(result, ['condition', 'next_step'], name, 'selection_review')
            elif route == 'existing':
                self.texts(premise, ['source_locator', 'support_scope'], name, 'selection_review')
            elif route == 'derivation':
                self.texts(premise, ['derivation', 'assumptions'], name, 'selection_review')
            else:
                self.texts(premise, ['why_no_acquisition', 'boundary'], name, 'selection_review')
        covered = {x for premise in premises for x in premise.get('candidate_ids', []) if isinstance(x, str)}
        self.need(chosen in covered, 'comparison_chosen_uncovered', 'the preferred candidate itself needs a received comparison basis', 'selection_review', [name])

    def run(self):
        p = self.packet
        require(isinstance(p, dict) and type(p.get('schema')) is int and p.get('schema') == SCHEMA, 'unsupported packet schema')
        require(nonempty(p.get('task_id')) and integer(p.get('revision')), 'task_id and positive revision required')
        require(p.get('phase') in {'analysis', 'plan'}, 'phase must be analysis or plan')
        require(isinstance(p.get('inputs'), list) and p['inputs'], 'nonempty original inputs required')
        ids = set()
        for source in p['inputs']:
            require(isinstance(source, dict) and nonempty(source.get('id')), 'input requires ID')
            require(source['id'] not in ids, 'duplicate input ID')
            ids.add(source['id'])
            require(source.get('status') in {'observed', 'reported', 'inferred', 'unknown'}, 'input status must preserve epistemic type')
            require(nonempty(source.get('locator')) and nonempty(source.get('precision')), 'input locator and original precision required')
            self.evidence(source, source['id'])
        self.nodes = node_index(p)
        self.chain = packet_chain(self.root, p, self.seen)
        if self.validate_history:
            for _, previous in self.chain:
                historical, historic_gate = evaluate(self.root, previous, 'settle', validate_history=False)
                self.seen.update(historic_gate.seen)
                self.need(historical['ok'], 'invalid_history', 'previous packet failed its settle gates; repair and preserve a valid lineage', 'repair_packet')
        targets = self.references(p.get('targets'), '@packet', 'targets', False)
        require(all(self.nodes[x]['kind'] in {'relation', 'point', 'proposal', 'action', 'output'} for x in targets), 'targets must be deliverable nodes')
        closure = ancestors(targets, self.nodes)
        for name, node in self.nodes.items():
            for dep, version in node['depends_on'].items():
                self.need(dep in self.nodes and integer(version), 'reference', 'missing or invalid dependency ' + str(dep), 'recompute', [name])
                if dep in self.nodes:
                    self.need(version == self.nodes[dep]['version'], 'stale_dependency', name + ' consumed an old ' + dep, 'recompute', descendants({name}, self.nodes))
        visiting, visited = set(), set()
        def visit(name):
            require(name not in visiting, 'dependency cycle: ' + name)
            if name in visited:
                return
            visiting.add(name)
            for dep in self.nodes[name]['depends_on']:
                if dep in self.nodes:
                    visit(dep)
            visiting.remove(name)
            visited.add(name)
        for name in self.nodes:
            visit(name)
        if self.chain:
            prior = self.chain[0][1]
            old = node_index(prior)
            for name, node in self.nodes.items():
                if name in old:
                    a, b = copy.deepcopy(old[name]), copy.deepcopy(node)
                    av, bv = a.pop('version'), b.pop('version')
                    changed = a != b
                    self.need(bv == av + int(changed), 'revision', 'node version must advance exactly when its content changes: ' + name, 'recompute', [name])
                    if changed:
                        self.changed.add(name)
                else:
                    self.need(node['version'] == 1, 'revision', 'new node must start at version 1', 'recompute', [name])
                    self.changed.add(name)
            removed = set(old) - set(self.nodes)
            retirements = p.get('retirements', {})
            require(isinstance(retirements, dict), 'retirements must be an object')
            for name in removed:
                record = retirements.get(name, {})
                if self.need(isinstance(record, dict) and record.get('reason') in {'superseded', 'value_ended'} and nonempty(record.get('explanation')), 'dropped_work', 'removed node needs evidence-backed retirement: ' + name, 'reception', [name]):
                    self.evidence(record.get('evidence'), name)
            self.changed |= removed
            self.invalidated = descendants(self.changed, {**old, **self.nodes})
            if input_hash(prior) != input_hash(p):
                scan = p.get('reopen', {})
                self.need(isinstance(scan, dict) and scan.get('input_hash') == input_hash(p), 'reopen', 'changed original inputs require current scope discovery', 'scope_discovery', self.nodes)
                if isinstance(scan, dict):
                    assessed = scan.get('assessed_ids', [])
                    expected = {x for x, n in {**old, **self.nodes}.items() if n['kind'] in {'relation', 'output', 'point', 'proposal', 'action', 'information'}}
                    self.need(isinstance(assessed, list) and set(assessed) == expected, 'reopen_coverage', 'scope discovery must assess all existing/new deliverable and information IDs', 'scope_discovery', expected)
                    affected = self.references(scan.get('affected_ids'), '@reopen', 'affected_ids')
                    self.texts(scan, ['basis'], '@reopen', 'scope_discovery')
                    self.evidence(scan.get('evidence'), '@reopen')
                    self.invalidated |= descendants(affected, self.nodes)
                    for affected_id in affected:
                        if affected_id in old:
                            self.need(self.nodes[affected_id]['version'] > old[affected_id]['version'], 'scope_not_recomputed', 'affected node must be updated or explicitly revalidated with changed content: ' + affected_id, 'recompute', [affected_id])
                self.invalidated |= {x for x, n in self.nodes.items() if n['kind'] in {'challenge', 'reception'}}
        else:
            self.need(all(n['version'] == 1 for n in self.nodes.values()), 'revision', 'first-packet nodes must start at version 1', 'recompute', self.nodes)
        relations = {x for x in closure if x in self.nodes and self.nodes[x]['kind'] == 'relation'}
        for target in targets:
            self.need(bool(ancestors({target}, self.nodes) & relations), 'relation_missing', 'each deliverable needs its own generating relation', 'generation', [target])
        acquisition = p.get('acquisition', {})
        require(isinstance(acquisition, dict), 'acquisition must be an object')
        self.need(acquisition.get('input_hash') == input_hash(p), 'acquisition_stale', 'source routing must bind current inputs', 'source_routing')
        self.evidence(acquisition.get('source_scan'), '@acquisition')
        for owner in ['public', 'user']:
            expected = {x for x, n in self.nodes.items() if n['kind'] == 'information' and n['data'].get('owner') == owner}
            actual = acquisition.get(owner + '_ids')
            self.need(isinstance(actual, list) and len(actual) == len(set(actual)) and set(actual) == expected, 'acquisition_coverage', 'source routing must cover all ' + owner + ' information', 'source_routing', expected)
        if acquisition.get('public_ids') == []:
            self.texts(acquisition, ['no_public_basis'], '@acquisition', 'source_routing')
        challenges, receptions, operations = {}, {}, []
        pending = []
        user_batches = []
        for name, node in self.nodes.items():
            data, kind, deps = node['data'], node['kind'], node['depends_on']
            if kind == 'relation':
                self.need(data.get('status') in {'candidate', 'established'}, 'epistemic_type', 'relation must be candidate or established', 'generation', [name])
                self.texts(data, ['prior_state', 'state_conditions', 'transformation', 'intermediate_result', 'result', 'scope', 'prediction', 'counterexample', 'unresolved'], name, 'generation')
                feedback = data.get('feedback', {})
                self.need(isinstance(feedback, dict) and feedback.get('mode') in {'present', 'not_applicable'} and nonempty(feedback.get('description')), 'feedback', 'feedback must describe next state or explain non-applicability; it is not a DAG edge', 'generation', [name])
                sources = data.get('sources')
                self.need(isinstance(sources, list) and sources and all(x in ids for x in sources), 'source', 'relation must cite current input IDs', 'evidence', [name])
                if data.get('status') == 'established':
                    self.evidence(data.get('support'), name)
                    candidates = {x for x in ancestors(set(deps), self.nodes) if self.nodes.get(x, {}).get('kind') == 'relation' and self.nodes[x]['data'].get('status') == 'candidate'}
                    self.need(not candidates, 'candidate_promoted', 'an established relation cannot rest on candidate premises', 'evidence', candidates | {name})
            elif kind == 'operation':
                self.texts(data, ['target_result', 'unrepresented_difference', 'selected', 'strongest_alternative', 'choice_basis', 'delta'], name, 'operation')
                self.need(data.get('delta_kind') in {'added', 'weakened', 'excluded', 'reframed', 'none', 'stop'}, 'operation_delta', 'operation must name its actual increment or honest none/stop', 'operation', [name])
                used = {x for x in deps if x in self.nodes and self.nodes[x]['kind'] == 'relation'}
                self.need(bool(used), 'operation_relation', 'operation must bind relation versions', 'operation', [name])
                self.references(data.get('updates'), name, 'updates')
                self.evidence(data.get('artifact'), name)
                operations.append(used)
            elif kind == 'challenge':
                self.need(data.get('input_hash') == input_hash(p), 'stale_challenge', 'challenge must bind the current raw input manifest', 'challenge', [name])
                self.need(data.get('mode') in {'isolated_branch', 'serial_rebuild'}, 'challenge_mode', 'declare actual isolated_branch or serial_rebuild mode', 'challenge', [name])
                self.texts(data, ['raw_input_basis'], name, 'challenge')
                self.evidence(data.get('artifact'), name)
                if data.get('mode') == 'isolated_branch':
                    self.evidence(data.get('isolation_record'), name)
                self.need('independent' not in data, 'identity_claim', 'independent labels are unsupported; use declared mode and host records', 'challenge', [name])
                findings = data.get('findings', [])
                valid = isinstance(findings, list) and bool(findings)
                self.need(valid, 'challenge_missing', 'challenge needs specific findings', 'challenge', [name])
                fids = set()
                if valid:
                    for finding in findings:
                        require(isinstance(finding, dict) and nonempty(finding.get('id')), 'finding requires an ID')
                        require(finding['id'] not in fids, 'duplicate finding ID')
                        fids.add(finding['id'])
                        self.texts(finding, ['claim', 'distinguishing_fact'], name, 'challenge')
                        self.need(nonempty(finding.get('competing_representation')) or nonempty(finding.get('cross_surface_prediction')), 'unchallenged_model', 'finding needs a competing representation or cross-surface prediction', 'challenge', [name])
                transfer = data.get('transfer', {})
                require(isinstance(transfer, dict), 'transfer must be an object')
                self.need(transfer.get('outcome') in {'candidate', 'no_useful', 'not_selected'}, 'transfer_missing', 'challenge must return a reconstruction product and conditional transfer disposition', 'representation_handoff', [name])
                self.evidence(transfer.get('artifact'), name)
                if transfer.get('outcome') == 'not_selected':
                    # Cross-surface transfer is optional; raw-input reconstruction and
                    # complete reception remain mandatory in controlled mode.
                    self.texts(transfer, ['selected_operation', 'selection_basis', 'search_result', 'value_basis'], name, 'representation_handoff')
                else:
                    self.texts(transfer, ['source_surface', 'shared_relation', 'search_result', 'value_basis'], name, 'representation_handoff')
                if transfer.get('outcome') == 'candidate':
                    self.texts(transfer, ['other_surface', 'prediction', 'discriminator', 'failure_boundary'], name, 'representation_handoff')
                    self.need(transfer.get('finding_id') in fids, 'transfer_reception', 'transfer candidate must enter a finding and its reception', 'reception', [name])
                challenges[name] = fids
            elif kind == 'reception':
                receptions[name] = node
            elif kind == 'information':
                self.need(data.get('owner') in {'public', 'user'}, 'information_owner', 'information owner must be public or user', 'information', [name])
                self.need(data.get('status') in {'open', 'answered', 'blocked', 'ready', 'asked', 'deferred'}, 'information_status', 'invalid information status', 'information', [name])
                self.texts(data, ['question'], name, 'information')
                required = set(self.references(data.get('required_for'), name, 'required_for'))
                # Forward dependency edges consume an information premise even if
                # the optional reverse registration omits that consumer.
                required |= {key for key, item in self.nodes.items() if name in item['depends_on']}
                status = data.get('status')
                if status in {'answered', 'blocked'}:
                    self.evidence(data.get('evidence'), name)
                    self.texts(data, ['result'], name, 'information')
                if status == 'blocked':
                    self.texts(data, ['attempt', 'constraint'], name, 'information')
                if status != 'answered':
                    affected = descendants(set(required), self.nodes) & closure
                    established = {x for x in affected if self.nodes[x]['data'].get('status') == 'established'}
                    self.need(not established, 'blocked_information_claim', 'unresolved necessary information cannot support established premises or completion', 'evidence' if data.get('owner') == 'public' else 'questions', established)
                if status not in {'answered', 'blocked'}:
                    pending.append((name, set(required), status, data.get('owner')))
                if data.get('owner') == 'public':
                    self.need(data.get('acquisition_kind') in {'fact', 'meaning_location'}, 'acquisition_kind', 'public work must distinguish ordinary fact from meaning-location', 'source_routing', [name])
                    if data.get('acquisition_kind') == 'meaning_location':
                        self.meaning_lookup(data, name)
                    relevant = descendants(set(required), self.nodes) & closure
                    self.need(not relevant or status in {'answered', 'blocked'}, 'public_acquisition_pending', 'material public facts require actual acquisition or evidenced blockage before settling', 'evidence', relevant)
                    self.need(status in {'open', 'answered', 'blocked'}, 'information_status', 'public facts cannot be marked asked/deferred', 'evidence', [name])
                elif status in {'ready', 'asked'}:
                    self.need(integer(data.get('batch')), 'question_batch', 'asked user facts need a question batch', 'questions', [name])
                    if status == 'asked':
                        self.evidence(data.get('evidence'), name)
                    if status == 'ready' or 'origin' in data:
                        self.question_delivery(data, name)
                    user_batches.append((name, data.get('batch')))
                elif status == 'deferred':
                    after = data.get('after')
                    parent = self.nodes.get(after, {}) if isinstance(after, str) else {}
                    self.need(parent.get('kind') == 'information' and parent.get('data', {}).get('owner') == 'user' and parent.get('data', {}).get('status') in {'open', 'ready', 'asked', 'deferred'} and after in deps, 'invalid_deferral', 'deferred question requires a versioned, unanswered user-information dependency', 'questions', [name])
                    self.texts(data, ['necessary_after'], name, 'questions')
            elif kind == 'point':
                self.need(any(x in self.nodes and self.nodes[x]['kind'] == 'relation' for x in deps), 'point_relation', 'point must map to a generating relation', 'generation', [name])
                self.texts(data, ['changed_state', 'mechanism', 'adoption', 'result', 'comparison', 'scope'], name, 'points')
            elif kind == 'proposal':
                self.need(any(x in self.nodes and self.nodes[x]['kind'] in {'relation', 'point'} for x in deps), 'proposal_relation', 'concrete proposal must bind a relation or intervention point', 'proposals', [name])
                self.texts(data, ['actor', 'situation', 'input', 'transformation', 'first_deliverable', 'use_path', 'expected_result', 'assumptions', 'limits'], name, 'proposals')
                self.evidence(data.get('artifact'), name)
                self.need(data.get('feasibility') in {'conditional', 'supported'}, 'proposal_feasibility', 'proposal feasibility must remain conditional or carry support', 'proposals', [name])
                if data.get('feasibility') == 'supported':
                    self.evidence(data.get('support'), name)
            elif kind == 'action':
                self.need(any(x in self.nodes and self.nodes[x]['kind'] == 'point' for x in deps), 'action_point', 'action must map to a point', 'actions', [name])
                self.texts(data, ['operation', 'adoption', 'result', 'comparison'], name, 'actions')
                selection = data.get('selection', {})
                require(isinstance(selection, dict), 'action selection must be an object')
                self.texts(selection, ['basis', 'switch_condition'], name, 'actions')
                chosen = selection.get('chosen')
                alternatives = self.references(selection.get('alternatives'), name, 'alternatives')
                chosen_valid = isinstance(chosen, str) and chosen in self.nodes and self.nodes[chosen]['kind'] == 'proposal'
                self.need(chosen_valid, 'selection_chosen', 'action must choose an actual concrete proposal', 'actions', [name])
                selected = ([chosen] if chosen_valid else []) + alternatives
                self.need(chosen not in alternatives and all(self.nodes[x]['kind'] == 'proposal' and x in deps for x in selected), 'selection_dependencies', 'chosen and alternative proposals must be distinct direct current dependencies', 'actions', [name])
                if not alternatives:
                    self.texts(selection, ['no_alternative_basis'], name, 'actions')
                mode = selection.get('mode')
                self.need(mode in {'conditional', 'commit'}, 'selection_mode', 'selection must distinguish conditional exploration from commitment', 'actions', [name])
                if mode == 'commit' and chosen_valid:
                    self.need(self.nodes[chosen]['data'].get('feasibility') == 'supported', 'selection_unsupported', 'commit requires a supported chosen proposal', 'actions', [name])
                    chain = ancestors({name}, self.nodes)
                    unresolved = {x for x, n in self.nodes.items() if n['kind'] == 'information' and n['data'].get('status') != 'answered' and (x in chain or bool(set(n['data'].get('required_for', [])) & chain))}
                    self.need(not unresolved, 'commit_information', 'commit cannot rely on unresolved necessary information', 'information', unresolved)

            elif kind == 'output':
                self.texts(data, ['claim'], name, 'compose')
                self.need(data.get('status') in {'conditional', 'established'}, 'output_status', 'output must be conditional or established', 'compose', [name])
                if data.get('status') == 'established':
                    upstream = ancestors({name}, self.nodes)
                    candidates = {x for x in upstream if self.nodes.get(x, {}).get('kind') == 'relation' and self.nodes[x]['data'].get('status') == 'candidate'}
                    self.need(not candidates, 'candidate_promoted', 'candidate relations cannot support an established output without being established', 'evidence', candidates | {name})
        for name, node in receptions.items():
            data, deps = node['data'], node['depends_on']
            challenge = data.get('challenge')
            self.need(challenge in challenges and challenge in deps, 'reception_binding', 'reception must bind a current challenge version', 'reception', [name])
            dispositions = data.get('dispositions', {})
            require(isinstance(dispositions, dict), 'dispositions must be an object')
            expected = challenges.get(challenge, set())
            self.need(set(dispositions) == expected, 'unreceived_findings', 'every challenge finding needs exactly one disposition', 'reception', [name])
            for fid, disposition in dispositions.items():
                require(isinstance(disposition, dict), 'disposition must be an object')
                self.need(disposition.get('decision') in {'incorporated', 'excluded', 'conditional'}, 'disposition', 'finding requires incorporated/excluded/conditional disposition', 'reception', [name])
                self.texts(disposition, ['basis'], name, 'reception')
                changed = self.references(disposition.get('affected_ids'), name, 'affected_ids', disposition.get('decision') == 'excluded')
                self.need(all(self.nodes[x]['kind'] in {'relation', 'information', 'point', 'proposal', 'action', 'output'} for x in changed), 'reception_destination', 'disposition must update cognitive, information or deliverable nodes, not process records', 'reception', changed)
                self.evidence(disposition.get('evidence'), name)
                versions = disposition.get('updated_versions', {})
                self.need(isinstance(versions, dict) and set(versions) == set(changed) and all(versions[x] == self.nodes[x]['version'] for x in changed), 'reception_update', 'disposition must bind affected outputs to their current versions', 'recompute', changed)
                self.transfer_acquisition(challenge, fid, disposition, changed, name)
        received = {n['data'].get('challenge') for n in receptions.values()}
        self.need(bool(challenges) and set(challenges) <= received, 'unreceived_challenge', 'settling requires a received current-input challenge', 'challenge' if not challenges else 'reception', challenges)
        covered = set().union(*operations) if operations else set()
        self.need(relations <= covered, 'missing_operation', 'each target relation needs a completed version-bound operation', 'operation', relations - covered)
        for name, required, status, owner in pending:
            affected = descendants(required, self.nodes) & set(targets)
            for target in list(affected):
                data = self.nodes[target]['data']
                treatment = data.get('conditional_on', {}).get(name, {}) if isinstance(data.get('conditional_on', {}), dict) else {}
                conditional = (self.nodes[target]['kind'] not in {'proposal', 'action'} and data.get('status') in {'candidate', 'conditional'}) or (self.nodes[target]['kind'] == 'proposal' and data.get('feasibility') == 'conditional') or (self.nodes[target]['kind'] == 'action' and isinstance(data.get('selection'), dict) and data['selection'].get('mode') == 'conditional')
                if conditional and isinstance(treatment, dict) and all(nonempty(treatment.get(k)) for k in ['assumption', 'alternative', 'next_step']):
                    affected.remove(target)
            self.need(not affected, 'information_open', 'unresolved information blocks only its dependent targets: ' + name, 'evidence' if owner == 'public' else 'questions', affected)
        batches = {batch for _, batch in user_batches}
        self.need(len(batches) <= 1, 'question_batches', 'independent current unanswered user questions must share a batch; dependent ones use deferred', 'questions', [x for x, _ in user_batches])
        if self.stage in {'select', 'plan', 'finalize'}:
            self.decision_coverage(targets)
        if self.stage == 'plan' or (self.stage == 'finalize' and p['phase'] == 'plan'):
            self.need(any(self.nodes[x]['kind'] == 'action' for x in closure if x in self.nodes), 'action_missing', 'plan completion requires a mapped action', 'actions', targets)
        if self.stage == 'finalize':
            self.evidence(p.get('draft'), '@draft')
            self.need(p.get('draft_targets') == targets, 'draft_binding', 'draft_targets must exactly match checked targets', 'compose', targets)
            review = p.get('final_review', {})
            require(isinstance(review, dict), 'final_review must be an object')
            self.evidence(review.get('artifact'), '@final_review')
            self.need(review.get('draft_sha256') == p.get('draft', {}).get('sha256') and review.get('input_hash') == input_hash(p), 'stale_review', 'final review must bind current draft bytes and original inputs', 'review')
            self.need(review.get('work_hash') == work_hash(p), 'stale_work_review', 'final review must bind all current work, versions and completion scope', 'review')
            self.need(review.get('mode') in {'self', 'peer'}, 'review_mode', 'final review must declare self or peer', 'review')
            if review.get('mode') == 'peer':
                self.evidence(review.get('execution_record'), '@final_review')
            self.texts(review, ['outside_model_attempt', 'limits'], '@final_review', 'review')
            self.need(review.get('verdict') == 'ready' and review.get('blockers') == [] and review.get('return_to') == [], 'review_blocked', 'final review must be ready with no unresolved blockers or return destinations', 'review')
        return self.result()

    def result(self):
        return {'ok': not self.blockers, 'stage': self.stage, 'blockers': self.blockers,
                'changed_ids': sorted(self.changed), 'invalidated_ids': sorted(self.invalidated),
                'preserved_ids': sorted(set(self.nodes) - self.invalidated), 'limits': LIMITS}


def evaluate(root, packet, stage='finalize', validate_history=True):
    gate = Gate(Path(root), packet, stage, validate_history)
    try:
        result = gate.run()
    except (WorkError, OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        gate.block('invalid_packet', str(error), 'repair_packet')
        result = gate.result()
    return result, gate


def stable(gate):
    for path, sha in gate.seen.items():
        require(path.is_file() and digest(path.read_bytes()) == sha, 'artifact changed during check: ' + str(path))


def atomic_write(path, data, exclusive=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name + '.', delete=False) as handle:
            tmp = Path(handle.name)
            handle.write(canonical(data) + b'\n')
            handle.flush()
            os.fsync(handle.fileno())
        if exclusive:
            os.link(tmp, path)  # Atomic no-replace publication; unsupported filesystems fail closed.
        else:
            os.replace(tmp, path)
        if os.name == 'posix':
            fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def finalize(root, packet_path, receipt_path, ledger_name='.cognitive-ledger.json'):
    root = Path(root).resolve()
    packet_file, receipt_file = safe_path(root, packet_path), safe_path(root, receipt_path)
    ledger_file = safe_path(root, ledger_name)
    require(len({packet_file, receipt_file, ledger_file}) == 3, 'packet, receipt, and ledger must be distinct')
    lock = ledger_file.with_name(ledger_file.name + '.lock')
    require(not lock.is_symlink(), 'ledger lock must not be a symlink')
    try:
        lock.mkdir()
    except FileExistsError as error:
        raise WorkError('ledger busy or interrupted writer; inspect lock before retry') from error
    try:
        raw = packet_file.read_bytes()
        packet_sha = digest(raw)
        packet = read_json(packet_file)
        result, gate = evaluate(root, packet, 'finalize')
        if not result['ok']:
            return result
        gate.seen[packet_file] = packet_sha
        head = read_json(ledger_file) if ledger_file.exists() else None
        if head:
            require(head.get('task_id') == packet['task_id'], 'ledger belongs to another task')
            require(head.get('packet_sha256') in {sha for sha, _ in gate.chain} and packet['revision'] > head.get('revision', 0), 'stale or repeated finalize: current ledger head must be in validated ancestry')
        else:
            require(packet['revision'] == 1 or bool(gate.chain), 'new ledger requires valid lineage rooted at revision 1')
        require(not receipt_file.exists(), 'receipt already exists; never overwrite an approval')
        require(receipt_file not in gate.seen and ledger_file not in gate.seen, 'outputs must not overwrite an input or evidence artifact')
        stable(gate)
        receipt = {'schema': SCHEMA, 'kind': 'cognitive_receipt', 'task_id': packet['task_id'],
                   'revision': packet['revision'], 'created_at': datetime.now(timezone.utc).isoformat(),
                   'packet': {'path': packet_path, 'sha256': packet_sha}, 'input_hash': input_hash(packet),
                   'draft': packet['draft'], 'targets': packet['targets'], 'ledger': ledger_name,
                   'previous_head': head.get('packet_sha256') if head else None, 'limits': LIMITS}
        atomic_write(receipt_file, receipt, exclusive=True)
        # Receipt publication precedes head commit. A crash in between leaves a visibly
        # uncommitted receipt: verify rejects it. Never report that state as approved.
        atomic_write(ledger_file, {'schema': SCHEMA, 'task_id': packet['task_id'], 'revision': packet['revision'],
                                  'packet_sha256': packet_sha, 'receipt': receipt_path,
                                  'receipt_sha256': digest(receipt_file.read_bytes())})
        result.update({'receipt': receipt_path, 'draft_sha256': packet['draft']['sha256'], 'packet_sha256': packet_sha})
        return result
    finally:
        lock.rmdir()


def verify(root, receipt_path):
    root = Path(root).resolve()
    file = safe_path(root, receipt_path)
    receipt = read_json(file)
    require(receipt.get('kind') == 'cognitive_receipt' and type(receipt.get('schema')) is int and receipt.get('schema') == SCHEMA, 'invalid receipt')
    seen = {}
    artifact(root, receipt.get('packet'), seen)
    ledger = read_json(safe_path(root, receipt.get('ledger')))
    require(ledger.get('receipt') == receipt_path and ledger.get('receipt_sha256') == digest(file.read_bytes()), 'receipt is not the current committed ledger head')
    require(ledger.get('packet_sha256') == receipt['packet']['sha256'], 'receipt/ledger packet mismatch')
    packet = read_json(safe_path(root, receipt['packet']['path']))
    result, gate = evaluate(root, packet, 'finalize')
    require(receipt.get('draft') == packet.get('draft') and receipt.get('targets') == packet.get('targets') and receipt.get('input_hash') == input_hash(packet), 'receipt bindings changed')
    stable(gate)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ['check', 'finalize', 'verify']:
        p = sub.add_parser(command)
        p.add_argument('file', help='packet or receipt path relative to --root')
        p.add_argument('--root', type=Path, default=Path.cwd())
        if command == 'check':
            p.add_argument('--stage', choices=['settle', 'select', 'plan', 'finalize'], default='settle')
        if command == 'finalize':
            p.add_argument('--receipt', required=True)
            p.add_argument('--ledger', default='.cognitive-ledger.json')
    for command in ['hash', 'input-hash', 'work-hash', 'transfer-hash']:
        p = sub.add_parser(command)
        p.add_argument('file', type=Path)
        if command == 'transfer-hash':
            p.add_argument('--challenge', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'hash':
            result = {'sha256': digest(args.file.read_bytes())}
        elif args.command == 'input-hash':
            result = {'input_hash': input_hash(read_json(args.file))}
        elif args.command == 'work-hash':
            result = {'work_hash': work_hash(read_json(args.file))}
        elif args.command == 'transfer-hash':
            node = node_index(read_json(args.file)).get(args.challenge, {})
            require(node.get('kind') == 'challenge', 'transfer-hash requires a challenge ID')
            require(isinstance(node['data'].get('transfer'), dict), 'challenge requires transfer')
            result = {'transfer_sha256': digest(canonical(node['data']['transfer']))}
        elif args.command == 'check':
            result, gate = evaluate(args.root, read_json(safe_path(args.root.resolve(), args.file)), args.stage)
            stable(gate)
        elif args.command == 'finalize':
            result = finalize(args.root, args.file, args.receipt, args.ledger)
        else:
            result = verify(args.root, args.file)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get('ok', True) else 2
    except (WorkError, OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        print(json.dumps({'ok': False, 'blockers': [{'code': 'io_or_binding', 'message': str(error), 'return_to': 'repair_packet', 'affected_ids': []}], 'limits': LIMITS}, ensure_ascii=False, indent=2))
        return 2


if __name__ == '__main__':
    sys.exit(main())
