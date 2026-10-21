#!/usr/bin/env python3
"""Compare two independently released StateDyne workspaces' pivotal quantities.

It does not adjudicate which estimate is true. It explains where numbers differ
and exposes their stated scenario and assumptions for independent review.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path


def read_pivot(path: Path) -> dict:
    root=path.resolve()
    state=json.loads((root/'state.json').read_text(encoding='utf-8'))
    release=json.loads((root/'release.json').read_text(encoding='utf-8'))
    draft=state.get('draft') or {}
    if not draft or not draft.get('output'):
        raise ValueError(f'No reviewed draft in {root}')
    if release.get('draft_sha256')!=draft.get('sha256') or not release.get('audit_job'):
        raise ValueError(f'Release and reviewed draft do not match in {root}')
    pivots=draft['output'].get('pivotal_quantities')
    if pivots is None:
        raise ValueError('Workspace does not implement audited pivotal quantities; compare manually')
    return {'folder':str(root),'assurance':release.get('assurance'),
            'pivots':pivots}


def index(pivots: list[dict]) -> dict:
    result={}
    for x in pivots:
        key=(x['metric'].strip().casefold(),x['unit'].strip().casefold(),
             x['period'].strip().casefold(),x['population_and_scope'].strip().casefold(),
             x['measure_kind'],x['scenario'].strip().casefold())
        if key in result:
            raise ValueError(f'A released run repeats one pivot definition: {key}')
        result[key]=x
    return result


def compare(a: dict,b: dict) -> dict:
    left,right=index(a['pivots']),index(b['pivots'])
    rows=[]
    for key in sorted(left.keys()|right.keys()):
        x,y=left.get(key),right.get(key)
        val=lambda d:(d.get('conclusion_value') or d.get('body_value') or d.get('headline_value')) if d else None
        va,vb=val(x),val(y)
        rows.append({'metric':key[0], 'unit':key[1], 'period':key[2], 'scope':key[3],
                     'kind':key[4], 'scenario':key[5], 'first':va, 'second':vb,
                     'status':('only_first' if y is None else 'only_second' if x is None else
                               'same_reported_number' if va==vb else 'different_reported_number'),
                     'first_assumption':x['assumption_or_limit'] if x else None,
                     'second_assumption':y['assumption_or_limit'] if y else None})
    return {'comparison':'independently released reported claims, not semantic truth',
            'first_assurance':a['assurance'],'second_assurance':b['assurance'],
            'pivot_count_first':len(left),'pivot_count_second':len(right),
            'shared_comparable':len(left.keys()&right.keys()),'results':rows,
            'limits':'Differences can reflect evidence, scenario, unit or source changes. Empty pivots do not certify no quantitative claims.'}


def main():
    pa=argparse.ArgumentParser(description=__doc__)
    pa.add_argument('first',type=Path)
    pa.add_argument('second',type=Path)
    a=pa.parse_args()
    print(json.dumps(compare(read_pivot(a.first),read_pivot(a.second)),ensure_ascii=False,indent=2))

if __name__=='__main__': main()
