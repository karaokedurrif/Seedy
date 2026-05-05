#!/bin/bash
# Monitor vLLM deployment status on DGX
# Usage: ./scripts/monitor-vllm-deployment.sh

set -euo pipefail

DGX_HOST="daviddgx@192.168.20.57"
COMPOSE_DIR="~/seedy/coder-vllm"

echo "🔍 Monitoring vLLM deployment on DGX..."
echo ""

# Function to check image download
check_image() {
    echo "📦 Checking image download..."
    if ssh "$DGX_HOST" "docker images | grep -q vllm/vllm-openai"; then
        echo "✅ Image vllm/vllm-openai:latest downloaded"
        return 0
    else
        echo "⏳ Image still downloading..."
        return 1
    fi
}

# Function to check container status
check_container() {
    echo "🐳 Checking container status..."
    local status
    status=$(ssh "$DGX_HOST" "cd $COMPOSE_DIR && docker compose ps --format json 2>/dev/null" || echo "[]")
    
    if [ "$status" = "[]" ] || [ -z "$status" ]; then
        echo "⏳ Container not yet created"
        return 1
    fi
    
    local container_status
    container_status=$(echo "$status" | jq -r '.[0].State' 2>/dev/null || echo "unknown")
    
    case "$container_status" in
        "running")
            echo "✅ Container running"
            return 0
            ;;
        "starting"|"health: starting")
            echo "🔄 Container starting..."
            return 1
            ;;
        *)
            echo "⚠️  Container status: $container_status"
            return 1
            ;;
    esac
}

# Function to check health
check_health() {
    echo "🏥 Checking health endpoint..."
    local health_status
    health_status=$(ssh "$DGX_HOST" "curl -sf http://localhost:8001/health 2>/dev/null" || echo "fail")
    
    if [ "$health_status" != "fail" ]; then
        echo "✅ Health check passed"
        return 0
    else
        echo "⏳ Waiting for server to be ready..."
        return 1
    fi
}

# Function to test models endpoint
test_models() {
    echo "🤖 Testing /v1/models endpoint..."
    local models
    models=$(ssh "$DGX_HOST" "curl -s -H 'Authorization: Bearer e37eea8c23dd665a7e19169ab05a30c23766b336e410367217031c8cd9303ed4' http://localhost:8001/v1/models 2>/dev/null" || echo "fail")
    
    if echo "$models" | grep -q "qwen2.5-coder-32b"; then
        echo "✅ Model endpoint responding correctly"
        echo "$models" | jq '.' 2>/dev/null || echo "$models"
        return 0
    else
        echo "⏳ Model endpoint not ready yet"
        return 1
    fi
}

# Main monitoring loop
MAX_WAIT=1800  # 30 minutes
ELAPSED=0
INTERVAL=30    # Check every 30 seconds

while [ $ELAPSED -lt $MAX_WAIT ]; do
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "⏱️  Elapsed: ${ELAPSED}s / ${MAX_WAIT}s"
    echo ""
    
    # Stage 1: Image download
    if ! check_image; then
        echo ""
        echo "💡 Tip: Image download can take 10-15 minutes"
        echo "   Current progress visible in docker compose logs"
        sleep $INTERVAL
        ELAPSED=$((ELAPSED + INTERVAL))
        continue
    fi
    
    # Stage 2: Container creation and startup
    if ! check_container; then
        echo ""
        echo "💡 Tip: If image is downloaded but container not created,"
        echo "   it may need manual restart: docker compose up -d"
        sleep $INTERVAL
        ELAPSED=$((ELAPSED + INTERVAL))
        continue
    fi
    
    # Stage 3: Health check
    if ! check_health; then
        echo ""
        echo "💡 Tip: Model loading can take 2-3 minutes"
        echo "   View logs: ssh $DGX_HOST \"cd $COMPOSE_DIR && docker compose logs -f\""
        sleep $INTERVAL
        ELAPSED=$((ELAPSED + INTERVAL))
        continue
    fi
    
    # Stage 4: Models endpoint test
    if ! test_models; then
        sleep $INTERVAL
        ELAPSED=$((ELAPSED + INTERVAL))
        continue
    fi
    
    # All checks passed!
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🎉 vLLM DEPLOYMENT COMPLETE!"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "✅ Image downloaded"
    echo "✅ Container running"
    echo "✅ Health check passed"
    echo "✅ Model endpoint ready"
    echo ""
    echo "Next steps:"
    echo "1. Run inference test: docs/V4.7_FINALIZACION.md (Section 4)"
    echo "2. Configure Openclaw: docs/V4.7_FINALIZACION.md (Section 7)"
    echo "3. Test Continue.dev: docs/V4.7_FINALIZACION.md (Section 9)"
    echo ""
    exit 0
done

# Timeout reached
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⏱️  TIMEOUT REACHED (${MAX_WAIT}s)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Deployment still in progress. Check manually:"
echo "  ssh $DGX_HOST"
echo "  cd $COMPOSE_DIR"
echo "  docker compose logs -f"
echo ""
exit 1
