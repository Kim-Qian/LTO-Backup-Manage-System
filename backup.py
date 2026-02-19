import tarfile
import os
import json
from collections import namedtuple
from datetime import datetime, timezone
import hashlib
from tqdm import tqdm
from crypto import EncryptionWriter, encrypt_name
from tape import TapeDevice
from config_manager import cfg
from ui import console, confirm

# Represents one file/directory node held in memory before the DB commit.
# Parent relationships use list indices rather than DB row ids so that nothing
# touches the database until the archive has been written successfully.
NodeRecord = namedtuple("NodeRecord", ["parent_idx", "name_stored", "is_dir", "size", "mtime"])

# Extra headroom applied to the raw source size during the capacity pre-check.
# Covers tar header blocks, block-boundary padding, and AES-GCM overhead.
CAPACITY_CHECK_OVERHEAD = 1.02


class ProgressWriter:
    """Wraps a file object to update a tqdm progress bar and optionally hash the stream."""
    def __init__(self, wrapped_file, progress_bar, calc_hash=True):
        self._file = wrapped_file
        self._bar = progress_bar
        self.sha256 = hashlib.sha256() if calc_hash else None

    def write(self, data):
        self._file.write(data)
        self._bar.update(len(data))
        if self.sha256:
            self.sha256.update(data)

    def flush(self):
        self._file.flush()

    def tell(self):
        return self._file.tell()


# =============================================================================
# DIRECTORY SCANNING
# =============================================================================

def _scan_directory(paths):
    """
    Recursively walk all paths and return a flat list of entries.

    Each entry is a tuple:
        (abs_path, arcname, is_dir, size_bytes, mtime_float)

    arcname is the path relative to the backup root, always using forward
    slashes (e.g. "mydir/sub/file.txt"), suitable for use as a tar member name.
    mtime is 0.0 for directory entries.
    """
    items = []

    def _walk(path, arcname):
        is_dir = os.path.isdir(path)
        size  = os.path.getsize(path) if not is_dir else 0
        mtime = os.path.getmtime(path) if not is_dir else 0.0
        items.append((path, arcname, is_dir, size, mtime))

        if is_dir:
            try:
                for child in sorted(os.listdir(path)):
                    _walk(os.path.join(path, child), arcname + "/" + child)
            except PermissionError:
                print(f"Warning: Permission denied accessing {path}")

    for p in paths:
        _walk(p, os.path.basename(p))

    return items


# =============================================================================
# INCREMENTAL HELPERS
# =============================================================================

def _get_previous_snapshot(tape, job_id):
    """
    Load the manifest JSON for job_id from the tape and return a snapshot dict:
        { arcname -> {"size": int, "mtime": float} }

    Understands both the old manifest format (files have only "name") and the
    new format (files have "rel_path", "mtime").  Returns None on any failure.
    """
    manifest_path = tape.mount_point / f"job_{job_id}.json"
    if not manifest_path.exists():
        return None
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        snapshot = {}
        for entry in meta.get("files", []):
            key = entry.get("rel_path") or entry.get("name", "")
            snapshot[key] = {
                "size":  entry.get("size", 0),
                "mtime": entry.get("mtime", 0.0),
            }
        return snapshot
    except Exception:
        return None


def _filter_changed(all_items, snapshot):
    """
    Compare all_items against a previous snapshot and return the subset of
    items that should be written to the incremental archive.

    Rules:
      - Directories are always included (needed for tar to reconstruct structure).
      - A file is included if it is new (not in snapshot) or its size or mtime
        has changed (1-second tolerance for filesystem mtime precision).

    Returns:
        changed_items  – list of items for the tar archive
        stats          – {"new": int, "modified": int, "unchanged": int}
    """
    changed = []
    stats = {"new": 0, "modified": 0, "unchanged": 0}

    for entry in all_items:
        _, arcname, is_dir, size, mtime = entry
        if is_dir:
            changed.append(entry)
            continue

        prev = snapshot.get(arcname)
        if prev is None:
            changed.append(entry)
            stats["new"] += 1
        elif size != prev["size"] or abs(mtime - prev.get("mtime", 0.0)) > 1.0:
            changed.append(entry)
            stats["modified"] += 1
        else:
            stats["unchanged"] += 1

    return changed, stats


# =============================================================================
# NODE BUILDING
# =============================================================================

def _build_nodes_and_manifest(all_items, items_for_archive, key):
    """
    Build the in-memory structures needed for the DB commit and the on-tape manifest.

    all_items        – complete directory scan; used for the manifest so it always
                       captures the full current state (previous unchanged files are
                       still referenced for the next incremental comparison).
    items_for_archive – only the items that will actually be written to the tar
                        archive (equals all_items for a full backup).
    key              – AES encryption key for filename encryption; None for plain.

    Returns:
        nodes          (list[NodeRecord]) – ready for _commit_file_index
        manifest_files (list[dict])       – full current-state file list for JSON
    """
    # ---- Full-state manifest (used as the snapshot for the next incremental) ----
    manifest_files = []
    for _, arcname, is_dir, size, mtime in all_items:
        manifest_files.append({
            "rel_path": arcname,
            "name":     os.path.basename(arcname),
            "is_dir":   is_dir,
            "size":     size,
            "mtime":    mtime,
        })

    # ---- DB nodes (only items going into this archive) ----
    # Sort by arcname so parent directories always appear before their children.
    arcname_to_idx = {}
    nodes = []

    for abs_path, arcname, is_dir, size, mtime in sorted(items_for_archive, key=lambda x: x[1]):
        name            = os.path.basename(arcname)
        parent_arcname  = os.path.dirname(arcname) or None
        parent_idx      = arcname_to_idx.get(parent_arcname)

        name_stored = encrypt_name(name, key) if key else name
        idx = len(nodes)
        nodes.append(NodeRecord(parent_idx, name_stored, int(is_dir), size, mtime))
        arcname_to_idx[arcname] = idx

    return nodes, manifest_files


# =============================================================================
# TAR SIZE ESTIMATION
# =============================================================================

def _estimated_tar_size(items):
    """
    Estimate how many bytes the tar archive for the given items will occupy.

    POSIX tar format:
      - Each entry (file or directory) has a 512-byte header block.
      - File content is padded to the next 512-byte block boundary.
      - The archive ends with two 512-byte zero (end-of-archive) blocks.
    """
    total       = 0
    entry_count = 0

    for _, _, is_dir, size, _ in items:
        entry_count += 1
        if not is_dir:
            total += size + (512 - size % 512) % 512  # content + block alignment

    total += entry_count * 512  # header blocks
    total += 1024               # end-of-archive marker
    return total


# =============================================================================
# DB COMMIT (deferred until archive succeeds)
# =============================================================================

def _commit_file_index(db, tape_id, job_id, nodes):
    """
    Bulk-insert all NodeRecords into the database in a single transaction.
    Converts list-index parent references into real DB row ids.
    Called only after the tape archive has been written successfully.
    """
    id_map = {}  # list index -> DB row id
    db.conn.execute("BEGIN")
    for idx, node in enumerate(nodes):
        parent_db_id = id_map.get(node.parent_idx)  # None for root entries
        db_id = db.insert_node(
            tape_id, parent_db_id, node.name_stored,
            node.is_dir, node.size, job_id, node.mtime
        )
        id_map[idx] = db_id
    db.conn.commit()


# =============================================================================
# MANIFEST PERSISTENCE
# =============================================================================

def save_job_metadata_to_tape(tape, job_id, meta_dict):
    """Write a lightweight JSON manifest to the tape alongside the archive."""
    json_path = tape.mount_point / f"job_{job_id}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta_dict, f, indent=2, ensure_ascii=False)
    return json_path


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def run_backup_job(db, tape_id, paths, key=None, generation="L5", incremental=False):
    """
    Execute a backup job writing to tape_id.

    Parameters
    ----------
    db          : Database instance
    tape_id     : target tape identifier
    paths       : list of source paths (files or directories)
    key         : AES-256 symmetric key bytes for encryption; None = plain
    generation  : LTO generation code (L5 … L10) for capacity lookup
    incremental : when True, only new/changed files are archived; the user is
                  shown a diff summary and asked to confirm before proceeding.
                  If no previous backup exists the job falls back to FULL.

    Returns the new job_id, or None if the user cancelled an incremental run.
    """
    tape = TapeDevice(tape_id)

    # --- 1. Scan source files ---------------------------------------------------
    print("Scanning source files...")
    all_items = _scan_directory(paths)

    # --- 2. Incremental: diff against previous snapshot ------------------------
    items_for_archive = all_items
    backup_type = "FULL"

    if incremental:
        prev_row = db.conn.execute(
            "SELECT job_id FROM jobs "
            "WHERE tape_id=? AND status='SUCCESS' AND action='BACKUP' "
            "ORDER BY job_id DESC LIMIT 1",
            (tape_id,)
        ).fetchone()

        if prev_row is None:
            console.print("[yellow]No previous backup found — performing full backup.[/]")
        else:
            snapshot = _get_previous_snapshot(tape, prev_row[0])
            if snapshot is None:
                console.print("[yellow]Previous manifest unreadable — performing full backup.[/]")
            else:
                changed, stats = _filter_changed(all_items, snapshot)
                file_delta = stats["new"] + stats["modified"]

                console.print("\n[bold]Incremental Analysis[/]")
                console.print(f"  [green]New files    :[/]  {stats['new']}")
                console.print(f"  [yellow]Modified files:[/]  {stats['modified']}")
                console.print(f"  [dim]Unchanged    :[/]  {stats['unchanged']}")

                if file_delta == 0:
                    console.print("\n[green]No changes detected — nothing to backup.[/]")
                    return None

                if not confirm(f"Proceed with incremental backup of {file_delta} file(s)?"):
                    return None

                items_for_archive = changed
                backup_type = "INCREMENTAL"

    # --- 3. Capacity pre-check --------------------------------------------------
    write_size_estimate = int(
        sum(s for _, _, is_dir, s, _ in items_for_archive if not is_dir)
        * CAPACITY_CHECK_OVERHEAD
    )
    used    = db.get_used_capacity(tape_id)
    gen_info = cfg.get_generation_info(generation)
    max_cap  = gen_info.get("capacity", 2500 * 10**9)

    if used + write_size_estimate > max_cap:
        raise Exception(
            f"Insufficient space.  "
            f"Estimated write: {write_size_estimate / 1e9:.2f} GB, "
            f"Available: {(max_cap - used) / 1e9:.2f} GB"
        )

    # --- 4. Crypto setup --------------------------------------------------------
    iv     = os.urandom(12) if key else None  # AES-GCM recommends 12-byte IV
    iv_hex = iv.hex() if iv else None

    # --- 5. Create job record (RUNNING) ----------------------------------------
    job_id = db.new_job(tape_id, "BACKUP", iv_hex, backup_type=backup_type)

    # --- 6. Build nodes and manifest in memory ---------------------------------
    print("Indexing files...")
    nodes, manifest_files = _build_nodes_and_manifest(all_items, items_for_archive, key)

    job_manifest = {
        "job_id":      job_id,
        "backup_type": backup_type,
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "encrypted":   bool(key),
        "crypto": {
            "iv_hex":  iv_hex,
            "tag_hex": None,  # filled in after archive is written
        },
        "files": manifest_files,
    }

    # --- 7. Stream archive to tape ---------------------------------------------
    tar_estimated = _estimated_tar_size(items_for_archive)
    tag_hex = None

    try:
        with tape.get_writer(job_id, encrypted=(key is not None)) as raw_tape_file:
            pbar = tqdm(total=tar_estimated, unit="B", unit_scale=True, desc="Backup & Sync")
            progress_writer = ProgressWriter(raw_tape_file, pbar, calc_hash=(key is None))

            enc_writer   = None
            final_writer = progress_writer
            if key:
                enc_writer   = EncryptionWriter(progress_writer, key, iv)
                final_writer = enc_writer

            with tarfile.open(fileobj=final_writer, mode="w|") as tar:
                for abs_path, arcname, _, _, _ in items_for_archive:
                    # recursive=False because we already have every item in the list
                    tar.add(abs_path, arcname=arcname, recursive=False)

            # Finalise crypto and capture authentication tag
            if enc_writer:
                tag_hex = enc_writer.finalize().hex()
                job_manifest["crypto"]["tag_hex"] = tag_hex
            elif progress_writer.sha256:
                tag_hex = progress_writer.sha256.hexdigest()
                job_manifest["crypto"]["tag_hex"] = tag_hex

            pbar.close()

        # --- 8. Commit index only after archive succeeded ----------------------
        # If the archive step raised, this block is skipped and the DB stays clean.
        _commit_file_index(db, tape_id, job_id, nodes)

        # --- 9. Finalise job record and write manifest to tape -----------------
        written_size = os.path.getsize(
            tape.get_job_filename(job_id, encrypted=(key is not None))
        )
        job_manifest["total_size"] = written_size

        json_path = save_job_metadata_to_tape(tape, job_id, job_manifest)
        db.update_used_capacity(tape_id, written_size)
        db.finish_job(job_id, "SUCCESS", size=written_size, tag_hex=tag_hex)

        print(f"Metadata saved to {json_path}")
        return job_id

    except Exception as e:
        db.finish_job(job_id, "FAILED")
        raise e
