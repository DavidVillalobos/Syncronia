import socket
import json
import time
import numpy as np
import pyaudio
import scipy.signal
import threading

with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

SAMPLE_RATE = 44100
CHUNK = 1024 * 4

last_trigger_time = 0
last_peak_time = 0
fade_thread = None
fade_stop_event = threading.Event()
beat_index = 0
fade_index = 0


def send_color(ip, r, g, b):
    command = {
        "msg": {
            "cmd": "colorwc",
            "data": {
                "color": {"r": r, "g": g, "b": b},
                "colorTemInKelvin": 0
            }
        }
    }
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(json.dumps(command).encode(), (ip, 4003))
    sock.close()


def broadcast_color(r, g, b):
    for light in CONFIG["lights"]:
        send_color(light["ip"], r, g, b)


def efecto_beat():
    global beat_index, fade_thread, fade_stop_event
    fade_stop_event.set()
    if fade_thread and fade_thread.is_alive():
        fade_thread.join()

    color = CONFIG["colors_beat"][beat_index % len(CONFIG["colors_beat"])]
    beat_index += 1
    brightness = CONFIG.get("brightness", 1.0)
    r = int(color[0] * brightness)
    g = int(color[1] * brightness)
    b = int(color[2] * brightness)

    broadcast_color(r, g, b)
    time.sleep(0.05)
    broadcast_color(0, 0, 0)


def efecto_volumen_bajo():
    global fade_index, fade_stop_event
    fade_stop_event.clear()
    color = CONFIG["colors_fade"][fade_index % len(CONFIG["colors_fade"])]
    fade_index += 1
    brightness = CONFIG.get("brightness", 1.0)
    steps = CONFIG.get("fade_steps", 20)
    delay = CONFIG.get("fade_delay", 0.3)
    levels = [i / steps for i in range(steps + 1)] + \
        [i / steps for i in range(steps - 1, -1, -1)]

    for level in levels:
        if fade_stop_event.is_set():
            return
        val_r = int(color[0] * level * brightness)
        val_g = int(color[1] * level * brightness)
        val_b = int(color[2] * level * brightness)
        broadcast_color(val_r, val_g, val_b)
        time.sleep(delay)

    time.sleep(0.5)


p = pyaudio.PyAudio()
stream = p.open(format=pyaudio.paFloat32,
                channels=1,
                rate=SAMPLE_RATE,
                input=True,
                input_device_index=CONFIG["device_index"],
                frames_per_buffer=CHUNK)

print("🎵 Listening from configured device with FFT peak detection...")

try:
    while True:
        data = stream.read(CHUNK, exception_on_overflow=False)
        samples = np.frombuffer(data, dtype=np.float32)

        fft = np.abs(np.fft.rfft(samples))
        freqs = np.fft.rfftfreq(len(samples), d=1.0 / SAMPLE_RATE)

        band = (freqs >= CONFIG["fft_band"]["low_freq"]) & (
            freqs <= CONFIG["fft_band"]["high_freq"])
        amplitude_band = fft[band]

        if len(amplitude_band) >= 11:
            amplitude_smoothed = scipy.signal.savgol_filter(
                amplitude_band, 11, 3)
        else:
            amplitude_smoothed = amplitude_band

        peaks, properties = scipy.signal.find_peaks(
            amplitude_smoothed,
            height=CONFIG["amplitude_threshold"],
            distance=int(CONFIG["min_peak_distance"] * SAMPLE_RATE / CHUNK)
        )

        now = time.time()
        beat_detected = len(peaks) > 0 and (
            now - last_peak_time) > CONFIG["min_peak_distance"]

        print(
            f"Amplitude (bass avg): {np.mean(amplitude_band):.2f}, Peaks: {len(peaks)}")

        if beat_detected:
            print("[BEAT DETECTED] Applying beat effect")
            last_trigger_time = now
            last_peak_time = now
            efecto_beat()
        elif (now - last_trigger_time) > CONFIG["idle_timeout"]:
            print(
                "[IDLE MODE] No beat detected for a while, applying low volume fade effect")
            if not fade_thread or not fade_thread.is_alive():
                fade_thread = threading.Thread(target=efecto_volumen_bajo)
                fade_thread.start()

        time.sleep(0.05)

except KeyboardInterrupt:
    print("🛑 Stopped by user.")
    stream.stop_stream()
    stream.close()
    p.terminate()
