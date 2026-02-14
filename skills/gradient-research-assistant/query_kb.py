#!/usr/bin/env python3
"""
Knowledge Base query layer for the Gradient Research Assistant.

Queries the Gradient Knowledge Base via RAG for ticker research
accumulated over time.

Usage:
    python3 query_kb.py --query "What do you know about CAKE?"
    python3 query_kb.py --ticker CAKE
"""

import argparse
import json
import os
import sys
from typing import Optional

import boto3
import requests
from botocore.config import Config as BotoConfig

# Gradient inference endpoint (used for RAG-enhanced queries)
GRADIENT_INFERENCE_URL = "https://inference.do-ai.run/v1/chat/completions"
DO_API_BASE = "https://api.digitalocean.com"


def _get_spaces_client():
    """Create an S3-compatible client for DO Spaces."""
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("DO_SPACES_ENDPOINT", "https://nyc3.digitaloceanspaces.com"),
        aws_access_key_id=os.environ.get("DO_SPACES_ACCESS_KEY", ""),
        aws_secret_access_key=os.environ.get("DO_SPACES_SECRET_KEY", ""),
        config=BotoConfig(signature_version="s3v4"),
    )


def _fetch_research_from_spaces(query: str) -> dict:
    """Fetch research files from Spaces bucket matching the query ticker.

    Reads up to 5 most recent research files for the ticker mentioned in the query.
    Returns results in the same format as query_knowledge_base.
    """
    bucket = os.environ.get("DO_SPACES_BUCKET", "openclawresearch")

    # Extract ticker from query (look for $TICKER or just TICKER as uppercase word)
    import re
    ticker_match = re.search(r'\$([A-Z]{1,6})\b', query)
    if not ticker_match:
        # Try to find uppercase word that looks like a ticker
        ticker_match = re.search(r'\b([A-Z]{1,6})\b', query)

    if not ticker_match:
        return {"success": True, "results": [], "message": "No ticker found in query."}

    ticker = ticker_match.group(1)

    try:
        client = _get_spaces_client()

        # List research files for this ticker (prefix: research/)
        resp = client.list_objects_v2(Bucket=bucket, Prefix="research/", MaxKeys=100)
        all_objects = resp.get("Contents", [])

        # Filter for files matching this ticker
        matching = [
            obj for obj in all_objects
            if ticker in obj["Key"].upper()
        ]

        # Sort by last modified (newest first), take top 5
        matching.sort(key=lambda x: x.get("LastModified", ""), reverse=True)
        matching = matching[:5]

        if not matching:
            return {"success": True, "results": [], "message": f"No research files found for {ticker}."}

        # Fetch content of each matching file
        results = []
        for obj in matching:
            try:
                file_resp = client.get_object(Bucket=bucket, Key=obj["Key"])
                content = file_resp["Body"].read().decode("utf-8")
                # Truncate to ~2000 chars per file to keep context manageable
                if len(content) > 2000:
                    content = content[:2000] + "\n\n[...truncated]"
                results.append({
                    "content": content,
                    "metadata": {"source": obj["Key"]},
                    "score": 1.0,
                })
            except Exception:
                continue

        return {
            "success": True,
            "results": results,
            "message": f"Found {len(results)} research files for {ticker} in Spaces.",
        }
    except Exception as e:
        return {"success": False, "results": [], "message": f"Spaces query failed: {str(e)}"}


def query_knowledge_base(
    query: str,
    kb_uuid: Optional[str] = None,
    api_token: Optional[str] = None,
) -> dict:
    """Query the Knowledge Base, falling back to Spaces if KB API is unavailable.

    Args:
        query: The search query
        kb_uuid: Knowledge Base UUID
        api_token: DO personal access token

    Returns:
        dict with 'success', 'results', and 'message'
    """
    kb_uuid = kb_uuid or os.environ.get("GRADIENT_KB_UUID", "")
    api_token = api_token or os.environ.get("DO_API_TOKEN", "")

    if not kb_uuid or not api_token:
        # Skip KB API, go directly to Spaces
        return _fetch_research_from_spaces(query)

    try:
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

        url = f"{DO_API_BASE}/v2/gen-ai/knowledge_bases/{kb_uuid}/query"
        payload = {"query": query, "top_k": 10}

        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()

        data = resp.json()
        results = data.get("results", [])

        return {
            "success": True,
            "results": results,
            "message": f"Found {len(results)} relevant documents.",
        }
    except requests.RequestException:
        # KB API unavailable (404 from Droplets) — fall back to Spaces
        return _fetch_research_from_spaces(query)


def build_rag_prompt(query: str, kb_results: list[dict]) -> str:
    """Build a RAG-enhanced prompt combining the user's question with KB context.

    Args:
        query: The user's original question
        kb_results: Results from the Knowledge Base query

    Returns:
        The RAG-enhanced prompt
    """
    if not kb_results:
        context = "No prior research data available yet. The knowledge base is still building up."
    else:
        context_parts = []
        for i, result in enumerate(kb_results, 1):
            content = result.get("content", result.get("text", ""))
            source = result.get("metadata", {}).get("source", "unknown")
            score = result.get("score", 0)
            context_parts.append(f"### Source {i} (relevance: {score:.2f})\n{content}")
        context = "\n\n".join(context_parts)

    return f"""You are a financial research assistant with access to a growing knowledge base of research data.
Answer the user's question using the research context below. Be specific, cite dates and sources when available,
and note when information might be outdated.

## Research Context (from Knowledge Base):
{context}

## User's Question:
{query}

## Instructions:
- Answer based on the research context above
- If the KB doesn't have enough data, say so honestly
- Mention when findings were gathered (dates from the documents)
- If asked about a ticker not in the KB, explain that it needs to be added to the watchlist
- Be concise but thorough"""


def query_with_rag(
    query: str,
    model: str = "openai-gpt-oss-120b",
    kb_uuid: Optional[str] = None,
    api_key: Optional[str] = None,
    api_token: Optional[str] = None,
) -> dict:
    """Run a RAG-enhanced query: KB search → LLM synthesis.

    Args:
        query: The user's question
        model: LLM model for synthesis
        kb_uuid: Knowledge Base UUID
        api_key: Gradient API key (for inference)
        api_token: DO API token (for KB query)

    Returns:
        dict with 'success', 'answer', 'sources_count', 'message'
    """
    api_key = api_key or os.environ.get("GRADIENT_API_KEY", "")

    if not api_key:
        return {
            "success": False,
            "answer": "",
            "sources_count": 0,
            "message": "No GRADIENT_API_KEY configured.",
        }

    # Step 1: Query the Knowledge Base
    kb_result = query_knowledge_base(query, kb_uuid=kb_uuid, api_token=api_token)
    kb_results = kb_result.get("results", [])

    # Step 2: Build RAG prompt
    prompt = build_rag_prompt(query, kb_results)

    # Step 3: Call LLM for synthesis
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a helpful financial research assistant."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
            "max_tokens": 1500,
        }

        resp = requests.post(GRADIENT_INFERENCE_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()

        data = resp.json()
        answer = data["choices"][0]["message"]["content"]

        return {
            "success": True,
            "answer": answer,
            "sources_count": len(kb_results),
            "kb_success": kb_result["success"],
            "message": f"Answered using {len(kb_results)} sources from the Knowledge Base.",
        }
    except (requests.RequestException, KeyError, IndexError) as e:
        return {
            "success": False,
            "answer": "",
            "sources_count": len(kb_results),
            "message": f"LLM synthesis failed: {str(e)}",
        }


# ─── CLI Interface ────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Query the research knowledge base")
    parser.add_argument("--query", help="Freeform query")
    parser.add_argument("--ticker", help="Ticker to ask about")

    args = parser.parse_args()

    if args.ticker:
        query = f"What do you know about ${args.ticker.upper()}? Summarize all research findings."
    elif args.query:
        query = args.query
    else:
        print("Error: --query or --ticker required.", file=sys.stderr)
        sys.exit(1)

    result = query_with_rag(query)

    if result["success"]:
        print(result["answer"])
        print(f"\n📚 Used {result['sources_count']} sources from the Knowledge Base.", file=sys.stderr)
    else:
        print(f"Error: {result['message']}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
