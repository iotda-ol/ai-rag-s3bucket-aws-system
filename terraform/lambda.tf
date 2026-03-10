data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../src"
  output_path = "${path.module}/../build/lambda.zip"
}

# ── Dead-letter queue ────────────────────────────────────────────────────────

resource "aws_sqs_queue" "lambda_dlq" {
  name              = "${local.name_prefix}-lambda-dlq"
  kms_master_key_id = aws_kms_key.main.key_id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-lambda-dlq"
  })
}

# ── Lambda function ──────────────────────────────────────────────────────────

resource "aws_lambda_function" "rag_query" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "${local.name_prefix}-query"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "lambda_function.handler"
  runtime          = "python3.12"
  timeout          = var.lambda_timeout
  memory_size      = var.lambda_memory_size
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  publish          = true

  reserved_concurrent_executions = var.lambda_reserved_concurrent_executions

  environment {
    variables = {
      RAG_CONFIG_SECRET_NAME     = aws_secretsmanager_secret.rag_config.name
      BEDROCK_CONFIG_SECRET_NAME = aws_secretsmanager_secret.bedrock_config.name
      AWS_REGION_NAME            = var.aws_region
      LOG_LEVEL                  = "INFO"
    }
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.lambda_dlq.arn
  }

  kms_key_arn = aws_kms_key.main.arn

  tracing_config {
    mode = "Active"
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-query"
  })

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic,
    aws_iam_role_policy.lambda_bedrock,
    aws_iam_role_policy.lambda_secrets,
    aws_iam_role_policy.lambda_kms,
    aws_iam_role_policy.lambda_dlq,
    aws_cloudwatch_log_group.rag_query,
    aws_bedrockagent_knowledge_base.main,
  ]
}

# ── Stable alias pointing at the published version ──────────────────────────

resource "aws_lambda_alias" "rag_query_live" {
  name             = "live"
  description      = "Live traffic alias for ${local.name_prefix}-query"
  function_name    = aws_lambda_function.rag_query.function_name
  function_version = aws_lambda_function.rag_query.version
}

# IAM-authenticated function URL (requires SigV4 – not publicly accessible)
resource "aws_lambda_function_url" "rag_query" {
  function_name      = aws_lambda_function.rag_query.function_name
  qualifier          = aws_lambda_alias.rag_query_live.name
  authorization_type = "AWS_IAM"
}

resource "aws_cloudwatch_log_group" "rag_query" {
  name              = "/aws/lambda/${local.name_prefix}-query"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.main.arn

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-lambda-logs"
  })
}
