# ローカル（PC）の処理に使うロール（docs/data_flow_design.md 11.）。
# 生データを読み、作業用に読み書きできるが、公開用（画面が読む場所）には書けない。公開は処理の Lambda に頼む。
# PC の CLI は、このロールを管理者のプロファイル（ct125-logger）から引き受けて使う（~/.aws/config の例は infra/README.md）。
# 人のログイン（AWS Settings で管理）には手を加えない。このロールはこの処理のためだけに使う。

resource "aws_iam_role" "local_pipeline" {
  name                 = "ct125-local-pipeline"
  description          = "Local pipeline CLI (python -m ct125 process/retrain). Cannot write the public bucket." # IAM の説明に日本語は使えない
  max_session_duration = 3600

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" } # このアカウントで、引き受ける権限を持つ人だけ
    }]
  })
}

data "aws_iam_policy_document" "local_pipeline" {
  statement {
    sid       = "ReadRaw"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.role["raw"].arn}/*"]
  }
  statement {
    sid       = "ReadWriteWork"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.role["work"].arn}/*"]
  }
  statement {
    sid       = "ListRawAndWork"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.role["raw"].arn, aws_s3_bucket.role["work"].arn]
  }
}

resource "aws_iam_role_policy" "local_pipeline" {
  name   = "ct125-local-pipeline-policy"
  role   = aws_iam_role.local_pipeline.id
  policy = data.aws_iam_policy_document.local_pipeline.json
}
