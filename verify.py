from crypto import DecryptionReader, HashReader
from ui import console
from tape import TapeDevice
from tqdm import tqdm

def verify_tape_integrity(db, tape_id, key=None):
    jobs = db.conn.execute(
        "SELECT job_id, size, iv_hex, tag_hex, action FROM jobs WHERE tape_id=? AND status='SUCCESS'",
        (tape_id,)
    ).fetchall()

    if not jobs:
        console.print(f"[yellow]No successful jobs found on tape {tape_id}.[/]")
        return

    results = []
    for job_id, size, iv_hex, tag_hex, action in jobs:
        is_encrypted = (iv_hex is not None)
        mode_str = "AES-GCM" if is_encrypted else "SHA-256"
        console.print(f"\n[bold]Checking Job #{job_id} ({action}) - Mode: {mode_str}[/]")
        
        if is_encrypted and key is None:
            console.print("[yellow]SKIPPED: Key required for encrypted job.[/]")
            results.append((job_id, "SKIPPED"))
            continue

        raw_reader = None
        pbar = None
        
        try:
            tape = TapeDevice(tape_id)
            raw_reader = tape.get_reader(job_id, encrypted=is_encrypted)
            pbar = tqdm(total=size, unit='B', unit_scale=True, desc="Scanning")

            verifier = None
            if is_encrypted:
                iv = bytes.fromhex(iv_hex)
                tag = bytes.fromhex(tag_hex)
                verifier = DecryptionReader(raw_reader, key, iv, tag)
            else:
                verifier = HashReader(raw_reader)

            # Consume the stream to trigger verification
            while True:
                chunk = verifier.read(1024 * 1024) # 1MB chunk
                if not chunk:
                    break
                pbar.update(len(chunk))
            
            pbar.close()

            if is_encrypted:
                # AES-GCM tag is verified automatically in verifier.read() at EOF
                # If it didn't raise exception, it's valid.
                pass 
            else:
                computed_hash = verifier.get_hash()
                if tag_hex is None:
                    raise ValueError("Missing stored hash for integrity check")
                if computed_hash != tag_hex:
                    raise ValueError(
                        f"Hash Mismatch! Expected: {tag_hex[:8]}, Got: {computed_hash[:8]}"
                    )
                
            console.print(f"[green]✓ Job #{job_id} Integrity Verified.[/]")
            results.append((job_id, "PASSED"))

        except Exception as e:
            if pbar: pbar.close()
            console.print(f"[bold red]✗ Job #{job_id} FAILED: {e}[/]")
            results.append((job_id, "CORRUPTED"))
        finally:
            if raw_reader: raw_reader.close()

    _print_summary_table(results)

def _print_summary_table(results):
    console.print("\n" + "="*30)
    console.print("[bold]FINAL VERIFICATION REPORT[/]")
    for j_id, res in results:
        icon = "✅" if res == "PASSED" else "❌" if res == "CORRUPTED" else "⚠️"
        console.print(f"{icon} Job #{j_id}: {res}")
    console.print("="*30 + "\n")