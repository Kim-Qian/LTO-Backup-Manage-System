import os
from pathlib import Path
from config_manager import cfg

class TapeDevice:
    """
    Manages interactions with the Tape filesystem (LTFS).
    Instead of one large file, we treat the tape as a directory.
    Each Job creates a separate file named 'job_{id}.tar' (or .enc).
    """
    def __init__(self, tape_id):
        self.tape_id = tape_id
        self.root_path = Path(cfg.get_root_path())
        
        # In LTFS, usually the tape is the root, but for simulation/structure,
        # we might use a folder per tape if debugging locally.
        # If real LTFS, root_path is "T:\".
        
        if cfg.get("debug_mode"):
            self.mount_point = self.root_path / tape_id
            self.mount_point.mkdir(parents=True, exist_ok=True)
        else:
            # In real LTFS, we assume the drive IS the tape. 
            # We must ensure the correct tape is loaded, but software can't physically swap it.
            # We assume T:\ is the current tape.
            self.mount_point = self.root_path

    def get_job_filename(self, job_id, encrypted=False):
        ext = ".enc" if encrypted else ".tar"
        return self.mount_point / f"job_{job_id}{ext}"

    def get_writer(self, job_id, encrypted=False):
        """Returns a file handle for writing a NEW file for this job."""
        file_path = self.get_job_filename(job_id, encrypted)
        return open(file_path, "wb")

    def get_reader(self, job_id, encrypted=False):
        """Returns a file handle for reading a SPECIFIC job file."""
        file_path = self.get_job_filename(job_id, encrypted)
        if not file_path.exists():
            raise FileNotFoundError(f"Job file {file_path} missing on tape.")
        return open(file_path, "rb")

    def current_size(self):
        """Calculates total size of files on the tape."""
        total = 0
        if self.mount_point.exists():
            for f in self.mount_point.iterdir():
                if f.is_file():
                    total += f.stat().st_size
        return total