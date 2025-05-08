import cv2

def main():
    # Kamera initialisieren (ID 0 sollte bei der Pi-Kamera funktionieren)
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("Fehler: Kamera konnte nicht geöffnet werden.")
        return

    print("Kamerastream gestartet. Drücke 'q' zum Beenden.")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Fehler beim Lesen des Kamerabildes.")
            break

        # Bild anzeigen
        cv2.imshow("Live-Vorschau", frame)

        # Mit 'q' beenden
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
