variable "kubeconfig_path" {
  description = "Absolute path to the local SkyWatch Kubernetes kubeconfig."
  type        = string
}

provider "kubernetes" {
  config_path = var.kubeconfig_path
}

provider "helm" {
  kubernetes = {
    config_path = var.kubeconfig_path
  }
}
