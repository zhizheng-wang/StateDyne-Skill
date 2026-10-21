#!/usr/bin/env python3
"""Bounded source reading. Verification checks identity, not truth."""
import argparse
import json
from pathlib import Path
import re
import sys
from validate_skill import ROOT, check, safe_path


def chunks(text, limit):
    # Slice oversized single lines too, preserving every character.
    return [text[i:i + limit] for i in range(0, len(text), limit)] or [""]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default="method", help="method, engineering, or a manifest profile")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--list", action="store_true", help="list bounded chunks; default without a selection")
    ap.add_argument("--headings", action="store_true")
    ap.add_argument("--find", help="literal case-insensitive text search with line numbers")
    ap.add_argument("--part", type=int, help="1-based chunk")
    ap.add_argument("--parts", help="1-based inclusive range, e.g. 2-4")
    ap.add_argument("--chunk-characters", type=int, default=5000)
    args = ap.parse_args()
    if not 100 <= args.chunk_characters <= 20000:
        ap.error("--chunk-characters must be in 100..20000")
    if args.part is not None and args.parts:
        ap.error("choose --part or --parts")
    try:
        manifest = json.loads((ROOT / "references/source-map.json").read_text())
        if args.source in ("method", "engineering"):
            paths = [manifest[args.source]["path"]]
        elif args.source in manifest["profiles"]:
            paths = manifest["profiles"][args.source]["paths"]
        else:
            ap.error("unknown source/profile")
        if args.verify:
            errors, _ = check()
            if errors:
                raise ValueError("; ".join(errors))
            print("Verified file identity and structural consistency; not semantic correctness.", file=sys.stderr)
        docs = [(p, safe_path(ROOT, p).read_text()) for p in paths]
        if args.headings or args.find:
            for p, text in docs:
                for n, line in enumerate(text.splitlines(), 1):
                    if (args.headings and re.match(r"^#{1,6} ", line)) or (args.find and args.find.casefold() in line.casefold()):
                        print(f"{p}:{n}: {line}")
            return 0
        parts = [(p, n, part) for p, text in docs for n, part in enumerate(chunks(text, args.chunk_characters), 1)]
        if args.part is not None:
            start = end = args.part
        elif args.parts:
            match = re.fullmatch(r"([1-9][0-9]*)-([1-9][0-9]*)", args.parts)
            if not match:
                ap.error("--parts must be N-M")
            start, end = map(int, match.groups())
        else:
            start = end = None
        if start is None or args.list:
            for i, (p, n, part) in enumerate(parts, 1):
                print(f"{i}: {p} chunk {n}, {len(part)} characters")
        else:
            if not 1 <= start <= end <= len(parts):
                ap.error(f"range must be within 1..{len(parts)}")
            for i in range(start - 1, end):
                p, n, part = parts[i]
                print(f"--- {i + 1}/{len(parts)} {p} chunk {n} ---")
                print(part)
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
