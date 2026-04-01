#!/bin/bash
# PCBooker bootstrap + run script
# Creates venv if missing, installs deps, runs the app

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/venv"
REQ="$SCRIPT_DIR/requirements.txt"

# Create venv if missing
if [ ! -d "$VENV" ]; then
    echo "Creating venv in $VENV..."
    python3 -m venv "$VENV" || { echo "FAILED: python3 -m venv"; exit 1; }
    echo "Installing dependencies..."
    "$VENV/bin/pip" install --upgrade pip -q
    "$VENV/bin/pip" install -r "$REQ" || { echo "FAILED: pip install"; exit 1; }
    echo "Done."
elif [ "$REQ" -nt "$VENV/.deps_installed" ] 2>/dev/null; then
    echo "requirements.txt changed, updating deps..."
    "$VENV/bin/pip" install -r "$REQ" -q
    touch "$VENV/.deps_installed"
fi

# Mark deps as installed
touch "$VENV/.deps_installed"

# Run
exec "$VENV/bin/python3" "$SCRIPT_DIR/pcbooker.py" "$@"
