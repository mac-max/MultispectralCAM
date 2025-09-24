import os, time, json
import cv2
import numpy as np
from picamera2 import Picamera2
from 4928d159-3e78-4a31-bcad-aa2d75829fb9 import LEDController  # deine Datei importieren

# --- LED Controller ---
led = LEDController()
channel_names = led.channel_names

def set_pwm(channel, percent):
    led.set_pwm(channel, percent)

def all_off():
    led.all_off()

# --- Kamera Setup ---
picam2 = Picamera2()
config = picam2.create_still_configuration(main={"size": (640, 480)})
picam2.configure(config)
controls = {
    "ExposureTime": 20000,
    "AnalogueGain": 1.0,
    "AwbEnable": False,
    "ColourGains": (1.0, 1.0),
}
picam2.set_controls(controls)
picam2.start()
time.sleep(1)

# --- ROI automatisch finden ---
def find_roi(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if contours:
        c = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(c)
        return (x, y, w, h)
    else:
        return (0, 0, frame.shape[1], frame.shape[0])

# --- Iterative Kalibrierung ---
def calibrate_channel(channel, target_mean=0.5, tolerance=0.05, max_trials=10):
    level = 30.0
    for trial in range(max_trials):
        set_pwm(channel, level)
        time.sleep(0.3)

        frame = picam2.capture_array("main")
        x, y, w, h = find_roi(frame)
        roi_frame = frame[y:y+h, x:x+w]

        mean_intensity = roi_frame.mean() / 255.0
        print(f"[{channel_names[channel]}] Trial {trial+1}: mean={mean_intensity:.3f}, level={level:.1f}%")

        # ROI anzeigen
        vis = frame.copy()
        cv2.rectangle(vis, (x, y), (x+w, y+h), (0,255,0), 2)
        cv2.imshow("ROI Preview", vis)
        cv2.waitKey(1)

        if abs(mean_intensity - target_mean) <= tolerance:
            print(f" {channel_names[channel]} kalibriert auf {level:.1f}% PWM")
            return level

        level *= target_mean / (mean_intensity + 1e-6)
        level = min(max(level, 1.0), 100.0)

    print(f" {channel_names[channel]} nicht perfekt kalibriert, Endwert={level:.1f}%")
    return level

# --- Hauptschleife: Alle Kanäle ---
results = {}
for ch in range(len(channel_names)):
    all_off()
    time.sleep(0.5)
    pwm_value = calibrate_channel(ch)
    results[channel_names[ch]] = pwm_value

all_off()
picam2.stop()
cv2.destroyAllWindows()

# --- Ergebnisse speichern ---
out_file = "/home/pi/captures/led_calibration.json"
os.makedirs(os.path.dirname(out_file), exist_ok=True)
with open(out_file, "w") as f:
    json.dump(results, f, indent=4)

print("\nErgebnisse gespeichert in:", out_file)
print(json.dumps(results, indent=4))
