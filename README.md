# Smart Mannequin Sensor Dashboard

Sebuah dasbor analitik interaktif berbasis web untuk mengeksplorasi, memvisualisasikan, dan mengevaluasi data sensor gerak (8-channel flex sensor) dari proyek Smart Mannequin. 

🔴 **Live Demo:** [https://smart-mannequin-skin-dashboard.streamlit.app/](https://smart-mannequin-skin-dashboard.streamlit.app/)

---

## 🛠️ Fitur Utama

Dasbor ini terbagi menjadi beberapa modul analisis utama:

* **Exploratory Data Analysis (EDA):** Ringkasan makro dataset, metrik durasi/repetisi, serta visualisasi audit retensi data mentah vs. data bersih. Termasuk juga matriks korelasi antar-sensor (Pearson).
* **Analisis Sinyal Sensor:** Visualisasi time-series resolusi tinggi untuk pembacaan nilai resistansi dan voltase. Mendukung fitur *Moving Average Smoothing* untuk reduksi noise dan anotasi rentang waktu per fase gerak (RUN, IDLE, REST).
* **Diagnostik Jeda Waktu (Time Gap Analysis):** Deteksi anomali transmisi data serial dari Arduino secara otomatis untuk membedakan fase istirahat normal dengan *delay* atau kendala teknis perangkat keras.
* **Komparasi & Evaluasi Eksperimen:**
  * **Cross-Subject:** Penyelarasan sinyal dan komparasi respons sensor antar-individu pada skenario yang sama.
  * **Bilateral:** Perbandingan performa sisi kiri vs. kanan.
  * **Analisis Fatigue:** Evaluasi degradasi atau penurunan amplitudo sinyal seiring bertambahnya repetisi gerakan.

## 💻 Tech Stack

* **Bahasa:** Python 3
* **Frontend/Framework:** Streamlit
* **Visualisasi:** Plotly Express & Plotly Graph Objects
* **Pemrosesan Data:** Pandas
* **Database:** Supabase (PostgreSQL)

## 📂 Struktur Repositori

```text
SMART_MANNEQUIN_PROJECT/
├── .streamlit/
│   └── secrets.toml             # (Git-ignored) Kredensial Supabase lokal
├── data_collected/
│   └── cleaning_audit_summary.json  # Ringkasan log pembersihan data
├── pages/
│   ├── 1_EDA.py                 # Halaman utama dasbor
│   ├── 2_Analisis_Sensor.py     # Visualisasi time-series & smoothing
│   ├── 3_Time_Gap_Analysis.py   # Diagnostik anomali waktu
│   └── 4_Komparasi_dan_Evaluasi.py # Komparasi antar-subjek & kelelahan
├── upload_to_supabase.py        # Skrip migrasi data CSV ke database
├── data_cleaning.py             # Pipeline pembersihan data mentah
├── requirements.txt             # Dependensi pustaka
└── .gitignore
