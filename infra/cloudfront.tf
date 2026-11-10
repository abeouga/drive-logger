# Web アプリの配信：https://<local.app_domain>/ を CloudFront で配る。
#   /*      → S3 の webapp/（React のビルド結果。走行データは入っていない）。バケットは非公開のまま、OAC で CloudFront だけが読める
#   /api/*  → API Gateway（データ API。ログインが必要）

data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_cache_policy" "caching_disabled" {
  name = "Managed-CachingDisabled"
}

# API Gateway には Host 以外のヘッダー（Authorization を含む）をそのまま渡す
data "aws_cloudfront_origin_request_policy" "all_viewer_except_host" {
  name = "Managed-AllViewerExceptHostHeader"
}

# HSTS・nosniff・フレーム埋め込み禁止などの基本のセキュリティヘッダー
data "aws_cloudfront_response_headers_policy" "security_headers" {
  name = "Managed-SecurityHeadersPolicy"
}

resource "aws_cloudfront_origin_access_control" "webapp" {
  name                              = "${local.name_prefix}-webapp"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

locals {
  webapp_origin_id = "webapp-s3"
  api_origin_id    = "data-api"
}

resource "aws_cloudfront_distribution" "app" {
  enabled             = true
  comment             = local.is_prod ? "CT125 走行データ Web アプリ" : "CT125 走行データ Web アプリ（${var.env}）"
  aliases             = [local.app_domain]
  default_root_object = "index.html"
  is_ipv6_enabled     = true
  http_version        = "http2and3"
  price_class         = "PriceClass_200" # 日本を含む

  origin {
    origin_id                = local.webapp_origin_id
    domain_name              = aws_s3_bucket.data.bucket_regional_domain_name
    origin_path              = "/${var.webapp_prefix}"
    origin_access_control_id = aws_cloudfront_origin_access_control.webapp.id
  }

  origin {
    origin_id   = local.api_origin_id
    domain_name = replace(aws_apigatewayv2_api.data.api_endpoint, "https://", "")

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id           = local.webapp_origin_id
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.caching_optimized.id
    response_headers_policy_id = data.aws_cloudfront_response_headers_policy.security_headers.id
  }

  ordered_cache_behavior {
    path_pattern           = "/api/*"
    target_origin_id       = local.api_origin_id
    viewer_protocol_policy = "https-only"
    # POST は機器からの受付（/api/device/*）で使う。CloudFront は「全部」か「GET 系だけ」しか選べない
    allowed_methods            = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id   = data.aws_cloudfront_origin_request_policy.all_viewer_except_host.id
    response_headers_policy_id = data.aws_cloudfront_response_headers_policy.security_headers.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.app.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}
