from __future__ import annotations

from importlib.metadata import version
import os

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
    import sys

    stdin_tty = sys.__stdin__.isatty()
    if not files and stdin_tty:
        ctx = click.get_current_context()
        click.echo(ctx.get_help())
        ctx.exit()
    if stdin_tty:
        try:
            ui = UI(files, merge=merge, save_merge=output_merge)
            ui.run()
        except Exception:
            pass
    else:
        import signal
        import selectors
        import subprocess
        import tempfile
        import sys
        import os

        def request_exit(signum, frame) -> None:
            """Gracefully handle termination signals."""
            sys.exit(0)

        # Handle termination signals more gracefully
        signal.signal(signal.SIGINT, request_exit)
        signal.signal(signal.SIGTERM, request_exit)

        # Write piped data to a temporary file
        with tempfile.NamedTemporaryFile(
            mode="w+b", buffering=0, prefix="tl_"
        ) as temp_file:

            # Get input directly from /dev/tty to free up stdin
            with open("/dev/tty", "rb", buffering=0) as tty_stdin:
                # Launch a new process to render the UI
                with subprocess.Popen(
                    [sys.argv[0], temp_file.name],
                    stdin=tty_stdin,
                    close_fds=True,
                    env={**os.environ, "TEXTUAL_ALLOW_SIGNALS": "1"},
                ) as process:

                    # Selector to monitor stdin for read events
                    selector = selectors.SelectSelector()
                    selector.register(sys.stdin.fileno(), selectors.EVENT_READ)

                    try:
                        while process.poll() is None:
                            for _, event in selector.select(0.1):
                                if process.poll() is not None:
                                    break
                                if event & selectors.EVENT_READ:
                                    line = os.read(sys.stdin.fileno(), 1024 * 64)
                                    if line:
                                        temp_file.write(line)
                                    else:
                                        break
                    except KeyboardInterrupt:
                        request_exit(signal.SIGINT, None)

                    finally:
                        # Ensure the process is properly terminated
                        process.terminate()
                        process.wait()
