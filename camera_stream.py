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

        self.proc_lock = threading.Lock()
        self.preview_paused = False

        self.debug = debug
        self.proc_lock = threading.Lock()
        self.stderr_lines = deque(maxlen=200)   # letzter libcamera-Output
        self._stderr_thread = None
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
            "--denoise", "cdn_off",
            "-t", "0",
            "--width", str(self.width),
            "--height", str(self.height),
            "--framerate", str(self.framerate),
            "--codec", "mjpeg",
            "--inline",
            "-o", "-"
        ]
        self.proc = subprocess.Popen(
            self.build_command(),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,  # <<—
            bufsize=10 ** 8
        )
        if self.shutter:
            cmd += ["--shutter", str(self.shutter)]
        if self.gain:
            cmd += ["--gain", str(self.gain)]
        return cmd

    def start(self):
        with self.proc_lock:
            if self.running:
                return
            self.running = True
            cmd = self.build_command()
            if self.debug:
                print("[VID] start:", " ".join(cmd))
            try:
                self.proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,  # <— NICHT DEVNULL!
                    bufsize=10 ** 8
                )
            except FileNotFoundError:
                self.running = False
                raise RuntimeError("libcamera-vid nicht gefunden.")

            # stderr reader
            def _read_stderr():
                try:
                    for line in iter(self.proc.stderr.readline, b""):
                        txt = line.decode(errors="replace").rstrip()
                        self.stderr_lines.append(txt)
                        # Optional: harmlose Meldungen filtern
                        # if "Corrupt JPEG data" in txt: continue
                        if self.debug and txt:
                            print("[VID][stderr]", txt)
                except Exception as e:
                    if self.debug:
                        print("[VID][stderr] reader err:", e)

            self._stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
            self._stderr_thread.start()

            self.thread = threading.Thread(target=self._read_stream, daemon=True)
            self.thread.start()

    def stop(self):
        with self.proc_lock:
            if not self.running:
                return
            self.running = False
            if self.proc:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                self.proc = None
            if self.thread:
                self.thread.join(timeout=1)
                self.thread = None
            if self._stderr_thread:
                self._stderr_thread.join(timeout=1)
                self._stderr_thread = None

    def last_errors(self, n=20):
        return "\n".join(list(self.stderr_lines)[-n:])

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
                           shutter=None, gain=None, fmt="dng", return_array=False, both=False):
        """
        OV5647 Sensor-RAW aufnehmen.
        fmt="dng": nur DNG schreiben (empfohlen)
        both=True: JPEG + DNG gleichzeitig (DNG-Name aus JPEG-Basename)
        return_array=True: DNG nach der Aufnahme als np.ndarray zurückgeben
        """
        import os, subprocess
        from PIL import Image
        import numpy as np

        def _prepare_output_path(path, wanted_ext):
            path = os.path.expanduser(path)
            base, ext = os.path.splitext(path)
            if ext.lower() != f".{wanted_ext}":
                path = f"{base}.{wanted_ext}"
            folder = os.path.dirname(path) or "."
            os.makedirs(folder, exist_ok=True)
            return path

        w = width or self.width
        h = height or self.height
        sh = shutter or self.shutter
        gn = gain or self.gain

        # Vorschau sicher pausieren
        was_running = self.running
        self.preview_paused = True
        if was_running:
            self.stop()

        try:
            base_cmd = [
                "libcamera-still",
                "-n",
                "--width", str(w),
                "--height", str(h),
                "--immediate",
                "--timeout", "1",
                "--denoise", "cdn_off",
            ]
            if sh: base_cmd += ["--shutter", str(sh)]
            if gn: base_cmd += ["--gain", str(gn)]

            if both:
                # JPEG + DNG: -r und JPEG-Pfad setzen
                jpg_path = _prepare_output_path(filename, "jpg")
                cmd = base_cmd + ["-r", "-o", jpg_path]
                dng_path = os.path.splitext(jpg_path)[0] + ".dng"
            else:
                # Nur DNG: --raw und DNG-Pfad setzen
                dng_path = _prepare_output_path(filename, "dng")
                cmd = base_cmd + ["--raw", "-o", dng_path]

            # Ausführen, bei sehr alten Builds Fallback von --raw auf -r
            try:
                self._run_capture(cmd, timeout=10)
            except subprocess.CalledProcessError as e:
                # Fallback: wenn --raw nicht existiert, versuche -r
                if not both and "--raw" in cmd:
                    cmd_fallback = [c for c in cmd if c != "--raw"]
                    cmd_fallback.insert(len(base_cmd), "-r")
                    # Bei -r braucht libcamera-still normalerweise einen "Haupt"-Output;
                    # wenn ein DNG-Name gesetzt war, vergeben wir zusätzlich einen JPEG,
                    # das DNG landet trotzdem beim Basename.
                    jpg_tmp = os.path.splitext(dng_path)[0] + ".jpg"
                    cmd_fallback = [c if c != dng_path else jpg_tmp for c in cmd_fallback]
                    subprocess.run(cmd_fallback, check=True)
                    # DNG-Pfad im Fallback:
                    dng_path = os.path.splitext(jpg_tmp)[0] + ".dng"
                else:
                    raise

            # Optional DNG als Array zurückgeben
            if return_array:
                try:
                    img = Image.open(dng_path)  # 16-bit Container, effektiv 10-bit
                    arr = np.array(img)  # shape (H, W), dtype=uint16
                    return arr
                except Exception as ex:
                    print(f"[WARN] DNG nicht als Array lesbar: {ex}")
                    return None

            return dng_path

        finally:
            if was_running:
                self.start()
            self.preview_paused = False

    # -------------------------------------------------
    # Stream-Thread
    # -------------------------------------------------
    # def _read_stream(self):
    #     """Liest kontinuierlich MJPEG-Daten und dekodiert sie zu PIL-Images."""
    #     while self.running:
    #         try:
    #             data = self.proc.stdout.read(4096)
    #             if not data:
    #                 break
    #             self.buffer += data
    #
    #             start = self.buffer.find(b'\xff\xd8')
    #             end = self.buffer.find(b'\xff\xd9')
    #
    #             if start != -1 and end != -1 and end > start:
    #                 jpg = self.buffer[start:end + 2]
    #                 self.buffer = self.buffer[end + 2:]
    #                 img = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
    #                 if img is not None:
    #                     img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    #                     self.frame = Image.fromarray(img)
    #         except Exception as e:
    #             print("Fehler im Kamera-Thread:", e)
    def _read_stream(self):
        CHUNK = 65536
        MAX_BUFFER = 8 * 1024 * 1024
        while self.running and self.proc and self.proc.stdout:
            try:
                data = self.proc.stdout.read(CHUNK)
                if not data:
                    break
                self.buffer += data

                if len(self.buffer) > MAX_BUFFER:
                    last_soi = self.buffer.rfind(b'\xff\xd8')
                    self.buffer = self.buffer[last_soi:] if last_soi != -1 else b""

                # alle kompletten Frames im Buffer verarbeiten
                while True:
                    start = self.buffer.find(b'\xff\xd8')
                    if start == -1:
                        # kein SOI im Buffer
                        self.buffer = self.buffer[-2:]  # Rest klein halten
                        break
                    end = self.buffer.find(b'\xff\xd9', start + 2)
                    if end == -1:
                        # Frame noch unvollständig
                        # kleinen Tail behalten, Rest vor SOI wegwerfen
                        self.buffer = self.buffer[start:]
                        break

                    jpg = self.buffer[start:end + 2]
                    self.buffer = self.buffer[end + 2:]

                    if len(jpg) < 2048:
                        continue

                    arr = np.frombuffer(jpg, dtype=np.uint8)
                    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if img is None:
                        continue
                    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    if not self.preview_paused:
                        self.frame = Image.fromarray(img)
            except Exception as e:
                print("Fehler im Kamera-Thread:", e)
                import time;
                time.sleep(0.01)

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

    def _run_capture(self, cmd, timeout=10):
        if self.debug:
            print("[STILL] run:", " ".join(cmd))
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if res.returncode != 0:
            # Kombiniere libcamera-still stderr + letzter Preview-stderr
            msg = [
                "[STILL] failed:",
                "cmd: " + " ".join(cmd),
                "stderr (still):",
                res.stderr.strip(),
                "— last preview stderr —",
                self.last_errors()
            ]
            raise RuntimeError("\n".join(msg))
        if self.debug and res.stderr.strip():
            print("[STILL][stderr]", res.stderr.strip())


# -------------------------------------------------
# Standalone-Test
# -------------------------------------------------
if __name__ == "__main__":
    stream = CameraStream(standalone=True)
