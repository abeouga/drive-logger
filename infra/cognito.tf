# Web アプリのログイン（Cognito ユーザープール）。
# - 新規登録はできない。ユーザーは terraform.tfvars の app_users / app_user_passwords から作る
#   （destroy して作り直しても、同じユーザー名・パスワードで自動的に戻る）
# - ログイン画面は Cognito の managed login。ブラウザは認可コード＋PKCE（クライアントシークレットなし）

resource "aws_cognito_user_pool" "app" {
  name = "${local.name_prefix}-app-users"
  # ユーザーは Terraform から作り直せるので、destroy できるように保護はかけない
  deletion_protection = "INACTIVE"
  user_pool_tier      = "ESSENTIALS"
  mfa_configuration   = "OFF"

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  username_configuration {
    case_sensitive = false
  }

  # 新規登録を閉じ、管理者が Terraform で作る少数のユーザーだけが使うので、条件は最低限にしている（8 文字以上・英小文字と数字）
  password_policy {
    minimum_length                   = 8
    require_lowercase                = true
    require_uppercase                = false
    require_numbers                  = true
    require_symbols                  = false
    temporary_password_validity_days = 7
  }

  # メールを登録しないので、パスワードを忘れたら管理者が設定し直す
  account_recovery_setting {
    recovery_mechanism {
      name     = "admin_only"
      priority = 1
    }
  }
}

resource "aws_cognito_user_group" "admin" {
  name         = "admin"
  user_pool_id = aws_cognito_user_pool.app.id
  description  = "管理者（今はデータの見え方は他のユーザーと同じ）"
}

resource "aws_cognito_user_pool_client" "web" {
  name         = "${local.name_prefix}-app-web"
  user_pool_id = aws_cognito_user_pool.app.id

  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid"]
  supported_identity_providers         = ["COGNITO"]
  # 手元の dev サーバー（web の npm run dev）からもログインできるように localhost を足す（#18）。
  # 認可コードは PKCE で守るので、ほかの人が localhost を開いてもコードだけでは使えない
  callback_urls = ["https://${local.app_domain}/", var.dev_login_url]
  logout_urls   = ["https://${local.app_domain}/", var.dev_login_url]

  explicit_auth_flows           = ["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true

  # API に付けるトークンは短く保ち、期限が切れたら更新用のトークンで取り直す。
  # 更新用のトークンは 30 日にして、1 か月はログインし直さずに使えるようにする（#63）
  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 30
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
}

resource "aws_cognito_user_pool_domain" "app" {
  domain                = local.cognito_domain_prefix
  user_pool_id          = aws_cognito_user_pool.app.id
  managed_login_version = 2
}

# managed login（新しいログイン画面）の見た目。Cognito の既定のデザインを使う
resource "aws_cognito_managed_login_branding" "web" {
  user_pool_id                = aws_cognito_user_pool.app.id
  client_id                   = aws_cognito_user_pool_client.web.id
  use_cognito_provided_values = true
}
