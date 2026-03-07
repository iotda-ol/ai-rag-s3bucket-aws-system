#!/usr/bin/env python3
"""
Local query CLI for the AWS Bedrock RAG system.

Runs RAG queries directly against the Bedrock Knowledge Base without going
through the Lambda function URL.  Useful for testing and development.

Usage examples::

    # Full RAG answer (retrieve + generate)
    python3 query.py "What is the return policy?" \\
        --config-secret rag-system-dev/config \\
        --bedrock-secret rag-system-dev/bedrock

    # Retrieve-only mode (no LLM generation)
    python3 query.py "return policy" \\
        --config-secret rag-system-dev/config \\
        --bedrock-secret rag-system-dev/bedrock \\
        --mode retrieve

    # JSON output for scripting
    python3 query.py "What is the SLA?" \\
        --config-secret rag-system-prod/config \\
        --bedrock-secret rag-system-prod/bedrock \\
        --profile prod --output json
"""

import argparse
import json
import logging
import sys

import boto3

from utils import get_secret, get_bedrock_agent_runtime_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def query_rag(
    query: str,
    config_secret_name: str,
    bedrock_secret_name: str,
    profile: str | None = None,
    region: str = "us-east-1",
    mode: str = "rag",
    number_of_results: int | None = None,
) -> dict:
    """Query the Bedrock Knowledge Base in RAG or retrieve-only mode.

    Args:
        query:               The natural-language question.
        config_secret_name:  Secrets Manager name for RAG config.
        bedrock_secret_name: Secrets Manager name for Bedrock config.
        profile:             AWS CLI profile name.
        region:              AWS region.
        mode:                ``"rag"`` or ``"retrieve"``.
        number_of_results:   Override the number of chunks to retrieve.

    Returns:
        Result dict containing ``answer`` (rag mode) or ``documents``
        (retrieve mode), plus ``query`` and ``mode``.
    """
    if profile:
        boto3.setup_default_session(profile_name=profile, region_name=region)

    config = {
        **get_secret(config_secret_name, region),
        **get_secret(bedrock_secret_name, region),
    }

    if number_of_results is not None:
        config["number_of_results"] = number_of_results

    kb_id: str = config["knowledge_base_id"]
    model_id: str = config["foundation_model_id"]
    model_arn = f"arn:aws:bedrock:{region}::foundation-model/{model_id}"
    client = get_bedrock_agent_runtime_client(region)

    if mode == "retrieve":
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
                "content": r.get("content", {}).get("text", ""),
                "location": r.get("location", {}),
                "score": r.get("score", 0),
            }
            for r in response.get("retrievalResults", [])
        ]
        return {"query": query, "mode": "retrieve", "documents": documents}

    # rag mode
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
        "query": query,
        "mode": "rag",
        "answer": response["output"]["text"],
        "citations": citations,
        "session_id": response.get("sessionId"),
    }


def _print_text(result: dict) -> None:
    """Pretty-print a query result to stdout."""
    mode = result.get("mode", "rag")
    if mode == "rag":
        print("\n=== Answer ===")
        print(result.get("answer", "(no answer)"))
        citations = result.get("citations", [])
        if citations:
            print(f"\n=== Sources ({len(citations)} chunk(s)) ===")
            for i, c in enumerate(citations, 1):
                score = c.get("score", 0)
                loc = c.get("location", {})
                uri = loc.get("s3Location", {}).get("uri", "N/A")
                excerpt = (c.get("content") or "")[:200]
                print(f"\n[{i}] score={score:.4f}  source={uri}")
                if excerpt:
                    print(f"    {excerpt} …")
    else:
        docs = result.get("documents", [])
        print(f"\n=== Retrieved {len(docs)} chunk(s) ===")
        for i, d in enumerate(docs, 1):
            score = d.get("score", 0)
            loc = d.get("location", {})
            uri = loc.get("s3Location", {}).get("uri", "N/A")
            excerpt = (d.get("content") or "")[:200]
            print(f"\n[{i}] score={score:.4f}  source={uri}")
            if excerpt:
                print(f"    {excerpt} …")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query the Bedrock RAG knowledge base from the command line.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("query", help="Question to ask the knowledge base")
    parser.add_argument(
        "--config-secret",
        required=True,
        metavar="SECRET",
        help="RAG config secret name, e.g. rag-system-dev/config",
    )
    parser.add_argument(
        "--bedrock-secret",
        required=True,
        metavar="SECRET",
        help="Bedrock config secret name, e.g. rag-system-dev/bedrock",
    )
    parser.add_argument("--profile", default=None, help="AWS CLI profile name")
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    parser.add_argument(
        "--mode",
        choices=["rag", "retrieve"],
        default="rag",
        help="'rag' = retrieve + generate; 'retrieve' = chunks only",
    )
    parser.add_argument(
        "--num-results",
        type=int,
        default=None,
        metavar="N",
        help="Number of chunks to retrieve (overrides secret value)",
    )
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )

    args = parser.parse_args()

    try:
        result = query_rag(
            query=args.query,
            config_secret_name=args.config_secret,
            bedrock_secret_name=args.bedrock_secret,
            profile=args.profile,
            region=args.region,
            mode=args.mode,
            number_of_results=args.num_results,
        )
    except Exception:
        logger.exception("Query failed")
        sys.exit(1)

    if args.output == "json":
        print(json.dumps(result, indent=2))
    else:
        _print_text(result)


if __name__ == "__main__":
    main()
