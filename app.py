import streamlit as st
from supabase import create_client, Client

st.set_page_config(
    page_title="Smart Mannequin Analytics",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inisialisasi koneksi global
@st.cache_resource
def init_connection() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

try:
    supabase = init_connection()
except Exception as e:
    st.error(f"Gagal terhubung ke Supabase: {e}")
    st.stop()

# Tampilan Beranda
st.title("🤖 Smart Mannequin IoT Analytics Platform")
st.markdown(
    """
    Selamat datang di platform analitik data sensor *smart mannequin* 8-channel.
    Sistem ini terintegrasi langsung dengan database PostgreSQL di Supabase untuk memantau,
    menganalisis sinyal, serta mendiagnosis eksperimen biomekanik secara terpusat.
    """
)

st.markdown("---")
st.subheader("📖 Modul Analitik yang Tersedia")

st.info("""
**1. 📊 Exploratory Data Analysis (EDA)**  
Statistik makro, sebaran durasi/repetisi, dan matriks korelasi linier antar-channel sensor.
""")

st.info("""
**2. 📈 Analisis Sensor & Sinyal**  
Visualisasi *time-series*, filter *smoothing* (Moving Average), anotasi fase *state*, dan inspeksi data mentah.
""")

st.info("""
**3. ⏱️ Diagnostik Jeda Waktu (Time Gap)**  
Deteksi otomatis anomali temporal (selisih *timestamp* janggal) untuk memisahkan jeda istirahat vs kendala transmisi serial.
""")

st.info("""
**4. ⚖️ Komparasi & Evaluasi Sesi**  
Analisis komparasi sisi aktif (kiri vs kanan) serta evaluasi degradasi sinyal (*fatigue tracking*).
""")

st.info("""
**5. 💻 Custom SQL Query**  
Konsol kueri SQL interaktif untuk penelusuran data *ad-hoc* langsung hingga tingkat baris tunggal.
""")

st.sidebar.success("Pilih modul di atas untuk memulai analisis.")