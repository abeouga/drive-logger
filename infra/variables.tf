# PC や AWS のプロジェクトに依る値は既定を持たない。terraform.tfvars（コミットしない。見本は example.tfvars）に書く

variable "aws_profile" {
  description = "管理者の ~/.aws の CLI プロファイル名（認証情報はここに書かない）。web・pipeline のスクリプトも出力の aws_profile から読む"
  type        = string
}

variable "aws_account_id" {
  description = "使う AWS のアカウント ID。provider の allowed_account_ids に渡し、別のアカウントのプロファイルで動かすのを防ぐ"
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id は 12 桁の数字にしてください。"
  }
}

variable "aws_region" {
  description = "プロジェクトのリージョン（新しい AWS 体験ではプロジェクトごとに固定。AWS Settings > View all projects > Overview > Additional Info > Region で確認）"
  type        = string
}

variable "base_domain" {
  description = "画面のドメインの親（DNS は Cloudflare）。画面のドメインは本番 drive.<base_domain>、test drive-<env>.<base_domain>（environment.tf）"
  type        = string
}

variable "bucket_prefix" {
  description = "バケット名の先頭。後ろにアカウント ID を付けて一意にする。test は後ろに -test が付く（environment.tf）"
  type        = string
  default     = "ct125-logger"
}

variable "app_domain" {
  description = "Web アプリを公開するドメイン（DNS は Cloudflare。プロキシはオフにする）。null なら本番 drive.<base_domain>、test drive-<env>.<base_domain>"
  type        = string
  default     = null
}

variable "app_users" {
  description = "Web アプリにログインできるユーザー（ユーザー名 → 設定）。値は terraform.tfvars に書く"
  type = map(object({
    is_admin = bool
  }))
}

variable "app_user_passwords" {
  description = "ユーザー名 → パスワード。terraform.tfvars に書く（コミットしない）"
  type        = map(string)
  sensitive   = true

  validation {
    condition     = alltrue([for password in values(var.app_user_passwords) : length(password) >= 8])
    error_message = "パスワードは 8 文字以上にしてください。"
  }
}

variable "cognito_domain_prefix" {
  description = "Cognito のログイン画面の URL の先頭（<prefix>.auth.<region>.amazoncognito.com）。世界で一意。null なら本番 ct125-drive-login、test ct125-drive-login-test"
  type        = string
  default     = null
}

variable "data_api_zip" {
  description = "データ API（FastAPI）の Lambda 用 zip。api/scripts/build-lambda.ps1 で作る。null ならこのリポジトリの api/dist/lambda.zip"
  type        = string
  default     = null
}

variable "webapp_prefix" {
  description = "Web アプリ（React のビルド結果）を置く S3 のフォルダー。CloudFront はここだけを読める"
  type        = string
  default     = "webapp"
}

variable "pipeline_image_digest" {
  description = "走行データ処理の Lambda のコンテナイメージの digest（sha256:…）。ECR の住所はこの環境の ECR から組み立てる（ride_pipeline.tf）。pipeline/ の scripts/build-pipeline-image.ps1 が pipeline_image.auto.tfvars（test は pipeline_image.test.tfvars）に書く"
  type        = string
  default     = null

  validation {
    condition     = var.pipeline_image_digest == null || can(regex("^sha256:[0-9a-f]{64}$", var.pipeline_image_digest))
    error_message = "pipeline_image_digest は sha256:<64 桁の 16 進> にしてください（ECR の住所は書かない）。"
  }
}

variable "noncurrent_version_days" {
  description = "上書き・削除された古い版を残す日数"
  type        = number
  default     = 30
}

variable "dev_login_url" {
  description = "手元の dev サーバーの URL（web の npm run dev。Cognito のログインの戻り先に足す）"
  type        = string
  default     = "http://localhost:5173/"
}
