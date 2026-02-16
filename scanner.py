import cv2
from pyzbar.pyzbar import decode
from ui import console

def scan_barcode_from_camera():
    """
    Opens the default camera to scan a barcode.
    Returns the decoded string or None if cancelled.
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

        # Decode barcodes
        decoded_objects = decode(frame)
        
        for obj in decoded_objects:
            detected_code = obj.data.decode("utf-8")
            
            # Draw rectangle
            points = obj.polygon
            if len(points) == 4:
                pts = [points[i] for i in range(4)]
                # Simple drawing logic (omitted complex numpy for brevity)
                pass 

            # Overlay text
            cv2.putText(frame, detected_code, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 
                        1, (0, 255, 0), 2, cv2.LINE_AA)
            
            # Auto-close on first detection? 
            # Let's wait for user to see it, but here we break fast for UX
            break

        cv2.imshow("Tape Barcode Scanner (Press 'q' to quit)", frame)

        if detected_code:
            # Short delay to show the user we found it
            cv2.waitKey(500)
            break

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    return detected_code