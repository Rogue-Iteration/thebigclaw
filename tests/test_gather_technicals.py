"""
Tests for gather_technicals.py — Ace's technical analysis gathering.

Tests cover:
- Indicator calculations (SMA, RSI, MACD, Bollinger Bands)
- Signal identification (crossovers, divergences, breakouts)
- Markdown formatting
- Combined gather_technicals() function
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import json

import pytest

import sys

SKILL_DIR = Path(__file__).parent.parent / "skills" / "gradient-data-gathering" / "scripts"
sys.path.insert(0, str(SKILL_DIR))

from gather_technicals import (
    fetch_price_data,
    calculate_indicators,
    identify_signals,
    format_technicals_markdown,
    gather_technicals,
    _sma,
    _ema,
    _calculate_rsi,
    _calculate_macd,
    _calculate_bollinger,
)


# ─── Fixtures ─────────────────────────────────────────────────────


def _make_ohlcv(n: int, base_price: float = 50.0, trend: float = 0.0) -> list[dict]:
    """Generate synthetic OHLCV data for testing."""
    data = []
    for i in range(n):
        close = base_price + trend * i + (i % 3 - 1) * 0.5
        data.append({
            "date": f"2026-01-{(i % 28) + 1:02d}",
            "open": round(close - 0.3, 2),
            "high": round(close + 1.0, 2),
            "low": round(close - 1.0, 2),
            "close": round(close, 2),
            "volume": 1_000_000 + i * 10_000,
        })
    return data


@pytest.fixture
def ohlcv_data():
    """130 days of OHLCV data — enough for SMA(50), RSI, MACD."""
    return _make_ohlcv(130, base_price=50.0, trend=0.1)


@pytest.fixture
def long_ohlcv_data():
    """250 days of OHLCV data — enough for SMA(200)."""
    return _make_ohlcv(250, base_price=40.0, trend=0.05)


# ─── SMA ─────────────────────────────────────────────────────────


class TestSMA:
    def test_sma_basic(self):
        prices = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = _sma(prices, 3)
        assert result[0] is None
        assert result[1] is None
        assert result[2] == 2.0
        assert result[3] == 3.0
        assert result[4] == 4.0

    def test_sma_single_period(self):
        prices = [5.0, 10.0, 15.0]
        result = _sma(prices, 1)
        assert result == [5.0, 10.0, 15.0]

    def test_sma_longer_than_data(self):
        prices = [1.0, 2.0]
        result = _sma(prices, 5)
        assert all(v is None for v in result)


# ─── EMA ─────────────────────────────────────────────────────────


class TestEMA:
    def test_ema_basic(self):
        prices = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        result = _ema(prices, 3)
        assert result[0] is None
        assert result[1] is None
        assert result[2] is not None
        assert result[-1] is not None
        # EMA should be > SMA for upward trend
        assert result[-1] > 5.0

    def test_ema_insufficient_data(self):
        prices = [1.0, 2.0]
        result = _ema(prices, 5)
        assert all(v is None for v in result)


# ─── RSI ─────────────────────────────────────────────────────────


class TestRSI:
    def test_rsi_uptrend(self):
        """Pure uptrend should give RSI near 100."""
        prices = [float(i) for i in range(1, 30)]
        rsi = _calculate_rsi(prices, 14)
        # Last RSI should be very high (strong uptrend)
        last_rsi = rsi[-1]
        assert last_rsi is not None
        assert last_rsi > 80

    def test_rsi_downtrend(self):
        """Pure downtrend should give RSI near 0."""
        prices = [float(30 - i) for i in range(30)]
        rsi = _calculate_rsi(prices, 14)
        last_rsi = rsi[-1]
        assert last_rsi is not None
        assert last_rsi < 20

    def test_rsi_insufficient_data(self):
        prices = [1.0, 2.0, 3.0]
        rsi = _calculate_rsi(prices, 14)
        assert all(v is None for v in rsi)


# ─── MACD ────────────────────────────────────────────────────────


class TestMACD:
    def test_macd_basic(self, ohlcv_data):
        closes = [d["close"] for d in ohlcv_data]
        macd_line, signal_line, histogram = _calculate_macd(closes)
        assert len(macd_line) == len(closes)
        # Should have non-None values after the slow period
        non_none = [v for v in macd_line if v is not None]
        assert len(non_none) > 0

    def test_macd_insufficient_data(self):
        closes = [float(i) for i in range(10)]
        macd_line, signal_line, histogram = _calculate_macd(closes)
        # Very short data: may not produce signal values
        assert len(macd_line) == 10


# ─── Bollinger Bands ──────────────────────────────────────────────


class TestBollingerBands:
    def test_bollinger_basic(self):
        prices = [float(50 + i % 5) for i in range(30)]
        upper, middle, lower = _calculate_bollinger(prices, 20, 2)
        assert upper[-1] is not None
        assert middle[-1] is not None
        assert lower[-1] is not None
        assert upper[-1] > middle[-1] > lower[-1]

    def test_bollinger_insufficient_data(self):
        prices = [50.0, 51.0, 52.0]
        upper, middle, lower = _calculate_bollinger(prices, 20, 2)
        assert all(v is None for v in upper)


# ─── Calculate Indicators ─────────────────────────────────────────


class TestCalculateIndicators:
    def test_returns_success_with_enough_data(self, ohlcv_data):
        result = calculate_indicators(ohlcv_data)
        assert result["success"] is True
        assert "latest" in result
        assert "price_range" in result

    def test_insufficient_data(self):
        data = _make_ohlcv(10)
        result = calculate_indicators(data)
        assert result["success"] is False

    def test_latest_values(self, ohlcv_data):
        result = calculate_indicators(ohlcv_data)
        latest = result["latest"]
        assert "close" in latest
        assert "sma_20" in latest
        assert "rsi" in latest
        assert "volume" in latest

    def test_price_range(self, ohlcv_data):
        result = calculate_indicators(ohlcv_data)
        pr = result["price_range"]
        assert "change_1d_pct" in pr
        assert "change_5d_pct" in pr
        assert "high_20d" in pr


# ─── Signal Identification ────────────────────────────────────────


class TestIdentifySignals:
    def test_no_signals_from_empty(self):
        assert identify_signals({"success": False}) == []

    def test_rsi_overbought_signal(self):
        indicators = {
            "success": True,
            "latest": {
                "close": 100, "volume": 1_000_000,
                "sma_20": 95, "sma_50": 90, "sma_200": 85,
                "rsi": 75, "macd": 1.0, "macd_signal": 0.5, "macd_histogram": 0.5,
                "bb_upper": 105, "bb_middle": 95, "bb_lower": 85,
                "volume_sma_20": 800_000,
            },
            "previous": {
                "sma_50": 89, "sma_200": 84,
                "macd": 0.8, "macd_signal": 0.9,
                "rsi": 72,
            },
            "price_range": {"change_1d_pct": 2.0, "change_5d_pct": 5.0, "change_20d_pct": 10.0,
                            "high_20d": 102, "low_20d": 88},
        }
        signals = identify_signals(indicators)
        signal_texts = [s["signal"] for s in signals]
        # Should detect RSI overbought
        assert any("RSI overbought" in s for s in signal_texts)

    def test_volume_spike_signal(self):
        indicators = {
            "success": True,
            "latest": {
                "close": 50, "volume": 5_000_000,
                "sma_20": 48, "sma_50": None, "sma_200": None,
                "rsi": 55, "macd": None, "macd_signal": None, "macd_histogram": None,
                "bb_upper": 53, "bb_middle": 50, "bb_lower": 47,
                "volume_sma_20": 1_000_000,
            },
            "previous": {"sma_50": None, "sma_200": None, "macd": None, "macd_signal": None, "rsi": 54},
            "price_range": {"change_1d_pct": 3.0, "change_5d_pct": 5.0, "change_20d_pct": 8.0,
                            "high_20d": 52, "low_20d": 46},
        }
        signals = identify_signals(indicators)
        assert any("Volume spike" in s["signal"] for s in signals)

    def test_signals_have_required_fields(self):
        indicators = {
            "success": True,
            "latest": {
                "close": 30, "volume": 500_000,
                "sma_20": 32, "sma_50": None, "sma_200": None,
                "rsi": 25, "macd": None, "macd_signal": None, "macd_histogram": None,
                "bb_upper": 35, "bb_middle": 32, "bb_lower": 29,
                "volume_sma_20": 500_000,
            },
            "previous": {"sma_50": None, "sma_200": None, "macd": None, "macd_signal": None, "rsi": 28},
            "price_range": {"change_1d_pct": -1.0, "change_5d_pct": -3.0, "change_20d_pct": -8.0,
                            "high_20d": 35, "low_20d": 29},
        }
        signals = identify_signals(indicators)
        for sig in signals:
            assert "signal" in sig
            assert "type" in sig
            assert sig["type"] in ("bullish", "bearish")
            assert "strength" in sig


# ─── Markdown Formatting ─────────────────────────────────────────


class TestFormatTechnicalsMarkdown:
    def test_format_with_data(self, ohlcv_data):
        indicators = calculate_indicators(ohlcv_data)
        signals = identify_signals(indicators)
        md = format_technicals_markdown("CAKE", indicators, signals, {})
        assert "Technical Analysis: $CAKE" in md
        assert "Price Summary" in md
        assert "Moving Averages" in md
        assert "Momentum" in md

    def test_format_failure(self):
        md = format_technicals_markdown("CAKE", {"success": False, "message": "No data"}, [], {})
        assert "No data" in md

    def test_format_includes_volume(self, ohlcv_data):
        indicators = calculate_indicators(ohlcv_data)
        md = format_technicals_markdown("CAKE", indicators, [], {})
        assert "Volume" in md


# ─── Combined Gather ─────────────────────────────────────────────


class TestGatherTechnicals:
    def test_returns_required_keys(self, monkeypatch):
        monkeypatch.setattr(
            "gather_technicals.fetch_price_data",
            lambda *a, **kw: {"success": True, "data": _make_ohlcv(130), "info": {}, "message": "OK"},
        )

        result = gather_technicals("CAKE", "The Cheesecake Factory")

        assert result["ticker"] == "CAKE"
        assert result["company"] == "The Cheesecake Factory"
        assert "timestamp" in result
        assert "markdown" in result
        assert "indicators" in result
        assert "signals" in result

    def test_handles_fetch_failure(self, monkeypatch):
        monkeypatch.setattr(
            "gather_technicals.fetch_price_data",
            lambda *a, **kw: {"success": False, "data": [], "info": {}, "message": "API error"},
        )

        result = gather_technicals("FAKE", "Fake Corp")

        assert result["indicators"]["success"] is False
        assert result["signals"] == []
        assert "Failed" in result["markdown"] or "API error" in result["markdown"]
