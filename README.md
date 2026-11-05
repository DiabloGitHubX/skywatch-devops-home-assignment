# SkyWatch — DevOps Home Assignment

A production-minded, locally hosted weather application deployed to Kubernetes through automated CI and GitOps.

## Project objectives

- Develop a Flask frontend and a backend weather API.
- Provision a three-node Kubernetes environment.
- Configure K3s using idempotent Ansible roles.
- Containerize both services.
- Build and publish versioned images through GitHub Actions.
- Package the application using Helm.
- Deploy and continuously reconcile the application using ArgoCD.
- Demonstrate an end-to-end automated GitOps deployment.

## Technology stack

- **Infrastructure:** Multipass, Ubuntu, Terraform (bonus)
- **Configuration management:** Ansible
- **Orchestration:** K3s / Kubernetes
- **Application:** Python, Flask, Open-Meteo
- **Containerization:** Docker
- **CI:** GitHub Actions
- **Registry:** GitHub Container Registry
- **Deployment:** Helm, ArgoCD
- **Observability:** Prometheus, Grafana (bonus)
- **Autoscaling:** Kubernetes HPA (bonus)

## Architecture

Browser → Flask Frontend → Backend API (2 replicas) → Open-Meteo API

Application deployments are managed through GitOps. GitHub Actions builds and publishes container images, updates Helm image references in Git, and ArgoCD reconciles the desired state with Kubernetes.

## Project status

Under development.

## Setup and verification

Detailed reproducible setup instructions will be added as implementation progresses.

## Design decisions and trade-offs

To be documented alongside implementation.

## Troubleshooting and lessons learned

To be documented alongside implementation.
