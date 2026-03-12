#!/bin/bash

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
