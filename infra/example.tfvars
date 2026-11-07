# terraform.tfvars の見本。コピーして terraform.tfvars を作り、パスワードを入れる（terraform.tfvars はコミットしない）

app_users = {
  admin       = { is_admin = true }
  guest       = { is_admin = false }
}

app_user_passwords = {
  admin       = "<8 文字以上、英小文字と数字を含む>"
  guest       = "<8 文字以上、英小文字と数字を含む>"
}
