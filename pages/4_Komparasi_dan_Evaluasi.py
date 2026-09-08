import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from supabase import create_client, Client

st.set_page_config(page_title="Komparasi & Evaluasi - Smart Mannequin", layout="wide")

VOLTAGE_COLS = [f"s{i}_volt" for i in range(1, 9)]
RESISTANCE_COLS = [f"s{i}" for i in range(1, 9)]
ALL_SENSOR_COLS = VOLTAGE_COLS + RESISTANCE_COLS

@st.cache_resource
def init_connection() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

def _fetch_paginated(table_name: str, filters: dict, start_t: str = None, end_t: str = None, select_cols: str = "*") -> list:
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
    rows = _fetch_paginated("summary_session_data", filters={})
    df = pd.DataFrame(rows)
    if not df.empty:
        labels = []
        for _, row in df.iterrows():
            parts = []
            for col in ["target_duration", "actual_duration_sec", "repetition", "angle"]:
                if col in row: row[col] = pd.to_numeric(row[col], errors="coerce")
            
            if pd.notna(row.get("angle")): parts.append(f"Sudut: {row['angle']:g}°")
            if pd.notna(row.get("target_duration")): parts.append(f"Dur: {row['target_duration']:g}s")
            if pd.notna(row.get("repetition")): parts.append(f"Rep: {row['repetition']:g}x")
            
            scen_id = str(row.get("scenario_id", ""))
            labels.append(f"{scen_id} ({', '.join(parts)})" if parts else scen_id)
        df["scenario_label"] = labels
    return df

@st.cache_data(ttl=300)
def fetch_raw_subset(subject: str, scenario: str, side: str, start_t: str, end_t: str) -> pd.DataFrame:
    filters = {"subject_name": subject, "scenario_id": scenario, "active_side": side}
    # Gunakan ALL_SENSOR_COLS agar tegangan dan resistansi ikut terpanggil
    cols = "timestamp, repetition, state, " + ", ".join(ALL_SENSOR_COLS)
    rows = _fetch_paginated("raw_sensor_data", filters=filters, start_t=start_t, end_t=end_t, select_cols=cols)
    df = pd.DataFrame(rows)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        # Konversi numerik untuk semua kolom sensor
        for col in ALL_SENSOR_COLS + ["repetition"]:
            if col in df.columns: df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.sort_values("timestamp").reset_index(drop=True)
    return df

st.title("Komparasi Sesi & Evaluasi Eksperimen")

df_summary = fetch_summary_data()
if df_summary.empty:
    st.warning("Data ringkasan sesi belum tersedia di database.")
    st.stop()

tab1, tab2, tab3 = st.tabs([
    "👥 Komparasi Antar-Individu (Cross-Subject)",
    "⚖️ Perbandingan Bilateral (Kiri vs Kanan)",
    "📉 Analisis Kelelahan (Fatigue)",
])

# ==============================================================================
# TAB 1: KOMPARASI ANTAR-INDIVIDU
# ==============================================================================
with tab1:
    st.subheader("Perbandingan Respons Sensor Antar-Individu")
    c_scen, c_side, c_sens = st.columns(3)
    
    with c_scen:
        scenarios_all = sorted(df_summary["scenario_label"].dropna().unique().tolist())
        scen_compare = st.selectbox("1. Pilih Skenario:", scenarios_all, key="cross_scen")
    with c_side:
        df_scen_sub = df_summary[df_summary["scenario_label"] == scen_compare]
        sides_all = sorted(df_scen_sub["active_side"].dropna().unique().tolist())
        side_compare = st.selectbox("2. Pilih Sisi Aktif:", sides_all, key="cross_side")
    with c_sens:
        sensor_choice = st.selectbox("3. Pilih Sensor:", ALL_SENSOR_COLS, index=0, key="cross_sens")

    avail_subjects = sorted(df_scen_sub[df_scen_sub["active_side"] == side_compare]["subject_name"].dropna().unique().tolist())
    selected_subjects = st.multiselect("Pilih Subjek yang Ingin Dibandingkan:", avail_subjects, default=avail_subjects)

    if selected_subjects:
        df_cross_summary = df_scen_sub[(df_scen_sub["active_side"] == side_compare) & (df_scen_sub["subject_name"].isin(selected_subjects))]
        st.plotly_chart(px.bar(df_cross_summary, x="subject_name", y="actual_duration_sec", color="subject_name", text_auto=".1f", title=f"Durasi Aktual — {scen_compare} ({side_compare})", template="plotly_white"), use_container_width=True)

        st.markdown(f"#### Penyelarasan Sinyal {sensor_choice.upper()} Antar-Individu")
        fig_cross_signals = go.Figure()
    
        # Buat label dinamis (V atau Ohm)
        unit_label = "V" if "volt" in sensor_choice else "Ohm"
        y_axis_name = "Tegangan (V)" if "volt" in sensor_choice else "Resistansi (Ohm)"
    
        with st.spinner("Memuat dan menyelaraskan data sensor..."):
            for subj in selected_subjects:
                subj_info = df_cross_summary[df_cross_summary["subject_name"] == subj].iloc[0]
                df_raw_s = fetch_raw_subset(subj, subj_info["scenario_id"], side_compare, subj_info["start_time"], subj_info["end_time"])
                if not df_raw_s.empty and sensor_choice in df_raw_s.columns:
                    elapsed_sec = (df_raw_s["timestamp"] - df_raw_s["timestamp"].iloc[0]).dt.total_seconds()
                    # Pasang label dinamis di hovertemplate
                    fig_cross_signals.add_trace(go.Scatter(x=elapsed_sec, y=df_raw_s[sensor_choice], mode="lines", name=subj, hovertemplate=f"Detik %{{x:.1f}}: %{{y:.2f}} {unit_label}"))
    
        # Pasang nama sumbu Y dinamis
        fig_cross_signals.update_layout(title=f"Kurva {sensor_choice.upper()} Skenario {scen_compare}", xaxis_title="Waktu Berjalan (s)", yaxis_title=y_axis_name, hovermode="x unified", template="plotly_white", height=480)
        st.plotly_chart(fig_cross_signals, use_container_width=True)


# ==============================================================================
# TAB 2: BILATERAL
# ==============================================================================
with tab2:
    st.subheader("Perbandingan Sisi Kiri vs Kanan")
    c_s2, c_sc2 = st.columns(2)
    
    with c_s2: 
        subj_tab2 = st.selectbox("Pilih Subjek:", sorted(df_summary["subject_name"].dropna().unique().tolist()), key="t2_s")
    
    df_subj2 = df_summary[df_summary["subject_name"] == subj_tab2]
    
    # Memfilter dataframe agar hanya menyisakan skenario yang mengandung Kiri/Kanan
    df_bilateral_only = df_subj2[df_subj2["active_side"].isin(["Kiri", "Kanan"])]
    bilateral_scenarios = sorted(df_bilateral_only["scenario_label"].dropna().unique().tolist())
    
    with c_sc2:
        # Peringatan jika subjek tidak memiliki data bilateral sama sekali
        if not bilateral_scenarios:
            st.warning("Subjek ini belum memiliki data skenario Kiri/Kanan.")
            scen_tab2 = None
        else:
            scen_tab2 = st.selectbox("Pilih Skenario:", bilateral_scenarios, key="t2_sc")

    # Hanya render grafik jika ada skenario yang terpilih
    if scen_tab2:
        df_sides = df_subj2[df_subj2["scenario_label"] == scen_tab2]
        if not df_sides.empty:
            col_kpi1, col_kpi2 = st.columns(2)
            with col_kpi1: 
                st.plotly_chart(px.bar(df_sides, x="active_side", y="actual_duration_sec", color="active_side", text_auto=".1f", title="Durasi Aktual (detik)", template="plotly_white"), use_container_width=True)
            with col_kpi2: 
                st.plotly_chart(px.bar(df_sides, x="active_side", y="repetition", color="active_side", title="Total Repetisi", template="plotly_white"), use_container_width=True)


# ==============================================================================
# TAB 3: FATIGUE
# ==============================================================================
with tab3:
    st.subheader("Evaluasi Penurunan Amplitudo Antar-Repetisi")
    subj_tab3 = st.selectbox("Pilih Subjek:", sorted(df_summary["subject_name"].dropna().unique().tolist()), key="t3_s")
    df_subj3 = df_summary[df_summary["subject_name"] == subj_tab3]
    scen_tab3 = st.selectbox("Pilih Skenario:", sorted(df_subj3["scenario_label"].dropna().unique().tolist()), key="t3_sc")
    
    df_fatigue_meta = df_subj3[df_subj3["scenario_label"] == scen_tab3]
    side_tab3 = st.selectbox("Pilih Sisi Aktif:", sorted(df_fatigue_meta["active_side"].dropna().unique().tolist()), key="t3_side")

    df_fatigue_side = df_fatigue_meta[df_fatigue_meta["active_side"] == side_tab3]
    
    # Pengaman transisi filter
    if df_fatigue_side.empty:
        st.warning("⏳ Menyesuaikan filter...")
        st.stop()

    selected_f_row = df_fatigue_side.iloc[0]
    df_fatigue_raw = fetch_raw_subset(subj_tab3, selected_f_row["scenario_id"], side_tab3, selected_f_row["start_time"], selected_f_row["end_time"])
    
    if not df_fatigue_raw.empty:
        # 1. Bersihkan teks state dari spasi tak kasat mata & huruf besar/kecil
        if "state" in df_fatigue_raw.columns:
            clean_state = df_fatigue_raw["state"].fillna("").astype(str).str.strip().str.upper()
            is_run = clean_state == "RUN"
            new_rep_starts = is_run & (clean_state.shift(1) != "RUN")
            df_fatigue_raw["auto_rep"] = new_rep_starts.cumsum()
            df_eval = df_fatigue_raw[is_run].copy()
        else:
            df_eval = pd.DataFrame()
        
        # 2. FALLBACK PLAN: Jika pemotongan 'RUN' gagal atau tidak ada fase istirahat
        if df_eval.empty or len(df_eval["auto_rep"].unique()) < 2:
            # Konversi paksa ke tipe data numerik agar bisa dibandingkan
            expected_reps = pd.to_numeric(selected_f_row.get("repetition", 0), errors="coerce")
            
            if pd.notna(expected_reps) and expected_reps >= 2:
                # Potong data mentah secara merata berdasarkan waktu/baris
                df_eval = df_fatigue_raw.copy()
                df_eval["auto_rep"] = pd.cut(df_eval.index, bins=int(expected_reps), labels=False) + 1
            else:
                df_eval = pd.DataFrame() 
        
        # --- MULAI PLOTTING ---
        if not df_eval.empty and len(df_eval["auto_rep"].unique()) >= 2:
            sensor_eval = st.selectbox("Pilih Sensor Evaluasi:", ALL_SENSOR_COLS, index=0, key="s_fatigue")
            df_eval["Repetisi_Label"] = "Repetisi " + df_eval["auto_rep"].astype(str)
            
            st.markdown("#### 1. Visualisasi Sinyal per Repetisi (Fase Aktif)")
            st.caption("Grafik ini memisahkan setiap tarikan gerakan. Jika deteksi state gagal, sistem akan membagi data secara proporsional berdasarkan durasi.")
            
            fig_raw_rep = px.line(
                df_eval, x="timestamp", y=sensor_eval, color="Repetisi_Label",
                title=f"Potongan Sinyal {sensor_eval.upper()} Berdasarkan Fase Gerak",
                template="plotly_white"
            )
            fig_raw_rep.update_traces(line=dict(width=2))
            st.plotly_chart(fig_raw_rep, use_container_width=True)

            rep_stats = df_eval.groupby("auto_rep")[sensor_eval].agg(Rentang_Amplitudo=lambda x: x.max() - x.min()).reset_index()
            rep_stats["Repetisi_Label"] = "Repetisi " + rep_stats["auto_rep"].astype(str)
            
            st.markdown("#### 2. Evaluasi Penurunan Kinerja (Fatigue Trend)")
            st.caption("Grafik ini mengukur rentang amplitudo (Maksimum - Minimum) dari tiap tarikan. Garis menurun menunjukkan pelemahan otot.")
            
            fig_trend = px.line(
                rep_stats, x="Repetisi_Label", y="Rentang_Amplitudo", 
                markers=True, 
                title=f"Tren Rentang Amplitudo {sensor_eval.upper()}", 
                template="plotly_white"
            )
            fig_trend.update_traces(marker=dict(size=10, color="red"), line=dict(dash="dot", color="gray"))
            st.plotly_chart(fig_trend, use_container_width=True)
            
        else:
            st.info("Tidak dapat memisahkan repetisi. Pastikan skenario ini memang memiliki instruksi repetisi > 1.")
    else:
        st.warning("Data mentah sensor tidak ditemukan untuk rentang waktu sesi ini.")
