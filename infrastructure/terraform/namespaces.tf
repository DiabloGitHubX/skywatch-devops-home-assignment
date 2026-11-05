# Platform namespaces managed by Terraform.
# Application workloads remain managed by Argo CD.

resource "kubernetes_namespace_v1" "argocd" {
  metadata {
    name = "argocd"

    labels = {
      "app.kubernetes.io/part-of"    = "skywatch-platform"
      "app.kubernetes.io/managed-by" = "terraform"
    }
  }
}

resource "kubernetes_namespace_v1" "monitoring" {
  metadata {
    name = "monitoring"

    labels = {
      "app.kubernetes.io/part-of"    = "skywatch-platform"
      "app.kubernetes.io/managed-by" = "terraform"
    }
  }
}
