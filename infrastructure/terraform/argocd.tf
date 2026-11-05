# Terraform installs and maintains the Argo CD controller.
# Argo CD, not Terraform, manages the SkyWatch application.
#
# Helm values are maintained separately for readability and configurability.
# yamlencode(yamldecode(...)) normalizes YAML formatting to avoid
# unnecessary changes caused by comments or whitespace.

resource "helm_release" "argocd" {
  name       = "argocd"
  repository = "https://argoproj.github.io/argo-helm"
  chart      = "argo-cd"
  version    = "7.7.22"

  namespace        = kubernetes_namespace_v1.argocd.metadata[0].name
  create_namespace = false

  wait    = true
  timeout = 600
  atomic  = true

  values = [
    yamlencode(yamldecode(file("${path.module}/values/argocd.yaml")))
  ]
}