# camera_stream.py
import subprocess, threading, time, os
from collections import deque
import numpy as np
import cv2
from PIL import Image

class CameraStream:
    """
    Solider MJPEG-Preview auf Basis libcamera-vid.
    - robustes Frame-Parsing (mehrere JPEGs pro chunk)
    - stderr-Ringpuffer für Diagnosen
    - health_check() gibt Status + letzte Fehlermeldungen zurück
    - preview_paused wird beim Capture IMMER zurückgesetzt
    """
    def __init__(self, width=640, height=480, framerate=15, shutter=None, gain=None, extra_opts=None):
        self.width = width
        self.height = height
        self.framerate = framerate
        self.shutter = shutter
        self.gain = gain
        self.extra_opts = extra_opts or {}

        self.proc = None
        self.thread = None
        self._stderr_thread = None
        self.proc_lock = threading.Lock()

        self.buffer = b""
        self.frame = None
        self.running = False
        self.preview_paused = False
        self.stderr_lines = deque(maxlen=200)

        self.start()

    # ---------------- diagnostics ----------------
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

    # ---------------- process control ----------------
    def start(self):
        with self.proc_lock:
            if self.running:
                return
            self.running = True
            cmd = self.build_command()
            # print("[VID] start:", " ".join(cmd))
            try:
                self.proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,     # nicht verschlucken!
                    bufsize=10**8
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
                        # harmlose Meldungen optional filtern:
                        if "Corrupt JPEG data" in txt:
                            continue
                        self.stderr_lines.append(txt)
                        # print("[VID][stderr]", txt)
                except Exception as ex:
                    self.stderr_lines.append(f"[stderr reader error] {ex}")

            self._stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
            self._stderr_thread.start()

            # stdout reader
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

    def reconfigure(self, **kwargs):
        self.stop()
        self.width = kwargs.get("width", self.width)
        self.height = kwargs.get("height", self.height)
        self.framerate = kwargs.get("framerate", self.framerate)
        self.shutter = kwargs.get("shutter", self.shutter)
        self.gain = kwargs.get("gain", self.gain)
        self.extra_opts = kwargs.get("extra_opts", self.extra_opts)
        self.buffer = b""
        self.frame = None
        self.start()

    def set_extra_options(self, extra_opts: dict):
        self.extra_opts = dict(extra_opts or {})

    # ---------------- command ----------------
    def build_command(self):
        cmd = [
            "libcamera-vid",
            "--nopreview", "-t", "0",
            "--width", str(self.width),
            "--height", str(self.height),
            "--framerate", str(self.framerate),
            "--codec", "mjpeg",
            "--inline",
            "-o", "-"
        ]
        extra = self.extra_opts or {}

        # AE aus -> feste shutter/gain
        if not extra.get("ae", False):
            if self.shutter: cmd += ["--shutter", str(self.shutter)]
            if self.gain:
