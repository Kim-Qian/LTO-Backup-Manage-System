from rich.console import Console
from rich.tree import Tree
from crypto import decrypt_name
from config_manager import cfg

console = Console()

def browse(db, tape_id, key=None):
    # ... Fetch Metadata ...
    tape_row = db.conn.execute(
        "SELECT generation, used_capacity, encrypted, description FROM tapes WHERE tape_id=?",
        (tape_id,)
    ).fetchone()

    if not tape_row:
        console.print(f"[red]Tape {tape_id} not found.[/]")
        return

    generation, used_bytes, is_encrypted, desc = tape_row
    gen_config = cfg.get_generation_info(generation)
    max_cap = gen_config["capacity"]

    # Header with Description
    enc_status = "[red]Encrypted[/]" if is_encrypted else "[green]Plain[/]"
    console.print(f"\n[bold cyan]Tape Viewer: {tape_id}[/]")
    console.print(f"Info: {desc}")
    console.print(f"Type: {gen_config['name']} | Status: {enc_status}")
    console.print(f"Usage: {used_bytes / 1024**3:.2f} GB / {max_cap / 1024**3:.2f} GB")

    # ... Build Tree ...
    console.print("\n[bold yellow]File Index:[/]")
    rows = db.conn.execute(
        f"SELECT id, parent_id, name, is_dir, size FROM tape_{tape_id} ORDER BY id"
    ).fetchall()

    if not rows:
        console.print("[italic dim]Tape is empty.[/]")
    else:
        tree = Tree(f":floppy_disk: [bold white]{tape_id}[/]")
        node_map = {None: tree}

        for node_id, parent_id, name_stored, is_dir, size in rows:
            display_name = name_stored
            # Decrypt name logic (same as before)
            if is_encrypted and key:
                try:
                    display_name = decrypt_name(name_stored, key)
                except:
                    display_name = f"[Locked] {name_stored}"
            elif is_encrypted and not key:
                display_name = f"[Locked] {name_stored}"

            # NEW: Config-based Icon
            icon = cfg.get_file_icon(bool(is_dir), display_name)

            if len(display_name) > 50:
                display_name = display_name[:50] + "..."

            if is_dir:
                label = f"{icon} [bold blue]{display_name}/[/]"
            else:
                size_str = f"{size/1024/1024:.2f} MB" if size > 1024*1024 else f"{size/1024:.1f} KB"
                label = f"{icon} [white]{display_name}[/] [dim]({size_str})[/]"

            parent_node = node_map.get(parent_id, tree)
            node_map[node_id] = parent_node.add(label)

        console.print(tree)
    
    # Display Job History
    console.print("\n[bold magenta]Operation History:[/]")
    jobs = db.conn.execute(
        "SELECT job_id, action, status, started_at, size FROM jobs WHERE tape_id=? ORDER BY job_id DESC",
        (tape_id,)
    ).fetchall()

    if not jobs:
        console.print("[dim]No jobs recorded.[/]")
    
    for j_id, action, status, ts, size in jobs:
        style = "green" if status == "SUCCESS" else "red"
        sz_str = f"{size/1024/1024:.2f} MB" if size else "0 MB"
        console.print(f"Job #{j_id} [{ts}] : {action} -> [{style}]{status}[/] ({sz_str})")