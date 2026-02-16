import tarfile
from tqdm import tqdm
from tape import TapeDevice
from crypto import DecryptionReader

class ProgressReader:
    """Wraps file reading to update progress bar."""
    def __init__(self, wrapped_file, size, pbar):
        self._file = wrapped_file
        self.size = size
        self.read_so_far = 0
        self._bar = pbar

    def read(self, size=-1):
        data = self._file.read(size)
        if data:
            self._bar.update(len(data))
            self.read_so_far += len(data)
        return data

def run_restore_job(db, tape_id, job_id, out_dir, key=None):
    row = db.conn.execute(
        "SELECT size, iv_hex, tag_hex FROM jobs WHERE job_id=? AND tape_id=?", 
        (job_id, tape_id)
    ).fetchone()
    
    if not row: raise Exception("Job not found in database.")
    size, iv_hex, tag_hex = row
    
    tape = TapeDevice(tape_id)
    # Open the file on tape
    raw_tape_file = tape.get_reader(job_id, encrypted=(key is not None))
    
    pbar = tqdm(total=size, unit='B', unit_scale=True, desc="Verifying & Restoring")
    progress_reader = ProgressReader(raw_tape_file, size, pbar)

    final_reader = progress_reader

    if key:
        if not iv_hex or not tag_hex:
            raise Exception("Encrypted job missing IV or GCM Tag in database.")
        iv = bytes.fromhex(iv_hex)
        tag = bytes.fromhex(tag_hex)
        # Pass the tag to DecryptionReader for integrity check
        final_reader = DecryptionReader(progress_reader, key, iv, tag)

    try:
        with tarfile.open(fileobj=final_reader, mode='r|') as tar:
            tar.extractall(out_dir)
        
        pbar.close()
        raw_tape_file.close()
        print(f"Restore Successful. Integrity verified.")
    except Exception as e:
        print(f"\n[bold red]CRITICAL RESTORE ERROR: {e}[/]")
        # Try to close explicitly if exception occurred
        try: raw_tape_file.close() 
        except: pass
        raise e