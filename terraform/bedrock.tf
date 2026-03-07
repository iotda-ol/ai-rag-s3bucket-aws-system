resource "aws_bedrockagent_knowledge_base" "main" {
  name        = "${local.name_prefix}-kb"
  description = "RAG knowledge base for ${var.project_name} (${var.environment})"
  role_arn    = aws_iam_role.bedrock_kb.arn

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:${data.aws_partition.current.partition}:bedrock:${var.aws_region}::foundation-model/${var.bedrock_embedding_model_id}"
    }
  }

  storage_configuration {
    type = "OPENSEARCH_SERVERLESS"
    opensearch_serverless_configuration {
      collection_arn    = aws_opensearchserverless_collection.main.arn
      vector_index_name = var.opensearch_index_name
      field_mapping {
        vector_field   = local.vector_field_name
        text_field     = local.text_field_name
        metadata_field = local.metadata_field_name
      }
    }
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-kb"
  })

  depends_on = [
    aws_iam_role_policy.bedrock_kb_s3,
    aws_iam_role_policy.bedrock_kb_opensearch,
    aws_iam_role_policy.bedrock_kb_model,
    aws_iam_role_policy.bedrock_kb_kms,
    null_resource.opensearch_index,
  ]
}

resource "aws_bedrockagent_data_source" "s3" {
  knowledge_base_id = aws_bedrockagent_knowledge_base.main.id
  name              = "${local.name_prefix}-s3-source"
  description       = "S3 document source for ${local.name_prefix} knowledge base"

  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn         = aws_s3_bucket.documents.arn
      inclusion_prefixes = [var.s3_document_prefix]
    }
  }

  server_side_encryption_configuration {
    kms_key_arn = aws_kms_key.main.arn
  }

  vector_ingestion_configuration {
    chunking_configuration {
      chunking_strategy = "FIXED_SIZE"
      fixed_size_chunking_configuration {
        max_tokens         = 512
        overlap_percentage = 20
      }
    }
  }

  depends_on = [aws_bedrockagent_knowledge_base.main]
}
