import json
import os
from glob import glob
from pathlib import Path
from ui import console, header
from tape import TapeDevice

def recover_database_from_tape(db, tape_id):
    """
    Scans the tape for 'job_*.json' files and rebuilds the SQLite database.
    This restores:
    - Job History (IDs, Dates, IVs, Tags)
    - File Index (Directory Tree)
    - Tape Metadata
    """
    header(f"Disaster Recovery: {tape_id}")
    
    try:
        tape = TapeDevice(tape_id)
        mount_point = tape.mount_point
    except Exception as e:
        console.print(f"[red]Error accessing tape device: {e}[/]")
        return
    
    if not mount_point.exists():
        console.print(f"[red]Tape mount point not found: {mount_point}[/]")
        return

    # Find all JSON metadata files
    json_files = sorted(list(mount_point.glob("job_*.json")))
    
    if not json_files:
        console.print("[red]No metadata files found on this tape. Cannot perform smart recovery.[/]")
        return

    console.print(f"[cyan]Found {len(json_files)} metadata files. Starting reconstruction...[/]")
    
    # Ensure Tape Exists in DB
    if not db.conn.execute("SELECT 1 FROM tapes WHERE tape_id=?", (tape_id,)).fetchone():
        console.print("[yellow]Tape not in DB. Creating entry...[/]")
        gen = input("Enter Tape Generation (L5/L6...): ").upper()
        desc = input("Enter Description: ")
        # Default to unencrypted, will update if jobs show encryption
        db.add_tape(tape_id, gen, desc, encrypted=False)

    success_count = 0
    
    for jf in json_files:
        try:
            with open(jf, "r", encoding="utf-8") as f:
                meta = json.load(f)
            
            job_id = meta.get("job_id")
            
            # Check if job already exists
            if db.conn.execute("SELECT 1 FROM jobs WHERE job_id=? AND tape_id=?", (job_id, tape_id)).fetchone():
                console.print(f"[dim]Skipping Job #{job_id} (Already exists)[/]")
                continue
                
            console.print(f"Restoring Job #{job_id}...", end="")
            
            crypto = meta.get("crypto", {})
            iv_hex = crypto.get("iv_hex")
            tag_hex = crypto.get("tag_hex")
            size = meta.get("total_size", 0)
            
            # Update encryption status of tape if we detect encryption
            if meta.get("encrypted"):
                db.conn.execute("UPDATE tapes SET encrypted=1 WHERE tape_id=?", (tape_id,))
            
            # Insert Job
            db.conn.execute(
                """INSERT INTO jobs (job_id, tape_id, action, started_at, finished_at, status, iv_hex, tag_hex, size)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (job_id, tape_id, "BACKUP", meta.get("timestamp"), meta.get("timestamp"), "SUCCESS", iv_hex, tag_hex, size)
            )
            
            # Restore File Index (Flattened)
            files = meta.get("files", [])
            for file_info in files:
                db.insert_node(
                    tape_id, 
                    None, # Parent structure is flattened in recovery for now
                    file_info["name"], 
                    int(file_info["is_dir"]), 
                    file_info["size"], 
                    job_id
                )
            
            db.conn.commit()
            console.print(f" [green]Done[/]")
            success_count += 1
            
        except Exception as e:
            console.print(f" [red]Error reading {jf.name}: {e}[/]")

    # Recalculate used capacity
    total_used = db.conn.execute("SELECT SUM(size) FROM jobs WHERE tape_id=?", (tape_id,)).fetchone()[0] or 0
    db.conn.execute("UPDATE tapes SET used_capacity=? WHERE tape_id=?", (total_used, tape_id))
    db.conn.commit()
    
    console.print(f"\n[bold green]Recovery Complete! {success_count} jobs restored.[/]")