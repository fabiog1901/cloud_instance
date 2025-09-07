#!/usr/bin/python

import json
import logging
import os
import platform
import sys
from enum import Enum
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import typer

# import cloud_instance.cli.util
from cloud_instance.models.main import gather_current_deployment, create, return_to_be_deleted_vms

# import cloud_instance.utils.common
from cloud_instance.cli.dep import EPILOG, Param

from .. import __version__

logger = logging.getLogger("cloud_instance")


app = typer.Typer(
    epilog=EPILOG,
    no_args_is_help=True,
    help=f"cloud_instance v{__version__}: utility to manage VMs in the cloud.",
)


# app.add_typer(cloud_instance.cli.util.app, name="util")

version: bool = typer.Option(True)


class LogLevel(str, Enum):
    debug = "debug"
    info = "info"
    warning = "warning"
    error = "error"


@app.command(help="gather existing VMs")
def gather_existing_vms(
    deployment_id: str = typer.Option(
        ...,
        "-d",
        "--deployment-id",
        help="The deployment_id",
    ),
):
    result = gather_current_deployment(deployment_id)

    print(json.dumps(result))


@app.command(help="Return VMs slated to be deleted")
def return_to_be_deleted_vms(
    deployment_id: str = typer.Option(
        ...,
        "-d",
        "--deployment-id",
        help="The deployment_id",
    ),
    deployment: str = typer.Option(
        ...,
        help="deployment",
    ),
):
    pass


@app.command(help="Create the deployment", epilog=EPILOG, no_args_is_help=True)
def create(
    deployment_id: str = typer.Option(
        ...,
        "-d",
        "--deployment-id",
        help="The deployment_id",
    ),
    deployment: str = typer.Option(
        ...,
        help="deployment",
    ),
    defaults: str = typer.Option(
        ...,
        help="defaults",
    ),
    preserve: bool = typer.Option(
        False,
        "--preserve",
        show_default=False,
        help="Whether to preserve existing VMs.",
    ),
    log_level: LogLevel = Param.LogLevel,
):
    logger.setLevel(log_level.upper())

    logger.debug("Executing run()")

    result = create(
        deployment_id,
        deployment,
        defaults,
        preserve,
    )

    print(json.dumps(result))


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"dbworkload : {__version__}")
        typer.echo(f"Python     : {platform.python_version()}")
        raise typer.Exit()


@app.callback()
def version_option(
    _: bool = typer.Option(
        False,
        "--version",
        "-v",
        callback=_version_callback,
        help="Print the version and exit",
    ),
) -> None:
    pass


# this is only needed for mkdocs-click
click_app = typer.main.get_command(app)
