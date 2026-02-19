import os
from rich.table import Table
from ui import console, header, wait_for_keypress
from crypto import decrypt_name, decrypt_symmetric_key, sha256_hex
from config_manager import cfg


# =============================================================================
# SILENT RSA UNLOCK
# =============================================================================

def auto_unlock_rsa(db, tape_id):
    """
    Attempt to silently unlock an RSA-encrypted tape.

    Looks for the private key at keys/{tape_id}/private.pem (the standard
    storage path used when a tape is registered with RSA encryption).

    Returns the plaintext AES symmetric key bytes, or None if the key file
    is missing, the tape is not RSA-encrypted, or decryption fails.
    """
    key_dir  = cfg.get("key_storage_path", "keys")
    key_path = os.path.join(key_dir, tape_id, "private.pem")

    if not os.path.exists(key_path):
        return None

    try:
        rows = db.conn.execute(
            f"SELECT key, value FROM tape_{tape_id}_info"
        ).fetchall()
        info = {k: v for k, v in rows}

        if "enc_sym_key" not in info or "sym_key_hash" not in info:
            return None

        with open(key_path, "rb") as f:
            priv_pem = f.read()

        enc_key = bytes.fromhex(info["enc_sym_key"])
        sym_key = decrypt_symmetric_key(enc_key, priv_pem)

        # Verify the decrypted key matches the stored hash
        if sha256_hex(sym_key) == info["sym_key_hash"]:
            return sym_key
    except Exception:
        pass

    return None


# =============================================================================
# SEARCH LOGIC
# =============================================================================

def search_files(db, keyword):
    """
    Search across all tapes for files/directories whose names contain keyword
    (case-insensitive).

    Encrypted tapes are automatically unlocked via their local RSA private key.
    If the key file is absent the filenames on that tape are reported as locked
    and excluded from matching.

    Returns a list of dicts with keys:
        tape_id, tape_description, job_id,
        display_name, is_dir, size, locked
    """
    keyword_lower = keyword.lower()
    tapes = db.conn.execute(
        "SELECT tape_id, encrypted, description FROM tapes"
    ).fetchall()

    results = []

    for tape_id, is_encrypted, tape_desc in tapes:
        key = None
        if is_encrypted:
            key = auto_unlock_rsa(db, tape_id)

        try:
            rows = db.conn.execute(
                f"SELECT name, is_dir, size, job_id FROM tape_{tape_id}"
            ).fetchall()
        except Exception:
            continue

        for name_stored, is_dir, size, job_id in rows:
            display_name = name_stored
            locked = False

            if is_encrypted:
                if key:
                    try:
                        display_name = decrypt_name(name_stored, key)
                    except Exception:
                        locked = True
                else:
                    locked = True

            # Only include rows whose decrypted name matches the keyword
            if not locked and keyword_lower in display_name.lower():
                results.append({
                    "tape_id":          tape_id,
                    "tape_description": tape_desc or "",
                    "job_id":           job_id,
                    "display_name":     display_name,
                    "is_dir":           bool(is_dir),
                    "size":             size or 0,
                    "locked":           False,
                })

    return results


# =============================================================================
# INTERACTIVE WORKFLOW
# =============================================================================

def search_workflow(db):
    """Present an interactive cross-tape file search to the user."""
    header("🔎 Search Files Across All Tapes")

    keyword = input("Enter search keyword: ").strip()
    if not keyword:
        return

    console.print(f"\n[dim]Searching for '{keyword}'…[/]")
    results = search_files(db, keyword)

    if not results:
        console.print("[yellow]No matching files found.[/]")
        wait_for_keypress()
        return

    # Sort by tape ID then filename for readability
    results.sort(key=lambda r: (r["tape_id"], r["display_name"].lower()))

    table = Table(show_header=True, header_style="bold magenta", show_lines=False)
    table.add_column("Tape",      style="cyan",    no_wrap=True)
    table.add_column("Job #",     style="dim",     no_wrap=True)
    table.add_column("Type",      no_wrap=True)
    table.add_column("File Name")
    table.add_column("Size",      justify="right")

    for r in results:
        icon = "📁" if r["is_dir"] else "📄"
        if not r["is_dir"] and r["size"]:
            size_str = (
                f"{r['size'] / 1024 ** 2:.2f} MB"
                if r["size"] > 1024 * 1024
                else f"{r['size'] / 1024:.1f} KB"
            )
        else:
            size_str = "—"

        table.add_row(
            r["tape_id"],
            str(r["job_id"]),
            icon,
            r["display_name"],
            size_str,
        )

    console.print(table)
    console.print(f"\n[dim]{len(results)} result(s) found.[/]")
    wait_for_keypress()
