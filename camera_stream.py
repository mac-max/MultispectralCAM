import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import subprocess
import threading
import cv2
import numpy as np
import tempfile


class CameraStream:
    """
    Liest einen kontinuierlichen Videostream von der Raspberry Pi Kamera
    über libcamera-vid und stellt aktuelle Frames als PIL-Images bereit.
    """

    def __init__(self, width=640, height=480, framerate=15, shutter=None, gain=None, standalone=True):
        self.width = width
        self.height = height
        self.framerate = framerate
        self.shutter = shutter
        self.gain = gain
        self.standalone = standalone

        self.buffer = b""
        self.frame = None
        self.running = False
        self.proc = None
        self.thread = None

        self.start()

        # Nur eigene GUI erzeugen, wenn standalone=True
        if self.standalone:
            self._create_preview_window()

    # -------------------------------------------------
    # Stream-Start und Konfiguration
    # -------------------------------------------------
    def build_command(self):
        """Erstellt den libcamera-vid-Befehlsaufruf."""
        cmd = [
            "libcamera-vid",
            "--nopreview",
            "-t", "0",
            "--width", str(self.width),
            "--height", str(self.height),
            "--framerate", str(self.framerate),
            "--codec", "mjpeg",
            "--inline",
            "-o", "-"
        ]
        if self.shutter:
            cmd += ["--shutter", str(self.shutter)]
        if self.gain:
            cmd += ["--gain", str(self.gain)]
        return cmd

    def start(self):
        """Startet den Streaming-Thread."""
        self.running = True
        try:
            self.proc = subprocess.Popen(
                self.build_command(),
                stdout=subprocess.PIPE,
                bufsize=10**8
            )
        except FileNotFoundError:
            raise RuntimeError("libcamera-vid wurde nicht gefunden. Bitte sicherstellen, dass es installiert ist.")

        self.thread = threading.Thread(target=self._read_stream, daemon=True)
        self.thread.start()

    def stop(self):
        """Stoppt Stream und Prozess."""
        self.running = False
        if self.proc:
            self.proc.terminate()
        if self.thread:
            self.thread.join(timeout=1)

    def reconfigure(self, **kwargs):
        """Ändert Kameraeinstellungen (z. B. Auflösung, Gain, Shutter) und startet Stream neu."""
        self.stop()
        self.width = kwargs.get("width", self.width)
        self.height = kwargs.get("height", self.height)
        self.framerate = kwargs.get("framerate", self.framerate)
        self.shutter = kwargs.get("shutter", self.shutter)
        self.gain = kwargs.get("gain", self.gain)
        self.buffer = b""
        self.frame = None
        self.start()

    def capture_sensor_raw(self, filename="capture.dng", width=None, height=None,
                           shutter=None, gain=None, return_array=False):
        """
        Nimmt ein echtes Sensor-RAW-Bild (Bayer RGGB, 10 Bit) auf.
        Speichert als .dng oder gibt optional das Bayer-Array zurück.
        """
        width = width or self.width
        height = height or self.height
        shutter = shutter or self.shutter
        gain = gain or self.gain

        was_running = self.running
        if was_running:
            self.stop()

        tmpfile = filename if filename.endswith(".dng") else filename + ".dng"

        cmd = [
            "libcamera-still",
            "-n",
            "--width", str(width),
            "--height", str(height),
            "--raw",
            "--immediate",
            "--timeout", "1",
            "-o", tmpfile,
            "--encoding", "dng"
        ]
        if shutter:
            cmd += ["--shutter", str(shutter)]
        if gain:
            cmd += ["--gain", str(gain)]

        print("[CAMERA] RAW-Sensoraufnahme:", " ".join(cmd))
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print("[ERROR] RAW-Aufnahme fehlgeschlagen:", e)

        if was_running:
            self.start()

        # Optional: Bayer-Daten direkt als NumPy-Array laden
        if return_array and os.path.exists(tmpfile):
            try:
                # libcamera DNG → 16-Bit-Bild, lineare 10-Bit-Werte in 16-Bit-Container
                img = Image.open(tmpfile)
                raw = np.array(img)
                return raw  # shape: (1944, 2592), dtype=uint16
            except Exception as e:
                print("[WARN] RAW nicht als Array lesbar:", e)
                return None
        return tmpfile

    # -------------------------------------------------
    # Stream-Thread
    # -------------------------------------------------
    def _read_stream(self):
        """Liest kontinuierlich MJPEG-Daten und dekodiert sie zu PIL-Images."""
        while self.running:
            try:
                data = self.proc.stdout.read(4096)
                if not data:
                    break
                self.buffer += data

                start = self.buffer.find(b'\xff\xd8')
                end = self.buffer.find(b'\xff\xd9')

                if start != -1 and end != -1 and end > start:
                    jpg = self.buffer[start:end + 2]
                    self.buffer = self.buffer[end + 2:]
                    img = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if img is not None:
                        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                        self.frame = Image.fromarray(img)
            except Exception as e:
                print("Fehler im Kamera-Thread:", e)

    # -------------------------------------------------
    # Frame-Zugriff
    # -------------------------------------------------
    def get_frame(self):
        """Gibt das zuletzt empfangene PIL.Image-Frame zurück."""
        return self.frame

    # -------------------------------------------------
    # Eigenes Vorschaufenster (nur im Standalone-Modus)
    # -------------------------------------------------
    def _create_preview_window(self):
        root = tk.Tk()
        root.title("Kamera-Vorschau")
        label = ttk.Label(root)
        label.pack(padx=10, pady=10)

        def update():
            frame = self.get_frame()
            if frame:
                imgtk = ImageTk.PhotoImage(image=frame)
                label.imgtk = imgtk
                label.configure(image=imgtk)
            root.after(50, update)

        ttk.Button(root, text="Beenden", command=lambda: (self.stop(), root.destroy())).pack(pady=10)
        update()
        root.mainloop()


# -------------------------------------------------
# Standalone-Test
# -------------------------------------------------
if __name__ == "__main__":
    stream = CameraStream(standalone=True)
