from ui import header, confirm, console, wait_for_keypress, clear, print_error, print_success, choose_arrow
from db import Database
import time
from backup import run_backup_job
from restore import run_restore_job
from browse import browse
from logger import Logger
from config_manager import cfg
from scanner import scan_barcode_from_camera
from rich.table import Table
from verify import verify_tape_integrity
from recovery import recover_database_from_tape
from crypto import derive_key, generate_rsa_keypair, encrypt_symmetric_key, decrypt_symmetric_key, sha256_hex
import secrets
import os

db = Database()
log = Logger()

def get_tape_id_input(prompt="Enter Tape ID"):
    """Helper to choose between manual input or camera scan."""
    console.print(f"\n{prompt}")
    console.print("[dim]Type ID directly or type 'scan' to use camera.[/]")
    val = input("> ").strip()
    if val.lower() == 'scan':
        code = scan_barcode_from_camera()
        if code:
            console.print(f"Scanned: [bold green]{code}[/]")
            if confirm(f"Use ID '{code}'?"):
                return code
        return None
    return val if val else None

def add_new_tapes():
    header("Add New Tapes")
    
    while True:
        tape_id = get_tape_id_input("Enter Tape ID to Add")
        if not tape_id: break

        # Check existence
        existing = db.conn.execute("SELECT 1 FROM tapes WHERE tape_id=?", (tape_id,)).fetchone()
        if existing:
            console.print(f"[red]Tape {tape_id} already exists![/]")
            continue

        description = input("Enter Description/Label: ").strip()
        gen = input("Generation (L5/L6/L7/L8/L9/L10): ").strip().upper()
        if gen not in cfg.config['generations']:
            console.print("[red]Invalid generation.[/]")
            continue

        is_enc = confirm(f"Enable encryption for {tape_id}?")
        
        db.add_tape(tape_id, gen, description, is_enc)

        if is_enc:
            console.print("\n[bold cyan]Encryption Setup[/]")
            print("1. Password Derived Key (Simpler, requires remembering password)")
            print("2. RSA Key Pair (Higher security, saves key file to disk)")
            choice = input("Select method (1/2): ").strip()
            
            final_key = None
            
            if choice == "1":
                pwd = input("Set Passphrase: ").strip().encode()
                if not pwd:
                    console.print("[red]Password cannot be empty. Tape set to Plain.[/]")
                    db.conn.execute("UPDATE tapes SET encrypted=0 WHERE tape_id=?", (tape_id,))
                    continue
                
                salt = os.urandom(16)
                final_key = derive_key(pwd, salt)
                
                # Store Salt and Hash of key (for validation)
                db.conn.execute(f"INSERT INTO tape_{tape_id}_info (key, value) VALUES (?, ?)", ("kdf_salt", salt.hex()))
                db.conn.execute(f"INSERT INTO tape_{tape_id}_info (key, value) VALUES (?, ?)", ("sym_key_hash", sha256_hex(final_key)))
                console.print("[green]Key derived from password and configured.[/]")

            elif choice == "2":
                # Generate a random master key for the tape
                final_key = secrets.token_bytes(32) # 256-bit key
                
                # Generate or Load RSA
                key_dir = f"keys/{tape_id}"
                console.print(f"Generating RSA keys in {key_dir}...")
                public_pem = generate_rsa_keypair(key_dir)
                
                # Encrypt the master key with the public key
                enc_sym_key = encrypt_symmetric_key(final_key, public_pem)
                
                # Store Encrypted Master Key and Hash
                db.conn.execute(f"INSERT INTO tape_{tape_id}_info (key, value) VALUES (?, ?)", ("enc_sym_key", enc_sym_key.hex()))
                db.conn.execute(f"INSERT INTO tape_{tape_id}_info (key, value) VALUES (?, ?)", ("sym_key_hash", sha256_hex(final_key)))
                console.print(f"[green]Random Master Key generated and encrypted with RSA.[/]")
                console.print(f"[yellow]IMPORTANT: Back up the 'private.pem' in {key_dir}![/]")
            
            else:
                console.print("[red]Invalid choice. Tape set to unencrypted.[/]")
                db.conn.execute("UPDATE tapes SET encrypted=0 WHERE tape_id=?", (tape_id,))
            
            db.conn.commit()
            
        console.print(f"Tape {tape_id} added successfully.", style="green")
        if not confirm("Add another tape?"):
            break

def select_tape_interactive():
    header("Select Tape")
    tapes = db.conn.execute("SELECT tape_id, generation, encrypted, description, used_capacity FROM tapes").fetchall()
    
    if not tapes:
        console.print("[red]No tapes found.[/]")
        return None, None, None

    # Use Rich Table for summary
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim")
    table.add_column("ID", style="cyan")
    table.add_column("Gen")
    table.add_column("Status")
    table.add_column("Capacity")
    table.add_column("Description")

    for i, (tid, gen, enc, desc, used) in enumerate(tapes, start=1):
        status = "[red]Locked[/]" if enc else "[green]Plain[/]"
        cap_gb = used / 1024**3
        table.add_row(str(i), tid, gen, status, f"{cap_gb:.2f} GB", desc)
    
    console.print(table)
    console.print("\n[dim]Options: Type number, 'scan' for barcode, or '0' to back.[/]")
    
    choice = input("> ").strip()
    
    if choice.lower() == 'scan':
        scanned_id = scan_barcode_from_camera()
        if scanned_id:
            # Find the tape in list
            for t in tapes:
                if t[0] == scanned_id:
                    header(f"Selected: {scanned_id}")
                    console.print(f"Description: {t[3]}")
                    console.print(f"Used: {t[4]/1024**3:.2f} GB")
                    if confirm("Confirm selection?"):
                        return t[0], t[1], t[2]
            console.print("[red]Scanned tape not in database.[/]")
        return None, None, None

    if not choice.isdigit() or choice == "0":
        return None, None, None

    idx = int(choice) - 1
    if 0 <= idx < len(tapes):
        t = tapes[idx]
        header(f"Selected: {t[0]}")
        console.print(f"Description: {t[3]}")
        console.print(f"Used: {t[4]/1024**3:.2f} GB")
        if confirm("Confirm selection?"):
            return t[0], t[1], t[2]
    
    return None, None, None

def unlock_tape(tape_id):
    """Authenticate and retrieve the symmetric key for a tape."""
    rows = db.conn.execute(f"SELECT key,value FROM tape_{tape_id}_info").fetchall()
    info = {k:v for k,v in rows}
    
    if "sym_key_hash" not in info:
        # Fallback if unconfigured
        return None 

    console.print(f"\n[bold red]LOCKED TAPE: {tape_id}[/]")
    print("1. Unlock with Passphrase")
    print("2. Unlock with RSA Private Key")
    choice = input("Select method: ")

    stored_hash = info["sym_key_hash"]
    key = None

    try:
        if choice == "1":
            if "kdf_salt" not in info:
                console.print("[red]This tape was not configured with a password.[/]")
                return None
            pwd = input("Passphrase: ").encode()
            salt = bytes.fromhex(info["kdf_salt"])
            key = derive_key(pwd, salt)
        elif choice == "2":
            if "enc_sym_key" not in info:
                console.print("[red]This tape was not configured with RSA.[/]")
                return None
            
            default_key_path = f"keys/{tape_id}/private.pem"
            prompt_path = default_key_path if os.path.exists(default_key_path) else ""
            path = input(f"Path to private.pem [{prompt_path}]: ").strip()
            if not path and prompt_path:
                path = prompt_path

            if not os.path.exists(path):
                console.print("[red]Key file not found.[/]")
                return None

            with open(path, "rb") as f:
                priv_pem = f.read()
            enc_key = bytes.fromhex(info["enc_sym_key"])
            key = decrypt_symmetric_key(enc_key, priv_pem)
        else:
            return None

        if sha256_hex(key) != stored_hash:
            console.print("Decryption Failed: Invalid Key/Passphrase", style="red")
            return None
        
        console.print("[green]Tape Unlocked.[/]")
        return key

    except Exception as e:
        console.print(f"[red]Error unlocking: {e}[/]")
        return None

def backup_workflow():
    tape_id, gen, is_enc = select_tape_interactive()
    if not tape_id: return

    header(f"Backup -> Tape: {tape_id}")
    
    key = unlock_tape(tape_id) if is_enc else None
    if is_enc and key is None:
        wait_for_keypress()
        return

    path_in = input("Enter paths to backup (comma separated): ")
    paths = [p.strip() for p in path_in.split(",") if os.path.exists(p.strip())]

    if not paths:
        console.print("[red]No valid paths provided.[/]")
        wait_for_keypress()
        return

    if confirm(f"Start backup to {tape_id}?"):
        try:
            run_backup_job(db, tape_id, paths, key, gen)
            log.log(f"Backup Success: {tape_id}")
        except Exception as e:
            console.print(f"Error: {e}", style="red")
            log.log(f"Backup Failed: {tape_id} - {e}")
    
    wait_for_keypress()

def restore_workflow():
    tape_id, gen, is_enc = select_tape_interactive()
    if not tape_id: return

    header(f"Restore -> Tape: {tape_id}")
    
    jobs = db.conn.execute(
        "SELECT job_id, started_at, size FROM jobs WHERE tape_id=? AND status='SUCCESS'", 
        (tape_id,)
    ).fetchall()

    if not jobs:
        console.print(f"[yellow]No valid backup jobs found on tape {tape_id}.[/]")
        wait_for_keypress()
        return

    console.print("Select a Backup Job to Restore:", style="bold cyan")
    for i, (jid, ts, sz) in enumerate(jobs, start=1):
        console.print(f"{i}. Job #{jid} | Date: {ts} | Size: {sz/1024**2:.2f} MB")
    
    job_choice = input("\nSelect job number: ").strip()
    if not job_choice.isdigit(): return
    idx = int(job_choice)-1
    if idx < 0 or idx >= len(jobs): return
    
    selected_job = jobs[idx][0]

    key = unlock_tape(tape_id) if is_enc else None
    if is_enc and key is None: return

    out_dir = input("Restore to directory (full path): ").strip()
    if not out_dir: return
    
    if not os.path.exists(out_dir):
        if confirm(f"Directory {out_dir} does not exist. Create it?"):
            os.makedirs(out_dir)
        else:
            return

    try:
        run_restore_job(db, tape_id, selected_job, out_dir, key)
    except Exception as e:
        console.print(f"Error: {e}", style="red")
    
    wait_for_keypress()

def browse_workflow():
    tape_id, gen, is_enc = select_tape_interactive()
    if not tape_id: return

    key = None
    if is_enc:
        if confirm("Tape is encrypted. Unlock to view filenames (if filenames are encrypted)?"):
            key = unlock_tape(tape_id)

    browse(db, tape_id, key)
    
    wait_for_keypress()

def verify_workflow():
    tape_id, gen, is_enc = select_tape_interactive()
    if not tape_id: return

    key = None
    if is_enc:
        key = unlock_tape(tape_id)
        if not key: return

    verify_tape_integrity(db, tape_id, key)
    wait_for_keypress()

def main():
    while True:
        clear()
        header("LTO Backup & Manage System")

        choice = choose_arrow(
            "Main Menu",
            [
                ("1", "➕ Add Tapes"),
                ("2", "💾 Backup (Write)"),
                ("3", "📥 Restore (Read)"),
                ("4", "📂 Browse Index"),
                ("5", "🔍 Verify Integrity"),
                ("6", "🛟 Disaster Recovery (Rebuild DB)"),
                ("7", "📤 Export Logs"),
                ("0", "🚪 Exit"),
            ]
        )

        if choice == "1":
            add_new_tapes()

        elif choice == "2":
            backup_workflow()

        elif choice == "3":
            restore_workflow()

        elif choice == "4":
            browse_workflow()

        elif choice == "5":
            verify_workflow()

        elif choice == "6":
            header("🛟 Disaster Recovery Mode")
            tape_id = input("Enter Tape ID to recover from: ").strip()
            if tape_id:
                recover_database_from_tape(db, tape_id)
                print_success(f"Database recovered from tape {tape_id}")
            else:
                print_error("No Tape ID provided")
            wait_for_keypress()

        elif choice == "7":
            log.export_csv("logs.csv")
            print_success("Logs exported to logs.csv")
            wait_for_keypress()

        elif choice == "0":
            if confirm("Are you sure you want to exit?"):
                print_success("Goodbye.")
                for i in range(3, 0, -1):
                    console.print(f"[dim]Closing in {i}...[/]")
                    time.sleep(1)
                break

if __name__ == "__main__":
    main()