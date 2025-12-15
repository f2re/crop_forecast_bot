#!/bin/bash
# Network connectivity check script for crop_forecast_bot

echo "================================================"
echo "Crop Forecast Bot - Network Diagnostics"
echo "================================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_success() { echo -e "${GREEN}✓${NC} $1"; }
print_error() { echo -e "${RED}✗${NC} $1"; }
print_warning() { echo -e "${YELLOW}⚠${NC} $1"; }
print_info() { echo -e "ℹ $1"; }

# Check if container is running
echo "1. Checking container status..."
if docker ps | grep -q crop_forecast_bot; then
    print_success "Container is running"
    CONTAINER_ID=$(docker ps -qf "name=crop_forecast_bot")
else
    print_error "Container is not running"
    echo ""
    echo "Start the container with:"
    echo "  sudo docker-compose up -d"
    exit 1
fi

echo ""

# Check DNS resolution inside container
echo "2. Checking DNS resolution..."
if docker exec crop_forecast_bot sh -c "nslookup api.telegram.org > /dev/null 2>&1"; then
    IP=$(docker exec crop_forecast_bot sh -c "nslookup api.telegram.org 2>/dev/null | grep -A1 'Name:' | tail -1 | awk '{print \$2}'")
    print_success "DNS resolves api.telegram.org → $IP"
else
    print_error "DNS resolution failed"
    echo "  Fix: Add DNS to docker-compose.yml:"
    echo "    dns:"
    echo "      - 8.8.8.8"
    echo "      - 8.8.4.4"
fi

echo ""

# Check internet connectivity
echo "3. Checking internet connectivity..."
if docker exec crop_forecast_bot sh -c "ping -c 1 8.8.8.8 > /dev/null 2>&1"; then
    print_success "Can reach 8.8.8.8 (Google DNS)"
else
    print_error "Cannot reach internet"
    echo "  Check Docker network settings"
fi

echo ""

# Check HTTPS connectivity to Telegram
echo "4. Checking Telegram API connectivity..."
if docker exec crop_forecast_bot sh -c "python -c 'import requests; requests.get(\"https://api.telegram.org\", timeout=5)' > /dev/null 2>&1"; then
    print_success "Can connect to api.telegram.org via HTTPS"
else
    print_error "Cannot connect to Telegram API"
    echo "  Possible causes:"
    echo "    - Firewall blocking port 443"
    echo "    - Network policy restrictions"
    echo "    - Telegram API down (check https://telegram.org/blog)"
fi

echo ""

# Check bot startup logs
echo "5. Checking bot startup logs..."
if docker logs crop_forecast_bot 2>&1 | grep -q "✓ Сеть доступна"; then
    print_success "Bot successfully verified network on startup"
elif docker logs crop_forecast_bot 2>&1 | grep -q "⚠ Сеть недоступна"; then
    print_warning "Bot had network issues on startup (may have recovered)"
    ATTEMPTS=$(docker logs crop_forecast_bot 2>&1 | grep -c "попытка")
    echo "  Network check attempts: $ATTEMPTS"
else
    print_info "No network check logs found (bot may not have started yet)"
fi

echo ""

# Check for errors
echo "6. Checking for errors in logs..."
ERROR_COUNT=$(docker logs crop_forecast_bot 2>&1 | grep -c "ConnectionError\|ReadTimeout\|Network is unreachable")
if [ "$ERROR_COUNT" -eq 0 ]; then
    print_success "No network errors found in logs"
else
    print_warning "Found $ERROR_COUNT network error(s) in logs"
    echo ""
    echo "Recent errors:"
    docker logs crop_forecast_bot 2>&1 | grep -E "(ConnectionError|ReadTimeout|Network is unreachable)" | tail -5
fi

echo ""

# Check healthcheck status
echo "7. Checking healthcheck status..."
HEALTH=$(docker inspect crop_forecast_bot | grep -A 1 '"Health":' | grep '"Status"' | awk '{print $2}' | tr -d '",')
if [ "$HEALTH" = "healthy" ]; then
    print_success "Container health status: healthy"
elif [ "$HEALTH" = "unhealthy" ]; then
    print_error "Container health status: unhealthy"
    echo "  Last 3 health checks:"
    docker inspect crop_forecast_bot | grep -A 5 '"Log"' | head -15
else
    print_info "Health status: $HEALTH (may still be starting)"
fi

echo ""

# Check network mode
echo "8. Checking network configuration..."
NETWORK_MODE=$(docker inspect crop_forecast_bot | grep '"NetworkMode"' | awk '{print $2}' | tr -d '",')
if [ "$NETWORK_MODE" = "bridge" ] || [ "$NETWORK_MODE" = "default" ]; then
    print_success "Network mode: $NETWORK_MODE (correct)"
else
    print_warning "Network mode: $NETWORK_MODE (may cause issues)"
    echo "  Recommended: bridge"
fi

echo ""

# Check DNS config in container
echo "9. Checking DNS configuration in container..."
DNS_SERVERS=$(docker exec crop_forecast_bot cat /etc/resolv.conf | grep nameserver | awk '{print $2}' | tr '\n' ' ')
if echo "$DNS_SERVERS" | grep -q "8.8.8.8"; then
    print_success "DNS configured: $DNS_SERVERS"
else
    print_warning "DNS servers: $DNS_SERVERS"
    echo "  Recommended: 8.8.8.8, 8.8.4.4"
fi

echo ""

# Summary
echo "================================================"
echo "Network Diagnostics Summary"
echo "================================================"
echo ""

# Count checks
CHECKS_PASSED=$(docker exec crop_forecast_bot sh -c "nslookup api.telegram.org > /dev/null 2>&1" && echo 1 || echo 0)
CHECKS_PASSED=$((CHECKS_PASSED + $(docker exec crop_forecast_bot sh -c "ping -c 1 8.8.8.8 > /dev/null 2>&1" && echo 1 || echo 0)))
CHECKS_PASSED=$((CHECKS_PASSED + $(docker exec crop_forecast_bot sh -c "python -c 'import requests; requests.get(\"https://api.telegram.org\", timeout=5)' > /dev/null 2>&1" && echo 1 || echo 0)))

if [ "$CHECKS_PASSED" -eq 3 ]; then
    print_success "All critical checks passed! Bot should work correctly."
    echo ""
    echo "Monitor logs with:"
    echo "  sudo docker-compose logs -f"
elif [ "$CHECKS_PASSED" -ge 1 ]; then
    print_warning "Some checks passed ($CHECKS_PASSED/3). Review warnings above."
    echo ""
    echo "Check troubleshooting guide:"
    echo "  cat TROUBLESHOOTING_NETWORK.md"
else
    print_error "All checks failed. Network is not configured correctly."
    echo ""
    echo "Quick fix:"
    echo "  1. Stop container: sudo docker-compose down"
    echo "  2. Pull latest: git pull"
    echo "  3. Rebuild: sudo docker-compose build --no-cache"
    echo "  4. Start: sudo docker-compose up -d"
    echo "  5. Re-run: ./scripts/check_network.sh"
fi

echo ""
