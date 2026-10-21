#!/usr/bin/env python3
"""Optional ordinary-chat artifact adapter. Identity/version gates, never semantics.

No model, network, execution of supplied code, or host message interception.
All artifacts are relative to a separate task root. Keep task data outside the skill.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from contextlib import contextmanager

KINDS = {'source', 'relation', 'information', 'point', 'proposal', 'action', 'output', 'challenge', 'reception'}
STATES = {'reported', 'observed', 'public', 'candidate', 'inferred', 'supported', 'unknown', 'ready', 'asked', 'answered', 'blocked', 'conditional', 'stale'}
ID = re.compile(r'^[A-Za-z0-9_.:-]+$')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf8')


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def unique(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, 'Duplicate JSON key: ' + key)
        out[key] = value
    return out


def load(path):
    return json.loads(path.read_text(encoding='utf8'), object_pairs_hook=unique,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Non-finite JSON')))


def path(root, name):
    require(isinstance(name, str) and bool(name) and not Path(name).is_absolute(), 'Artifact path must be relative')
    p = (root / name).resolve()
    require(p.is_relative_to(root.resolve()) and p != root.resolve(), 'Path escapes task root')
    return p


def ref(root, name):
    p = path(root, name)
    require(p.is_file(), 'Missing artifact: ' + name)
    return {'path': name, 'sha256': digest(p.read_bytes())}


def artifact(root, value):
    require(isinstance(value, dict) and set(value) == {'path', 'sha256'}, 'Invalid artifact reference')
    resolved = path(root, value['path'])
    require(resolved not in {path(root, 'current-work.json'), path(root, '.current-work-next.json')}, 'Mutable control file cannot be an artifact')
    require(re.fullmatch(r'[0-9a-f]{64}', value['sha256'] or '') is not None, 'Invalid artifact hash')
    require(ref(root, value['path']) == value, 'Artifact bytes changed: ' + value['path'])


def text(value):
    return isinstance(value, str) and bool(value.strip())


def write_new(root, name, value):
    p = path(root, name)
    require(p not in {path(root, 'current-work.json'), path(root, '.current-work-next.json')} and not p.is_relative_to(path(root, '.current-work-lock')), 'Reserved control destination')
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x', encoding='utf8') as f:
        json.dump(value, f, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        f.write('\n')
    return ref(root, name)


@contextmanager
def lock(root):
    p = path(root, '.current-work-lock')
    try:
        p.mkdir()
    except FileExistsError as exc:
        raise ValueError('Task locked; verify no writer before recovering a stale lock') from exc
    try:
        yield
    finally:
        p.rmdir()


def pointer(root):
    p = load(path(root, 'current-work.json'))
    require(isinstance(p, dict) and set(p) == {'snapshot'}, 'Invalid current pointer')
    artifact(root, p['snapshot'])
    state = load(path(root, p['snapshot']['path']))
    validate(root, state)
    return state, p['snapshot']


def publish(root, state):
    name = 'work-history/%06d-%s.json' % (state['revision'], digest(state)[:16])
    existing = path(root, name)
    if existing.exists():
        require(load(existing) == state, 'Snapshot identity collision')
        snap = ref(root, name)
    else:
        snap = write_new(root, name, state)
    tmp = path(root, '.current-work-next.json')
    created = False
    try:
        with tmp.open('x', encoding='utf8') as f:
            created = True
            json.dump({'snapshot': snap}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path(root, 'current-work.json'))
    finally:
        if created and tmp.exists():
            tmp.unlink()
    return snap


def quote(root, reference, value):
    artifact(root, reference)
    require(isinstance(value, dict) and set(value) == {'start', 'end', 'text'}, 'Invalid exact quote')
    start, end = value['start'], value['end']
    data = path(root, reference['path']).read_bytes()
    require(type(start) is int and type(end) is int and 0 <= start < end <= len(data), 'Invalid quote byte range')
    require(text(value['text']) and data[start:end] == value['text'].encode('utf8'), 'Quote does not match original bytes')


def history(root):
    """Identity-linked history, not an arbitrary author-supplied old statement."""
    current = load(path(root, 'current-work.json'))['snapshot']
    seen, previous_revision, task = set(), None, None
    while current:
        artifact(root, current)
        require(current['sha256'] not in seen, 'History cycle')
        seen.add(current['sha256'])
        state = load(path(root, current['path']))
        require(type(state.get('revision')) is int, 'Invalid historical revision')
        if previous_revision is not None:
            require(state['revision'] == previous_revision - 1 and state['task_id'] == task, 'Broken task history')
        previous_revision, task = state['revision'], state['task_id']
        yield current, state
        current = state.get('previous')
    require(previous_revision == 0, 'Incomplete task history')


def prior_claim(root, claim):
    require(isinstance(claim, dict), 'Invalid prior claim')
    for snapshot, state in history(root):
        if snapshot == claim.get('snapshot'):
            item = state['items'].get(claim.get('item_id'))
            require(isinstance(item, dict) and type(claim.get('version')) is int and item['version'] == claim['version'] and item['content'] == claim.get('content'), 'Prior claim must match exact historical item/version/content')
            return
    raise ValueError('Prior claim snapshot is not in this task history')


def diff_work(root, before, item_id):
    current, current_ref = pointer(root)
    for snapshot, state in history(root):
        if state['revision'] == before:
            require(item_id in current['items'] or item_id in state['items'], 'Unknown diff item')
            return {'item_id': item_id, 'before_snapshot': snapshot, 'before': state['items'].get(item_id),
                    'after_snapshot': current_ref, 'after': current['items'].get(item_id), 'semantic_verdict': 'not_evaluated'}
    raise ValueError('Historical revision not found')


RESULT_KINDS = {'relation', 'information', 'point', 'proposal', 'action', 'output'}


def required_facts(root, finding):
    facts = finding.get('required_facts', {})
    require(isinstance(facts, dict), 'Required facts must be an object')
    for key, fact in facts.items():
        require(isinstance(key, str) and ID.fullmatch(key) is not None and isinstance(fact, dict) and text(fact.get('required_fact')), 'Invalid required fact')
        anchor = fact.get('anchor')
        require(isinstance(anchor, dict) and text(anchor.get('locator')), 'Required fact source locator required')
        artifact(root, anchor.get('artifact'))
        for q in anchor.get('quotes', []):
            quote(root, anchor['artifact'], q)
    return facts


def obligations(root, items):
    result = {}
    for item_id, item in items.items():
        declared = item.get('obligations', {})
        require(isinstance(declared, dict) and (not declared or item['kind'] == 'information'), 'Obligations belong to information')
        for key, entry in declared.items():
            require(key not in result and isinstance(entry, dict), 'Duplicate or invalid obligation identity')
            original = original_result(root, entry.get('original_result'))
            finding = original['findings'].get(entry.get('finding_id'))
            require(isinstance(finding, dict), 'Obligation finding missing from original result')
            fact = required_facts(root, finding).get(key)
            require(isinstance(fact, dict) and entry.get('required_fact') == fact['required_fact'] and entry.get('anchor') == fact['anchor'], 'Obligation must preserve exact original required fact and anchor')
            require(entry.get('state') in {'pending', 'asked', 'deferred', 'obtained', 'retired'} and text(entry.get('basis')), 'Obligation state and basis required')
            if entry['state'] in {'pending', 'asked', 'deferred'}:
                require(item['status'] not in {'answered', 'supported', 'observed', 'reported', 'public'}, 'Unresolved obligation cannot be labeled completed information')
            if entry['state'] != 'pending':
                evidence = entry.get('evidence')
                require(isinstance(evidence, dict) and text(evidence.get('locator')), 'Obligation disposition evidence locator required')
                artifact(root, evidence.get('artifact'))
                quotes = evidence.get('quotes', [])
                require(isinstance(quotes, list), 'Obligation evidence quotes must be a list')
                if entry['state'] == 'asked':
                    media = evidence.get('media_type', '')
                    require(bool(quotes) or (isinstance(media, str) and media.startswith(('audio/', 'image/', 'video/'))), 'Asked obligation requires exact question quote or located multimodal question')
                if entry['state'] == 'obtained':
                    require(text(evidence.get('scope')), 'Obtained obligation requires answer support scope')
                for q in quotes:
                    quote(root, evidence['artifact'], q)
            result[key] = (item_id, entry)
    return result


def obligation_transition(root, old, new):
    before, after = obligations(root, old['items']), obligations(root, new['items'])
    for key, (_, prior) in before.items():
        if key not in after:
            require(prior['state'] == 'retired', 'Obligation cannot disappear without prior evidenced retirement: ' + key)
            continue
        current = after[key][1]
        identity = ('original_result', 'finding_id', 'required_fact', 'anchor')
        require(all(current.get(k) == prior.get(k) for k in identity), 'Obligation identity immutable; retire and register a new ID: ' + key)
        if prior['state'] == 'retired':
            require(current == prior, 'Retired obligation cannot be rewritten')
    # IDs retired in earlier snapshots cannot be reused after their item is removed.
    for _, snapshot in history(root):
        for item in snapshot['items'].values():
            for key, prior in item.get('obligations', {}).items():
                if key in after and prior.get('state') == 'retired':
                    require(after[key][1] == prior, 'Retired obligation identity cannot be reused')


def findings(root, record):
    """Explicit atomic results; an empty declaration is not semantic clearance."""
    found = record.get('findings')
    require(isinstance(found, dict), 'Explicit findings object required')
    require(found or text(record.get('no_findings_basis')), 'Empty findings require actual basis')
    for key, finding in found.items():
        require(ID.fullmatch(key) is not None and isinstance(finding, dict) and text(finding.get('claim')), 'Invalid atomic finding')
        artifact(root, finding.get('artifact'))
        required_facts(root, finding)
        require(isinstance(finding.get('prior_claims', []), list), 'Prior claims must be a list')
        for claim in finding.get('prior_claims', []):
            prior_claim(root, claim)
    return found


def receive_findings(root, found, dispositions, items, original_reference=None):
    require(isinstance(dispositions, dict) and set(dispositions) == set(found), 'Finding dispositions must exactly cover declared findings')
    for key, d in dispositions.items():
        require(isinstance(d, dict) and d.get('decision') in {'incorporated', 'conditional', 'excluded'}, 'Invalid finding disposition: ' + key)
        require(text(d.get('basis')), 'Finding disposition basis required: ' + key)
        artifact(root, d.get('artifact'))
        versions = d.get('updated_versions')
        require(isinstance(versions, dict) and (versions or d['decision'] == 'excluded'), 'Finding must map to accepted result versions: ' + key)
        for target, version in versions.items():
            require(target in items and items[target]['kind'] in RESULT_KINDS and items[target]['status'] != 'stale', 'Invalid finding destination: ' + key)
            require(type(version) is int and version == items[target]['version'], 'Stale finding destination: ' + key)
        facts = required_facts(root, found[key])
        if facts:
            mapped = d.get('required_fact_targets')
            require(isinstance(mapped, dict) and set(mapped) == set(facts), 'Required fact targets must exactly cover original obligations')
            registry = obligations(root, items)
            for fact_id in facts:
                target = mapped[fact_id]
                require(target in versions and target in items and items[target]['kind'] == 'information', 'Required fact must map to current information version')
                require(fact_id in registry and registry[fact_id][0] == target, 'Required fact obligation missing from mapped information')
                entry = registry[fact_id][1]
                require(entry['finding_id'] == key and entry['required_fact'] == facts[fact_id]['required_fact'] and entry['anchor'] == facts[fact_id]['anchor'], 'Required fact mapping identity mismatch')
                if original_reference is not None:
                    require(entry['original_result'] == original_reference, 'Required fact must bind exact original return')



def coverage_report(root, check):
    """Content presence only; nonempty bytes do not establish a useful review."""
    artifact(root, check.get('artifact'))
    report = path(root, check['artifact']['path'])
    data = report.read_bytes()
    require(bool(data), 'Coverage report must contain nonempty bytes')
    media_type = check.get('media_type', '')
    require(isinstance(media_type, str), 'Coverage report media_type must be text')
    mime = media_type.lower().split(';')[0].strip()
    textual = report.suffix.lower() in {'.txt', '.md', '.json', '.jsonl', '.csv', '.tsv', '.yaml', '.yml', '.xml', '.html', '.htm'} or mime.startswith('text/') or mime in {'application/json', 'application/xml'} or mime.endswith(('+json', '+xml'))
    if textual:
        try:
            content = data.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise ValueError('Declared text coverage report must use UTF-8') from exc
        require(bool(content.strip()), 'Text coverage report cannot be whitespace only')


def original_result(root, reference):
    artifact(root, reference)
    original = load(path(root, reference['path']))
    require(isinstance(original, dict), 'Original result must be an object')
    artifact(root, original.get('artifact'))
    findings(root, original)
    return original


def receive_original(root, reference, receipt, items):
    original = original_result(root, reference)
    require(isinstance(receipt, dict), 'Original result reception required')
    check = receipt.get('coverage_review')
    require(isinstance(check, dict) and check.get('original_result') == reference, 'Coverage review must bind exact original result')
    coverage_report(root, check)
    receive_findings(root, original['findings'], receipt.get('finding_dispositions'), items, reference)
    return original


def operation_reception(root, state, items):
    originals, receptions = state.get('original_results'), state.get('result_receptions')
    require(isinstance(originals, dict) and originals, 'Operation original results required')
    require(isinstance(receptions, dict) and set(receptions) == set(originals), 'Operation receptions must cover exact original results')
    covered = set()
    for key, reference in originals.items():
        require(isinstance(key, str) and ID.fullmatch(key) is not None, 'Invalid original result ID')
        original = receive_original(root, reference, receptions[key], items)
        covered.add(digest(original['artifact']))
    required = {digest(state['operation'])} | {digest(f['artifact']) for f in state['findings'].values()}
    required |= {digest(items[k]['artifact']) for k in state.get('changed_ids', []) if k in items and items[k]['kind'] in RESULT_KINDS and 'artifact' in items[k]}
    require(required <= covered, 'Operation, finding and changed-result artifacts must have original-result reception')


def reception_targets(item):
    return {target for ds in item.get('finding_dispositions', {}).values()
            for d in ds.values() for target in d.get('updated_versions', {})}


def validate(root, state):
    require(isinstance(state, dict) and type(state.get('schema')) is int and state.get('schema') == 1, 'Unsupported work schema')
    require(type(state.get('revision')) is int and state['revision'] >= 0, 'Invalid revision')
    require(text(state.get('task_id')) and text(state.get('goal')), 'Task and goal required')
    require(isinstance(state.get('items'), dict), 'Items must be an object')
    items = state['items']
    require(isinstance(state.get('retired_ids', {}), dict) and not (set(items) & set(state.get('retired_ids', {}))), 'Retired identifiers cannot be reused')
    for key, item in items.items():
        require(ID.fullmatch(key) is not None and isinstance(item, dict), 'Invalid item')
        require(item.get('kind') in KINDS and item.get('status') in STATES, 'Invalid kind/status: ' + key)
        require(type(item.get('version')) is int and item['version'] > 0, 'Invalid item version')
        require(text(item.get('content')), 'Actual result content required: ' + key)
        require(isinstance(item.get('depends_on'), dict), 'Dependencies required: ' + key)
        require(isinstance(item.get('sources'), list), 'Sources required: ' + key)
        for s in item['sources']:
            require(s in items and items[s]['kind'] == 'source', 'Unknown source: ' + str(s))
        for dep, version in item['depends_on'].items():
            require(dep in items and type(version) is int, 'Unknown dependency: ' + dep)
            if item['status'] != 'stale':
                require(items[dep]['version'] == version and items[dep]['status'] != 'stale', 'Stale dependency: ' + key + ' -> ' + dep)
                if item['status'] == 'supported':
                    require(items[dep]['status'] not in {'unknown', 'ready', 'asked', 'blocked', 'candidate', 'conditional'}, 'Supported result consumes unresolved premise: ' + key)
        if 'candidate_versions' in item:
            candidates = item['candidate_versions']
            require(item['kind'] in RESULT_KINDS and isinstance(candidates, dict) and candidates, 'Selection requires declared candidate versions')
            if item['status'] != 'stale':
                for candidate, version in candidates.items():
                    proposal = items.get(candidate)
                    require(isinstance(proposal, dict) and proposal['kind'] == 'proposal' and proposal['status'] != 'stale', 'Selection must consume a constructed proposal')
                    require(type(version) is int and proposal['version'] == version and item['depends_on'].get(candidate) == version, 'Candidate must be a current registered dependency')
                    coverage_report(root, {'artifact': proposal.get('artifact'), 'media_type': proposal.get('media_type', '')})
        if 'choice_scope' in item:
            require(item['kind'] in RESULT_KINDS and item['choice_scope'] in {'personal_lead', 'conditional_choice', 'robust_default'}, 'Invalid declared choice scope')
        if 'decision_rules' in item:
            rules = item['decision_rules']
            require(item['kind'] in RESULT_KINDS and isinstance(rules, dict), 'Decision rules require a result item and object')
            for rule_id, rule in rules.items():
                require(ID.fullmatch(rule_id) is not None and isinstance(rule, dict) and set(rule) == {'trigger', 'judgment', 'action'}, 'Invalid declared decision rule')
                require(all(text(value) for value in rule.values()), 'Rule trigger, judgment and action required')
        if item['kind'] == 'information':
            affects = item.get('affects')
            require(isinstance(affects, dict), 'Information impact declaration required: ' + key)
            require(affects or text(item.get('no_current_effect')), 'Empty information impact needs basis: ' + key)
            for target, effect in affects.items():
                require(target in items and target != key and text(effect), 'Invalid information impact target/effect: ' + key)
                if items[target]['status'] != 'stale':
                    require(items[target]['depends_on'].get(key) == item['version'], 'Declared impact must be consumed at current version: ' + key + ' -> ' + target)
        if item['kind'] == 'source':
            require(item['status'] in {'reported', 'observed', 'public'}, 'Source identity required')
            require(text(item.get('locator')) and text(item.get('scope')) and text(item.get('precision')), 'Source scope/precision/locator required')
            artifact(root, item.get('artifact'))
            require(isinstance(item.get('quotes', []), list), 'Source quotes must be a list')
            for value in item.get('quotes', []):
                quote(root, item['artifact'], value)
        elif 'artifact' in item:
            artifact(root, item['artifact'])
        if item['kind'] == 'action' and item['status'] != 'stale':
            require(any(items[d]['kind'] == 'point' for d in item['depends_on']), 'Action must reference a point')
        if item['kind'] == 'point' and item['status'] != 'stale':
            require(any(items[d]['kind'] == 'relation' for d in item['depends_on']), 'Point must reference a relation')
        if item['kind'] == 'challenge':
            declared = findings(root, item)
            original = original_result(root, item.get('original_result'))
            require(findings(root, original) == declared, 'Challenge findings differ from original producer result')
            require(original.get('no_findings_basis') == item.get('no_findings_basis'), 'Empty-result basis differs from original')
        if item['kind'] == 'reception' and item['status'] != 'stale':
            challenges = {d for d in item['depends_on'] if items[d]['kind'] == 'challenge'}
            require(challenges, 'Reception must reference challenge')
            dispositions = item.get('finding_dispositions')
            require(isinstance(dispositions, dict) and set(dispositions) == challenges, 'Reception must cover exact challenge dependencies')
            coverage = item.get('coverage_reviews')
            require(isinstance(coverage, dict) and set(coverage) == challenges, 'Raw-result coverage reviews must cover exact challenges')
            for challenge in challenges:
                receive_original(root, items[challenge]['original_result'], {'coverage_review': coverage[challenge], 'finding_dispositions': dispositions[challenge]}, items)
    obligations(root, items)
    visiting, done = set(), set()
    def visit(k):
        require(k not in visiting, 'Version dependency cycle; reality feedback belongs in content')
        if k in done:
            return
        visiting.add(k)
        for d in items[k]['depends_on']:
            visit(d)
        visiting.remove(k)
        done.add(k)
    for k in items:
        visit(k)
    for key, item in items.items():
        if item['status'] == 'supported':
            pending = list(item['depends_on']); seen = set()
            while pending:
                dep = pending.pop()
                if dep in seen:
                    continue
                seen.add(dep)
                require(items[dep]['status'] not in {'unknown', 'ready', 'asked', 'blocked', 'candidate', 'conditional', 'stale'}, 'Supported result has unresolved ancestor: ' + key)
                pending.extend(items[dep]['depends_on'])
    if 'scope_reopen' in state:
        artifact(root, state['scope_reopen'])
    require(isinstance(state.get('completion'), dict) and set(state['completion']) == {'explanation', 'action', 'request'}, 'Three distinct completion descriptions required')
    require(all(text(v) for v in state['completion'].values()), 'Completion descriptions cannot be empty')
    if state['revision']:
        artifact(root, state.get('previous'))
        artifact(root, state.get('operation'))
        receive_findings(root, findings(root, state), state.get('finding_dispositions'), items)
        operation_reception(root, state, items)
        require(text(state.get('delta')) and text(state.get('selection_basis')), 'Operation result and selection basis required')
    return state


def initialize(root, task_id, goal):
    root.mkdir(parents=True, exist_ok=True)
    with lock(root):
        require(not path(root, 'current-work.json').exists(), 'Task already initialized')
        state = {'schema': 1, 'task_id': task_id, 'goal': goal, 'revision': 0, 'items': {},
                 'completion': {'explanation': 'Not assessed', 'action': 'Not assessed', 'request': 'Not completed'}, 'previous': None, 'retired_ids': {}}
        validate(root, state)
        return publish(root, state)


def read_work(root, receipt=None):
    state, snapshot = pointer(root)
    result = {'revision': state['revision'], 'work_sha256': digest(state), 'snapshot': snapshot, 'work': state}
    if receipt:
        result['read_receipt'] = write_new(root, receipt, {'kind': 'read', 'revision': state['revision'], 'work_sha256': digest(state), 'snapshot': snapshot})
    return result


def read_binding(root, name, state, snapshot):
    r = load(path(root, name))
    require(isinstance(r, dict), 'Read receipt must be an object')
    require(r.get('kind') == 'read' and r.get('revision') == state['revision'] and r.get('work_sha256') == digest(state) and r.get('snapshot') == snapshot, 'Read receipt is stale or for different work')
    return r


def apply(root, read_name, patch_name):
    with lock(root):
        old, snapshot = pointer(root)
        read_binding(root, read_name, old, snapshot)
        patch = load(path(root, patch_name))
        require(isinstance(patch, dict), 'Patch must be an object')
        require(type(patch.get('expected_revision')) is int and patch.get('expected_revision') == old['revision'] and patch.get('expected_work_sha256') == digest(old), 'Patch base mismatch')
        require(isinstance(patch.get('upsert'), dict) and isinstance(patch.get('retire', {}), dict), 'Explicit upserts/retirements required')
        require(text(patch.get('delta')) and text(patch.get('selection_basis')), 'Actual delta and operation choice required')
        artifact(root, patch.get('operation'))
        new = copy.deepcopy(old)
        new.update(revision=old['revision'] + 1, previous=snapshot, delta=patch['delta'], selection_basis=patch['selection_basis'], operation=patch['operation'])
        changed = set()
        for key, item in patch['upsert'].items():
            require(key not in old.get('retired_ids', {}), 'Retired identifier cannot be reused: ' + key)
            prior = old['items'].get(key)
            require(isinstance(item, dict), 'Invalid upsert')
            if prior:
                require(prior['kind'] == item.get('kind'), 'Item kind cannot change')
                require(prior['kind'] != 'source' or item == prior, 'Source records immutable; add correction as new source')
                a, b = dict(prior), dict(item)
                a.pop('version', None); b.pop('version', None)
                version = prior['version'] + (a != b)
            else:
                version = 1
            require(type(item.get('version')) is int and item['version'] == version, 'Wrong next version: ' + key)
            new['items'][key] = item
            if item != prior:
                changed.add(key)
        retire = patch.get('retire', {})
        for key, reason in retire.items():
            require(key in old['items'] and key not in patch['upsert'] and text(reason), 'Invalid retirement')
            require(old['items'][key]['kind'] != 'source', 'Original sources cannot be retired')
            del new['items'][key]
            new.setdefault('retired_ids', {})[key] = {'version': old['items'][key]['version'], 'kind': old['items'][key]['kind'], 'reason': reason}
            changed.add(key)
        new['findings'] = patch.get('findings')
        new['no_findings_basis'] = patch.get('no_findings_basis')
        new['finding_dispositions'] = patch.get('finding_dispositions')
        new['original_results'] = patch.get('original_results')
        new['result_receptions'] = patch.get('result_receptions')
        new['retirements'] = retire
        # Changing a source set requires an actual scope artifact, not a central=false switch.
        if any(new['items'].get(k, {}).get('kind') == 'source' for k in changed):
            artifact(root, patch.get('scope_reopen'))
            new['scope_reopen'] = patch['scope_reopen']
        elif 'scope_reopen' in patch:
            artifact(root, patch['scope_reopen']); new['scope_reopen'] = patch['scope_reopen']
        # Registered downstream consumers must be explicitly revised or retired.
        impacted = set(changed)
        while True:
            more = {k for k, i in old['items'].items() if (set(i['depends_on']) | (reception_targets(i) if i['kind'] == 'reception' else set())) & impacted}
            if more <= impacted:
                break
            impacted |= more
        for key in impacted - changed:
            require(key in patch['upsert'] and patch['upsert'][key] != old['items'][key], 'Affected consumer not revised or marked stale: ' + key)
        new['changed_ids'] = sorted(changed)
        new['affected_ids'] = sorted(impacted)
        if 'completion' in patch:
            new['completion'] = patch['completion']
        validate(root, new)
        obligation_transition(root, old, new)
        snap = publish(root, new)
        return {'revision': new['revision'], 'snapshot': snap, 'work_sha256': digest(new), 'changed_ids': sorted(changed), 'affected_ids': sorted(impacted), 'semantic_verdict': 'not_evaluated'}



def challenge_dispositions(root, state, review):
    """Require explicit handling of registered challenges, not semantic adequacy."""
    challenges = {key: item for key, item in state['items'].items() if item['kind'] == 'challenge'}
    dispositions = review.get('challenge_dispositions', {})
    require(isinstance(dispositions, dict) and set(dispositions) == set(challenges), 'Challenge dispositions must exactly cover current registered challenges')
    targets = set(review['targets'])
    for key, item in challenges.items():
        d = dispositions[key]
        require(isinstance(d, dict), 'Invalid challenge disposition: ' + key)
        require(type(d.get('version')) is int and d['version'] == item['version'], 'Stale challenge disposition: ' + key)
        decision = d.get('decision')
        require(decision in {'received', 'deferred', 'excluded'}, 'Unknown challenge disposition: ' + key)
        if decision == 'received':
            reception = state['items'].get(d.get('reception_id'))
            require(isinstance(reception, dict) and reception['kind'] == 'reception' and reception['status'] != 'stale', 'Current non-stale reception required: ' + key)
            require(type(d.get('reception_version')) is int and d['reception_version'] == reception['version'], 'Stale reception version: ' + key)
            require(reception['depends_on'].get(key) == item['version'], 'Reception must consume this challenge version: ' + key)
        else:
            require(text(d.get('basis')) and text(d.get('delivery_basis')), 'Disposition and continued-delivery basis required: ' + key)
            artifact(root, d.get('artifact'))
            effects = d.get('target_effects')
            require(isinstance(effects, dict) and set(effects) == targets and all(text(v) for v in effects.values()), 'Disposition effects must cover exact delivery targets: ' + key)
            receive_original(root, item['original_result'], {'coverage_review': {'original_result': item['original_result'], 'artifact': d['artifact'], 'media_type': d.get('media_type', '')}, 'finding_dispositions': d.get('finding_dispositions', {})}, state['items'])


def information_dispositions(root, state, review):
    """Close registered unresolved influences only; do not discover missing ones."""
    items = state['items']
    closure, pending = set(), list(review['targets'])
    while pending:
        key = pending.pop()
        if key in closure:
            continue
        closure.add(key)
        pending.extend(items[key]['depends_on'])
    # Every substantive consumer in delivery ancestry has its own scope. An
    # executable terminal action cannot discharge an intermediate goal or rank.
    consumers = {k for k in closure if items[k]['kind'] in RESULT_KINDS and
                 (items[k]['kind'] != 'information' or k in review['targets'])}
    affected = {}
    for target in consumers:
        pending, seen = [target], set()
        while pending:
            key = pending.pop()
            if key in seen:
                continue
            seen.add(key)
            item = items[key]
            if item['kind'] == 'information' and item['status'] not in {'answered', 'supported', 'observed', 'reported', 'public'}:
                affected.setdefault(key, set()).add(target)
            pending.extend(item['depends_on'])
    dispositions = review.get('information_dispositions', {})
    require(isinstance(dispositions, dict) and set(dispositions) == set(affected), 'Information dispositions must exactly cover unresolved delivery influences')
    for key, targets in affected.items():
        d = dispositions[key]
        require(isinstance(d, dict) and type(d.get('version')) is int and d['version'] == items[key]['version'], 'Stale information disposition: ' + key)
        effects = d.get('target_effects')
        require(isinstance(effects, dict) and set(effects) == targets, 'Information effects must cover exact affected substantive delivery ancestry: ' + key)
        for target, effect in effects.items():
            require(isinstance(effect, dict) and effect.get('decision') in {'conditional', 'robust', 'not_used'}, 'Invalid information disposition decision: ' + key)
            require(text(effect.get('basis')) and text(effect.get('effect')), 'Actual information effect and basis required: ' + key)
            artifact(root, effect.get('artifact'))
            if 'choice_scope' in items[target]:
                require(effect.get('choice_basis') in {'comparison', 'default_only'}, 'Declared route requires comparison or default-only basis scope')
                require(not (effect['choice_basis'] == 'default_only' and items[target]['choice_scope'] == 'personal_lead'), 'Default-only disposition cannot establish declared personal lead')
            if effect['decision'] == 'not_used':
                require(text(effect.get('withdrawn_judgment')), 'Unused uncertainty requires explicit withdrawn judgment: ' + key)


def rule_dispositions(root, state, review):
    """Check declared rule identity and receipt, never inference correctness."""
    items = state['items']
    pending, closure = list(review['targets']), set()
    while pending:
        key = pending.pop()
        if key in closure:
            continue
        closure.add(key)
        pending.extend(items[key]['depends_on'])
    expected = {k: items[k] for k in closure if items[k].get('decision_rules')}
    dispositions = review.get('rule_dispositions', {})
    require(isinstance(dispositions, dict) and set(dispositions) == set(expected), 'Rule dispositions must exactly cover declared delivery rules')
    for key, item in expected.items():
        d = dispositions[key]
        require(isinstance(d, dict) and type(d.get('version')) is int and d['version'] == item['version'], 'Stale rule owner version: ' + key)
        rules = d.get('rules')
        require(isinstance(rules, dict) and set(rules) == set(item['decision_rules']), 'Each declared rule requires a disposition: ' + key)
        for rule_id, rule in item['decision_rules'].items():
            treatment = rules[rule_id]
            require(isinstance(treatment, dict) and treatment.get('rule_sha256') == digest(rule), 'Disposition does not bind exact trigger/judgment/action: ' + rule_id)
            require(all(text(treatment.get(field)) for field in ['judgment_basis', 'action_basis', 'effect']), 'Separate judgment/action grounds and actual effect required')
            alternative = treatment.get('alternative')
            require(isinstance(alternative, dict) and alternative.get('kind') in {'compatible_process', 'none_found'}, 'Actual alternative comparison required')
            require(text(alternative.get('basis')) and text(alternative.get('consequence')), 'Alternative process/comparison and consequence required')
            artifact(root, treatment.get('artifact'))


def bind(root, read_name, draft_name, review_name, receipt_name):
    with lock(root):
        state, snap = pointer(root)
        read_binding(root, read_name, state, snap)
        draft = ref(root, draft_name)
        review_ref = ref(root, review_name)
        review = load(path(root, review_name))
        require(isinstance(review, dict), 'Review must be an object')
        require(review.get('work_sha256') == digest(state) and review.get('draft') == draft, 'Review not bound to exact work and draft')
        require(isinstance(review.get('targets'), list) and review['targets'] and len(review['targets']) == len(set(review['targets'])), 'Unique delivery targets required')
        for key in review['targets']:
            require(key in state['items'] and state['items'][key]['status'] != 'stale', 'Unknown or stale delivery target')
        require(review.get('open_findings') == [], 'Unresolved review findings')
        require(text(review.get('argument_review')) and text(review.get('limits')), 'Actual argument review and limits required')
        artifact(root, review.get('artifact'))
        challenge_dispositions(root, state, review)
        information_dispositions(root, state, review)
        rule_dispositions(root, state, review)
        result = {'kind': 'draft_binding', 'revision': state['revision'], 'snapshot': snap, 'work_sha256': digest(state), 'draft': draft, 'review': review_ref, 'semantic_verdict': 'not_evaluated'}
        write_new(root, receipt_name, result)
        return result


def verify(root, receipt_name):
    state, snap = pointer(root)
    r = load(path(root, receipt_name))
    require(isinstance(r, dict), 'Binding must be an object')
    require(r.get('kind') == 'draft_binding' and r.get('snapshot') == snap and r.get('work_sha256') == digest(state) and r.get('revision') == state['revision'], 'Draft binding is stale')
    artifact(root, r.get('draft')); artifact(root, r.get('review'))
    # Review artifact itself is also identity-bound.
    review = load(path(root, r['review']['path']))
    artifact(root, review.get('artifact'))
    challenge_dispositions(root, state, review)
    information_dispositions(root, state, review)
    rule_dispositions(root, state, review)
    return {'binding_valid': True, 'revision': state['revision'], 'semantic_verdict': 'not_evaluated', 'host_send_control': False}


def reconcile(root, challenge_id):
    """Expose producer discoveries beside exact current reception, without semantic grading."""
    state, snapshot = pointer(root)
    if challenge_id is None:
        return {'snapshot': snapshot, 'operation': state.get('operation'),
                'originals': {k: {'reference': v, 'original': original_result(root, v),
                                  'reception': state['result_receptions'][k]} for k, v in state.get('original_results', {}).items()},
                'current_results': {k: v for k, v in state['items'].items() if v['kind'] in RESULT_KINDS},
                'semantic_verdict': 'not_evaluated'}
    c = state['items'].get(challenge_id)
    require(isinstance(c, dict) and c['kind'] == 'challenge', 'Unknown challenge')
    original = load(path(root, c['original_result']['path']))
    receptions = {}
    for key, item in state['items'].items():
        if item['kind'] == 'reception' and item['status'] != 'stale' and challenge_id in item['depends_on']:
            dispositions = item['finding_dispositions'][challenge_id]
            targets = {t for d in dispositions.values() for t in d['updated_versions']}
            receptions[key] = {'version': item['version'], 'dispositions': dispositions,
                               'current_results': {t: state['items'][t] for t in sorted(targets)},
                               'coverage_review': item['coverage_reviews'][challenge_id]}
    return {'snapshot': snapshot, 'challenge_id': challenge_id, 'challenge_version': c['version'],
            'original_result': c['original_result'], 'original': original, 'receptions': receptions,
            'semantic_verdict': 'not_evaluated'}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    subs = ap.add_subparsers(dest='command', required=True)
    for command in ['init', 'read', 'apply', 'bind', 'verify', 'check', 'hash', 'diff', 'reconcile']:
        p = subs.add_parser(command)
        p.add_argument('root', type=Path)
        if command == 'init':
            p.add_argument('--task-id', required=True); p.add_argument('--goal', required=True)
        if command == 'read': p.add_argument('--receipt')
        if command in {'apply', 'bind'}: p.add_argument('--from-read', required=True)
        if command == 'apply': p.add_argument('--patch', required=True)
        if command == 'bind':
            p.add_argument('--draft', required=True); p.add_argument('--review', required=True); p.add_argument('--receipt', required=True)
        if command == 'verify': p.add_argument('--receipt', required=True)
        if command == 'hash': p.add_argument('file')
        if command == 'reconcile': p.add_argument('--challenge')
        if command == 'diff':
            p.add_argument('--before', required=True, type=int); p.add_argument('--item', required=True)
    args = ap.parse_args(argv)
    try:
        root = args.root.resolve()
        if args.command == 'init': out = initialize(root, args.task_id, args.goal)
        elif args.command == 'read': out = read_work(root, args.receipt)
        elif args.command == 'apply': out = apply(root, args.from_read, args.patch)
        elif args.command == 'bind': out = bind(root, args.from_read, args.draft, args.review, args.receipt)
        elif args.command == 'verify': out = verify(root, args.receipt)
        elif args.command == 'hash': out = ref(root, args.file)
        elif args.command == 'reconcile': out = reconcile(root, args.challenge)
        elif args.command == 'diff': out = diff_work(root, args.before, args.item)
        else:
            state, _ = pointer(root)
            out = {'structure_valid': True, 'revision': state['revision'], 'semantic_verdict': 'not_evaluated'}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, TypeError, KeyError, OSError, RecursionError) as exc:
        print(json.dumps({'error': str(exc), 'return_to': 'repair_artifact_or_version', 'semantic_verdict': 'not_evaluated'}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
