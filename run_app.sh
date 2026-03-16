#!/bin/bash

find /tmp -maxdepth 1 -name "browser_manager_*" -type d -mmin +720 -exec sudo rm -rf {} +
find /tmp -maxdepth 1 -name "org.chromium.Chromium*" -type d -mmin +720 -exec sudo rm -rf {} +
find /tmp -maxdepth 1 -name "hffs-*" -mmin +720 -exec sudo rm -rf {} +
find /tmp -maxdepth 1 -name "perf-*.map" -mmin +720 -exec sudo rm -f {} +
find /tmp -maxdepth 1 -name "pip-unpack-*" -mmin +720 -exec sudo rm -rf {} +
find /tmp -maxdepth 1 -name "playwright-artifacts-*" -mmin +720 -exec sudo rm -rf {} +
find /tmp -maxdepth 1 -name "neko_port_state.*" -mmin +720 -exec sudo rm -f {} +

# Kill any existing instance
pkill -f "panelflow_env/.*python main.py $*$" 2>/dev/null || true

# CPU affinity setup: reserves 2 cores, uses remaining cores
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
exec taskset -c "$CORE_LIST" nice -n 15 python main.py "$@"
