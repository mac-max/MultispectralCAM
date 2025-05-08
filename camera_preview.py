import subprocess
import cv2
import numpy as np

def run_camera_preview():
    # Starte libcamera-vid mit MJPEG-Ausgabe an stdout
    cmd = [
        "libcamera-vid",
        "-t", "0",                    # Unbegrenzt laufen
        "--width", "640",
        "--height", "480",
        "--framerate", "15",
        "--codec", "mjpeg",          # JPEG-Frames
        "--inline",                  # JPEG-Marker erforderlich
        "-o", "-"                    # Ausgabe auf stdout
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=10**8)

    buffer = b""
    while True:
        # Lese Daten vom MJPEG-Stream
        data = proc.stdout.read(4096)
        if not data:
            break
        buffer += data

        # Suche JPEG-Start- und End-Marker
        start = buffer.find(b'\xff\xd8')
        end = buffer.find(b'\xff\xd9')
        if start != -1 and end != -1 and end > start:
            jpg = buffer[start:end+2]
            buffer = buffer[end+2:]

            # JPEG dekodieren und anzeigen
            img = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is not None:
                cv2.imshow("Live-Vorschau (libcamera-vid)", img)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

    proc.terminate()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    run_camera_preview()
