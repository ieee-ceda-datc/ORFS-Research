#!/bin/bash
# run_all.sh - sequentially run maindriver.sh for multiple (design, platform) pairs

# define (design, platform) pairs
pairs=(
  "aes asap7"
  "aes sky130hd"
  "ibex sky130hd"
  "ibex asap7"
  "jpeg sky130hd"
  "jpeg asap7"
)

# Execute each combination sequentially
for pair in "${pairs[@]}"; do
  read d p <<< "$pair"
  echo "==========================================="
  echo "Running design: $d, platform: $p"
  echo "==========================================="
  ./maindriver.sh -p "$p" -d "$d" -o DWL
  echo
done
