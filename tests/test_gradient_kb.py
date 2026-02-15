"""
Tests for gradient-knowledge-base skill scripts:
- gradient_kb_query.py — KB queries + RAG pipeline
- gradient_kb_manage.py — KB CRUD + data sources
- gradient_spaces.py — DO Spaces operations

Uses responses for HTTP mocking and moto for S3/Spaces mocking.
"""

import json
from pathlib import Path

import boto3
import pytest
import responses
from moto import mock_aws

import sys

SKILL_DIR = Path(__file__).parent.parent / "skills" / "gradient-knowledge-base" / "scripts"
sys.path.insert(0, str(SKILL_DIR))

from gradient_kb_query import (
    query_kb,
    build_rag_prompt,
    query_with_rag,
    KB_RETRIEVE_BASE_URL,
    INFERENCE_URL,
)
from gradient_kb_manage import (
    list_knowledge_bases,
    create_knowledge_base,
    get_knowledge_base,
    delete_knowledge_base,
    list_data_sources,
    add_spaces_source,
    trigger_reindex,
    DO_API_BASE,
    KB_API_PATH,
)
from gradient_spaces import (
    build_key,
    upload_file,
    list_files,
    delete_file,
)


# ═══════════════════════════════════════════════════════════════════
# KB Query Tests
# ═══════════════════════════════════════════════════════════════════


class TestQueryKB:
    def test_no_kb_uuid_returns_error(self, monkeypatch):
        monkeypatch.delenv("GRADIENT_KB_UUID", raising=False)
        result = query_kb("test query", kb_uuid="", api_token="fake")
        assert result["success"] is False
        assert "KB_UUID" in result["message"]

    def test_no_api_token_returns_error(self, monkeypatch):
        monkeypatch.delenv("DO_API_TOKEN", raising=False)
        result = query_kb("test query", kb_uuid="kb-123", api_token="")
        assert result["success"] is False
        assert "API_TOKEN" in result["message"]

    @responses.activate
    def test_successful_query(self):
        kb_uuid = "test-kb-uuid"
        responses.add(
            responses.POST,
            f"{KB_RETRIEVE_BASE_URL}/{kb_uuid}/retrieve",
            json={"results": [{"content": "CAKE earnings data", "score": 0.92}]},
            status=200,
        )

        result = query_kb("CAKE earnings", kb_uuid=kb_uuid, api_token="fake-token")
        assert result["success"] is True
        assert len(result["results"]) == 1
        assert result["query"] == "CAKE earnings"

    @responses.activate
    def test_query_with_alpha(self):
        """Verify the alpha parameter is sent in the request."""
        kb_uuid = "test-kb-uuid"
        responses.add(
            responses.POST,
            f"{KB_RETRIEVE_BASE_URL}/{kb_uuid}/retrieve",
            json={"results": []},
            status=200,
        )

        query_kb("$CAKE", kb_uuid=kb_uuid, api_token="fake-token", alpha=0.5)

        req = json.loads(responses.calls[0].request.body)
        assert req["alpha"] == 0.5

    @responses.activate
    def test_query_without_alpha(self):
        """When alpha is None, it should not appear in the request."""
        kb_uuid = "test-kb-uuid"
        responses.add(
            responses.POST,
            f"{KB_RETRIEVE_BASE_URL}/{kb_uuid}/retrieve",
            json={"results": []},
            status=200,
        )

        query_kb("test", kb_uuid=kb_uuid, api_token="fake-token", alpha=None)

        req = json.loads(responses.calls[0].request.body)
        assert "alpha" not in req

    @responses.activate
    def test_custom_num_results(self):
        kb_uuid = "test-kb-uuid"
        responses.add(
            responses.POST,
            f"{KB_RETRIEVE_BASE_URL}/{kb_uuid}/retrieve",
            json={"results": []},
            status=200,
        )

        query_kb("test", kb_uuid=kb_uuid, api_token="fake-token", num_results=25)

        req = json.loads(responses.calls[0].request.body)
        assert req["num_results"] == 25

    @responses.activate
    def test_handles_api_error(self):
        kb_uuid = "test-kb-uuid"
        responses.add(
            responses.POST,
            f"{KB_RETRIEVE_BASE_URL}/{kb_uuid}/retrieve",
            body="Internal Server Error",
            status=500,
        )

        result = query_kb("test", kb_uuid=kb_uuid, api_token="fake-token")
        assert result["success"] is False


class TestBuildRagPrompt:
    def test_includes_user_query(self):
        prompt = build_rag_prompt("What about CAKE?", [])
        assert "What about CAKE?" in prompt

    def test_empty_results_mentions_no_data(self):
        prompt = build_rag_prompt("test", [])
        assert "no relevant" in prompt.lower() or "building up" in prompt.lower()

    def test_includes_kb_results(self):
        results = [
            {"content": "CAKE beat Q4 earnings", "metadata": {"source": "sec"}, "score": 0.95},
            {"content": "Reddit bullish on CAKE", "metadata": {"source": "reddit"}, "score": 0.82},
        ]
        prompt = build_rag_prompt("Tell me about CAKE", results)
        assert "beat Q4" in prompt
        assert "bullish" in prompt
        assert "0.95" in prompt


class TestQueryWithRag:
    def test_no_api_key_returns_error(self, monkeypatch):
        monkeypatch.delenv("GRADIENT_API_KEY", raising=False)
        result = query_with_rag("test", api_key="")
        assert result["success"] is False

    @responses.activate
    def test_full_rag_pipeline(self):
        kb_uuid = "test-kb-uuid"

        # Mock KB query
        responses.add(
            responses.POST,
            f"{KB_RETRIEVE_BASE_URL}/{kb_uuid}/retrieve",
            json={"results": [{"content": "CAKE data", "score": 0.9}]},
            status=200,
        )

        # Mock LLM synthesis
        responses.add(
            responses.POST,
            INFERENCE_URL,
            json={"choices": [{"message": {"content": "CAKE had strong results."}}]},
            status=200,
        )

        result = query_with_rag(
            "What about CAKE?",
            kb_uuid=kb_uuid,
            api_key="fake-key",
            api_token="fake-token",
        )

        assert result["success"] is True
        assert "CAKE" in result["answer"]
        assert result["sources_count"] == 1

    @responses.activate
    def test_rag_with_alpha(self):
        kb_uuid = "test-kb-uuid"

        responses.add(
            responses.POST,
            f"{KB_RETRIEVE_BASE_URL}/{kb_uuid}/retrieve",
            json={"results": []},
            status=200,
        )
        responses.add(
            responses.POST,
            INFERENCE_URL,
            json={"choices": [{"message": {"content": "No data yet."}}]},
            status=200,
        )

        query_with_rag("test", kb_uuid=kb_uuid, api_key="key", api_token="token", alpha=0.3)

        # Verify alpha was passed to the KB query
        kb_req = json.loads(responses.calls[0].request.body)
        assert kb_req["alpha"] == 0.3


# ═══════════════════════════════════════════════════════════════════
# KB Management Tests
# ═══════════════════════════════════════════════════════════════════


class TestListKnowledgeBases:
    def test_no_token_returns_error(self, monkeypatch):
        monkeypatch.delenv("DO_API_TOKEN", raising=False)
        result = list_knowledge_bases(api_token="")
        assert result["success"] is False

    @responses.activate
    def test_successful_list(self):
        responses.add(
            responses.GET,
            f"{DO_API_BASE}{KB_API_PATH}",
            json={"knowledge_bases": [
                {"uuid": "kb-1", "name": "Research KB"},
                {"uuid": "kb-2", "name": "Docs KB"},
            ]},
            status=200,
        )

        result = list_knowledge_bases(api_token="fake-token")
        assert result["success"] is True
        assert len(result["knowledge_bases"]) == 2


class TestCreateKnowledgeBase:
    @responses.activate
    def test_successful_create(self):
        responses.add(
            responses.POST,
            f"{DO_API_BASE}{KB_API_PATH}",
            json={"knowledge_base": {"uuid": "new-kb", "name": "Test KB"}},
            status=201,
        )

        result = create_knowledge_base(name="Test KB", api_token="fake-token")
        assert result["success"] is True
        assert result["knowledge_base"]["uuid"] == "new-kb"

    @responses.activate
    def test_sends_correct_params(self):
        responses.add(
            responses.POST,
            f"{DO_API_BASE}{KB_API_PATH}",
            json={"knowledge_base": {"uuid": "new-kb"}},
            status=201,
        )

        create_knowledge_base(
            name="My KB",
            region="sfo3",
            project_id="proj-123",
            api_token="fake-token",
        )

        req = json.loads(responses.calls[0].request.body)
        assert req["name"] == "My KB"
        assert req["region"] == "sfo3"
        assert req["project_id"] == "proj-123"


class TestGetKnowledgeBase:
    @responses.activate
    def test_successful_get(self):
        responses.add(
            responses.GET,
            f"{DO_API_BASE}{KB_API_PATH}/kb-123",
            json={"knowledge_base": {"uuid": "kb-123", "name": "My KB", "status": "active"}},
            status=200,
        )

        result = get_knowledge_base("kb-123", api_token="fake-token")
        assert result["success"] is True
        assert result["knowledge_base"]["status"] == "active"


class TestDeleteKnowledgeBase:
    @responses.activate
    def test_successful_delete(self):
        responses.add(
            responses.DELETE,
            f"{DO_API_BASE}{KB_API_PATH}/kb-123",
            status=204,
        )

        result = delete_knowledge_base("kb-123", api_token="fake-token")
        assert result["success"] is True

    @responses.activate
    def test_delete_nonexistent(self):
        responses.add(
            responses.DELETE,
            f"{DO_API_BASE}{KB_API_PATH}/nonexistent",
            body="Not Found",
            status=404,
        )

        result = delete_knowledge_base("nonexistent", api_token="fake-token")
        assert result["success"] is False


class TestListDataSources:
    @responses.activate
    def test_successful_list(self):
        responses.add(
            responses.GET,
            f"{DO_API_BASE}{KB_API_PATH}/kb-123/data_sources",
            json={"knowledge_base_data_sources": [
                {"uuid": "ds-1", "type": "spaces"},
            ]},
            status=200,
        )

        result = list_data_sources("kb-123", api_token="fake-token")
        assert result["success"] is True
        assert len(result["data_sources"]) == 1


class TestAddSpacesSource:
    @responses.activate
    def test_successful_add(self):
        responses.add(
            responses.POST,
            f"{DO_API_BASE}{KB_API_PATH}/kb-123/data_sources",
            json={"knowledge_base_data_source": {"uuid": "ds-new", "type": "spaces"}},
            status=201,
        )

        result = add_spaces_source("kb-123", bucket="my-data", api_token="fake-token")
        assert result["success"] is True

    @responses.activate
    def test_sends_prefix(self):
        responses.add(
            responses.POST,
            f"{DO_API_BASE}{KB_API_PATH}/kb-123/data_sources",
            json={"knowledge_base_data_source": {}},
            status=201,
        )

        add_spaces_source("kb-123", bucket="data", prefix="research/", api_token="fake-token")

        req = json.loads(responses.calls[0].request.body)
        assert req["spaces"]["prefix"] == "research/"


class TestTriggerReindex:
    @responses.activate
    def test_with_source_uuid(self):
        responses.add(
            responses.POST,
            f"{DO_API_BASE}{KB_API_PATH}/kb-123/data_sources/ds-456/indexing_jobs",
            json={"job_id": "job-789"},
            status=201,
        )

        result = trigger_reindex("kb-123", source_uuid="ds-456", api_token="fake-token")
        assert result["success"] is True

    @responses.activate
    def test_auto_detects_source(self):
        # Mock: list sources
        responses.add(
            responses.GET,
            f"{DO_API_BASE}{KB_API_PATH}/kb-123/data_sources",
            json={"knowledge_base_data_sources": [{"uuid": "ds-auto"}]},
            status=200,
        )
        # Mock: trigger indexing
        responses.add(
            responses.POST,
            f"{DO_API_BASE}{KB_API_PATH}/kb-123/data_sources/ds-auto/indexing_jobs",
            json={"job_id": "job-auto"},
            status=201,
        )

        result = trigger_reindex("kb-123", api_token="fake-token")
        assert result["success"] is True
        assert "ds-auto" in result["message"]

    @responses.activate
    def test_no_sources_returns_error(self):
        responses.add(
            responses.GET,
            f"{DO_API_BASE}{KB_API_PATH}/kb-123/data_sources",
            json={"knowledge_base_data_sources": []},
            status=200,
        )

        result = trigger_reindex("kb-123", api_token="fake-token")
        assert result["success"] is False
        assert "no data sources" in result["message"].lower()


# ═══════════════════════════════════════════════════════════════════
# Spaces Operations Tests
# ═══════════════════════════════════════════════════════════════════


class TestBuildKey:
    def test_with_prefix(self):
        key = build_key("research/2026-02-15", "CAKE.md")
        assert key == "research/2026-02-15/CAKE.md"

    def test_without_prefix(self):
        key = build_key("", "report.md")
        assert key == "report.md"

    def test_strips_trailing_slash(self):
        key = build_key("data/", "file.md")
        assert key == "data/file.md"


class TestUploadFile:
    @mock_aws
    def test_successful_upload(self):
        conn = boto3.client("s3", region_name="us-east-1")
        conn.create_bucket(Bucket="test-bucket")

        result = upload_file(
            content="# Hello\nTest content",
            key="docs/test.md",
            bucket="test-bucket",
            client=conn,
        )

        assert result["success"] is True
        assert result["key"] == "docs/test.md"

        # Verify file was uploaded
        obj = conn.get_object(Bucket="test-bucket", Key="docs/test.md")
        body = obj["Body"].read().decode("utf-8")
        assert body == "# Hello\nTest content"

    @mock_aws
    def test_upload_to_nonexistent_bucket_fails(self):
        conn = boto3.client("s3", region_name="us-east-1")
        result = upload_file(
            content="test",
            key="test.md",
            bucket="nonexistent",
            client=conn,
        )
        assert result["success"] is False

    def test_no_bucket_returns_error(self, monkeypatch):
        monkeypatch.delenv("DO_SPACES_BUCKET", raising=False)
        result = upload_file(content="test", key="test.md", bucket="")
        assert result["success"] is False
        assert "bucket" in result["message"].lower()


class TestListFiles:
    @mock_aws
    def test_successful_list(self):
        conn = boto3.client("s3", region_name="us-east-1")
        conn.create_bucket(Bucket="test-bucket")
        conn.put_object(Bucket="test-bucket", Key="a.md", Body=b"aaa")
        conn.put_object(Bucket="test-bucket", Key="b.md", Body=b"bbb")

        result = list_files(bucket="test-bucket", client=conn)
        assert result["success"] is True
        assert len(result["files"]) == 2

    @mock_aws
    def test_list_with_prefix(self):
        conn = boto3.client("s3", region_name="us-east-1")
        conn.create_bucket(Bucket="test-bucket")
        conn.put_object(Bucket="test-bucket", Key="docs/a.md", Body=b"a")
        conn.put_object(Bucket="test-bucket", Key="other/b.md", Body=b"b")

        result = list_files(bucket="test-bucket", prefix="docs/", client=conn)
        assert result["success"] is True
        assert len(result["files"]) == 1
        assert result["files"][0]["key"] == "docs/a.md"

    @mock_aws
    def test_empty_bucket(self):
        conn = boto3.client("s3", region_name="us-east-1")
        conn.create_bucket(Bucket="test-bucket")

        result = list_files(bucket="test-bucket", client=conn)
        assert result["success"] is True
        assert len(result["files"]) == 0


class TestDeleteFile:
    @mock_aws
    def test_successful_delete(self):
        conn = boto3.client("s3", region_name="us-east-1")
        conn.create_bucket(Bucket="test-bucket")
        conn.put_object(Bucket="test-bucket", Key="deleteme.md", Body=b"bye")

        result = delete_file("deleteme.md", bucket="test-bucket", client=conn)
        assert result["success"] is True

        # Verify deleted
        remaining = conn.list_objects_v2(Bucket="test-bucket")
        assert remaining.get("KeyCount", 0) == 0
