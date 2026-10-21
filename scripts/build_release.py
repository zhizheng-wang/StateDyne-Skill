#!/usr/bin/env python3
"""Build one cognitive skill, packaged for three distinct distribution surfaces.

The *same* skill files are used for direct skill upload, portable plugin
upload, and source archives.  This script never claims a successful remote
plugin install or live-model invocation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FIXED_ZIP_DATE = (2026, 10, 21, 0, 0, 0)
INSTALL_EXCLUDE = ('tests/', '.github/', 'engineering/history/')
SOURCE_ONLY = {'scripts/build_release.py'}
MAX_ZIP_BYTES = 50 * 1024 * 1024
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_FILES = 500


def plugin_manifest(version: str) -> dict:
    return {
        "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
        "name": "statedyne",
        "version": version,
        "description": "StateDyne: unified generative causal research, independent alternatives, evidence, goal discovery and real-world interventions.",
        "license": "Apache-2.0",
        "keywords": ["causal-research", "generative-discovery", "interventions", "decisions"],
        "extensions": {
            "com.openai": {
                "interface": {
                    "displayName": "StateDyne",
                    "shortDescription": "Find how outcomes arise, challenge causes, and design better changes",
                    "longDescription": "One full-strength cognitive standard across plugin and skill calls: investigate how a result is generated, test independent explanations, seek different feasible paths, explain causal intervention points and combinations, and retain meaningful next research steps."
                }
            }
        }
    }


def skill_file_paths(root: Path = ROOT) -> list[str]:
    source_map = json.loads((root / 'references/source-map.json').read_text(encoding='utf-8'))
    all_paths = [item['path'] for item in source_map['files']]
    all_paths.append('references/source-map.json')
    paths = [path for path in all_paths if not path.startswith(INSTALL_EXCLUDE) and path not in SOURCE_ONLY]
    if len(paths) != len(set(paths)) or 'SKILL.md' not in paths:
        raise ValueError('The active installation inventory has duplicate/missing skill entries')
    if any('/SKILL.md' in p or p.lower() == 'skill.md' and p != 'SKILL.md' for p in paths):
        raise ValueError('Nested or ambiguous skill entry')
    return sorted(paths)


def _zip_write(z: zipfile.ZipFile, path: str, content: bytes):
    if path.startswith('/') or '..' in Path(path).parts or '\\' in path:
        raise ValueError(f'Unsafe archive name: {path}')
    info = zipfile.ZipInfo(path, FIXED_ZIP_DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    z.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def assemble(root: Path, out_dir: Path) -> dict[str, Path]:
    source_map = json.loads((root / 'references/source-map.json').read_text(encoding='utf8'))
    version = source_map['skill_version']
    all_paths = sorted([item['path'] for item in source_map['files']] + ['references/source-map.json'])
    paths = skill_file_paths(root)
    if any(not (root / p).is_file() for p in all_paths):
        raise ValueError('Source map references a missing release file')
    out_dir.mkdir(parents=True, exist_ok=True)
    specs = {
        'Install': ([(p, (root / p).read_bytes()) for p in paths]),
        'Agent-Skill': ([(f'statedyne/{p}', (root / p).read_bytes()) for p in paths]),
        'Plugin': ([('plugin.json', (json.dumps(plugin_manifest(version), ensure_ascii=False, indent=2)+'\n').encode('utf8'))] +
                   [(f'skills/statedyne/{p}', (root / p).read_bytes()) for p in paths]),
        'GitHub-Ready': ([(f'statedyne/{p}', (root / p).read_bytes()) for p in all_paths])
    }
    files = {}
    for name, entries in specs.items():
        archive = out_dir / f'StateDyne-{version}-{name}.zip'
        names = [entry[0] for entry in entries]
        folded_names = [entry.casefold() for entry in names]
        if len(names) > MAX_FILES:
            raise ValueError(f'Too many files for one skill bundle in {name}: {len(names)}')
        if any(len(blob) > MAX_FILE_BYTES for _, blob in entries):
            raise ValueError(f'An uncompressed file exceeds 25 MB in {name}')
        if len(folded_names) != len(set(folded_names)):
            raise ValueError(f'Duplicate archive names in {name}')
        skill_entries = [entry for entry in names if Path(entry).name.casefold() == 'skill.md']
        expected_skill = {
            'Install': 'SKILL.md',
            'Agent-Skill': 'statedyne/SKILL.md',
            'Plugin': 'skills/statedyne/SKILL.md',
            'GitHub-Ready': 'statedyne/SKILL.md',
        }[name]
        if skill_entries != [expected_skill]:
            raise ValueError(f'Expected one active skill entry at {expected_skill} in {name}; found {skill_entries}')
        if name in {'Agent-Skill', 'GitHub-Ready'} and {entry.split('/', 1)[0] for entry in names} != {'statedyne'}:
            raise ValueError(f'{name} must contain exactly one top-level statedyne folder')
        with zipfile.ZipFile(archive, 'w') as z:
            for path, blob in entries: _zip_write(z, path, blob)
        if archive.stat().st_size > MAX_ZIP_BYTES:
            raise ValueError(f'{archive.name} exceeds the 50 MB upload limit')
        # Inspect exact byte identity *after* re-opening the final file.
        with zipfile.ZipFile(archive, 'r') as z:
            if z.testzip() is not None or set(z.namelist()) != set(names):
                raise ValueError(f'Invalid ZIP or missing entries in {archive.name}')
            for path, blob in entries:
                if z.read(path) != blob:
                    raise ValueError(f'Byte identity changed in {archive.name}::{path}')
        files[name] = archive
    # Two upload routes must have the same cognitive instructions, not variants.
    with zipfile.ZipFile(files['Install']) as inst, zipfile.ZipFile(files['Agent-Skill']) as agent, zipfile.ZipFile(files['Plugin']) as plug, zipfile.ZipFile(files['GitHub-Ready']) as src:
        for p in paths:
            source = (root / p).read_bytes()
            if not (inst.read(p) == agent.read('statedyne/' + p) == plug.read('skills/statedyne/' + p) == src.read('statedyne/'+p) == source):
                raise ValueError(f'Cross-archive skill divergence: {p}')
    hashes = out_dir / f'StateDyne-{version}-SHA256.txt'
    hashes.write_text(''.join(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n' for path in files.values()), encoding='ascii')
    files['SHA256'] = hashes
    return files


def main():
    parser = argparse.ArgumentParser(description='Build reproducible skill, portable plugin and GitHub ZIPs')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    built = assemble(ROOT, args.out)
    for name,path in built.items():
        print(f'{name}: {path} ({path.stat().st_size} bytes)')
    return 0

if __name__ == '__main__': raise SystemExit(main())
