import os
import readchar
from rich.console import Console
from rich.prompt import Confirm
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich.prompt import Prompt

# Initialize the global console object
console = Console()

def clear():
    """
    Clears the terminal screen (Cross-platform: Windows/Linux/Mac).
    """
    os.system("cls" if os.name == "nt" else "clear")

def header(title):
    clear()
    gradient = ["cyan", "bright_cyan", "blue", "bright_blue"]
    text = Text()
    for i, ch in enumerate(title):
        text.append(ch, style=f"bold {gradient[i % len(gradient)]}")

    console.print(
        Panel(
            Align.center(text),
            border_style="bright_blue",
            padding=(1, 4),
            expand=False
        )
    )

def confirm(question):
    """
    Asks the user for a Yes/No confirmation.
    Returns: Boolean
    """
    return Confirm.ask(f"[yellow]{question}[/]")

def print_error(msg):
    console.print(
        Panel(
            f"❌  {msg}",
            title="[bold red]ERROR[/]",
            border_style="red"
        )
    )

def print_success(msg):
    console.print(
        Panel(
            f"✅  {msg}",
            title="[bold green]SUCCESS[/]",
            border_style="green"
        )
    )

def wait_for_keypress():
    """
    Ensures the user sees the result before returning to the main menu.
    """
    console.print("\n[dim]Press Enter to continue...[/]")
    input()

def choose(title, options):
    """
    options: list of (key, label)
    returns: key
    """
    body = "\n".join([f"[bold cyan]{k}[/]  {label}" for k, label in options])

    console.print(
        Panel(
            body,
            title=f"[bold]{title}[/]",
            border_style="cyan"
        )
    )

    valid_keys = [str(k) for k, _ in options]

    while True:
        choice = Prompt.ask("Select", default=valid_keys[0])
        if choice in valid_keys:
            return choice
        console.print("[red]Invalid selection[/red]")

def choose_arrow(title, options, default=0):
    """
    options: list of (key, label)
    return: key
    """
    index = default

    while True:
        console.clear()

        body = []
        for i, (k, label) in enumerate(options):
            if i == index:
                body.append(f"[bold black on cyan] ▶ {label} [/]")
            else:
                body.append(f"   {label}")

        console.print(
            Panel(
                "\n".join(body),
                title=f"[bold]{title}[/]",
                border_style="cyan"
            )
        )
        console.print("[dim]↑ ↓ move   Enter select[/]")

        key = readchar.readkey()

        if key == readchar.key.UP:
            index = (index - 1) % len(options)
        elif key == readchar.key.DOWN:
            index = (index + 1) % len(options)
        elif key == readchar.key.ENTER:
            return options[index][0]