data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../src"
  output_path = "${path.module}/../build/lambda.zip"
}

resource "aws_lambda_function" "rag_query" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "${local.name_prefix}-query"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "lambda_function.handler"
  runtime          = "python3.12"
  timeout          = var.lambda_timeout
  memory_size      = var.lambda_memory_size
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      RAG_CONFIG_SECRET_NAME     = aws_secretsmanager_secret.rag_config.name
      BEDROCK_CONFIG_SECRET_NAME = aws_secretsmanager_secret.bedrock_config.name
      AWS_REGION_NAME            = var.aws_region
      LOG_LEVEL                  = "INFO"
    }
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
    aws_cloudwatch_log_group.rag_query,
    aws_bedrockagent_knowledge_base.main,
  ]
}

# IAM-authenticated function URL (requires SigV4 – not publicly accessible)
resource "aws_lambda_function_url" "rag_query" {
  function_name      = aws_lambda_function.rag_query.function_name
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
