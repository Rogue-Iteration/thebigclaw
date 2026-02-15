"""
Tests for gradient_image.py — Gradient Inference skill (image generation).

Tests cover:
- Image generation (mocked API)
- Image saving from URL and base64
- Error handling and missing credentials
"""

import base64
import json
import tempfile
from pathlib import Path

import pytest
import responses

import sys

SKILL_DIR = Path(__file__).parent.parent / "skills" / "gradient-inference" / "scripts"
sys.path.insert(0, str(SKILL_DIR))

from gradient_image import (
    generate_image,
    save_image,
    IMAGE_GENERATION_URL,
)


# ─── Image Generation ────────────────────────────────────────────


class TestGenerateImage:
    def test_no_api_key_returns_error(self, monkeypatch):
        monkeypatch.delenv("GRADIENT_API_KEY", raising=False)
        result = generate_image(prompt="A lobster", api_key="")
        assert result["success"] is False
        assert "GRADIENT_API_KEY" in result["message"]

    @responses.activate
    def test_successful_generation(self):
        responses.add(
            responses.POST,
            IMAGE_GENERATION_URL,
            json={
                "data": [
                    {"url": "https://example.com/image.png"},
                ]
            },
            status=200,
        )

        result = generate_image(prompt="A lobster trading stocks", api_key="fake-key")
        assert result["success"] is True
        assert len(result["images"]) == 1
        assert result["images"][0]["url"] == "https://example.com/image.png"

    @responses.activate
    def test_sends_correct_params(self):
        responses.add(
            responses.POST,
            IMAGE_GENERATION_URL,
            json={"data": [{"url": "https://example.com/img.png"}]},
            status=200,
        )

        generate_image(
            prompt="Test prompt",
            model="custom-model",
            api_key="fake-key",
            n=2,
            size="512x512",
        )

        req = json.loads(responses.calls[0].request.body)
        assert req["prompt"] == "Test prompt"
        assert req["model"] == "custom-model"
        assert req["n"] == 2
        assert req["size"] == "512x512"

    @responses.activate
    def test_api_error(self):
        responses.add(
            responses.POST,
            IMAGE_GENERATION_URL,
            body="Model not found",
            status=404,
        )

        result = generate_image(prompt="Test", api_key="fake-key")
        assert result["success"] is False

    @responses.activate
    def test_base64_response(self):
        fake_b64 = base64.b64encode(b"fake image data").decode()
        responses.add(
            responses.POST,
            IMAGE_GENERATION_URL,
            json={"data": [{"b64_json": fake_b64}]},
            status=200,
        )

        result = generate_image(prompt="Base64 test", api_key="fake-key")
        assert result["success"] is True
        assert "b64_json" in result["images"][0]


# ─── Save Image ──────────────────────────────────────────────────


class TestSaveImage:
    def test_save_from_base64(self):
        original = b"PNG image bytes here"
        b64_data = base64.b64encode(original).decode()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.png"
            result = save_image({"b64_json": b64_data}, str(output_path))

            assert result["success"] is True
            assert output_path.exists()
            assert output_path.read_bytes() == original

    @responses.activate
    def test_save_from_url(self):
        image_bytes = b"downloaded image data"
        image_url = "https://example.com/generated.png"

        responses.add(
            responses.GET,
            image_url,
            body=image_bytes,
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "downloaded.png"
            result = save_image({"url": image_url}, str(output_path))

            assert result["success"] is True
            assert output_path.exists()
            assert output_path.read_bytes() == image_bytes

    def test_no_image_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "empty.png"
            result = save_image({}, str(output_path))

            assert result["success"] is False
            assert "expected" in result["message"].lower()

    def test_creates_parent_directories(self):
        original = b"image bytes"
        b64_data = base64.b64encode(original).decode()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "deep" / "test.png"
            result = save_image({"b64_json": b64_data}, str(output_path))

            assert result["success"] is True
            assert output_path.exists()
