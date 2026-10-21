#!/usr/bin/env python3
"""Verify file identity, profile accounting and local links; not semantic quality."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
MAX_ZIP_BYTES = 50 * 1024 * 1024
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_FILES = 500


def parse_ui(text):
    """Optional PyYAML is needed only to accept host YAML reserialization."""
    try:
        import yaml
    except ImportError as exc:
        raise ValueError("UI bytes changed; install PyYAML for semantic comparison or use exact release bytes") from exc

    class UniqueLoader(yaml.SafeLoader):
        pass

    def mapping(loader, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise ValueError("UI YAML contains a non-string or duplicate key")
            result[key] = loader.construct_object(value_node, deep=deep)
        return result

    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    try:
        data = yaml.load(text, Loader=UniqueLoader)
        json.dumps(data, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (yaml.YAMLError, TypeError, ValueError, RecursionError) as exc:
        raise ValueError(f"Invalid UI YAML: {exc}") from exc
    return data


def ui_semantic_hash(text):
    raw = json.dumps(parse_ui(text), ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def safe_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes skill: {relative}")
    return path


def check_downloads(root, version, required=False):
    errors = []
    folder = root / "downloads"
    layouts = {
        "Install": "SKILL.md",
        "Agent-Skill": "statedyne/SKILL.md",
        "Plugin": "skills/statedyne/SKILL.md",
        "GitHub-Ready": "statedyne/SKILL.md",
    }
    zip_names = {kind: f"StateDyne-{version}-{kind}.zip" for kind in layouts}
    checksum_name = f"StateDyne-{version}-SHA256.txt"
    expected_files = set(zip_names.values()) | {checksum_name}
    if not folder.exists():
        return ["downloads directory is required for the publishable repository"] if required else []
    actual_files = {path.name for path in folder.iterdir() if path.is_file()}
    if actual_files != expected_files:
        errors.append(f"Download inventory mismatch: missing={expected_files-actual_files}, extra={actual_files-expected_files}")
    checksums = {}
    checksum_path = folder / checksum_name
    if checksum_path.is_file():
        for number, line in enumerate(checksum_path.read_text(encoding="ascii").splitlines(), 1):
            match = re.fullmatch(r"([0-9a-f]{64})  ([^/\\]+)", line)
            if not match or match.group(2) in checksums:
                errors.append(f"Invalid SHA-256 line {number}")
                continue
            checksums[match.group(2)] = match.group(1)
        if set(checksums) != set(zip_names.values()):
            errors.append("SHA-256 inventory does not match release ZIPs")
    elif required:
        errors.append("Missing SHA-256 file")
    source_skill = (root / "SKILL.md").read_bytes()
    for kind, archive_name in zip_names.items():
        archive = folder / archive_name
        if not archive.is_file():
            continue
        if archive.stat().st_size > MAX_ZIP_BYTES:
            errors.append(f"{archive_name}: exceeds 50 MB")
        observed_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
        if checksums.get(archive_name) not in (None, observed_hash):
            errors.append(f"{archive_name}: SHA-256 mismatch")
        try:
            with zipfile.ZipFile(archive) as package:
                entries = [entry for entry in package.infolist() if not entry.is_dir()]
                names = [entry.filename for entry in entries]
                if len(entries) > MAX_FILES:
                    errors.append(f"{archive_name}: exceeds 500 files")
                if len({name.casefold() for name in names}) != len(names):
                    errors.append(f"{archive_name}: duplicate or case-colliding paths")
                for entry in entries:
                    parts = entry.filename.split("/")
                    if (not entry.filename or entry.filename.startswith("/") or "\\" in entry.filename
                            or ".." in parts or any(not part for part in parts)):
                        errors.append(f"{archive_name}: unsafe path {entry.filename}")
                    if entry.file_size > MAX_FILE_BYTES:
                        errors.append(f"{archive_name}: {entry.filename} exceeds 25 MB")
                broken = package.testzip()
                if broken is not None:
                    errors.append(f"{archive_name}: CRC failure at {broken}")
                skill_entries = [name for name in names if name.rsplit("/", 1)[-1].casefold() == "skill.md"]
                expected_skill = layouts[kind]
                if skill_entries != [expected_skill]:
                    errors.append(f"{archive_name}: expected only {expected_skill}, found {skill_entries}")
                elif package.read(expected_skill) != source_skill:
                    errors.append(f"{archive_name}: SKILL.md differs from repository source")
                if kind in {"Agent-Skill", "GitHub-Ready"} and {name.split("/", 1)[0] for name in names} != {"statedyne"}:
                    errors.append(f"{archive_name}: must contain one top-level statedyne folder")
                if kind == "Plugin":
                    plugin = json.loads(package.read("plugin.json"))
                    if plugin.get("name") != "statedyne" or plugin.get("version") != version:
                        errors.append(f"{archive_name}: plugin metadata mismatch")
        except (OSError, KeyError, ValueError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
            errors.append(f"{archive_name}: {exc}")
    return errors


def check(root=ROOT, strict_bytes=False, require_downloads=False):
    errors = []
    ui_data = None
    manifest = json.loads((root / "references/source-map.json").read_text())
    skill_entries = [p.relative_to(root).as_posix() for p in root.rglob('SKILL.md') if p.is_file()]
    if skill_entries != ['SKILL.md']:
        errors.append(f'Exactly one active SKILL.md must exist at skill root; found {skill_entries}')
    listed = {entry["path"] for entry in manifest["files"]}
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*")
              if p.is_file() and "__pycache__" not in p.parts and ".git" not in p.parts
              and p.relative_to(root).parts[0] != "downloads"
              and p.relative_to(root).as_posix() != "references/source-map.json"}
    if listed != actual:
        errors.append(f"Inventory mismatch: missing={listed-actual}, unlisted={actual-listed}")
    if len(listed) != len(manifest["files"]):
        errors.append("Duplicate manifest paths")
    for entry in manifest["files"]:
        try:
            p = safe_path(root, entry["path"])
            raw = p.read_bytes()
            text = raw.decode("utf-8")
            observed = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                        "characters": len(text), "lines": len(text.splitlines())}
            mismatches = [key for key, val in observed.items() if entry.get(key) != val]
            if (mismatches and not strict_bytes and entry["path"] == "agents/openai.yaml"
                    and entry.get("semantic_sha256")):
                if ui_semantic_hash(text) == entry["semantic_sha256"]:
                    mismatches = []
                    ui_data = parse_ui(text)
                else:
                    errors.append("agents/openai.yaml: semantic identity mismatch")
            if (mismatches and not strict_bytes and entry["path"] == "assets/icon.svg"
                    and any(all(variant.get(key) == val for key, val in observed.items())
                            for variant in entry.get("host_materialized_variants", []))):
                # Accept only explicitly observed complete byte identities for this
                # host-managed icon. Runtime/method/other assets remain exact.
                mismatches = []
            for key in mismatches:
                errors.append(f"{entry['path']}: {key} mismatch")
            if p.suffix == ".md" and entry["role"] != "archive":
                for link in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text):
                    if re.match(r"[a-zA-Z]+://|#|mailto:", link):
                        continue
                    target = link.split("#", 1)[0]
                    if target and not safe_path(root, str(p.parent.relative_to(root) / target)).exists():
                        errors.append(f"{entry['path']}: broken link {link}")
        except (OSError, ValueError, KeyError) as exc:
            errors.append(f"{entry.get('path')}: {exc}")
    version = manifest["skill_version"]
    entry_text = (root / "SKILL.md").read_text()
    frontmatter = re.match(r"\A---\n(.*?)\n---\n", entry_text, re.S)
    if not frontmatter or set(re.findall(r"^([\w-]+):", frontmatter.group(1), re.M)) != {"name", "description"}:
        errors.append("Entry frontmatter must contain only name and description")
    if not re.search(rf"^# StateDyne {re.escape(version)}$", entry_text, re.M):
        errors.append("Skill version differs from source map")
    if (root / "NOTICE").read_text().splitlines()[0] != f"StateDyne Skill {version}":
        errors.append("NOTICE version differs")
    for name, profile in manifest["profiles"].items():
        paths = profile["paths"]
        if len(paths) != len(set(paths)) or not set(paths).issubset(listed):
            errors.append(f"Invalid profile {name}")
            continue
        if all(safe_path(root, p).exists() for p in paths):
            for key, mode in [("bytes", "bytes"), ("characters", "text")]:
                total = sum(len(safe_path(root, p).read_bytes() if mode == "bytes"
                                else safe_path(root, p).read_text()) for p in paths)
                if profile.get(key) != total:
                    errors.append(f"Profile {name}: {key} mismatch")
    for key in ("method", "engineering"):
        source = manifest[key]
        p = safe_path(root, source["path"])
        if hashlib.sha256(p.read_bytes()).hexdigest() != source["sha256"]:
            errors.append(f"Source identity mismatch: {key}")
    ui = (root / "agents/openai.yaml").read_text()
    for field in ("display_name", "short_description", "default_prompt", "icon_small", "icon_large"):
        match = re.search(rf"^  {field}: (.+)$", ui, re.M)
        try:
            raw = match.group(1).strip() if match else None
            val = (ui_data["interface"].get(field) if ui_data is not None else
                   json.loads(raw) if raw and raw.startswith('"') else raw)
            if not isinstance(val, str):
                raise ValueError("not a string")
            if field == "short_description" and not 25 <= len(val) <= 64:
                errors.append("UI short description outside 25..64 characters")
            if field == "default_prompt" and "$statedyne" not in val:
                errors.append("UI prompt lacks skill invocation")
            if field.startswith("icon_") and not safe_path(root, val).is_file():
                errors.append(f"Missing {field}")
        except (ValueError, AttributeError):
            errors.append(f"Invalid UI field {field}")
    errors.extend(check_downloads(root, version, require_downloads))
    return errors, manifest["profiles"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--strict-bytes", action="store_true",
                        help="Require exact release bytes, including UI YAML formatting")
    parser.add_argument("--require-downloads", action="store_true",
                        help="Require and validate the four public release archives in downloads/")
    args = parser.parse_args()
    try:
        errors, profiles = check(args.root.resolve(), args.strict_bytes, args.require_downloads)
    except (OSError, ValueError, KeyError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    if errors:
        print("\n".join(f"FAIL: {e}" for e in errors), file=sys.stderr)
        return 1
    print(json.dumps({"structure": "PASS", "profiles": profiles,
                      "identity_mode": "exact bytes" if args.strict_bytes else
                      "exact runtime/method bytes; UI semantic equivalence and recorded host icon byte variants",
                      "limit": "File identity and structural consistency only; no quality or timing claim."},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
