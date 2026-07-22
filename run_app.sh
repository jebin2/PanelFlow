#!/bin/bash

set -uo pipefail

# `-m panelflow.v2.batch` needs the repo on the path, and the inbox is resolved
# relative to it — so run from here no matter where the script was called from.
cd "$(dirname "$(readlink -f "$0")")" || exit 1

cleanup() {
    local pattern="$1"
    local type="$2"
    local remove_cmd="$3"

    echo "Cleaning: $pattern"

    if [ -n "$type" ]; then
        find /tmp -maxdepth 1 -name "$pattern" -type "$type" -mmin +720 -exec $remove_cmd {} + \
            || echo "Failed to clean: $pattern"
    else
        find /tmp -maxdepth 1 -name "$pattern" -mmin +720 -exec $remove_cmd {} + \
            || echo "Failed to clean: $pattern"
    fi
}

cleanup "browser_manager_*" "d" "rm -rf"
cleanup "org.chromium.Chromium*" "d" "rm -rf"
cleanup "hffs-*" "" "rm -rf"
cleanup "perf-*.map" "" "rm -f"
cleanup "pip-unpack-*" "" "rm -rf"
cleanup "playwright-artifacts-*" "" "rm -rf"
cleanup "neko_port_state.*" "" "rm -f"

echo "Cleanup completed."

# Kill any existing instance. Matched on the module, not on main.py: the v1
# entry point is gone and the old pattern had the env's name in the wrong case,
# so it never matched anything.
pkill -f "PanelFlow_env/.*python.*panelflow\.v2\.batch" 2>/dev/null || true
sleep 1

# Remove stale lock files
find /tmp -maxdepth 1 -name "panelflow_*.lock" -exec rm -f {} + \
    || echo "Failed to remove lock files"

# CPU affinity setup: reserve 2 cores, use remaining
RESERVED=2
TOTAL=$(nproc)
THREADS=$((TOTAL - RESERVED))

CORE_LIST=""
for ((i=RESERVED; i<TOTAL; i++)); do
    CORE_LIST="${CORE_LIST:+$CORE_LIST,}$i"
done

# Export threading environment variables
export OMP_NUM_THREADS=$THREADS
export MKL_NUM_THREADS=$THREADS
export NUMEXPR_NUM_THREADS=$THREADS
export OPENBLAS_NUM_THREADS=$THREADS

# Run with CPU affinity and nice priority
PYTHON="${PYENV_ROOT:-$HOME/.pyenv}/versions/PanelFlow_env/bin/python"

# The v2 batch loop: every comic in content_to_be_processed, then watch for
# more. Pass --once for a single pass, or --model NAME to override the LLM.
exec taskset -c "$CORE_LIST" nice -n 15 "$PYTHON" -m panelflow.v2.batch "$@"
