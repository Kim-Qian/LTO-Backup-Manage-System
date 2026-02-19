from crypto import DecryptionReader, HashReader
from ui import console
from tape import TapeDevice
from tqdm import tqdm


def verify_tape_integrity(db, tape_id, key=None):
    # Query only BACKUP jobs so the VERIFY job we're about to create doesn't
    # appear in the list (its status is RUNNING during the check).
    jobs = db.conn.execute(
        "SELECT job_id, size, iv_hex, tag_hex, action FROM jobs "
        "WHERE tape_id=? AND status='SUCCESS' AND action='BACKUP'",
        (tape_id,)
    ).fetchall()

    if not jobs:
        console.print(f"[yellow]No successful backup jobs found on tape {tape_id}.[/]")
        return

    # Create a VERIFY job so the health report can track when verification was run.
    verify_job_id = db.new_job(tape_id, "VERIFY", backup_type="N/A")

    results = []
    for job_id, size, iv_hex, tag_hex, action in jobs:
        is_encrypted = (iv_hex is not None)
        mode_str = "AES-GCM" if is_encrypted else "SHA-256"
        console.print(f"\n[bold]Checking Job #{job_id} ({action}) — Mode: {mode_str}[/]")

        if is_encrypted and key is None:
            console.print("[yellow]SKIPPED: Key required for encrypted job.[/]")
            results.append((job_id, "SKIPPED"))
            continue

        raw_reader = None
        pbar = None

        try:
            tape = TapeDevice(tape_id)
            raw_reader = tape.get_reader(job_id, encrypted=is_encrypted)
            pbar = tqdm(total=size, unit="B", unit_scale=True, desc="Scanning")

            if is_encrypted:
                iv  = bytes.fromhex(iv_hex)
                tag = bytes.fromhex(tag_hex)
                verifier = DecryptionReader(raw_reader, key, iv, tag)
            else:
                verifier = HashReader(raw_reader)

            # Consume stream to trigger integrity verification
            while True:
                chunk = verifier.read(1024 * 1024)  # 1 MB chunks
                if not chunk:
                    break
                pbar.update(len(chunk))

            pbar.close()

            if not is_encrypted:
                computed_hash = verifier.get_hash()
                if tag_hex is None:
                    raise ValueError("Missing stored hash for integrity check")
                if computed_hash != tag_hex:
                    raise ValueError(
                        f"Hash mismatch!  "
                        f"Expected: {tag_hex[:8]}…  Got: {computed_hash[:8]}…"
                    )

            console.print(f"[green]✓ Job #{job_id} integrity verified.[/]")
            results.append((job_id, "PASSED"))

        except Exception as e:
            if pbar:
                pbar.close()
            console.print(f"[bold red]✗ Job #{job_id} FAILED: {e}[/]")
            results.append((job_id, "CORRUPTED"))
        finally:
            if raw_reader:
                raw_reader.close()

    # Determine overall outcome and finalise the VERIFY job record.
    statuses = [r for _, r in results]
    if "CORRUPTED" in statuses:
        overall = "FAILED"
    elif all(s == "PASSED" for s in statuses):
        overall = "SUCCESS"
    else:
        overall = "PARTIAL"  # Mix of PASSED and SKIPPED

    db.finish_job(verify_job_id, overall)

    _print_summary_table(results)


def _print_summary_table(results):
    console.print("\n" + "=" * 30)
    console.print("[bold]FINAL VERIFICATION REPORT[/]")
    for j_id, res in results:
        icon = "✅" if res == "PASSED" else "❌" if res == "CORRUPTED" else "⚠️"
        console.print(f"{icon}  Job #{j_id}: {res}")
    console.print("=" * 30 + "\n")
