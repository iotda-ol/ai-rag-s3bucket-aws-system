#!/usr/bin/env python3
"""
Document ingestion CLI for the AWS Bedrock RAG system.

Uploads one or more documents to the RAG S3 bucket and optionally triggers
a Bedrock Knowledge Base sync.  All connection parameters are read from
AWS Secrets Manager; only ``--secret-name`` and the source path are required.

Usage examples::

    # Ingest a single PDF and wait for the sync to finish
    python3 ingest.py docs/handbook.pdf \\
        --secret-name rag-system-dev/config --wait

    # Ingest an entire folder without syncing (upload only)
    python3 ingest.py ./corpus/ \\
        --secret-name rag-system-dev/config --no-sync

    # Use a non-default AWS profile
    python3 ingest.py docs/ \\
        --secret-name rag-system-prod/config --profile prod --wait
"""

import argparse
import logging
import sys
import time
from pathlib import Path

import boto3

from utils import (
    get_secret,
    upload_document,
    start_ingestion_job,
    wait_for_ingestion_job,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".pdf", ".txt", ".docx", ".html", ".md",
    ".csv", ".json", ".xlsx", ".pptx",
}


def ingest_documents(
    source_path: str,
    config_secret_name: str,
    profile: str | None = None,
    region: str = "us-east-1",
    sync: bool = True,
    wait: bool = False,
) -> int:
    """Upload documents to S3 and optionally sync the knowledge base.

    Args:
        source_path:         Path to a file or directory.
        config_secret_name:  Secrets Manager secret name that holds RAG config.
        profile:             AWS CLI profile name.
        region:              AWS region.
        sync:                Whether to trigger a knowledge base sync after upload.
        wait:                Whether to block until the sync job completes.

    Returns:
        Number of documents successfully uploaded.
    """
    if profile:
        boto3.setup_default_session(profile_name=profile, region_name=region)

    config = get_secret(config_secret_name, region)
    bucket_name: str = config["s3_bucket_name"]
    prefix: str = config.get("s3_document_prefix", "documents/")
    knowledge_base_id: str = config["knowledge_base_id"]
    data_source_id: str = config["data_source_id"]

    source = Path(source_path)
    if not source.exists():
        logger.error("Path does not exist: %s", source_path)
        sys.exit(1)

    # Collect files to upload
    if source.is_file():
        files = [source]
    else:
        files = [
            f for f in source.rglob("*")
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        ]

    if not files:
        logger.warning(
            "No supported documents found in %s (extensions: %s)",
            source_path,
            ", ".join(sorted(SUPPORTED_EXTENSIONS)),
        )
        return 0

    logger.info(
        "Uploading %d document(s) to s3://%s/%s …", len(files), bucket_name, prefix
    )

    uploaded = 0
    base = source if source.is_dir() else source.parent
    for file_path in files:
        relative = file_path.relative_to(base)
        s3_key = f"{prefix}{relative}"
        try:
            upload_document(
                str(file_path),
                bucket_name,
                s3_key,
                region,
                metadata={
                    "source-path": str(file_path),
                    "ingested-by": "rag-ingest-script",
                },
            )
            uploaded += 1
        except Exception:
            logger.exception("Failed to upload: %s", file_path)

    logger.info("Uploaded %d / %d document(s).", uploaded, len(files))

    if sync and uploaded > 0:
        logger.info("Triggering knowledge base sync …")
        job_id = start_ingestion_job(knowledge_base_id, data_source_id, region)
        logger.info("Ingestion job started: %s", job_id)

        if wait:
            logger.info("Waiting for ingestion job to complete …")
            result = wait_for_ingestion_job(
                knowledge_base_id, data_source_id, job_id, region
            )
            status = result["status"]
            if status == "COMPLETE":
                stats = result.get("statistics", {})
                logger.info("Ingestion complete. Statistics: %s", stats)
            else:
                reasons = result.get("failureReasons", [])
                logger.error("Ingestion ended with status %s: %s", status, reasons)
                sys.exit(1)

    return uploaded


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest documents into the Bedrock RAG knowledge base.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("source", help="File or directory to ingest")
    parser.add_argument(
        "--secret-name",
        required=True,
        metavar="SECRET",
        help="Secrets Manager secret name, e.g. rag-system-dev/config",
    )
    parser.add_argument("--profile", default=None, help="AWS CLI profile name")
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    parser.add_argument(
        "--no-sync",
        action="store_true",
        help="Upload documents but do not trigger a knowledge base sync",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Block until the sync job completes (implies --sync)",
    )

    args = parser.parse_args()
    ingest_documents(
        source_path=args.source,
        config_secret_name=args.secret_name,
        profile=args.profile,
        region=args.region,
        sync=not args.no_sync,
        wait=args.wait,
    )


if __name__ == "__main__":
    main()
