#!/bin/bash
# SOSTEscrow Foundry test runner
set -e

cd "$(dirname "$0")"

if ! command -v forge &> /dev/null; then
    echo "Foundry not installed. Install with:"
    echo "  curl -L https://foundry.paradigm.xyz | bash"
    echo "  foundryup"
    exit 1
fi

# Install forge-std if not present
if [ ! -d "lib/forge-std" ]; then
    echo "Installing forge-std..."
    forge install foundry-rs/forge-std --no-commit
fi

echo "Running SOSTEscrow tests..."
forge test -vvv
