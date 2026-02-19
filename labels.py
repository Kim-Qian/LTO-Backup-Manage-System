from ui import header, console, confirm, wait_for_keypress, choose_arrow, clear
from rich.table import Table


def manage_labels_workflow(db):
    """Top-level interactive workflow for the label management menu."""
    while True:
        clear()
        header("🏷️  Label Management")

        choice = choose_arrow(
            "Labels Menu",
            [
                ("1", "📋 List All Labels"),
                ("2", "➕ Create Label"),
                ("3", "🗑️  Delete Label"),
                ("4", "🔗 Assign Label to Tape"),
                ("5", "✂️  Remove Label from Tape"),
                ("6", "🔍 Browse Tapes by Label"),
                ("0", "← Back"),
            ]
        )

        if   choice == "1": _list_labels(db)
        elif choice == "2": _create_label(db)
        elif choice == "3": _delete_label(db)
        elif choice == "4": _assign_label(db)
        elif choice == "5": _remove_label(db)
        elif choice == "6": _browse_by_label(db)
        elif choice == "0": break


# =============================================================================
# SUB-WORKFLOWS
# =============================================================================

def _list_labels(db):
    header("All Labels")
    labels = db.list_labels()
    if not labels:
        console.print("[dim]No labels defined yet.[/]")
        wait_for_keypress()
        return

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Label",  style="cyan")
    table.add_column("Color")
    table.add_column("Tapes", justify="right")

    for name, color, count in labels:
        table.add_row(name, color, str(count))

    console.print(table)
    wait_for_keypress()


def _create_label(db):
    header("Create Label")
    name = input("Label name: ").strip()
    if not name:
        return
    color = input("Color (hex, e.g. #ff8800) [Enter = #5588cc]: ").strip() or "#5588cc"

    if db.create_label(name, color):
        console.print(f"[green]Label '{name}' created.[/]")
    else:
        console.print(f"[red]Label '{name}' already exists.[/]")
    wait_for_keypress()


def _delete_label(db):
    header("Delete Label")
    labels = db.list_labels()
    if not labels:
        console.print("[dim]No labels to delete.[/]")
        wait_for_keypress()
        return

    for i, (name, _, count) in enumerate(labels, 1):
        console.print(f"  {i}. {name}  [dim]({count} tape(s))[/]")

    raw = input("\nSelect number to delete (0 to cancel): ").strip()
    if not raw.isdigit() or raw == "0":
        return
    idx = int(raw) - 1
    if not (0 <= idx < len(labels)):
        return

    name = labels[idx][0]
    if confirm(f"Delete label '{name}'? It will be removed from all tapes."):
        db.delete_label(name)
        console.print(f"[green]Label '{name}' deleted.[/]")
    wait_for_keypress()


def _assign_label(db):
    header("Assign Label to Tape")

    tapes = db.conn.execute(
        "SELECT tape_id, description FROM tapes ORDER BY tape_id"
    ).fetchall()
    if not tapes:
        console.print("[red]No tapes found.[/]")
        wait_for_keypress()
        return

    for i, (tid, desc) in enumerate(tapes, 1):
        existing = db.get_labels_for_tape(tid)
        tag_str  = f"  [dim][{', '.join(existing)}][/]" if existing else ""
        console.print(f"  {i}. [cyan]{tid}[/] — {desc or '—'}{tag_str}")

    raw = input("\nSelect tape number (0 to cancel): ").strip()
    if not raw.isdigit() or raw == "0":
        return
    idx = int(raw) - 1
    if not (0 <= idx < len(tapes)):
        return
    tape_id = tapes[idx][0]

    labels = db.list_labels()
    if not labels:
        console.print("[red]No labels defined. Create one first.[/]")
        wait_for_keypress()
        return

    console.print("\nAvailable labels:")
    for i, (name, _, _) in enumerate(labels, 1):
        console.print(f"  {i}. {name}")

    raw = input("Select label number (0 to cancel): ").strip()
    if not raw.isdigit() or raw == "0":
        return
    idx = int(raw) - 1
    if not (0 <= idx < len(labels)):
        return

    label_name = labels[idx][0]
    if db.assign_label(tape_id, label_name):
        console.print(f"[green]Label '{label_name}' assigned to tape {tape_id}.[/]")
    else:
        console.print(f"[yellow]Tape {tape_id} already has label '{label_name}'.[/]")
    wait_for_keypress()


def _remove_label(db):
    header("Remove Label from Tape")

    tapes = db.conn.execute(
        "SELECT tape_id, description FROM tapes ORDER BY tape_id"
    ).fetchall()
    if not tapes:
        console.print("[red]No tapes found.[/]")
        wait_for_keypress()
        return

    # Only show tapes that actually have labels
    tapes_with_labels = [
        (tid, desc, db.get_labels_for_tape(tid))
        for tid, desc in tapes
        if db.get_labels_for_tape(tid)
    ]
    if not tapes_with_labels:
        console.print("[dim]No tape has any labels assigned.[/]")
        wait_for_keypress()
        return

    for i, (tid, desc, lbls) in enumerate(tapes_with_labels, 1):
        console.print(f"  {i}. [cyan]{tid}[/] — [{', '.join(lbls)}]")

    raw = input("\nSelect tape number (0 to cancel): ").strip()
    if not raw.isdigit() or raw == "0":
        return
    idx = int(raw) - 1
    if not (0 <= idx < len(tapes_with_labels)):
        return
    tape_id, _, labels_on_tape = tapes_with_labels[idx]

    console.print(f"\nLabels on {tape_id}:")
    for i, name in enumerate(labels_on_tape, 1):
        console.print(f"  {i}. {name}")

    raw = input("Select label to remove (0 to cancel): ").strip()
    if not raw.isdigit() or raw == "0":
        return
    idx = int(raw) - 1
    if not (0 <= idx < len(labels_on_tape)):
        return

    label_name = labels_on_tape[idx]
    db.remove_label_from_tape(tape_id, label_name)
    console.print(f"[green]Label '{label_name}' removed from tape {tape_id}.[/]")
    wait_for_keypress()


def _browse_by_label(db):
    header("Browse Tapes by Label")

    labels = db.list_labels()
    if not labels:
        console.print("[dim]No labels defined.[/]")
        wait_for_keypress()
        return

    for i, (name, _, count) in enumerate(labels, 1):
        console.print(f"  {i}. {name}  [dim]({count} tape(s))[/]")

    raw = input("\nSelect label number (0 to cancel): ").strip()
    if not raw.isdigit() or raw == "0":
        return
    idx = int(raw) - 1
    if not (0 <= idx < len(labels)):
        return
    label_name = labels[idx][0]

    tape_ids = db.get_tapes_by_label(label_name)
    if not tape_ids:
        console.print(f"[yellow]No tapes assigned to '{label_name}'.[/]")
        wait_for_keypress()
        return

    console.print(f"\n[bold cyan]Tapes labelled '{label_name}':[/]")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("ID",          style="cyan")
    table.add_column("Gen")
    table.add_column("Status")
    table.add_column("Used",        justify="right")
    table.add_column("Description")

    for tid in tape_ids:
        row = db.conn.execute(
            "SELECT generation, encrypted, used_capacity, description "
            "FROM tapes WHERE tape_id=?", (tid,)
        ).fetchone()
        if row:
            gen, enc, used, desc = row
            status = "[red]Encrypted[/]" if enc else "[green]Plain[/]"
            table.add_row(tid, gen, status, f"{used / 1024**3:.2f} GB", desc or "")

    console.print(table)
    wait_for_keypress()
