# test 環境の tfvars の見本。コピーして test.tfvars を作り、パスワードを入れる（test.tfvars はコミットしない）。
# 使い方は docs/test_environment.md（workspace の test で -var-file=test.tfvars -var-file=pipeline_image.test.tfvars を付ける）

env = "test"

# test 用のログインの利用者（本番とは別のユーザープール。本番と同じパスワードにしない）
app_users = {
  admin = { is_admin = true }
  guest = { is_admin = false }
}

app_user_passwords = {
  admin = "<8 文字以上、英小文字と数字を含む>"
  guest = "<8 文字以上、英小文字と数字を含む>"
}

# 画面のドメインとログイン画面の URL の先頭。書かなければ drive-test.herdio-system.com と ct125-drive-login-test
# app_domain            = "drive-test.herdio-system.com"
# cognito_domain_prefix = "ct125-drive-login-test"
