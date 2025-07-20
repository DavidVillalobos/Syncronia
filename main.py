import sys
import json
import threading
import time
import socket
import numpy as np
import pyaudio
from collections import deque

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QComboBox,
    QSlider, QPushButton, QColorDialog
)
from PyQt6.QtCore import Qt, QTimer

import pyqtgraph as pg

PRESETS = {
    "Kick (Bombo)": {"freq": 90, "bw": 30},
    "Snare (Caja)": {"freq": 180, "bw": 50},
    "Voz baja (Masculina)": {"freq": 200, "bw": 100},
    "Voz media (Conversación)": {"freq": 400, "bw": 200},
    "Voz alta (Femenina)": {"freq": 700, "bw": 250},
    "Melodía baja": {"freq": 500, "bw": 300},
    "Melodía media": {"freq": 1200, "bw": 500},
    "Melodía aguda": {"freq": 3000, "bw": 800},
    "Hi-hat / Agudos": {"freq": 7500, "bw": 1500}
}

config_path = "live_config.json"


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


def calcular_energia(data, rate, freq, bw):
    data = data - np.mean(data)
    fft = np.fft.fft(data)
    freqs = np.fft.fftfreq(len(fft), 1.0 / rate)
    magnitude = np.abs(fft)
    indices = np.where((freqs >= freq - bw) & (freqs <= freq + bw))[0]
    return np.mean(magnitude[indices]) if len(indices) > 0 else 0


def procesar_luz(ip, stream, control, stop_event):
    RATE = 44100
    CHUNK = 1024
    FLASH_DURATION = 0.05
    last_beat = 0
    apagado_programado = 0

    while not stop_event.is_set():
        try:
            data = np.frombuffer(stream.read(
                CHUNK, exception_on_overflow=False), dtype=np.int16)
        except Exception:
            continue

        t_now = time.time()

        freq = control.freq_slider.value()
        bw = control.bw_slider.value()
        color = control.color
        energia = calcular_energia(data, RATE, freq, bw)

        control.energy_plot.append(energia)
        control.plot_curve.setData(list(control.energy_plot))

        if energia > 50000 and (t_now - last_beat) >= 0.25:
            brightness = control.brightness_slider.value()
            rgb = [int(c * (brightness / 100)) for c in color]
            send_color(ip, *rgb)
            last_beat = t_now
            apagado_programado = t_now + FLASH_DURATION

        if apagado_programado and time.time() >= apagado_programado:
            send_color(ip, 0, 0, 0)
            apagado_programado = 0

    send_color(ip, 0, 0, 0)


class LuzController(QWidget):
    def __init__(self, ip):
        super().__init__()
        self.ip = ip
        self.color = [255, 255, 255]
        self.energy_plot = deque(maxlen=100)

        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"Luz: {ip}"))

        self.preset_selector = QComboBox()
        self.preset_selector.addItems(list(PRESETS.keys()))
        self.preset_selector.currentTextChanged.connect(self.update_sliders)
        layout.addWidget(self.preset_selector)

        self.freq_label = QLabel("Frecuencia (Hz): 0")
        self.freq_slider = QSlider(Qt.Orientation.Horizontal)
        self.freq_slider.setRange(20, 10000)
        self.freq_slider.valueChanged.connect(
            lambda v: self.freq_label.setText(f"Frecuencia (Hz): {v}"))
        layout.addWidget(self.freq_label)
        layout.addWidget(self.freq_slider)

        self.bw_label = QLabel("Ancho de banda (Hz): 0")
        self.bw_slider = QSlider(Qt.Orientation.Horizontal)
        self.bw_slider.setRange(10, 3000)
        self.bw_slider.valueChanged.connect(
            lambda v: self.bw_label.setText(f"Ancho de banda (Hz): {v}"))
        layout.addWidget(self.bw_label)
        layout.addWidget(self.bw_slider)

        self.color_btn = QPushButton("Color")
        self.color_btn.clicked.connect(self.select_color)
        layout.addWidget(self.color_btn)

        self.brightness_label = QLabel("Brillo: 100")
        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(0, 100)
        self.brightness_slider.setValue(100)
        self.brightness_slider.valueChanged.connect(
            lambda v: self.brightness_label.setText(f"Brillo: {v}"))
        layout.addWidget(self.brightness_label)
        layout.addWidget(self.brightness_slider)

        self.plot_widget = pg.PlotWidget()
        self.plot_curve = self.plot_widget.plot(pen="y")
        layout.addWidget(self.plot_widget)

        self.setLayout(layout)
        self.update_sliders(self.preset_selector.currentText())

    def update_sliders(self, preset):
        valores = PRESETS.get(preset)
        if valores:
            self.freq_slider.setValue(valores["freq"])
            self.bw_slider.setValue(valores["bw"])

    def select_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.color = [color.red(), color.green(), color.blue()]


class GoveeApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Controlador de luces Govee")
        self.resize(800, 600)

        self.layout = QVBoxLayout()
        with open("config.json") as f:
            config = json.load(f)
        self.ips = config.get("ips", [])
        self.device_index = config.get("device_index", 0)

        self.controllers = []
        for ip in self.ips:
            ctrl = LuzController(ip)
            self.controllers.append(ctrl)
            self.layout.addWidget(ctrl)

        self.toggle_btn = QPushButton("Iniciar")
        self.toggle_btn.clicked.connect(self.toggle_run)
        self.layout.addWidget(self.toggle_btn)

        self.setLayout(self.layout)
        self.running = False
        self.threads = []
        self.stop_events = []
        self.stream = None
        self.audio = None

        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_graphs)
        self.update_timer.start(100)

    def update_graphs(self):
        for ctrl in self.controllers:
            ctrl.plot_curve.setData(list(ctrl.energy_plot))

    def toggle_run(self):
        if self.running:
            for e in self.stop_events:
                e.set()
            for grupo in self.controllers:
                send_color(grupo.ip, 0, 0, 0)
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
            if self.audio:
                self.audio.terminate()
            self.running = False
            self.threads.clear()
            self.stop_events.clear()
            self.toggle_btn.setText("Iniciar")
        else:
            self.running = True
            self.toggle_btn.setText("Detener")
            self.start_sync()

    def start_sync(self):
        RATE = 44100
        CHUNK = 1024
        self.audio = pyaudio.PyAudio()
        self.stream = self.audio.open(format=pyaudio.paInt16,
                                      channels=1,
                                      rate=RATE,
                                      input=True,
                                      input_device_index=self.device_index,
                                      frames_per_buffer=CHUNK)

        self.stop_events = []
        self.threads = []
        for ctrl in self.controllers:
            stop_event = threading.Event()
            hilo = threading.Thread(target=procesar_luz, args=(
                ctrl.ip, self.stream, ctrl, stop_event))
            hilo.daemon = True
            hilo.start()
            self.threads.append(hilo)
            self.stop_events.append(stop_event)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ventana = GoveeApp()
    ventana.show()
    sys.exit(app.exec())
