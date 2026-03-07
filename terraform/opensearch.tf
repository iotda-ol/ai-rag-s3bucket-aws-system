# ── Encryption policy (uses CMK, not AWS-owned key) ─────────────────────────

resource "aws_opensearchserverless_security_policy" "encryption" {
  name        = "${local.name_prefix}-enc"
  type        = "encryption"
  description = "CMK encryption for ${local.name_prefix} collection"

  policy = jsonencode({
    Rules = [{
      Resource     = ["collection/${local.name_prefix}-collection"]
      ResourceType = "collection"
    }]
    AWSOwnedKey = false
    KmsARN      = aws_kms_key.main.arn
  })
}

# ── Network policy (public endpoint; Bedrock requires reachability) ──────────

resource "aws_opensearchserverless_security_policy" "network" {
  name        = "${local.name_prefix}-net"
  type        = "network"
  description = "Network policy for ${local.name_prefix} collection"

  policy = jsonencode([{
    Rules = [
      {
        Resource     = ["collection/${local.name_prefix}-collection"]
        ResourceType = "collection"
      },
      {
        Resource     = ["collection/${local.name_prefix}-collection"]
        ResourceType = "dashboard"
      },
    ]
    AllowFromPublic = true
  }])
}

# ── Data access policy ───────────────────────────────────────────────────────

resource "aws_opensearchserverless_access_policy" "main" {
  name        = "${local.name_prefix}-access"
  type        = "data"
  description = "Bedrock KB and Lambda access for ${local.name_prefix}"

  policy = jsonencode([{
    Description = "Allow Bedrock KB role and Lambda role to read/write"
    Rules = [
      {
        Resource     = ["collection/${local.name_prefix}-collection"]
        ResourceType = "collection"
        Permission = [
          "aoss:DescribeCollectionItems",
          "aoss:CreateCollectionItems",
          "aoss:UpdateCollectionItems",
        ]
      },
      {
        Resource     = ["index/${local.name_prefix}-collection/*"]
        ResourceType = "index"
        Permission = [
          "aoss:CreateIndex",
          "aoss:DeleteIndex",
          "aoss:UpdateIndex",
          "aoss:DescribeIndex",
          "aoss:ReadDocument",
          "aoss:WriteDocument",
        ]
      },
    ]
    Principal = [
      aws_iam_role.bedrock_kb.arn,
      aws_iam_role.lambda_exec.arn,
      data.aws_caller_identity.current.arn,
    ]
  }])
}

# ── VECTORSEARCH collection ──────────────────────────────────────────────────

resource "aws_opensearchserverless_collection" "main" {
  name        = "${local.name_prefix}-collection"
  description = "Vector store for ${local.name_prefix} RAG system"
  type        = "VECTORSEARCH"

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-collection"
  })

  depends_on = [
    aws_opensearchserverless_security_policy.encryption,
    aws_opensearchserverless_security_policy.network,
  ]
}

# ── Create the vector index (requires a Python helper via local-exec) ────────

resource "null_resource" "opensearch_index" {
  triggers = {
    collection_id = aws_opensearchserverless_collection.main.id
    index_name    = var.opensearch_index_name
    dimensions    = var.vector_dimensions
  }

  provisioner "local-exec" {
    command = <<-EOT
      python3 ${path.module}/../scripts/create_opensearch_index.py \
        --endpoint "${aws_opensearchserverless_collection.main.collection_endpoint}" \
        --index "${var.opensearch_index_name}" \
        --region "${var.aws_region}" \
        --profile "${var.aws_profile}" \
        --dimensions ${var.vector_dimensions} \
        --vector-field "${local.vector_field_name}" \
        --text-field "${local.text_field_name}" \
        --metadata-field "${local.metadata_field_name}"
    EOT
  }

  depends_on = [
    aws_opensearchserverless_collection.main,
    aws_opensearchserverless_access_policy.main,
  ]
}
