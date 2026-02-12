"""
Tests for Spaces-backed watchlist persistence.

Tests cover:
- Loading from Spaces when configured
- Falling back to local file when Spaces not configured
- Saving to both Spaces and local file
- First-run fallback (Spaces doesn't have file yet)
- Full roundtrip through Spaces
"""

import json
import os
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

import sys

SKILL_DIR = Path(__file__).parent.parent / "skills" / "gradient-research-assistant"
sys.path.insert(0, str(SKILL_DIR))

from manage_watchlist import (
    load_watchlist,
    save_watchlist,
    _spaces_enabled,
    SPACES_CONFIG_KEY,
)

SAMPLE_WATCHLIST = {
    "default_rules": {"price_movement_pct": 5, "sentiment_shift": True},
    "global_settings": {"significance_threshold": 6},
    "tickers": [{"symbol": "CAKE", "name": "Cheesecake Factory", "added": "2026-02-12", "rules": {}}],
}


@pytest.fixture
def local_watchlist_file(tmp_path):
    """Create a local watchlist.json for fallback tests."""
    filepath = tmp_path / "watchlist.json"
    filepath.write_text(json.dumps(SAMPLE_WATCHLIST, indent=2))
    return str(filepath)


@pytest.fixture
def spaces_env(monkeypatch):
    """Set Spaces environment variables for testing."""
    monkeypatch.setenv("DO_SPACES_ACCESS_KEY", "test-key")
    monkeypatch.setenv("DO_SPACES_SECRET_KEY", "test-secret")
    monkeypatch.setenv("DO_SPACES_ENDPOINT", "https://nyc3.digitaloceanspaces.com")
    monkeypatch.setenv("DO_SPACES_BUCKET", "test-bucket")


@pytest.fixture
def no_spaces_env(monkeypatch):
    """Ensure Spaces env vars are not set."""
    monkeypatch.delenv("DO_SPACES_ACCESS_KEY", raising=False)
    monkeypatch.delenv("DO_SPACES_SECRET_KEY", raising=False)
    monkeypatch.delenv("DO_SPACES_ENDPOINT", raising=False)
    monkeypatch.delenv("DO_SPACES_BUCKET", raising=False)


class TestSpacesEnabled:
    def test_enabled_when_all_vars_set(self, spaces_env):
        assert _spaces_enabled() is True

    def test_disabled_when_vars_missing(self, no_spaces_env):
        assert _spaces_enabled() is False

    def test_disabled_when_partial_vars(self, monkeypatch):
        monkeypatch.setenv("DO_SPACES_ACCESS_KEY", "key")
        monkeypatch.delenv("DO_SPACES_SECRET_KEY", raising=False)
        assert _spaces_enabled() is False


class TestLoadFromSpaces:
    @mock_aws
    def test_loads_from_spaces_via_client_injection(self, spaces_env):
        """When a client is injected and has the file, load from Spaces."""
        conn = boto3.client("s3", region_name="us-east-1")
        conn.create_bucket(Bucket="test-bucket")
        conn.put_object(
            Bucket="test-bucket",
            Key=SPACES_CONFIG_KEY,
            Body=json.dumps(SAMPLE_WATCHLIST).encode(),
        )

        result = load_watchlist("/nonexistent/path.json", client=conn)
        assert result == SAMPLE_WATCHLIST

    @mock_aws
    def test_falls_back_to_local_on_first_run(self, spaces_env, local_watchlist_file):
        """When Spaces (via client) is empty, fall back to local file."""
        conn = boto3.client("s3", region_name="us-east-1")
        conn.create_bucket(Bucket="test-bucket")
        # Don't put any file in Spaces — simulates first run

        result = load_watchlist(local_watchlist_file, client=conn)
        assert result == SAMPLE_WATCHLIST

    def test_falls_back_to_local_when_not_configured(self, no_spaces_env, local_watchlist_file):
        """When Spaces is not configured, load from local file."""
        result = load_watchlist(local_watchlist_file)
        assert result == SAMPLE_WATCHLIST


class TestSaveToSpaces:
    @mock_aws
    def test_saves_to_both_spaces_and_local(self, spaces_env, tmp_path):
        """When a client is injected, save to both locations."""
        conn = boto3.client("s3", region_name="us-east-1")
        conn.create_bucket(Bucket="test-bucket")

        local_path = str(tmp_path / "watchlist.json")
        save_watchlist(SAMPLE_WATCHLIST, local_path, client=conn)

        # Verify local file
        local_data = json.loads(Path(local_path).read_text())
        assert local_data == SAMPLE_WATCHLIST

        # Verify Spaces
        obj = conn.get_object(Bucket="test-bucket", Key=SPACES_CONFIG_KEY)
        spaces_data = json.loads(obj["Body"].read().decode())
        assert spaces_data == SAMPLE_WATCHLIST

    def test_saves_only_locally_when_not_configured(self, no_spaces_env, tmp_path):
        """When Spaces is not configured, only save locally."""
        local_path = str(tmp_path / "watchlist.json")
        save_watchlist(SAMPLE_WATCHLIST, local_path)

        local_data = json.loads(Path(local_path).read_text())
        assert local_data == SAMPLE_WATCHLIST

    @mock_aws
    def test_roundtrip_through_spaces(self, spaces_env, tmp_path):
        """Save to Spaces then load from Spaces — full roundtrip."""
        conn = boto3.client("s3", region_name="us-east-1")
        conn.create_bucket(Bucket="test-bucket")

        local_path = str(tmp_path / "watchlist.json")
        save_watchlist(SAMPLE_WATCHLIST, local_path, client=conn)
        loaded = load_watchlist(local_path, client=conn)
        assert loaded == SAMPLE_WATCHLIST
