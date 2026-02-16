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
from ui import console
from rich.table import Table

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
    if not os.path.exists("main.exe"):
        print("ERROR: main.exe not found")
        sys.exit(1)
    subprocess.call([sys.executable, "main.exe"])

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

def main():
    print_banner()
    # loading_bar()

    db = Database()
    tapes = db.conn.execute("SELECT tape_id, generation, encrypted, description, used_capacity FROM tapes").fetchall()
    
    if not tapes:
        console.print("[red]No tapes found.[/]")
    else:
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

    wait_any_key()
    # print("\nLaunching main.py...\n")
    tape_drive_animation(cycles=2)
    run_main()

if __name__ == "__main__":
    main()