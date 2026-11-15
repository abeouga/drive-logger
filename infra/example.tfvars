# terraform.tfvars の見本。コピーして terraform.tfvars を作り、<> の所とパスワードを入れる（terraform.tfvars はコミットしない）。
# test の workspace でも読まれる（test.tfvars で上書きしない値は本番と同じ。同じ AWS のプロジェクトを使うため）

# 管理者の AWS のプロファイル・アカウント ID・リージョン（AWS Settings > View all projects > Overview > Additional Info > Region）
aws_profile    = "<管理者のプロファイル>"
aws_account_id = "<アカウントID（12 桁）>"
aws_region     = "<AWS の project の Region>"

# 画面のドメインの親（本番 drive.<これ>、test drive-test.<これ>。DNS は Cloudflare）
base_domain = "<example.com>"

app_users = {
  admin = { is_admin = true }
  guest = { is_admin = false }
}

app_user_passwords = {
  admin = "<8 文字以上、英小文字と数字を含む>"
  guest = "<8 文字以上、英小文字と数字を含む>"
}
