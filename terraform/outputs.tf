output "s3_bucket_name" {
  description = "S3 bucket name for RAG source documents"
  value       = aws_s3_bucket.documents.id
}

output "s3_bucket_arn" {
  description = "S3 bucket ARN"
  value       = aws_s3_bucket.documents.arn
}

output "knowledge_base_id" {
  description = "Bedrock Knowledge Base ID"
  value       = aws_bedrockagent_knowledge_base.main.id
}

output "data_source_id" {
  description = "Bedrock Data Source ID"
  value       = aws_bedrockagent_data_source.s3.data_source_id
}

output "opensearch_collection_arn" {
  description = "OpenSearch Serverless collection ARN"
  value       = aws_opensearchserverless_collection.main.arn
}

output "opensearch_endpoint" {
  description = "OpenSearch Serverless collection endpoint"
  value       = aws_opensearchserverless_collection.main.collection_endpoint
}

output "lambda_function_name" {
  description = "RAG query Lambda function name"
  value       = aws_lambda_function.rag_query.function_name
}

output "lambda_function_alias" {
  description = "Lambda function live alias name"
  value       = aws_lambda_alias.rag_query_live.name
}

output "lambda_function_url" {
  description = "Lambda function URL (requires AWS_IAM SigV4 auth)"
  value       = aws_lambda_function_url.rag_query.function_url
}

output "lambda_dlq_arn" {
  description = "ARN of the Lambda dead-letter SQS queue"
  value       = aws_sqs_queue.lambda_dlq.arn
}

output "kms_key_id" {
  description = "KMS CMK key ID"
  value       = aws_kms_key.main.key_id
}

output "kms_key_arn" {
  description = "KMS CMK key ARN"
  value       = aws_kms_key.main.arn
  sensitive   = true
}

output "kms_key_alias" {
  description = "KMS CMK alias"
  value       = aws_kms_alias.main.name
}

output "rag_config_secret_name" {
  description = "Secrets Manager secret name for RAG configuration"
  value       = aws_secretsmanager_secret.rag_config.name
}

output "rag_config_secret_arn" {
  description = "Secrets Manager secret ARN for RAG configuration"
  value       = aws_secretsmanager_secret.rag_config.arn
}

output "bedrock_config_secret_name" {
  description = "Secrets Manager secret name for Bedrock model configuration"
  value       = aws_secretsmanager_secret.bedrock_config.name
}

output "bedrock_config_secret_arn" {
  description = "Secrets Manager secret ARN for Bedrock model configuration"
  value       = aws_secretsmanager_secret.bedrock_config.arn
}

output "opensearch_config_secret_arn" {
  description = "Secrets Manager secret ARN for OpenSearch configuration"
  value       = aws_secretsmanager_secret.opensearch_config.arn
}

output "aws_region" {
  description = "AWS region where resources are deployed"
  value       = var.aws_region
}

output "account_id" {
  description = "AWS account ID"
  value       = data.aws_caller_identity.current.account_id
}
