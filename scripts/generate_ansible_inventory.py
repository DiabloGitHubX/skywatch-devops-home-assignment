#!/usr/bin/env python3
"""Generate an Ansible inventory from Multipass VM information."""

import argparse
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys


def discover_vms(multipass):
    """Discover Multipass virtual machines."""
    result = subprocess.run(
        [multipass, "list", "--format", "json"],
        capture_output=True,
        text=True,
        check=True,
    )

    data = json.loads(result.stdout)
    vms = data["list"]

    names = [vm["name"] for vm in vms]
    if len(names) != len(set(names)):
        raise ValueError("Multipass returned duplicate VM names")

    return {vm["name"]: vm for vm in vms}


def get_ipv4(vms, name):
    """Return the single usable IPv4 address of a running VM."""
    vm = vms.get(name)

    if vm is None:
        raise ValueError(f"Required VM not found: {name}")

    if vm.get("state") != "Running":
        raise ValueError(f"VM is not running: {name}")

    addresses = []

    for value in vm.get("ipv4", []):
        address = ipaddress.ip_address(value)

        if (
            isinstance(address, ipaddress.IPv4Address)
            and not address.is_loopback
            and not address.is_link_local
            and not address.is_unspecified
        ):
            addresses.append(str(address))

    addresses = sorted(set(addresses))

    if len(addresses) != 1:
        raise ValueError(
            f"Expected exactly one usable IPv4 address for {name}; found {addresses}"
        )

    return addresses[0]


def generate_inventory(
    master_name,
    master_ip,
    workers,
    controller_mode,
    ssh_key_path,
    known_hosts_path,
):
    """Build a deterministic Ansible INI inventory."""
    lines = [
        "[k3s_master]",
    ]

    if controller_mode == "master":
        lines.append(f"{master_name} ansible_connection=local k3s_node_ip={master_ip}")
    else:
        lines.append(f"{master_name} ansible_host={master_ip} k3s_node_ip={master_ip}")

    lines.extend(
        [
            "",
            "[k3s_workers]",
        ]
    )

    lines.extend(f"{name} ansible_host={address}" for name, address in workers)

    lines.extend(
        [
            "",
            "[k3s_cluster:children]",
            "k3s_master",
            "k3s_workers",
            "",
            "[k3s_cluster:vars]",
            "ansible_user=ubuntu",
            "ansible_python_interpreter=/usr/bin/python3",
            f"ansible_ssh_private_key_file={ssh_key_path}",
            (
                "ansible_ssh_common_args='"
                "-o IdentitiesOnly=yes "
                "-o StrictHostKeyChecking=yes "
                f"-o UserKnownHostsFile={known_hosts_path}'"
            ),
            "",
        ]
    )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate an Ansible inventory from Multipass."
    )

    parser.add_argument(
        "--multipass",
        default=os.environ.get("MULTIPASS_BIN", "multipass"),
        help="Multipass executable path",
    )

    parser.add_argument(
        "--master",
        default="skywatch-master",
        help="Multipass control-plane VM name",
    )

    parser.add_argument(
        "--workers",
        nargs="+",
        default=["skywatch-worker1", "skywatch-worker2"],
        help="Multipass worker VM names",
    )

    parser.add_argument(
        "--controller-mode",
        choices=["master", "external"],
        default="master",
        help="Where Ansible runs (default: master)",
    )

    parser.add_argument(
        "--ssh-key-path",
        default="/home/ubuntu/.ssh/skywatch_ansible",
        help="SSH private key path on the Ansible controller",
    )

    parser.add_argument(
        "--known-hosts-path",
        default="/home/ubuntu/.ssh/skywatch_known_hosts",
        help="SSH known_hosts path on the Ansible controller",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("infrastructure/ansible/inventory/hosts.generated.ini"),
        help="Destination inventory file",
    )

    args = parser.parse_args()

    names = [args.master, *args.workers]

    if len(names) != len(set(names)):
        parser.error("Master and worker VM names must be unique")

    if not args.workers:
        parser.error("At least one worker VM is required")

    try:
        vms = discover_vms(args.multipass)

        master_ip = get_ipv4(vms, args.master)

        workers = [(name, get_ipv4(vms, name)) for name in args.workers]

        content = generate_inventory(
            master_name=args.master,
            master_ip=master_ip,
            workers=workers,
            controller_mode=args.controller_mode,
            ssh_key_path=args.ssh_key_path,
            known_hosts_path=args.known_hosts_path,
        )

        args.output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        # Explicit LF endings for Windows/Linux consistency.
        with args.output.open(
            "w",
            encoding="utf-8",
            newline="\n",
        ) as file:
            file.write(content)

    except (
        OSError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
        ValueError,
        KeyError,
        TypeError,
    ) as exc:
        print(
            f"Inventory generation failed: {exc}",
            file=sys.stderr,
        )
        return 1

    print(f"Generated inventory: {args.output}")
    print(content)

    return 0


if __name__ == "__main__":
    sys.exit(main())
