# SkyWatch — DevOps Home Assignment

A locally hosted weather-search application deployed on a three-node K3s cluster using **Multipass, Ansible, Terraform, Helm, GitHub Actions, GHCR, and Argo CD**. The deployment is GitOps-driven: application changes are validated, packaged as commit-tagged container images, and reconciled into Kubernetes without a manual Helm upgrade or application `kubectl apply` on each release.

## Demo and evidence

| Evidence | Screenshot |
| --- | --- |
| Argo CD application Healthy / Synced | [Argo CD](docs/screenshots/1-argocd.png) |
| Successful GitHub Actions run | [CI run](docs/screenshots/2-Ci-Github-Actions.png) |
| GitHub Actions workflow history | [CI workflows](docs/screenshots/3-ci-workflows.png) |
| Three-node cluster and running workloads | [Kubernetes nodes and pods](docs/screenshots/04-kubernetes-cluster-and-pods.png) |
| Weather lookup for Tel Aviv | [Application demo](docs/screenshots/05-skywatch-request-demo.png) |

The demonstrated GitOps change was commit [`d058a57`](https://github.com/DiabloGitHubX/skywatch-devops-home-assignment/commit/d058a5747c891a01a22b12a6bd894d6874d3af4f): scale the backend to two replicas and supply the frontend backend URL through a ConfigMap. Argo CD reported **Healthy**, **Synced**, and **Sync OK** for that commit. Kubernetes verification showed **2/2 backend** and **1/1 frontend** replicas ready, with backend pods on separate worker nodes.

## Architecture

```text
                       User browser
                            |
                    localhost:5000
                     (port-forward)
                            |
                 Flask frontend (1 pod)
                            |
             BACKEND_URL from ConfigMap
                            |
                ClusterIP: backend:5001
                            |
                Flask backend (2 pods)
                            |
             Open-Meteo geocoding + forecast

 Windows host / Git Bash
       |
       +-- Multipass: Ubuntu 22.04 VMs
       |     +-- skywatch-master  (K3s control plane; no app workloads)
       |     +-- skywatch-worker1 (K3s agent)
       |     +-- skywatch-worker2 (K3s agent)
       |
       +-- Python bootstrap -> Ansible -> K3s
       +-- Terraform -> Argo CD controller + platform namespaces

 Git push to main
       -> GitHub Actions: lint/test/Helm validation
       -> Docker build + Trivy HIGH/CRITICAL scan
       -> GHCR: images tagged with 7-character commit SHA
       -> CI commits Helm image tags to values-gitops.yaml [skip ci]
       -> Argo CD watches main and reconciles the Helm release
       -> Kubernetes rolling deployment
```

The frontend communicates with the backend over Kubernetes DNS. Only the frontend is exposed to the local workstation through a port-forward; both application Services are `ClusterIP`. Ingress is intentionally disabled in this small lab.

## Repository layout

```text
app/backend/                 Flask weather API, Dockerfile, dependencies
app/frontend/                Flask UI, HTML template, Dockerfile
scripts/bootstrap_cluster.py Multipass + Ansible bootstrap entry point
scripts/provision_vms.py     VM specifications and validation
scripts/generate_ansible_inventory.py  Inventory from current VM IPs
infrastructure/ansible/      Pinned K3s installation and worker join roles
infrastructure/terraform/    Argo CD installation and platform namespaces
helm/skywatch/               Application chart and GitOps image values
argocd/skywatch-application.yaml  Argo CD Application definition
.github/workflows/ci.yaml    Validation, image scanning/publishing, GitOps update
tests/                       Backend and frontend automated tests
docs/screenshots/            Deployment and end-to-end evidence
```

## Prerequisites

This implementation was developed on **Windows with Git Bash**. Install and configure:

- Git, Python 3.12, and Multipass with enough available CPU, RAM, and disk space for three Ubuntu VMs.
- `kubectl`, Helm 3, and Terraform **>= 1.6, < 2.0** on the host.
- A GitHub repository with Actions enabled and permission to publish GitHub Container Registry (GHCR) packages.
- Network access for Ubuntu package installation, K3s, Helm charts, Python dependencies, and Open-Meteo.

Ansible runs **inside the control-plane VM** and is installed by the bootstrap script if missing; it does not need to be installed on Windows. Docker is used by GitHub Actions to build the application images, so a local Docker daemon is not required for the GitOps deployment path.

The default Multipass executable is discovered from `PATH`. The scripts also support `MULTIPASS_BIN` or `--multipass` for custom installations.

### VM resources

| VM | CPU | RAM | Disk | Role |
| --- | ---: | ---: | ---: | --- |
| `skywatch-master` | 1 | 1536 MB | 12 GB | Control plane / Ansible controller |
| `skywatch-worker1` | 2 | 2 GB | 15 GB | Worker |
| `skywatch-worker2` | 2 | 2 GB | 15 GB | Worker |

All three VMs use Ubuntu **22.04**. K3s is pinned to **`v1.29.15+k3s1`** in `infrastructure/ansible/group_vars/all.yml` for repeatability. **Kubernetes 1.29 is end-of-life and this pinned version is for the assignment lab only, not production.** Traefik and ServiceLB are disabled to reduce resource usage.

## Reproduce the deployment

Run the commands below from the repository root unless stated otherwise. The bootstrap, Terraform installation, and initial Argo CD Application registration are **one-time infrastructure setup**; subsequent application releases use GitOps.

### 1. Clone and bootstrap K3s

```bash
git clone https://github.com/DiabloGitHubX/skywatch-devops-home-assignment.git
cd skywatch-devops-home-assignment

# Optional: inspect existing VMs before making changes
python scripts/bootstrap_cluster.py --dry-run

# Create/reuse VMs, prepare SSH trust, generate inventory,
# run Ansible, and verify all three K3s nodes are Ready
python scripts/bootstrap_cluster.py
```

The script discovers the VMs' current default-route IPs, generates `infrastructure/ansible/inventory/hosts.ini`, installs Ansible on the master if needed, configures a dedicated SSH key with strict host-key verification, and runs `infrastructure/ansible/playbook.yml`. It validates existing VM specifications rather than silently replacing VMs. The K3s roles configure the master and join both workers using the cluster's existing node token.

### 2. Configure host access to Kubernetes

The bootstrap verifies Kubernetes **inside** `skywatch-master`; it does **not** automatically export a host kubeconfig. Copy the control-plane kubeconfig from `/etc/rancher/k3s/k3s.yaml` on the master to a **private local file**, then replace its `server:` address (`127.0.0.1` on the VM) with the master VM's reachable IP, keeping port `6443`. Use the IP reported by Multipass and ensure the certificate configuration allows access from the host. Protect the kubeconfig: it contains cluster administrator credentials and must never be committed.

In Git Bash, for example:

```bash
export KUBECONFIG="$HOME/.kube/skywatch/config"
kubectl get nodes -o wide
```

If your kubeconfig is elsewhere, set `KUBECONFIG` to that path. Set it again in new terminal sessions, or add the export to your shell profile. Verify that all three nodes are `Ready` before continuing.

### 3. Install Argo CD with Terraform

Terraform verifies the existing cluster, creates the `argocd` and `monitoring` namespaces, and installs the pinned Argo CD Helm chart (`7.7.22`). The `monitoring` namespace is reserved for future observability components; its existence does **not** mean Prometheus or Grafana is installed.

```bash
cd infrastructure/terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` to point to your **absolute host kubeconfig path** (the example uses Windows-style paths). Then run:

```bash
terraform init
terraform plan
terraform apply
cd ../..
```

`terraform.tfvars` and Terraform state files are ignored by Git. Terraform owns the Argo CD controller and platform namespaces, **not** the SkyWatch application workloads.

### 4. Register the Argo CD Application once

```bash
kubectl apply -f argocd/skywatch-application.yaml
kubectl get application skywatch -n argocd
```

This one-time command registers the GitOps controller's Application resource. It is **not** a manual deployment of the SkyWatch workloads. The Application watches the repository's `main` branch, reads `helm/skywatch` with `values.yaml` and `values-gitops.yaml`, creates the `skywatch` namespace if needed, and enables automatic sync, pruning, and self-healing.

The chart's default image tags are deliberately empty. A successful GitHub Actions publication populates `values-gitops.yaml` with published commit-SHA image tags. For a fork or a different GitHub account, update the Argo CD `repoURL` and Helm image repository names, and ensure the GHCR packages are accessible to the cluster.

### 5. Access Argo CD and the application

In one terminal:

```bash
kubectl port-forward -n argocd svc/argocd-server 8080:443
```

Open **https://localhost:8080** (the local certificate may be self-signed). Use your configured Argo CD credentials; change the initial admin password on first setup.

In a second terminal:

```bash
kubectl port-forward -n skywatch svc/skywatch-frontend 5000:5000
```

Open **http://localhost:5000** and search for a city such as **Tel Aviv**. Keep the port-forward running while using the browser. If a port is already occupied, choose another free local port (for example, `5002:5000`).

## Application API

| Endpoint | Service | Behavior |
| --- | --- | --- |
| `GET /` | Frontend | HTML weather-search page |
| `GET /?city=Tel%20Aviv` | Frontend | Query weather and render a result |
| `GET /healthz` | Frontend | Health endpoint |
| `GET /api/weather?city=Tel%20Aviv` | Backend | JSON weather response |
| `GET /healthz` | Backend | Liveness endpoint |
| `GET /readyz` | Backend | Readiness endpoint |

The backend queries Open-Meteo's geocoding and forecast APIs. It returns HTTP `400` for a missing/invalid city, `404` when no city is found, `504` for provider timeouts, and `502` for other provider failures. The frontend handles backend errors and request timeouts with user-facing messages. The frontend defaults to `http://127.0.0.1:5001` for local development; Kubernetes injects `BACKEND_URL=http://skywatch-backend:5001` through the `skywatch-frontend-config` ConfigMap.

## CI/CD and GitOps

The workflow in `.github/workflows/ci.yaml` runs on pushes and pull requests targeting `main`:

1. **Validate:** Python 3.12, Ruff linting, pytest, strict Helm lint, and Helm template rendering.
2. **Build and scan:** Build backend/frontend Linux AMD64 images, scan OS and library dependencies with Trivy, and fail on actionable HIGH/CRITICAL findings (`ignore-unfixed: true`).
3. **Publish (pushes to `main`):** Publish scanned images to GHCR using the first seven characters of the commit SHA, not `latest`.
4. **Update GitOps (pushes to `main`):** Commit both new image tags to `helm/skywatch/values-gitops.yaml` with `[skip ci]` to prevent an endless pipeline loop.
5. **Reconcile:** Argo CD detects the Git change and automatically deploys the desired Helm release. `prune: true` removes obsolete managed resources; `selfHeal: true` repairs drift.

Pull requests run validation and image scanning but do not publish images or update GitOps tags. Image publishing uses the GitHub Actions `GITHUB_TOKEN` with package-write permission.

**Observed rollout:** commit `d058a57` changed the Helm chart to use **two backend replicas** and a **ConfigMap-based frontend URL**. The successful CI pipeline published images and the bot subsequently updated the image tags in commit `2b54dd4`. Argo CD automatically synchronized the application, and Kubernetes showed two backend pods running on different worker nodes. No manual application `helm upgrade`, `kubectl apply`, or Argo CD sync was required for this change.

### Verify the live state

```bash
kubectl get nodes -o wide
kubectl get deployments -n skywatch
kubectl get pods -n skywatch -o wide
kubectl get configmap skywatch-frontend-config -n skywatch \
  -o jsonpath='{.data.BACKEND_URL}'; echo
kubectl get application skywatch -n argocd
```

Expected: three Ready nodes; backend `2/2`, frontend `1/1`; `BACKEND_URL` points to `http://skywatch-backend:5001`; Argo CD is **Synced** and **Healthy**. The control-plane node is configured to avoid scheduling application workloads.

To inspect the ConfigMap reference in the frontend Deployment:

```bash
kubectl get deployment skywatch-frontend -n skywatch \
  -o jsonpath='{.spec.template.spec.containers[0].env}'; echo
```

### Run quality checks locally

```bash
python -m pip install -r app/backend/requirements.txt \
  -r app/frontend/requirements.txt -r requirements-dev.txt
ruff check app tests
python -m pytest -q
helm lint helm/skywatch --strict \
  --set backend.image.tag=a3f8c91 \
  --set frontend.image.tag=a3f8c91
helm template skywatch-dev helm/skywatch \
  --set backend.image.tag=a3f8c91 \
  --set frontend.image.tag=a3f8c91
```

The placeholder tags in these last two commands are **only for rendering and validation**, not deployment.

## Design decisions and trade-offs

- **K3s + Multipass:** Lightweight, repeatable three-node lab on one workstation; not a highly available production control plane.
- **Ansible for K3s:** Configuration-as-code with a pinned version, separate master/worker roles, dynamic inventory, and reusable bootstrap logic.
- **Terraform for platform, Argo CD for app:** Separates platform provisioning from continuous application reconciliation and avoids competing managers for the same workloads.
- **SHA-based images:** Each release points to a specific source revision. CI owns `values-gitops.yaml`; developers should not manually invent image tags.
- **Helm ConfigMap:** Keeps the frontend's backend endpoint out of the container image, allowing environment-specific configuration.
- **Workload placement:** Control plane is tainted; backend replicas run across the two workers in the demonstrated cluster. This is observed placement, not a guaranteed anti-affinity policy.
- **Container hardening:** Non-root UID/GID `10001`, dropped Linux capabilities, no privilege escalation, read-only root filesystem, default seccomp profile, CPU/memory requests and limits, and health probes.
- **Local access:** `ClusterIP` and port-forwarding avoid introducing an ingress controller or public exposure for a small assignment environment.
- **Pinned legacy K3s:** Improves repeatability of the tested lab, but requires upgrading to a supported Kubernetes release before any production use.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Multipass command not found | Add Multipass to `PATH`, set `MULTIPASS_BIN`, or pass `--multipass` to the bootstrap script. |
| Existing VM rejected | The bootstrap validates Ubuntu version, CPU, memory, and disk. Inspect `multipass info <vm>` rather than silently replacing it. |
| Ansible SSH failure | Check worker IPs, the controller's authorized SSH key, and strict known-host verification. A changed host key requires investigation, not disabling verification. |
| `kubectl` cannot reach cluster | Check `KUBECONFIG`, master VM IP, port `6443`, and kubeconfig certificate/server configuration. |
| Terraform cannot connect | Confirm `terraform.tfvars` uses the absolute kubeconfig path and `kubectl get nodes` succeeds first. |
| Argo CD `OutOfSync` or `Progressing` | Allow reconciliation time; inspect the Application resource tree, events, image pull errors, and pod readiness. |
| GHCR `ImagePullBackOff` | Confirm both SHA-tagged packages exist and are public or supply valid `imagePullSecrets`. |
| Git push rejected (`fetch first`) | CI may have pushed an automated GitOps tag commit. Fetch and fast-forward or rebase your local work; do not force-push `main`. |
| Frontend cannot reach backend | Inspect `skywatch-frontend-config`, frontend Deployment environment, backend Service, and backend pod readiness. |
| Local browser connection fails | Keep the port-forward process running and verify the selected local port is free. |

Useful diagnostics:

```bash
kubectl describe application skywatch -n argocd
kubectl get events -n skywatch --sort-by=.lastTimestamp
kubectl logs -n skywatch deployment/skywatch-backend --tail=100
kubectl logs -n skywatch deployment/skywatch-frontend --tail=100
```

## Future improvements

- Upgrade K3s/Kubernetes to a currently supported release and establish a routine upgrade process.
- Add Prometheus/Grafana dashboards and alerting; currently only the `monitoring` namespace is provisioned.
- Add Horizontal Pod Autoscalers after validating metrics-server and workload sizing.
- Add HTTPS ingress, DNS, and TLS certificate management for non-local environments.
- Enforce backend spread using pod anti-affinity or topology-spread constraints, and add disruption budgets.
- Introduce secrets management, more restrictive network policies, and image signing/verification.
- Add integration tests against the deployed environment and automated GitOps rollout checks.
- Improve production resilience with a highly available control plane, externalized state, and backup/restore procedures.

## Scope and security note

This is a **development assignment**, not a production-ready weather service. Do not commit kubeconfigs, private SSH keys, Terraform state, `.tfvars` containing local values, or other credentials. The repository's `.gitignore` excludes common local artifacts, but always inspect staged changes before pushing.
