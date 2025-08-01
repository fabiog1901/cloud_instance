import boto3
import time
from pprint import pprint

# Configuration
INSTANCE_ID = "i-08ae0517e30269aac"
NEW_INSTANCE_TYPE = "t3.large"  # Change to desired type
REGION="sa-east-1"

ec2 = boto3.client("ec2", region_name=REGION)

def get_allocation_id(public_ip, instance_id):
    # Step 1: Get the Elastic IP associated with the instance
    response = ec2.describe_addresses(PublicIps=[public_ip])
    
    

    for address in response['Addresses']:
        # Check if the EIP is associated with the given instance ID
        if address.get('InstanceId') == instance_id:
            public_ip = address.get('PublicIp')
            allocation_id = address.get('AllocationId')
            print(f"Instance {instance_id} has EIP {public_ip} with Allocation ID {allocation_id}")
            return allocation_id

    print(f"No Elastic IP found associated with instance {instance_id}")
    return None

def ter(instance_id):
    
    response = ec2.describe_instances(
                InstanceIds=[instance_id]
            )
    
    public_ip = response["Reservations"][0]["Instances"][0]["PublicIpAddress"]
    print(public_ip)
    
    alloc = get_allocation_id(public_ip, instance_id)
    
    print(alloc)
    
    r = ec2.terminate_instances(
                InstanceIds=[instance_id]
            )
    
    waiter = ec2.get_waiter("instance_terminated")
    waiter.wait(InstanceIds=[instance_id])
    print("TERMINATED")
    
    response = ec2.release_address(AllocationId=alloc)
    
    pprint(response)
    
def stop_instance(instance_id):
    print(f"Stopping instance {instance_id}...")
    ec2.stop_instances(InstanceIds=[instance_id])
    waiter = ec2.get_waiter("instance_stopped")
    waiter.wait(InstanceIds=[instance_id])
    print("Instance stopped.")


def modify_instance_type(instance_id, new_type):
    print(f"Modifying instance {instance_id} to type {new_type}...")
    ec2.modify_instance_attribute(
        InstanceId=instance_id, InstanceType={"Value": new_type}
    )
    print("Instance type modified.")


def start_instance(instance_id):
    print(f"Starting instance {instance_id}...")
    ec2.start_instances(InstanceIds=[instance_id])
    waiter = ec2.get_waiter("instance_running")
    waiter.wait(InstanceIds=[instance_id])
    print("Instance is running.")


def main():
    ter(INSTANCE_ID)
    return
    describe_instance(INSTANCE_ID)
    return
    # Step 1: Stop the instance
    stop_instance(INSTANCE_ID)

    # Step 2: Change instance type
    modify_instance_type(INSTANCE_ID, NEW_INSTANCE_TYPE)

    # Step 3: Start the instance again
    start_instance(INSTANCE_ID)

    print("✅ Instance has been successfully resized.")


if __name__ == "__main__":
    main()
