#!/bin/bash
# Download Qwen2.5-14B-Instruct model files sequentially with wget (resume support)
set -e

DIR="/home/davidia/models/qwen25_14b_base"
BASE_URL="https://huggingface.co/Qwen/Qwen2.5-14B-Instruct/resolve/main"
mkdir -p "$DIR"

# Download safetensors shards (the big files) one at a time
for i in $(seq 1 8); do
    SHARD=$(printf "model-%05d-of-00008.safetensors" $i)
    if [ -f "$DIR/$SHARD" ]; then
        echo "✅ $SHARD already exists, skipping"
        continue
    fi
    echo "⬇️  Downloading $SHARD..."
    wget -c -q --show-progress -O "$DIR/$SHARD" "$BASE_URL/$SHARD" || {
        echo "❌ Failed to download $SHARD, retrying..."
        sleep 5
        wget -c -q --show-progress -O "$DIR/$SHARD" "$BASE_URL/$SHARD"
    }
    echo "✅ $SHARD done ($(du -h "$DIR/$SHARD" | cut -f1))"
done

# Download small files
for f in config.json generation_config.json model.safetensors.index.json merges.txt tokenizer.json tokenizer_config.json vocab.json special_tokens_map.json added_tokens.json; do
    if [ -f "$DIR/$f" ]; then
        echo "✅ $f exists"
        continue
    fi
    wget -c -q -O "$DIR/$f" "$BASE_URL/$f" 2>/dev/null && echo "✅ $f" || echo "⚠️  $f not found (optional)"
done

echo ""
echo "=== Download complete ==="
du -sh "$DIR"
ls -lh "$DIR"/*.safetensors | wc -l
echo "safetensors files"
