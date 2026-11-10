# 画面のドメイン（local.app_domain。本番は drive.herdio-system.com）の証明書（CloudFront 用なので us-east-1）。
# DNS は Cloudflare なので、検証用の CNAME は Cloudflare の画面で足す（terraform output certificate_validation_record）。

resource "aws_acm_certificate" "app" {
  provider          = aws.us_east_1
  domain_name       = local.app_domain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# Cloudflare に CNAME を足して発行されるまで待つ（最大 45 分）
resource "aws_acm_certificate_validation" "app" {
  provider        = aws.us_east_1
  certificate_arn = aws_acm_certificate.app.arn

  timeouts {
    create = "45m"
  }
}
