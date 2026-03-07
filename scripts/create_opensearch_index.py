#!/usr/bin/env python3
"""
Creates (or verifies) the OpenSearch Serverless HNSW vector index required by
Amazon Bedrock Knowledge Base.

This script is invoked automatically by ``terraform/opensearch.tf`` as a
``local-exec`` provisioner.  It can also be run standalone:

    python3 scripts/create_opensearch_index.py \\
        --endpoint https://abc123.us-east-1.aoss.amazonaws.com \\
        --index rag-knowledge-base \\
        --region us-east-1 \\
        --profile default \\
        --dimensions 1024

The script authenticates every request with AWS Signature Version 4
(``aoss`` service) so no static credentials are embedded.
"""

import argparse
import json
import logging
import sys
import time

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 24        # up to ~6 minutes for the collection to become active
RETRY_INTERVAL_S = 15


def _signed_request(
    method: str,
    url: str,
    body: str,
    credentials,
    region: str,
) -> requests.Response:
    """Build a SigV4-signed HTTP request and execute it."""
    aws_req = AWSRequest(
        method=method,
        url=url,
        data=body.encode(),
        headers={"Content-Type": "application/json"},
    )
    SigV4Auth(credentials, "aoss", region).add_auth(aws_req)

    return requests.request(
        method=method,
        url=url,
        data=body.encode(),
        headers=dict(aws_req.headers),
        timeout=30,
    )


def create_index(
    endpoint: str,
    index_name: str,
    region: str,
    profile: str,
    dimensions: int,
    vector_field: str,
    text_field: str,
    metadata_field: str,
) -> None:
    """Create an HNSW (faiss) knn_vector index on an OpenSearch Serverless collection.

    Retries for up to ~6 minutes while the collection initialises.  Exits
    successfully if the index already exists.

    Args:
        endpoint:       Collection endpoint URL (``https://…aoss.amazonaws.com``).
        index_name:     Target index name.
        region:         AWS region.
        profile:        AWS CLI profile to use for SigV4 signing.
        dimensions:     Vector dimensions (must match the Bedrock embedding model).
        vector_field:   Name of the knn_vector field.
        text_field:     Name of the full-text source field.
        metadata_field: Name of the metadata storage field.
    """
    session = boto3.Session(profile_name=profile, region_name=region)
    credentials = session.get_credentials().get_frozen_credentials()

    index_body = json.dumps({
        "settings": {
            "index": {
                "knn": True,
                "knn.algo_param.ef_search": 512,
            }
        },
        "mappings": {
            "properties": {
                vector_field: {
                    "type": "knn_vector",
                    "dimension": dimensions,
                    "method": {
                        "name": "hnsw",
                        "engine": "faiss",
                        "space_type": "l2",
                        "parameters": {
                            "ef_construction": 512,
                            "m": 16,
                        },
                    },
                },
                text_field: {"type": "text"},
                metadata_field: {"type": "text"},
            }
        },
    })

    # Normalise endpoint (strip trailing slash)
    base_url = endpoint.rstrip("/")
    url = f"{base_url}/{index_name}"

    logger.info("Target index URL: %s", url)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = _signed_request("PUT", url, index_body, credentials, region)

            if response.status_code == 200:
                logger.info("Index '%s' created successfully.", index_name)
                return

            body_text = response.text or ""

            if response.status_code == 400 and "resource_already_exists_exception" in body_text.lower():
                logger.info("Index '%s' already exists – nothing to do.", index_name)
                return

            logger.warning(
                "Attempt %d/%d – HTTP %d: %s",
                attempt, MAX_ATTEMPTS, response.status_code, body_text[:300],
            )

        except requests.exceptions.ConnectionError as exc:
            logger.warning("Attempt %d/%d – connection error: %s", attempt, MAX_ATTEMPTS, exc)
        except Exception:
            logger.exception("Attempt %d/%d – unexpected error", attempt, MAX_ATTEMPTS)

        if attempt < MAX_ATTEMPTS:
            logger.info("Retrying in %ds …", RETRY_INTERVAL_S)
            time.sleep(RETRY_INTERVAL_S)

    logger.error(
        "Failed to create index '%s' after %d attempts. "
        "Verify that the collection is active and the access policy grants "
        "aoss:CreateIndex to the caller's IAM principal.",
        index_name, MAX_ATTEMPTS,
    )
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create the OpenSearch Serverless vector index for Bedrock KB.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--endpoint", required=True, help="Collection endpoint URL")
    parser.add_argument("--index", required=True, help="Index name")
    parser.add_argument("--region", required=True, help="AWS region")
    parser.add_argument("--profile", required=True, help="AWS CLI profile name")
    parser.add_argument("--dimensions", type=int, default=1024, help="Vector dimensions")
    parser.add_argument(
        "--vector-field",
        default="bedrock-knowledge-base-default-vector",
        help="knn_vector field name",
    )
    parser.add_argument(
        "--text-field",
        default="AMAZON_BEDROCK_TEXT_CHUNK",
        help="Full-text field name",
    )
    parser.add_argument(
        "--metadata-field",
        default="AMAZON_BEDROCK_METADATA",
        help="Metadata field name",
    )

    args = parser.parse_args()

    create_index(
        endpoint=args.endpoint,
        index_name=args.index,
        region=args.region,
        profile=args.profile,
        dimensions=args.dimensions,
        vector_field=args.vector_field,
        text_field=args.text_field,
        metadata_field=args.metadata_field,
    )


if __name__ == "__main__":
    main()
