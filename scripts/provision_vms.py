
#!/usr/bin/env python3
"""Provision and validate the SkyWatch Multipass virtual machines."""

import argparse
import json
import os
import shutil
import subprocess
import sys


# Desired virtual machine specifications.
# Values are passed directly to Multipass when creating new VMs.
VM_SPECS = {
    "skywatch-master": {
        "cpus": 1,
        "memory": "1536M",
        "disk": "12G",
    },
    "skywatch-worker1": {
        "cpus": 2,
        "memory": "2G",
        "disk": "15G",
    },
    "skywatch-worker2": {
        "cpus": 2,
        "memory": "2G",
        "disk": "15G",
    },
}

UBUNTU_IMAGE = "22.04"
EXPECTED_RELEASE = "22.04"

# Multipass reports usable guest memory and filesystem capacity,
# which can be lower than the requested VM allocations.
MIN_MEMORY_RATIO = 0.90
MIN_DISK_RATIO = 0.90

# Multipass CLI suffixes are decimal:
# M = 1,000,000 bytes; G = 1,000,000,000 bytes.
SIZE_MULTIPLIERS = {
    "M": 1_000_000,
    "G": 1_000_000_000,
}


def parse_size(value):
    """Convert a Multipass size such as 1536M or 12G to bytes."""
    suffix = value[-1].upper()

    if suffix not in SIZE_MULTIPLIERS:
        raise ValueError(f"Unsupported size unit: {value}")

    return int(value[:-1]) * SIZE_MULTIPLIERS[suffix]


def run_command(command):
    """Execute a command and raise an error on failure."""
    print("+", " ".join(command), flush=True)

    subprocess.run(
        command,
        check=True,
        text=True,
    )


def discover_vms(multipass):
    """Return the existing Multipass instances."""
    result = subprocess.run(
        [multipass, "list", "--format", "json"],
        capture_output=True,
        text=True,
        check=True,
    )

    data = json.loads(result.stdout)
    instances = data["list"]

    names = [instance["name"] for instance in instances]

    if len(names) != len(set(names)):
        raise ValueError("Multipass returned duplicate VM names")

    return {
        instance["name"]: instance
        for instance in instances
    }


def get_vm_info(multipass, name):
    """Retrieve structured information for a single VM."""
    result = subprocess.run(
        [multipass, "info", "--format", "json", name],
        capture_output=True,
        text=True,
        check=True,
    )

    data = json.loads(result.stdout)

    return data["info"][name]


def validate_vm(name, spec, info):
    """Validate an existing VM against the desired specification."""
    if info.get("state") != "Running":
        raise ValueError(f"{name} is not running")

    release = info.get("image_release", "")

    if not release.startswith(EXPECTED_RELEASE):
        raise ValueError(
            f"{name}: expected Ubuntu {EXPECTED_RELEASE}, "
            f"found image release {release!r}"
        )

    actual_cpus = int(info["cpu_count"])

    if actual_cpus != spec["cpus"]:
        raise ValueError(
            f"{name}: expected {spec['cpus']} CPUs, "
            f"found {actual_cpus}"
        )

    expected_memory = parse_size(spec["memory"])
    actual_memory = int(info["memory"]["total"])

    if actual_memory < expected_memory * MIN_MEMORY_RATIO:
        raise ValueError(
            f"{name}: insufficient RAM. "
            f"Expected approximately {spec['memory']}, "
            f"found {actual_memory} bytes"
        )

    expected_disk = parse_size(spec["disk"])

    disks = info.get("disks", {})

    if not disks:
        raise ValueError(
            f"{name}: no disk information returned by Multipass"
        )

    actual_disk = max(
        int(disk["total"])
        for disk in disks.values()
    )

    if actual_disk < expected_disk * MIN_DISK_RATIO:
        raise ValueError(
            f"{name}: insufficient disk capacity. "
            f"Expected approximately {spec['disk']}, "
            f"found {actual_disk} bytes"
        )

    print(
        f"Validated {name}: "
        f"{actual_cpus} CPU(s), "
        f"{actual_memory / 1_000_000_000:.2f} GB RAM, "
        f"{actual_disk / 1_000_000_000:.2f} GB disk",
        flush=True,
    )


def provision_vm(multipass, name, spec, existing):
    """Create, start, or reuse a Multipass VM."""
    if existing is None:
        print(f"\nCreating missing VM: {name}", flush=True)

        run_command(
            [
                multipass,
                "launch",
                UBUNTU_IMAGE,
                "--name",
                name,
                "--cpus",
                str(spec["cpus"]),
                "--memory",
                spec["memory"],
                "--disk",
                spec["disk"],
            ]
        )

    else:
        state = existing.get("state")

        if state == "Running":
            print(f"\nReusing running VM: {name}", flush=True)

        elif state == "Stopped":
            print(f"\nStarting stopped VM: {name}", flush=True)
            run_command([multipass, "start", name])

        else:
            raise ValueError(
                f"{name} is in unexpected state: {state}"
            )

    info = get_vm_info(multipass, name)
    validate_vm(name, spec, info)


def main():
    parser = argparse.ArgumentParser(
        description="Provision SkyWatch Multipass VMs."
    )

    parser.add_argument(
        "--multipass",
        default=(
            os.environ.get("MULTIPASS_BIN")
            or shutil.which("multipass")
            or r"D:\Multipass\bin\multipass.exe"
        ),
        help="Multipass executable path",
    )

    args = parser.parse_args()

    try:
        vms = discover_vms(args.multipass)

        for name, spec in VM_SPECS.items():
            provision_vm(
                multipass=args.multipass,
                name=name,
                spec=spec,
                existing=vms.get(name),
            )

    except (
        OSError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        print(
            f"VM provisioning failed: {exc}",
            file=sys.stderr,
        )
        return 1

    print(
        "\nAll SkyWatch VMs are running and validated.",
        flush=True,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
