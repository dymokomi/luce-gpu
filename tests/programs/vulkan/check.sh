#!/bin/sh
# Vulkan submission batching, deferred destruction and pooled memory, on Vulkan hosts.
set -eu
cd "$(dirname "$0")/../../.."
mkdir -p build
exec python3 tests/programs/vulkan/run.py "${1:-../luce-base/build/luce-base}"
