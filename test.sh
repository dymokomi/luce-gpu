#!/bin/sh
# The package's gate: its own checks, then every module's tests and program checks.
set -eu
cd "$(dirname "$0")"
compiler="${LUCE_BASE:-../luce-base/build/luce-base}"
python3 tools/test_platform_boundaries.py
exec python3 tests/run.py --base "$compiler" "$@"
