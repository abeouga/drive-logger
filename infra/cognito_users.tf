# ログインできるユーザー。terraform apply のたびに、terraform.tfvars の内容どおりにそろえる。
# パスワードは terraform.tfvars（コミットしない）に書き、state にも入る（state もコミットしない）。

resource "aws_cognito_user" "app" {
  for_each = var.app_users

  user_pool_id   = aws_cognito_user_pool.app.id
  username       = each.key
  password       = var.app_user_passwords[each.key] # 初回ログインでの変更を求めない、恒久のパスワード
  message_action = "SUPPRESS"                       # 招待メールは送らない
}

locals {
  admin_usernames = [for name, user in var.app_users : name if user.is_admin]
}

resource "aws_cognito_user_in_group" "admin" {
  for_each = toset(local.admin_usernames)

  user_pool_id = aws_cognito_user_pool.app.id
  group_name   = aws_cognito_user_group.admin.name
  username     = aws_cognito_user.app[each.key].username
}
