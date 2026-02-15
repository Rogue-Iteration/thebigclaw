"""
Tests for store.py — Phase 4 (TDD)

Tests cover:
- S3 key construction
- Upload to DO Spaces (mocked via moto)
- KB re-indexing trigger (mocked HTTP)
- Combined store_research flow
"""

import json
import os
from pathlib import Path

import boto3
import pytest
import responses
from moto import mock_aws

import sys

SKILL_DIR = Path(__file__).parent.parent / "skills" / "gradient-research-assistant" / "scripts"
KB_DIR = Path(__file__).parent.parent / "skills" / "gradient-knowledge-base" / "scripts"
sys.path.insert(0, str(SKILL_DIR))
sys.path.insert(0, str(KB_DIR))

from store import (
    build_spaces_key,
    upload_to_spaces,
    trigger_kb_reindex,
    store_research,
    DO_API_BASE,
)


# ─── Key Construction ─────────────────────────────────────────────


class TestBuildSpacesKey:
    def test_default_format(self):
        key = build_spaces_key("CAKE", "combined", "2026-02-12T14:30:00+00:00")
        assert key == "research/2026-02-12/CAKE_combined.md"

    def test_custom_source(self):
        key = build_spaces_key("HOG", "news", "2026-02-12T14:30:00+00:00")
        assert key == "research/2026-02-12/HOG_news.md"

    def test_no_timestamp_uses_today(self):
        key = build_spaces_key("CAKE")
        assert key.startswith("research/")
        assert key.endswith("/CAKE_combined.md")
        # Date part should be YYYY-MM-DD format
        date_part = key.split("/")[1]
        assert len(date_part) == 10


# ─── Upload to Spaces (moto) ─────────────────────────────────────


class TestUploadToSpaces:
    @mock_aws
    def test_successful_upload(self):
        # Create bucket
        conn = boto3.client("s3", region_name="us-east-1")
        conn.create_bucket(Bucket="test-bucket")

        result = upload_to_spaces(
            markdown_content="# Test\nHello",
            ticker="CAKE",
            source="combined",
            bucket="test-bucket",
            timestamp="2026-02-12T14:00:00+00:00",
            client=conn,
        )

        assert result["success"] is True
        assert result["key"] == "research/2026-02-12/CAKE_combined.md"
        assert result["bucket"] == "test-bucket"

        # Verify file was uploaded
        obj = conn.get_object(Bucket="test-bucket", Key="research/2026-02-12/CAKE_combined.md")
        body = obj["Body"].read().decode("utf-8")
        assert body == "# Test\nHello"

    @mock_aws
    def test_upload_nonexistent_bucket_fails(self):
        conn = boto3.client("s3", region_name="us-east-1")
        result = upload_to_spaces(
            markdown_content="# Test",
            ticker="CAKE",
            bucket="nonexistent-bucket",
            client=conn,
        )
        assert result["success"] is False
        assert "failed" in result["message"].lower()


# ─── KB Re-indexing (mocked API) ──────────────────────────────────


class TestTriggerKBReindex:
    def test_no_kb_uuid_returns_error(self, monkeypatch):
        monkeypatch.delenv("GRADIENT_KB_UUID", raising=False)
        result = trigger_kb_reindex(kb_uuid="", api_token="fake-token")
        assert result["success"] is False
        assert "KB_UUID" in result["message"]

    def test_no_api_token_returns_error(self, monkeypatch):
        monkeypatch.delenv("DO_API_TOKEN", raising=False)
        result = trigger_kb_reindex(kb_uuid="test-uuid", api_token="")
        assert result["success"] is False
        assert "API_TOKEN" in result["message"]

    @responses.activate
    def test_successful_reindex(self):
        kb_uuid = "test-kb-uuid"

        # Mock: list data sources
        responses.add(
            responses.GET,
            f"{DO_API_BASE}/v2/gen-ai/knowledge_bases/{kb_uuid}/data_sources",
            json={"knowledge_base_data_sources": [{"uuid": "ds-123"}]},
            status=200,
        )
        # Mock: trigger indexing
        responses.add(
            responses.POST,
            f"{DO_API_BASE}/v2/gen-ai/knowledge_bases/{kb_uuid}/data_sources/ds-123/indexing_jobs",
            json={"job_id": "job-456"},
            status=201,
        )

        result = trigger_kb_reindex(kb_uuid=kb_uuid, api_token="fake-token")
        assert result["success"] is True
        assert "ds-123" in result["message"]

    @responses.activate
    def test_no_data_sources_returns_error(self):
        kb_uuid = "test-kb-uuid"
        responses.add(
            responses.GET,
            f"{DO_API_BASE}/v2/gen-ai/knowledge_bases/{kb_uuid}/data_sources",
            json={"knowledge_base_data_sources": []},
            status=200,
        )

        result = trigger_kb_reindex(kb_uuid=kb_uuid, api_token="fake-token")
        assert result["success"] is False
        assert "no data sources" in result["message"].lower()
