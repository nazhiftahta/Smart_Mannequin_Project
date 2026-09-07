import streamlit as st
import pandas as pd
from supabase import create_client, Client

st.set_page_config(
    page_title="Custom SQL Query - Smart Mannequin",
    layout="wide",
)

# Inisialisasi Supabase
@st.cache_resource
def init_connection() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

st.title("Konsol Kueri SQL Mandiri")
st.caption("Eksplorasi data mentah dan ringkasan sesi hingga level baris tunggal secara langsung menggunakan kueri SQL.")

# --- SIDEBAR: CONTOH KUERI ---
st.sidebar.header("Katalog Kueri Siap Pakai")

query_templates = {
    "Pilih Template": "",
    "1. Ambil 10 Baris Pertama Data Mentah": (
        "SELECT id, timestamp, subject_name, scenario_id, active_side, s1_volt, s2_volt\n"
        "FROM raw_sensor_data\n"
        "ORDER BY timestamp ASC\n"
        "LIMIT 10"
    ),
    "2. Cari Baris dengan Tegangan S1 Tertinggi": (
        "SELECT id, timestamp, subject_name, scenario_id, active_side, s1_volt\n"
        "FROM raw_sensor_data\n"
        "WHERE s1_volt IS NOT NULL\n"
        "ORDER BY s1_volt DESC\n"
        "LIMIT 1"
    ),
    "3. Rekap Total Baris per Subjek": (
        "SELECT subject_name, COUNT(*) AS total_records\n"
        "FROM raw_sensor_data\n"
        "GROUP BY subject_name\n"
        "ORDER BY total_records DESC"
    ),
    "4. Sesi dengan Kondisi Khusus": (
        "SELECT subject_name, scenario_id, target_duration, actual_duration_sec, kondisi_khusus\n"
        "FROM summary_session_data\n"
        "WHERE kondisi_khusus IS NOT NULL AND kondisi_khusus != ''"
    ),
}

selected_template = st.sidebar.selectbox("Pilih Contoh Kueri:", list(query_templates.keys()))
default_query = query_templates[selected_template] if selected_template != "Pilih Template" else "SELECT id, timestamp, subject_name, scenario_id, s1_volt FROM raw_sensor_data LIMIT 5"

# --- AREA INPUT KUERI ---
user_query = st.text_area(
    "Masukkan Kueri SQL (Hanya SELECT yang diizinkan):",
    value=default_query,
    height=150,
)

col_exec, col_clear = st.columns([1, 5])
execute_btn = col_exec.button("Eksekusi Kueri", type="primary")

if execute_btn:
    # Membersihkan spasi dan karakter titik koma di akhir kueri
    clean_query = user_query.strip().rstrip(";")

    # Validasi awal di sisi antarmuka
    if not clean_query.lower().startswith("select"):
        st.error("Demi keamanan data, hanya kueri dengan perintah SELECT yang diizinkan.")
    else:
        with st.spinner("Mengeksekusi kueri di Supabase..."):
            try:
                # Panggil stored procedure via RPC dengan query yang sudah dibersihkan dari titik koma
                response = supabase.rpc("run_custom_query", {"query_text": clean_query}).execute()
                raw_result = response.data

                if raw_result and len(raw_result) > 0:
                    df_res = pd.DataFrame(raw_result)
                    st.success(f"Kueri berhasil! Mengembalikan {len(df_res)} baris data.")

                    # Tampilkan tabel data
                    st.dataframe(df_res, use_container_width=True)

                    # Fitur unduh CSV hasil kueri
                    csv_data = df_res.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        label="Unduh Hasil Kueri (CSV)",
                        data=csv_data,
                        file_name="hasil_query_kustom.csv",
                        mime="text/csv",
                    )
                else:
                    st.info("Kueri berhasil dieksekusi, tetapi tidak ada data yang cocok dengan kriteria filter.")
            except Exception as e:
                st.error(f"Terjadi kesalahan saat mengeksekusi kueri:\n`{e}`")

st.markdown("---")

# --- SKEMA REFERENSI KOLOM ---
with st.expander("Lihat Referensi Nama Tabel dan Kolom"):
    c_ref1, c_ref2 = st.columns(2)
    with c_ref1:
        st.markdown(
            """
            **Tabel: `summary_session_data`**
            * `id` (int8)
            * `start_time` (timestamp)
            * `end_time` (timestamp)
            * `scenario_id` (text)
            * `angle` (numeric)
            * `target_duration` (numeric)
            * `repetition` (numeric)
            * `active_side` (text)
            * `actual_duration_sec` (numeric)
            * `kondisi_khusus` (text)
            * `subject_name` (text)
            """
        )
    with c_ref2:
        st.markdown(
            """
            **Tabel: `raw_sensor_data`**
            * `id` (int8)
            * `timestamp` (timestamp)
            * `s1` hingga `s8` (numeric ADC)
            * `s1_volt` hingga `s8_volt` (numeric Tegangan)
            * `subject_name` (text)
            * `scenario_id` (text)
            * `duration_target` (numeric)
            * `repetition` (numeric)
            * `active_side` (text)
            * `state` (text)
            * `kondisi_khusus` (text)
            """
        )