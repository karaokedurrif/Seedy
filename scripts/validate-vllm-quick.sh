#!/bin/bash
# Quick validation script for vLLM v4.7 deployment
# Run this after image download completes
# Usage: ./scripts/validate-vllm-quick.sh

set -euo pipefail

API_KEY="e37eea8c23dd665a7e19169ab05a30c23766b336e410367217031c8cd9303ed4"
VLLM_URL="http://192.168.20.57:8001"

echo "🚀 vLLM v4.7 Quick Validation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Test 1: Health check
echo "📋 Test 1: Health Check"
if curl -sf "$VLLM_URL/health" > /dev/null 2>&1; then
    echo "✅ PASS - Server healthy"
else
    echo "❌ FAIL - Server not responding"
    exit 1
fi
echo ""

# Test 2: Models endpoint
echo "📋 Test 2: Models Endpoint"
models_response=$(curl -s -H "Authorization: Bearer $API_KEY" "$VLLM_URL/v1/models")
if echo "$models_response" | grep -q "qwen2.5-coder-32b-awq"; then
    echo "✅ PASS - Model listed"
    echo "$models_response" | jq -C '.' 2>/dev/null || echo "$models_response"
else
    echo "❌ FAIL - Model not found"
    echo "$models_response"
    exit 1
fi
echo ""

# Test 3: Single inference (short)
echo "📋 Test 3: Single Inference (Quick)"
start_time=$(date +%s)
inference_response=$(curl -s -X POST "$VLLM_URL/v1/chat/completions" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{
        "model": "/models/qwen2.5-coder-32b-awq",
        "messages": [{"role": "user", "content": "Say hello in Python"}],
        "max_tokens": 50,
        "temperature": 0.7
    }')
end_time=$(date +%s)
latency=$((end_time - start_time))

if echo "$inference_response" | grep -q "choices"; then
    echo "✅ PASS - Inference successful"
    echo "⏱️  Latency: ${latency}s"
    echo "$inference_response" | jq -C '.choices[0].message.content' 2>/dev/null || echo "$inference_response"
else
    echo "❌ FAIL - Inference failed"
    echo "$inference_response"
    exit 1
fi
echo ""

# Test 4: Ollama survival check
echo "📋 Test 4: Ollama Survival (GPU coexistence)"
if ssh daviddgx@192.168.20.57 "docker exec ollama ollama run qwen2.5:7b 'Test' --verbose" 2>&1 | grep -q "success\|test"; then
    echo "✅ PASS - Ollama still responsive"
else
    echo "⚠️  WARNING - Ollama may be affected by vLLM memory usage"
    echo "   This is expected if both models are large"
fi
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 VALIDATION COMPLETE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "All core tests passed! vLLM v4.7 is operational."
echo ""
echo "Next steps:"
echo "1. Run full validation: docs/V4.7_FINALIZACION.md"
echo "2. Configure Openclaw: docs/OPENCLAW_MINIPC_VLLM_CONFIG.md"
echo "3. Configure Continue.dev: docs/vllm-coder-v4.7.md (Section 7)"
echo ""
