#!/usr/bin/python

import json
import logging
import platform
from enum import Enum

import typer

# import cloud_instance.utils.common
from cloud_instance.cli.dep import EPILOG, Param

# import cloud_instance.cli.util
from cloud_instance.models import main

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


@app.command(help="gather a list of all existing VMs in the specified deployment_id")
def gather_current_deployment(
    deployment_id: str = typer.Option(
        ...,
        "-d",
        "--deployment-id",
        help="The deployment_id",
    ),
):
    
    logger.info(f"START: gather-current-deployment {deployment_id=}")
    
    result = main.gather_current_deployment(deployment_id)

    print(json.dumps(result))
    
    logger.info(f"COMPLETED: gather-current-deployment {deployment_id=}")
    

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
    
    logger.info(f"START: return-to-be-deleted-vms {deployment_id=}")
    
    result = main.return_to_be_deleted_vms(
        deployment_id,
        json.loads(deployment),
    )

    print(json.dumps(result))

    logger.info(f"COMPLETED: return-to-be-deleted-vms {deployment_id=}")

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
):
    
    logger.info(f"START: create {deployment_id=}")

    result = main.create(
        deployment_id,
        json.loads(deployment),
        json.loads(defaults),
        preserve,
    )

    print(json.dumps(result))
    
    logger.info(f"COMPLETED: create {deployment_id=}")

@app.command(help="Modify instance type", epilog=EPILOG, no_args_is_help=True)
def modify_instance_type(
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
    
    main.modify_instance_type(
        deployment_id,
        new_cpus_count,
        filter_by_groups.split(",") if filter_by_groups else [],
        sequential,
        pause_between,
        json.loads(defaults),
    )
    
    logger.info(f"COMPLETED: modify-instance-type {deployment_id=}")


@app.command(help="Destroy the deployment", epilog=EPILOG, no_args_is_help=True)
def destroy(
    deployment_id: str = typer.Option(
        ...,
        "-d",
        "--deployment-id",
        help="The deployment_id",
    ),
):
    
    logger.info(f"START: destroy {deployment_id=}")
    
    main.destroy(deployment_id)
    
    logger.info(f"COMPLETED: destroy {deployment_id=}")

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
