"""
Tests for query_kb.py — Phase 6 (TDD)

Tests cover:
- RAG prompt construction (with and without KB results)
- KB query handling (mocked API)
- Full RAG pipeline (KB → LLM synthesis)
"""

import json
from pathlib import Path

import pytest
import responses

import sys

SKILL_DIR = Path(__file__).parent.parent / "skills" / "gradient-research-assistant"
sys.path.insert(0, str(SKILL_DIR))

from query_kb import (
    build_rag_prompt,
    query_knowledge_base,
    query_with_rag,
    GRADIENT_INFERENCE_URL,
    DO_API_BASE,
)


# ─── RAG Prompt Construction ─────────────────────────────────────


class TestBuildRagPrompt:
    def test_includes_user_query(self):
        prompt = build_rag_prompt("What do you know about CAKE?", [])
        assert "What do you know about CAKE?" in prompt

    def test_no_results_mentions_empty_kb(self):
        prompt = build_rag_prompt("Tell me about CAKE", [])
        assert "no prior research" in prompt.lower() or "still building" in prompt.lower()

    def test_includes_kb_results(self):
        results = [
            {"content": "CAKE beat earnings by 12%", "metadata": {"source": "news"}, "score": 0.92},
            {"content": "Reddit is bullish on CAKE", "metadata": {"source": "reddit"}, "score": 0.85},
        ]
        prompt = build_rag_prompt("What do you know about CAKE?", results)
        assert "beat earnings" in prompt
        assert "bullish" in prompt
        assert "0.92" in prompt


# ─── KB Query (Mocked API) ───────────────────────────────────────


class TestQueryKnowledgeBase:
    def test_no_kb_uuid_returns_error(self, monkeypatch):
        monkeypatch.delenv("GRADIENT_KB_UUID", raising=False)
        result = query_knowledge_base("test query", kb_uuid="", api_token="fake")
        assert result["success"] is False

    def test_no_api_token_returns_error(self, monkeypatch):
        monkeypatch.delenv("DO_API_TOKEN", raising=False)
        result = query_knowledge_base("test query", kb_uuid="kb-123", api_token="")
        assert result["success"] is False

    @responses.activate
    def test_successful_query(self):
        kb_uuid = "test-kb-uuid"
        responses.add(
            responses.POST,
            f"{DO_API_BASE}/v2/gen-ai/knowledge_bases/{kb_uuid}/query",
            json={"results": [{"content": "CAKE data", "score": 0.9}]},
            status=200,
        )

        result = query_knowledge_base("CAKE research", kb_uuid=kb_uuid, api_token="fake")
        assert result["success"] is True
        assert len(result["results"]) == 1

    @responses.activate
    def test_handles_api_error(self):
        kb_uuid = "test-kb-uuid"
        responses.add(
            responses.POST,
            f"{DO_API_BASE}/v2/gen-ai/knowledge_bases/{kb_uuid}/query",
            body="Error",
            status=500,
        )

        result = query_knowledge_base("CAKE", kb_uuid=kb_uuid, api_token="fake")
        assert result["success"] is False


# ─── Full RAG Pipeline ───────────────────────────────────────────


class TestQueryWithRag:
    def test_no_api_key_returns_error(self, monkeypatch):
        monkeypatch.delenv("GRADIENT_API_KEY", raising=False)
        result = query_with_rag("test query", api_key="")
        assert result["success"] is False

    @responses.activate
    def test_full_rag_pipeline(self):
        kb_uuid = "test-kb-uuid"

        # Mock KB query
        responses.add(
            responses.POST,
            f"{DO_API_BASE}/v2/gen-ai/knowledge_bases/{kb_uuid}/query",
            json={"results": [{"content": "CAKE beat earnings", "score": 0.9}]},
            status=200,
        )

        # Mock LLM synthesis
        responses.add(
            responses.POST,
            GRADIENT_INFERENCE_URL,
            json={"choices": [{"message": {"content": "CAKE had strong earnings with 12% beat."}}]},
            status=200,
        )

        result = query_with_rag(
            "What do you know about CAKE?",
            kb_uuid=kb_uuid,
            api_key="fake-key",
            api_token="fake-token",
        )

        assert result["success"] is True
        assert "CAKE" in result["answer"]
        assert result["sources_count"] == 1

    @responses.activate
    def test_rag_works_without_kb_data(self):
        kb_uuid = "test-kb-uuid"

        # KB returns empty (maybe not indexed yet)
        responses.add(
            responses.POST,
            f"{DO_API_BASE}/v2/gen-ai/knowledge_bases/{kb_uuid}/query",
            json={"results": []},
            status=200,
        )

        # LLM still answers
        responses.add(
            responses.POST,
            GRADIENT_INFERENCE_URL,
            json={"choices": [{"message": {"content": "I don't have research data on CAKE yet."}}]},
            status=200,
        )

        result = query_with_rag(
            "What about CAKE?",
            kb_uuid=kb_uuid,
            api_key="fake-key",
            api_token="fake-token",
        )

        assert result["success"] is True
        assert result["sources_count"] == 0
