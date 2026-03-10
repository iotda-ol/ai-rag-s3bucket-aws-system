terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
  }

  # ── Remote state (recommended for all shared/production deployments) ────────
  #
  # Before enabling, create the backend resources once:
  #   aws s3 mb s3://<tfstate-bucket> --region us-east-1
  #   aws s3api put-bucket-versioning --bucket <tfstate-bucket> \
  #       --versioning-configuration Status=Enabled
  #   aws s3api put-bucket-encryption --bucket <tfstate-bucket> \
  #       --server-side-encryption-configuration \
  #       '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"aws:kms"}}]}'
  #   aws dynamodb create-table --table-name terraform-state-lock \
  #       --attribute-definitions AttributeName=LockID,AttributeType=S \
  #       --key-schema AttributeName=LockID,KeyType=HASH \
  #       --billing-mode PAY_PER_REQUEST --region us-east-1
  #
  # Then uncomment the block below and run: terraform init -reconfigure
  #
  # backend "s3" {
  #   bucket         = "<tfstate-bucket>"
  #   key            = "rag-system/terraform.tfstate"
  #   region         = "us-east-1"
  #   encrypt        = true
  #   kms_key_id     = "alias/<tfstate-kms-key>"
  #   dynamodb_table = "terraform-state-lock"
  # }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
