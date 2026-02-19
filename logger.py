import logging
import json
import csv
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler


class _JsonFormatter(logging.Formatter):
    """Formats each log record as a single-line JSON object for reliable parsing."""
    def format(self, record):
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        return json.dumps(entry, ensure_ascii=False)


class Logger:
    def __init__(self, log_file="system.log", max_bytes=5 * 1024 * 1024, backup_count=3):
        """
        Args:
            log_file:     Path to the primary log file.
            max_bytes:    Rotate the log when it exceeds this size (default 5 MB).
            backup_count: Number of rotated backup files to keep (default 3).
        """
        self.log_file = log_file
        self._logger = logging.getLogger("lto_system")
        self._logger.setLevel(logging.DEBUG)

        # Guard against duplicate handlers if Logger is re-instantiated in the
        # same process (e.g., during testing or hot-reload scenarios).
        if not self._logger.handlers:
            handler = RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            handler.setFormatter(_JsonFormatter())
            self._logger.addHandler(handler)

    def log(self, message, level="INFO"):
        """Appends a structured JSON log entry at the given level."""
        dispatch = {
            "DEBUG":    self._logger.debug,
            "INFO":     self._logger.info,
            "WARNING":  self._logger.warning,
            "ERROR":    self._logger.error,
            "CRITICAL": self._logger.critical,
        }
        dispatch.get(level.upper(), self._logger.info)(message)

    def export_csv(self, output_path="operations_export.csv"):
        """
        Reads every JSON log line and writes a structured CSV.
        Silently skips any malformed lines (e.g., partial writes from a crash).
        """
        if not os.path.exists(self.log_file):
            print("No log file found to export.")
            return

        rows = []
        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    rows.append([
                        entry.get("timestamp", ""),
                        entry.get("level", ""),
                        entry.get("message", ""),
                    ])
                except json.JSONDecodeError:
                    # Skip lines that are not valid JSON (e.g., rotation boundary markers)
                    continue

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Level", "Message"])
            writer.writerows(rows)

        print(f"Exported {len(rows)} log entries to {output_path}")
