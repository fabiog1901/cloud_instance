import typer

from .. import __version__

EPILOG = "Docs: <https://github.com/fabiog1901/cloud_instance>"


class Param:
    LogLevel = typer.Option(
        "info", "--log-level", "-l", show_choices=True, help="Set the logging level."
    )
