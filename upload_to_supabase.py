"""
Upload CSV Data ke Supabase Database

Script ini mengmigrasi seluruh file CSV lokal ke database Supabase dengan:
- Batch processing (1000 rows per batch)
- Progress indicator
- Error handling & retry logic
- NaN/Null handling untuk PostgreSQL compatibility

Folder structure:
    data_collected/
    ├── processed_data/{subject}/*.csv  → raw_sensor_data table
    └── summary_data/{subject}/*.csv    → summary_session_data table

Requirements:
    pip install supabase pandas python-dotenv
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Optional, Any
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv

# Import Supabase client
try:
    import supabase
    from supabase import create_client
except ImportError:
    print("[ERROR] supabase package not found. Install with: pip install supabase")
    sys.exit(1)


# ============================================================================
# CONFIGURATION
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_ROOT = PROJECT_ROOT / "data_collected"
PROCESSED_DATA_DIR = DATA_ROOT / "processed_data"
SUMMARY_DATA_DIR = DATA_ROOT / "summary_data"

# Batch configuration
BATCH_SIZE = 1000  # rows per batch
UPLOAD_TIMEOUT_SEC = 30  # timeout per batch insert
RETRY_ATTEMPTS = 3  # retry count untuk failed batches

# Supabase table names
RAW_SENSOR_TABLE = "raw_sensor_data"
SUMMARY_SESSION_TABLE = "summary_session_data"

# Load environment variables
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("[ERROR] SUPABASE_URL dan SUPABASE_KEY tidak ditemukan di environment")
    print("        Tambahkan ke file .env atau set sebagai environment variable")
    sys.exit(1)


# ============================================================================
# SUPABASE CLIENT INITIALIZATION
# ============================================================================

def initialize_supabase_client() -> supabase.client.Client:
    """Initialize dan validate Supabase client connection."""
    try:
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Quick validation: fetch one row untuk check koneksi
        try:
            client.table(RAW_SENSOR_TABLE).select("*", count="exact").limit(1).execute()
        except Exception as e:
            if "Does not exist" in str(e) or "not found" in str(e):
                # Table might not exist, yang penting koneksi OK
                print(f"[WARNING] Table '{RAW_SENSOR_TABLE}' tidak ditemukan - akan dibuat saat first insert")
            else:
                raise e
        
        print("[✓] Supabase client connected successfully")
        return client
    except Exception as e:
        print(f"[ERROR] Gagal menghubungkan ke Supabase: {e}")
        sys.exit(1)


# ============================================================================
# DATA PREPARATION & NaN HANDLING
# ============================================================================

def read_and_clean_csv(csv_file: Path) -> Optional[pd.DataFrame]:
    """
    Baca CSV file dan bersihkan NaN/Null values untuk PostgreSQL compatibility.
    
    Konversi:
    - NaN / None / null → Python None (akan menjadi NULL di PostgreSQL)
    - Tanggal string tetap string (akan diparse di Supabase jika perlu)
    """
    try:
        df = pd.read_csv(csv_file)

        df.columns = df.columns.str.lower()

        # Replace NaN dengan None untuk PostgreSQL compatibility
        df = df.where(pd.notna(df), None)
        
        print(f"    [✓] Read: {csv_file.name} ({len(df)} rows)")
        return df
    except Exception as e:
        print(f"    [ERROR] Gagal membaca {csv_file.name}: {e}")
        return None


def dataframe_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """
    Convert DataFrame ke list of dicts (records) untuk Supabase insert.
    Pastikan tipe data kompatibel dengan JSON.
    """
    records = []
    for _, row in df.iterrows():
        record = {}
        for col, val in row.items():
            # Convert NaN / None / NaT ke Python None
            if pd.isna(val):
                record[col] = None
            # Convert numpy types ke Python native types
            elif hasattr(val, 'item'):  # numpy types
                record[col] = val.item()
            else:
                record[col] = val
        records.append(record)
    
    return records


# ============================================================================
# BATCH UPLOAD LOGIC
# ============================================================================

def upload_batch(
    client: supabase.client.Client,
    table_name: str,
    batch_records: list[dict[str, Any]],
    batch_num: int,
    file_name: str
) -> bool:
    """
    Upload single batch ke Supabase dengan retry logic.
    
    Returns:
        True jika success, False jika gagal semua retry attempts
    """
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            # Insert batch
            response = client.table(table_name).insert(batch_records).execute()
            
            # Sukses
            print(f"        [Batch {batch_num:03d}] ✓ Uploaded {len(batch_records)} rows")
            return True
        
        except Exception as e:
            error_msg = str(e)
            
            if attempt < RETRY_ATTEMPTS:
                wait_time = 2 ** (attempt - 1)  # Exponential backoff: 1s, 2s, 4s
                print(f"        [Batch {batch_num:03d}] ⚠ Error (attempt {attempt}/{RETRY_ATTEMPTS}): {error_msg[:50]}")
                print(f"        [Batch {batch_num:03d}] Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"        [Batch {batch_num:03d}] ✗ FAILED after {RETRY_ATTEMPTS} attempts: {error_msg}")
                return False
    
    return False


def upload_csv_to_supabase(
    client: supabase.client.Client,
    csv_file: Path,
    table_name: str,
    file_type: str  # "raw" atau "summary"
) -> dict[str, int]:
    """
    Upload CSV file ke Supabase dalam batches.
    
    Returns:
        dict with keys: total_rows, uploaded_rows, failed_rows, batches_processed
    """
    stats = {
        "total_rows": 0,
        "uploaded_rows": 0,
        "failed_rows": 0,
        "batches_processed": 0,
    }
    
    # Baca dan bersihkan data
    df = read_and_clean_csv(csv_file)
    if df is None or df.empty:
        print(f"    [WARNING] File kosong atau gagal dibaca: {csv_file.name}")
        return stats

    if 'subject_name' not in df.columns:
        df['subject_name'] = csv_file.parent.name
        
    stats["total_rows"] = len(df)
    records = dataframe_to_records(df)
    
    stats["total_rows"] = len(df)
    records = dataframe_to_records(df)
    
    # Upload dalam batches
    total_batches = (len(records) + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"    Uploading {len(records)} rows in {total_batches} batch(es)...")
    
    for batch_num in range(total_batches):
        start_idx = batch_num * BATCH_SIZE
        end_idx = min((batch_num + 1) * BATCH_SIZE, len(records))
        batch_records = records[start_idx:end_idx]
        
        # Upload batch dengan retry
        success = upload_batch(
            client, table_name, batch_records, 
            batch_num + 1, csv_file.name
        )
        
        if success:
            stats["uploaded_rows"] += len(batch_records)
            stats["batches_processed"] += 1
        else:
            stats["failed_rows"] += len(batch_records)
    
    return stats

# ============================================================================
# FILE DISCOVERY & SCANNING
# ============================================================================

def discover_csv_files(
    data_dir: Path,
    file_type: str  # "raw" atau "summary"
) -> dict[str, list[Path]]:
    """
    Discover semua CSV files di folder dengan struktur {subject}/*.csv
    
    Returns:
        dict dengan key=subject_name, value=list of CSV file paths
    """
    files_by_subject = {}
    
    if not data_dir.is_dir():
        print(f"[WARNING] Directory tidak ditemukan: {data_dir}")
        return files_by_subject
    
    # Scan setiap subject folder
    for subject_dir in sorted(data_dir.iterdir()):
        if not subject_dir.is_dir():
            continue
        
        subject_name = subject_dir.name
        csv_files = sorted(subject_dir.glob("*.csv"))
        
        if csv_files:
            files_by_subject[subject_name] = csv_files
            print(f"  Found {len(csv_files)} CSV files in '{subject_name}' ({file_type})")
    
    return files_by_subject


# ============================================================================
# MAIN UPLOAD ORCHESTRATION
# ============================================================================

def upload_processed_data(client: supabase.client.Client) -> dict[str, Any]:
    """Upload semua raw sensor data dari processed_data folder."""
    print("\n" + "=" * 80)
    print(" UPLOADING RAW SENSOR DATA")
    print("=" * 80)
    
    all_stats = {
        "total_files": 0,
        "successful_files": 0,
        "failed_files": 0,
        "total_rows": 0,
        "uploaded_rows": 0,
        "failed_rows": 0,
    }
    
    files_by_subject = discover_csv_files(PROCESSED_DATA_DIR, "raw")
    
    if not files_by_subject:
        print("[WARNING] Tidak ada file CSV ditemukan di processed_data")
        return all_stats
    
    for subject_name, csv_files in files_by_subject.items():
        print(f"\n[Subject: {subject_name}]")
        
        for csv_file in csv_files:
            print(f"  File: {csv_file.name}")
            
            stats = upload_csv_to_supabase(
                client, csv_file, RAW_SENSOR_TABLE, "raw"
            )
            
            all_stats["total_files"] += 1
            all_stats["total_rows"] += stats["total_rows"]
            all_stats["uploaded_rows"] += stats["uploaded_rows"]
            all_stats["failed_rows"] += stats["failed_rows"]
            
            if stats["failed_rows"] == 0 and stats["uploaded_rows"] > 0:
                all_stats["successful_files"] += 1
                print(f"    [COMPLETE] {stats['uploaded_rows']} rows uploaded")
            else:
                all_stats["failed_files"] += 1
                print(f"    [PARTIAL] {stats['uploaded_rows']} uploaded, {stats['failed_rows']} failed")
    
    return all_stats


def upload_summary_data(client: supabase.client.Client) -> dict[str, Any]:
    """Upload semua summary data dari summary_data folder."""
    print("\n" + "=" * 80)
    print(" UPLOADING SUMMARY SESSION DATA")
    print("=" * 80)
    
    all_stats = {
        "total_files": 0,
        "successful_files": 0,
        "failed_files": 0,
        "total_rows": 0,
        "uploaded_rows": 0,
        "failed_rows": 0,
    }
    
    files_by_subject = discover_csv_files(SUMMARY_DATA_DIR, "summary")
    
    if not files_by_subject:
        print("[WARNING] Tidak ada file CSV ditemukan di summary_data")
        return all_stats
    
    for subject_name, csv_files in files_by_subject.items():
        print(f"\n[Subject: {subject_name}]")
        
        for csv_file in csv_files:
            print(f"  File: {csv_file.name}")
            
            stats = upload_csv_to_supabase(
                client, csv_file, SUMMARY_SESSION_TABLE, "summary"
            )
            
            all_stats["total_files"] += 1
            all_stats["total_rows"] += stats["total_rows"]
            all_stats["uploaded_rows"] += stats["uploaded_rows"]
            all_stats["failed_rows"] += stats["failed_rows"]
            
            if stats["failed_rows"] == 0 and stats["uploaded_rows"] > 0:
                all_stats["successful_files"] += 1
                print(f"    [COMPLETE] {stats['uploaded_rows']} rows uploaded")
            else:
                all_stats["failed_files"] += 1
                print(f"    [PARTIAL] {stats['uploaded_rows']} uploaded, {stats['failed_rows']} failed")
    
    return all_stats


def print_upload_summary(
    raw_stats: dict[str, Any],
    summary_stats: dict[str, Any]
) -> None:
    """Print ringkasan hasil upload."""
    print("\n" + "=" * 80)
    print(" UPLOAD SUMMARY REPORT")
    print("=" * 80)
    
    # Raw Data Summary
    print("\n[RAW SENSOR DATA]")
    print(f"  Total Files: {raw_stats['total_files']}")
    print(f"  Successful: {raw_stats['successful_files']} | Failed: {raw_stats['failed_files']}")
    print(f"  Total Rows: {raw_stats['total_rows']}")
    print(f"  Uploaded: {raw_stats['uploaded_rows']} | Failed: {raw_stats['failed_rows']}")
    
    # Summary Data Summary
    print("\n[SUMMARY SESSION DATA]")
    print(f"  Total Files: {summary_stats['total_files']}")
    print(f"  Successful: {summary_stats['successful_files']} | Failed: {summary_stats['failed_files']}")
    print(f"  Total Rows: {summary_stats['total_rows']}")
    print(f"  Uploaded: {summary_stats['uploaded_rows']} | Failed: {summary_stats['failed_rows']}")
    
    # Grand Total
    total_files = raw_stats["total_files"] + summary_stats["total_files"]
    total_rows = raw_stats["total_rows"] + summary_stats["total_rows"]
    uploaded_rows = raw_stats["uploaded_rows"] + summary_stats["uploaded_rows"]
    failed_rows = raw_stats["failed_rows"] + summary_stats["failed_rows"]
    
    print("\n[GRAND TOTAL]")
    print(f"  Total Files: {total_files}")
    print(f"  Total Rows: {total_rows}")
    print(f"  Successfully Uploaded: {uploaded_rows} rows ({100*uploaded_rows/max(total_rows,1):.1f}%)")
    print(f"  Failed: {failed_rows} rows ({100*failed_rows/max(total_rows,1):.1f}%)")
    
    if failed_rows == 0 and total_rows > 0:
        print("\n[✓] UPLOAD SUCCESSFUL - All data migrated!")
    elif uploaded_rows > 0:
        print("\n[⚠] UPLOAD PARTIAL - Some data failed, review logs above")
    else:
        print("\n[✗] UPLOAD FAILED - No data uploaded")


def main() -> int:
    """Main entry point."""
    print("=" * 80)
    print(" SUPABASE DATA MIGRATION - CSV UPLOAD")
    print("=" * 80)
    print(f"\nConfiguration:")
    print(f"  Supabase URL: {SUPABASE_URL[:50]}...")
    print(f"  Batch Size: {BATCH_SIZE} rows")
    print(f"  Retry Attempts: {RETRY_ATTEMPTS}")
    print(f"  Data Directories:")
    print(f"    - Processed: {PROCESSED_DATA_DIR}")
    print(f"    - Summary: {SUMMARY_DATA_DIR}")
    
    # Initialize Supabase
    client = initialize_supabase_client()
    
    # Upload data
    start_time = time.time()
    
    raw_stats = upload_processed_data(client)
    summary_stats = upload_summary_data(client)
    
    elapsed_time = time.time() - start_time
    
    # Print summary
    print_upload_summary(raw_stats, summary_stats)
    
    print(f"\n[INFO] Total execution time: {elapsed_time:.1f} seconds")
    print("=" * 80)
    
    # Determine exit code
    failed_rows = raw_stats["failed_rows"] + summary_stats["failed_rows"]
    if failed_rows == 0 and (raw_stats["uploaded_rows"] + summary_stats["uploaded_rows"]) > 0:
        print("[✓] Migration completed successfully!")
        return 0
    else:
        print("[✗] Migration completed with errors")
        return 1


if __name__ == "__main__":
    sys.exit(main())
