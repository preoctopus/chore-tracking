#!/bin/bash
# run_dev.sh - Dev runner for ChoreTracker Pro (Local Flask + Docker MongoDB)

# Exit on any command failure
set -e

echo "========================================================="
echo "   ChoreTracker Pro - Local Development Server           "
echo "========================================================="

# 1. Verify Docker Daemon is running
if ! docker info >/dev/null 2>&1; then
    echo "❌ Error: Docker is not running. Please start Docker Desktop and try again."
    exit 1
fi

# 2. Spin up MongoDB Container in the background
echo "🚀 Bootstrapping MongoDB service in Docker..."
docker-compose up -d db

# 3. Wait for MongoDB to report healthy status
echo -n "⏳ Waiting for MongoDB container healthcheck..."
until [ "$(docker inspect --format='{{json .State.Health.Status}}' chore_tracker_db 2>/dev/null)" == "\"healthy\"" ]; do
    echo -n "."
    sleep 1.5
done
echo ""
echo "✅ MongoDB is running and healthy on host port 27017!"

# 4. Set local host environment variables and detect open port
PORT=5000
if lsof -Pi :5000 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "⚠️  Port 5000 is already in use (possibly by macOS AirPlay Receiver or another process)."
    echo "🔌 Automatically switching local development server port to 5001..."
    PORT=5001
fi
export PORT
export MONGO_URI="mongodb://localhost:27017/chore_tracking"
export FLASK_SECRET_KEY="dev-secret-key-chore-tracker-12345"
export FLASK_DEBUG=1
export FLASK_ENV=development

# 5. Check/Create Python virtual environment and install dependencies
if [ ! -d "VENV" ] && [ ! -d "venv" ] && [ ! -d ".venv" ]; then
    echo "📦 Virtual environment not found. Creating virtual environment 'VENV'..."
    python3 -m venv VENV
fi

if [ -d "VENV" ]; then
    echo "📦 Activating virtual environment (VENV)..."
    source VENV/bin/activate
elif [ -d "venv" ]; then
    echo "📦 Activating virtual environment (venv)..."
    source venv/bin/activate
else
    echo "📦 Activating virtual environment (.venv)..."
    source .venv/bin/activate
fi

echo "📥 Verifying and installing dependencies from requirements.txt..."
pip install -r requirements.txt

# 6. Run Flask Application locally on the host
echo "🔌 Starting local Flask development server on http://localhost:$PORT ..."
python3 app.py
