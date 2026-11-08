variable "aws_profile" {
  description = "~/.aws の CLI プロファイル名（認証情報はここに書かない）"
  type        = string
  default     = "ct125-logger"
}

variable "aws_region" {
  description = "プロジェクトのリージョン（新しい AWS 体験ではプロジェクトごとに固定。AWS Settings で確認）"
  type        = string
  default     = "ap-northeast-1"
}

variable "bucket_prefix" {
  description = "バケット名の先頭。後ろにアカウント ID を付けて一意にする"
  type        = string
  default     = "ct125-logger"
}

variable "app_domain" {
  description = "Web アプリを公開するドメイン（DNS は Cloudflare。プロキシはオフにする）"
  type        = string
  default     = "drive.herdio-system.com"
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
  description = "Cognito のログイン画面の URL の先頭（<prefix>.auth.<region>.amazoncognito.com）。世界で一意"
  type        = string
  default     = "ct125-drive-login"
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

variable "pipeline_image_uri" {
  description = "走行データ処理の Lambda のコンテナイメージ（ECR の digest 付き URI）。pipeline/ の scripts/build-pipeline-image.ps1 が pipeline_image.auto.tfvars に書く"
  type        = string
  default     = null
}

variable "noncurrent_version_days" {
  description = "上書き・削除された古い版を残す日数"
  type        = number
  default     = 30
}
