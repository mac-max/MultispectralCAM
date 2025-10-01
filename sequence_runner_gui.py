import sys
import os
import json
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton, QWidget,
    QVBoxLayout, QHBoxLayout, QFileDialog
)
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt, QTimer
import numpy as np
import cv2
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from led_control import LEDController  # dein vorhandenes Tkinter-LED-Fenster

# Optional später nutzbar:
# from sequence_runner import calibrate_channel

class HistogramCanvas(FigureCanvas):
    def __init__(self, parent=None):
        fig = Figure(figsize=(5, 2))
        self.ax = fig.add_subplot(111)
        super().__init__(fig)
        self.setParent(parent)
        self.ax.set_title("Histogramm (RGB)")

    def plot_histogram(self, image):
        self.ax.clear()
        colors = ('r', 'g', 'b')
        for i, color in enumerate(colors):
            hist = cv2.calcHist([image], [i], None, [256], [0, 256])
            self.ax.plot(hist, color=color)
        self.ax.set_xlim([0, 256])
        self.draw()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spektralkamera Steuerung")
        self.resize(1200, 800)

        self.picam2 = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.output_path = "/home/pi/captures"  # Default-Speicherort wie in sequence_runner

        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)

        # Linke Buttonspalte
        button_layout = QVBoxLayout()
        btn_led = QPushButton("LED-Kanäle wählen")
        btn_led.clicked.connect(self.open_led_control)

        btn_preview = QPushButton("Live Vorschau starten")
        btn_preview.clicked.connect(self.toggle_preview)

        btn_capture = QPushButton("Aufnahmesequenz starten")
        btn_capture.clicked.connect(self.run_sequence)

        btn_save = QPushButton("Speicherort wählen")
        btn_save.clicked.connect(self.choose_directory)

        button_layout.addWidget(btn_led)
        button_layout.addWidget(btn_preview)
        button_layout.addWidget(btn_capture)
        button_layout.addWidget(btn_save)
        button_layout.addStretch()

        # Bildanzeige & Histogramm
        right_layout = QVBoxLayout()

        self.image_label = QLabel("Livebild wird hier angezeigt")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: black; color: white")
        right_layout.addWidget(self.image_label, stretch=4)

        self.hist_canvas = HistogramCanvas(self)
        right_layout.addWidget(self.hist_canvas, stretch=1)

        main_layout.addLayout(button_layout, stretch=1)
        main_layout.addLayout(right_layout, stretch=4)

    def open_led_control(self):
        LEDController()  # Öffnet dein bestehendes Tkinter-Fenster

    def toggle_preview(self):
        if self.timer.isActive():
            self.timer.stop()
            if self.picam2:
                self.picam2.stop()
        else:
            from picamera2 import Picamera2  # erst beim Start importieren
            self.picam2 = Picamera2()
            config = self.picam2.create_preview_configuration(main={"size": (640, 480)})
            self.picam2.configure(config)
            self.picam2.set_controls({
                "ExposureTime": 20000,
                "AnalogueGain": 1.0,
                "AwbEnable": False,
                "ColourGains": (1.0, 1.0),
            })
            self.picam2.start()
            self.timer.start(100)

    def update_frame(self):
        if self.picam2:
            frame = self.picam2.capture_array("main")
            self.display_image(frame)
            self.hist_canvas.plot_histogram(frame)

    def display_image(self, frame):
        rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        q_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(q_image)
        self.image_label.setPixmap(pixmap.scaled(
            self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def choose_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Speicherort wählen", self.output_path)
        if dir_path:
            self.output_path = dir_path

    def run_sequence(self):
        # Hier wird später deine calibrate_channel-Logik integriert
        print(f"📸 Aufnahmesequenz wird gestartet. Speichern nach: {self.output_path}")
        # Platzhalter
        pass

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())