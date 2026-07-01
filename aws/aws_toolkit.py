import boto3
import os
import sys
import time
from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError
from datetime import datetime


# ─────────────────────────────────────────────
#  SHARED UTILITIES
# ─────────────────────────────────────────────

def get_ec2_client(region=None):
    if region:
        session = boto3.Session(region_name=region)
        return session.client('ec2')
    return boto3.client('ec2')


def print_header(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_divider(width=80):
    print("-" * width)


# ─────────────────────────────────────────────
#  1. LIST INSTANCES
# ─────────────────────────────────────────────

def list_instances():
    print_header("List EC2 Instances")
    try:
        ec2 = get_ec2_client()
        response = ec2.describe_instances()

        # Column widths: 22+21+16+16+30 = 105
        TW = 105
        print(f"\n{'Name':<22}{'Instance ID':<21}{'Public IP':<16}{'Private IP':<16}{'Open Ports':<30}")
        print_divider(TW)

        found = False
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                found = True
                instance_id  = instance.get('InstanceId', 'N/A')
                public_ip    = instance.get('PublicIpAddress', 'N/A')
                private_ip   = instance.get('PrivateIpAddress', 'N/A')

                name_tag = 'N/A'
                for tag in instance.get('Tags', []):
                    if tag['Key'] == 'Name':
                        name_tag = tag['Value']
                        break

                # Collect open ports from all attached security groups
                all_ports = []
                for sg in instance.get('SecurityGroups', []):
                    sg_detail = ec2.describe_security_groups(GroupIds=[sg['GroupId']])['SecurityGroups'][0]
                    all_ports.append(get_open_ports(sg_detail))
                ports_str = " | ".join(all_ports) if all_ports else "None"
                if len(ports_str) > 28:
                    ports_str = ports_str[:25] + "..."

                print(f"{name_tag:<22}{instance_id:<21}{public_ip:<16}{private_ip:<16}{ports_str:<30}")

        print_divider(TW)
        if not found:
            print("No EC2 instances found.")

    except NoCredentialsError:
        print("AWS credentials not found. Please configure your credentials.")
    except PartialCredentialsError:
        print("Incomplete AWS credentials. Please check your configuration.")
    except Exception as e:
        print(f"An error occurred: {e}")


# ─────────────────────────────────────────────
#  2. CREATE INSTANCE
# ─────────────────────────────────────────────

def list_key_pairs(ec2):
    response = ec2.describe_key_pairs()
    key_pairs = response.get('KeyPairs', [])
    print("\nExisting Key Pairs:")
    if not key_pairs:
        print("  None")
    else:
        for idx, kp in enumerate(key_pairs, start=1):
            print(f"  {idx} - {kp['KeyName']}")
    return key_pairs


def create_key_pair(ec2, key_name):
    try:
        ec2.describe_key_pairs(KeyNames=[key_name])
        print(f"\n⚠  Key Pair '{key_name}' already exists in AWS. Using it (no new .pem file generated).")
    except ClientError:
        print(f"Creating Key Pair '{key_name}'...")
        key_pair = ec2.create_key_pair(KeyName=key_name)
        pem_path = f"{key_name}.pem"
        with open(pem_path, "w") as file:
            file.write(key_pair['KeyMaterial'])
        os.chmod(pem_path, 0o400)
        print(f"✅ Key Pair created and saved as '{pem_path}' (keep this safe — it won't be available again)")


def list_security_groups(ec2):
    response = ec2.describe_security_groups()
    groups = response.get('SecurityGroups', [])
    print("\nExisting Security Groups:")
    for idx, sg in enumerate(groups, start=1):
        print(f"  {idx} - {sg['GroupName']} (ID: {sg['GroupId']})")
    return groups


def get_or_create_security_group(ec2, group_input):
    security_group_id = None
    try:
        if group_input.startswith("sg-"):
            response = ec2.describe_security_groups(GroupIds=[group_input])
            security_group_id = response['SecurityGroups'][0]['GroupId']
            print(f"Security Group ID '{group_input}' found. Using the existing group.")
        else:
            response = ec2.describe_security_groups(GroupNames=[group_input])
            security_group_id = response['SecurityGroups'][0]['GroupId']
            print(f"Security Group Name '{group_input}' found. Using the existing group.")
    except ClientError:
        print(f"Security Group '{group_input}' does not exist. Creating a new one...")
        response = ec2.create_security_group(
            GroupName=group_input,
            Description="Security group for EC2 instance"
        )
        security_group_id = response['GroupId']
        ec2.authorize_security_group_ingress(
            GroupId=security_group_id,
            IpProtocol="tcp", FromPort=22, ToPort=22, CidrIp="0.0.0.0/0"
        )
        print(f"New Security Group created with ID: {security_group_id}")
    return security_group_id


def get_amis_by_os(ec2_client, os_choice):
    filters_map = {
        "1": [{'Name': 'name', 'Values': ['amzn2-ami-hvm-*-x86_64-gp2']}, {'Name': 'state', 'Values': ['available']}],
        "2": [{'Name': 'name', 'Values': ['ubuntu/images/hvm-ssd/ubuntu-focal-20.04-amd64-server-*']}, {'Name': 'state', 'Values': ['available']}],
        "3": [{'Name': 'name', 'Values': ['Windows_Server-2019-English-Full-Base-*']}, {'Name': 'state', 'Values': ['available']}],
        "4": [{'Name': 'name', 'Values': ['RHEL-8-HVM-*']}, {'Name': 'state', 'Values': ['available']}],
        "5": [{'Name': 'name', 'Values': ['suse-sles-15-sp*']}, {'Name': 'state', 'Values': ['available']}],
    }
    filters = filters_map.get(os_choice)
    if not filters:
        print("Invalid OS choice.")
        return []
    response = ec2_client.describe_images(
        Filters=filters,
        Owners=['amazon', '099720109477', '137112412989', '125523088429'],
    )
    images = response.get('Images', [])
    images.sort(key=lambda x: x['CreationDate'], reverse=True)
    return images


def select_ami(ec2_client):
    print("\nSelect OS for the AMI:")
    print("1 - Amazon Linux")
    print("2 - Ubuntu 20.04 LTS")
    print("3 - Windows Server 2019")
    print("4 - Red Hat Enterprise Linux 8")
    print("5 - SUSE Linux Enterprise Server 15")

    os_choice = input("Enter the number for your desired OS (default 1): ").strip() or "1"
    images = get_amis_by_os(ec2_client, os_choice)
    if not images:
        print("No AMIs found for selected OS.")
        sys.exit(1)

    print("\nAvailable AMIs (top 10):")
    for idx, img in enumerate(images[:10], start=1):
        print(f"{idx}. {img['Name']} - {img['ImageId']} - Created: {img['CreationDate'][:10]}")

    choice = input("Select an AMI by number (default 1): ").strip() or "1"
    choice = int(choice) if choice.isdigit() and 1 <= int(choice) <= len(images[:10]) else 1
    selected_ami = images[choice - 1]['ImageId']
    print(f"Selected AMI: {selected_ami}")
    return selected_ami


def create_instance():
    print_header("Create EC2 Instance")

    region_options = {"1": "ap-south-1", "2": "us-east-1", "3": "us-west-2", "4": "eu-north-1"}
    print("\nSelect AWS Region:")
    for key, value in region_options.items():
        print(f"  {key} - {value}")
    region_choice = input("Enter region number (default 1): ").strip() or "1"
    region = region_options.get(region_choice, "ap-south-1")

    ec2 = get_ec2_client(region)

    existing_keys = list_key_pairs(ec2)
    key_input = input("\nEnter Key Pair Name OR number from list: ").strip()

    if not key_input:
        print("Key Pair name is required."); return

    if key_input.isdigit():
        idx = int(key_input) - 1
        if 0 <= idx < len(existing_keys):
            key_name = existing_keys[idx]['KeyName']
            print(f"✅ Using existing Key Pair: '{key_name}'")
        else:
            print("Invalid selection."); return
    else:
        key_name = key_input
        create_key_pair(ec2, key_name)

    existing_sgs = list_security_groups(ec2)
    sg_input = input("\nEnter Security Group Name/ID OR number from list (default 1): ").strip() or "1"
    if sg_input.isdigit():
        idx = int(sg_input) - 1
        if 0 <= idx < len(existing_sgs):
            security_group_id = existing_sgs[idx]['GroupId']
            print(f"Selected SG: {existing_sgs[idx]['GroupName']} ({security_group_id})")
        else:
            print("Invalid selection."); return
    else:
        security_group_id = get_or_create_security_group(ec2, sg_input)

    print("\nSelect Instance Type:")
    print("1 - t3.small  (2vCPU, 2GiB)  — Linux Practice")
    print("2 - t3.medium (2vCPU, 4GiB)  — Jenkins / Docker / K8S")
    print("3 - t3.large  (2vCPU, 8GiB)  — Kubernetes Setup")
    instance_type_map = {"1": "t3.small", "2": "t3.medium", "3": "t3.large"}
    instance_type = instance_type_map.get(input("Enter number (default 1): ").strip() or "1", "t3.small")
    print(f"Selected Instance Type: {instance_type}")

    ami_id = select_ami(ec2)

    storage_size = input("\nRoot Storage Size in GB (default 20): ").strip() or "20"

    add_volume = input("\nAdd an additional EBS volume? (y/n, default n): ").strip().lower() or "n"
    additional_volume = None
    if add_volume == "y":
        vol_size = input("Additional EBS volume size in GB: ").strip()
        if vol_size.isdigit() and int(vol_size) > 0:
            additional_volume = int(vol_size)
        else:
            print("Invalid size, skipping.")

    default_user_data_file = "temp-swap-setup-file.txt"
    if os.path.isfile(default_user_data_file):
        user_data_file = default_user_data_file
    else:
        user_data_file = input("\nUser Data file not found. Enter path: ").strip()
        if not os.path.isfile(user_data_file):
            print("Error: User Data file does not exist."); return
    with open(user_data_file, 'r') as f:
        user_data = f.read()

    instance_count = int(input("\nNumber of instances to create (default 1): ").strip() or "1")
    if instance_count <= 0:
        print("Instance count must be at least 1."); return

    now = datetime.now().strftime("%Y-%m-%d-%H-%M")
    default_name = f"Instance-{now}"
    if instance_count > 1:
        instance_names = []
        for i in range(instance_count):
            name = input(f"Name for instance {i+1} (default {default_name}-{i+1}): ").strip() or f"{default_name}-{i+1}"
            instance_names.append(name)
    else:
        name = input(f"Name for instance (default {default_name}): ").strip() or default_name
        instance_names = [name]

    block_device_mappings = [{
        "DeviceName": "/dev/xvda",
        "Ebs": {"VolumeSize": int(storage_size), "DeleteOnTermination": True, "VolumeType": "gp2"}
    }]
    if additional_volume:
        block_device_mappings.append({
            "DeviceName": "/dev/sdf",
            "Ebs": {"VolumeSize": additional_volume, "DeleteOnTermination": True, "VolumeType": "gp2"}
        })

    print("\nLaunching instances...")
    try:
        instances = ec2.run_instances(
            ImageId=ami_id,
            MinCount=instance_count,
            MaxCount=instance_count,
            InstanceType=instance_type,
            KeyName=key_name,
            SecurityGroupIds=[security_group_id],
            BlockDeviceMappings=block_device_mappings,
            UserData=user_data,
        )
        instance_ids = [i['InstanceId'] for i in instances['Instances']]
        print(f"\n✅ Launched instances: {', '.join(instance_ids)}")

        for instance_id, name in zip(instance_ids, instance_names):
            ec2.create_tags(Resources=[instance_id], Tags=[{"Key": "Name", "Value": name}])
        print("Instances tagged successfully.")

        response = ec2.describe_instances(InstanceIds=instance_ids)
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                print(f"  ID: {instance['InstanceId']}, Public IP: {instance.get('PublicIpAddress', 'N/A')}")

    except Exception as e:
        print(f"Error launching instances: {e}")


# ─────────────────────────────────────────────
#  3. DELETE / REMOVE AWS RESOURCES
# ─────────────────────────────────────────────

# ── 3a. EC2 Instances ──────────────────────

def fetch_instances_for_deletion():
    ec2 = get_ec2_client()
    response = ec2.describe_instances()
    instances = []
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            name = "No Name"
            for tag in instance.get('Tags', []):
                if tag['Key'] == 'Name':
                    name = tag['Value']
            instances.append({
                'InstanceName': name,
                'State': instance['State']['Name'],
                'InstanceId': instance['InstanceId']
            })
    return instances


def terminate_instances(instance_ids, instances):
    ec2 = get_ec2_client()
    print(f"\nTerminating: {', '.join(instance_ids)}...")
    response = ec2.terminate_instances(InstanceIds=instance_ids)
    print("\nTermination initiated:")
    for inst in response['TerminatingInstances']:
        iid   = inst['InstanceId']
        state = inst['CurrentState']['Name']
        name  = next((i['InstanceName'] for i in instances if i['InstanceId'] == iid), iid)
        print(f"  - {name}: {state}")
    print("\nWaiting for termination...")
    terminated = []
    while len(terminated) < len(instance_ids):
        time.sleep(10)
        status = ec2.describe_instances(InstanceIds=instance_ids)
        for reservation in status['Reservations']:
            for inst in reservation['Instances']:
                if inst['State']['Name'] == 'terminated' and inst['InstanceId'] not in terminated:
                    name = next((i['InstanceName'] for i in instances if i['InstanceId'] == inst['InstanceId']), inst['InstanceId'])
                    terminated.append(inst['InstanceId'])
                    print(f"  ✅ {name}: terminated")
    print("\nAll selected instances have been terminated.")


def delete_ec2_instances():
    print_header("Delete EC2 Instances")
    try:
        instances = fetch_instances_for_deletion()
        if not instances:
            print("No EC2 instances found.")
            return
        TW = 70
        print(f"\n{'No':<4}{'Name':<25}{'Instance ID':<22}{'State'}")
        print_divider(TW)
        for idx, inst in enumerate(instances):
            print(f"  {idx+1:<3}{inst['InstanceName']:<25}{inst['InstanceId']:<22}{inst['State']}")
        print_divider(TW)
        user_input = input("\nDelete ALL instances? (yes/no): ").strip().lower()
        if user_input == 'yes':
            confirm = input("⚠  Are you sure? This cannot be undone. (yes/no): ").strip().lower()
            if confirm == 'yes':
                terminate_instances([i['InstanceId'] for i in instances], instances)
            else:
                print("Cancelled.")
        else:
            selected = input("\nEnter instance numbers to delete (e.g. 1, 3): ")
            indexes = [int(i.strip()) - 1 for i in selected.split(',')]
            if all(0 <= idx < len(instances) for idx in indexes):
                ids_to_delete = [instances[idx]['InstanceId'] for idx in indexes]
                print("\nSelected for deletion:")
                for idx in indexes:
                    print(f"  - {instances[idx]['InstanceName']} ({instances[idx]['State']})")
                confirm = input("Confirm deletion? (yes/no): ").strip().lower()
                if confirm == 'yes':
                    terminate_instances(ids_to_delete, instances)
                else:
                    print("Deletion cancelled.")
            else:
                print("Invalid selection.")
    except ValueError:
        print("Invalid input. Please enter numbers separated by commas.")
    except Exception as e:
        print(f"Error: {e}")


# ── 3b. Remove Port from Security Group ────

def remove_port():
    print_header("Remove Port from Security Group")
    try:
        ec2 = get_ec2_client()
        sgs = ec2.describe_security_groups()['SecurityGroups']
        TW  = 60
        print(f"\n{'No':<4}{'SG Name':<25}{'SG ID':<22}{'Open Ports'}")
        print_divider(TW + 30)
        for idx, sg in enumerate(sgs):
            print(f"  {idx+1:<3}{sg['GroupName'][:23]:<25}{sg['GroupId']:<22}{get_open_ports(sg)}")
        print_divider(TW + 30)
        choice = input("\nSelect Security Group Number: ").strip()
        if not choice.isdigit() or not (1 <= int(choice) <= len(sgs)):
            print("Invalid selection."); return
        selected_sg = sgs[int(choice) - 1]
        sg_id   = selected_sg['GroupId']
        sg_name = selected_sg['GroupName']
        print(f"\nSelected: {sg_name} ({sg_id})")

        rules = []
        print(f"\n{'No':<4}{'Protocol':<12}{'From Port':<12}{'To Port':<12}{'Source'}")
        print_divider(60)
        for rule in selected_sg.get('IpPermissions', []):
            protocol  = rule.get('IpProtocol', 'all')
            from_port = rule.get('FromPort', 'ALL')
            to_port   = rule.get('ToPort',   'ALL')
            for ip in rule.get('IpRanges', []):
                rules.append({'protocol': protocol, 'from': from_port, 'to': to_port, 'cidr': ip['CidrIp']})
                idx = len(rules)
                print(f"  {idx:<3}{protocol:<12}{str(from_port):<12}{str(to_port):<12}{ip['CidrIp']}")
        print_divider(60)
        if not rules:
            print("No inbound rules found."); return

        r_choice = input("\nEnter rule number to remove: ").strip()
        if not r_choice.isdigit() or not (1 <= int(r_choice) <= len(rules)):
            print("Invalid selection."); return
        rule = rules[int(r_choice) - 1]
        perm = {
            'IpProtocol': rule['protocol'],
            'IpRanges':   [{'CidrIp': rule['cidr']}]
        }
        if rule['from'] != 'ALL':
            perm['FromPort'] = rule['from']
            perm['ToPort']   = rule['to']
        ec2.revoke_security_group_ingress(GroupId=sg_id, IpPermissions=[perm])
        print(f"\n✅ Rule removed from '{sg_name}'")
        updated = ec2.describe_security_groups(GroupIds=[sg_id])['SecurityGroups'][0]
        print(f"Remaining Ports: {get_open_ports(updated)}")
    except ClientError as e:
        print(f"\nAWS Error: {e}")
    except Exception as e:
        print(f"\nError: {e}")


# ── 3c. Delete Security Group ──────────────

def delete_security_group():
    print_header("Delete Security Group")
    try:
        ec2 = get_ec2_client()
        sgs = [sg for sg in ec2.describe_security_groups()['SecurityGroups']
               if sg['GroupName'] != 'default']
        if not sgs:
            print("No deletable security groups found (default SG cannot be deleted).")
            return
        TW = 90
        print(f"\n{'No':<4}{'SG Name':<25}{'SG ID':<22}{'Open Ports'}")
        print_divider(TW)
        for idx, sg in enumerate(sgs):
            print(f"  {idx+1:<3}{sg['GroupName'][:23]:<25}{sg['GroupId']:<22}{get_open_ports(sg)}")
        print_divider(TW)
        choice = input("\nSelect Security Group Number to Delete: ").strip()
        if not choice.isdigit() or not (1 <= int(choice) <= len(sgs)):
            print("Invalid selection."); return
        selected = sgs[int(choice) - 1]
        print(f"\nSelected: {selected['GroupName']} ({selected['GroupId']})")
        confirm = input("⚠  Are you sure you want to delete this Security Group? (yes/no): ").strip().lower()
        if confirm == 'yes':
            ec2.delete_security_group(GroupId=selected['GroupId'])
            print(f"✅ Security Group '{selected['GroupName']}' deleted.")
        else:
            print("Cancelled.")
    except ClientError as e:
        if 'DependencyViolation' in str(e):
            print("\n⚠  Cannot delete: Security Group is still attached to an instance.")
        else:
            print(f"\nAWS Error: {e}")
    except Exception as e:
        print(f"\nError: {e}")


# ── 3d. Delete Key Pair ────────────────────

def delete_key_pair():
    print_header("Delete Key Pair")
    try:
        ec2 = get_ec2_client()
        kps = ec2.describe_key_pairs().get('KeyPairs', [])
        if not kps:
            print("No Key Pairs found."); return
        print(f"\n{'No':<4}{'Key Pair Name':<30}{'Key ID'}")
        print_divider(60)
        for idx, kp in enumerate(kps):
            print(f"  {idx+1:<3}{kp['KeyName']:<30}{kp.get('KeyPairId','N/A')}")
        print_divider(60)
        choice = input("\nSelect Key Pair Number to Delete: ").strip()
        if not choice.isdigit() or not (1 <= int(choice) <= len(kps)):
            print("Invalid selection."); return
        selected = kps[int(choice) - 1]
        confirm = input(f"⚠  Delete Key Pair '{selected['KeyName']}'? (yes/no): ").strip().lower()
        if confirm == 'yes':
            ec2.delete_key_pair(KeyName=selected['KeyName'])
            print(f"✅ Key Pair '{selected['KeyName']}' deleted.")
            pem = f"{selected['KeyName']}.pem"
            if os.path.isfile(pem):
                os.remove(pem)
                print(f"   Local file '{pem}' also removed.")
        else:
            print("Cancelled.")
    except Exception as e:
        print(f"\nError: {e}")


# ── 3e. Delete EBS Volume ──────────────────

def delete_ebs_volume():
    print_header("Delete EBS Volume")
    try:
        ec2 = get_ec2_client()
        vols = [v for v in ec2.describe_volumes()['Volumes'] if v['State'] == 'available']
        if not vols:
            print("No unattached (available) EBS volumes found."); return
        TW = 80
        print(f"\n{'No':<4}{'Volume ID':<24}{'Size (GB)':<12}{'State':<14}{'AZ'}")
        print_divider(TW)
        for idx, v in enumerate(vols):
            print(f"  {idx+1:<3}{v['VolumeId']:<24}{v['Size']:<12}{v['State']:<14}{v['AvailabilityZone']}")
        print_divider(TW)
        choice = input("\nSelect Volume Number to Delete: ").strip()
        if not choice.isdigit() or not (1 <= int(choice) <= len(vols)):
            print("Invalid selection."); return
        selected = vols[int(choice) - 1]
        confirm = input(f"⚠  Delete Volume '{selected['VolumeId']}' ({selected['Size']} GB)? (yes/no): ").strip().lower()
        if confirm == 'yes':
            ec2.delete_volume(VolumeId=selected['VolumeId'])
            print(f"✅ Volume '{selected['VolumeId']}' deleted.")
        else:
            print("Cancelled.")
    except Exception as e:
        print(f"\nError: {e}")


# ── 3f. Release Elastic IP ─────────────────

def release_elastic_ip():
    print_header("Release Elastic IP")
    try:
        ec2  = get_ec2_client()
        eips = ec2.describe_addresses()['Addresses']
        if not eips:
            print("No Elastic IPs found."); return
        TW = 90
        print(f"\n{'No':<4}{'Public IP':<18}{'Allocation ID':<26}{'Associated Instance'}")
        print_divider(TW)
        for idx, eip in enumerate(eips):
            assoc = eip.get('InstanceId', 'Not associated')
            print(f"  {idx+1:<3}{eip.get('PublicIp','N/A'):<18}{eip.get('AllocationId','N/A'):<26}{assoc}")
        print_divider(TW)
        choice = input("\nSelect Elastic IP Number to Release: ").strip()
        if not choice.isdigit() or not (1 <= int(choice) <= len(eips)):
            print("Invalid selection."); return
        selected = eips[int(choice) - 1]
        confirm = input(f"⚠  Release '{selected['PublicIp']}'? (yes/no): ").strip().lower()
        if confirm == 'yes':
            ec2.release_address(AllocationId=selected['AllocationId'])
            print(f"✅ Elastic IP '{selected['PublicIp']}' released.")
        else:
            print("Cancelled.")
    except ClientError as e:
        if 'AuthFailure' in str(e) or 'InvalidAddress' in str(e):
            print(f"\n⚠  Cannot release: {e}")
        else:
            print(f"\nAWS Error: {e}")
    except Exception as e:
        print(f"\nError: {e}")


# ── 3g. Delete S3 Bucket ──────────────────

def delete_s3_bucket():
    print_header("Delete S3 Bucket")
    try:
        s3      = boto3.client('s3')
        buckets = s3.list_buckets().get('Buckets', [])
        if not buckets:
            print("No S3 buckets found."); return
        print(f"\n{'No':<4}{'Bucket Name':<40}{'Creation Date'}")
        print_divider(70)
        for idx, b in enumerate(buckets):
            print(f"  {idx+1:<3}{b['Name']:<40}{str(b['CreationDate'])[:10]}")
        print_divider(70)
        choice = input("\nSelect Bucket Number to Delete: ").strip()
        if not choice.isdigit() or not (1 <= int(choice) <= len(buckets)):
            print("Invalid selection."); return
        selected = buckets[int(choice) - 1]
        bname    = selected['Name']
        print(f"\n⚠  This will delete ALL objects inside '{bname}' and the bucket itself.")
        confirm = input("Type the bucket name to confirm: ").strip()
        if confirm != bname:
            print("Name did not match. Cancelled."); return
        # Delete all objects first
        paginator = s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=bname):
            objects = [{'Key': obj['Key']} for obj in page.get('Contents', [])]
            if objects:
                s3.delete_objects(Bucket=bname, Delete={'Objects': objects})
                print(f"  Deleted {len(objects)} object(s)...")
        # Delete versioned objects if any
        try:
            for page in s3.get_paginator('list_object_versions').paginate(Bucket=bname):
                versions = [{'Key': v['Key'], 'VersionId': v['VersionId']}
                            for v in page.get('Versions', []) + page.get('DeleteMarkers', [])]
                if versions:
                    s3.delete_objects(Bucket=bname, Delete={'Objects': versions})
        except Exception:
            pass
        s3.delete_bucket(Bucket=bname)
        print(f"✅ Bucket '{bname}' deleted.")
    except ClientError as e:
        print(f"\nAWS Error: {e}")
    except Exception as e:
        print(f"\nError: {e}")


# ── 3. Main Delete/Remove Menu ─────────────

def delete_instances():
    W = 46
    while True:
        print_header("Delete / Remove AWS Resources")
        top    = "┌" + "─" * W + "┐"
        title  = "│" + " Select Resource to Delete ".center(W) + "│"
        sep    = "├" + "─" * W + "┤"
        bottom = "└" + "─" * W + "┘"
        items  = [
            ("1", "Delete EC2 Instance(s)"),
            ("2", "Remove Port from Security Group"),
            ("3", "Delete Security Group"),
            ("4", "Delete Key Pair"),
            ("5", "Delete EBS Volume"),
            ("6", "Release Elastic IP"),
            ("7", "Delete S3 Bucket"),
            ("8", "Back to Main Menu"),
        ]
        print(top); print(title); print(sep)
        for key, label in items:
            row = f"  {key}.  {label}"
            print("│" + row.ljust(W) + "│")
        print(bottom)

        choice = input("\nEnter your choice: ").strip()
        actions = {
            "1": delete_ec2_instances,
            "2": remove_port,
            "3": delete_security_group,
            "4": delete_key_pair,
            "5": delete_ebs_volume,
            "6": release_elastic_ip,
            "7": delete_s3_bucket,
        }
        if choice == "8" or choice == "":
            return
        elif choice in actions:
            actions[choice]()
        else:
            print("Invalid choice. Enter 1–8.")


# ─────────────────────────────────────────────
#  4. OPEN PORT (ADD PORT TO SECURITY GROUP)
# ─────────────────────────────────────────────

def get_open_ports(security_group):
    ports = []
    for rule in security_group.get('IpPermissions', []):
        protocol = rule.get('IpProtocol')
        if protocol == '-1':
            ports.append("ALL")
        elif 'FromPort' in rule:
            fp, tp = rule['FromPort'], rule['ToPort']
            ports.append(f"{protocol}/{fp}" if fp == tp else f"{protocol}/{fp}-{tp}")
    return ", ".join(ports) if ports else "None"


def display_updated_rules(sg):
    print("\nUpdated Inbound Rules")
    print_divider(80)
    print(f"{'Protocol':<12}{'From Port':<12}{'To Port':<12}{'Source'}")
    print_divider(80)
    for rule in sg.get('IpPermissions', []):
        protocol = rule.get('IpProtocol', 'all')
        from_port = rule.get('FromPort', 'ALL')
        to_port = rule.get('ToPort', 'ALL')
        for ip in rule.get('IpRanges', []):
            print(f"{protocol:<12}{str(from_port):<12}{str(to_port):<12}{ip['CidrIp']}")
    print_divider(80)


def open_port():
    print_header("Open Port in Security Group")
    try:
        ec2 = get_ec2_client()
        security_groups = ec2.describe_security_groups()['SecurityGroups']
        reservations = ec2.describe_instances()['Reservations']

        # Column widths: 4+22+22+22+16+16+25 = 127
        TW = 127
        print("\nAvailable Security Groups")
        print_divider(TW)
        print(
            f"{'No':<4}{'SG Name':<22}{'SG ID':<22}"
            f"{'Instance Name':<22}{'Public IP':<16}{'Private IP':<16}{'Ports':<25}"
        )
        print_divider(TW)

        row_num = 1
        row_map = {}  # maps row number -> actual sg object

        for sg in security_groups:
            sg_name = sg['GroupName'][:20]
            sg_id   = sg['GroupId'][:20]
            ports   = get_open_ports(sg)
            if len(ports) > 22:
                ports = ports[:22] + "..."

            found = False
            for reservation in reservations:
                for instance in reservation['Instances']:
                    for attached_sg in instance.get('SecurityGroups', []):
                        if attached_sg['GroupId'] == sg['GroupId']:
                            found = True
                            instance_name = next(
                                (t['Value'] for t in instance.get('Tags', []) if t['Key'] == 'Name'), 'N/A'
                            )[:20]
                            public_ip  = instance.get('PublicIpAddress', 'N/A')
                            private_ip = instance.get('PrivateIpAddress', 'N/A')
                            print(
                                f"{row_num:<4}{sg_name:<22}{sg_id:<22}"
                                f"{instance_name:<22}{public_ip:<16}{private_ip:<16}{ports:<25}"
                            )
                            row_map[row_num] = sg
                            row_num += 1

            if not found:
                print(
                    f"{row_num:<4}{sg_name:<22}{sg_id:<22}"
                    f"{'No Instances':<22}{'N/A':<16}{'N/A':<16}{ports:<25}"
                )
                row_map[row_num] = sg
                row_num += 1

        print_divider(TW)

        sg_choice = input("\nSelect Security Group Number (or press Enter to Exit): ").strip()
        if not sg_choice:
            print("Returning to main menu.")
            return

        if not sg_choice.isdigit() or int(sg_choice) not in row_map:
            print("Invalid selection.")
            return

        selected_sg = row_map[int(sg_choice)]
        sg_id = selected_sg['GroupId']
        sg_name = selected_sg['GroupName']

        print(f"\nSelected: {sg_name} ({sg_id})")
        print(f"Open Ports: {get_open_ports(selected_sg)}")

        while True:
            print("\n┌────────────────────────────────────┐")
            print("│  What would you like to do?        │")
            print("├────────────────────────────────────┤")
            print("│  1.  Open a Port                   │")
            print("│  2.  Exit to Main Menu             │")
            print("└────────────────────────────────────┘")

            action = input("\nEnter your choice: ").strip()

            if action == "2" or action == "":
                print("Returning to main menu.")
                return

            elif action == "1":
                try:
                    port = int(input("\nEnter Port Number to Open: "))
                    ec2.authorize_security_group_ingress(
                        GroupId=sg_id,
                        IpPermissions=[{
                            'IpProtocol': 'tcp',
                            'FromPort': port,
                            'ToPort': port,
                            'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': f'Port {port} Access'}]
                        }]
                    )
                    print(f"\n✅ Port {port} opened successfully in '{sg_name}'")

                    updated_sg = ec2.describe_security_groups(GroupIds=[sg_id])['SecurityGroups'][0]
                    print(f"Updated Ports: {get_open_ports(updated_sg)}")
                    display_updated_rules(updated_sg)

                except ClientError as e:
                    if "InvalidPermission.Duplicate" in str(e):
                        print(f"\n⚠  Port {port} already exists in '{sg_name}'.")
                    else:
                        print(f"\nAWS Error: {e}")
                except ValueError:
                    print("\nPlease enter a valid port number.")
            else:
                print("Invalid choice. Enter 1 or 2.")

    except ClientError as e:
        print(f"\nAWS Error: {e}")
    except ValueError:
        print("\nPlease enter a valid number.")
    except Exception as e:
        print(f"\nError: {e}")


# ─────────────────────────────────────────────
#  5. START / STOP EC2 INSTANCES
# ─────────────────────────────────────────────

def _list_instances_for_action(ec2, state_filter=None):
    """Return instances optionally filtered by state."""
    response = ec2.describe_instances()
    instances = []
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            state = instance['State']['Name']
            if state_filter and state not in state_filter:
                continue
            name = next((t['Value'] for t in instance.get('Tags', []) if t['Key'] == 'Name'), 'No Name')
            instances.append({
                'InstanceId':   instance['InstanceId'],
                'InstanceName': name,
                'State':        state,
                'PublicIp':     instance.get('PublicIpAddress', 'N/A'),
                'PrivateIp':    instance.get('PrivateIpAddress', 'N/A'),
            })
    return instances


def _print_instance_table(instances):
    TW = 90
    print(f"\n{'No':<4}{'Name':<25}{'Instance ID':<22}{'State':<14}{'Public IP':<16}{'Private IP'}")
    print_divider(TW)
    for idx, inst in enumerate(instances):
        print(f"  {idx+1:<3}{inst['InstanceName']:<25}{inst['InstanceId']:<22}"
              f"{inst['State']:<14}{inst['PublicIp']:<16}{inst['PrivateIp']}")
    print_divider(TW)


def _pick_instances(instances, action_label):
    _print_instance_table(instances)
    raw = input(f"\nEnter instance numbers to {action_label} (e.g. 1,3 or 'all'): ").strip().lower()
    if raw == 'all':
        return instances
    indexes = [int(i.strip()) - 1 for i in raw.split(',')]
    if not all(0 <= i < len(instances) for i in indexes):
        print("Invalid selection."); return []
    return [instances[i] for i in indexes]


def start_stop_instances():
    W = 46
    while True:
        print_header("Start / Stop EC2 Instances")
        top    = "┌" + "─" * W + "┐"
        title  = "│" + " Select Action ".center(W) + "│"
        sep    = "├" + "─" * W + "┤"
        bottom = "└" + "─" * W + "┘"
        items  = [("1","Start Instance(s)"), ("2","Stop Instance(s)"),
                  ("3","Reboot Instance(s)"), ("4","Instance Status Check"),
                  ("5","Back to Main Menu")]
        print(top); print(title); print(sep)
        for k, l in items:
            print("│" + f"  {k}.  {l}".ljust(W) + "│")
        print(bottom)

        choice = input("\nEnter your choice: ").strip()

        ec2 = get_ec2_client()

        if choice == "5" or choice == "":
            return

        elif choice == "1":   # START
            insts = _list_instances_for_action(ec2, state_filter=['stopped'])
            if not insts:
                print("No stopped instances found."); continue
            selected = _pick_instances(insts, "start")
            if not selected: continue
            ids = [i['InstanceId'] for i in selected]
            ec2.start_instances(InstanceIds=ids)
            print(f"\n✅ Start initiated for: {', '.join(ids)}")
            print("Waiting for instances to be running...")
            waiter = ec2.get_waiter('instance_running')
            waiter.wait(InstanceIds=ids)
            print("✅ All selected instances are now running.")

        elif choice == "2":   # STOP
            insts = _list_instances_for_action(ec2, state_filter=['running'])
            if not insts:
                print("No running instances found."); continue
            selected = _pick_instances(insts, "stop")
            if not selected: continue
            ids = [i['InstanceId'] for i in selected]
            confirm = input(f"⚠  Stop {len(ids)} instance(s)? (yes/no): ").strip().lower()
            if confirm == 'yes':
                ec2.stop_instances(InstanceIds=ids)
                print(f"\n✅ Stop initiated for: {', '.join(ids)}")
                print("Waiting for instances to stop...")
                waiter = ec2.get_waiter('instance_stopped')
                waiter.wait(InstanceIds=ids)
                print("✅ All selected instances are now stopped.")
            else:
                print("Cancelled.")

        elif choice == "3":   # REBOOT
            insts = _list_instances_for_action(ec2, state_filter=['running'])
            if not insts:
                print("No running instances found."); continue
            selected = _pick_instances(insts, "reboot")
            if not selected: continue
            ids = [i['InstanceId'] for i in selected]
            confirm = input(f"⚠  Reboot {len(ids)} instance(s)? (yes/no): ").strip().lower()
            if confirm == 'yes':
                ec2.reboot_instances(InstanceIds=ids)
                print(f"✅ Reboot initiated for: {', '.join(ids)}")
            else:
                print("Cancelled.")

        elif choice == "4":   # STATUS CHECK
            insts = _list_instances_for_action(ec2)
            if not insts:
                print("No instances found."); continue
            ids = [i['InstanceId'] for i in insts]
            statuses = ec2.describe_instance_status(InstanceIds=ids, IncludeAllInstances=True)['InstanceStatuses']
            TW = 95
            print(f"\n{'No':<4}{'Name':<25}{'Instance ID':<22}{'State':<14}{'System Check':<16}{'Instance Check'}")
            print_divider(TW)
            for idx, inst in enumerate(insts):
                st = next((s for s in statuses if s['InstanceId'] == inst['InstanceId']), None)
                sys_chk  = st['SystemStatus']['Status']   if st else 'N/A'
                inst_chk = st['InstanceStatus']['Status'] if st else 'N/A'
                print(f"  {idx+1:<3}{inst['InstanceName']:<25}{inst['InstanceId']:<22}"
                      f"{inst['State']:<14}{sys_chk:<16}{inst_chk}")
            print_divider(TW)
        else:
            print("Invalid choice. Enter 1–5.")


# ─────────────────────────────────────────────
#  6. IAM ROLES
# ─────────────────────────────────────────────

def iam_menu():
    W = 46
    while True:
        print_header("IAM Roles Manager")
        top    = "┌" + "─" * W + "┐"
        title  = "│" + " Select Action ".center(W) + "│"
        sep    = "├" + "─" * W + "┤"
        bottom = "└" + "─" * W + "┘"
        items  = [("1","List IAM Roles"), ("2","Create IAM Role"),
                  ("3","Attach Policy to Role"), ("4","Detach Policy from Role"),
                  ("5","Delete IAM Role"), ("6","Back to Main Menu")]
        print(top); print(title); print(sep)
        for k, l in items:
            print("│" + f"  {k}.  {l}".ljust(W) + "│")
        print(bottom)

        choice = input("\nEnter your choice: ").strip()
        iam = boto3.client('iam')

        if choice == "6" or choice == "":
            return

        elif choice == "1":   # LIST ROLES
            roles = iam.list_roles()['Roles']
            if not roles:
                print("No IAM Roles found."); continue
            TW = 90
            print(f"\n{'No':<4}{'Role Name':<35}{'Created':<14}{'Description'}")
            print_divider(TW)
            for idx, r in enumerate(roles):
                desc = r.get('Description', '')[:25]
                created = str(r['CreateDate'])[:10]
                print(f"  {idx+1:<3}{r['RoleName']:<35}{created:<14}{desc}")
            print_divider(TW)

        elif choice == "2":   # CREATE ROLE
            role_name = input("\nEnter new Role Name: ").strip()
            if not role_name: print("Role name required."); continue
            print("\nSelect Trust Policy (who can assume this role):")
            print("  1 - EC2")
            print("  2 - Lambda")
            print("  3 - ECS Tasks")
            svc_map = {"1": "ec2.amazonaws.com", "2": "lambda.amazonaws.com", "3": "ecs-tasks.amazonaws.com"}
            svc_choice = input("Enter number (default 1): ").strip() or "1"
            service = svc_map.get(svc_choice, "ec2.amazonaws.com")
            import json
            trust_policy = json.dumps({
                "Version": "2012-10-17",
                "Statement": [{"Effect": "Allow", "Principal": {"Service": service},
                               "Action": "sts:AssumeRole"}]
            })
            description = input("Enter Role Description (optional): ").strip()
            try:
                iam.create_role(RoleName=role_name, AssumeRolePolicyDocument=trust_policy,
                                Description=description)
                print(f"✅ IAM Role '{role_name}' created (trust: {service})")
            except ClientError as e:
                print(f"AWS Error: {e}")

        elif choice == "3":   # ATTACH POLICY
            roles = iam.list_roles()['Roles']
            if not roles: print("No roles found."); continue
            print("\nRoles:")
            for idx, r in enumerate(roles):
                print(f"  {idx+1}. {r['RoleName']}")
            rc = input("Select Role Number: ").strip()
            if not rc.isdigit() or not (1 <= int(rc) <= len(roles)):
                print("Invalid selection."); continue
            role_name = roles[int(rc)-1]['RoleName']
            print("\nCommon AWS Managed Policies:")
            common = [
                ("1",  "AmazonEC2FullAccess",           "arn:aws:iam::aws:policy/AmazonEC2FullAccess"),
                ("2",  "AmazonS3FullAccess",             "arn:aws:iam::aws:policy/AmazonS3FullAccess"),
                ("3",  "AmazonRDSFullAccess",            "arn:aws:iam::aws:policy/AmazonRDSFullAccess"),
                ("4",  "AdministratorAccess",            "arn:aws:iam::aws:policy/AdministratorAccess"),
                ("5",  "ReadOnlyAccess",                 "arn:aws:iam::aws:policy/ReadOnlyAccess"),
                ("6",  "AmazonEKSClusterPolicy",         "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"),
                ("7",  "AWSLambdaBasicExecutionRole",    "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"),
                ("8",  "Enter custom policy ARN", None),
            ]
            for k, name, _ in common:
                print(f"  {k}. {name}")
            pc = input("Select Policy Number: ").strip()
            pol = next((p for p in common if p[0] == pc), None)
            if not pol: print("Invalid selection."); continue
            if pol[2] is None:
                arn = input("Enter full Policy ARN: ").strip()
            else:
                arn = pol[2]
            try:
                iam.attach_role_policy(RoleName=role_name, PolicyArn=arn)
                print(f"✅ Policy attached to '{role_name}'")
            except ClientError as e:
                print(f"AWS Error: {e}")

        elif choice == "4":   # DETACH POLICY
            roles = iam.list_roles()['Roles']
            if not roles: print("No roles found."); continue
            print("\nRoles:")
            for idx, r in enumerate(roles):
                print(f"  {idx+1}. {r['RoleName']}")
            rc = input("Select Role Number: ").strip()
            if not rc.isdigit() or not (1 <= int(rc) <= len(roles)):
                print("Invalid selection."); continue
            role_name = roles[int(rc)-1]['RoleName']
            attached  = iam.list_attached_role_policies(RoleName=role_name)['AttachedPolicies']
            if not attached: print(f"No policies attached to '{role_name}'."); continue
            print(f"\nPolicies attached to '{role_name}':")
            for idx, p in enumerate(attached):
                print(f"  {idx+1}. {p['PolicyName']}")
            pc = input("Select Policy Number to Detach: ").strip()
            if not pc.isdigit() or not (1 <= int(pc) <= len(attached)):
                print("Invalid selection."); continue
            pol = attached[int(pc)-1]
            confirm = input(f"⚠  Detach '{pol['PolicyName']}' from '{role_name}'? (yes/no): ").strip().lower()
            if confirm == 'yes':
                iam.detach_role_policy(RoleName=role_name, PolicyArn=pol['PolicyArn'])
                print(f"✅ Policy detached from '{role_name}'")
            else:
                print("Cancelled.")

        elif choice == "5":   # DELETE ROLE
            roles = iam.list_roles()['Roles']
            if not roles: print("No roles found."); continue
            print("\nRoles:")
            for idx, r in enumerate(roles):
                print(f"  {idx+1}. {r['RoleName']}")
            rc = input("Select Role Number to Delete: ").strip()
            if not rc.isdigit() or not (1 <= int(rc) <= len(roles)):
                print("Invalid selection."); continue
            role_name = roles[int(rc)-1]['RoleName']
            confirm = input(f"⚠  Delete Role '{role_name}'? Attached policies will be detached first. (yes/no): ").strip().lower()
            if confirm == 'yes':
                try:
                    # Detach all policies first
                    for p in iam.list_attached_role_policies(RoleName=role_name)['AttachedPolicies']:
                        iam.detach_role_policy(RoleName=role_name, PolicyArn=p['PolicyArn'])
                    # Remove inline policies
                    for p in iam.list_role_policies(RoleName=role_name)['PolicyNames']:
                        iam.delete_role_policy(RoleName=role_name, PolicyName=p)
                    iam.delete_role(RoleName=role_name)
                    print(f"✅ IAM Role '{role_name}' deleted.")
                except ClientError as e:
                    print(f"AWS Error: {e}")
            else:
                print("Cancelled.")
        else:
            print("Invalid choice. Enter 1–6.")


# ─────────────────────────────────────────────
#  7. VPC MANAGER
# ─────────────────────────────────────────────

def vpc_menu():
    W = 46
    while True:
        print_header("VPC Manager")
        top    = "┌" + "─" * W + "┐"
        title  = "│" + " Select Action ".center(W) + "│"
        sep    = "├" + "─" * W + "┤"
        bottom = "└" + "─" * W + "┘"
        items  = [("1","List VPCs"), ("2","Create VPC"),
                  ("3","List Subnets"), ("4","Create Subnet"),
                  ("5","List Internet Gateways"), ("6","Create & Attach Internet Gateway"),
                  ("7","List Route Tables"), ("8","Delete VPC"),
                  ("9","Back to Main Menu")]
        print(top); print(title); print(sep)
        for k, l in items:
            print("│" + f"  {k}.  {l}".ljust(W) + "│")
        print(bottom)

        choice = input("\nEnter your choice: ").strip()
        ec2 = get_ec2_client()

        if choice == "9" or choice == "":
            return

        elif choice == "1":   # LIST VPCs
            vpcs = ec2.describe_vpcs()['Vpcs']
            if not vpcs: print("No VPCs found."); continue
            TW = 90
            print(f"\n{'No':<4}{'VPC ID':<22}{'CIDR':<20}{'Default':<10}{'Name'}")
            print_divider(TW)
            for idx, v in enumerate(vpcs):
                name = next((t['Value'] for t in v.get('Tags', []) if t['Key'] == 'Name'), 'N/A')
                print(f"  {idx+1:<3}{v['VpcId']:<22}{v['CidrBlock']:<20}{str(v['IsDefault']):<10}{name}")
            print_divider(TW)

        elif choice == "2":   # CREATE VPC
            cidr = input("\nEnter CIDR block (e.g. 10.0.0.0/16): ").strip()
            name = input("Enter VPC Name: ").strip()
            if not cidr: print("CIDR required."); continue
            try:
                vpc = ec2.create_vpc(CidrBlock=cidr)['Vpc']
                vpc_id = vpc['VpcId']
                if name:
                    ec2.create_tags(Resources=[vpc_id], Tags=[{'Key': 'Name', 'Value': name}])
                ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={'Value': True})
                ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport={'Value': True})
                print(f"✅ VPC '{vpc_id}' created with CIDR {cidr}")
            except ClientError as e:
                print(f"AWS Error: {e}")

        elif choice == "3":   # LIST SUBNETS
            vpcs    = ec2.describe_vpcs()['Vpcs']
            subnets = ec2.describe_subnets()['Subnets']
            if not subnets: print("No subnets found."); continue
            TW = 100
            print(f"\n{'No':<4}{'Subnet ID':<24}{'VPC ID':<22}{'CIDR':<20}{'AZ':<18}{'Name'}")
            print_divider(TW)
            for idx, s in enumerate(subnets):
                name = next((t['Value'] for t in s.get('Tags', []) if t['Key'] == 'Name'), 'N/A')
                print(f"  {idx+1:<3}{s['SubnetId']:<24}{s['VpcId']:<22}{s['CidrBlock']:<20}{s['AvailabilityZone']:<18}{name}")
            print_divider(TW)

        elif choice == "4":   # CREATE SUBNET
            vpcs = ec2.describe_vpcs()['Vpcs']
            if not vpcs: print("No VPCs found."); continue
            print("\nAvailable VPCs:")
            for idx, v in enumerate(vpcs):
                name = next((t['Value'] for t in v.get('Tags', []) if t['Key'] == 'Name'), 'N/A')
                print(f"  {idx+1}. {v['VpcId']} ({v['CidrBlock']}) — {name}")
            vc = input("Select VPC Number: ").strip()
            if not vc.isdigit() or not (1 <= int(vc) <= len(vpcs)):
                print("Invalid selection."); continue
            vpc_id = vpcs[int(vc)-1]['VpcId']
            cidr   = input("Enter Subnet CIDR (e.g. 10.0.1.0/24): ").strip()
            azs    = ec2.describe_availability_zones()['AvailabilityZones']
            print("\nAvailability Zones:")
            for idx, az in enumerate(azs):
                print(f"  {idx+1}. {az['ZoneName']}")
            azc = input("Select AZ Number (default 1): ").strip() or "1"
            az  = azs[int(azc)-1]['ZoneName'] if azc.isdigit() and 1 <= int(azc) <= len(azs) else azs[0]['ZoneName']
            name = input("Enter Subnet Name: ").strip()
            try:
                subnet = ec2.create_subnet(VpcId=vpc_id, CidrBlock=cidr, AvailabilityZone=az)['Subnet']
                if name:
                    ec2.create_tags(Resources=[subnet['SubnetId']], Tags=[{'Key': 'Name', 'Value': name}])
                print(f"✅ Subnet '{subnet['SubnetId']}' created in {az}")
            except ClientError as e:
                print(f"AWS Error: {e}")

        elif choice == "5":   # LIST IGWs
            igws = ec2.describe_internet_gateways()['InternetGateways']
            if not igws: print("No Internet Gateways found."); continue
            TW = 80
            print(f"\n{'No':<4}{'IGW ID':<26}{'Attached VPC':<24}{'Name'}")
            print_divider(TW)
            for idx, igw in enumerate(igws):
                name = next((t['Value'] for t in igw.get('Tags', []) if t['Key'] == 'Name'), 'N/A')
                vpc  = igw['Attachments'][0]['VpcId'] if igw['Attachments'] else 'Not attached'
                print(f"  {idx+1:<3}{igw['InternetGatewayId']:<26}{vpc:<24}{name}")
            print_divider(TW)

        elif choice == "6":   # CREATE & ATTACH IGW
            vpcs = ec2.describe_vpcs()['Vpcs']
            if not vpcs: print("No VPCs found."); continue
            print("\nAvailable VPCs:")
            for idx, v in enumerate(vpcs):
                name = next((t['Value'] for t in v.get('Tags', []) if t['Key'] == 'Name'), 'N/A')
                print(f"  {idx+1}. {v['VpcId']} — {name}")
            vc = input("Select VPC to attach IGW: ").strip()
            if not vc.isdigit() or not (1 <= int(vc) <= len(vpcs)):
                print("Invalid selection."); continue
            vpc_id = vpcs[int(vc)-1]['VpcId']
            name   = input("Enter IGW Name (optional): ").strip()
            try:
                igw    = ec2.create_internet_gateway()['InternetGateway']
                igw_id = igw['InternetGatewayId']
                if name:
                    ec2.create_tags(Resources=[igw_id], Tags=[{'Key': 'Name', 'Value': name}])
                ec2.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
                print(f"✅ Internet Gateway '{igw_id}' created and attached to '{vpc_id}'")
            except ClientError as e:
                print(f"AWS Error: {e}")

        elif choice == "7":   # LIST ROUTE TABLES
            rts = ec2.describe_route_tables()['RouteTables']
            if not rts: print("No Route Tables found."); continue
            TW = 90
            print(f"\n{'No':<4}{'RT ID':<26}{'VPC ID':<22}{'Main':<8}{'Name'}")
            print_divider(TW)
            for idx, rt in enumerate(rts):
                name = next((t['Value'] for t in rt.get('Tags', []) if t['Key'] == 'Name'), 'N/A')
                main = any(a.get('Main') for a in rt.get('Associations', []))
                print(f"  {idx+1:<3}{rt['RouteTableId']:<26}{rt['VpcId']:<22}{str(main):<8}{name}")
            print_divider(TW)

        elif choice == "8":   # DELETE VPC
            vpcs = [v for v in ec2.describe_vpcs()['Vpcs'] if not v['IsDefault']]
            if not vpcs:
                print("No non-default VPCs found (default VPC cannot be deleted)."); continue
            print("\nNon-default VPCs:")
            for idx, v in enumerate(vpcs):
                name = next((t['Value'] for t in v.get('Tags', []) if t['Key'] == 'Name'), 'N/A')
                print(f"  {idx+1}. {v['VpcId']} ({v['CidrBlock']}) — {name}")
            vc = input("Select VPC Number to Delete: ").strip()
            if not vc.isdigit() or not (1 <= int(vc) <= len(vpcs)):
                print("Invalid selection."); continue
            vpc_id = vpcs[int(vc)-1]['VpcId']
            confirm = input(f"⚠  Delete VPC '{vpc_id}' and all its resources? (yes/no): ").strip().lower()
            if confirm != 'yes':
                print("Cancelled."); continue
            try:
                # Detach & delete IGWs
                for igw in ec2.describe_internet_gateways(Filters=[{'Name':'attachment.vpc-id','Values':[vpc_id]}])['InternetGateways']:
                    ec2.detach_internet_gateway(InternetGatewayId=igw['InternetGatewayId'], VpcId=vpc_id)
                    ec2.delete_internet_gateway(InternetGatewayId=igw['InternetGatewayId'])
                # Delete subnets
                for s in ec2.describe_subnets(Filters=[{'Name':'vpc-id','Values':[vpc_id]}])['Subnets']:
                    ec2.delete_subnet(SubnetId=s['SubnetId'])
                # Delete non-main route tables
                for rt in ec2.describe_route_tables(Filters=[{'Name':'vpc-id','Values':[vpc_id]}])['RouteTables']:
                    if not any(a.get('Main') for a in rt.get('Associations', [])):
                        ec2.delete_route_table(RouteTableId=rt['RouteTableId'])
                # Delete non-default security groups
                for sg in ec2.describe_security_groups(Filters=[{'Name':'vpc-id','Values':[vpc_id]}])['SecurityGroups']:
                    if sg['GroupName'] != 'default':
                        ec2.delete_security_group(GroupId=sg['GroupId'])
                ec2.delete_vpc(VpcId=vpc_id)
                print(f"✅ VPC '{vpc_id}' and its resources deleted.")
            except ClientError as e:
                print(f"AWS Error: {e}")
        else:
            print("Invalid choice. Enter 1–9.")


# ─────────────────────────────────────────────
#  MAIN MENU
# ─────────────────────────────────────────────

def main():
    print("""
╔══════════════════════════════════════════════╗
║        HINTechnologies — EC2 Manager         ║
╚══════════════════════════════════════════════╝
""")

    menu = {
        "1": ("List EC2 Instances",          list_instances),
        "2": ("Create EC2 Instance",         create_instance),
        "3": ("Delete / Remove Resources",   delete_instances),
        "4": ("Open Port (Security Group)",  open_port),
        "5": ("Start / Stop Instances",      start_stop_instances),
        "6": ("IAM Roles",                   iam_menu),
        "7": ("VPC Manager",                 vpc_menu),
        "8": ("Exit",                        None),
    }

    W = 46
    while True:
        top    = "┌" + "─" * W + "┐"
        title  = "│" + " Main Menu ".center(W) + "│"
        sep    = "├" + "─" * W + "┤"
        bottom = "└" + "─" * W + "┘"

        print("\n" + top)
        print(title)
        print(sep)
        for key, (label, _) in menu.items():
            print("│" + f"  {key}.  {label}".ljust(W) + "│")
        print(bottom)

        choice = input("\nEnter your choice: ").strip()

        if choice == "8":
            print("\nGoodbye! 👋\n")
            break
        elif choice in menu:
            _, action = menu[choice]
            action()
        else:
            print("Invalid choice. Please enter 1–8.")


if __name__ == "__main__":
    main()