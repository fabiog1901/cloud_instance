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
import json

import typer

# import cloud_instance.cli.util
from cloud_instance.models import main

# import cloud_instance.utils.common
from cloud_instance.cli.dep import EPILOG, Param

from .. import __version__

# setup global logger
logger = logging.getLogger("cloud_instance")
logger.setLevel(logging.INFO)

# create console handler and set level to debug
ch = logging.FileHandler(filename="/tmp/cloud_instance.log")
ch.setLevel(logging.INFO)

# create formatter
formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] (%(threadName)s) %(lineno)d %(message)s"
)

# add formatter to ch
ch.setFormatter(formatter)

# add ch to logger
logger.addHandler(ch)
logger.removeHandler(logger.handlers[0])  # Remove the console output

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


@app.command(help="gather a list of all existing VMs in the specified deployment_id")
def gather_current_deployment(
    deployment_id: str = typer.Option(
        ...,
        "-d",
        "--deployment-id",
        help="The deployment_id",
    ),
):
    result = main.gather_current_deployment(deployment_id)

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
    #logger.setLevel(log_level.upper())
    
    logger.debug("Executing run()")

    result = main.create(
        deployment_id,
        json.loads(deployment),
        json.loads(defaults),
        preserve,
    )


    print(json.dumps(result, indent=4))


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
