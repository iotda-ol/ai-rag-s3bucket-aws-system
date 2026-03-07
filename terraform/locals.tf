locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = merge(
    {
      Project     = var.project_name
      Environment = var.environment
    },
    var.tags,
  )

  # OpenSearch field names required by Amazon Bedrock Knowledge Base
  vector_field_name   = "bedrock-knowledge-base-default-vector"
  text_field_name     = "AMAZON_BEDROCK_TEXT_CHUNK"
  metadata_field_name = "AMAZON_BEDROCK_METADATA"
}
