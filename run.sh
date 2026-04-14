#!/bin/bash
# ================================================
# ATFM System - Start Application
# Run this after setup.sh has been run once.
# Usage: bash run.sh
# ================================================

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Add PostgreSQL 18 to PATH
export PATH="/Library/PostgreSQL/18/bin:$PATH"

# Check PostgreSQL is running
if ! pg_isready -q 2>/dev/null; then
    echo "ERROR: PostgreSQL is not running."
    echo "Start it from: Applications > PostgreSQL 18 > Start Service"
    exit 1
fi

echo ""
echo "========================================"
echo "  ATFM System running at:"
echo "  http://127.0.0.1:8080"
echo ""
echo "  Press CTRL+C to stop."
echo "========================================"
echo ""

cd "$PROJECT_DIR"
python3 app.py
