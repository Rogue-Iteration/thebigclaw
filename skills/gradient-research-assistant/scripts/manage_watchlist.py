#!/usr/bin/env python3
"""
Watchlist management for the Gradient Research Assistant.

Handles adding/removing tickers, per-ticker alert rule overrides,
global settings, and display of effective rules.

All data is stored in SQLite via db.py. Changes take effect on the
next heartbeat cycle.

Usage (called by OpenClaw):
    python3 manage_watchlist.py --add TICKER --name "Company Name"
    python3 manage_watchlist.py --remove TICKER
    python3 manage_watchlist.py --set-rule TICKER rule_name value
    python3 manage_watchlist.py --reset-rules TICKER
    python3 manage_watchlist.py --set-global key value
    python3 manage_watchlist.py --show
"""

import argparse
import json
import sys
from datetime import date
from typing import Any, Optional

from db import get_connection, init_db, get_default_rules, get_setting, set_setting

# Valid rule names and their expected types
VALID_RULES = {
    "price_movement_pct": (int, float),
    "sentiment_shift": (bool,),
    "social_volume_spike": (bool,),
    "sec_filing": (bool,),
    "competitive_news": (bool,),
}

# Valid global setting keys
VALID_GLOBALS = {"significance_threshold", "cheap_model", "strong_model"}


# ─── Helpers ─────────────────────────────────────────────────────


def _normalize_symbol(symbol: str) -> str:
    """Strip $ prefix and uppercase the symbol."""
    return symbol.lstrip("$").upper().strip()


def _row_to_dict(row) -> dict:
    """Convert a sqlite3.Row to a plain dict with parsed rules JSON."""
    d = dict(row)
    # Parse the rules JSON column
    if "rules" in d:
        try:
            d["rules"] = json.loads(d["rules"]) if d["rules"] else {}
        except (json.JSONDecodeError, TypeError):
            d["rules"] = {}
    # Convert explore_adjacent int to bool
    if "explore_adjacent" in d:
        d["explore_adjacent"] = bool(d["explore_adjacent"])
    return d


# ─── Core Operations ─────────────────────────────────────────────


def find_ticker(conn, symbol: str) -> Optional[dict]:
    """Find a ticker in the watchlist by symbol (case-insensitive, $-tolerant).

    Returns the ticker dict if found, None otherwise.
    """
    normalized = _normalize_symbol(symbol)
    row = conn.execute(
        "SELECT * FROM watchlist WHERE symbol = ?", (normalized,)
    ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def add_ticker(
    conn,
    symbol: str,
    name: str,
    theme: Optional[str] = None,
    directive: Optional[str] = None,
    explore_adjacent: bool = False,
) -> dict:
    """Add a new ticker to the watchlist.

    Args:
        conn: Database connection
        symbol: Stock ticker symbol
        name: Company name
        theme: Optional research theme (e.g., "mRNA cancer research")
        directive: Optional research directive
        explore_adjacent: Whether to explore adjacent tickers

    Returns:
        dict with 'success' (bool) and 'message' (str).
    """
    normalized = _normalize_symbol(symbol)

    if not normalized:
        return {"success": False, "message": "Symbol cannot be empty."}

    if not name or not name.strip():
        return {"success": False, "message": "Company name cannot be empty."}

    if find_ticker(conn, normalized):
        return {
            "success": False,
            "message": f"${normalized} is already in your watchlist.",
        }

    conn.execute(
        """INSERT INTO watchlist (symbol, name, theme, directive, explore_adjacent, added_at, rules)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            normalized,
            name.strip(),
            theme.strip() if theme else None,
            directive.strip() if directive else None,
            1 if explore_adjacent else 0,
            date.today().isoformat(),
            "{}",
        ),
    )
    conn.commit()

    msg = f"Added ${normalized} ({name.strip()}) to your watchlist."
    if theme:
        msg += f" Theme: {theme.strip()}"
    if directive:
        msg += f" Directive: {directive.strip()}"
    if explore_adjacent:
        msg += " Adjacent ticker exploration enabled."

    return {"success": True, "message": msg}


def remove_ticker(conn, symbol: str) -> dict:
    """Remove a ticker from the watchlist.

    Returns:
        dict with 'success' (bool) and 'message' (str).
    """
    normalized = _normalize_symbol(symbol)

    cursor = conn.execute(
        "DELETE FROM watchlist WHERE symbol = ?", (normalized,)
    )
    conn.commit()

    if cursor.rowcount == 0:
        return {
            "success": False,
            "message": f"${normalized} not found in your watchlist.",
        }

    return {
        "success": True,
        "message": f"Removed ${normalized} from your watchlist.",
    }


def set_rule(conn, symbol: str, rule_name: str, value: Any) -> dict:
    """Set a per-ticker alert rule override.

    Validates that the rule name is known and the value type is correct.

    Returns:
        dict with 'success' (bool) and 'message' (str).
    """
    ticker = find_ticker(conn, symbol)
    if ticker is None:
        normalized = _normalize_symbol(symbol)
        return {
            "success": False,
            "message": f"${normalized} not found in your watchlist.",
        }

    if rule_name not in VALID_RULES:
        return {
            "success": False,
            "message": f"Unknown rule '{rule_name}'. Valid rules: {', '.join(sorted(VALID_RULES.keys()))}",
        }

    expected_types = VALID_RULES[rule_name]
    if not isinstance(value, expected_types):
        type_names = " or ".join(t.__name__ for t in expected_types)
        return {
            "success": False,
            "message": f"Invalid value for '{rule_name}': expected {type_names}, got {type(value).__name__}.",
        }

    # Update the rules JSON column
    rules = ticker["rules"]
    rules[rule_name] = value
    conn.execute(
        "UPDATE watchlist SET rules = ? WHERE symbol = ?",
        (json.dumps(rules), ticker["symbol"]),
    )
    conn.commit()

    return {
        "success": True,
        "message": f"Set {rule_name} = {value} for ${ticker['symbol']}. Effective next heartbeat.",
    }


def reset_rules(conn, symbol: str) -> dict:
    """Reset a ticker's rules to defaults (clear all overrides).

    Returns:
        dict with 'success' (bool) and 'message' (str).
    """
    ticker = find_ticker(conn, symbol)
    if ticker is None:
        normalized = _normalize_symbol(symbol)
        return {
            "success": False,
            "message": f"${normalized} not found in your watchlist.",
        }

    conn.execute(
        "UPDATE watchlist SET rules = '{}' WHERE symbol = ?",
        (ticker["symbol"],),
    )
    conn.commit()

    return {
        "success": True,
        "message": f"Reset ${ticker['symbol']} to default alert rules.",
    }


def set_global(conn, key: str, value: Any) -> dict:
    """Set a global setting (significance_threshold, cheap_model, strong_model).

    Returns:
        dict with 'success' (bool) and 'message' (str).
    """
    if key not in VALID_GLOBALS:
        return {
            "success": False,
            "message": f"Unknown setting '{key}'. Valid settings: {', '.join(sorted(VALID_GLOBALS))}",
        }

    set_setting(conn, key, value)
    return {
        "success": True,
        "message": f"Set global {key} = {value}. Effective next heartbeat.",
    }


def get_effective_rules(conn, symbol: str) -> Optional[dict]:
    """Get the effective alert rules for a ticker (defaults merged with overrides).

    Returns:
        dict of effective rules, or None if ticker not found.
    """
    ticker = find_ticker(conn, symbol)
    if ticker is None:
        return None

    defaults = get_default_rules(conn)
    overrides = ticker.get("rules", {})

    # Merge: defaults as base, overrides take precedence
    effective = {**defaults, **overrides}
    return effective


def set_directive(
    conn,
    symbol: str,
    theme: Optional[str] = None,
    directive: Optional[str] = None,
    explore_adjacent: Optional[bool] = None,
) -> dict:
    """Set research theme, directive, or explore_adjacent for a ticker.

    Args:
        conn: Database connection
        symbol: Stock ticker symbol
        theme: Research theme (None = don't change)
        directive: Research directive (None = don't change)
        explore_adjacent: Whether to explore adjacent tickers (None = don't change)

    Returns:
        dict with 'success' (bool) and 'message' (str).
    """
    ticker = find_ticker(conn, symbol)
    if ticker is None:
        normalized = _normalize_symbol(symbol)
        return {
            "success": False,
            "message": f"${normalized} not found in your watchlist.",
        }

    changes = []
    updates = {}

    if theme is not None:
        updates["theme"] = theme.strip() if theme else None
        changes.append(f"theme='{theme}'" if theme else "theme cleared")
    if directive is not None:
        updates["directive"] = directive.strip() if directive else None
        changes.append(f"directive='{directive}'" if directive else "directive cleared")
    if explore_adjacent is not None:
        updates["explore_adjacent"] = 1 if explore_adjacent else 0
        changes.append(f"explore_adjacent={'on' if explore_adjacent else 'off'}")

    if not changes:
        return {"success": False, "message": "No changes specified."}

    # Build dynamic UPDATE
    set_clauses = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [ticker["symbol"]]
    conn.execute(
        f"UPDATE watchlist SET {set_clauses} WHERE symbol = ?",
        values,
    )
    conn.commit()

    return {
        "success": True,
        "message": f"Updated ${ticker['symbol']}: {', '.join(changes)}",
    }


def show_watchlist(conn) -> str:
    """Format the current watchlist with effective rules for display.

    Returns:
        Human-readable string representation.
    """
    rows = conn.execute(
        "SELECT * FROM watchlist ORDER BY added_at"
    ).fetchall()

    if not rows:
        return "No tickers in your watchlist. Send me a ticker to start tracking!"

    lines = []
    lines.append("📊 **Your Watchlist**\n")

    # Show global settings
    threshold = get_setting(conn, "significance_threshold", "N/A")
    cheap_model = get_setting(conn, "cheap_model", "N/A")
    strong_model = get_setting(conn, "strong_model", "N/A")

    if any(v != "N/A" for v in [threshold, cheap_model, strong_model]):
        lines.append(f"⚙️ Global significance threshold: {threshold}")
        lines.append(f"   Cheap model: {cheap_model}")
        lines.append(f"   Strong model: {strong_model}")
        lines.append("")

    defaults = get_default_rules(conn)

    for row in rows:
        ticker = _row_to_dict(row)
        symbol = ticker["symbol"]
        name = ticker["name"]
        added = ticker.get("added_at", "unknown")
        overrides = ticker.get("rules", {})
        theme = ticker.get("theme")
        directive_val = ticker.get("directive")
        explore = ticker.get("explore_adjacent", False)

        lines.append(f"**${symbol}** — {name} (since {added})")

        # Show theme/directive if set
        if theme:
            lines.append(f"  🎯 Theme: {theme}")
        if directive_val:
            lines.append(f"  📌 Directive: {directive_val}")
        if explore:
            lines.append("  🔍 Adjacent ticker exploration: on")

        effective = {**defaults, **overrides}
        for rule_name, value in sorted(effective.items()):
            is_override = rule_name in overrides
            marker = " ✏️" if is_override else ""
            if rule_name == "price_movement_pct":
                lines.append(f"  • Price movement alert: >{value}%{marker}")
            elif isinstance(value, bool):
                status = "✅" if value else "❌"
                label = rule_name.replace("_", " ").title()
                lines.append(f"  • {label}: {status}{marker}")
        lines.append("")

    return "\n".join(lines)


# ─── CLI Interface ────────────────────────────────────────────────


def _parse_value(value_str: str) -> Any:
    """Parse a CLI string value into the appropriate Python type."""
    if value_str.lower() in ("true", "yes", "on"):
        return True
    if value_str.lower() in ("false", "no", "off"):
        return False
    try:
        return int(value_str)
    except ValueError:
        pass
    try:
        return float(value_str)
    except ValueError:
        pass
    return value_str


def main():
    parser = argparse.ArgumentParser(description="Manage research watchlist")
    parser.add_argument("--db", default=None, help="Path to database file")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--add", metavar="TICKER", help="Add a ticker")
    group.add_argument("--remove", metavar="TICKER", help="Remove a ticker")
    group.add_argument("--set-rule", nargs=3, metavar=("TICKER", "RULE", "VALUE"), help="Set a per-ticker rule")
    group.add_argument("--reset-rules", metavar="TICKER", help="Reset ticker to default rules")
    group.add_argument("--set-global", nargs=2, metavar=("KEY", "VALUE"), help="Set a global setting")
    group.add_argument("--set-directive", metavar="TICKER", help="Set theme/directive for a ticker")
    group.add_argument("--show", action="store_true", help="Show current watchlist")

    parser.add_argument("--name", help="Company name (required with --add)")
    parser.add_argument("--theme", default=None, help="Research theme (with --add or --set-directive)")
    parser.add_argument("--directive", default=None, help="Research directive (with --add or --set-directive)")
    parser.add_argument("--explore", action="store_true", help="Enable adjacent ticker exploration (with --add or --set-directive)")

    args = parser.parse_args()

    conn = get_connection(args.db)
    init_db(conn)

    if args.add:
        if not args.name:
            print("Error: --name is required when adding a ticker.", file=sys.stderr)
            sys.exit(1)
        result = add_ticker(
            conn,
            args.add,
            args.name,
            theme=args.theme,
            directive=args.directive,
            explore_adjacent=args.explore,
        )
    elif args.remove:
        result = remove_ticker(conn, args.remove)
    elif args.set_rule:
        ticker, rule, value = args.set_rule
        result = set_rule(conn, ticker, rule, _parse_value(value))
    elif args.reset_rules:
        result = reset_rules(conn, args.reset_rules)
    elif args.set_global:
        key, value = args.set_global
        result = set_global(conn, key, _parse_value(value))
    elif args.set_directive:
        result = set_directive(
            conn,
            args.set_directive,
            theme=args.theme,
            directive=args.directive,
            explore_adjacent=args.explore if args.explore else None,
        )
    elif args.show:
        print(show_watchlist(conn))
        return

    print(result["message"])
    if not result["success"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
