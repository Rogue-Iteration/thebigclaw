"""
Tests for gradient_models.py and gradient_chat.py — Gradient Inference skill.

Tests cover:
- Model listing + filtering (mocked API)
- Chat completions (mocked API)
- Responses API with prompt caching (mocked API)
- Error handling and missing credentials
"""

import json
from pathlib import Path

import pytest
import responses

import sys

SKILL_DIR = Path(__file__).parent.parent / "skills" / "gradient-inference" / "scripts"
sys.path.insert(0, str(SKILL_DIR))

from gradient_models import (
    list_models,
    filter_models,
    format_model_table,
    INFERENCE_BASE_URL,
)
from gradient_chat import (
    chat_completion,
    responses_api,
    pick_api,
    CHAT_COMPLETIONS_URL,
    RESPONSES_URL,
)


# ─── Model Listing ───────────────────────────────────────────────


class TestListModels:
    def test_no_api_key_returns_error(self, monkeypatch):
        monkeypatch.delenv("GRADIENT_API_KEY", raising=False)
        result = list_models(api_key="")
        assert result["success"] is False
        assert "GRADIENT_API_KEY" in result["message"]

    @responses.activate
    def test_successful_list(self):
        responses.add(
            responses.GET,
            f"{INFERENCE_BASE_URL}/models",
            json={
                "data": [
                    {"id": "openai-gpt-oss-120b", "owned_by": "openai"},
                    {"id": "llama3.3-70b-instruct", "owned_by": "meta"},
                ]
            },
            status=200,
        )

        result = list_models(api_key="fake-key")
        assert result["success"] is True
        assert len(result["models"]) == 2
        assert result["models"][0]["id"] == "openai-gpt-oss-120b"

    @responses.activate
    def test_handles_api_error(self):
        responses.add(
            responses.GET,
            f"{INFERENCE_BASE_URL}/models",
            body="Internal Server Error",
            status=500,
        )

        result = list_models(api_key="fake-key")
        assert result["success"] is False
        assert "failed" in result["message"].lower()

    @responses.activate
    def test_handles_alternate_response_format(self):
        """Some API versions return 'models' instead of 'data'."""
        responses.add(
            responses.GET,
            f"{INFERENCE_BASE_URL}/models",
            json={
                "models": [
                    {"id": "qwen3-32b", "owned_by": "qwen"},
                ]
            },
            status=200,
        )

        result = list_models(api_key="fake-key")
        assert result["success"] is True
        assert len(result["models"]) == 1


class TestFilterModels:
    def test_filter_by_id(self):
        models = [
            {"id": "openai-gpt-oss-120b", "owned_by": "openai"},
            {"id": "llama3.3-70b-instruct", "owned_by": "meta"},
            {"id": "qwen3-32b", "owned_by": "qwen"},
        ]
        result = filter_models(models, "llama")
        assert len(result) == 1
        assert result[0]["id"] == "llama3.3-70b-instruct"

    def test_filter_case_insensitive(self):
        models = [{"id": "OpenAI-GPT-oss-120b", "owned_by": "openai"}]
        result = filter_models(models, "openai")
        assert len(result) == 1

    def test_filter_no_match(self):
        models = [{"id": "llama3.3-70b-instruct", "owned_by": "meta"}]
        result = filter_models(models, "nonexistent")
        assert len(result) == 0

    def test_filter_by_name_field(self):
        models = [{"id": "model-1", "name": "Super Lobster Model"}]
        result = filter_models(models, "lobster")
        assert len(result) == 1


class TestFormatModelTable:
    def test_empty_list(self):
        output = format_model_table([])
        assert "empty" in output.lower() or "No models" in output

    def test_formats_models(self):
        models = [
            {"id": "openai-gpt-oss-120b", "owned_by": "openai"},
            {"id": "llama3.3-70b-instruct", "owned_by": "meta"},
        ]
        output = format_model_table(models)
        assert "openai-gpt-oss-120b" in output
        assert "llama3.3-70b-instruct" in output
        assert "2 models" in output


# ─── Chat Completions ────────────────────────────────────────────


class TestChatCompletion:
    def test_no_api_key_returns_error(self, monkeypatch):
        monkeypatch.delenv("GRADIENT_API_KEY", raising=False)
        result = chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            api_key="",
        )
        assert result["success"] is False

    @responses.activate
    def test_successful_call(self):
        responses.add(
            responses.POST,
            CHAT_COMPLETIONS_URL,
            json={
                "choices": [{"message": {"content": "Hello! 🦞"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
            status=200,
        )

        result = chat_completion(
            messages=[{"role": "user", "content": "Hello!"}],
            api_key="fake-key",
        )
        assert result["success"] is True
        assert "Hello" in result["content"]
        assert result["api"] == "chat/completions"
        assert result["usage"]["prompt_tokens"] == 10

    @responses.activate
    def test_api_error(self):
        responses.add(
            responses.POST,
            CHAT_COMPLETIONS_URL,
            body="Rate limited",
            status=429,
        )

        result = chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            api_key="fake-key",
        )
        assert result["success"] is False

    @responses.activate
    def test_sends_correct_params(self):
        responses.add(
            responses.POST,
            CHAT_COMPLETIONS_URL,
            json={"choices": [{"message": {"content": "OK"}}]},
            status=200,
        )

        chat_completion(
            messages=[
                {"role": "system", "content": "You are a pirate."},
                {"role": "user", "content": "Ahoy?"},
            ],
            model="qwen3-32b",
            api_key="fake-key",
            temperature=0.3,
            max_tokens=500,
        )

        # Verify the request payload
        req = json.loads(responses.calls[0].request.body)
        assert req["model"] == "qwen3-32b"
        assert req["temperature"] == 0.3
        assert req["max_tokens"] == 500
        assert len(req["messages"]) == 2
        assert req["messages"][0]["role"] == "system"


# ─── Responses API ────────────────────────────────────────────────


class TestResponsesApi:
    def test_no_api_key_returns_error(self, monkeypatch):
        monkeypatch.delenv("GRADIENT_API_KEY", raising=False)
        result = responses_api(input_text="Hello", api_key="")
        assert result["success"] is False

    @responses.activate
    def test_successful_call(self):
        responses.add(
            responses.POST,
            RESPONSES_URL,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "text", "text": "Ahoy, matey! 🦞"}],
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 8},
            },
            status=200,
        )

        result = responses_api(input_text="Say ahoy", api_key="fake-key")
        assert result["success"] is True
        assert "Ahoy" in result["content"]
        assert result["api"] == "responses"

    @responses.activate
    def test_with_cache_enabled(self):
        responses.add(
            responses.POST,
            RESPONSES_URL,
            json={
                "output": [{"type": "message", "content": [{"type": "text", "text": "Cached!"}]}],
            },
            status=200,
        )

        result = responses_api(input_text="Cache me", api_key="fake-key", store=True)
        assert result["success"] is True
        assert result["cached"] is True

        # Verify store was sent in the payload
        req = json.loads(responses.calls[0].request.body)
        assert req["store"] is True

    @responses.activate
    def test_without_cache(self):
        responses.add(
            responses.POST,
            RESPONSES_URL,
            json={"output": [{"type": "message", "content": [{"type": "text", "text": "OK"}]}]},
            status=200,
        )

        responses_api(input_text="No cache", api_key="fake-key", store=False)

        req = json.loads(responses.calls[0].request.body)
        assert "store" not in req

    @responses.activate
    def test_api_error(self):
        responses.add(
            responses.POST,
            RESPONSES_URL,
            body="Service unavailable",
            status=503,
        )

        result = responses_api(input_text="Hello", api_key="fake-key")
        assert result["success"] is False

    @responses.activate
    def test_fallback_to_choices_format(self):
        """Some models return chat-completions format even via responses API."""
        responses.add(
            responses.POST,
            RESPONSES_URL,
            json={"choices": [{"message": {"content": "Fallback format"}}]},
            status=200,
        )

        result = responses_api(input_text="Hello", api_key="fake-key")
        assert result["success"] is True
        assert "Fallback" in result["content"]


# ─── Pick API ─────────────────────────────────────────────────────


class TestPickApi:
    def test_returns_responses_url(self):
        assert pick_api(True) == RESPONSES_URL

    def test_returns_chat_completions_url(self):
        assert pick_api(False) == CHAT_COMPLETIONS_URL
