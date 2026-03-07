"""
Shared utility helpers for the AWS Bedrock RAG system.

Provides:
- AWS Secrets Manager access with in-process caching
- Cached boto3 client factories for Bedrock, S3, and Bedrock Agent Runtime
- Document upload and knowledge-base ingestion helpers
"""

import json
import logging
import time
from functools import lru_cache

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


# ── Secrets Manager ───────────────────────────────────────────────────────────

@lru_cache(maxsize=32)
def get_secret(secret_name: str, region_name: str | None = None) -> dict:
    """Retrieve and JSON-parse a secret from AWS Secrets Manager.

    Results are cached per (secret_name, region_name) pair for the lifetime of
    the Python process (Lambda container reuse / script run).

    Args:
        secret_name: Secret name or ARN.
        region_name: AWS region; uses the session default when *None*.

    Returns:
        Parsed secret value as a dict.

    Raises:
        ClientError: If the secret cannot be retrieved.
        ValueError:  If the secret has no string value.
        json.JSONDecodeError: If the secret value is not valid JSON.
    """
    session = boto3.session.Session()
    kwargs: dict = {"service_name": "secretsmanager"}
    if region_name:
        kwargs["region_name"] = region_name

    client = session.client(**kwargs)

    try:
        response = client.get_secret_value(SecretId=secret_name)
    except ClientError:
        logger.exception("Failed to retrieve secret: %s", secret_name)
        raise

    secret_string = response.get("SecretString")
    if not secret_string:
        raise ValueError(f"Secret '{secret_name}' has no SecretString value.")

    return json.loads(secret_string)


# ── Boto3 client factories (cached per region) ────────────────────────────────

@lru_cache(maxsize=8)
def get_bedrock_runtime_client(region: str = "us-east-1"):
    """Return a cached ``bedrock-runtime`` client."""
    return boto3.client("bedrock-runtime", region_name=region)


@lru_cache(maxsize=8)
def get_bedrock_agent_runtime_client(region: str = "us-east-1"):
    """Return a cached ``bedrock-agent-runtime`` client."""
    return boto3.client("bedrock-agent-runtime", region_name=region)


@lru_cache(maxsize=8)
def get_bedrock_agent_client(region: str = "us-east-1"):
    """Return a cached ``bedrock-agent`` management client."""
    return boto3.client("bedrock-agent", region_name=region)


@lru_cache(maxsize=8)
def get_s3_client(region: str = "us-east-1"):
    """Return a cached ``s3`` client."""
    return boto3.client("s3", region_name=region)


# ── S3 helpers ────────────────────────────────────────────────────────────────

def upload_document(
    file_path: str,
    bucket_name: str,
    s3_key: str,
    region: str = "us-east-1",
    metadata: dict[str, str] | None = None,
) -> str:
    """Upload a local file to S3 and return the ``s3://`` URI.

    Args:
        file_path:   Absolute path to the local file.
        bucket_name: Target S3 bucket.
        s3_key:      Destination object key.
        region:      AWS region of the bucket.
        metadata:    Optional user-defined S3 object metadata.

    Returns:
        ``s3://<bucket>/<key>`` URI string.
    """
    client = get_s3_client(region)
    extra_args: dict = {}
    if metadata:
        extra_args["Metadata"] = metadata

    client.upload_file(file_path, bucket_name, s3_key, ExtraArgs=extra_args)
    s3_uri = f"s3://{bucket_name}/{s3_key}"
    logger.info("Uploaded %s → %s", file_path, s3_uri)
    return s3_uri


# ── Bedrock Knowledge Base ingestion helpers ──────────────────────────────────

def start_ingestion_job(
    knowledge_base_id: str,
    data_source_id: str,
    region: str = "us-east-1",
) -> str:
    """Start a Bedrock Knowledge Base ingestion (sync) job.

    Args:
        knowledge_base_id: Bedrock Knowledge Base ID.
        data_source_id:    Data Source ID within the knowledge base.
        region:            AWS region.

    Returns:
        Ingestion job ID string.
    """
    client = get_bedrock_agent_client(region)
    response = client.start_ingestion_job(
        knowledgeBaseId=knowledge_base_id,
        dataSourceId=data_source_id,
    )
    job_id: str = response["ingestionJob"]["ingestionJobId"]
    logger.info("Started ingestion job: %s", job_id)
    return job_id


def get_ingestion_job_status(
    knowledge_base_id: str,
    data_source_id: str,
    ingestion_job_id: str,
    region: str = "us-east-1",
) -> dict:
    """Poll a Bedrock ingestion job and return its current status dict.

    Args:
        knowledge_base_id:  Bedrock Knowledge Base ID.
        data_source_id:     Data Source ID.
        ingestion_job_id:   ID returned by :func:`start_ingestion_job`.
        region:             AWS region.

    Returns:
        The ``ingestionJob`` dict from the Bedrock API response.
    """
    client = get_bedrock_agent_client(region)
    response = client.get_ingestion_job(
        knowledgeBaseId=knowledge_base_id,
        dataSourceId=data_source_id,
        ingestionJobId=ingestion_job_id,
    )
    return response["ingestionJob"]


def wait_for_ingestion_job(
    knowledge_base_id: str,
    data_source_id: str,
    ingestion_job_id: str,
    region: str = "us-east-1",
    poll_interval: int = 10,
    max_wait: int = 1800,
) -> dict:
    """Block until an ingestion job reaches a terminal state.

    Args:
        knowledge_base_id:  Bedrock Knowledge Base ID.
        data_source_id:     Data Source ID.
        ingestion_job_id:   Ingestion job ID.
        region:             AWS region.
        poll_interval:      Seconds between status polls.
        max_wait:           Maximum seconds to wait before raising.

    Returns:
        Final ingestion job status dict.

    Raises:
        TimeoutError: If the job does not complete within *max_wait* seconds.
    """
    terminal_states = {"COMPLETE", "FAILED", "STOPPED"}
    elapsed = 0
    while elapsed < max_wait:
        status = get_ingestion_job_status(
            knowledge_base_id, data_source_id, ingestion_job_id, region
        )
        job_status = status["status"]
        logger.info("Ingestion job %s status: %s", ingestion_job_id, job_status)
        if job_status in terminal_states:
            return status
        time.sleep(poll_interval)
        elapsed += poll_interval

    raise TimeoutError(
        f"Ingestion job {ingestion_job_id} did not complete within {max_wait}s."
    )
