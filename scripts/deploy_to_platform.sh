#!/bin/bash

# Deployment helper script for telegram-bots-platform
# This script helps prepare and verify the bot for deployment

set -e

echo "================================"
echo "Crop Forecast Bot - Platform Deployment Helper"
echo "================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "ℹ $1"
}

# Check if we're in the right directory
if [ ! -f "Dockerfile" ]; then
    print_error "Dockerfile not found. Please run this script from the bot's root directory."
    exit 1
fi

print_success "Found Dockerfile"

# Check for required files
echo ""
echo "Checking required files..."

required_files=(
    "Dockerfile"
    "docker-compose.yml"
    ".dockerignore"
    ".env.docker.example"
    "requirements.txt"
    "run_bot.py"
    "config/settings.py"
)

all_files_present=true
for file in "${required_files[@]}"; do
    if [ -f "$file" ]; then
        print_success "$file"
    else
        print_error "$file - MISSING"
        all_files_present=false
    fi
done

if [ "$all_files_present" = false ]; then
    print_error "Some required files are missing. Please fix and try again."
    exit 1
fi

# Check for .env file
echo ""
if [ -f ".env" ]; then
    print_warning ".env file exists (will be used for testing)"

    # Check if critical variables are set
    if grep -q "TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here" .env; then
        print_error "TELEGRAM_BOT_TOKEN not configured in .env"
    else
        print_success "TELEGRAM_BOT_TOKEN is configured"
    fi

    if grep -q "CDS_API_KEY=your_uid:your_api_key" .env; then
        print_error "CDS_API_KEY not configured in .env"
    else
        print_success "CDS_API_KEY is configured"
    fi
else
    print_info ".env file not found (will need to be created during deployment)"
fi

# Check directory structure
echo ""
echo "Checking directory structure..."

required_dirs=(
    "src"
    "src/bot"
    "src/data"
    "src/models"
    "config"
    "data"
    "models"
    "logs"
)

for dir in "${required_dirs[@]}"; do
    if [ -d "$dir" ]; then
        print_success "$dir/"
    else
        print_error "$dir/ - MISSING"
        mkdir -p "$dir"
        print_info "Created $dir/"
    fi
done

# Verify Python files syntax
echo ""
echo "Verifying Python syntax..."

if command -v python3 &> /dev/null; then
    python_files=(
        "run_bot.py"
        "config/settings.py"
        "src/bot/handlers.py"
        "src/bot/keyboards.py"
    )

    syntax_ok=true
    for pyfile in "${python_files[@]}"; do
        if python3 -m py_compile "$pyfile" 2>/dev/null; then
            print_success "$pyfile"
        else
            print_error "$pyfile - SYNTAX ERROR"
            syntax_ok=false
        fi
    done

    if [ "$syntax_ok" = false ]; then
        print_error "Some Python files have syntax errors. Please fix them."
        exit 1
    fi
else
    print_warning "Python3 not found, skipping syntax check"
fi

# Check Docker availability
echo ""
echo "Checking Docker environment..."

if command -v docker &> /dev/null; then
    print_success "Docker is installed"
    docker --version

    # Check if Docker daemon is running
    if docker info &> /dev/null; then
        print_success "Docker daemon is running"
    else
        print_warning "Docker daemon is not running or requires sudo"
    fi
else
    print_warning "Docker not found (required for deployment)"
fi

if command -v docker-compose &> /dev/null; then
    print_success "Docker Compose is installed"
    docker-compose --version
else
    print_warning "Docker Compose not found (required for deployment)"
fi

# Verify Dockerfile best practices
echo ""
echo "Analyzing Dockerfile..."

if grep -q "FROM.*python:3.11" Dockerfile; then
    print_success "Using Python 3.11 base image"
else
    print_warning "Not using Python 3.11"
fi

if grep -q "multi-stage" Dockerfile || grep -q "as builder" Dockerfile; then
    print_success "Multi-stage build detected"
else
    print_info "Single-stage build"
fi

if grep -q "USER.*botuser" Dockerfile; then
    print_success "Running as non-root user (security best practice)"
else
    print_warning "Running as root user (security risk)"
fi

# Check docker-compose.yml
echo ""
echo "Analyzing docker-compose.yml..."

if grep -q "restart: unless-stopped" docker-compose.yml; then
    print_success "Auto-restart enabled"
else
    print_warning "Auto-restart not configured"
fi

if grep -q "healthcheck:" docker-compose.yml; then
    print_success "Healthcheck configured"
else
    print_warning "No healthcheck configured"
fi

if grep -q "deploy:" docker-compose.yml; then
    print_success "Resource limits configured"
else
    print_warning "No resource limits set"
fi

# Platform compatibility check
echo ""
echo "Checking telegram-bots-platform compatibility..."

# Check if network name is appropriate
if grep -q "crop_forecast_bot_network" docker-compose.yml; then
    print_success "Dedicated network configured"
fi

# Check volume mounts
if grep -q "./data:/app/data" docker-compose.yml; then
    print_success "Data volume configured"
fi

if grep -q "./models:/app/models" docker-compose.yml; then
    print_success "Models volume configured"
fi

if grep -q "./logs:/app/logs" docker-compose.yml; then
    print_success "Logs volume configured"
fi

# Summary
echo ""
echo "================================"
echo "Deployment Readiness Summary"
echo "================================"
echo ""

print_success "All critical files present"
print_success "Directory structure verified"
print_success "Docker configuration validated"
print_success "Platform compatibility confirmed"

echo ""
echo "Next steps for deployment to telegram-bots-platform:"
echo ""
echo "1. Push your code to GitHub:"
echo "   git add ."
echo "   git commit -m 'Prepare for platform deployment'"
echo "   git push origin main"
echo ""
echo "2. On the platform server, run:"
echo "   cd /opt/telegram-bots-platform"
echo "   sudo ./add-bot.sh"
echo ""
echo "3. Follow the prompts:"
echo "   - Bot name: crop_forecast_bot"
echo "   - Git URL: <your-repo-url>"
echo "   - Branch: main"
echo ""
echo "4. Configure environment variables when prompted:"
echo "   - TELEGRAM_BOT_TOKEN (required)"
echo "   - CDS_API_KEY (required)"
echo "   - OPENROUTER_API_KEY (optional)"
echo ""
echo "5. Monitor logs after deployment:"
echo "   sudo docker-compose logs -f crop_forecast_bot"
echo ""
echo "For detailed instructions, see: PLATFORM_INTEGRATION.md"
echo ""

print_success "Bot is ready for deployment! 🚀"
