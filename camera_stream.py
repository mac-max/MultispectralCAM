# camera_stream.py
import os
import subprocess
import threading
import time
from collections import deque
import re
import numpy as np
import cv2
from PIL import Image


class CameraStream:
    """
    MJPEG-Preview auf Basis libcamera-vid (stdout -> JPEG Frames).
    Fixes:
      - --flush 1 erzwingt frameweises Flushen (sonst kann stdout lange leer wirken)
      - Popen(bufsize=0) -> keine Python-seitige Pufferung
      - health_check() für Debug
    """

    def __init__(self, width=640, height=480, framerate=15,
                 shutter=None, gain=None, extra_opts=None):
        self.width = width
        self.height = height
        self.framerate = framerate
        self.shutter = shutter
        self.gain = gain
        self.extra_opts = dict(extra_opts or {})

        self.proc = None
        self.thread = None
        self._stderr_thread = None
        self.proc_lock = threading.Lock()

        self.buffer = b""
        self.frame = None
        self.running = False
        self.preview_paused = False
        self.stderr_lines = deque(maxlen=200)
        self._supported_vid_opts = self._probe_supported_options("libcamera-vid")
        self._supported_still_opts = self._probe_supported_options("libcamera-still")

        self.start()

    # ---------- Diagnostics ----------

    def last_errors(self, n=20):
        return "\n".join(list(self.stderr_lines)[-n:])

    def health_check(self):
        return {
            "running": bool(self.running),
            "preview_paused": bool(self.preview_paused),
            "proc_exists": self.proc is not None,
            "proc_returncode": (None if not self.proc else self.proc.poll()),
            "thread_alive": bool(self.thread and self.thread.is_alive()),
            "cmd": " ".join(self.build_command()),
            "stderr_tail": self.last_errors(12),
        }

    def _probe_supported_options(self, toolname: str):
        try:
            res = subprocess.run([toolname, "--help"], capture_output=True, text=True, timeout=2)
            txt = (res.stdout or "") + "\n" + (res.stderr or "")
            return set(re.findall(r"--[a-zA-Z0-9_-]+", txt))
        except Exception:
            return set()


    # ---------- Process control ----------

    def start(self):
        with self.proc_lock:
            if self.running:
                return
            self.running = True
            cmd = self.build_command()

            try:
                # bufsize=0 => unbuffered pipes (hilft bei Live-Streams)
                self.proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0
                )
            except FileNotFoundError as e:
                self.running = False
                raise RuntimeError("libcamera-vid not found") from e

            # stderr reader
            def _read_stderr():
                try:
                    for line in iter(self.proc.stderr.readline, b""):
                        txt = line.decode(errors="replace").rstrip()
                        if not txt:
                            continue
                        # "Corrupt JPEG data" ist oft harmlos, aber wir loggen es nicht zu
                        if "Corrupt JPEG data" in txt:
                            continue
                        self.stderr_lines.append(txt)
                except Exception as ex:
                    self.stderr_lines.append(f"[stderr reader error] {ex}")

            self._stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
            self._stderr_thread.start()

            # stdout reader
            self.thread = threading.Thread(target=self._read_stream, daemon=True)
            self.thread.start()

            # Kurz prüfen, ob der Prozess sofort stirbt
            time.sleep(0.1)
            if self.proc.poll() is not None:
                self.stderr_lines.append("[CameraStream] libcamera-vid exited immediately")
                self.running = False

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

    def reconfigure(self, **kwargs):
        self.stop()

        # robust: libcamera mag hier i.d.R. ints (framerate/shutter/width/height)
        if "width" in kwargs and kwargs["width"] is not None:
            self.width = int(kwargs["width"])
        if "height" in kwargs and kwargs["height"] is not None:
            self.height = int(kwargs["height"])
        if "framerate" in kwargs and kwargs["framerate"] is not None:
            self.framerate = int(round(float(kwargs["framerate"])))
        if "shutter" in kwargs:
            self.shutter = None if kwargs["shutter"] is None else int(kwargs["shutter"])
        if "gain" in kwargs:
            self.gain = None if kwargs["gain"] is None else float(kwargs["gain"])

        if "extra_opts" in kwargs and kwargs["extra_opts"] is not None:
            self.extra_opts = dict(kwargs["extra_opts"])

        self.buffer = b""
        self.frame = None
        self.start()

    def set_extra_options(self, extra_opts: dict):
        self.extra_opts = dict(extra_opts or {})

    # ---------- Command ----------

    def build_command(self):
        cmd = [
            "libcamera-vid",
            "--nopreview",
            "-t", "0",
            "--width", str(self.width),
            "--height", str(self.height),
            "--framerate", str(int(self.framerate)),
            "--codec", "mjpeg",
            "--quality", "85",
            "--flush", "1",          # <<< wichtig für Live!
            "-o", "-"
        ]

        extra = self.extra_opts or {}

        # AE aus -> feste shutter/gain
        if not extra.get("ae", False):
            if self.shutter:
                cmd += ["--shutter", str(self.shutter)]
            if self.gain is not None:
                cmd += ["--gain", str(self.gain)]

        # AWB
        if extra.get("awb", False) is False:
            # libcamera: "off" ist ungültig -> für festen Weißabgleich "custom"
            cmd += ["--awb", "custom"]
            r, b = extra.get("awbgains", (2.0, 1.5))
            cmd += ["--awbgains", f"{r},{b}"]

        # Denoise / ISP
        if extra.get("denoise"):
            cmd += ["--denoise", extra["denoise"]]  # cdn_off|fast|hq
        if "sharpness" in extra:
            cmd += ["--sharpness", str(extra["sharpness"])]
        if "contrast" in extra:
            cmd += ["--contrast", str(extra["contrast"])]
        if "saturation" in extra:
            cmd += ["--saturation", str(extra["saturation"])]

        # Flicker (nur wenn Build das kennt)
        f = extra.get("flicker")
        if f and "--flicker" in getattr(self, "_supported_vid_opts", set()):
            cmd += ["--flicker", str(f)]

        return cmd

    # ---------- Stream reader ----------

    def _read_stream(self):
        CHUNK = 65536
        MAX_BUFFER = 8 * 1024 * 1024

        while self.running and self.proc and self.proc.stdout:
            try:
                data = self.proc.stdout.read(CHUNK)
                if not data:
                    break
                self.buffer += data

                # Puffer begrenzen
                if len(self.buffer) > MAX_BUFFER:
                    last_soi = self.buffer.rfind(b"\xff\xd8")
                    self.buffer = self.buffer[last_soi:] if last_soi != -1 else b""

                # komplette JPEGs dekodieren
                while True:
                    start = self.buffer.find(b"\xff\xd8")
                    if start == -1:
                        break
                    end = self.buffer.find(b"\xff\xd9", start + 2)
                    if end == -1:
                        break

                    jpg = self.buffer[start:end + 2]
                    self.buffer = self.buffer[end + 2:]

                    if len(jpg) < 1024:
                        continue

                    img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                    if img is None:
                        continue
                    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

                    if not self.preview_paused:
                        self.frame = Image.fromarray(img)

            except Exception as e:
                self.stderr_lines.append(f"[CameraStream error] {e}")
                time.sleep(0.05)

    def get_frame(self):
        return self.frame

    # ---------- Still capture helpers ----------

    def _run_capture(self, cmd, timeout=10):
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if res.returncode != 0:
            msg = [
                "[STILL] failed",
                "cmd: " + " ".join(cmd),
                "stderr:",
                (res.stderr or "").strip(),
                "— last preview stderr —",
                self.last_errors(20)
            ]
            raise RuntimeError("\n".join(msg))
        if res.stderr:
            self.stderr_lines.append("[still] " + res.stderr.strip())

    def _apply_extra_to_still(self, base_cmd: list, extra: dict):
        # AWB/awbgains
        if extra.get("awb", False) is False:
            base_cmd += ["--awb", "custom"]
            r, b = extra.get("awbgains", (2.0, 1.5))
            base_cmd += ["--awbgains", f"{r},{b}"]

        if extra.get("denoise"):
            base_cmd += ["--denoise", extra["denoise"]]
        if "sharpness" in extra:
            base_cmd += ["--sharpness", str(extra["sharpness"])]
        if "contrast" in extra:
            base_cmd += ["--contrast", str(extra["contrast"])]
        if "saturation" in extra:
            base_cmd += ["--saturation", str(extra["saturation"])]
        # Flicker
        f = extra.get("flicker")
        if f and "--flicker" in getattr(self, "_supported_still_opts", set()):
            base_cmd += ["--flicker", str(f)]

        return base_cmd

    def capture_still(self, filename="capture.jpg", fmt="jpg",
                      width=None, height=None, shutter=None, gain=None):
        """
        Speichert ein 'entwickeltes' Bild (jpg/png/tiff/bmp) über libcamera-still.
        Berücksichtigt extra_opts (AWB off, awbgains, denoise,...).
        """
        fmt = (fmt or "jpg").lower()
        enc = "jpg" if fmt == "jpeg" else fmt
        if enc not in ("jpg", "png", "tiff", "bmp"):
            raise ValueError(f"Unsupported format: {fmt}")

        filename = os.path.expanduser(filename)
        base, ext = os.path.splitext(filename)
        if ext.lower() != f".{enc}":
            filename = base + f".{enc}"
        os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)

        w = width or self.width
        h = height or self.height
        extra = self.extra_opts or {}

        if extra.get("ae", False):
            sh = None
            gn = None
        else:
            sh = shutter if shutter is not None else self.shutter
            gn = gain if gain is not None else self.gain

        base_cmd = [
            "libcamera-still",
            "-n",
            "--immediate",
            "--timeout", "1",
            "--width", str(w),
            "--height", str(h),
            "--encoding", enc,
        ]
        if sh:
            base_cmd += ["--shutter", str(sh)]
        if gn:
            base_cmd += ["--gain", str(gn)]
        base_cmd = self._apply_extra_to_still(base_cmd, extra)
        base_cmd += ["-o", filename]

        was_running = self.running
        self.preview_paused = True
        if was_running:
            self.stop()
        try:
            self._run_capture(base_cmd, timeout=15)
            return filename
        finally:
            if was_running:
                self.start()
            self.preview_paused = False

    def capture_raw_dng(self, filename="capture.dng", width=None, height=None,
                        shutter=None, gain=None, both=False):
        """
        Echten Sensor-RAW (DNG) aufnehmen.
        - both=False: nur DNG
        - both=True : JPEG + DNG (DNG neben JPEG-Basename)
        """
        filename = os.path.expanduser(filename)
        base, ext = os.path.splitext(filename)

        w = width or self.width
        h = height or self.height
        extra = self.extra_opts or {}

        if extra.get("ae", False):
            sh = None
            gn = None
        else:
            sh = shutter if shutter is not None else self.shutter
            gn = gain if gain is not None else self.gain

        base_cmd = [
            "libcamera-still",
            "-n",
            "--immediate",
            "--timeout", "1",
            "--width", str(w),
            "--height", str(h),
        ]
        if sh:
            base_cmd += ["--shutter", str(sh)]
        if gn:
            base_cmd += ["--gain", str(gn)]
        base_cmd = self._apply_extra_to_still(base_cmd, extra)

        was_running = self.running
        self.preview_paused = True
        if was_running:
            self.stop()
        try:
            if both:
                jpg_path = base + ".jpg" if ext.lower() != ".jpg" else filename
                os.makedirs(os.path.dirname(jpg_path) or ".", exist_ok=True)
                cmd = base_cmd + ["-r", "-o", jpg_path]
                self._run_capture(cmd, timeout=20)
                dng_path = os.path.splitext(jpg_path)[0] + ".dng"
                return jpg_path, dng_path
            else:
                dng_path = base + ".dng" if ext.lower() != ".dng" else filename
                os.makedirs(os.path.dirname(dng_path) or ".", exist_ok=True)
                cmd = base_cmd + ["--raw", "-o", dng_path]
                try:
                    self._run_capture(cmd, timeout=20)
                except RuntimeError:
                    # Fallback für Builds ohne --raw: -r erzeugt JPEG+DNG
                    jpg_tmp = base + ".tmp.jpg"
                    cmd_fb = base_cmd + ["-r", "-o", jpg_tmp]
                    self._run_capture(cmd_fb, timeout=20)
                    dng_path = os.path.splitext(jpg_tmp)[0] + ".dng"
                    try:
                        os.remove(jpg_tmp)
                    except Exception:
                        pass
                return dng_path
        finally:
            if was_running:
                self.start()
            self.preview_paused = False
