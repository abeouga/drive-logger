terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # state は S3 に置き、どの PC からも同じものを使う（README の「state の置き場」）。
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
    tags = {
      Project   = "ct125-logger"
      ManagedBy = "terraform"
    }
  }
}

# CloudFront に付ける証明書（ACM）は us-east-1 に作る決まり。それ以外には使わない
provider "aws" {
  alias   = "us_east_1"
  region  = "us-east-1"
  profile = var.aws_profile

  default_tags {
    tags = {
      Project   = "ct125-logger"
      ManagedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}
