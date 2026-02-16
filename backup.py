import tarfile
import os
import json
from datetime import datetime, timezone
import hashlib
from tqdm import tqdm
from crypto import EncryptionWriter, encrypt_name
from tape import TapeDevice
from config_manager import cfg

class ProgressWriter:
    """Wraps a file object to update a tqdm progress bar and optionally calculate SHA256."""
    def __init__(self, wrapped_file, progress_bar, calc_hash=True):
        self._file = wrapped_file
        self._bar = progress_bar
        self.sha256 = hashlib.sha256() if calc_hash else None

    def write(self, data):
        self._file.write(data)
        # Update progress based on compressed/encrypted size written to tape
        self._bar.update(len(data))
        if self.sha256:
            self.sha256.update(data)
    
    def flush(self):
        self._file.flush()

    def tell(self):
        return self._file.tell()

def calculate_total_size(paths):
    """Calculates the total size of files to be backed up."""
    total = 0
    for p in paths:
        if os.path.isfile(p):
            total += os.path.getsize(p)
        elif os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                for f in files:
                    total += os.path.getsize(os.path.join(root, f))
    return total

def save_job_metadata_to_tape(tape, job_id, meta_dict):
    """Writes a lightweight JSON manifest to the tape alongside the archive."""
    json_filename = f"job_{job_id}.json"
    json_path = tape.mount_point / json_filename
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta_dict, f, indent=2, ensure_ascii=False)
    
    return json_path

def run_backup_job(db, tape_id, paths, key=None, generation="L5"):
    # 1. Validation
    tape = TapeDevice(tape_id)
    total_size = calculate_total_size(paths)
    
    used = db.get_used_capacity(tape_id)
    gen_info = cfg.get_generation_info(generation)
    max_cap = gen_info.get("capacity", 2500 * 10**9) # Default to L6 size if missing
    
    if used + total_size > max_cap:
        raise Exception(f"Insufficient space. Needed: {total_size/1e9:.2f} GB, Available: {(max_cap-used)/1e9:.2f} GB")

    # 2. Crypto Setup
    iv = os.urandom(12) if key else None # AES-GCM recommends 12 bytes IV
    iv_hex = iv.hex() if iv else None
    
    # 3. Start Job in DB
    job_id = db.new_job(tape_id, "BACKUP", iv_hex)
    
    # 4. Save Metadata
    job_manifest = {
        "job_id": job_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "encrypted": bool(key),
        "crypto": {
            "iv_hex": iv_hex,
            "tag_hex": None, # To be filled after writing
        },
        "files": []
    }

    print("Indexing files...")
    db.conn.execute("BEGIN TRANSACTION")

    def index_and_collect(path, parent_id, key):
        name = os.path.basename(path)
        is_dir = os.path.isdir(path)
        size = os.path.getsize(path) if not is_dir else 0
        name_stored = encrypt_name(name, key) if key else name
        # 1. DB Insert
        node_id = db.insert_node(tape_id, parent_id, name_stored, int(is_dir), size, job_id)
        
        # 2. Manifest Collect
        job_manifest["files"].append({
            "name": name,
            "is_dir": is_dir,
            "size": size
        })
        
        if is_dir:
            try:
                for item in os.listdir(path):
                    index_and_collect(os.path.join(path, item), node_id, key)
            except PermissionError:
                print(f"Warning: Permission denied accessing {path}")

    for p in paths:
        index_and_collect(p, None, key)
    db.conn.commit()

    # 5. Execute Streaming Backup
    tag_hex = None
    try:
        # Open the actual file on the tape (or simulated folder)
        with tape.get_writer(job_id, encrypted=(key is not None)) as raw_tape_file:
            # Progress bar tracks bytes WRITTEN to tape (compressed/encrypted)
            pbar = tqdm(total=total_size, unit='B', unit_scale=True, desc="Backup & Sync")
            progress_writer = ProgressWriter(raw_tape_file, pbar, calc_hash=(key is None))
            
            enc_writer = None
            final_writer = progress_writer

            if key:
                enc_writer = EncryptionWriter(progress_writer, key, iv)
                final_writer = enc_writer
            
            # Create Tar archive streaming into the writer
            with tarfile.open(fileobj=final_writer, mode='w|') as tar:
                for p in paths:
                    tar.add(p, arcname=os.path.basename(p))
            
            # Finalize crypto (Calculate GCM Tag)
            if enc_writer:
                tag = enc_writer.finalize()
                tag_hex = tag.hex()
                job_manifest["crypto"]["tag_hex"] = tag_hex
            elif progress_writer.sha256:
                # If not encrypted, we use SHA256 of the plain tar stream as the 'tag'
                tag_hex = progress_writer.sha256.hexdigest()
                job_manifest["crypto"]["tag_hex"] = tag_hex
            
            pbar.close()

        # 6. Finalize & Write JSON to Tape
        job_file_path = tape.get_job_filename(job_id, encrypted=(key is not None))
        written_size = os.path.getsize(job_file_path)
        
        # Update Manifest with final stats
        job_manifest["total_size"] = written_size
        
        # Write JSON to Tape!
        json_path = save_job_metadata_to_tape(tape, job_id, job_manifest)
        
        db.update_used_capacity(tape_id, written_size)
        db.finish_job(job_id, "SUCCESS", size=written_size, tag_hex=tag_hex)
        
        print(f"Metadata saved to {json_path}")
        return job_id

    except Exception as e:
        db.finish_job(job_id, "FAILED")
        raise e