import click

from tailless.ui import UI


@click.command()
@click.argument("files", metavar="FILE", nargs=-1)
@click.option("-m", "--merge", is_flag=True, help="Merge files")
def run(files: list[str], merge: bool):
    """Simple program that greets NAME for a total of COUNT times."""
    ui = UI(files, merge=merge)
    ui.run()


if __name__ == "__main__":
    run()
