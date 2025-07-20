import numpy as np
import pyaudio
import json
import time
import threading
from collections import deque
import socket

# === Presets de instrumentos ===
PRESETS = {
    "1": {"nombre": "Kick (Bombo)", "freq": 90, "bw": 30},
    "2": {"nombre": "Snare (Caja)", "freq": 180, "bw": 50},
    "3": {"nombre": "Voz baja (Masculina)", "freq": 200, "bw": 100},
    "4": {"nombre": "Voz media (Conversación)", "freq": 400, "bw": 200},
    "5": {"nombre": "Voz alta (Femenina)", "freq": 700, "bw": 250},
    "6": {"nombre": "Melodía baja (Bajo eléctrico, pads)", "freq": 500, "bw": 300},
    "7": {"nombre": "Melodía media (Piano, sintetizador)", "freq": 1200, "bw": 500},
    "8": {"nombre": "Melodía aguda (violines, leads)", "freq": 3000, "bw": 800},
    "9": {"nombre": "Hi-hat / Agudos", "freq": 7500, "bw": 1500},
    "10": "personalizado"
}

# === Colores disponibles ===
COLOR_PRESETS = {
    "rojo": (255, 0, 0),
    "verde": (0, 255, 0),
    "azul": (0, 0, 255),
    "blanco": (255, 255, 255),
    "amarillo": (255, 255, 0),
    "purpura": (128, 0, 128),
    "cyan": (0, 255, 255)
}


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
    message = json.dumps(command).encode("utf-8")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(message, (ip, 4003))
    sock.close()


def seleccionar_config_por_luz(ips):
    grupos = []
    for ip in ips:
        print(f"\n💡 Configurando luz: {ip}")

        print("Selecciona el instrumento a seguir:")
        for key, val in PRESETS.items():
            if key != "10":
                print(
                    f"{key}. {val['nombre']} ({val['freq']} Hz ±{val['bw']} Hz)")
        print("10. Personalizado")
        opcion = input("Opción: ").strip()

        if opcion in PRESETS and opcion != "10":
            freq = PRESETS[opcion]["freq"]
            bw = PRESETS[opcion]["bw"]
            nombre = PRESETS[opcion]["nombre"]
        else:
            freq = float(input("🎯 Frecuencia objetivo (Hz): "))
            bw = float(input("📶 Ancho de banda (Hz): "))
            nombre = "Personalizado"

        print("Colores disponibles:")
        for cname in COLOR_PRESETS:
            print(f"- {cname}")
        color_nombre = input("Color para esta luz: ").strip().lower()
        color = COLOR_PRESETS.get(color_nombre, (255, 255, 255))

        grupos.append({
            "ip": ip,
            "instrumento": nombre,
            "freq": freq,
            "bw": bw,
            "color": color
        })
    return grupos


def calcular_energia(data, rate, freq, bw):
    data = data - np.mean(data)
    fft = np.fft.fft(data)
    freqs = np.fft.fftfreq(len(fft), 1.0 / rate)
    magnitude = np.abs(fft)
    indices = np.where((freqs >= freq - bw) & (freqs <= freq + bw))[0]
    return np.mean(magnitude[indices]) if len(indices) > 0 else 0


def procesar_luz(grupo, config, stream, energy_buffer, bpm_tracker):
    RATE = 44100
    CHUNK = 1024
    THRESHOLD = config.get("threshold", 50000)
    FLASH_DURATION = config.get("flash_duration", 0.05)
    COOLDOWN_BASE = config.get("cooldown", 0.25)
    ip = grupo["ip"]
    freq = grupo["freq"]
    bw = grupo["bw"]
    color = grupo["color"]

    last_beat = 0
    apagado_programado = 0
    last_pulse = deque(maxlen=10)

    while True:
        data = np.frombuffer(stream.read(
            CHUNK, exception_on_overflow=False), dtype=np.int16)
        t_now = time.time()

        energia = calcular_energia(data, RATE, freq, bw)
        energy_buffer.append(energia)
        avg_energy = sum(energy_buffer) / len(energy_buffer)

        if last_pulse and (t_now - last_pulse[-1]) > 1.5:
            last_pulse.clear()
        if len(last_pulse) >= 2:
            intervals = [t - s for s,
                         t in zip(last_pulse, list(last_pulse)[1:])]
            avg_interval = sum(intervals) / len(intervals)
            bpm = 60 / avg_interval if avg_interval > 0 else 120
        else:
            bpm = 120
        bpm_tracker["cooldown"] = max(60 / bpm, FLASH_DURATION * 1.2)

        if energia > avg_energy * 1.7 and (t_now - last_beat) >= bpm_tracker["cooldown"]:
            send_color(ip, *color)
            last_beat = t_now
            apagado_programado = t_now + FLASH_DURATION
            last_pulse.append(t_now)

        if apagado_programado and time.time() >= apagado_programado:
            send_color(ip, 0, 0, 0)
            apagado_programado = 0


def run_multi_sync(grupos):
    with open("config.json") as f:
        config = json.load(f)

    device_index = config.get("device_index", 0)
    RATE = 44100
    CHUNK = 1024

    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16,
                    channels=1,
                    rate=RATE,
                    input=True,
                    input_device_index=device_index,
                    frames_per_buffer=CHUNK)

    energy_buffer = deque(maxlen=30)
    bpm_tracker = {"cooldown": config.get("cooldown", 0.25)}

    threads = []
    for grupo in grupos:
        hilo = threading.Thread(target=procesar_luz, args=(
            grupo, config, stream, energy_buffer, bpm_tracker))
        hilo.daemon = True
        hilo.start()
        threads.append(hilo)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        for grupo in grupos:
            send_color(grupo["ip"], 0, 0, 0)
        stream.stop_stream()
        stream.close()
        p.terminate()


if __name__ == "__main__":
    with open("config.json") as f:
        config = json.load(f)
    ips = config.get("ips", [])

    if not ips:
        print("No se encontraron IPs en config.json")
    else:
        grupos = seleccionar_config_por_luz(ips)
        run_multi_sync(grupos)
