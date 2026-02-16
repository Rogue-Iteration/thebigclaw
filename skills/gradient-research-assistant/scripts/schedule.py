#!/usr/bin/env python3
"""
Scheduled updates management for the Gradient Research Assistant.

Allows agents and users to create, list, update, and delete scheduled reports
(morning briefings, evening wraps, weekly digests, etc.). Schedules are
timezone-aware and checked during Max's heartbeat cycle.

Usage (called by OpenClaw agents):
    python3 schedule.py --add --name "Morning Briefing" --time 08:00 --days 1-5 --agent max --prompt "Deliver morning briefing"
    python3 schedule.py --list
    python3 schedule.py --show 1
    python3 schedule.py --update 1 --time 09:00
    python3 schedule.py --update 1 --enabled false
    python3 schedule.py --delete 1
    python3 schedule.py --check                          # returns due schedules (for heartbeat)
    python3 schedule.py --mark-run 1                     # mark schedule as run (for heartbeat)
    python3 schedule.py --set-timezone "Europe/Berlin"
    python3 schedule.py --show-timezone
    python3 schedule.py --seed-defaults                  # create default schedules (idempotent)
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo, available_timezones

from db import get_connection, get_setting, init_db, set_setting


# ─── Constants ───────────────────────────────────────────────────

VALID_AGENTS = {"max", "nova", "luna", "ace", "all"}
VALID_SCHEDULE_TYPES = {"daily", "weekly", "custom"}
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

# Day constants: 0=Sun, 1=Mon, ..., 6=Sat (matching Python isoweekday % 7)
WEEKDAY_NAMES = {
    0: "Sun", 1: "Mon", 2: "Tue", 3: "Wed",
    4: "Thu", 5: "Fri", 6: "Sat",
}

DEFAULT_SCHEDULES = [
    {
        "name": "Morning Briefing",
        "description": "Daily morning briefing covering overnight developments, "
                       "current theses, conviction changes, and team activity.",
        "schedule_type": "daily",
        "time": "08:00",
        "days": "1-5",
        "agent": "max",
        "prompt": (
            "Deliver your morning briefing. Cover ALL tickers on the watchlist: "
            "overnight developments, your current thesis for each, conviction "
            "level changes, team activity summary (Nova's articles, Luna's social "
            "signals, Ace's technical signals), and what the team should focus on "
            "today. End with a question to the user."
        ),
    },
    {
        "name": "Evening Wrap",
        "description": "Daily evening wrap-up summarizing the day's research, "
                       "alerts, and any shifts in outlook.",
        "schedule_type": "daily",
        "time": "18:00",
        "days": "1-5",
        "agent": "max",
        "prompt": (
            "Deliver your evening wrap-up. Summarize today's research activity "
            "across the team: key findings from Nova, sentiment shifts from Luna, "
            "technical signals from Ace. Highlight any thesis changes or new "
            "developments. Note any tickers that were quiet. Briefly outline "
            "what to watch for overnight."
        ),
    },
]


# ─── Days Parsing ────────────────────────────────────────────────


def parse_days(days_str: str) -> set[int]:
    """Parse a days string into a set of day numbers (0-6, 0=Sun).

    Accepts:
        "*"     → all days
        "1-5"   → range (Mon-Fri)
        "0,6"   → specific days (Sun, Sat)
        "1-5,0" → mixed
    """
    if days_str.strip() == "*":
        return {0, 1, 2, 3, 4, 5, 6}

    result = set()
    for part in days_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            start, end = int(start), int(end)
            if start <= end:
                result.update(range(start, end + 1))
            else:
                # Wrap around: 5-1 means Fri,Sat,Sun,Mon
                result.update(range(start, 7))
                result.update(range(0, end + 1))
        else:
            result.add(int(part))

    # Validate all days are 0-6
    if not all(0 <= d <= 6 for d in result):
        raise ValueError(f"Invalid day numbers in '{days_str}'. Must be 0-6 (0=Sun).")
    return result


def format_days(days_str: str) -> str:
    """Format a days string into human-readable text."""
    if days_str.strip() == "*":
        return "every day"

    days = parse_days(days_str)
    if days == {1, 2, 3, 4, 5}:
        return "weekdays"
    if days == {0, 6}:
        return "weekends"
    if days == {0, 1, 2, 3, 4, 5, 6}:
        return "every day"

    names = [WEEKDAY_NAMES[d] for d in sorted(days)]
    return ", ".join(names)


def validate_days(days_str: str) -> Optional[str]:
    """Validate a days string. Returns error message or None if valid."""
    try:
        parse_days(days_str)
        return None
    except (ValueError, KeyError) as e:
        return str(e)


# ─── Timezone Helpers ────────────────────────────────────────────


def get_user_timezone(conn) -> str:
    """Get the user's configured timezone. Defaults to UTC."""
    return get_setting(conn, "user_timezone", "UTC")


def set_user_timezone(conn, tz_name: str) -> dict:
    """Set the user's timezone.

    Returns:
        dict with 'success' and 'message'.
    """
    if tz_name not in available_timezones() and tz_name != "UTC":
        return {
            "success": False,
            "message": (
                f"Unknown timezone '{tz_name}'. Use IANA timezone names "
                f"(e.g., Europe/Berlin, US/Eastern, Asia/Tokyo)."
            ),
        }
    set_setting(conn, "user_timezone", tz_name)
    return {"success": True, "message": f"Timezone set to {tz_name}."}


# ─── CRUD Operations ────────────────────────────────────────────


def create_schedule(
    conn,
    name: str,
    time: str,
    prompt: str,
    description: Optional[str] = None,
    schedule_type: str = "daily",
    days: str = "*",
    agent: str = "max",
    enabled: bool = True,
) -> dict:
    """Create a new scheduled update.

    Returns:
        dict with 'success', 'message', and 'schedule_id'.
    """
    if not name or not name.strip():
        return {"success": False, "message": "Schedule name cannot be empty.", "schedule_id": None}

    if not TIME_PATTERN.match(time):
        return {
            "success": False,
            "message": f"Invalid time format '{time}'. Use HH:MM (24-hour).",
            "schedule_id": None,
        }

    if not prompt or not prompt.strip():
        return {"success": False, "message": "Prompt cannot be empty.", "schedule_id": None}

    if agent.lower() not in VALID_AGENTS:
        return {
            "success": False,
            "message": f"Unknown agent '{agent}'. Valid: {', '.join(sorted(VALID_AGENTS))} (use 'all' for team-wide)",
            "schedule_id": None,
        }

    if schedule_type not in VALID_SCHEDULE_TYPES:
        return {
            "success": False,
            "message": f"Invalid type '{schedule_type}'. Valid: {', '.join(sorted(VALID_SCHEDULE_TYPES))}",
            "schedule_id": None,
        }

    days_error = validate_days(days)
    if days_error:
        return {"success": False, "message": days_error, "schedule_id": None}

    cursor = conn.execute(
        """INSERT INTO scheduled_updates
           (name, description, schedule_type, time, days, agent, prompt, enabled)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            name.strip(),
            description.strip() if description else None,
            schedule_type,
            time,
            days,
            agent.lower(),
            prompt.strip(),
            1 if enabled else 0,
        ),
    )
    conn.commit()

    schedule_id = cursor.lastrowid
    tz = get_user_timezone(conn)
    msg = f"Created schedule #{schedule_id}: {name.strip()} at {time} ({tz}), {format_days(days)}"

    return {"success": True, "message": msg, "schedule_id": schedule_id}


def list_schedules(
    conn,
    agent: Optional[str] = None,
    enabled_only: bool = False,
) -> list[dict]:
    """List scheduled updates with optional filters."""
    query = "SELECT * FROM scheduled_updates WHERE 1=1"
    params: list = []

    if agent:
        query += " AND agent = ?"
        params.append(agent.lower())
    if enabled_only:
        query += " AND enabled = 1"

    query += " ORDER BY time ASC"

    rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_schedule(conn, schedule_id: int) -> Optional[dict]:
    """Get a single schedule by ID."""
    row = conn.execute(
        "SELECT * FROM scheduled_updates WHERE id = ?", (schedule_id,)
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def update_schedule(
    conn,
    schedule_id: int,
    name: Optional[str] = None,
    time: Optional[str] = None,
    days: Optional[str] = None,
    agent: Optional[str] = None,
    prompt: Optional[str] = None,
    enabled: Optional[bool] = None,
    description: Optional[str] = None,
) -> dict:
    """Update a scheduled update.

    Returns:
        dict with 'success' and 'message'.
    """
    schedule = get_schedule(conn, schedule_id)
    if schedule is None:
        return {"success": False, "message": f"Schedule #{schedule_id} not found."}

    updates = {}
    changes = []

    if name is not None:
        if not name.strip():
            return {"success": False, "message": "Schedule name cannot be empty."}
        updates["name"] = name.strip()
        changes.append(f"name → {name.strip()}")

    if time is not None:
        if not TIME_PATTERN.match(time):
            return {"success": False, "message": f"Invalid time format '{time}'. Use HH:MM (24-hour)."}
        updates["time"] = time
        changes.append(f"time → {time}")

    if days is not None:
        days_error = validate_days(days)
        if days_error:
            return {"success": False, "message": days_error}
        updates["days"] = days
        changes.append(f"days → {format_days(days)}")

    if agent is not None:
        if agent.lower() not in VALID_AGENTS:
            return {
                "success": False,
                "message": f"Unknown agent '{agent}'. Valid: {', '.join(sorted(VALID_AGENTS))}",
            }
        updates["agent"] = agent.lower()
        changes.append(f"agent → {agent.lower()}")

    if prompt is not None:
        if not prompt.strip():
            return {"success": False, "message": "Prompt cannot be empty."}
        updates["prompt"] = prompt.strip()
        changes.append("prompt updated")

    if enabled is not None:
        updates["enabled"] = 1 if enabled else 0
        changes.append("enabled" if enabled else "paused")

    if description is not None:
        updates["description"] = description.strip() if description else None
        changes.append("description updated")

    if not updates:
        return {"success": False, "message": "No changes specified."}

    set_clauses = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [schedule_id]
    conn.execute(f"UPDATE scheduled_updates SET {set_clauses} WHERE id = ?", values)
    conn.commit()

    return {
        "success": True,
        "message": f"Updated schedule #{schedule_id}: {', '.join(changes)}",
    }


def delete_schedule(conn, schedule_id: int) -> dict:
    """Delete a scheduled update.

    Returns:
        dict with 'success' and 'message'.
    """
    cursor = conn.execute(
        "DELETE FROM scheduled_updates WHERE id = ?", (schedule_id,)
    )
    conn.commit()

    if cursor.rowcount == 0:
        return {"success": False, "message": f"Schedule #{schedule_id} not found."}

    return {"success": True, "message": f"Deleted schedule #{schedule_id}."}


def mark_run(conn, schedule_id: int, agent: Optional[str] = None) -> dict:
    """Mark a schedule as having just run.

    For 'all' schedules, pass the agent name to track per-agent completion.
    For single-agent schedules, uses the existing last_run_at column.

    Returns:
        dict with 'success' and 'message'.
    """
    schedule = get_schedule(conn, schedule_id)
    if schedule is None:
        return {"success": False, "message": f"Schedule #{schedule_id} not found."}

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    if schedule["agent"] == "all" and agent:
        # Per-agent tracking for team schedules
        tz_name = get_user_timezone(conn)
        try:
            user_tz = ZoneInfo(tz_name)
        except (KeyError, Exception):
            user_tz = ZoneInfo("UTC")
        today_str = now.astimezone(user_tz).strftime("%Y-%m-%d")

        conn.execute(
            """INSERT OR REPLACE INTO schedule_agent_runs
               (schedule_id, agent, run_date, run_at)
               VALUES (?, ?, ?, ?)""",
            (schedule_id, agent.lower(), today_str, now_iso),
        )
        conn.commit()
        return {"success": True, "message": f"Marked schedule #{schedule_id} as run by {agent}."}
    else:
        # Single-agent: use existing last_run_at
        conn.execute(
            "UPDATE scheduled_updates SET last_run_at = ? WHERE id = ?",
            (now_iso, schedule_id),
        )
        conn.commit()
        return {"success": True, "message": f"Marked schedule #{schedule_id} as run."}


# ─── Due Check ───────────────────────────────────────────────────


def _python_weekday_to_schedule_day(python_weekday: int) -> int:
    """Convert Python's weekday (0=Mon) to our format (0=Sun).

    Python: Mon=0, Tue=1, ..., Sun=6
    Ours:   Sun=0, Mon=1, ..., Sat=6
    """
    return (python_weekday + 1) % 7


def check_due_schedules(
    conn,
    now: Optional[datetime] = None,
    agent: Optional[str] = None,
) -> list[dict]:
    """Check which schedules are due right now.

    A schedule is due when:
    1. It is enabled
    2. The current day (in user's timezone) matches the schedule's days
    3. The current time (in user's timezone) is within 30 minutes after the
       scheduled time (to account for heartbeat intervals)
    4. It hasn't already run today (based on last_run_at or per-agent tracking)

    Args:
        conn: Database connection
        now: Optional datetime override for testing. If None, uses current time.
        agent: Optional agent name. When provided, returns schedules where
               agent matches this name OR agent is 'all' (and this agent
               hasn't run it today).

    Returns:
        List of schedule dicts that are due.
    """
    tz_name = get_user_timezone(conn)
    try:
        user_tz = ZoneInfo(tz_name)
    except (KeyError, Exception):
        user_tz = ZoneInfo("UTC")

    if now is None:
        now = datetime.now(user_tz)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=user_tz)
    else:
        now = now.astimezone(user_tz)

    current_day = _python_weekday_to_schedule_day(now.weekday())
    current_minutes = now.hour * 60 + now.minute
    today_str = now.strftime("%Y-%m-%d")

    schedules = list_schedules(conn, enabled_only=True)
    due = []

    for sched in schedules:
        # Filter by agent if specified
        if agent:
            sched_agent = sched["agent"]
            if sched_agent != agent.lower() and sched_agent != "all":
                continue

        # Check day match
        try:
            allowed_days = parse_days(sched["days"])
        except ValueError:
            continue

        if current_day not in allowed_days:
            continue

        # Check time match (within 30-minute window after scheduled time)
        parts = sched["time"].split(":")
        sched_minutes = int(parts[0]) * 60 + int(parts[1])

        time_diff = current_minutes - sched_minutes
        if time_diff < 0 or time_diff >= 30:
            continue

        # Check if already run today
        if sched["agent"] == "all" and agent:
            # For 'all' schedules: check per-agent run tracking
            row = conn.execute(
                """SELECT 1 FROM schedule_agent_runs
                   WHERE schedule_id = ? AND agent = ? AND run_date = ?""",
                (sched["id"], agent.lower(), today_str),
            ).fetchone()
            if row is not None:
                continue
        else:
            # For single-agent schedules: check last_run_at
            if sched.get("last_run_at"):
                try:
                    last_run = datetime.fromisoformat(sched["last_run_at"])
                    if last_run.tzinfo is None:
                        last_run = last_run.replace(tzinfo=timezone.utc)
                    last_run_local = last_run.astimezone(user_tz)
                    if last_run_local.strftime("%Y-%m-%d") == today_str:
                        continue
                except (ValueError, TypeError):
                    pass

        due.append(sched)

    return due


# ─── Seed Defaults ───────────────────────────────────────────────


def seed_defaults(conn) -> dict:
    """Create default schedules if none exist. Idempotent.

    Returns:
        dict with 'success' and 'message'.
    """
    existing = list_schedules(conn)
    if existing:
        return {
            "success": True,
            "message": f"Schedules already exist ({len(existing)} found). Skipping seed.",
        }

    created = []
    for sched in DEFAULT_SCHEDULES:
        result = create_schedule(conn, **sched)
        if result["success"]:
            created.append(sched["name"])

    return {
        "success": True,
        "message": f"Seeded {len(created)} default schedule(s): {', '.join(created)}",
    }


# ─── Display ─────────────────────────────────────────────────────


def format_schedule(schedule: dict, tz_name: str = "UTC") -> str:
    """Format a single schedule for display."""
    status = "✅ Active" if schedule["enabled"] else "⏸️  Paused"
    lines = [
        f"🗓️ **Schedule #{schedule['id']}**: {schedule['name']}",
        f"  ⏰ Time: {schedule['time']} ({tz_name}), {format_days(schedule['days'])}",
        f"  🤖 Agent: {schedule['agent']}",
        f"  📋 Status: {status}",
    ]

    if schedule.get("description"):
        lines.append(f"  📝 {schedule['description']}")
    if schedule.get("last_run_at"):
        lines.append(f"  🕐 Last run: {schedule['last_run_at']}")

    return "\n".join(lines)


def format_schedule_list(schedules: list[dict], tz_name: str = "UTC") -> str:
    """Format a list of schedules for display."""
    if not schedules:
        return "No scheduled updates configured."

    lines = [f"🗓️ **Scheduled Updates** ({len(schedules)} total, timezone: {tz_name})\n"]
    for sched in schedules:
        lines.append(format_schedule(sched, tz_name))
        lines.append("")

    return "\n".join(lines)


# ─── CLI Interface ───────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Manage scheduled updates")
    parser.add_argument("--db", default=None, help="Path to database file")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--add", action="store_true", help="Create a new schedule")
    group.add_argument("--list", action="store_true", help="List schedules")
    group.add_argument("--show", type=int, metavar="ID", help="Show schedule details")
    group.add_argument("--update", type=int, metavar="ID", help="Update a schedule")
    group.add_argument("--delete", type=int, metavar="ID", help="Delete a schedule")
    group.add_argument("--check", action="store_true", help="Check for due schedules")
    group.add_argument("--mark-run", type=int, metavar="ID", help="Mark schedule as run")
    group.add_argument("--set-timezone", metavar="TZ", help="Set user timezone")
    group.add_argument("--show-timezone", action="store_true", help="Show current timezone")
    group.add_argument("--seed-defaults", action="store_true", help="Seed default schedules")

    # For --add / --update
    parser.add_argument("--name", help="Schedule name")
    parser.add_argument("--time", help="Time in HH:MM format (24-hour)")
    parser.add_argument("--days", help="Days: * (all), 1-5 (weekdays), 0,6 (weekends), etc.")
    parser.add_argument("--agent", help="Agent to execute (max, nova, luna, ace)")
    parser.add_argument("--prompt", help="Prompt for the agent when schedule triggers")
    parser.add_argument("--description", help="Human-readable description")
    parser.add_argument(
        "--enabled", help="Enable/disable (true/false)", metavar="BOOL"
    )
    parser.add_argument("--schedule-type", help="Type: daily, weekly, custom", default="daily")

    args = parser.parse_args()

    conn = get_connection(args.db)
    init_db(conn)

    if args.add:
        if not args.name:
            print("Error: --name is required when adding a schedule.", file=sys.stderr)
            sys.exit(1)
        if not args.time:
            print("Error: --time is required when adding a schedule.", file=sys.stderr)
            sys.exit(1)
        if not args.prompt:
            print("Error: --prompt is required when adding a schedule.", file=sys.stderr)
            sys.exit(1)

        result = create_schedule(
            conn,
            name=args.name,
            time=args.time,
            prompt=args.prompt,
            description=args.description,
            schedule_type=args.schedule_type,
            days=args.days or "*",
            agent=args.agent or "max",
        )
        print(result["message"])
        if not result["success"]:
            sys.exit(1)

    elif args.list:
        schedules = list_schedules(conn, agent=args.agent)
        tz = get_user_timezone(conn)
        print(format_schedule_list(schedules, tz))

    elif args.show is not None:
        schedule = get_schedule(conn, args.show)
        if schedule is None:
            print(f"Schedule #{args.show} not found.", file=sys.stderr)
            sys.exit(1)
        tz = get_user_timezone(conn)
        print(format_schedule(schedule, tz))

    elif args.update is not None:
        enabled = None
        if args.enabled is not None:
            enabled = args.enabled.lower() in ("true", "1", "yes")

        result = update_schedule(
            conn,
            args.update,
            name=args.name,
            time=args.time,
            days=args.days,
            agent=args.agent,
            prompt=args.prompt,
            enabled=enabled,
            description=args.description,
        )
        print(result["message"])
        if not result["success"]:
            sys.exit(1)

    elif args.delete is not None:
        result = delete_schedule(conn, args.delete)
        print(result["message"])
        if not result["success"]:
            sys.exit(1)

    elif args.check:
        due = check_due_schedules(conn, agent=args.agent)
        if due:
            print(json.dumps(due, indent=2))
        else:
            print("No schedules due right now.")

    elif args.mark_run is not None:
        result = mark_run(conn, args.mark_run, agent=args.agent)
        print(result["message"])
        if not result["success"]:
            sys.exit(1)

    elif args.set_timezone:
        result = set_user_timezone(conn, args.set_timezone)
        print(result["message"])
        if not result["success"]:
            sys.exit(1)

    elif args.show_timezone:
        tz = get_user_timezone(conn)
        print(f"Current timezone: {tz}")

    elif args.seed_defaults:
        result = seed_defaults(conn)
        print(result["message"])


if __name__ == "__main__":
    main()
