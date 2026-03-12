# ai-rag-s3bucket-aws-system

Production-ready **Retrieval-Augmented Generation (RAG)** system on AWS, featuring:

- 🤖 **Amazon Bedrock Knowledge Base** – managed RAG with hybrid vector + keyword search
- 📦 **Amazon S3** – encrypted, versioned document storage
- 🔍 **Amazon OpenSearch Serverless** – HNSW vector store
- 🔐 **AWS Secrets Manager** – all runtime parameters stored as secrets (zero hardcoded config)
- 🔑 **AWS KMS** – customer-managed key for all at-rest encryption
- ⚡ **AWS Lambda** – serverless RAG query endpoint with function URL
- 🏗️ **Terraform** – complete IaC; only `aws_profile` is required to deploy

---

## Architecture

```
Documents (PDF, DOCX, TXT…)
       │
       ▼
  ┌──────────┐   PutObject    ┌──────────────────────┐
  │  ingest  │──────────────▶│  S3 bucket (SSE-KMS) │
  │  script  │               │  versioning + logging │
  └──────────┘               └──────────┬───────────┘
                                         │ sync trigger
                                         ▼
                            ┌───────────────────────────┐
                            │  Bedrock Knowledge Base   │
                            │  (titan-embed-text-v2:0)  │
                            └──────────┬────────────────┘
                                       │ embed & index
                                       ▼
                            ┌───────────────────────────┐
                            │  OpenSearch Serverless    │
                            │  HNSW vector index        │
                            └──────────┬────────────────┘
                                       │
               ┌───────────────────────┼───────────────────────┐
               │                       │                       │
      ┌────────▼────────┐   ┌──────────▼──────────┐   ┌───────▼───────┐
      │ Lambda function │   │  AWS Secrets Manager│   │  KMS CMK      │
      │ (rag_query)     │   │  /config            │   │  key rotation │
      │  function URL   │   │  /bedrock           │   └───────────────┘
      │  (AWS_IAM auth) │   │  /opensearch        │
      └────────┬────────┘   └─────────────────────┘
               │
      ┌────────▼────────┐
      │  Bedrock LLM    │
      │  Claude 3 Sonnet│
      └─────────────────┘
```

**Secrets Manager secrets** (all encrypted with the KMS CMK):

| Secret path | Contents |
|---|---|
| `<project>-<env>/config` | bucket name, knowledge-base ID, data-source ID, KMS ARN |
| `<project>-<env>/bedrock` | model IDs, max_tokens, temperature, top_p, prompt template |
| `<project>-<env>/opensearch` | collection ARN/endpoint, index name, field names |

---

## Prerequisites

| Tool | Version |
|---|---|
| [Terraform](https://developer.hashicorp.com/terraform/downloads) | ≥ 1.5 |
| [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) | v2 |
| Python | ≥ 3.12 |
| pip packages | `boto3`, `requests` |

An AWS CLI profile with permissions to create IAM roles, S3, KMS, Secrets Manager, OpenSearch Serverless, Bedrock, and Lambda resources is required.

Enable the Bedrock foundation models you plan to use in the [AWS console](https://console.aws.amazon.com/bedrock/home#/modelaccess) before deploying.

---

## Quick start

### 1 – Configure

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars and set aws_profile = "your-profile-name"
```

### 2 – Deploy

```bash
# Option A: automated script (recommended)
./scripts/deploy.sh

# Option B: manual
pip3 install -r requirements.txt
cd terraform
terraform init
terraform plan -out=../build/tfplan
terraform apply ../build/tfplan
```

The deployment creates all AWS resources and automatically provisions the OpenSearch
vector index via a `local-exec` provisioner.  Typical deployment time is **8–12 minutes**
(most of which is the OpenSearch collection becoming active).

### 3 – Ingest documents

```bash
python3 src/ingest.py ./my-docs/ \
  --secret-name $(terraform -chdir=terraform output -raw rag_config_secret_name) \
  --profile your-profile --wait
```

### 4 – Query

```bash
python3 src/query.py "What is the refund policy?" \
  --config-secret $(terraform -chdir=terraform output -raw rag_config_secret_name) \
  --bedrock-secret $(terraform -chdir=terraform output -raw bedrock_config_secret_name) \
  --profile your-profile
```

Or via the Lambda function URL (requires SigV4 signing):

```bash
# Using curl with --aws-sigv4 (curl ≥ 7.75)
FUNC_URL=$(terraform -chdir=terraform output -raw lambda_function_url)
curl -X POST "$FUNC_URL" \
  --aws-sigv4 "aws:amz:us-east-1:lambda" \
  --user "$(aws configure get aws_access_key_id):$(aws configure get aws_secret_access_key)" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the refund policy?"}'
```

---

## Repository structure

```
.
├── terraform/                      # All AWS infrastructure as code
│   ├── providers.tf                # AWS provider (profile + region)
│   ├── variables.tf                # Input variables (aws_profile is the only required one)
│   ├── locals.tf                   # Name prefixes and OpenSearch field names
│   ├── data.tf                     # Caller identity, KMS key policy document
│   ├── kms.tf                      # Customer-managed KMS key
│   ├── s3.tf                       # Documents bucket + access-log bucket
│   ├── opensearch.tf               # OpenSearch Serverless collection + vector index
│   ├── iam.tf                      # IAM roles for Bedrock KB and Lambda
│   ├── bedrock.tf                  # Bedrock Knowledge Base + S3 data source
│   ├── secrets.tf                  # Three Secrets Manager secrets
│   ├── lambda.tf                   # Lambda function, function URL, CloudWatch log group
│   ├── outputs.tf                  # Terraform outputs
│   └── terraform.tfvars.example    # Template – copy to terraform.tfvars
│
├── src/                            # Python application code
│   ├── lambda_function.py          # Lambda handler (RAG + retrieve modes)
│   ├── utils.py                    # Shared helpers (Secrets Manager, boto3 clients)
│   ├── ingest.py                   # CLI: upload documents + trigger KB sync
│   └── query.py                    # CLI: local RAG / retrieve queries
│
├── scripts/
│   ├── create_opensearch_index.py  # Creates the HNSW vector index (called by Terraform)
│   └── deploy.sh                   # Interactive end-to-end deployment script
│
├── requirements.txt                # Python runtime dependencies
└── .gitignore
```

---

## Terraform variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `aws_profile` | ✅ | – | AWS CLI profile name |
| `aws_region` | | `us-east-1` | Deployment region |
| `project_name` | | `rag-system` | Resource name prefix |
| `environment` | | `dev` | `dev` / `staging` / `prod` |
| `bedrock_embedding_model_id` | | `amazon.titan-embed-text-v2:0` | Embedding model |
| `bedrock_foundation_model_id` | | `anthropic.claude-3-sonnet-20240229-v1:0` | Generation model |
| `vector_dimensions` | | `1024` | Must match the embedding model (1–16000) |
| `opensearch_index_name` | | `rag-knowledge-base` | OpenSearch index name |
| `s3_document_prefix` | | `documents/` | S3 key prefix for source docs |
| `lambda_timeout` | | `60` | Lambda timeout in seconds (1–900) |
| `lambda_memory_size` | | `512` | Lambda memory in MB (128–10240, multiple of 64) |
| `lambda_reserved_concurrent_executions` | | `10` | Reserved Lambda concurrency; `-1` = unreserved |
| `tags` | | `{}` | Additional resource tags |

---

## Lambda API

**Request** (POST, `application/json`):

```json
{
  "query": "What is the SLA for priority-1 incidents?",
  "mode":  "rag"
}
```

`mode` can be `"rag"` (default – retrieve + generate) or `"retrieve"` (chunks only).

**Response** – RAG mode:

```json
{
  "query": "What is the SLA for priority-1 incidents?",
  "mode": "rag",
  "answer": "Priority-1 incidents must be acknowledged within 15 minutes…",
  "citations": [
    {
      "content": "P1 incidents require a 15-minute acknowledgement SLA…",
      "location": {"s3Location": {"uri": "s3://bucket/documents/sla.pdf"}},
      "score": 0.9123
    }
  ],
  "session_id": "abc123"
}
```

**Response** – retrieve mode:

```json
{
  "query": "SLA priority-1",
  "mode": "retrieve",
  "documents": [
    {
      "content": "P1 incidents require a 15-minute acknowledgement SLA…",
      "location": {"s3Location": {"uri": "s3://bucket/documents/sla.pdf"}},
      "score": 0.9123
    }
  ]
}
```

---

## Supported document types

`.pdf` · `.txt` · `.docx` · `.html` · `.md` · `.csv` · `.json` · `.xlsx` · `.pptx`

---

## Tear down

```bash
./scripts/deploy.sh --destroy
# or
terraform -chdir=terraform destroy
```

> **Note:** S3 buckets with objects must be emptied before Terraform can delete them.
> The `aws s3 rm s3://<bucket> --recursive` command empties a bucket.

---

## Security notes

- All data at rest is encrypted with a **customer-managed KMS key** (annual rotation enabled, 30-day deletion window).
- The S3 bucket policy enforces **TLS-only** access.
- The Lambda function URL requires **AWS IAM SigV4** authentication.
- All runtime configuration lives in **Secrets Manager** – no secrets in environment variables or source code.
- IAM roles follow **least-privilege**: each role only has the actions it needs on the exact resources it needs.
- The Lambda Bedrock IAM policy is scoped to specific foundation-model and knowledge-base ARNs (no `Resource: *`).
- The Lambda function has **reserved concurrent executions** (default: 10) to prevent runaway invocations and cost spikes.
- A **dead-letter SQS queue** (encrypted with the CMK) captures any failed async Lambda invocations.
- The documents S3 bucket and KMS key have `prevent_destroy = true` to guard against accidental `terraform destroy`.
- Access logs on the logs bucket expire after **90 days** to control storage costs.

---

## Remote state (recommended for teams)

Terraform state should be stored remotely for any shared or production deployment.
`providers.tf` contains a commented-out `backend "s3"` block with step-by-step instructions.
Create the S3 bucket and DynamoDB lock table, fill in the values, uncomment the block,
then run `terraform init -reconfigure`.

The `.terraform.lock.hcl` dependency lock file **is committed to version control** so that
all contributors and CI pipelines use exactly the same provider versions.

