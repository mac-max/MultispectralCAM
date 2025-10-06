from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QSlider, QPushButton, QHBoxLayout, QScrollArea
from PyQt5.QtCore import Qt
import board
import busio
import re
from adafruit_pca9685 import PCA9685

class LEDControlWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("LED PWM Steuerung – PCA9685 @ 0x40 & 0x58")
        self.channel_1_names = [
            "644 nm", "3000 K", "455 nm", "510 nm", "610 nm", "597 nm", "434 nm", "pink"
        ]
        self.channel_2_names = [
            "453 nm", "441 nm", "421 nm", "391 nm", "378 nm", "495 nm", "591 nm",
            "630 nm", "655 nm", "863 nm", "968 nm", "pink", "519 nm", "5000 K"
        ]

        self.sliders_1 = []
        self.sliders_2 = []

        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self.pca_1 = PCA9685(i2c, address=0x40)
            self.pca_2 = PCA9685(i2c, address=0x58)
            self.pca_1.frequency = 1600
            self.pca_2.frequency = 1600
        except Exception as e:
            error_label = QLabel(f"[Fehler] I2C init: {e}")
            layout = QVBoxLayout()
            layout.addWidget(error_label)
            self.setLayout(layout)
            return

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)

        layout.addWidget(QLabel("PCA9685 @ 0x40"))
        for ch, name in self.sorted_channels(self.channel_1_names):
            slider, hbox = self.create_slider_row(name, lambda val, ch=ch: self.set_pwm(self.pca_1, ch, val))
            layout.addLayout(hbox)
            self.sliders_1.append(slider)

        layout.addWidget(QLabel("PCA9685 @ 0x58"))
        for ch, name in self.sorted_channels(self.channel_2_names, offset=2):
            slider, hbox = self.create_slider_row(name, lambda val, ch=ch: self.set_pwm(self.pca_2, ch, val))
            layout.addLayout(hbox)
            self.sliders_2.append(slider)

        off_button = QPushButton("Alle Kanäle AUS")
        off_button.clicked.connect(self.all_off)
        layout.addWidget(off_button)

        scroll.setWidget(container)
        main_layout = QVBoxLayout()
        main_layout.addWidget(scroll)
        self.setLayout(main_layout)

    def extract_wavelength(self, label):
        match = re.search(r"(\d+)", label)
        return int(match.group(1)) if match else float("inf")

    def sorted_channels(self, names, offset=0):
        return sorted(
            [(i + offset, name) for i, name in enumerate(names)],
            key=lambda x: self.extract_wavelength(x[1])
        )

    def create_slider_row(self, name, on_change):
        hbox = QHBoxLayout()
        label = QLabel(name)
        label.setFixedWidth(70)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(0)
        slider.valueChanged.connect(on_change)
        hbox.addWidget(label)
        hbox.addWidget(slider)
        return slider, hbox

    def set_pwm(self, pca, channel, percent):
        percent = max(0, min(100, percent))
        value = int((percent / 100) * 0xFFFF)
        pca.channels[channel].duty_cycle = value

    def all_off(self):
        for ch, s in enumerate(self.sliders_1):
            s.setValue(0)
            self.set_pwm(self.pca_1, ch, 0)
        for ch, s in enumerate(self.sliders_2):
            s.setValue(0)
            self.set_pwm(self.pca_2, ch + 2, 0)
