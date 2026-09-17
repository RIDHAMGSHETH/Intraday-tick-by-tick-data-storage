"""
===============================================================================
KOTAK NEO - HUGGING FACE DAILY TICK DATA UPLOADER (PARQUET ENGINE)
===============================================================================
Features:
1. Compresses large CSV tick data (500MB - 1GB) into ultra-fast Parquet (85% smaller)
2. Uploads date-partitioned Parquet files to private Hugging Face dataset repository
3. Retries on connection interruptions
4. Supports both Crude Oil & Nifty datasets
5. Provides a simple Python reader function to query data directly from HF
===============================================================================
"""

import os
import sys
import glob
import time
from datetime import datetime
import pandas as pd
from huggingface_hub import HfApi, create_repo

# Configuration (supports environment variables for cloud runners)
HF_TOKEN = os.environ.get("HF_TOKEN", "REDACTED")
REPO_ID = os.environ.get("HF_REPO_ID", "Ridham2310/kotak-tick-data")
REPO_TYPE = "dataset"
IS_PRIVATE = True

RECORDINGS_ROOT = r"C:\Users\Ridham\.gemini\antigravity-ide\scratch\Kotak-neo-api-v2\crude_oil_daily_recordings"

api = HfApi(token=HF_TOKEN)

def ensure_repository():
    """Ensures the Hugging Face private repository exists."""
    try:
        url = create_repo(
            repo_id=REPO_ID,
            repo_type=REPO_TYPE,
            private=IS_PRIVATE,
            exist_ok=True,
            token=HF_TOKEN
        )
        return url
    except Exception as e:
        print(f"[-] Warning verifying repo: {e}")
        return f"https://huggingface.co/datasets/{REPO_ID}"

def convert_and_upload_file(csv_path, asset_name="crudeoil", date_str=None):
    """
    Converts a single CSV to compressed Parquet and uploads to Hugging Face.
    """
    if not os.path.exists(csv_path):
        print(f"[-] File not found: {csv_path}")
        return False

    file_size_mb = os.path.getsize(csv_path) / (1024 * 1024)
    if file_size_mb == 0:
        print(f"[-] Skipping empty file: {csv_path}")
        return False

    base_name = os.path.splitext(os.path.basename(csv_path))[0]
    parquet_path = os.path.join(os.path.dirname(csv_path), f"{base_name}.parquet")

    # Determine date from path or filename if not provided
    if not date_str:
        parent_folder = os.path.basename(os.path.dirname(csv_path))
        if len(parent_folder) == 10 and parent_folder.count("-") == 2:
            date_str = parent_folder
        else:
            date_str = datetime.now().strftime("%Y-%m-%d")

    print(f"\n[*] Processing: {os.path.basename(csv_path)} ({file_size_mb:.1f} MB)")
    
    # 1. Convert to Snappy-compressed Parquet
    print(f"    1. Converting to Apache Parquet...")
    t0 = time.time()
    try:
        df = pd.read_csv(csv_path, low_memory=False)
        df.to_parquet(parquet_path, engine="pyarrow", compression="snappy", index=False)
        pq_size_mb = os.path.getsize(parquet_path) / (1024 * 1024)
        compression_ratio = (1.0 - (pq_size_mb / file_size_mb)) * 100.0 if file_size_mb > 0 else 0
        print(f"    [+] Converted in {time.time()-t0:.1f}s: {file_size_mb:.1f} MB -> {pq_size_mb:.1f} MB ({compression_ratio:.1f}% space saved!)")
    except Exception as e:
        print(f"    [-] Error converting to Parquet: {e}")
        return False

    # 2. Upload to Hugging Face
    repo_dest = f"{asset_name}/{date_str}/{os.path.basename(parquet_path)}"
    print(f"    2. Uploading to Hugging Face: {repo_dest}...")
    t1 = time.time()
    for attempt in range(1, 4):
        try:
            api.upload_file(
                path_or_fileobj=parquet_path,
                path_in_repo=repo_dest,
                repo_id=REPO_ID,
                repo_type=REPO_TYPE,
                token=HF_TOKEN,
                commit_message=f"Upload {asset_name} {date_str} ({os.path.basename(parquet_path)})"
            )
            print(f"    [OK] Successfully uploaded in {time.time()-t1:.1f}s!")
            return True
        except Exception as e:
            print(f"    [-] Upload attempt {attempt} failed: {e}")
            time.sleep(3)

    return False

def upload_day_folder(day_str, asset_name="crudeoil"):
    """Uploads all CSVs in a given date folder (e.g. '2026-09-08' or '2026-09-09')."""
    day_folder = os.path.join(RECORDINGS_ROOT, day_str)
    if not os.path.exists(day_folder):
        print(f"[-] Day folder not found: {day_folder}")
        return

    csv_files = glob.glob(os.path.join(day_folder, "*.csv"))
    print(f"\n=======================================================")
    print(f"  UPLOADING {asset_name.upper()} DATA FOR DATE: {day_str}")
    print(f"  Found {len(csv_files)} CSV files in {day_folder}")
    print(f"=======================================================")

    for f in csv_files:
        convert_and_upload_file(f, asset_name=asset_name, date_str=day_str)

def load_data_from_huggingface(asset_name, date_str, file_name):
    """
    Helper function to load Parquet data directly into Pandas from Hugging Face.
    Example usage:
        df = load_data_from_huggingface('crudeoil', '2026-09-08', 'Crude_Options_Ticks_2026-09-08.parquet')
    """
    from huggingface_hub import hf_hub_download
    relative_path = f"{asset_name}/{date_str}/{file_name}"
    print(f"[*] Downloading/Streaming dataset: {relative_path} from {REPO_ID}...")
    local_path = hf_hub_download(
        repo_id=REPO_ID,
        filename=relative_path,
        repo_type=REPO_TYPE,
        token=HF_TOKEN
    )
    return pd.read_parquet(local_path)

if __name__ == "__main__":
    ensure_repository()
    
    # Check if a specific date argument was provided
    if len(sys.argv) > 1:
        target_day = sys.argv[1]
        upload_day_folder(target_day)
    else:
        # By default, upload 2026-09-08 and 2026-09-09
        print("[*] Uploading historical recordings to Hugging Face...")
        upload_day_folder("2026-09-08")
        # For 2026-09-09, we upload the tape & ticks
        upload_day_folder("2026-09-09")
