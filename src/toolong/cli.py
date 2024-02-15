from __future__ import annotations

from importlib.metadata import version
import click

from toolong.ui import UI


@click.command()
@click.version_option(version("toolong"))
@click.argument("files", metavar="FILE1 FILE2", nargs=-1)
@click.option("-m", "--merge", is_flag=True, help="Merge files.")
@click.option(
    "-o",
    "--output-merge",
    metavar="PATH",
    nargs=1,
    help="Path to save merged file (requires -m).",
)
def run(files: list[str], merge: bool, output_merge: str) -> None:
    """View / tail / search log files."""
    if not files:
        ctx = click.get_current_context()
        click.echo(ctx.get_help())
        ctx.exit()
    ui = UI(files, merge=merge, save_merge=output_merge)
    ui.run()
