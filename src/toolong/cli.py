from importlib.metadata import version
import click
from typing import List

from toolong.ui import UI


@click.command()
@click.version_option(version("toolong"))
@click.argument("files", metavar="FILE1 FILE2", nargs=-1)
@click.option("-m", "--merge", is_flag=True, help="Merge files")
def run(files: List[str], merge: bool):
    """View / tail / search log files."""
    if not files:
        ctx = click.get_current_context()
        click.echo(ctx.get_help())
        ctx.exit()
    ui = UI(files, merge=merge)
    ui.run()
