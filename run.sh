#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
command=${1:-run}
[[ $# == 0 ]] || shift
case "$command" in
    setup|build) exec bash "$root/scripts/$command.sh" "$@" ;;
    run|test|check|validate|config)
        source "$root/scripts/activate.sh"
        if [[ "$command" == config ]]; then
            exec "$AXI_PYTHON" "$root/scripts/configure.py" --show "$@"
        fi
        exec "$AXI_PYTHON" "$root/scripts/$command.py" "$@" ;;
    *) echo "用法: ./run.sh {setup|build|config|run|test|check|validate} [参数]" >&2; exit 2 ;;
esac
