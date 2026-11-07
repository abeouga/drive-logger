terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
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
