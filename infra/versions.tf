terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # state は S3 に置き、どの PC からも同じものを使う（README の「state の置き場」）。
  # key は本番（workspace の default）の場所。test（workspace の test）は env:/test/<key> になる（environment.tf）
  # バケットは Terraform の外で作った（非公開・SSE-S3・バージョニング・HTTPS のみ）。
  # use_lockfile：S3 だけでロックする（DynamoDB は使わない）。2 台が同時に apply しても止まる
  backend "s3" {
    bucket       = "ct125-logger-tfstate-535562976288"
    key          = "infra/terraform.tfstate"
    region       = "ap-northeast-1"
    profile      = "ct125-logger"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile

  default_tags {
    # test にだけ Environment のタグを足す（本番のタグは変えない。費用を環境ごとに見られるように）
    tags = merge(
      {
        Project   = "ct125-logger"
        ManagedBy = "terraform"
      },
      local.is_prod ? {} : { Environment = var.env },
    )
  }
}

# CloudFront に付ける証明書（ACM）は us-east-1 に作る決まり。それ以外には使わない
provider "aws" {
  alias   = "us_east_1"
  region  = "us-east-1"
  profile = var.aws_profile

  default_tags {
    # test にだけ Environment のタグを足す（本番のタグは変えない。費用を環境ごとに見られるように）
    tags = merge(
      {
        Project   = "ct125-logger"
        ManagedBy = "terraform"
      },
      local.is_prod ? {} : { Environment = var.env },
    )
  }
}

data "aws_caller_identity" "current" {
  # 選んでいる workspace と、tfvars の env が食い違っていたら止める。
  # 本番の state に test の名前で plan して、本番を作り直す案が出るのを防ぐ（逆も同じ）
  lifecycle {
    precondition {
      condition     = local.workspace_env == var.env
      error_message = "workspace（${terraform.workspace}）と env（${var.env}）が合っていません。本番は workspace の default と terraform.tfvars、test は workspace の test と -var-file=test.tfvars を使ってください（docs/test_environment.md）。"
    }
  }
}
