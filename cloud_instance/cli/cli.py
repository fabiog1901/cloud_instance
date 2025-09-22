#!/usr/bin/python

import json
import logging
import platform
import sys

import typer

# import cloud_instance.utils.common
from cloud_instance.cli.dep import EPILOG

# import cloud_instance.cli.util
from cloud_instance.models import create, delete, gather, modify, resize, slated

from .. import __version__

# setup global logger
logger = logging.getLogger("cloud_instance")
logger.setLevel(logging.INFO)

# create console handler and set level to debug
ch = logging.FileHandler(filename="/tmp/cloud_instance.log")
ch.setLevel(logging.INFO)

# create formatter
formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] (%(threadName)s) %(filename)s:%(lineno)d %(message)s"
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

version: bool = typer.Option(True)


@app.command(
    name="create",
    help="Create the deployment",
    no_args_is_help=True,
)
def cli_create(
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
):

    logger.info(f"START: create {deployment_id=}")

    try:
        result = create.create(
            deployment_id,
            json.loads(deployment),
            json.loads(defaults),
            preserve,
        )
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result))

    logger.info(f"COMPLETED: create {deployment_id=}")


@app.command(
    name="gather",
    help="Gather a list of all existing VMs in the specified deployment_id",
    no_args_is_help=True,
)
def cli_gather(
    deployment_id: str = typer.Option(
        ...,
        "-d",
        "--deployment-id",
        help="The deployment_id",
    ),
):

    logger.info(f"START: gather {deployment_id=}")

    try:
        result = gather.gather(deployment_id)
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result))

    logger.info(f"COMPLETED: gather {deployment_id=}")


@app.command(
    name="slated",
    help="Return VMs slated to be deleted",
    no_args_is_help=True,
)
def cli_slated(
    deployment_id: str = typer.Option(
        ...,
        "-d",
        "--deployment-id",
        help="The deployment_id",
    ),
    deployment: str = typer.Option(
        ...,
        help="The deployment_id",
    ),
):

    logger.info(f"START: slated {deployment_id=}")

    try:
        result = slated.slated(
            deployment_id,
            json.loads(deployment),
        )
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result))

    logger.info(f"COMPLETED: slated {deployment_id=}")


@app.command(
    name="modify",
    help="Modify instance type",
    no_args_is_help=True,
)
def cli_modify(
    deployment_id: str = typer.Option(
        ...,
        "-d",
        "--deployment-id",
        help="The deployment_id",
    ),
    new_cpus_count: int = typer.Option(
        ...,
        "-c",
        "--cpu-count",
        help="New CPU count.",
    ),
    filter_by_groups: str = typer.Option(
        None,
        "-f",
        "--filter-by-groups",
        help="comma separated list of groups the instance must belong to",
    ),
    sequential: bool = typer.Option(
        True,
        "--no-sequential",
        show_default=False,
        help="Whether to modify instances sequentially.",
    ),
    pause_between: int = typer.Option(
        30,
        "-p",
        "--pause-between",
        help="If sequential, seconds to pause between modifications.",
    ),
    defaults: str = typer.Option(
        ...,
        help="defaults",
    ),
):

    logger.info(f"START: modify-instance-type {deployment_id=}")

    modify.modify(
        deployment_id,
        new_cpus_count,
        filter_by_groups.split(",") if filter_by_groups else [],
        sequential,
        pause_between,
        json.loads(defaults),
    )

    logger.info(f"COMPLETED: modify-instance-type {deployment_id=}")


@app.command(
    name="resize",
    help="Resize disk",
    no_args_is_help=True,
)
def cli_resize(
    deployment_id: str = typer.Option(
        ...,
        "-d",
        "--deployment-id",
        help="The deployment_id",
    ),
    new_disk_size: int = typer.Option(
        ...,
        "-s",
        "--disk-size",
        help="New CPU count.",
    ),
    filter_by_groups: str = typer.Option(
        None,
        "-f",
        "--filter-by-groups",
        help="comma separated list of groups the instance must belong to",
    ),
    sequential: bool = typer.Option(
        True,
        "--no-sequential",
        show_default=False,
        help="Whether to modify instances sequentially.",
    ),
    pause_between: int = typer.Option(
        30,
        "-p",
        "--pause-between",
        help="If sequential, seconds to pause between modifications.",
    ),
):

    logger.info(f"START: resize {deployment_id=}")

    resize.resize(
        deployment_id,
        new_disk_size,
        filter_by_groups.split(",") if filter_by_groups else [],
        sequential,
        pause_between,
    )

    logger.info(f"COMPLETED: resize {deployment_id=}")


@app.command(
    name="delete",
    help="Destroy the deployment",
    no_args_is_help=True,
)
def cli_delete(
    deployment_id: str = typer.Option(
        ...,
        "-d",
        "--deployment-id",
        help="The deployment_id",
    ),
):

    logger.info(f"START: delete {deployment_id=}")

    delete.delete(deployment_id)

    logger.info(f"COMPLETED: delete {deployment_id=}")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"cloud_instance : {__version__}")
        typer.echo(f"Python         : {platform.python_version()}")
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
