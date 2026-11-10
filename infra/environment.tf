# 環境（本番 prod と test）。同じ Terraform を 2 つに使い、今の AWS のプロジェクトの中で名前で分ける（docs/data_flow_design.md 14.、#26）。
#   - 本番は今の名前のまま（作り直しにならないように）。test は ct125-test-… にする
#   - state は Terraform の workspace で分ける。本番は default（今の infra/terraform.tfstate）、test は test（env:/test/infra/terraform.tfstate）
#   - IAM は、どのロールも自分の環境の名前のリソースだけを指す（test のロールは本番のバケットや Lambda に届かない）
# 手順は docs/test_environment.md。

variable "env" {
  description = "環境の名前（prod か test）。test は test.tfvars に env = \"test\" と書き、workspace の test で使う"
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["prod", "test"], var.env)
    error_message = "env は prod か test にしてください。"
  }
}

locals {
  is_prod = var.env == "prod"
  # 選んでいる workspace が示す環境。default は本番
  workspace_env = terraform.workspace == "default" ? "prod" : terraform.workspace

  # リソースの名前の先頭：本番 ct125-…、test ct125-test-…
  name_prefix = local.is_prod ? "ct125" : "ct125-${var.env}"
  # バケットの名前の先頭：本番 ct125-logger-…、test ct125-logger-test-…（後ろに役割とアカウント ID が付く）
  bucket_prefix = local.is_prod ? var.bucket_prefix : "${var.bucket_prefix}-${var.env}"

  app_domain            = coalesce(var.app_domain, local.is_prod ? "drive.herdio-system.com" : "drive-${var.env}.herdio-system.com")
  cognito_domain_prefix = coalesce(var.cognito_domain_prefix, local.is_prod ? "ct125-drive-login" : "ct125-drive-login-${var.env}")

  # 機器トークンのハッシュを置く SSM の場所：本番 /ct125/devices/、test /ct125-test/devices/
  device_parameter_prefix = "/${local.name_prefix}/devices/"

  # 走行データ処理のコンテナを ECR に残す数（test は確かめるだけなので少なくする）
  pipeline_images_to_keep = local.is_prod ? 5 : 2
}
