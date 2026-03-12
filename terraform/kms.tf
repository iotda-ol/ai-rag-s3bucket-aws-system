resource "aws_kms_key" "main" {
  description             = "KMS CMK for ${local.name_prefix} – encrypts S3, Secrets Manager, Lambda, and CloudWatch Logs"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.kms_key_policy.json

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-cmk"
  })

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_kms_alias" "main" {
  name          = "alias/${local.name_prefix}"
  target_key_id = aws_kms_key.main.key_id
}
