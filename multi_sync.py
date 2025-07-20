import numpy as np
import pyaudio
import json
import time
from govee_lan import GoveeLan

# === Presets de instrumentos ===
PRESETS = {
    "1": {"nombre": "Kick", "freq": 100, "bw": 60},
    "2": {"nombre": "Snare", "freq": 225, "bw": 75},
    "3": {"nombre": "Voz", "freq": 500, "bw": 250},
    "4": {"nombre": "Teclado", "freq": 2000, "bw": 1000},
    "5": {"nombre": "Hi-hat", "freq": 6000, "bw": 2000},
    "6": "personalizado"
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


def seleccionar_config_por_luz(ips):
    grupos = []
    for ip in ips:
        print(f"\n💡 Configurando luz: {ip}")

        # Selección de instrumento
        print("Selecciona el instrumento a seguir:")
        for key, val in PRESETS.items():
            if key != "6":
                print(
                    f"{key}. {val['nombre']} ({val['freq']} Hz ±{val['bw']} Hz)")
        print("6. Personalizado")
        opcion = input("Opción: ").strip()

        if opcion in PRESETS and opcion != "6":
            freq = PRESETS[opcion]["freq"]
            bw = PRESETS[opcion]["bw"]
            nombre = PRESETS[opcion]["nombre"]
        else:
            freq = float(input("🎯 Frecuencia objetivo (Hz): "))
            bw = float(input("📶 Ancho de banda (Hz): "))
            nombre = "Personalizado"

        # Selección de color
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


def run_multi_sync(grupos):
    RATE = 44100
    CHUNK = 1024
    THRESHOLD = 1e6
    COOLDOWN = 0.25
    last_beat = {g["ip"]: 0 for g in grupos}
    govee = GoveeLan([g["ip"] for g in grupos])

    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16,
                    channels=1,
                    rate=RATE,
                    input=True,
                    frames_per_buffer=CHUNK)

    print("\n🎛 Ejecutando sincronización por grupo. Ctrl+C para detener.\n")
    for g in grupos:
        print(
            f"Luz {g['ip']} → {g['instrumento']} ({g['freq']} Hz ±{g['bw']}) Color: {g['color']}")

    try:
        while True:
            data = np.frombuffer(stream.read(
                CHUNK, exception_on_overflow=False), dtype=np.int16)
            t_now = time.time()

            for g in grupos:
                energia = calcular_energia(data, RATE, g["freq"], g["bw"])
                print(
                    f"[{g['ip']}] Energía: {energia:.2f} | TH: {THRESHOLD:.0f}", end="\r")
                if energia > THRESHOLD and (t_now - last_beat[g["ip"]]) >= COOLDOWN:
                    print(
                        f"\n💥 BEAT detectado en {g['instrumento']} ({g['ip']}) → Enviando color {g['color']}")
                    govee.set_color(*g["color"])
                    last_beat[g["ip"]] = t_now

    except KeyboardInterrupt:
        print("\nApagando luces...")
        govee.set_color(0, 0, 0)
        stream.stop_stream()
        stream.close()
        p.terminate()


if __name__ == "__main__":
    with open("lights.json") as f:
        ips = json.load(f).get("ips", [])

    if not ips:
        print("No se encontraron IPs en lights.json")
    else:
        grupos = seleccionar_config_por_luz(ips)
        run_multi_sync(grupos)
