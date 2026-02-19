import time
import os
import secrets

from ui import (
    header, confirm, console, wait_for_keypress,
    clear, print_error, print_success, choose_arrow,
)
from db import Database
from backup import run_backup_job
from restore import run_restore_job
from browse import browse
from logger import Logger
from config_manager import cfg
from scanner import scan_barcode_from_camera
from rich.table import Table
from verify import verify_tape_integrity
from recovery import recover_database_from_tape
from crypto import (
    derive_key, generate_rsa_keypair,
    encrypt_symmetric_key, decrypt_symmetric_key, sha256_hex,
)
from labels import manage_labels_workflow
from search import search_workflow
from report import health_report_workflow

db  = Database()
log = Logger()


# =============================================================================
# SHARED HELPERS
# =============================================================================

def get_tape_id_input(prompt="Enter Tape ID"):
    """Accept a tape ID typed directly or scanned from the camera."""
    console.print(f"\n{prompt}")
    console.print("[dim]Type ID directly or 'scan' to use camera.[/]")
    val = input("> ").strip()
    if val.lower() == "scan":
        code = scan_barcode_from_camera()
        if code:
            console.print(f"Scanned: [bold green]{code}[/]")
            if confirm(f"Use ID '{code}'?"):
                return code
        return None
    return val if val else None


def select_tape_interactive(filter_label=None):
    """
    Show a tape selection table and return (tape_id, generation, is_encrypted).
    Optional filter_label restricts the list to tapes that carry that label.
    """
    header("Select Tape" + (f" — Label: {filter_label}" if filter_label else ""))

    # Join with label map so we can show labels in the table and optionally filter
    query = """
        SELECT t.tape_id, t.generation, t.encrypted, t.description, t.used_capacity,
               GROUP_CONCAT(m.label_name, ', ') AS labels
        FROM tapes t
        LEFT JOIN tape_label_map m ON t.tape_id = m.tape_id
        {where}
        GROUP BY t.tape_id
        ORDER BY t.tape_id
    """
    if filter_label:
        tapes = db.conn.execute(
            query.format(where="WHERE t.tape_id IN "
                               "(SELECT tape_id FROM tape_label_map WHERE label_name=?)"),
            (filter_label,)
        ).fetchall()
    else:
        tapes = db.conn.execute(query.format(where="")).fetchall()

    if not tapes:
        console.print("[red]No tapes found.[/]")
        return None, None, None

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#",           style="dim")
    table.add_column("ID",          style="cyan")
    table.add_column("Gen")
    table.add_column("Status")
    table.add_column("Used",        justify="right")
    table.add_column("Labels")
    table.add_column("Description")

    for i, (tid, gen, enc, desc, used, labels_str) in enumerate(tapes, start=1):
        status     = "[red]Locked[/]" if enc else "[green]Plain[/]"
        labels_disp = labels_str or "—"
        table.add_row(
            str(i), tid, gen, status,
            f"{used / 1024**3:.2f} GB",
            labels_disp,
            desc or "",
        )

    console.print(table)
    console.print("\n[dim]Type number, 'scan' for barcode, or '0' to go back.[/]")
    choice = input("> ").strip()

    if choice.lower() == "scan":
        scanned_id = scan_barcode_from_camera()
        if scanned_id:
            for t in tapes:
                if t[0] == scanned_id:
                    console.print(f"Description: {t[3]}")
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
        console.print(f"Used: {t[4] / 1024**3:.2f} GB")
        if confirm("Confirm selection?"):
            return t[0], t[1], t[2]

    return None, None, None


def unlock_tape(tape_id):
    """
    Prompt the user to authenticate and retrieve the AES symmetric key for a
    tape.  Returns the key bytes on success, or None on failure/cancel.
    """
    rows = db.conn.execute(
        f"SELECT key, value FROM tape_{tape_id}_info"
    ).fetchall()
    info = {k: v for k, v in rows}

    if "sym_key_hash" not in info:
        return None  # Tape has no encryption configured

    console.print(f"\n[bold red]LOCKED TAPE: {tape_id}[/]")
    print("1. Unlock with Passphrase")
    print("2. Unlock with RSA Private Key")
    choice = input("Select method: ").strip()

    stored_hash = info["sym_key_hash"]
    key = None

    try:
        if choice == "1":
            if "kdf_salt" not in info:
                console.print("[red]This tape was not configured with a password.[/]")
                return None
            pwd  = input("Passphrase: ").encode()
            salt = bytes.fromhex(info["kdf_salt"])
            key  = derive_key(pwd, salt)

        elif choice == "2":
            if "enc_sym_key" not in info:
                console.print("[red]This tape was not configured with RSA.[/]")
                return None
            default_path = f"keys/{tape_id}/private.pem"
            prompt_path  = default_path if os.path.exists(default_path) else ""
            path = input(f"Path to private.pem [{prompt_path}]: ").strip()
            if not path and prompt_path:
                path = prompt_path
            if not os.path.exists(path):
                console.print("[red]Key file not found.[/]")
                return None
            with open(path, "rb") as f:
                priv_pem = f.read()
            enc_key = bytes.fromhex(info["enc_sym_key"])
            key     = decrypt_symmetric_key(enc_key, priv_pem)
        else:
            return None

        if sha256_hex(key) != stored_hash:
            console.print("[red]Decryption failed: invalid key/passphrase.[/]")
            return None

        console.print("[green]Tape unlocked.[/]")
        return key

    except Exception as e:
        console.print(f"[red]Error unlocking: {e}[/]")
        return None


# =============================================================================
# TAPE MANAGEMENT
# =============================================================================

def add_new_tapes():
    header("Add New Tapes")

    while True:
        tape_id = get_tape_id_input("Enter Tape ID to Add")
        if not tape_id:
            break

        existing = db.conn.execute(
            "SELECT 1 FROM tapes WHERE tape_id=?", (tape_id,)
        ).fetchone()
        if existing:
            console.print(f"[red]Tape {tape_id} already exists![/]")
            continue

        description = input("Enter Description/Label: ").strip()
        gen = input("Generation (L5/L6/L7/L8/L9/L10): ").strip().upper()
        if gen not in cfg.config["generations"]:
            console.print("[red]Invalid generation.[/]")
            continue

        is_enc = confirm(f"Enable encryption for {tape_id}?")
        db.add_tape(tape_id, gen, description, is_enc)

        if is_enc:
            console.print("\n[bold cyan]Encryption Setup[/]")
            print("1. Password Derived Key")
            print("2. RSA Key Pair (saves key files to disk)")
            choice = input("Select method (1/2): ").strip()

            final_key = None

            if choice == "1":
                pwd = input("Set Passphrase: ").strip().encode()
                if not pwd:
                    console.print("[red]Password cannot be empty. Tape set to plain.[/]")
                    db.conn.execute(
                        "UPDATE tapes SET encrypted=0 WHERE tape_id=?", (tape_id,)
                    )
                    continue
                salt      = os.urandom(16)
                final_key = derive_key(pwd, salt)
                db.conn.execute(
                    f"INSERT INTO tape_{tape_id}_info (key, value) VALUES (?, ?)",
                    ("kdf_salt", salt.hex())
                )
                db.conn.execute(
                    f"INSERT INTO tape_{tape_id}_info (key, value) VALUES (?, ?)",
                    ("sym_key_hash", sha256_hex(final_key))
                )
                console.print("[green]Key derived from password and configured.[/]")

            elif choice == "2":
                final_key = secrets.token_bytes(32)
                key_dir   = f"keys/{tape_id}"
                console.print(f"Generating RSA keys in {key_dir}…")
                public_pem  = generate_rsa_keypair(key_dir)
                enc_sym_key = encrypt_symmetric_key(final_key, public_pem)
                db.conn.execute(
                    f"INSERT INTO tape_{tape_id}_info (key, value) VALUES (?, ?)",
                    ("enc_sym_key", enc_sym_key.hex())
                )
                db.conn.execute(
                    f"INSERT INTO tape_{tape_id}_info (key, value) VALUES (?, ?)",
                    ("sym_key_hash", sha256_hex(final_key))
                )
                console.print("[green]RSA key pair generated.[/]")
                console.print(f"[yellow]IMPORTANT: Back up 'private.pem' in {key_dir}![/]")
            else:
                console.print("[red]Invalid choice. Tape set to unencrypted.[/]")
                db.conn.execute(
                    "UPDATE tapes SET encrypted=0 WHERE tape_id=?", (tape_id,)
                )

            db.conn.commit()

        print_success(f"Tape {tape_id} added.")
        if not confirm("Add another tape?"):
            break


# =============================================================================
# BACKUP
# =============================================================================

def backup_workflow():
    tape_id, gen, is_enc = select_tape_interactive()
    if not tape_id:
        return

    header(f"Backup → Tape: {tape_id}")

    key = unlock_tape(tape_id) if is_enc else None
    if is_enc and key is None:
        wait_for_keypress()
        return

    path_in = input("Enter paths to backup (comma separated): ")
    paths   = [p.strip() for p in path_in.split(",") if os.path.exists(p.strip())]
    if not paths:
        print_error("No valid paths provided.")
        wait_for_keypress()
        return

    # Offer incremental only when a previous successful backup exists
    incremental = False
    has_previous = db.conn.execute(
        "SELECT 1 FROM jobs WHERE tape_id=? AND status='SUCCESS' AND action='BACKUP'",
        (tape_id,)
    ).fetchone()

    if has_previous:
        btype_choice = choose_arrow(
            "Backup Type",
            [
                ("F", "📦 Full Backup  — archive all files"),
                ("I", "📋 Incremental — archive only new/changed files"),
            ]
        )
        incremental = (btype_choice == "I")

    try:
        if incremental:
            # run_backup_job handles its own confirmation (shows diff summary)
            result = run_backup_job(db, tape_id, paths, key, gen, incremental=True)
            if result is None:
                console.print("[dim]Incremental backup cancelled or no changes.[/]")
            else:
                log.log(f"Backup Success (incremental): {tape_id} Job#{result}")
                print_success(f"Incremental backup complete!  Job #{result}")
        else:
            if confirm(f"Start full backup to {tape_id}?"):
                result = run_backup_job(db, tape_id, paths, key, gen, incremental=False)
                log.log(f"Backup Success (full): {tape_id} Job#{result}")
                print_success(f"Full backup complete!  Job #{result}")

    except Exception as e:
        print_error(f"Backup failed: {e}")
        log.log(f"Backup Failed: {tape_id} — {e}", level="ERROR")

    wait_for_keypress()


# =============================================================================
# RESTORE
# =============================================================================

def restore_workflow():
    tape_id, gen, is_enc = select_tape_interactive()
    if not tape_id:
        return

    header(f"Restore ← Tape: {tape_id}")

    jobs = db.conn.execute(
        "SELECT job_id, started_at, backup_type, size "
        "FROM jobs WHERE tape_id=? AND status='SUCCESS' AND action='BACKUP'",
        (tape_id,)
    ).fetchall()
    if not jobs:
        console.print(f"[yellow]No successful backup jobs on tape {tape_id}.[/]")
        wait_for_keypress()
        return

    console.print("[bold cyan]Select a job to restore:[/]")
    for i, (jid, ts, btype, sz) in enumerate(jobs, start=1):
        type_tag = f" [{btype}]" if btype and btype != "FULL" else ""
        console.print(
            f"  {i}. Job #{jid}{type_tag}  |  {ts}  |  {sz / 1024**2:.2f} MB"
        )

    raw = input("\nJob number: ").strip()
    if not raw.isdigit():
        return
    idx = int(raw) - 1
    if not (0 <= idx < len(jobs)):
        return
    selected_job = jobs[idx][0]

    key = unlock_tape(tape_id) if is_enc else None
    if is_enc and key is None:
        return

    out_dir = input("Restore to directory (full path): ").strip()
    if not out_dir:
        return
    if not os.path.exists(out_dir):
        if confirm(f"'{out_dir}' does not exist. Create it?"):
            os.makedirs(out_dir)
        else:
            return

    try:
        run_restore_job(db, tape_id, selected_job, out_dir, key)
    except Exception as e:
        print_error(f"Restore failed: {e}")

    wait_for_keypress()


# =============================================================================
# BROWSE / VERIFY
# =============================================================================

def browse_workflow():
    tape_id, _, is_enc = select_tape_interactive()
    if not tape_id:
        return

    key = None
    if is_enc and confirm("Unlock tape to view decrypted filenames?"):
        key = unlock_tape(tape_id)

    browse(db, tape_id, key)
    wait_for_keypress()


def verify_workflow():
    tape_id, _, is_enc = select_tape_interactive()
    if not tape_id:
        return

    key = None
    if is_enc:
        key = unlock_tape(tape_id)
        if not key:
            return

    verify_tape_integrity(db, tape_id, key)
    wait_for_keypress()


# =============================================================================
# MAIN MENU
# =============================================================================

def main():
    while True:
        clear()
        header("LTO Backup & Manage System")

        choice = choose_arrow(
            "Main Menu",
            [
                ("1",  "➕  Add Tapes"),
                ("2",  "💾  Backup  (Write)"),
                ("3",  "📥  Restore (Read)"),
                ("4",  "📂  Browse Index"),
                ("5",  "🔍  Verify Integrity"),
                ("6",  "🏷️  Manage Labels"),
                ("7",  "🔎  Search Files"),
                ("8",  "📋  Health Report"),
                ("9",  "🛟  Disaster Recovery"),
                ("10", "📤  Export Logs"),
                ("0",  "🚪  Exit"),
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
            manage_labels_workflow(db)

        elif choice == "7":
            search_workflow(db)

        elif choice == "8":
            health_report_workflow(db)

        elif choice == "9":
            header("🛟 Disaster Recovery Mode")
            tape_id = input("Enter Tape ID to recover from: ").strip()
            if tape_id:
                recover_database_from_tape(db, tape_id)
                print_success(f"Database recovered from tape {tape_id}")
            else:
                print_error("No Tape ID provided")
            wait_for_keypress()

        elif choice == "10":
            log.export_csv("logs.csv")
            print_success("Logs exported to logs.csv")
            wait_for_keypress()

        elif choice == "0":
            if confirm("Are you sure you want to exit?"):
                print_success("Goodbye.")
                for i in range(3, 0, -1):
                    console.print(f"[dim]Closing in {i}…[/]")
                    time.sleep(1)
                break


if __name__ == "__main__":
    main()
