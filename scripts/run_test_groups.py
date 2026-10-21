#!/usr/bin/env python3
"""Run the deterministic suite in isolated import/runtime groups.

Some legacy tests reuse module-global synthetic fixtures. Group isolation
prevents cross-module state contamination while preserving EVERY test case.
No real model calls are made.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
TEST_ROOT=ROOT/'tests'
NUM_GROUPS=4
GROUP_TIMEOUT_SECONDS=240


def module_names():
    return sorted(p.stem for p in TEST_ROOT.glob('test_*.py'))


def run_group(index):
    sys.path.insert(0,str(ROOT/'scripts'))
    sys.path.insert(0,str(TEST_ROOT))
    all_names=module_names()
    names=all_names[index::NUM_GROUPS]
    suite=unittest.TestSuite()
    loader=unittest.TestLoader()
    for name in names:
        suite.addTests(loader.loadTestsFromName(name))
    print(f'Group {index+1}/{NUM_GROUPS}: {suite.countTestCases()} tests in {len(names)} modules',flush=True)
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


def main():
    if len(sys.argv)==3 and sys.argv[1]=='--group':
        index=int(sys.argv[2]);return run_group(index)
    if len(sys.argv)!=1:
        print('Usage: python scripts/run_test_groups.py [--group 0..3]',file=sys.stderr)
        return 2
    # Independent test groups do not need to share an interpreter, cache or
    # environment. Run each in its own process concurrently. Capture each
    # group's full output and enforce an explicit timeout, so a flaky fixture
    # cannot silently hold a release/CI job forever. Report every group,
    # including failures, rather than stopping after the first result.
    def launch(index):
        command=[sys.executable,str(Path(__file__).resolve()),'--group',str(index)]
        try:
            done=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,
                                timeout=GROUP_TIMEOUT_SECONDS,check=False)
            return index,done.returncode,done.stdout,done.stderr
        except subprocess.TimeoutExpired as error:
            out=error.stdout or b''
            err=error.stderr or b''
            if isinstance(out,bytes): out=out.decode('utf-8','replace')
            if isinstance(err,bytes): err=err.decode('utf-8','replace')
            return index,124,out,err+f"\nFAIL: group exceeded {GROUP_TIMEOUT_SECONDS} seconds\n"
    results={}
    with ThreadPoolExecutor(max_workers=NUM_GROUPS) as pool:
        for future in as_completed([pool.submit(launch,i) for i in range(NUM_GROUPS)]):
            index,code,out,err=future.result()
            results[index]=(code,out,err)
    failures=0
    for index in range(NUM_GROUPS):
        code,out,err=results[index]
        print(f"\n===== isolated group {index+1}/{NUM_GROUPS}: {'PASS' if code==0 else 'FAIL'} =====",flush=True)
        if out: print(out.rstrip(),flush=True)
        if err: print(err.rstrip(),file=sys.stderr,flush=True)
        if code: failures+=1
    if failures:
        print(f'FAIL: {failures} isolated test groups did not pass.',file=sys.stderr,flush=True)
        return 1
    print('PASS: all deterministic tests across isolated groups; not a live model evaluation.',flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
