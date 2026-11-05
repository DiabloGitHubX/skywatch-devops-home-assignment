# Read-only verification of access to the existing K3s cluster.
# This namespace is managed by Kubernetes, not Terraform.

data "kubernetes_namespace_v1" "kube_system" {
  metadata {
    name = "kube-system"
  }
}
