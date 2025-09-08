import logging

# setup global logger
logger = logging.getLogger("cloud_instance")


from .build import build_deployment
from .destroy import destroy_all
from .fetch import fetch_all
from .provision import provision


def gather_current_deployment(
    deployment_id: str,
) -> list[dict]:

    logger.info(f"Fetching all instances with deployment_id = '{deployment_id}'")
    current_instances, errors = fetch_all(deployment_id)

    if errors:
        raise ValueError(errors)

    return current_instances


def create(
    deployment_id: str,
    deployment: list,
    defaults: dict,
    preserve: bool,
) -> list[dict]:

    # fetch all running instances for the deployment_id and append them to the 'instances' list
    logger.info(f"Fetching all instances with deployment_id = '{deployment_id}'")
    current_instances, errors = fetch_all(deployment_id)

    logger.info(f"current_instances count={len(current_instances)}")
    for idx, x in enumerate(current_instances, start=1):
        logger.info(f"{idx}:\t{x}")

    if errors:
        raise ValueError(errors)

    logger.info("Building deployment...")
    current_vms, surplus_vms, new_vms = build_deployment(
        deployment_id,
        deployment,
        current_instances,
    )

    logger.info(f"current_vms count={len(current_vms)}")
    for idx, x in enumerate(current_vms, start=1):
        logger.info(f"{idx}:\t{x}")

    logger.info(f"surplus_vms count={len(surplus_vms)}")
    for idx, x in enumerate(surplus_vms, start=1):
        logger.info(f"{idx}:\t{x}")

    logger.info(f"new_vms count={len(new_vms)}")
    for idx, x in enumerate(new_vms, start=1):
        logger.info(f"{idx}:\t{x}")

    logger.info("Provisioning new_vms...")
    new_instances, errors = provision(new_vms, defaults)

    if not preserve:
        logger.info("Destroying surplus_vms...")
        destroy_all(surplus_vms)

    logger.info(f"new deployment count={len(new_instances + current_vms)}")
    for idx, x in enumerate(new_instances + current_vms, start=1):
        logger.info(f"{idx}:\t{x}")

    if errors:
        raise ValueError(errors)

    logger.info("Returning new deployment list to client")
    return new_instances + current_vms


def return_to_be_deleted_vms(self) -> list[dict]:

    # fetch all running instances for the deployment_id and append them to the 'instances' list
    logger.info(f"Fetching all instances with deployment_id = '{self.deployment_id}'")
    self.current_instances, self.errors = fetch_all(
        self.deployment_id, self.gcp_project, self.azure_resource_group
    )

    if self.errors:
        raise ValueError(self.errors)

    if self.current_instances:
        logger.info("Listing pre-existing instances:")
        for x in self.current_instances:
            logger.info(f"\t{x}")
    else:
        logger.info("No pre-existing instances")

    # instances of the new deployment will go into the 'new_instances' list
    logger.info("Building deployment...")
    build_deployment()

    # at this point, `instances` only has surplus vms that will be deleted

    logger.info("Listing instances slated for deletion")
    for x in self.current_instances:
        logger.info(f"\t{x}")

    logger.info("Returning list of instances slated to be deleted to client")
    return self.current_instances


"""
    
    if args.mod:
        ec2 = boto3.client("ec2", region_name=args.mod_region)
        
        print(f"Stopping instance {args.mod}...")
        ec2.stop_instances(InstanceIds=[args.mod])
        waiter = ec2.get_waiter("instance_stopped")
        waiter.wait(InstanceIds=[args.mod])
        print("Instance stopped.")

        
        print(f"Modifying instance {args.mod} to type {new_type}...")
        ec2.modify_instance_attribute(
            InstanceId=args.mod, InstanceType={"Value": new_type}
        )
        print("Instance type modified.")

        print(f"Starting instance {args.mod}...")
        ec2.start_instances(InstanceIds=[args.mod])
        waiter = ec2.get_waiter("instance_running")
        waiter.wait(InstanceIds=[args.mod])
        print("Instance is running.")

        return

"""
