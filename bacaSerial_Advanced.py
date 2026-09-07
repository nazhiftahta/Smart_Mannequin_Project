import csv
from collections import deque
from datetime import datetime
import math
import os
import re
import sys
import threading
import time

import serial


ARDUINO_PORT = "COM9"  # Ganti sesuai port Arduino
BAUD_RATE = 115200
ANOMALY_WINDOW_SECONDS = 5.0
ANOMALY_LIMIT = 3
FLUSH_INTERVAL_SECONDS = 1.0


def safe_component(value, fallback):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value.strip()) or fallback


print("=" * 53)
print(" SETUP IDENTITAS EKSPERIMEN")
print("=" * 53)
titik_eksperimen = safe_component(
    input("Bagian Titik Eksperimen (contoh: Bahu, Lutut) : "), "unknown_experiment"
)
nama_subjek = safe_component(
    input("Masukkan Nama Subjek    (contoh: Rey)         : "), "unknown_subject"
)

# Pisahkan data sensor dan summary per subjek agar hasil eksperimen terorganisir.
sensor_subject_dir = os.path.join("data_collected", "sensor_data", nama_subjek)
summary_subject_dir = os.path.join("data_collected", "summary_data", nama_subjek)

if not os.path.isdir(sensor_subject_dir):
    os.makedirs(sensor_subject_dir, exist_ok=True)

if not os.path.isdir(summary_subject_dir):
    os.makedirs(summary_subject_dir, exist_ok=True)

nama_file = os.path.join(sensor_subject_dir, f"{titik_eksperimen}_{nama_subjek}.csv")
nama_file_summary = os.path.join(
    summary_subject_dir, f"{titik_eksperimen}_{nama_subjek}_summary.csv"
)

# [MODIFIKASI] Posisi Kondisi_Khusus dipindah SETELAH State
RAW_HEADER = [
    "Timestamp",
    "S1", "S1_Volt", "S2", "S2_Volt", "S3", "S3_Volt", "S4", "S4_Volt",
    "S5", "S5_Volt", "S6", "S6_Volt", "S7", "S7_Volt", "S8", "S8_Volt",
    "Subject_Name", "Scenario_ID", "Angle", "Duration_Target", "Repetition",
    "Active_Side", "State", "Kondisi_Khusus"
]
SUMMARY_HEADER = [
    "Start_Time", "End_Time", "Scenario_ID", "Angle", "Target_Duration",
    "Repetition", "Active_Side", "Actual_Duration_Sec", "Kondisi_Khusus"
]

# Semua variabel berikut hanya dibaca/ditulis ketika state_lock sedang dipegang.
state_lock = threading.RLock()
recording_event = threading.Event()
recording_event.set()
serial_connected_event = threading.Event()

metadata = {
    "scenario": "", "kondisi": "", "angle": "", "duration": "", "repetition": "",
    "side": "", "state": "IDLE",
}
active_log = None
paused_state = None
auto_idle_timer = None
current_session_id = 0


def file_is_empty(path):
    return not os.path.exists(path) or os.path.getsize(path) == 0


def is_valid_duration(value):
    try:
        value = float(value)
        return math.isfinite(value) and value > 0
    except (TypeError, ValueError):
        return False


def parse_duration(value):
    """Return (accepted, duration_text, timer_seconds)."""
    value = value.strip()
    if value in ("", "-"):
        return True, "", None  # Manual mode.
    if not is_valid_duration(value):
        return False, None, None
    return True, value, float(value)


def clear_metadata_locked(state):
    metadata.update({
        "scenario": "", "kondisi": "", "angle": "", "duration": "", "repetition": "",
        "side": "", "state": state,
    })


def cancel_timer_locked():
    global auto_idle_timer
    if auto_idle_timer is not None:
        auto_idle_timer.cancel()
        auto_idle_timer = None


def save_active_summary_locked():
    """Save one continuous RUN segment. Caller must hold state_lock."""
    global active_log
    if active_log is None:
        return

    end_wall = datetime.now()
    actual_seconds = max(0.0, time.monotonic() - active_log["start_monotonic"])
    is_new = file_is_empty(nama_file_summary)
    with open(nama_file_summary, "a", newline="", encoding="utf-8") as summary_file:
        writer = csv.writer(summary_file)
        if is_new:
            writer.writerow(SUMMARY_HEADER)
        # [MODIFIKASI] Kondisi khusus diletakkan setelah durasi aktual
        writer.writerow([
            active_log["start_wall"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            end_wall.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            active_log["scenario"], active_log["angle"], active_log["duration"],
            active_log["repetition"], active_log["side"], f"{actual_seconds:.2f}", active_log["kondisi"]
        ])
        summary_file.flush()
    active_log = None


def force_idle(session_token):
    """Timer lama tidak boleh menutup sesi baru."""
    global current_session_id, auto_idle_timer
    with state_lock:
        if session_token != current_session_id or metadata["state"] != "RUN":
            return
        save_active_summary_locked()
        current_session_id += 1
        auto_idle_timer = None
        clear_metadata_locked("IDLE")
    print("\n\n[AUTO-IDLE] Waktu habis. Status kembali ke IDLE.")
    print(">> Skenario / IDLE / PAUSE / RESUME : ", end="", flush=True)


def start_run_locked(scenario, kondisi, angle, duration_text, repetition, side, timer_seconds):
    """Start a new RUN segment. Caller must hold state_lock."""
    global active_log, auto_idle_timer, current_session_id
    cancel_timer_locked()
    save_active_summary_locked()
    current_session_id += 1
    token = current_session_id

    metadata.update({
        "scenario": scenario if scenario != "-" else "",
        "kondisi": kondisi if kondisi != "-" else "",
        "angle": angle if angle != "-" else "",
        "duration": duration_text,
        "repetition": repetition if repetition != "-" else "",
        "side": side if side != "-" else "",
        "state": "RUN",
    })
    active_log = {
        "start_wall": datetime.now(),
        "start_monotonic": time.monotonic(),
        "scenario": metadata["scenario"],
        "kondisi": metadata["kondisi"],
        "angle": metadata["angle"],
        "duration": metadata["duration"],
        "repetition": metadata["repetition"],
        "side": metadata["side"],
        "timer_seconds": timer_seconds,
    }
    if timer_seconds is not None:
        auto_idle_timer = threading.Timer(timer_seconds, force_idle, args=(token,))
        auto_idle_timer.start()


def start_run(scenario, kondisi, angle, duration_text, repetition, side, timer_seconds):
    with state_lock:
        start_run_locked(scenario, kondisi, angle, duration_text, repetition, side, timer_seconds)
    print(f"\n[STATUS] RUN: {scenario} | Kondisi: {kondisi} | Sudut: {angle} | Repetisi: {repetition}")
    if timer_seconds is None:
        print("[MODE MANUAL] Gunakan IDLE atau PAUSE untuk mengakhiri sesi.")
    else:
        print(f"[TIMER AKTIF] Auto-IDLE dalam {timer_seconds:.1f} detik.")


def pause_run():
    """Pause atomik: timer dibatalkan/invalidate sebelum lock dilepas."""
    global paused_state, current_session_id
    with state_lock:
        if metadata["state"] == "REST" and paused_state is not None:
            print("\n[INFO] Skenario sudah dalam keadaan PAUSE.")
            return
        if metadata["state"] != "RUN" or active_log is None:
            print("\n[INFO] Tidak ada skenario RUN yang dapat dijeda.")
            return

        elapsed = time.monotonic() - active_log["start_monotonic"]
        timer_seconds = active_log["timer_seconds"]
        remaining = None if timer_seconds is None else max(0.0, timer_seconds - elapsed)

        current_session_id += 1
        cancel_timer_locked()
        if remaining is not None and remaining <= 0:
            save_active_summary_locked()
            paused_state = None
            clear_metadata_locked("IDLE")
            print("\n[INFO] Durasi sudah habis; sesi diselesaikan sebagai IDLE.")
            return

        paused_state = {
            "scenario": active_log["scenario"],
            "kondisi": active_log["kondisi"],
            "angle": active_log["angle"],
            "duration": active_log["duration"],
            "repetition": active_log["repetition"],
            "side": active_log["side"],
            "remaining_seconds": remaining,
        }
        scenario_name = active_log["scenario"]
        save_active_summary_locked()
        clear_metadata_locked("REST")

    if remaining is None:
        print(f"\n[PAUSE BERHASIL] Skenario manual {scenario_name} dijeda.")
    else:
        print(f"\n[PAUSE BERHASIL] {scenario_name}; sisa waktu {remaining:.1f} detik.")


def resume_run():
    global paused_state
    with state_lock:
        if paused_state is None or metadata["state"] != "REST":
            print("\n[GAGAL] Tidak ada sesi yang sedang di-PAUSE.")
            return
        saved = paused_state.copy()
        paused_state = None
        start_run_locked(
            saved["scenario"], saved["kondisi"], saved["angle"], saved["duration"],
            saved["repetition"], saved["side"], saved["remaining_seconds"],
        )
    print(f"\n[RESUME] Melanjutkan skenario {saved['scenario']}.")


def enter_idle():
    global paused_state, current_session_id
    with state_lock:
        current_session_id += 1
        paused_state = None
        cancel_timer_locked()
        save_active_summary_locked()
        clear_metadata_locked("IDLE")
    print("\n[STATUS] Mode: IDLE (Sistem standby)")


def hardware_fault_handler(error_message, expected_session_id):
    """
    Hanya membatalkan sesi yang menghasilkan sampel anomali.
    Ini mencegah sampel lama membatalkan skenario baru yang baru dimulai user.
    """
    global current_session_id
    with state_lock:
        if (expected_session_id != current_session_id
                or metadata["state"] != "RUN"):
            return False
        current_session_id += 1
        cancel_timer_locked()
        save_active_summary_locked()
        clear_metadata_locked("HARDWARE_FAULT")

    print(f"\n\n[HARDWARE ALERT] {error_message}")
    print("[HARDWARE ALERT] Skenario dibatalkan. Perbaiki sensor/kabel sebelum mulai ulang.")
    print(">> Skenario / IDLE / PAUSE / RESUME : ", end="", flush=True)
    return True


def metadata_snapshot():
    with state_lock:
        return metadata.copy(), current_session_id


def shutdown_recording(final_state="IDLE"):
    """Idempotent; aman dipanggil dari thread serial maupun main thread."""
    global current_session_id, paused_state
    recording_event.clear()
    with state_lock:
        current_session_id += 1
        cancel_timer_locked()
        save_active_summary_locked()
        paused_state = None
        if metadata["state"] != "HARDWARE_FAULT":
            clear_metadata_locked(final_state)


def parse_sensor_line(line):
    values = [value.strip() for value in line.split(",")]
    if len(values) != 16:
        return None
    try:
        parsed = [float(value) for value in values]
    except ValueError:
        return None
    if not all(math.isfinite(value) for value in parsed):
        return None
    return values, parsed


def read_serial_and_save():
    anomaly_times = deque()
    anomaly_session_id = None
    next_flush_at = time.monotonic() + FLUSH_INTERVAL_SECONDS

    try:
        with serial.Serial(ARDUINO_PORT, BAUD_RATE, timeout=1) as ser:
            print(f"\n--- Terhubung ke Arduino di port {ARDUINO_PORT} ---")
            time.sleep(2)  # Arduino dapat reset ketika port dibuka.
            ser.reset_input_buffer()  # Sengaja membuang data boot/stale.
            serial_connected_event.set()

            is_new = file_is_empty(nama_file)
            with open(nama_file, "a", newline="", encoding="utf-8") as raw_file:
                writer = csv.writer(raw_file)
                if is_new:
                    writer.writerow(RAW_HEADER)
                    raw_file.flush()

                while recording_event.is_set():
                    raw_line = ser.readline()
                    if not raw_line:
                        continue
                    parsed_line = parse_sensor_line(
                        raw_line.decode("utf-8", errors="ignore").strip()
                    )
                    if parsed_line is None:
                        continue  # Baris korup/non-numerik tidak menjadi dataset valid.
                    sensor_data, sensor_values = parsed_line

                    snapshot, session_token = metadata_snapshot()
                    if snapshot["state"] != "RUN":
                        anomaly_times.clear()
                        anomaly_session_id = None
                    else:
                        if anomaly_session_id != session_token:
                            anomaly_times.clear()
                            anomaly_session_id = session_token
                        bad_sensor_info = ""
                        anomalous = False
                        for index in range(8):
                            resistance = sensor_values[index * 2]
                            voltage = sensor_values[index * 2 + 1]
                            if resistance > 90000 or resistance < 1000 or voltage < 0:
                                anomalous = True
                                bad_sensor_info = (
                                    f"S{index + 1} (R: {resistance} Ohm, V: {voltage} V)"
                                )
                                break

                        now = time.monotonic()
                        while anomaly_times and now - anomaly_times[0] > ANOMALY_WINDOW_SECONDS:
                            anomaly_times.popleft()
                        if anomalous:
                            anomaly_times.append(now)
                            if len(anomaly_times) >= ANOMALY_LIMIT:
                                hardware_fault_handler(
                                    f"Sensor {bad_sensor_info} tidak stabil dalam "
                                    f"{ANOMALY_WINDOW_SECONDS:g} detik.",
                                    session_token,
                                )
                                anomaly_times.clear()

                    snapshot, _ = metadata_snapshot()
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    
                    # [MODIFIKASI] Kondisi khusus diletakkan setelah state
                    writer.writerow([timestamp] + sensor_data + [
                        nama_subjek, snapshot["scenario"], snapshot["angle"],
                        snapshot["duration"], snapshot["repetition"],
                        snapshot["side"], snapshot["state"], snapshot["kondisi"]
                    ])
                    if time.monotonic() >= next_flush_at:
                        raw_file.flush()
                        next_flush_at = time.monotonic() + FLUSH_INTERVAL_SECONDS

    except serial.SerialException as error:
        print(f"\n[CRITICAL ERROR] Koneksi serial {ARDUINO_PORT} gagal/terputus: {error}")
    except Exception as error:
        print(f"\n[CRITICAL ERROR] Thread serial berhenti: {error}")
    finally:
        shutdown_recording()


print("\n" + "=" * 53)
print(" PEREKAMAN DIMULAI (Tekan Ctrl+C untuk berhenti)")
print("=" * 53)

t_serial = threading.Thread(target=read_serial_and_save, name="serial-recorder")
t_serial.start()

try:
    while recording_event.is_set() and not serial_connected_event.wait(timeout=0.1):
        pass

    while recording_event.is_set() and serial_connected_event.is_set():
        print("\n" + "-" * 53)
        command = input(">> Skenario / IDLE / PAUSE / RESUME : ").strip().upper()

        if not recording_event.is_set():
            break
        if command == "PAUSE":
            pause_run()
        elif command == "RESUME":
            resume_run()
        elif command == "IDLE":
            enter_idle()
        elif command == "":
            continue
        else:
            parameter_labels = (
                "Sudut (derajat)",
                "Durasi (detik)",
                "Repetisi (jumlah kali)",
                "Sisi Tubuh (Kiri/Kanan/Keduanya)",
                "Kondisi Khusus (- jika tak ada)",
            )
            parameter_values = []
            input_cancelled = False

            for label in parameter_labels:
                value = input(f">> {label:<33}: ").strip()
                if value.upper() == "IDLE":
                    enter_idle()
                    print("[INPUT DIBATALKAN] Kembali ke mode IDLE.")
                    input_cancelled = True
                    break
                parameter_values.append(value)

            if input_cancelled:
                continue

            angle, duration_input, repetition, side, kondisi = parameter_values
            
            # Anti-error jika tidak sengaja ngetik koma di input sudut
            angle = angle.replace(",", ".")

            accepted, duration_text, timer_seconds = parse_duration(duration_input)
            if not accepted:
                print("\n[INPUT TIDAK VALID] Durasi harus angka finite > 0, kosong, atau '-'.")
                continue
            
            start_run(command, kondisi, angle, duration_text, repetition, side, timer_seconds)

except (KeyboardInterrupt, EOFError):
    print("\n\n[PROSES BERHENTI] Mengamankan data dan menutup koneksi...")
finally:
    shutdown_recording()
    t_serial.join(timeout=3)
    if t_serial.is_alive():
        print("[PERINGATAN] Thread serial belum berhenti dalam 3 detik.")
    print(f"Selesai. Data: {nama_file}; ringkasan: {nama_file_summary}")
    sys.exit(0)