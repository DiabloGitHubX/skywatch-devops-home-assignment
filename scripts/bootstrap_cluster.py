
#!/usr/bin/env python3
"""Bootstrap the SkyWatch Multipass and Ansible K3s cluster."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

import generate_ansible_inventory as inventory
import provision_vms


ROOT = Path(__file__).resolve().parents[1]
ANSIBLE_SOURCE = ROOT / "infrastructure" / "ansible"

MASTER = "skywatch-master"
WORKERS = ("skywatch-worker1", "skywatch-worker2")

REMOTE_WORKSPACE = "/home/ubuntu/skywatch-ansible"
REMOTE_ARCHIVE = "/home/ubuntu/skywatch-ansible-bootstrap.tar.gz"

SSH_DIRECTORY = "/home/ubuntu/.ssh"
SSH_PRIVATE_KEY = f"{SSH_DIRECTORY}/skywatch_ansible"
SSH_PUBLIC_KEY = f"{SSH_PRIVATE_KEY}.pub"
SSH_KNOWN_HOSTS = f"{SSH_DIRECTORY}/skywatch_known_hosts"

INVENTORY_PATH = ANSIBLE_SOURCE / "inventory" / "hosts.ini"


def run(command, *, capture=False):
    """Run a local command, failing immediately on errors."""
    if not capture:
        print("+", " ".join(command), flush=True)

    return subprocess.run(
        command,
        check=True,
        text=True,
        capture_output=capture,
        timeout=600,
    )


def vm_exec(multipass, vm, command, *, capture=False):
    """Execute a command through the authenticated Multipass channel."""
    return run(
        [multipass, "exec", vm, "--", *command],
        capture=capture,
    )


def vm_bash(multipass, vm, script, *, capture=False):
    """Execute a Linux shell script without Git Bash path conversion."""
    return vm_exec(
        multipass,
        vm,
        ["bash", "-c", script],
        capture=capture,
    )


def ensure_ansible(multipass):
    """Install Ansible on the controller if it is missing."""
    script = """
set -eu

if ! command -v ansible-playbook >/dev/null 2>&1; then
    sudo -n apt-get update
    sudo -n env DEBIAN_FRONTEND=noninteractive \
        apt-get install -y ansible
fi

ansible-playbook --version | head -n 1
"""
    vm_bash(multipass, MASTER, script)


def ensure_controller_key(multipass):
    """Create the dedicated SSH key only if neither key file exists."""
    script = f"""
set -eu

install -d -m 700 {SSH_DIRECTORY}

if [ ! -e {SSH_PRIVATE_KEY} ] && [ ! -e {SSH_PUBLIC_KEY} ]; then
    ssh-keygen -q -t ed25519 -N '' -f {SSH_PRIVATE_KEY}
fi

test -s {SSH_PRIVATE_KEY}
test -s {SSH_PUBLIC_KEY}

chmod 700 {SSH_DIRECTORY}
chmod 600 {SSH_PRIVATE_KEY}
chmod 644 {SSH_PUBLIC_KEY}
"""
    vm_bash(multipass, MASTER, script)


def get_controller_public_key(multipass):
    """Read only the controller's public SSH key."""
    result = vm_exec(
        multipass,
        MASTER,
        ["cat", SSH_PUBLIC_KEY],
        capture=True,
    )

    public_key = result.stdout.strip()
    parts = public_key.split()

    if len(parts) < 2 or parts[0] != "ssh-ed25519":
        raise ValueError("Invalid controller ED25519 public key")

    return public_key


def authorize_worker(multipass, worker, public_key):
    """Append the controller public key without replacing existing keys."""
    script = r"""
import pathlib
import sys

key = sys.argv[1]
ssh_dir = pathlib.Path("/home/ubuntu/.ssh")
authorized = ssh_dir / "authorized_keys"

ssh_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
ssh_dir.chmod(0o700)

existing = (
    authorized.read_text(encoding="utf-8")
    if authorized.exists()
    else ""
)

key_identity = tuple(key.split()[:2])

present = any(
    tuple(line.split()[:2]) == key_identity
    for line in existing.splitlines()
    if line.strip()
)

if not present:
    with authorized.open("a", encoding="utf-8") as output:
        if existing and not existing.endswith("\n"):
            output.write("\n")
        output.write(key + "\n")

authorized.chmod(0o600)
"""

    vm_exec(
        multipass,
        worker,
        ["python3", "-c", script, public_key],
    )


def get_worker_host_key(multipass, worker):
    """Read the worker host public key through Multipass."""
    result = vm_exec(
        multipass,
        worker,
        ["cat", "/etc/ssh/ssh_host_ed25519_key.pub"],
        capture=True,
    )

    parts = result.stdout.strip().split()

    if len(parts) < 2 or parts[0] != "ssh-ed25519":
        raise ValueError(f"{worker}: invalid SSH host public key")

    return " ".join(parts[:2])


def ensure_known_host(multipass, ip, host_key):
    """Trust a new host key, but never replace a conflicting existing key."""
    script = r"""
import pathlib
import sys

address = sys.argv[1]
expected_key = sys.argv[2]

path = pathlib.Path("/home/ubuntu/.ssh/skywatch_known_hosts")
path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
path.parent.chmod(0o700)

lines = (
    path.read_text(encoding="utf-8").splitlines()
    if path.exists()
    else []
)

matches = []

for line in lines:
    fields = line.split()

    if not fields or fields[0].startswith("#"):
        continue

    # Do not silently bypass hashed or marker-based entries.
    if fields[0].startswith("|") or fields[0].startswith("@"):
        raise SystemExit(
            "Unsupported known_hosts entry format; inspect manually"
        )

    if address in fields[0].split(","):
        if len(fields) < 3:
            raise SystemExit("Malformed known_hosts entry")
        matches.append(" ".join(fields[1:3]))

if matches:
    if any(value != expected_key for value in matches):
        raise SystemExit(
            "SSH HOST KEY MISMATCH for " + address
            + ". Refusing to replace trusted identity."
        )
else:
    with path.open("a", encoding="utf-8") as output:
        output.write(address + " " + expected_key + "\n")

path.chmod(0o600)
"""

    vm_exec(
        multipass,
        MASTER,
        ["python3", "-c", script, ip, host_key],
    )


def verify_worker_ssh(multipass, ip):
    """Verify passwordless SSH with strict host-key checking."""
    command = [
        "ssh",
        "-i",
        SSH_PRIVATE_KEY,
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={SSH_KNOWN_HOSTS}",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        f"ubuntu@{ip}",
        "sudo -n true",
    ]

    vm_exec(multipass, MASTER, command)


def generate_inventory(multipass):
    """Discover the current VM addresses and write Ansible's inventory."""
    vms = inventory.discover_vms(multipass)

    master_ip = inventory.get_ipv4(vms, MASTER, multipass)

    workers = [
        (name, inventory.get_ipv4(vms, name, multipass))
        for name in WORKERS
    ]

    addresses = [master_ip, *(ip for _, ip in workers)]

    if len(set(addresses)) != len(addresses):
        raise ValueError("Duplicate VM network addresses detected")

    content = inventory.generate_inventory(
        master_name=MASTER,
        master_ip=master_ip,
        workers=workers,
        controller_mode="master",
        ssh_key_path=SSH_PRIVATE_KEY,
        known_hosts_path=SSH_KNOWN_HOSTS,
    )

    INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)

    with INVENTORY_PATH.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as output:
        output.write(content)

    print(f"Generated inventory: {INVENTORY_PATH}", flush=True)

    return workers


def synchronize_ansible(multipass):
    """Transfer only the required Ansible project files."""
    required_files = [
        ANSIBLE_SOURCE / "ansible.cfg",
        ANSIBLE_SOURCE / "playbook.yml",
        ANSIBLE_SOURCE / "group_vars" / "all.yml",
        ANSIBLE_SOURCE / "playbooks" / "cluster.yml",
        ANSIBLE_SOURCE / "playbooks" / "validate_controller.yml",
        ANSIBLE_SOURCE / "roles" / "k3s_master" / "tasks" / "main.yml",
        ANSIBLE_SOURCE / "roles" / "k3s_worker" / "tasks" / "main.yml",
        INVENTORY_PATH,
    ]

    for path in required_files:
        if not path.is_file():
            raise FileNotFoundError(f"Missing Ansible file: {path}")

    with tempfile.TemporaryDirectory(prefix="skywatch-") as directory:
        archive = Path(directory) / "ansible.tar.gz"

        with tarfile.open(archive, "w:gz") as tar:
            for path in required_files:
                tar.add(
                    path,
                    arcname=path.relative_to(ANSIBLE_SOURCE).as_posix(),
                    recursive=False,
                )

        run(
            [
                multipass,
                "transfer",
                str(archive),
                f"{MASTER}:{REMOTE_ARCHIVE}",
            ]
        )

    script = f"""
set -eu

mkdir -p {REMOTE_WORKSPACE}
tar -xzf {REMOTE_ARCHIVE} -C {REMOTE_WORKSPACE}

find {REMOTE_WORKSPACE} -type d -exec chmod 755 {{}} +
find {REMOTE_WORKSPACE} -type f -exec chmod 644 {{}} +

rm -f {REMOTE_ARCHIVE}

test -s {REMOTE_WORKSPACE}/inventory/hosts.ini
test -s {REMOTE_WORKSPACE}/playbook.yml
"""

    vm_bash(multipass, MASTER, script)


def run_ansible(multipass):
    """Execute the existing K3s Ansible playbook."""
    script = f"""
set -eu
cd {REMOTE_WORKSPACE}
ansible-playbook playbook.yml
"""

    vm_bash(multipass, MASTER, script)


def verify_cluster(multipass):
    """Verify all expected Kubernetes nodes are Ready."""
    script = """
set -eu

sudo -n k3s kubectl wait \
    --for=condition=Ready \
    nodes/skywatch-master \
    nodes/skywatch-worker1 \
    nodes/skywatch-worker2 \
    --timeout=120s

echo
echo "========== VERIFIED KUBERNETES NODES =========="
sudo -n k3s kubectl get nodes -o wide
"""

    vm_bash(multipass, MASTER, script)

    print(
        "All three SkyWatch Kubernetes nodes are Ready.",
        flush=True,
    )


def dry_run(multipass):
    """Perform read-only discovery without changing infrastructure."""
    print("DRY RUN: no changes will be made.", flush=True)

    vms = inventory.discover_vms(multipass)

    for name, spec in provision_vms.VM_SPECS.items():
        vm = vms.get(name)

        if vm is None:
            print(
                f"Would create {name}: "
                f"{spec['cpus']} CPU, "
                f"{spec['memory']} RAM, "
                f"{spec['disk']} disk"
            )
            continue

        state = vm.get("state")

        if state == "Stopped":
            print(f"Would start VM: {name}")
        elif state == "Running":
            info = provision_vms.get_vm_info(multipass, name)
            provision_vms.validate_vm(name, spec, info)
            print(f"Would reuse VM: {name}")
        else:
            raise ValueError(f"{name}: unexpected VM state {state}")

    print("Would configure controller SSH and Ansible.")
    print("Would generate inventory and synchronize Ansible.")
    print("Would run the K3s playbook and verify nodes.")


def bootstrap(multipass):
    """Execute the complete cluster bootstrap workflow."""
    print("\n[1/7] Provisioning Multipass VMs", flush=True)

    vms = provision_vms.discover_vms(multipass)

    for name, spec in provision_vms.VM_SPECS.items():
        provision_vms.provision_vm(
            multipass,
            name,
            spec,
            vms.get(name),
        )

    print("\n[2/7] Preparing Ansible controller", flush=True)
    ensure_ansible(multipass)
    ensure_controller_key(multipass)

    print("\n[3/7] Generating inventory", flush=True)
    workers = generate_inventory(multipass)

    print("\n[4/7] Establishing SSH trust", flush=True)
    public_key = get_controller_public_key(multipass)

    for worker, ip in workers:
        # Verify worker identity before changing authorized_keys.
        host_key = get_worker_host_key(multipass, worker)
        ensure_known_host(multipass, ip, host_key)

        authorize_worker(multipass, worker, public_key)
        verify_worker_ssh(multipass, ip)

    print("\n[5/7] Synchronizing Ansible", flush=True)
    synchronize_ansible(multipass)

    print("\n[6/7] Running Ansible", flush=True)
    run_ansible(multipass)

    print("\n[7/7] Verifying Kubernetes", flush=True)
    verify_cluster(multipass)

    print(
        "\nSkyWatch K3s bootstrap completed successfully.",
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Bootstrap the SkyWatch K3s cluster."
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

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect existing VMs without changing infrastructure",
    )

    args = parser.parse_args()

    try:
        if args.dry_run:
            dry_run(args.multipass)
        else:
            bootstrap(args.multipass)

    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        KeyError,
        TypeError,
        ValueError,
        tarfile.TarError,
    ) as exc:
        print(f"Bootstrap failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
