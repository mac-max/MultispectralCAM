import RPi.GPIO as GPIO
import time

# --- Pinbelegung für M1 auf dem Stepper Motor HAT (B) ---
PIN_ENA  = 12   # Enable für M1
PIN_DIR  = 13   # Richtung für M1
PIN_STEP = 19   # Schritt für M1

GPIO.setmode(GPIO.BCM)
GPIO.setup(PIN_ENA,  GPIO.OUT)
GPIO.setup(PIN_DIR,  GPIO.OUT)
GPIO.setup(PIN_STEP, GPIO.OUT)

# Aktivieren (HR8825: ENA LOW = aktiv; je nach HAT-Logik ggf. invertiert,
# der HAT schaltet ENA über Transistor; probier beides, falls Motor nicht reagiert)
GPIO.output(PIN_ENA, GPIO.LOW)

# Richtung vorgeben
GPIO.output(PIN_DIR, GPIO.HIGH)  # HIGH = Uhrzeigersinn (relativ)
time.sleep(0.1)

# Schrittweite / Geschwindigkeit
step_delay = 0.0015   # 1.5 ms (≈ 333 Hz). Bei Microstepping ggf. erhöhen.

steps = 200  # 200 Steps ≈ eine Umdrehung bei Vollschritt (1.8°/Step)

print("Drehe vorwärts...")
for _ in range(steps):
    GPIO.output(PIN_STEP, GPIO.HIGH)
    time.sleep(step_delay)
    GPIO.output(PIN_STEP, GPIO.LOW)
    time.sleep(step_delay)

time.sleep(0.3)

print("Drehe rückwärts...")
GPIO.output(PIN_DIR, GPIO.LOW)
for _ in range(steps):
    GPIO.output(PIN_STEP, GPIO.HIGH)
    time.sleep(step_delay)
    GPIO.output(PIN_STEP, GPIO.LOW)
    time.sleep(step_delay)

# Deaktivieren (Halten aus, Strom sparen)
GPIO.output(PIN_ENA, GPIO.HIGH)

GPIO.cleanup()
print("Fertig.")
