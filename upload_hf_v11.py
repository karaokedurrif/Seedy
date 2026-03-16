#!/usr/bin/env python3
"""
Upload seedy-v11 merged model to HuggingFace using the Python API.
More reliable than CLI for large models (28 GB with 6 shards).
"""
from huggingface_hub import HfApi, create_repo
import os

REPO_ID = "durrif/seedy-v11"
MODEL_DIR = "/home/davidia/models/seedy_v11_merged"
HF_TOKEN = os.environ.get("HF_TOKEN", "")

api = HfApi(token=HF_TOKEN)

# 1. Create repo if needed
print("=" * 60)
print(f"Uploading seedy-v11 to HuggingFace: {REPO_ID}")
print("=" * 60)

try:
    repo_info = api.repo_info(REPO_ID)
    print(f"✅ Repo already exists: {REPO_ID}")
except Exception:
    print(f"Creating repo {REPO_ID}...")
    create_repo(REPO_ID, repo_type="model", token=HF_TOKEN, private=False)
    print(f"✅ Repo created: {REPO_ID}")

# 2. List files to upload
files = os.listdir(MODEL_DIR)
total_size = sum(os.path.getsize(os.path.join(MODEL_DIR, f)) for f in files if os.path.isfile(os.path.join(MODEL_DIR, f)))
print(f"\nFiles to upload: {len(files)}")
print(f"Total size: {total_size / 1e9:.1f} GB")
for f in sorted(files):
    fp = os.path.join(MODEL_DIR, f)
    if os.path.isfile(fp):
        print(f"  {f}: {os.path.getsize(fp) / 1e9:.2f} GB")

# 3. Upload folder with progress
print(f"\n{'='*60}")
print("Starting upload... (this will take ~30-60 min for 28 GB)")
print(f"{'='*60}")

url = api.upload_large_folder(
    folder_path=MODEL_DIR,
    repo_id=REPO_ID,
    repo_type="model",
)

print(f"\n{'='*60}")
print(f"✅ Upload COMPLETE!")
print(f"URL: https://huggingface.co/{REPO_ID}")
print(f"{'='*60}")
