import sys
import json
import time
import socket
import numpy as np
import pyaudio
from aubio import tempo

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QComboBox, QPushButton,
    QVBoxLayout, QGridLayout, QHBoxLayout, QSpinBox, QDoubleSpinBox
)
from PyQt6.QtCore import Qt, QTimer

# === Presets e Interfaces ===
PRESETS = {
    "Kick": {"freq": 90, "bw": 30},
    "Snare": {"freq": 180, "bw": 50},
    "Voz": {"freq": 400, "bw": 200},
    "Teclado": {"freq": 2000, "bw": 1000},
    "Hi-Hat": {"freq": 7500, "bw": 1500},
}

COLOR_OPTIONS = {
    "Rojo": (255, 0, 0),
    "Verde": (0, 255, 0),
    "Azul": (0, 0, 255),
}

# === Envío de comandos ===


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

# === Controlador por luz ===


class LuzController(QWidget):
    def __init__(self, light, device_index):
        super().__init__()
        self.ip = light["ip"]
        self.label = f"{light['name']} - {light['model']} - {light['ip']}"
        self.device_index = device_index
        self.color = COLOR_OPTIONS["Rojo"]
        self.last_beat_time = 0
        self.stream = None
        self.tempo_obj = None

        layout = QVBoxLayout()
        layout.addWidget(QLabel(self.label))

        self.preset = QComboBox()
        self.preset.addItems(PRESETS.keys())
        self.preset.currentTextChanged.connect(self.apply_preset)
        layout.addWidget(self.preset)

        self.freq_input = self._spinbox("Freq", layout, 20, 10000, 400)
        self.bw_input = self._spinbox("BW", layout, 10, 2000, 100)
        self.thr_input = self._spinbox(
            "Threshold", layout, 50000, 1000000, 300000)
        self.cooldown_input = self._spinbox(
            "Cooldown (ms)", layout, 10, 5000, 250)
        self.flash_input = self._spinbox("Flash ms", layout, 10, 500, 50)
        self.brightness_input = self._spinbox("Brillo", layout, 1, 100, 100)

        self.color_box = QComboBox()
        self.color_box.addItems(COLOR_OPTIONS.keys())
        self.color_box.currentTextChanged.connect(self.update_color)
        layout.addWidget(self.color_box)

        btns = QHBoxLayout()
        self.btn_start = QPushButton("Encender")
        self.btn_stop = QPushButton("Apagar")
        self.btn_apply = QPushButton("Aplicar cambios")
        btns.addWidget(self.btn_start)
        btns.addWidget(self.btn_stop)
        btns.addWidget(self.btn_apply)
        layout.addLayout(btns)

        self.setLayout(layout)

        self.btn_start.clicked.connect(self.setup_audio)
        self.btn_stop.clicked.connect(self.stop_audio)
        self.btn_apply.clicked.connect(self.apply_changes)

        self.btn_stop.setEnabled(False)
        self.apply_preset(self.preset.currentText())

    def _spinbox(self, name, layout, min_, max_, value):
        hbox = QHBoxLayout()
        label = QLabel(f"{name}:")
        spin = QSpinBox() if isinstance(value, int) else QDoubleSpinBox()
        spin.setRange(min_, max_)
        spin.setValue(value)
        hbox.addWidget(label)
        hbox.addWidget(spin)
        layout.addLayout(hbox)
        return spin

    def update_color(self, name):
        self.color = COLOR_OPTIONS[name]

    def apply_preset(self, name):
        if name in PRESETS:
            preset = PRESETS[name]
            self.freq_input.setValue(preset['freq'])
            self.bw_input.setValue(preset['bw'])

    def get_params(self):
        return {
            "freq": self.freq_input.value(),
            "bw": self.bw_input.value(),
            "threshold": self.thr_input.value(),
            "cooldown": self.cooldown_input.value() / 1000,
            "flash_duration": self.flash_input.value() / 1000,
            "brightness": self.brightness_input.value(),
            "color": self.color,
            "device_index": self.device_index
        }

    def setup_audio(self):
        if self.stream:
            return
        RATE = 44100
        self.HOP_SIZE = 512
        self.RATE = RATE
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(format=pyaudio.paFloat32,
                                  channels=1,
                                  rate=RATE,
                                  input=True,
                                  input_device_index=self.device_index,
                                  frames_per_buffer=self.HOP_SIZE)
        self.tempo_obj = tempo("default", 1024, self.HOP_SIZE, RATE)
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

    def stop_audio(self):
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        if hasattr(self, 'p'):
            self.p.terminate()
        send_color(self.ip, 0, 0, 0)
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def apply_changes(self):
        # Reiniciar audio para aplicar valores nuevos
        was_running = self.stream is not None
        self.stop_audio()
        if was_running:
            self.setup_audio()

    def analyze(self):
        if not self.stream:
            return
        buffer = self.stream.read(self.HOP_SIZE, exception_on_overflow=False)
        samples = np.frombuffer(buffer, dtype=np.float32)
        if self.tempo_obj(samples):
            now = time.time()
            if now - self.last_beat_time >= self.cooldown_input.value() / 1000:
                brightness = self.brightness_input.value() / 100
                rgb = [int(c * brightness) for c in self.color]
                send_color(self.ip, *rgb)
                time.sleep(self.flash_input.value() / 1000)
                send_color(self.ip, 0, 0, 0)
                self.last_beat_time = now

# === App principal ===


class GoveeApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Controlador de Luces Govee")
        self.resize(1000, 600)

        with open("config.json") as f:
            config = json.load(f)

        self.lights = config.get("lights", [])
        self.device_index = config.get("device_index", 0)

        self.controllers = []
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_all)

        self.grid = QGridLayout()
        for i, light in enumerate(self.lights):
            ctrl = LuzController(light, self.device_index)
            self.controllers.append(ctrl)
            row, col = divmod(i, 2)
            self.grid.addWidget(ctrl, row, col)

        layout = QVBoxLayout()
        layout.addLayout(self.grid)
        self.setLayout(layout)

        self.timer.start(30)

    def update_all(self):
        for ctrl in self.controllers:
            ctrl.analyze()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    gui = GoveeApp()
    gui.show()
    sys.exit(app.exec())
