#!/bin/bash
# ================================================
# ATFM System - Full Setup Script
# Run this once to install everything and start
# the application.
#
# Usage: bash setup.sh
# ================================================

set -e  # stop on any error

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$PROJECT_DIR/.env"

echo ""
echo "========================================"
echo "  ATFM System - Setup"
echo "========================================"
echo ""

# ------------------------------------------------
# STEP 1: Install Homebrew (if not installed)
# ------------------------------------------------
echo "[1/6] Checking Homebrew..."
if ! command -v brew &>/dev/null; then
    echo "      Installing Homebrew (you may be asked for your password)..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    # Add homebrew to PATH for Apple Silicon and Intel Macs
    if [ -f /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
    elif [ -f /usr/local/bin/brew ]; then
        eval "$(/usr/local/bin/brew shellenv)"
    fi
    echo "      Homebrew installed."
else
    echo "      Homebrew already installed. OK"
fi

# ------------------------------------------------
# STEP 2: Install PostgreSQL (if not installed)
# ------------------------------------------------
echo ""
echo "[2/6] Checking PostgreSQL..."
if ! command -v psql &>/dev/null; then
    echo "      Installing PostgreSQL..."
    brew install postgresql@16
    brew link --force postgresql@16
    echo "      PostgreSQL installed."
else
    echo "      PostgreSQL already installed. OK"
fi

# ------------------------------------------------
# STEP 3: Start PostgreSQL service
# ------------------------------------------------
echo ""
echo "[3/6] Starting PostgreSQL service..."
brew services start postgresql@16 2>/dev/null || brew services start postgresql 2>/dev/null || true
sleep 3  # wait for postgres to start

# Check it's running
if pg_isready -q; then
    echo "      PostgreSQL is running. OK"
else
    echo "      ERROR: PostgreSQL failed to start."
    echo "      Try: brew services restart postgresql@16"
    exit 1
fi

# ------------------------------------------------
# STEP 4: Create database and run setup SQL
# ------------------------------------------------
echo ""
echo "[4/6] Setting up database..."

# Read DB credentials from .env
source "$ENV_FILE" 2>/dev/null || true
DB_NAME="${DB_NAME:-atfm_db}"
DB_USER="${DB_USER:-postgres}"
DB_PASS="${DB_PASSWORD:-}"

# Create role/user if it doesn't exist
psql postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 || \
    psql postgres -c "CREATE ROLE $DB_USER WITH LOGIN SUPERUSER PASSWORD '$DB_PASS';"

# Create database if it doesn't exist
psql postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 && \
    echo "      Database '$DB_NAME' already exists. Skipping creation." || \
    (psql postgres -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" && echo "      Database '$DB_NAME' created.")

# Run the full setup SQL
echo "      Loading tables and data..."
PGPASSWORD="$DB_PASS" psql -U "$DB_USER" -d "$DB_NAME" -f "$PROJECT_DIR/db_setup.sql" -q && \
    echo "      Database setup complete. OK"

# ------------------------------------------------
# STEP 5: Install Python packages
# ------------------------------------------------
echo ""
echo "[5/6] Installing Python packages..."
pip3 install --user -r "$PROJECT_DIR/requirements.txt" -q && \
    echo "      Python packages installed. OK"

# ------------------------------------------------
# STEP 6: Start Flask app
# ------------------------------------------------
echo ""
echo "[6/6] Starting ATFM System..."
echo ""
echo "========================================"
echo "  App running at: http://127.0.0.1:5000"
echo ""
echo "  Login credentials:"
echo "  Username: admin1       Password: password123"
echo "  Username: airline_ba   Password: password123"
echo "  Username: atc_dxb      Password: password123"
echo "  Username: airport_ops1 Password: password123"
echo "  Username: ai_analyst1  Password: password123"
echo "  Username: observer1    Password: password123"
echo ""
echo "  Press CTRL+C to stop the server."
echo "========================================"
echo ""

cd "$PROJECT_DIR"
python3 app.py
