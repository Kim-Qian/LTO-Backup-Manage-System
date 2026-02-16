import csv
import os
from datetime import datetime

class Logger:
    def __init__(self, log_file="system.log"):
        self.log_file = log_file
    
    def log(self, message, level="INFO"):
        """
        Appends a log entry with timestamp to the local log file.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{level}] {message}\n"
        
        # Append to file
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(entry)
        
        # Also print to stdout nicely (optional, dependent on use case)
        # print(entry.strip())

    def export_csv(self, output_path="operations_export.csv"):
        """
        Parses the log file and exports it to a structured CSV.
        """
        if not os.path.exists(self.log_file):
            print("No log file found to export.")
            return

        rows = []
        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                # Simple parsing logic based on the format above
                # Format: [Time] [Level] Message
                try:
                    parts = line.strip().split("] [")
                    if len(parts) >= 2:
                        ts = parts[0].strip("[")
                        # Split level and message
                        lvl_msg = parts[1].split("] ")
                        level = lvl_msg[0]
                        msg = lvl_msg[1] if len(lvl_msg) > 1 else ""
                        rows.append([ts, level, msg])
                except Exception:
                    continue

        # Write CSV
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Level", "Message"])
            writer.writerows(rows)