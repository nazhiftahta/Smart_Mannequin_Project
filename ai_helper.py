import os
import streamlit as st
from google import genai
from google.genai import types

# Lokasi berkas diagram referensi sensor
DIAGRAM_PATH_CANDIDATES = [
    "assets/pemasangan_sensor.jpeg",
    "assets/pemasangan_sensor.jpg",
    "pemasangan_sensor.jpeg",
    "pemasangan_sensor.jpg"
]

def _get_diagram_path() -> str | None:
    for path in DIAGRAM_PATH_CANDIDATES:
        if os.path.exists(path):
            return path
    return None

def render_sensor_placement():
    """
    Menampilkan panduan visual penempatan 8-channel flex sensor
    beserta konfigurasi pin hardware S1-S8 tepat di bawah judul halaman.
    """
    diagram_path = _get_diagram_path()
    
    with st.expander("📍 **Panduan Penempatan Titik Sensor**", expanded=False):
        if diagram_path:
            st.image(
                diagram_path, 
                caption="Diagram Penempatan 8-Channel Flex Sensor pada Subjek & Manekin (Tampak Depan, Belakang, dan Lapisan Elastomer)", 
                use_container_width=True
            )
        else:
            st.warning("Berkas diagram `assets/pemasangan_sensor.jpeg` belum ditemukan. Harap letakkan gambar di dalam folder `assets/`.")
            
        st.markdown("---")
        col_upper, col_lower = st.columns(2)
        
        with col_upper:
            st.markdown("#### 🦾 Kalibrasi, Bahu, & Siku (F, B, E)")
            st.markdown("""
            * **S1** : Bahu Kanan Depan
            * **S2** : Bahu Kanan Belakang
            * **S3** : Bahu Kiri Depan
            * **S4** : Bahu Kiri Belakang
            * **S5** : Bagian Dalam Siku Kanan
            * **S6** : Bagian Luar Siku Kanan
            * **S7** : Bagian Dalam Siku Kiri
            * **S8** : Bagian Luar Siku Kiri
            """)
            
        with col_lower:
            st.markdown("#### 🦵 Pinggang & Lutut (P, K)")
            st.markdown("""
            * **S1** : Pinggang Samping Kanan
            * **S2** : Pinggang Samping Kiri
            * **S3** : Pinggang Belakang (Lumbar) Kanan
            * **S4** : Pinggang Belakang (Lumbar) Kiri
            * **S5** : Lutut Depan Kanan
            * **S6** : Lutut Belakang Kanan
            * **S7** : Lutut Depan Kiri
            * **S8** : Lutut Belakang Kiri
            """)

def analyze_chart_with_vision(fig, chart_title: str, stats_context: dict) -> str:
    """
    Mengirimkan grafik Plotly BESERTA diagram referensi pemasangan sensor (.jpeg)
    ke Gemini 3.6 Flash untuk analisis biomekanika dan perangkat keras yang mendalam.
    """
    api_key = st.secrets.get("GEMINI_API_KEY")
    if not api_key:
        return "⚠️ Konfigurasi API Key belum ditemukan. Mohon atur GEMINI_API_KEY di secrets.toml."

    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    Anda adalah Principal IoT Hardware & Biomechanical Engineer untuk perakitan "Smart Mannequin".

    KONTEKS PENGUJIAN:
    - Judul Visualisasi: "{chart_title}"
    - Ground-Truth Statistik & Konfigurasi Sesi:
    {stats_context}

    REFERENSI DIAGRAM FISIK:
    Terdapat gambar referensi diagram penempatan 8-channel flex sensor pada tubuh manusia dan manekin yang dilampirkan:
    1. Kelompok Bahu, Siku, & Kalibrasi (B, E, F):
       - S1: Bahu Kanan Depan, S2: Bahu Kanan Belakang, S3: Bahu Kiri Depan, S4: Bahu Kiri Belakang
       - S5: Bagian Dalam Siku Kanan, S6: Bagian Luar Siku Kanan, S7: Bagian Dalam Siku Kiri, S8: Bagian Luar Siku Kiri
    2. Kelompok Pinggang & Lutut (P, K):
       - S1: Pinggang Samping Kanan, S2: Pinggang Samping Kiri, S3: Pinggang Belakang Kanan, S4: Pinggang Belakang Kiri
       - S5: Lutut Depan Kanan, S6: Lutut Belakang Kanan, S7: Lutut Depan Kiri, S8: Lutut Belakang Kiri
    3. Lapisan Manekin: Menggunakan busa/elastomer di bawah kulit buatan agar kelengkungan tekukan sensor terdistribusi.

    ---
    TUGAS ANDA:
    Analisis grafik pengujian secara mendalam dengan selalu mengaitkannya ke posisi fisik sensor pada diagram referensi. 
    Jelaskan secara sistematis, komprehensif, dan mudah dimengerti oleh tim hardware/IoT:

    ### 1. 🔍 Evaluasi Bentuk Gelombang & Kualitas Sinyal
    - Baca kurva pada grafik: apakah transisi naik-turun mulus, ada noise frekuensi tinggi (kabel ADC goyang), spike listrik, atau penahanan (hold) sinyal yang stabil?
    - Cek batas tegangan: apakah ada indikasi clipping/saturasi pembagi tegangan (mentok di batas suplai atau ground)?

    ### 2. 🦾 Implikasi Fisik pada Sendi & Kulit Manekin
    - Hubungkan pergerakan channel (misal S1, S2, dst.) ke anatomi tubuh berdasarkan diagram: apakah deformasi sensor merefleksikan peregangan sendi yang nyata?
    - Bahas fenomena repetisi/durasi: jika ada degradasi amplitudo, jelaskan apakah itu murni kelelahan gerak, histeresis polimer sensor flex, atau selip pada lapisan elastomer manekin.

    ### 3. ⚡ Kondisi Rangkaian & Instrumentasi
    - Evaluasi rentang dinamika pembacaan (delta resistansi/voltase) terhadap sensitivitas resistor pembagi tegangan pada rentang sudut tersebut.

    ### 4. 🛠️ Rekomendasi Aplikatif untuk Tim Perakitan Manekin
    - Berikan solusi fisik konkret: posisi rekat sensor, pengikatan kabel, peredaman noise mekanis, atau penyesuaian kalibrasi perangkat lunak sebelum sensor ditanam permanen ke dalam manekin.

    Gunakan Bahasa Indonesia teknis yang runtut, lugas, dan terstruktur.
    """

    contents_payload = []

    # 1. Masukkan Gambar Diagram Pemasangan Sensor (.jpeg/.jpg)
    diagram_path = _get_diagram_path()
    if diagram_path:
        with open(diagram_path, "rb") as f:
            diagram_bytes = f.read()
        contents_payload.append(types.Part.from_bytes(data=diagram_bytes, mime_type="image/jpeg"))

    # 2. Masukkan Gambar Visualisasi Plotly yang Sedang Dianalisis
    try:
        img_bytes = fig.to_image(format="png", width=900, height=450, scale=2)
        contents_payload.append(types.Part.from_bytes(data=img_bytes, mime_type="image/png"))
    except Exception as e:
        prompt += f"\n\n[Catatan Sistem: Grafik pengujian tidak dapat diekspor menjadi gambar ({str(e)}), analisis dilakukan berbasis metrik ground-truth.]"

    # 3. Masukkan Prompt Instruksi
    contents_payload.append(prompt)

    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=contents_payload
        )
        return response.text
    except Exception as err:
        return f"⚠️ Gagal mendapatkan analisis dari AI: {str(err)}"