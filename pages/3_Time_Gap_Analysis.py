import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from supabase import create_client, Client

st.set_page_config(
    page_title="Time Gap Analysis - Smart Mannequin",
    layout="wide"
)

@st.cache_resource
def init_connection() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

def _fetch_paginated(table_name: str, filters: dict, start_t: str = None, end_t: str = None, select_cols: str = "*", order_col: str = None) -> list:
    page_size = 1000
    start = 0
    all_rows = []

    while True:
        query = supabase.table(table_name).select(select_cols)
        for col, val in filters.items():
            if val is not None:
                query = query.eq(col, val)
                
        if start_t and end_t:
            query = query.gte("timestamp", start_t).lte("timestamp", end_t)
            
        if order_col:
            query = query.order(order_col)
            
        query = query.range(start, start + page_size - 1)
        res = query.execute()
        rows = res.data

        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < page_size:
            break
        start += page_size

    return all_rows

@st.cache_data(ttl=300)
def fetch_summary_data() -> pd.DataFrame:
    rows = _fetch_paginated("summary_session_data", filters={}, order_col="start_time")
    df = pd.DataFrame(rows)
    if not df.empty:
        # Buat pemetaan kategori Bagian Tubuh berdasarkan awalan scenario_id
        def map_body_part(sid):
            if pd.isna(sid): return "Lainnya"
            sid_upper = str(sid).upper()
            if sid_upper.startswith('B'): return "Bahu (Semua B)"
            elif sid_upper.startswith('S'): return "Siku (Semua S)"
            elif sid_upper.startswith('P'): return "Pinggang (Semua P)"
            elif sid_upper.startswith('L'): return "Lutut (Semua L)"
            else: return "Kalibrasi / Lainnya"
            
        df["body_part"] = df["scenario_id"].apply(map_body_part)
    return df

@st.cache_data(ttl=300)
def fetch_raw_timestamps_macro(subject: str, start_t: str, end_t: str) -> pd.DataFrame:
    # Hanya filter by Subject + Time Range agar semua jeda transisi antar-skenario ikut terambil
    filters = {"subject_name": subject}
    rows = _fetch_paginated(
        "raw_sensor_data", 
        filters=filters, 
        start_t=start_t, 
        end_t=end_t, 
        select_cols="id, timestamp, state, scenario_id", 
        order_col="timestamp"
    )
    df = pd.DataFrame(rows)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df

st.title("Diagnostik Jeda Waktu (Time Gap Analysis)")
st.caption("Deteksi otomatis anomali jeda waktu pengiriman data Arduino secara makro per bagian tubuh.")

summary_df = fetch_summary_data()
if summary_df.empty:
    st.warning("Data sesi tidak ditemukan di database.")
    st.stop()

# --- SIDEBAR FILTER ---
st.sidebar.header("Pilih Sesi Uji")
subjects = sorted(summary_df["subject_name"].dropna().unique().tolist())
selected_subject = st.sidebar.selectbox("1. Pilih Subjek", subjects)

df_by_subj = summary_df[summary_df["subject_name"] == selected_subject]
body_parts = sorted(df_by_subj["body_part"].dropna().unique().tolist())
selected_part = st.sidebar.selectbox("2. Pilih Bagian Tubuh", body_parts)

df_filtered_part = df_by_subj[df_by_subj["body_part"] == selected_part]

if df_filtered_part.empty:
    st.warning("⏳ Menyesuaikan filter...")
    st.stop()

# Ambil rentang waktu terluar (Absolute Min & Max) untuk merangkum seluruh skenario di bagian tubuh tersebut
start_time_val = df_filtered_part["start_time"].dropna().min()
end_time_val = df_filtered_part["end_time"].dropna().max()

with st.spinner(f"Menganalisis urutan waktu sensor untuk {selected_part}..."):
    df_time = fetch_raw_timestamps_macro(selected_subject, start_time_val, end_time_val)

if df_time.empty:
    st.warning("Data mentah untuk rentang waktu ini tidak ditemukan.")
    st.stop()

st.subheader("Konfigurasi Ambang Batas Deteksi")
col_cfg1, col_cfg2 = st.columns([2, 2])
with col_cfg1:
    gap_threshold_sec = st.number_input("Batas Minimal Jeda Waktu (Detik):", 0.5, 60.0, 2.0, step=0.5)

df_time["time_diff_sec"] = df_time["timestamp"].diff().dt.total_seconds()
normal_sampling_median = df_time["time_diff_sec"].median()
with col_cfg2:
    st.metric("Median Frekuensi Antar-Sampel Normal", f"{normal_sampling_median:.3f} detik" if pd.notna(normal_sampling_median) else "-")

gap_events = df_time[df_time["time_diff_sec"] >= gap_threshold_sec].copy()

st.markdown("---")
st.subheader("Hasil Temuan Temporal")
m1, m2, m3 = st.columns(3)
total_gaps = len(gap_events)
m1.metric("Total Jeda Terdeteksi", f"{total_gaps} kali")

if total_gaps > 0:
    m2.metric("Jeda Terlama", f"{gap_events['time_diff_sec'].max():.2f} detik")
    m3.metric("Total Akumulasi Waktu Berhenti", f"{gap_events['time_diff_sec'].sum():.1f} detik")
else:
    m2.metric("Jeda Terlama", "0.00 detik")
    m3.metric("Total Akumulasi Waktu Berhenti", "0.0 detik")

st.markdown("#### Grafik Selisih Waktu Antar-Baris (Delta T)")
fig_gap = px.line(
    df_time, x="timestamp", y="time_diff_sec",
    title=f"Delta Waktu Antar-Sampel — {selected_subject} ({selected_part})",
    labels={"timestamp": "Waktu", "time_diff_sec": "Jeda (s)"}, template="plotly_white"
)
fig_gap.add_hline(y=gap_threshold_sec, line_dash="dash", line_color="red", annotation_text=f"Threshold ({gap_threshold_sec}s)")
if total_gaps > 0:
    fig_gap.add_trace(go.Scatter(x=gap_events["timestamp"], y=gap_events["time_diff_sec"], mode="markers", name="Anomali Gap", marker=dict(color="red", size=8, symbol="x")))

fig_gap.update_layout(height=420, hovermode="x unified")
st.plotly_chart(fig_gap, use_container_width=True)

if total_gaps > 0:
    log_records = []
    for idx, row in gap_events.iterrows():
        prev_idx = idx - 1
        start_gap = df_time.loc[prev_idx, "timestamp"] if prev_idx in df_time.index else row["timestamp"]
        diagnosis = "Istirahat Antar-Skenario / Transisi" if str(row.get("state", "UNKNOWN")).upper() in ["IDLE", "REST"] else "Potensi Delay Serial"
        
        log_records.append({
            "Skenario Terdekat": row.get("scenario_id", "Transisi"),
            "Waktu Mulai Berhenti": start_gap, 
            "Waktu Lanjut Kembali": row["timestamp"],
            "Durasi Jeda (s)": round(row["time_diff_sec"], 2), 
            "Status State": row.get("state", "UNKNOWN"), 
            "Indikasi Lapangan": diagnosis
        })
    st.dataframe(pd.DataFrame(log_records), use_container_width=True)
else:
    st.success("Aliran data konsisten. Tidak ditemukan jeda waktu di atas ambang batas yang ditentukan.")
