#!/bin/bash
# Lilith Unified Dashboard - Startup Script
# Starts all required services and the dashboard

set -e

echo "🜏 Lilith Unified Dashboard - Starting services..."
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check dependencies
check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "${RED}✗ $1 not found${NC}"
        return 1
    else
        echo -e "${GREEN}✓ $1 found${NC}"
        return 0
    fi
}

echo "Checking dependencies..."
check_command node
check_command npm
check_command python3
check_command curl

# Check if Lilith Gateway is running
echo ""
echo "Checking Lilith Gateway (port 8080)..."
if curl -s http://localhost:8080/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Lilith Gateway is running${NC}"
else
    echo -e "${YELLOW}⚠ Lilith Gateway not running on port 8080${NC}"
    echo "  Starting Lilith Gateway..."
    
    # Start Lilith Gateway in background
    cd /home/tehlappy/Projects/Dev\ Console/vm-ai-gateway/lilith-gateway
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
    fi
    nohup python3 gateway_server.py > /tmp/lilith-gateway.log 2>&1 &
    GATEWAY_PID=$!
    echo $GATEWAY_PID > /tmp/lilith-gateway.pid
    
    # Wait for gateway to start
    echo "  Waiting for gateway to start..."
    for i in {1..10}; do
        if curl -s http://localhost:8080/health > /dev/null 2>&1; then
            echo -e "${GREEN}✓ Lilith Gateway started (PID: $GATEWAY_PID)${NC}"
            break
        fi
        sleep 1
    done
fi

# Check if Ollama is running
echo ""
echo "Checking Ollama (port 11434)..."
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Ollama is running${NC}"
else
    echo -e "${YELLOW}⚠ Ollama not running on port 11434${NC}"
    echo "  Start with: ollama serve"
fi

# Check environment variables
echo ""
echo "Checking environment..."
if [ -z "$GEMINI_API_KEY" ]; then
    echo -e "${YELLOW}⚠ GEMINI_API_KEY not set${NC}"
    echo "  AI features will be limited. Set with: export GEMINI_API_KEY=your_key"
else
    echo -e "${GREEN}✓ GEMINI_API_KEY configured${NC}"
fi

if [ -z "$GITHUB_TOKEN" ]; then
    echo -e "${YELLOW}⚠ GITHUB_TOKEN not set${NC}"
    echo "  GitHub API rate limited. Set with: export GITHUB_TOKEN=your_token"
else
    echo -e "${GREEN}✓ GITHUB_TOKEN configured${NC}"
fi

# Install dashboard dependencies if needed
echo ""
echo "Setting up Unified Dashboard..."
cd /home/tehlappy/Projects/UnifiedDashboard

if [ ! -d "node_modules" ]; then
    echo "  Installing dependencies..."
    npm install
fi

# Build if in production
if [ "$1" = "production" ] || [ "$1" = "prod" ]; then
    echo "  Building for production..."
    npm run build
    echo -e "${GREEN}✓ Build complete${NC}"
    echo ""
    echo "Starting production server..."
    npm start
else
    echo -e "${GREEN}✓ Ready for development${NC}"
    echo ""
    echo "Starting development servers..."
    echo ""
    echo "  Frontend: http://localhost:5173 (Vite)"
    echo "  Backend:  http://localhost:3000 (Express)"
    echo "  Gateway:  http://localhost:8080 (Lilith)"
    echo ""
    echo "Press Ctrl+C to stop all services"
    echo ""
    
    # Start both frontend and backend
    npm run dev
fi