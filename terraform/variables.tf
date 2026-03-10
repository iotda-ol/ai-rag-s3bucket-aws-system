variable "aws_profile" {
  description = "AWS CLI profile name to use for authentication. This is the only required input."
  type        = string
}

variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used as prefix for all resource names"
  type        = string
  default     = "rag-system"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "bedrock_embedding_model_id" {
  description = "Amazon Bedrock embedding model ID for generating vector embeddings"
  type        = string
  default     = "amazon.titan-embed-text-v2:0"
}

variable "bedrock_foundation_model_id" {
  description = "Amazon Bedrock foundation model ID for text generation"
  type        = string
  default     = "anthropic.claude-3-sonnet-20240229-v1:0"
}

variable "vector_dimensions" {
  description = "Embedding vector dimensions (must match the chosen embedding model)"
  type        = number
  default     = 1024

  validation {
    condition     = var.vector_dimensions > 0 && var.vector_dimensions <= 16000
    error_message = "Vector dimensions must be between 1 and 16000."
  }
}

variable "opensearch_index_name" {
  description = "OpenSearch Serverless index name for the vector store"
  type        = string
  default     = "rag-knowledge-base"
}

variable "s3_document_prefix" {
  description = "S3 key prefix for knowledge base source documents"
  type        = string
  default     = "documents/"
}

variable "lambda_timeout" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 60

  validation {
    condition     = var.lambda_timeout >= 1 && var.lambda_timeout <= 900
    error_message = "Lambda timeout must be between 1 and 900 seconds."
  }
}

variable "lambda_memory_size" {
  description = "Lambda function memory size in MB"
  type        = number
  default     = 512

  validation {
    condition     = var.lambda_memory_size >= 128 && var.lambda_memory_size <= 10240 && var.lambda_memory_size % 64 == 0
    error_message = "Lambda memory size must be between 128 and 10240 MB and a multiple of 64."
  }
}

variable "lambda_reserved_concurrent_executions" {
  description = "Reserved concurrent executions for the Lambda function. Use -1 for unreserved (default: 10 to prevent runaway invocations)."
  type        = number
  default     = 10

  validation {
    condition     = var.lambda_reserved_concurrent_executions >= -1
    error_message = "Reserved concurrent executions must be -1 (unreserved) or a non-negative integer."
  }
}

variable "tags" {
  description = "Additional resource tags to merge with defaults"
  type        = map(string)
  default     = {}
}
