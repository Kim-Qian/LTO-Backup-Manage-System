# launcher.py
# LTO Backup & Manage System launcher
# Typewriter effect + loading bar
# Title: blue only
# Subtitle: rainbow color
# Press any key -> run main.py

import os
import sys
import time
import shutil
import subprocess

from db import Database
from config_manager import cfg
from ui import console
from rich.table import Table
from rich.columns import Columns
from rich.panel import Panel
from rich.text import Text
from datetime import datetime, timezone

# Optional pyfiglet
try:
    import pyfiglet
    HAS_FIGLET = True
except ImportError:
    HAS_FIGLET = False

# ANSI colors
BLUE = "\033[1;34m"
RESET = "\033[0m"
RAINBOW = [
    "\033[1;31m",  # red
    "\033[1;33m",  # yellow
    "\033[1;32m",  # green
    "\033[1;36m",  # cyan
    "\033[1;35m",  # magenta
]

def term_width(default=80):
    try:
        return shutil.get_terminal_size().columns
    except Exception:
        return default

# -------- effects --------

def typewriter(text, delay=0.002):
    for ch in text:
        print(ch, end="", flush=True)
        time.sleep(delay)
    print()

def typewriter_centered(text, delay=0.002):
    w = term_width()
    pad = max((w - len(text)) // 2, 0)
    typewriter(" " * pad + text, delay)

def typewriter_blue_centered(text, delay=0.002):
    w = term_width()
    pad = max((w - len(text)) // 2, 0)
    for ch in " " * pad + text:
        print(f"{BLUE}{ch}{RESET}", end="", flush=True)
        time.sleep(delay)
    print()

def typewriter_rainbow_centered(text, delay=0.01):
    w = term_width()
    pad = max((w - len(text)) // 2, 0)
    i = 0
    for ch in " " * pad + text:
        if ch.isspace():
            print(ch, end="", flush=True)
        else:
            print(f"{RAINBOW[i % len(RAINBOW)]}{ch}{RESET}", end="", flush=True)
            i += 1
        time.sleep(delay)
    print()

def loading_bar(duration=1.2, width=30):
    print()
    print(" " * ((term_width() - (width + 10)) // 2) + "Loading ", end="", flush=True)
    start = time.time()
    while True:
        elapsed = time.time() - start
        progress = min(elapsed / duration, 1.0)
        filled = int(width * progress)
        bar = "[" + "=" * filled + " " * (width - filled) + "]"
        print("\r" + " " * ((term_width() - (width + 10)) // 2) + "Loading " + bar,
              end="", flush=True)
        if progress >= 1:
            break
        time.sleep(0.02)
    print("\n")

def tape_drive_animation(cycles=2, delay=0.12):
    """
    High-quality ASCII LTO tape drive startup animation
    Clean, symmetric, industrial blue style
    """

    BLUE = "\033[1;34m"
    RESET = "\033[0m"

    frames = [
r"""
        ╔══════════════════════════╗
        ║       LTO TAPE DRIVE     ║
        ╠══════════════════════════╣
        ║  ┌────────────────────┐  ║
        ║  │     INSERT TAPE    │  ║
        ║  │                    │  ║
        ║  └────────────────────┘  ║
        ║         [    ]           ║
        ╚══════════════════════════╝
""",
r"""
        ╔══════════════════════════╗
        ║       LTO TAPE DRIVE     ║
        ╠══════════════════════════╣
        ║  ┌────────────────────┐  ║
        ║  │    LOADING TAPE    │  ║
        ║  │                    │  ║
        ║  └────────────────────┘  ║
        ║         [=   ]           ║
        ╚══════════════════════════╝
""",
r"""
        ╔══════════════════════════╗
        ║       LTO TAPE DRIVE     ║
        ╠══════════════════════════╣
        ║  ┌────────────────────┐  ║
        ║  │    LOADING TAPE    │  ║
        ║  │                    │  ║
        ║  └────────────────────┘  ║
        ║         [==  ]           ║
        ╚══════════════════════════╝
""",
r"""
        ╔══════════════════════════╗
        ║       LTO TAPE DRIVE     ║
        ╠══════════════════════════╣
        ║  ┌────────────────────┐  ║
        ║  │    LOADING TAPE    │  ║
        ║  │                    │  ║
        ║  └────────────────────┘  ║
        ║         [=== ]           ║
        ╚══════════════════════════╝
""",
r"""
        ╔══════════════════════════╗
        ║       LTO TAPE DRIVE     ║
        ╠══════════════════════════╣
        ║  ┌────────────────────┐  ║
        ║  │    LOADING TAPE    │  ║
        ║  │                    │  ║
        ║  └────────────────────┘  ║
        ║         [====]           ║
        ╚══════════════════════════╝
""",
r"""
        ╔══════════════════════════╗
        ║       LTO TAPE DRIVE     ║
        ╠══════════════════════════╣
        ║  ┌────────────────────┐  ║
        ║  │       ONLINE       │  ║
        ║  │                    │  ║
        ║  └────────────────────┘  ║
        ║      ◐          ◑       ║
        ╚══════════════════════════╝
""",
r"""
        ╔══════════════════════════╗
        ║       LTO TAPE DRIVE     ║
        ╠══════════════════════════╣
        ║  ┌────────────────────┐  ║
        ║  │       ONLINE       │  ║
        ║  │                    │  ║
        ║  └────────────────────┘  ║
        ║      ◓          ◒       ║
        ╚══════════════════════════╝
""",
r"""
        ╔══════════════════════════╗
        ║       LTO TAPE DRIVE     ║
        ╠══════════════════════════╣
        ║  ┌────────────────────┐  ║
        ║  │       ONLINE       │  ║
        ║  │                    │  ║
        ║  └────────────────────┘  ║
        ║      ◐          ◑       ║
        ╚══════════════════════════╝
""",
r"""
        ╔══════════════════════════╗
        ║       LTO TAPE DRIVE     ║
        ╠══════════════════════════╣
        ║  ┌────────────────────┐  ║
        ║  │       ONLINE       │  ║
        ║  │                    │  ║
        ║  └────────────────────┘  ║
        ║      ◓          ◒       ║
        ╚══════════════════════════╝
"""
    ]

    for _ in range(cycles):
        for frame in frames:
            os.system("cls" if os.name == "nt" else "clear")
            print(BLUE + frame + RESET)
            time.sleep(delay)

# -------- input --------

def wait_any_key():
    print("Press any key to continue...")
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.getch()
        else:
            import tty, termios
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        input()

# -------- main logic --------

def run_main():
    if not os.path.exists("main.py"):
        print("ERROR: main.py not found")
        sys.exit(1)
    subprocess.call([sys.executable, "main.py"])

def print_banner():
    print("\n")
    if HAS_FIGLET:
        fig1 = pyfiglet.figlet_format("LTO Backup &", font="standard")
        fig2 = pyfiglet.figlet_format("Manage System", font="standard")
        for block in (fig1, fig2):
            for line in block.splitlines():
                typewriter_blue_centered(line, delay=0.0008)
    else:
        typewriter_blue_centered("LTO Backup & Manage System", delay=0.002)

    print()
    typewriter_rainbow_centered("Designed By Kim Qian", delay=0.02)
    print()

def _make_stat_card(icon, value, label, value_style="bold cyan"):
    """Build a single Rich Panel stat card for the dashboard."""
    content = Text(justify="center")
    content.append(f"{icon}\n", style="")
    content.append(f"{value}\n", style=value_style)
    content.append(label, style="dim")
    return Panel(content, border_style="blue", padding=(1, 3))


def print_dashboard(db):
    """Render a one-screen summary dashboard using Rich panels and a table."""

    # ---- Global stats --------------------------------------------------------
    tape_count = db.conn.execute("SELECT COUNT(*) FROM tapes").fetchone()[0]

    total_used = db.conn.execute(
        "SELECT SUM(used_capacity) FROM tapes"
    ).fetchone()[0] or 0

    failed_jobs = db.conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE status='FAILED'"
    ).fetchone()[0]

    last_bk_row = db.conn.execute(
        "SELECT MAX(finished_at) FROM jobs WHERE status='SUCCESS' AND action='BACKUP'"
    ).fetchone()
    last_backup_ts = last_bk_row[0] if last_bk_row else None

    if last_backup_ts:
        try:
            dt = datetime.fromisoformat(last_backup_ts)
            last_backup_str = dt.strftime("%Y-%m-%d  %H:%M")
        except Exception:
            last_backup_str = last_backup_ts
    else:
        last_backup_str = "Never"

    used_tb = total_used / 1024 ** 4

    # Colour-code the failed-jobs card
    fail_style = "bold red" if failed_jobs > 0 else "bold green"

    # ---- Four summary cards --------------------------------------------------
    cards = [
        _make_stat_card("📼", str(tape_count), "Total Tapes"),
        _make_stat_card("💾", f"{used_tb:.3f} TB", "Total Used"),
        _make_stat_card("❌" if failed_jobs > 0 else "✅",
                        str(failed_jobs), "Failed Jobs", fail_style),
        _make_stat_card("🕒", last_backup_str, "Last Backup", "bold white"),
    ]
    console.print(Columns(cards, equal=True, expand=True))

    # ---- Per-tape breakdown table -------------------------------------------
    tape_rows = db.conn.execute(
        "SELECT tape_id, generation, encrypted, description, used_capacity "
        "FROM tapes ORDER BY tape_id"
    ).fetchall()

    if not tape_rows:
        console.print("[dim]No tapes registered yet.[/]")
        return

    table = Table(show_header=True, header_style="bold magenta", box=None)
    table.add_column("Tape ID",     style="cyan",  no_wrap=True)
    table.add_column("Gen",         no_wrap=True)
    table.add_column("Enc",         no_wrap=True)
    table.add_column("Used",        justify="right", no_wrap=True)
    table.add_column("Usage %",     justify="right", no_wrap=True)
    table.add_column("Description")

    for tid, gen, enc, desc, used in tape_rows:
        gen_info = cfg.get_generation_info(gen)
        max_cap  = gen_info.get("capacity", 1)
        pct      = used / max_cap * 100 if max_cap > 0 else 0

        # Colour the usage percentage based on thresholds
        if pct > 95:
            pct_str = f"[red]{pct:.1f}%[/]"
        elif pct > 80:
            pct_str = f"[yellow]{pct:.1f}%[/]"
        else:
            pct_str = f"[green]{pct:.1f}%[/]"

        enc_str  = "[red]🔒[/]" if enc else "[green]🔓[/]"
        used_str = f"{used / 1024**3:.2f} GB"

        table.add_row(tid, gen, enc_str, used_str, pct_str, desc or "")

    console.print(table)


def main():
    print_banner()
    # loading_bar()

    db = Database()
    print_dashboard(db)

    wait_any_key()
    # print("\nLaunching main.py...\n")
    tape_drive_animation(cycles=2)
    run_main()

if __name__ == "__main__":
    main()

