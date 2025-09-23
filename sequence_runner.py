import os
import json
import time
import pathlib
from typing import Dict, Tuple

import numpy as np
import tifffile as tiff

# ---------- LED / PCA9685 ----------
os.environ["BLINKA_FORCECHIP"] = "BCM2XXX"  # für Blinka auf dem Pi

import board
import busio
from adafruit_pca9685 import PCA9685

# ---------- IR-Filter ----------
# Deine Datei filter_controller.py muss im selben Ordner liegen:
from filter_controller import IRFilterController  # nutzt pigpio (pigpiod muss laufen)

# ---------- Kamera (Platzhalter) ----------
def set_camera_settings(settings: dict):
    """
    TODO: an deine Kamera-API anpassen (Exposure, Gain, Auflösung, Bit-Tiefe, etc.)
    """
    print("[Kamera] Settings:", settings)

def capture_raw() -> np.ndarray:
    """
    TODO: durch echte Kameraaufnahme ersetzen.
    Dummy: erzeugt 16-bit-Rauschbild mit 1080x1920.
    """
    return np.random.randint(0, 65535, (1080, 1920), dtype=np.uint16)

# ---------- Panels initialisieren ----------
i2c = busio.I2C(board.SCL, board.SDA)

# Adresse ggf. anpassen, falls deine Panels andere I2C-Adressen haben
panelA = PCA9685(i2c, address=0x41)  # z. B. 8-Kanal-Panel
panelB = PCA9685(i2c, address=0x42)  # z. B. 14-Kanal-Panel
panelA.frequency = 1000
panelB.frequency = 1000

PANELS = {
    "A": {"driver": panelA, "channels": 8},
    "B": {"driver": panelB, "channels": 14},
}

def set_led(panel: str, channel: int, percent: float):
    if panel not in PANELS:
        raise ValueError(f"Unbekanntes Panel '{panel}'")
    percent = max(0.0, min(100.0, float(percent)))
    value = int((percent / 100.0) * 0xFFFF)
    drv = PANELS[panel]["driver"]
    drv.channels[channel].duty_cycle = value
    print(f"[LED] Panel {panel}, Kanal {channel} = {percent:.1f}%")

def all_off():
    for pname, pdata in PANELS.items():
        for ch in range(pdata["channels"]):
            pdata["driver"].channels[ch].duty_cycle = 0
    print("[LED] Alle Kanäle AUS")

# ---------- Wellenlängen-Mapping ----------
# Numeric Keys bevorzugt (drei-/vierstellig). Aliasse für Sonder-LEDs möglich.
# Panel A (aus deinem 8-Kanal-Skript): 640, WW, 457, 512, 609, 596, 448, pink
# Panel B (aus deinem 14-Kanal-Skript): 415, 445, 480, 515, 555, 590, 630, 680, 700, 750, 780, 850, NIR, CW
WAVELENGTH_MAP: Dict[str, Tuple[str, int]] = {
    # Panel A
    "640": ("A", 0),
    "457": ("A", 2),
    "512": ("A", 3),
    # nicht-numerische Aliasse (optional verwendbar)
    "WW": ("A", 1),
    "609": ("A", 4),
    "596": ("A", 5), "yellow": ("A", 5),
    "448": ("A", 6),
    "pink": ("A", 7),

    # Panel B
    "415": ("B", 0),
    "445": ("B", 1),
    "480": ("B", 2),
    "515": ("B", 3),
    "555": ("B", 4),
    "590": ("B", 5),
    "630": ("B", 6),
    "680": ("B", 7),
    "700": ("B", 8),
    "750": ("B", 9),
    "780": ("B", 10),
    "850": ("B", 11),
    "nir": ("B", 12),
    "CW": ("B", 13)
}

# ---------- IR-Filter-Wrapper ----------
def set_ir_filter(controller: IRFilterController, position: str):
    pos = str(position).strip().lower()
    if pos in ("in", "ein", "on"):
        controller.switch_in()
        print("[IR-Filter] → IN")
    elif pos in ("out", "aus", "off"):
        controller.switch_out()
        print("[IR-Filter] → OUT")
    else:
        raise ValueError(f"Ungültige IR-Filter-Position: {position!r} (erlaubt: 'in'/'out')")

# ---------- Hauptablauf ----------
def run_sequence(seqfile: str, outdir: str = "output"):
    seqfile = pathlib.Path(seqfile)
    outdir = pathlib.Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    with seqfile.open("r", encoding="utf-8") as f:
        config = json.load(f)

    # Kamera konfigurieren
    set_camera_settings(config.get("camera_settings", {}))

    # IR-Filter Controller initialisieren
    irc = IRFilterController()  # Pins/Timing notfalls in JSON konfigurierbar machen
    try:
        for i, step in enumerate(config.get("steps", []), 1):
            # --- Wellenlänge → (Panel, Kanal)
            wl_key = str(step["wavelength"]).strip().lower()
            if wl_key not in WAVELENGTH_MAP:
                raise KeyError(
                    f"Wellenlänge/Key '{wl_key}' nicht im Mapping. "
                    f"Bitte in WAVELENGTH_MAP ergänzen."
                )
            panel, ch = WAVELENGTH_MAP[wl_key]
            intensity = float(step.get("intensity", 1.0))  # 0.0–1.0
            percent = intensity * 100.0

            print(f"\n[Step {i}] wl={wl_key}, panel={panel}, ch={ch}, "
                  f"intensity={intensity:.3f}, ir={step.get('ir_filter')}")

            # --- LEDs setzen
            set_led(panel, ch, percent)

            # --- optional: andere Kanäle dieses Panels auf 0 setzen
            # (falls du wirklich nur *eine* LED pro Step willst)
            # for other in range(PANELS[panel]["channels"]):
            #     if other != ch:
            #         set_led(panel, other, 0.0)

            # --- IR-Filter schalten
            set_ir_filter(irc, step.get("ir_filter", "out"))

            # --- optionale Wartezeit pro Step (ms)
            delay_ms = int(step.get("delay_ms", 200))
            time.sleep(max(0, delay_ms) / 1000.0)

            # --- Bild aufnehmen & speichern
            img = capture_raw()
            tag = step.get("tag", f"{wl_key}nm_{step.get('ir_filter','out')}")
            fname = outdir / f"step_{i:03d}_{tag}.tiff"
            tiff.imwrite(str(fname), img)
            print(f"[Saved] {fname}")

    finally:
        # immer aufräumen
        all_off()
        try:
            irc.cleanup()
        except Exception as e:
            print(f"[IR-Filter] cleanup Hinweis: {e}")

if __name__ == "__main__":
    # Beispielaufruf
    run_sequence("example_sequence_wavelength.json", outdir="output")
