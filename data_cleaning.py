"""
Bersihkan data mentah 8-channel flex sensor untuk konsumsi dashboard Streamlit.

Input:
    data_collected/sensor_data/{subjek}/{titik}_{subjek}.csv
Output:
    data_collected/processed_data/{subjek}/{titik}_{subjek}_clean.csv

Skema Data (RAW):
    Timestamp, S1-S8 + Volt variants, Subject_Name, Scenario_ID, Angle, 
    Duration_Target, Repetition, Active_Side, State, Kondisi_Khusus
"""

from __future__ import annotations

import re
import sys  
from pathlib import Path
from typing import Dict

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_ROOT = PROJECT_ROOT / "data_collected"

# Skema header data raw sesuai spesifikasi
RAW_HEADER = [
    "Timestamp", "S1", "S1_Volt", "S2", "S2_Volt", "S3", "S3_Volt", 
    "S4", "S4_Volt", "S5", "S5_Volt", "S6", "S6_Volt", "S7", "S7_Volt", 
    "S8", "S8_Volt", "Subject_Name", "Scenario_ID", "Angle", "Duration_Target", 
    "Repetition", "Active_Side", "State", "Kondisi_Khusus"
]

SENSOR_COLUMNS = [
    "S1", "S1_Volt", "S2", "S2_Volt", "S3", "S3_Volt", "S4", "S4_Volt",
    "S5", "S5_Volt", "S6", "S6_Volt", "S7", "S7_Volt", "S8", "S8_Volt",
]

METADATA_COLUMNS = [
    "Subject_Name", "Scenario_ID", "Angle", "Duration_Target", 
    "Repetition", "Active_Side", "State", "Kondisi_Khusus"
]

MIN_RESISTANCE_OHM = 1_000.0
MAX_RESISTANCE_OHM = 90_000.0
MIN_VOLTAGE = 0.0


def safe_component(value: str, fallback: str) -> str:
    """Return a filename-safe component for Windows and Unix-like systems."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value.strip())
    return cleaned or fallback


def get_paths(subject: str, experiment_point: str) -> tuple[Path, Path, Path]:
    """Build source, destination directory, and output-file paths."""
    source_file = (
        DATA_ROOT / "sensor_data" / subject / f"{experiment_point}_{subject}.csv"
    )
    processed_subject_dir = DATA_ROOT / "processed_data" / subject
    output_file = processed_subject_dir / f"{experiment_point}_{subject}_clean.csv"
    return source_file, processed_subject_dir, output_file


def validate_columns(dataframe: pl.DataFrame) -> None:
    required_columns = set(RAW_HEADER)
    missing_columns = required_columns.difference(dataframe.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Kolom wajib tidak ditemukan: {missing}")


def clean_sensor_data(source_file: Path) -> pl.DataFrame:
    """
    Keep only valid RUN rows that contain finite, non-anomalous sensor readings.

    Numeric values are explicitly cast to Float64 so the dashboard receives a
    predictable schema even when the raw CSV was inferred as string columns.
    
    Schema override dipaksa untuk:
    - Sensor columns: Float64
    - Metadata columns: Utf8 (string) untuk mencegah type inference error
    - Timestamp: akan dikonversi ke datetime setelah pembacaan
    """
    # Define schema overrides untuk memastikan tipe data konsisten
    schema_overrides: Dict[str, pl.DataType] = {
        "Timestamp": pl.Utf8,  # Baca sebagai string dulu, konversi nanti
    }
    
    # Force sensor columns ke Float64
    for col in SENSOR_COLUMNS:
        schema_overrides[col] = pl.Float64
    
    # Force metadata columns ke Utf8 (string)
    for col in METADATA_COLUMNS:
        schema_overrides[col] = pl.Utf8
    
    raw_data = pl.read_csv(
        source_file,
        schema_overrides=schema_overrides,
        null_values=["", "null", "NULL", "None", "nan", "NaN"],
        ignore_errors=False,
    )
    validate_columns(raw_data)
    
    # Konversi Timestamp ke datetime Polars secara aman
    raw_data = raw_data.with_columns(
        pl.col("Timestamp")
        .str.to_datetime(format="%Y-%m-%d %H:%M:%S%.f", exact=False, strict=False)
        .alias("Timestamp")
    )

    # Cek finite dan non-null untuk sensor columns
    finite_sensor_rows = [
        pl.col(column).is_not_null() & pl.col(column).is_finite()
        for column in SENSOR_COLUMNS
    ]
    
    # Cek anomali pada sensor readings (range nilai)
    anomaly_free_sensor_rows = []
    for sensor_number in range(1, 9):
        resistance_column = f"S{sensor_number}"
        voltage_column = f"S{sensor_number}_Volt"
        anomaly_free_sensor_rows.extend([
            pl.col(resistance_column).is_between(
                MIN_RESISTANCE_OHM, MAX_RESISTANCE_OHM, closed="both"
            ),
            pl.col(voltage_column) >= MIN_VOLTAGE,
        ])

    return (
        raw_data
        .filter(pl.col("State").str.strip_chars() == "RUN")
        .filter(pl.all_horizontal(finite_sensor_rows))
        .filter(pl.all_horizontal(anomaly_free_sensor_rows))
    )


def main() -> int:
    print("=" * 53)
    print(" DATA CLEANING SENSOR FLEX 8-CHANNEL")
    print("=" * 53)

    subject = safe_component(
        input("Masukkan Nama Subjek (contoh: Rey)         : "),
        "unknown_subject",
    )
    experiment_point = safe_component(
        input("Bagian Titik Eksperimen (contoh: Lutut)   : "),
        "unknown_experiment",
    )

    source_file, processed_subject_dir, output_file = get_paths(
        subject, experiment_point
    )
    if not source_file.is_file():
        print(f"\n[ERROR] File data mentah tidak ditemukan:\n{source_file}")
        return 1

    # Hanya buat folder baru bila direktori subjek belum ada.
    if not processed_subject_dir.is_dir():
        processed_subject_dir.mkdir(parents=True, exist_ok=True)

    try:
        cleaned_data = clean_sensor_data(source_file)
        cleaned_data.write_csv(output_file)
    except (OSError, pl.exceptions.PolarsError, ValueError) as error:
        print(f"\n[ERROR] Gagal membersihkan data: {error}")
        return 1

    print("\n[SUKSES] Data bersih berhasil disimpan.")
    print(f"Baris valid RUN: {cleaned_data.height}")
    print(f"Path output: {output_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
