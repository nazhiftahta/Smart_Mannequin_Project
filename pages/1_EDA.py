import os
import json
import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client, Client
from ai_helper import render_sensor_placement, analyze_chart_with_vision

st.set_page_config(
    page_title="EDA - Smart Mannequin",
    layout="wide"
)

# Styling custom untuk kartu metrik agar tidak terpotong
st.markdown("""
    <style>
    [data-testid="stMetricValue"] {
        font-size: 1.75rem !important;
        font-weight: 700;
        white-space: nowrap;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.9rem !important;
        color: #8c8c8c;
    }
    .metric-container {
        border-radius: 8px;
        padding: 8px 12px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        margin-bottom: 8px;
    }
    </style>
""", unsafe_allow_html=True)

# Inisialisasi Supabase
@st.cache_resource
def init_connection() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

@st.cache_data(ttl=300)
def fetch_summary_data() -> pd.DataFrame:
    res = supabase.table("summary_session_data").select("*").execute()
    df = pd.DataFrame(res.data)
    if not df.empty:
        numeric_cols = ["target_duration", "actual_duration_sec", "repetition", "angle"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

@st.cache_data(ttl=300)
def fetch_raw_sample(subject: str) -> pd.DataFrame:
    res = supabase.table("raw_sensor_data").select(
        "subject_name,s1,s2,s3,s4,s5,s6,s7,s8,s1_volt,s2_volt,s3_volt,s4_volt,s5_volt,s6_volt,s7_volt,s8_volt"
    ).eq("subject_name", subject).limit(10000).execute() 
    
    df = pd.DataFrame(res.data)
    if not df.empty:
        for col in df.columns:
            if col != "subject_name":
                df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

st.title("Exploratory Data Analysis")
st.caption("Eksplorasi statistik agregat, audit kualitas pembersihan data, dan karakteristik korelasi sensor.")

with st.spinner("Memuat data sesi..."):
    df_summary = fetch_summary_data()

if df_summary.empty:
    st.warning("Data ringkasan sesi belum tersedia di database.")
    st.stop()

# =====================================================================
# 1. RINGKASAN MAKRO DATASET
# =====================================================================
st.subheader("1. Ringkasan Makro Dataset")
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("Total Sesi", f"{len(df_summary):,}")
with m2:
    st.metric("Total Subjek", df_summary["subject_name"].nunique() if "subject_name" in df_summary.columns else 0)
with m3:
    st.metric("Rata-rata Durasi", f"{df_summary['actual_duration_sec'].mean():.1f} s")
with m4:
    st.metric("Total Repetisi", f"{int(df_summary['repetition'].sum(skipna=True)):,}")

st.markdown("---")

# =====================================================================
# 2. AUDIT PEMBERSIHAN DATA (RAW VS CLEANED)
# =====================================================================
st.subheader("2. Audit Pembersihan Data")
st.caption("Perbandingan volume rekaman sensor mentah terhadap data bersih yang siap dianalisis.")

AUDIT_FILE = os.path.join("data_collected", "cleaning_audit_summary.json")

if os.path.exists(AUDIT_FILE):
    with open(AUDIT_FILE, "r", encoding="utf-8") as f:
        audit_data = json.load(f)
    
    df_audit = pd.DataFrame(audit_data)
    
    if not df_audit.empty:
        total_raw = int(df_audit["raw_rows"].sum())
        total_clean = int(df_audit["clean_rows"].sum())
        total_dropped = int(df_audit["dropped_rows"].sum())
        total_idle = int(df_audit["idle_rows"].sum())
        overall_retention = (total_clean / total_raw * 100) if total_raw > 0 else 0.0

        col_left, col_right = st.columns(2)

        with col_left:
            with st.container(border=True):
                st.markdown("**Hasil Pipeline Data**")
                sub_c1, sub_c2, sub_c3 = st.columns(3)
                with sub_c1:
                    st.metric("Data Mentah", f"{total_raw:,}")
                with sub_c2:
                    st.metric("Data Bersih", f"{total_clean:,}")
                with sub_c3:
                    st.metric("Retensi Valid", f"{overall_retention:.1f}%")

        with col_right:
            with st.container(border=True):
                st.markdown("**Detail Pemangkasan**")
                sub_d1, sub_d2 = st.columns(2)
                with sub_d1:
                    st.metric("Total Tereliminasi", f"{total_dropped:,}")
                with sub_d2:
                    st.metric("Fase Idle", f"{total_idle:,}")

        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)

        df_sub_audit = df_audit.groupby("subject_name").agg(
            Mentah=("raw_rows", "sum"),
            Bersih=("clean_rows", "sum")
        ).reset_index()

        df_sub_melted = df_sub_audit.melt(
            id_vars=["subject_name"], 
            value_vars=["Mentah", "Bersih"],
            var_name="Kondisi Data", 
            value_name="Jumlah Baris"
        )

        fig_audit = px.bar(
            df_sub_melted,
            x="subject_name",
            y="Jumlah Baris",
            color="Kondisi Data",
            barmode="group",
            title="Perbandingan Volume Data Mentah vs Bersih per Subjek",
            labels={"subject_name": "Subjek", "Jumlah Baris": "Volume Baris"},
            template="plotly_white",
            color_discrete_map={"Mentah": "#5c7cfa", "Bersih": "#20c997"}
        )
        fig_audit.update_layout(
            height=380,
            margin=dict(l=10, r=10, t=40, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_audit, use_container_width=True)

        with st.expander("Lihat Rincian Audit per Berkas"):
            table_display = df_audit.rename(columns={
                "subject_name": "Subjek",
                "filename": "Nama Berkas",
                "raw_rows": "Baris Mentah",
                "clean_rows": "Baris Bersih",
                "dropped_rows": "Tereliminasi",
                "idle_rows": "Baris Idle",
                "retention_rate_pct": "Retensi %"
            })
            st.dataframe(table_display, use_container_width=True)
else:
    st.info("Berkas ringkasan audit belum ditemukan. Jalankan generator audit di terminal.")

st.markdown("---")

# =====================================================================
# 3. DISTRIBUSI STATISTIK
# =====================================================================
st.subheader("3. Distribusi Durasi dan Target Sudut")
col_chart1, col_chart2 = st.columns(2)

with col_chart1:
    fig_dur = px.histogram(
        df_summary,
        x="actual_duration_sec",
        nbins=20,
        color="subject_name" if "subject_name" in df_summary.columns else None,
        title="Distribusi Durasi Aktual Eksperimen (detik)",
        labels={"actual_duration_sec": "Durasi Aktual (s)"},
        template="plotly_white",
    )
    fig_dur.update_layout(height=380)
    st.plotly_chart(fig_dur, use_container_width=True)

with col_chart2:
    if "angle" in df_summary.columns:
        fig_angle = px.box(
            df_summary,
            x="angle",
            y="actual_duration_sec",
            color="subject_name" if "subject_name" in df_summary.columns else None,
            title="Sebaran Durasi Berdasarkan Target Sudut",
            labels={"angle": "Target Sudut (°)", "actual_duration_sec": "Durasi Aktual (s)"},
            template="plotly_white",
        )
        fig_angle.update_layout(height=380)
        st.plotly_chart(fig_angle, use_container_width=True)

st.markdown("---")

# =====================================================================
# 4. MATRIKS KORELASI ANTAR-CHANNEL SENSOR
# =====================================================================
st.subheader("4. Matriks Korelasi Antar-Channel Sensor (8-Channel)")
st.caption("Dihitung dari sampel 10.000 titik data mentah per subjek untuk mendeteksi hubungan linier antar-sensor.")

render_sensor_placement()

if not df_summary.empty and "subject_name" in df_summary.columns:
    list_subjects = sorted(df_summary["subject_name"].dropna().unique().tolist())
    
    col_filter1, col_filter2 = st.columns(2)
    with col_filter1:
        selected_subject = st.selectbox("Pilih Subjek:", list_subjects)
        
    with col_filter2:
        corr_type = st.radio(
            "Pilih domain sensor untuk korelasi:",
            options=["Resistansi (s1–s8)", "Voltase (s1_volt–s8_volt)"],
            horizontal=True,
        )

    with st.spinner(f"Memuat sampel data sensor untuk {selected_subject}..."):
        df_raw_subject = fetch_raw_sample(selected_subject)

    if not df_raw_subject.empty:
        if "Resistansi" in corr_type:
            target_cols = [f"s{i}" for i in range(1, 9)]
        else:
            target_cols = [f"s{i}_volt" for i in range(1, 9)]

        valid_cols = [c for c in target_cols if c in df_raw_subject.columns]
        
        if valid_cols:
            corr_matrix = df_raw_subject[valid_cols].corr()

            fig_corr = px.imshow(
                corr_matrix,
                text_auto=".2f",
                aspect="auto",
                color_continuous_scale="RdBu_r",
                title=f"Heatmap Korelasi Pearson — {corr_type.split(' ')[0]} ({selected_subject})",
                range_color=[-1, 1],
            )
            fig_corr.update_layout(height=480)
            st.plotly_chart(fig_corr, use_container_width=True)

            # --- FITUR AI EVALUASI TATA LETAK SENSOR ---
            col_ai_eda, _ = st.columns([2, 4])
            with col_ai_eda:
                btn_corr_ai = st.button("✨ Minta Penjelasan AI untuk Tim IoT", key="btn_ai_corr")

            if btn_corr_ai:
                with st.spinner("🤖 AI sedang membaca pola korelasi dan mengevaluasi tata letak sensor di mannequin..."):
                    # Ekstrak pasangan sensor penting
                    corr_unstack = corr_matrix.unstack()
                    corr_pairs = corr_unstack[corr_unstack.index.get_level_values(0) != corr_unstack.index.get_level_values(1)]
                    
                    highest_pos = corr_pairs.sort_values(ascending=False).head(6)
                    lowest_or_neg = corr_pairs.sort_values().head(6)

                    # Ambil sampel unik (lewati duplikat A-B dan B-A)
                    top_pos_dict = {f"{k[0].upper()} & {k[1].upper()}": round(float(v), 3) for k, v in highest_pos.items()}[::2]
                    top_neg_dict = {f"{k[0].upper()} & {k[1].upper()}": round(float(v), 3) for k, v in lowest_or_neg.items()}[::2]

                    corr_payload = {
                        "subjek": selected_subject,
                        "domain_sensor": corr_type,
                        "jumlah_sampel_evaluasi": len(df_raw_subject),
                        "pasangan_korelasi_positif_tertinggi": top_pos_dict,
                        "pasangan_korelasi_terendah_atau_negatif": top_neg_dict,
                        "konteks_hardware": "Korelasi > 0.85 menandakan sensor membaca regangan elastis yang identik (potensi redundansi fisik). Korelasi mendekati 0 menandakan sensor mengisolasi derajat kebebasan (DoF) gerak yang berbeda secara mandiri."
                    }

                    insight_corr = analyze_chart_with_vision(
                        fig=fig_corr,
                        chart_title=f"Matriks Korelasi Sensor 8-Channel ({selected_subject} - {corr_type})",
                        stats_context=corr_payload
                    )
                    st.info("### 📋 Evaluasi Penempatan & Redundansi Sensor (AI Vision)")
                    st.markdown(insight_corr)
        else:
            st.warning(f"Data kolom sensor tidak lengkap untuk {selected_subject}.")
    else:
        st.info(f"Data mentah belum tersedia di database untuk {selected_subject}.")
else:
    st.info("Data subjek belum tersedia.")