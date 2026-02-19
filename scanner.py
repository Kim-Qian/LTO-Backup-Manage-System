import cv2
import numpy as np
from pyzbar.pyzbar import decode
from ui import console


def scan_barcode_from_camera():
    """
    Opens the default camera and scans for a barcode.
    Draws a coloured polygon around the detected barcode and overlays the
    decoded text on a solid background for readability.
    Returns the decoded string, or None if the user cancelled.
    """
    console.print("[yellow]Initializing Camera... Press 'q' to cancel.[/]")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        console.print("[red]Error: Could not open camera.[/]")
        return None

    detected_code = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        decoded_objects = decode(frame)

        for obj in decoded_objects:
            detected_code = obj.data.decode("utf-8")

            # Draw the barcode boundary polygon
            points = obj.polygon
            if len(points) >= 4:
                pts = np.array([[p.x, p.y] for p in points], dtype=np.int32)
                cv2.polylines(
                    frame, [pts], isClosed=True,
                    color=(0, 255, 0), thickness=3, lineType=cv2.LINE_AA
                )

                # Highlight the top-left corner so orientation is obvious
                cv2.circle(frame, (points[0].x, points[0].y), 6, (0, 0, 255), -1)

            # Measure text dimensions so we can draw a filled background box
            label = detected_code
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.85
            thickness = 2
            (text_w, text_h), baseline = cv2.getTextSize(label, font, font_scale, thickness)

            # Draw filled black rectangle behind the label
            pad = 6
            x0, y0 = 10, 10
            cv2.rectangle(
                frame,
                (x0, y0),
                (x0 + text_w + pad * 2, y0 + text_h + baseline + pad * 2),
                (0, 0, 0),
                cv2.FILLED,
            )
            # Draw label text in green
            cv2.putText(
                frame, label,
                (x0 + pad, y0 + text_h + pad),
                font, font_scale, (0, 255, 0), thickness, cv2.LINE_AA,
            )

            break  # Process only the first detected barcode per frame

        cv2.imshow("Tape Barcode Scanner (Press 'q' to quit)", frame)

        if detected_code:
            # Hold the frame briefly so the user can confirm the detection
            cv2.waitKey(800)
            break

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    return detected_code
