import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client, Client
from ai_helper import render_sensor_placement, analyze_chart_with_vision

st.set_page_config(
    page_title="Analisis Sensor - Smart Mannequin",
    layout="wide"
)

RESISTANCE_COLS = [f"s{i}" for i in range(1, 9)]
VOLTAGE_COLS = [f"s{i}_volt" for i in range(1, 9)]

@st.cache_resource
def init_connection() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

def _fetch_paginated(table_name: str, filters: dict, start_t: str = None, end_t: str = None, order_col: str = None) -> list:
    page_size = 1000
    start = 0
    all_rows = []

    while True:
        query = supabase.table(table_name).select("*")
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
        labels = []
        for _, row in df.iterrows():
            parts = []
            for col in ["target_duration", "actual_duration_sec", "repetition", "angle"]:
                if col in row:
                    row[col] = pd.to_numeric(row[col], errors="coerce")
                    
            if pd.notna(row.get("angle")):
                parts.append(f"Sudut: {row['angle']:g}°")
            if pd.notna(row.get("target_duration")):
                parts.append(f"Dur: {row['target_duration']:g}s")
            if pd.notna(row.get("repetition")):
                parts.append(f"Rep: {row['repetition']:g}x")
                
            scen_id = str(row.get("scenario_id", ""))
            labels.append(f"{scen_id} ({', '.join(parts)})" if parts else scen_id)
            
        df["scenario_label"] = labels
    return df

@st.cache_data(ttl=300)
def fetch_raw_data(subject: str, scenario: str, side: str, start_t: str, end_t: str) -> pd.DataFrame:
    filters = {"subject_name": subject, "scenario_id": scenario, "active_side": side}
    rows = _fetch_paginated("raw_sensor_data", filters=filters, start_t=start_t, end_t=end_t, order_col="timestamp")
    df = pd.DataFrame(rows)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        for col in RESISTANCE_COLS + VOLTAGE_COLS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.sort_values("timestamp")
    return df

st.title("Analisis Sinyal Sensor 8-Channel")
st.caption("Eksplorasi sinyal fisik time-series, reduksi noise (smoothing), dan pemetaan fase gerak.")

render_sensor_placement()

summary_df = fetch_summary_data()
if summary_df.empty:
    st.warning("Data summary kosong. Tidak dapat memuat opsi filter.")
    st.stop()

# --- SIDEBAR FILTER ---
st.sidebar.header("Filter Eksperimen")
subjects = sorted(summary_df["subject_name"].dropna().unique().tolist())
selected_subject = st.sidebar.selectbox("1. Pilih Subjek", subjects)

df_by_subj = summary_df[summary_df["subject_name"] == selected_subject]
scenarios = df_by_subj["scenario_label"].dropna().unique().tolist()
selected_label = st.sidebar.selectbox("2. Pilih Skenario", scenarios)

df_by_scen = df_by_subj[df_by_subj["scenario_label"] == selected_label]
active_sides = sorted(df_by_scen["active_side"].dropna().unique().tolist())
selected_side = st.sidebar.selectbox("3. Pilih Sisi Aktif", active_sides)

df_filtered_side = df_by_scen[df_by_scen["active_side"] == selected_side]

if df_filtered_side.empty:
    st.warning("⏳ Menyesuaikan filter... Silakan pastikan pilihan Skenario dan Sisi Aktif sesuai.")
    st.stop()

selected_row = df_filtered_side.iloc[0]
real_scenario_id = selected_row["scenario_id"]
start_time_val = selected_row["start_time"]
end_time_val = selected_row["end_time"]

with st.spinner("Mengambil data sensor resolusi tinggi..."):
    raw_df = fetch_raw_data(selected_subject, real_scenario_id, selected_side, start_time_val, end_time_val)

if raw_df.empty:
    st.warning("Data sensor mentah tidak ditemukan untuk sesi ini.")
    st.stop()

# --- KONTROL VISUALISASI ---
st.subheader("Pengaturan Visualisasi")
c1, c2, c3 = st.columns([2, 2, 2])
with c1:
    metric_type = st.radio("Pilih Domain Sinyal:", ["Resistansi (s1–s8)", "Voltase (s1_volt–s8_volt)"], horizontal=True)
with c2:
    apply_smoothing = st.toggle("Aktifkan Smoothing", value=False)
    window_size = st.slider("Ukuran Window:", 3, 51, 9, step=2) if apply_smoothing else 1
with c3:
    show_states = st.toggle("Tampilkan Fase (State Mapping)", value=True)

target_cols = RESISTANCE_COLS if "Resistansi" in metric_type else VOLTAGE_COLS
available_cols = [c for c in target_cols if c in raw_df.columns]

# --- PLOTLY TIME-SERIES ---
fig = go.Figure()
for col in available_cols:
    y_series = raw_df[col].rolling(window=window_size, min_periods=1, center=True).mean() if apply_smoothing else raw_df[col]
    fig.add_trace(go.Scatter(x=raw_df["timestamp"], y=y_series, mode="lines", name=col.upper(), hovertemplate="%{y:.2f}<extra>" + col.upper() + "</extra>"))

if show_states and "state" in raw_df.columns:
    raw_df["state_shift"] = (raw_df["state"] != raw_df["state"].shift()).cumsum()
    state_blocks = raw_df.groupby(["state_shift", "state"]).agg(start_time=("timestamp", "first"), end_time=("timestamp", "last")).reset_index()
    state_colors = {"RUN": "rgba(46, 204, 113, 0.15)", "IDLE": "rgba(241, 196, 15, 0.15)", "REST": "rgba(52, 152, 219, 0.15)", "HOLD": "rgba(155, 89, 182, 0.15)"}
    
    for _, block in state_blocks.iterrows():
        s_name = str(block["state"]).upper()
        fig.add_vrect(
            x0=block["start_time"], x1=block["end_time"], 
            fillcolor=state_colors.get(s_name, "rgba(149, 165, 166, 0.1)"), 
            layer="below", line_width=0, 
            annotation_text=s_name if s_name in ["RUN", "REST", "HOLD"] else "", annotation_position="top left"
        )

fig.update_layout(
    title=f"Time-Series: {selected_subject} | {selected_label} | {selected_side}",
    xaxis_title="Waktu", yaxis_title="Ohm (ADC)" if "Resistansi" in metric_type else "Volt (V)",
    hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    height=550, margin=dict(l=10, r=10, t=60, b=10)
)
fig.update_xaxes(rangeslider_visible=True)
st.plotly_chart(fig, use_container_width=True)

# --- FITUR AI HARDWARE & TIME-SERIES INSIGHT ---
col_ai_s2, _ = st.columns([2, 4])
with col_ai_s2:
    btn_s2_ai = st.button("✨ Minta Penjelasan AI untuk Tim IoT", key="btn_sensor_page_ai")

if btn_s2_ai:
    with st.spinner("🤖 AI sedang menganalisis kurva 8-channel, kestabilan tegangan, dan respons mekanik sensor..."):
        sensor_stats = {}
        for col in available_cols:
            s_series = raw_df[col].dropna()
            if not s_series.empty:
                sensor_stats[col.upper()] = {
                    "min": round(float(s_series.min()), 2),
                    "max": round(float(s_series.max()), 2),
                    "delta (rentang kerja)": round(float(s_series.max() - s_series.min()), 2),
                    "rata-rata": round(float(s_series.mean()), 2),
                    "standar_deviasi": round(float(s_series.std()), 2)
                }

        sensor_payload = {
            "subjek": selected_subject,
            "skenario": selected_label,
            "sisi_aktif": selected_side,
            "domain_sinyal": metric_type,
            "smoothing_aktif": apply_smoothing,
            "ukuran_window": window_size if apply_smoothing else 1,
            "total_sampel_data": len(raw_df),
            "durasi_sesi_detik": round((raw_df["timestamp"].iloc[-1] - raw_df["timestamp"].iloc[0]).total_seconds(), 2) if len(raw_df) > 1 else 0,
            "distribusi_fase": raw_df["state"].value_counts().to_dict() if "state" in raw_df.columns else {},
            "metrik_per_sensor": sensor_stats
        }

        insight_sensor = analyze_chart_with_vision(
            fig=fig,
            chart_title=f"Time-Series Sinyal 8-Channel ({selected_subject} - {selected_label} - {selected_side})",
            stats_context=sensor_payload
        )
        st.info("### 📋 Evaluasi Respons Sinyal & Hardware (AI Vision)")
        st.markdown(insight_sensor)

st.markdown("---")
with st.expander("Inspeksi Cuplikan Data Sensor (Maksimal 500 Baris)"):
    display_cols = ["timestamp"] + available_cols + (["state"] if "state" in raw_df.columns else [])
    st.dataframe(raw_df[display_cols].head(500), use_container_width=True)