import os
import glob
import pandas as pd
import json

# Menjamin path selalu absolut terhadap letak file script ini
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_COLLECTED_DIR = os.path.join(BASE_DIR, "data_collected")
RAW_DIR = os.path.join(DATA_COLLECTED_DIR, "sensor_data")
CLEAN_DIR = os.path.join(DATA_COLLECTED_DIR, "processed_data")
OUTPUT_JSON = os.path.join(DATA_COLLECTED_DIR, "cleaning_audit_summary.json")

def audit_cleaning():
    print(f"Target RAW_DIR  : {RAW_DIR}")
    print(f"Target CLEAN_DIR: {CLEAN_DIR}")

    if not os.path.exists(RAW_DIR) or not os.path.exists(CLEAN_DIR):
        print("Folder sensor_data atau processed_data tidak ditemukan!")
        return

    # Kumpulkan semua file clean terlebih dahulu ke memori
    clean_files_pool = glob.glob(os.path.join(CLEAN_DIR, "**", "*.csv"), recursive=True)
    print(f"Ditemukan {len(clean_files_pool)} berkas di folder processed_data.")

    # Indeks file clean berdasarkan: (nama_subjek_lower, kata_kunci_skenario_lower)
    clean_index = {}
    for cp in clean_files_pool:
        rel = os.path.relpath(cp, CLEAN_DIR)
        parts = rel.split(os.sep)
        subj = parts[0].lower() if len(parts) > 1 else ""
        fname = os.path.basename(cp).lower()
        clean_index[(subj, fname)] = cp

    raw_files = glob.glob(os.path.join(RAW_DIR, "**", "*.csv"), recursive=True)
    print(f"Ditemukan {len(raw_files)} berkas di folder sensor_data. Memulai audit...")

    records = []
    for raw_path in raw_files:
        rel_path = os.path.relpath(raw_path, RAW_DIR)
        parts = rel_path.split(os.sep)
        subject_name = parts[0] if len(parts) > 1 else "Unknown"
        raw_filename = os.path.basename(raw_path)
        base_raw_name = os.path.splitext(raw_filename)[0].lower()

        # Baca data mentah
        try:
            df_raw = pd.read_csv(raw_path)
            raw_rows = len(df_raw)
            state_col = next((c for c in df_raw.columns if c.lower() == "state"), None)
            idle_rows = int((df_raw[state_col].astype(str).str.upper() == "IDLE").sum()) if state_col else 0
        except Exception as e:
            print(f"Gagal membaca {raw_filename}: {e}")
            continue

        # Pencarian berkas clean yang cocok
        matched_clean_path = None
        subj_lower = subject_name.lower()

        # 1. Coba pencarian langsung
        if (subj_lower, raw_filename.lower()) in clean_index:
            matched_clean_path = clean_index[(subj_lower, raw_filename.lower())]
        else:
            # 2. Coba pencarian berbasis kata kunci (misal: 'lutut' di 'lutut_chika.csv')
            for (c_subj, c_fname), full_path in clean_index.items():
                if c_subj == subj_lower:
                    c_base = os.path.splitext(c_fname)[0]
                    # Cek keterkaitan nama skenario
                    scenarios = ["bahu", "kalibrasi", "lutut", "pinggang", "siku"]
                    for sc in scenarios:
                        if sc in base_raw_name and sc in c_base:
                            matched_clean_path = full_path
                            break
                if matched_clean_path:
                    break

        clean_rows = 0
        if matched_clean_path and os.path.exists(matched_clean_path):
            try:
                df_clean = pd.read_csv(matched_clean_path)
                clean_rows = len(df_clean)
            except Exception:
                clean_rows = 0
        else:
            print(f"[Peringatan] Tidak menemukan pasangan bersih untuk: {subject_name}/{raw_filename}")

        dropped_rows = max(0, raw_rows - clean_rows)
        retention_rate = round((clean_rows / raw_rows * 100), 2) if raw_rows > 0 else 0.0

        records.append({
            "subject_name": subject_name,
            "filename": raw_filename,
            "raw_rows": raw_rows,
            "clean_rows": clean_rows,
            "dropped_rows": dropped_rows,
            "idle_rows": idle_rows,
            "retention_rate_pct": retention_rate
        })

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

    print(f"\nAudit selesai! File diperbarui di: {OUTPUT_JSON}")

if __name__ == "__main__":
    audit_cleaning()