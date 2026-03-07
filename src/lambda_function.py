"""
AWS Lambda handler for the Bedrock RAG query endpoint.

All runtime configuration is read from AWS Secrets Manager at cold-start and
cached for the lifetime of the Lambda container.  The function supports two
modes via the ``mode`` request field:

* ``"rag"`` (default) – Retrieve relevant chunks **and** generate an answer
  with the configured foundation model.
* ``"retrieve"`` – Return the top-k retrieved text chunks without generation.

Expected request body (JSON):

.. code-block:: json

    {
        "query": "What is the refund policy?",
        "mode":  "rag"
    }

The Lambda function URL uses ``AWS_IAM`` authorization; callers must sign
requests with SigV4.
"""

import json
import logging
import os
from typing import Any

from botocore.exceptions import ClientError

from utils import get_secret, get_bedrock_agent_runtime_client

logger = logging.getLogger()
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logger.setLevel(getattr(logging, log_level, logging.INFO))

# ── In-process config cache (survives Lambda container reuse) ─────────────────
_config_cache: dict[str, Any] = {}


def _load_config() -> dict[str, Any]:
    """Load and merge RAG + Bedrock secrets on first invocation."""
    if _config_cache:
        return _config_cache

    rag_secret_name = os.environ["RAG_CONFIG_SECRET_NAME"]
    bedrock_secret_name = os.environ["BEDROCK_CONFIG_SECRET_NAME"]
    region = os.environ.get("AWS_REGION_NAME", "us-east-1")

    rag_cfg = get_secret(rag_secret_name, region)
    bedrock_cfg = get_secret(bedrock_secret_name, region)

    _config_cache.update({**rag_cfg, **bedrock_cfg})
    logger.info(
        "Configuration loaded from Secrets Manager (KB: %s, model: %s)",
        _config_cache.get("knowledge_base_id"),
        _config_cache.get("foundation_model_id"),
    )
    return _config_cache


# ── RAG helpers ───────────────────────────────────────────────────────────────

def _retrieve_and_generate(query: str, config: dict) -> dict:
    """Call Bedrock RetrieveAndGenerate and return a structured result."""
    region = config["aws_region"]
    kb_id = config["knowledge_base_id"]
    model_id = config["foundation_model_id"]
    model_arn = f"arn:aws:bedrock:{region}::foundation-model/{model_id}"

    client = get_bedrock_agent_runtime_client(region)

    response = client.retrieve_and_generate(
        input={"text": query},
        retrieveAndGenerateConfiguration={
            "type": "KNOWLEDGE_BASE",
            "knowledgeBaseConfiguration": {
                "knowledgeBaseId": kb_id,
                "modelArn": model_arn,
                "retrievalConfiguration": {
                    "vectorSearchConfiguration": {
                        "numberOfResults": int(config.get("number_of_results", 5)),
                        "overrideSearchType": config.get("search_type", "HYBRID"),
                    }
                },
                "generationConfiguration": {
                    "inferenceConfig": {
                        "textInferenceConfig": {
                            "maxTokens": int(config.get("max_tokens", 2048)),
                            "temperature": float(config.get("temperature", 0.1)),
                            "topP": float(config.get("top_p", 0.9)),
                        }
                    },
                    "promptTemplate": {
                        "textPromptTemplate": config.get(
                            "prompt_template",
                            "Answer using this context:\n$search_results$\n\nQ: $query$\nA:",
                        )
                    },
                },
            },
        },
    )

    citations = [
        {
            "content": ref.get("content", {}).get("text", ""),
            "location": ref.get("location", {}),
            "score": ref.get("score", 0),
        }
        for citation in response.get("citations", [])
        for ref in citation.get("retrievedReferences", [])
    ]

    return {
        "answer": response["output"]["text"],
        "citations": citations,
        "session_id": response.get("sessionId"),
    }


def _retrieve_only(query: str, config: dict) -> dict:
    """Call Bedrock Retrieve and return matching document chunks."""
    region = config["aws_region"]
    kb_id = config["knowledge_base_id"]

    client = get_bedrock_agent_runtime_client(region)

    response = client.retrieve(
        knowledgeBaseId=kb_id,
        retrievalQuery={"text": query},
        retrievalConfiguration={
            "vectorSearchConfiguration": {
                "numberOfResults": int(config.get("number_of_results", 5)),
                "overrideSearchType": config.get("search_type", "HYBRID"),
            }
        },
    )

    documents = [
        {
            "content": result.get("content", {}).get("text", ""),
            "location": result.get("location", {}),
            "score": result.get("score", 0),
        }
        for result in response.get("retrievalResults", [])
    ]

    return {"documents": documents}


# ── Lambda entry-point ────────────────────────────────────────────────────────

def handler(event: dict, context: Any) -> dict:
    """Lambda handler.

    Accepts requests from a Lambda function URL or API Gateway (both raw
    body and pre-parsed dict formats are supported).
    """
    logger.info(
        "Request received: %s",
        json.dumps({k: v for k, v in event.items() if k != "body"}),
    )

    try:
        # Support Lambda function URL (body is a JSON string) and direct invocation
        body: dict = event
        if "body" in event:
            raw_body = event["body"]
            body = json.loads(raw_body) if isinstance(raw_body, str) else raw_body

        query: str = (body.get("query") or "").strip()
        if not query:
            return _response(400, {"error": "Missing or empty 'query' field."})

        mode: str = (body.get("mode") or "rag").lower()
        if mode not in {"rag", "retrieve"}:
            return _response(
                400,
                {"error": f"Invalid mode '{mode}'. Must be 'rag' or 'retrieve'."},
            )

        config = _load_config()

        result = _retrieve_and_generate(query, config) if mode == "rag" else _retrieve_only(query, config)
        result["query"] = query
        result["mode"] = mode

        return _response(200, result)

    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        msg = exc.response["Error"]["Message"]
        logger.error("AWS error %s: %s", code, msg)
        return _response(500, {"error": f"AWS error ({code}): {msg}"})

    except Exception:
        logger.exception("Unhandled exception")
        return _response(500, {"error": "Internal server error."})


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
