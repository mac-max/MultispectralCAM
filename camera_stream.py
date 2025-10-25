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

        self.preview_paused = False

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
                           shutter=None, gain=None, fmt="dng", return_array=False):
        """
        Nimmt ein Sensor-RAW (OV5647, 10-bit Bayer) auf.
        fmt:
          - "dng" (empfohlen): schreibt echtes RAW-DNG.
          - "npy": schreibt DNG und zusätzlich ein .npy-Array (und/oder gibt es zurück).
          - "jpg"/"png"/"tiff": WARNUNG – das ist demosaiziertes 8/16-bit, kein Sensor-RAW.
        """
        import os
        import subprocess
        from PIL import Image
        import numpy as np

        width = width or self.width
        height = height or self.height
        shutter = shutter or self.shutter
        gain = gain or self.gain
        fmt = (fmt or "dng").lower()

        # Zielpfade & Endungen
        def ensure_ext(path, wanted_ext):
            base, ext = os.path.splitext(path)
            return path if ext.lower() == f".{wanted_ext}" else f"{base}.{wanted_ext}"

        # Stream ggf. pausieren
        was_running = self.running
self.preview_paused = True
        if was_running:
            self.stop()

        try:
            base_cmd = [
                "libcamera-still",
                "-n",
                "--width", str(width),
                "--height", str(height),
                "--immediate",
                "--timeout", "1",
            ]
            if shutter:
                base_cmd += ["--shutter", str(shutter)]
            if gain:
                base_cmd += ["--gain", str(gain)]

            out_path = filename

            if fmt == "dng":
                out_path = ensure_ext(filename, "dng")
                cmd = base_cmd + ["--raw", "--encoding", "dng", "-o", out_path]
            elif fmt == "npy":
                # Wir erzeugen DNG und lesen es in ein Array ein; zusätzlich .npy speichern
                out_path = ensure_ext(filename, "dng")
                cmd = base_cmd + ["--raw", "--encoding", "dng", "-o", out_path]
            elif fmt in ("jpg", "jpeg", "png", "tiff", "bmp"):
                # Kein echtes Sensor-RAW – demosaiziert/tonemapped von libcamera
                out_path = ensure_ext(filename, "jpg" if fmt == "jpeg" else fmt)
                print(f"[WARN] fmt='{fmt}' ist kein Sensor-RAW. Es wird ein demosaiziertes Bild gespeichert.")
                cmd = base_cmd + ["--encoding", ("jpg" if fmt == "jpeg" else fmt), "-o", out_path]
            else:
                print(f"[WARN] Unbekanntes fmt='{fmt}', verwende DNG.")
                fmt = "dng"
                out_path = ensure_ext(filename, "dng")
                cmd = base_cmd + ["--raw", "--encoding", "dng", "-o", out_path]

            print("[CAMERA] RAW-Capture:", " ".join(cmd))
            subprocess.run(cmd, check=True)

            # npy-Export / Rückgabe des Arrays (nur sinnvoll bei DNG)
            if fmt in ("dng", "npy") and os.path.exists(out_path):
                try:
                    img = Image.open(out_path)  # DNG -> 16-bit container, 10-bit effektiv
                    raw = np.array(img)  # shape (H, W), dtype=uint16
                    if fmt == "npy":
                        npy_path = os.path.splitext(out_path)[0] + ".npy"
                        np.save(npy_path, raw)
                    if return_array:
                        return raw
                except Exception as e:
                    print(f"[WARN] DNG konnte nicht als Array gelesen werden: {e}")
                    if return_array:
                        return None

            return out_path

        finally:
            if was_running:
                self.start()
            self.preview_paused = False

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
        if self.preview_paused:
            return None
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
