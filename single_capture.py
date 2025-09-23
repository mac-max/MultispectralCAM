from picamera2 import Picamera2, Preview
import time

picam2 = Picamera2()

# Kamera-Konfiguration für RAW + JPEG Ausgabe
config = picam2.create_still_configuration(
    raw={"size": picam2.sensor_resolution},  # Bayer-Rohdaten
    main={"size": (2592, 1944)},             # zusätzlich ein "normales" Bild
    buffer_count=2
)

picam2.configure(config)

# Automatik ausschalten (Belichtung, Gain, Weißabgleich)
controls = {
    "ExposureTime": 100000,   # in µs (100 ms)
    "AnalogueGain": 1.0,     # ~ ISO 100
    "AwbEnable": False,      # Auto White Balance aus
    "ColourGains": (1.0, 1.0)  # manuelles Weißabgleich-Gain für R/G/B
}

picam2.set_controls(controls)

picam2.start()
time.sleep(2)  # kurze Wartezeit, damit Kamera sich stabilisiert

# Einzelbild aufnehmen
raw_capture = picam2.capture_array("raw")
jpeg_capture = picam2.capture_array("main")

# Oder direkt als Datei (RAW + JPEG gleichzeitig)

picam2.capture_metadata()  # Metadaten mitnehmen
picam2.capture_file("/run/user/1000/gvfs/ftp:host=192.168.178.1,user=max/Frank/Images/image.dng", name="raw")   # speichert echtes RAW im DNG-Format
picam2.capture_file("/run/user/1000/gvfs/ftp:host=192.168.178.1,user=max/Frank/Images/image.jpg")

picam2.stop()
