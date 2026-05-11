#!/bin/bash

set -uo pipefail

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

# Kill any existing instance
pkill -f "panelflow_env/.*python main.py" 2>/dev/null || true
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

exec taskset -c "$CORE_LIST" nice -n 15 "$PYTHON" main.py "$@"
