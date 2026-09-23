#!/usr/bin/env python3
"""Run this package's tests: every module's `test` blocks and the unit tests under
tests/unit through both backends, then each program check under tests/programs."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT.name
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--base", type=Path, default=ROOT.parent / ("luce-base/build/luce-base.exe" if os.name == "nt" else "luce-base/build/luce-base"))
parser.add_argument("--skip-programs", action="store_true", help="only the test blocks")
args = parser.parse_args()
compiler = str(args.base.resolve())
env = dict(os.environ, LUCE_BASE=compiler)
(ROOT / "build").mkdir(exist_ok=True)

def run(command, **kwargs):
    subprocess.run([str(part) for part in command], check=True, env=env, cwd=ROOT, timeout=900, **kwargs)

source = ROOT / "src" / PACKAGE.replace("-", "_")
targets = sorted(p for p in source.iterdir() if p.suffix == ".lucb" or (p / "ORDER").exists())
targets += sorted((ROOT / "tests/unit").glob("*.lucb")) if (ROOT / "tests/unit").exists() else []
for target in targets:
    text = "".join(f.read_text(encoding="utf-8") for f in ([target] if target.is_file() else target.rglob("*.lucb")))
    if 'test "' not in text:
        continue
    for flags in (["--native"], ["--backend=c"]):
        print(f"== test {target.relative_to(ROOT)} {flags[0]}", flush=True)
        run([compiler, "test", target, *flags], stdout=subprocess.DEVNULL)
if not args.skip_programs:
    for check in sorted((ROOT / "tests/programs").glob("*/check.sh")):
        print(f"== {check.parent.relative_to(ROOT)}", flush=True)
        run(["sh", check, compiler])
print(f"PASS {PACKAGE}: module tests through both backends" + ("" if args.skip_programs else " and program checks"))
