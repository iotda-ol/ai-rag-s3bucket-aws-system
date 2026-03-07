# ── RAG system configuration (bucket, KB IDs, model IDs) ─────────────────────

resource "aws_secretsmanager_secret" "rag_config" {
  name                    = "${local.name_prefix}/config"
  description             = "RAG system runtime configuration – bucket, knowledge base, and model IDs"
  kms_key_id              = aws_kms_key.main.arn
  recovery_window_in_days = 7

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-config"
  })
}

resource "aws_secretsmanager_secret_version" "rag_config" {
  secret_id = aws_secretsmanager_secret.rag_config.id

  secret_string = jsonencode({
    project_name       = var.project_name
    environment        = var.environment
    aws_region         = var.aws_region
    s3_bucket_name     = aws_s3_bucket.documents.id
    s3_bucket_arn      = aws_s3_bucket.documents.arn
    s3_document_prefix = var.s3_document_prefix
    knowledge_base_id  = aws_bedrockagent_knowledge_base.main.id
    data_source_id     = aws_bedrockagent_data_source.s3.data_source_id
    kms_key_id         = aws_kms_key.main.key_id
    kms_key_arn        = aws_kms_key.main.arn
  })

  depends_on = [
    aws_bedrockagent_knowledge_base.main,
    aws_bedrockagent_data_source.s3,
  ]
}

# ── Bedrock model and inference parameters ───────────────────────────────────

resource "aws_secretsmanager_secret" "bedrock_config" {
  name                    = "${local.name_prefix}/bedrock"
  description             = "Bedrock model IDs and inference hyper-parameters"
  kms_key_id              = aws_kms_key.main.arn
  recovery_window_in_days = 7

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-bedrock-config"
  })
}

resource "aws_secretsmanager_secret_version" "bedrock_config" {
  secret_id = aws_secretsmanager_secret.bedrock_config.id

  secret_string = jsonencode({
    foundation_model_id = var.bedrock_foundation_model_id
    embedding_model_id  = var.bedrock_embedding_model_id
    max_tokens          = 2048
    temperature         = 0.1
    top_p               = 0.9
    number_of_results   = 5
    search_type         = "HYBRID"
    prompt_template     = "You are a knowledgeable assistant. Use only the retrieved context below to answer the user's question accurately and concisely. If the context does not contain enough information, say so.\n\nContext:\n$search_results$\n\nQuestion: $query$\n\nAnswer:"
  })
}

# ── OpenSearch Serverless parameters ─────────────────────────────────────────

resource "aws_secretsmanager_secret" "opensearch_config" {
  name                    = "${local.name_prefix}/opensearch"
  description             = "OpenSearch Serverless collection endpoint and index configuration"
  kms_key_id              = aws_kms_key.main.arn
  recovery_window_in_days = 7

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-opensearch-config"
  })
}

resource "aws_secretsmanager_secret_version" "opensearch_config" {
  secret_id = aws_secretsmanager_secret.opensearch_config.id

  secret_string = jsonencode({
    collection_arn      = aws_opensearchserverless_collection.main.arn
    collection_endpoint = aws_opensearchserverless_collection.main.collection_endpoint
    collection_name     = aws_opensearchserverless_collection.main.name
    index_name          = var.opensearch_index_name
    vector_field        = local.vector_field_name
    text_field          = local.text_field_name
    metadata_field      = local.metadata_field_name
    vector_dimensions   = var.vector_dimensions
  })
}
