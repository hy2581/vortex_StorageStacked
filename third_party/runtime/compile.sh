#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/environment.sh"
exec "$AXI_PYTHON" "$SS_ROOT/third_party/runtime/compile.py" "$@"
