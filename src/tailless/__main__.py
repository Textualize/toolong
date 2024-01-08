import click

from tailless.ui import UI


@click.command()
@click.argument("files", metavar="FILE", nargs=-1)
def run(files):
    """Simple program that greets NAME for a total of COUNT times."""
    ui = UI(files)
    ui.run()


if __name__ == "__main__":
    run()
