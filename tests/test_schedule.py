"""
Tests for schedule.py — Scheduled updates management.

Tests cover:
- Creating schedules with various options
- Listing schedules with filters
- Getting individual schedules
- Updating schedule fields
- Deleting schedules
- Input validation (time, days, agent, timezone)
- Due-check logic with mocked times and timezones
- Timezone setting/getting
- Default seeding (idempotent)
- Days parsing and formatting
- Display formatting
"""

import pytest
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SKILL_DIR = Path(__file__).parent.parent / "skills" / "gradient-research-assistant" / "scripts"
sys.path.insert(0, str(SKILL_DIR))

from db import get_connection, init_db
from schedule import (
    create_schedule,
    list_schedules,
    get_schedule,
    update_schedule,
    delete_schedule,
    mark_run,
    check_due_schedules,
    seed_defaults,
    set_user_timezone,
    get_user_timezone,
    parse_days,
    format_days,
    validate_days,
    format_schedule,
    format_schedule_list,
)


@pytest.fixture
def conn():
    """In-memory database with schema initialized."""
    c = get_connection(":memory:")
    init_db(c)
    yield c
    c.close()


# ─── Days Parsing ────────────────────────────────────────────────


class TestDaysParsing:
    def test_wildcard(self):
        assert parse_days("*") == {0, 1, 2, 3, 4, 5, 6}

    def test_range(self):
        assert parse_days("1-5") == {1, 2, 3, 4, 5}

    def test_specific_days(self):
        assert parse_days("0,6") == {0, 6}

    def test_mixed(self):
        assert parse_days("1-3,6") == {1, 2, 3, 6}

    def test_single_day(self):
        assert parse_days("0") == {0}

    def test_invalid_day_number(self):
        with pytest.raises(ValueError):
            parse_days("8")

    def test_format_weekdays(self):
        assert format_days("1-5") == "weekdays"

    def test_format_weekends(self):
        assert format_days("0,6") == "weekends"

    def test_format_every_day(self):
        assert format_days("*") == "every day"

    def test_format_specific(self):
        result = format_days("1,3,5")
        assert "Mon" in result
        assert "Wed" in result
        assert "Fri" in result

    def test_validate_valid(self):
        assert validate_days("1-5") is None
        assert validate_days("*") is None
        assert validate_days("0,6") is None

    def test_validate_invalid(self):
        assert validate_days("8") is not None


# ─── Timezone ────────────────────────────────────────────────────


class TestTimezone:
    def test_default_timezone(self, conn):
        tz = get_user_timezone(conn)
        assert tz == "UTC"

    def test_set_valid_timezone(self, conn):
        result = set_user_timezone(conn, "Europe/Berlin")
        assert result["success"] is True
        assert get_user_timezone(conn) == "Europe/Berlin"

    def test_set_invalid_timezone(self, conn):
        result = set_user_timezone(conn, "Mars/Olympus_Mons")
        assert result["success"] is False
        assert "Unknown timezone" in result["message"]

    def test_set_utc(self, conn):
        result = set_user_timezone(conn, "UTC")
        assert result["success"] is True


# ─── Creating Schedules ─────────────────────────────────────────


class TestCreateSchedule:
    def test_create_basic(self, conn):
        result = create_schedule(
            conn, name="Test", time="08:00", prompt="Do something"
        )
        assert result["success"] is True
        assert result["schedule_id"] is not None

    def test_create_with_all_fields(self, conn):
        result = create_schedule(
            conn,
            name="Morning Briefing",
            time="08:00",
            prompt="Deliver briefing",
            description="Daily morning update",
            schedule_type="daily",
            days="1-5",
            agent="max",
        )
        assert result["success"] is True
        sched = get_schedule(conn, result["schedule_id"])
        assert sched["name"] == "Morning Briefing"
        assert sched["time"] == "08:00"
        assert sched["days"] == "1-5"
        assert sched["agent"] == "max"
        assert sched["enabled"] == 1

    def test_create_empty_name_fails(self, conn):
        result = create_schedule(conn, name="", time="08:00", prompt="Test")
        assert result["success"] is False

    def test_create_invalid_time_fails(self, conn):
        result = create_schedule(conn, name="Test", time="25:00", prompt="Test")
        assert result["success"] is False
        result = create_schedule(conn, name="Test", time="8am", prompt="Test")
        assert result["success"] is False

    def test_create_empty_prompt_fails(self, conn):
        result = create_schedule(conn, name="Test", time="08:00", prompt="")
        assert result["success"] is False

    def test_create_invalid_agent_fails(self, conn):
        result = create_schedule(
            conn, name="Test", time="08:00", prompt="Test", agent="bob"
        )
        assert result["success"] is False

    def test_create_invalid_days_fails(self, conn):
        result = create_schedule(
            conn, name="Test", time="08:00", prompt="Test", days="8"
        )
        assert result["success"] is False

    def test_create_normalizes_agent(self, conn):
        result = create_schedule(
            conn, name="Test", time="08:00", prompt="Test", agent="MAX"
        )
        assert result["success"] is True
        sched = get_schedule(conn, result["schedule_id"])
        assert sched["agent"] == "max"


# ─── Listing Schedules ──────────────────────────────────────────


class TestListSchedules:
    def test_list_empty(self, conn):
        schedules = list_schedules(conn)
        assert schedules == []

    def test_list_all(self, conn):
        create_schedule(conn, name="A", time="08:00", prompt="Test")
        create_schedule(conn, name="B", time="18:00", prompt="Test")
        schedules = list_schedules(conn)
        assert len(schedules) == 2

    def test_filter_by_agent(self, conn):
        create_schedule(conn, name="A", time="08:00", prompt="T", agent="max")
        create_schedule(conn, name="B", time="18:00", prompt="T", agent="nova")
        schedules = list_schedules(conn, agent="max")
        assert len(schedules) == 1
        assert schedules[0]["agent"] == "max"

    def test_filter_enabled_only(self, conn):
        r1 = create_schedule(conn, name="A", time="08:00", prompt="T")
        create_schedule(conn, name="B", time="18:00", prompt="T")
        update_schedule(conn, r1["schedule_id"], enabled=False)

        enabled = list_schedules(conn, enabled_only=True)
        assert len(enabled) == 1

    def test_ordered_by_time(self, conn):
        create_schedule(conn, name="Evening", time="18:00", prompt="T")
        create_schedule(conn, name="Morning", time="08:00", prompt="T")
        schedules = list_schedules(conn)
        assert schedules[0]["time"] == "08:00"
        assert schedules[1]["time"] == "18:00"


# ─── Getting Schedules ──────────────────────────────────────────


class TestGetSchedule:
    def test_get_existing(self, conn):
        result = create_schedule(conn, name="Test", time="08:00", prompt="T")
        sched = get_schedule(conn, result["schedule_id"])
        assert sched is not None
        assert sched["name"] == "Test"

    def test_get_nonexistent(self, conn):
        assert get_schedule(conn, 9999) is None


# ─── Updating Schedules ─────────────────────────────────────────


class TestUpdateSchedule:
    def test_update_time(self, conn):
        r = create_schedule(conn, name="Test", time="08:00", prompt="T")
        result = update_schedule(conn, r["schedule_id"], time="09:00")
        assert result["success"] is True
        sched = get_schedule(conn, r["schedule_id"])
        assert sched["time"] == "09:00"

    def test_update_name(self, conn):
        r = create_schedule(conn, name="Test", time="08:00", prompt="T")
        result = update_schedule(conn, r["schedule_id"], name="New Name")
        assert result["success"] is True
        sched = get_schedule(conn, r["schedule_id"])
        assert sched["name"] == "New Name"

    def test_update_enabled(self, conn):
        r = create_schedule(conn, name="Test", time="08:00", prompt="T")
        result = update_schedule(conn, r["schedule_id"], enabled=False)
        assert result["success"] is True
        sched = get_schedule(conn, r["schedule_id"])
        assert sched["enabled"] == 0

    def test_update_days(self, conn):
        r = create_schedule(conn, name="Test", time="08:00", prompt="T")
        result = update_schedule(conn, r["schedule_id"], days="0,6")
        assert result["success"] is True
        sched = get_schedule(conn, r["schedule_id"])
        assert sched["days"] == "0,6"

    def test_update_nonexistent_fails(self, conn):
        result = update_schedule(conn, 9999, time="09:00")
        assert result["success"] is False

    def test_update_invalid_time_fails(self, conn):
        r = create_schedule(conn, name="Test", time="08:00", prompt="T")
        result = update_schedule(conn, r["schedule_id"], time="25:00")
        assert result["success"] is False

    def test_update_invalid_agent_fails(self, conn):
        r = create_schedule(conn, name="Test", time="08:00", prompt="T")
        result = update_schedule(conn, r["schedule_id"], agent="bob")
        assert result["success"] is False

    def test_update_no_changes_fails(self, conn):
        r = create_schedule(conn, name="Test", time="08:00", prompt="T")
        result = update_schedule(conn, r["schedule_id"])
        assert result["success"] is False


# ─── Deleting Schedules ─────────────────────────────────────────


class TestDeleteSchedule:
    def test_delete_existing(self, conn):
        r = create_schedule(conn, name="Test", time="08:00", prompt="T")
        result = delete_schedule(conn, r["schedule_id"])
        assert result["success"] is True
        assert get_schedule(conn, r["schedule_id"]) is None

    def test_delete_nonexistent(self, conn):
        result = delete_schedule(conn, 9999)
        assert result["success"] is False


# ─── Mark Run ────────────────────────────────────────────────────


class TestMarkRun:
    def test_mark_run(self, conn):
        r = create_schedule(conn, name="Test", time="08:00", prompt="T")
        result = mark_run(conn, r["schedule_id"])
        assert result["success"] is True
        sched = get_schedule(conn, r["schedule_id"])
        assert sched["last_run_at"] is not None

    def test_mark_run_nonexistent(self, conn):
        result = mark_run(conn, 9999)
        assert result["success"] is False


# ─── Due Check ───────────────────────────────────────────────────


class TestCheckDueSchedules:
    def test_no_schedules(self, conn):
        due = check_due_schedules(conn)
        assert due == []

    def test_schedule_due_now(self, conn):
        set_user_timezone(conn, "UTC")
        create_schedule(conn, name="Test", time="08:00", prompt="T", days="*")

        # Simulate 08:05 UTC on a Monday
        now = datetime(2026, 2, 16, 8, 5, tzinfo=ZoneInfo("UTC"))
        due = check_due_schedules(conn, now=now)
        assert len(due) == 1
        assert due[0]["name"] == "Test"

    def test_schedule_not_due_wrong_time(self, conn):
        set_user_timezone(conn, "UTC")
        create_schedule(conn, name="Test", time="08:00", prompt="T", days="*")

        # Simulate 10:00 UTC — outside the 30-minute window
        now = datetime(2026, 2, 16, 10, 0, tzinfo=ZoneInfo("UTC"))
        due = check_due_schedules(conn, now=now)
        assert due == []

    def test_schedule_not_due_wrong_day(self, conn):
        set_user_timezone(conn, "UTC")
        # Weekdays only
        create_schedule(conn, name="Test", time="08:00", prompt="T", days="1-5")

        # 2026-02-15 is a Sunday → day 0
        now = datetime(2026, 2, 15, 8, 5, tzinfo=ZoneInfo("UTC"))
        due = check_due_schedules(conn, now=now)
        assert due == []

    def test_schedule_due_on_correct_weekday(self, conn):
        set_user_timezone(conn, "UTC")
        create_schedule(conn, name="Test", time="08:00", prompt="T", days="1-5")

        # 2026-02-16 is a Monday → day 1
        now = datetime(2026, 2, 16, 8, 5, tzinfo=ZoneInfo("UTC"))
        due = check_due_schedules(conn, now=now)
        assert len(due) == 1

    def test_schedule_not_due_already_run_today(self, conn):
        set_user_timezone(conn, "UTC")
        r = create_schedule(conn, name="Test", time="08:00", prompt="T", days="*")
        mark_run(conn, r["schedule_id"])

        # Simulate same day
        now = datetime.now(ZoneInfo("UTC"))
        due = check_due_schedules(conn, now=now.replace(hour=8, minute=5))
        assert due == []

    def test_schedule_disabled_not_due(self, conn):
        set_user_timezone(conn, "UTC")
        r = create_schedule(conn, name="Test", time="08:00", prompt="T", days="*")
        update_schedule(conn, r["schedule_id"], enabled=False)

        now = datetime(2026, 2, 16, 8, 5, tzinfo=ZoneInfo("UTC"))
        due = check_due_schedules(conn, now=now)
        assert due == []

    def test_timezone_aware_due_check(self, conn):
        set_user_timezone(conn, "Europe/Berlin")
        create_schedule(conn, name="Test", time="08:00", prompt="T", days="*")

        # 08:05 Berlin time = 07:05 UTC (Berlin is UTC+1 in winter)
        now = datetime(2026, 2, 16, 8, 5, tzinfo=ZoneInfo("Europe/Berlin"))
        due = check_due_schedules(conn, now=now)
        assert len(due) == 1

    def test_timezone_aware_not_due_in_utc(self, conn):
        set_user_timezone(conn, "Europe/Berlin")
        create_schedule(conn, name="Test", time="08:00", prompt="T", days="*")

        # 08:05 UTC = 09:05 Berlin → outside 30-min window
        now = datetime(2026, 2, 16, 8, 5, tzinfo=ZoneInfo("UTC"))
        due = check_due_schedules(conn, now=now)
        # This should NOT be due because in Berlin it's 09:05, which is 65 mins past 08:00
        assert due == []

    def test_within_30min_window(self, conn):
        set_user_timezone(conn, "UTC")
        create_schedule(conn, name="Test", time="08:00", prompt="T", days="*")

        # 08:29 — within 30-min window
        now = datetime(2026, 2, 16, 8, 29, tzinfo=ZoneInfo("UTC"))
        due = check_due_schedules(conn, now=now)
        assert len(due) == 1

    def test_outside_30min_window(self, conn):
        set_user_timezone(conn, "UTC")
        create_schedule(conn, name="Test", time="08:00", prompt="T", days="*")

        # 08:30 — outside 30-min window (boundary)
        now = datetime(2026, 2, 16, 8, 30, tzinfo=ZoneInfo("UTC"))
        due = check_due_schedules(conn, now=now)
        assert due == []

    def test_before_scheduled_time(self, conn):
        set_user_timezone(conn, "UTC")
        create_schedule(conn, name="Test", time="08:00", prompt="T", days="*")

        # 07:59 — before scheduled time
        now = datetime(2026, 2, 16, 7, 59, tzinfo=ZoneInfo("UTC"))
        due = check_due_schedules(conn, now=now)
        assert due == []


# ─── Seed Defaults ───────────────────────────────────────────────


class TestSeedDefaults:
    def test_seeds_when_empty(self, conn):
        result = seed_defaults(conn)
        assert result["success"] is True
        assert "2" in result["message"]

        schedules = list_schedules(conn)
        assert len(schedules) == 2
        names = {s["name"] for s in schedules}
        assert "Morning Briefing" in names
        assert "Evening Wrap" in names

    def test_idempotent(self, conn):
        seed_defaults(conn)
        result = seed_defaults(conn)
        assert result["success"] is True
        assert "already exist" in result["message"].lower()

        schedules = list_schedules(conn)
        assert len(schedules) == 2

    def test_default_times(self, conn):
        seed_defaults(conn)
        schedules = list_schedules(conn)
        times = {s["name"]: s["time"] for s in schedules}
        assert times["Morning Briefing"] == "08:00"
        assert times["Evening Wrap"] == "18:00"

    def test_default_days(self, conn):
        seed_defaults(conn)
        schedules = list_schedules(conn)
        for s in schedules:
            assert s["days"] == "1-5"  # weekdays

    def test_default_agent(self, conn):
        seed_defaults(conn)
        schedules = list_schedules(conn)
        for s in schedules:
            assert s["agent"] == "max"


# ─── Formatting ──────────────────────────────────────────────────


class TestFormatting:
    def test_format_schedule(self, conn):
        r = create_schedule(
            conn, name="Morning Briefing", time="08:00", prompt="T",
            days="1-5", agent="max"
        )
        sched = get_schedule(conn, r["schedule_id"])
        output = format_schedule(sched, "Europe/Berlin")
        assert "Morning Briefing" in output
        assert "08:00" in output
        assert "Europe/Berlin" in output
        assert "weekdays" in output

    def test_format_empty_list(self, conn):
        output = format_schedule_list([], "UTC")
        assert "No scheduled updates" in output

    def test_format_schedule_list(self, conn):
        create_schedule(conn, name="A", time="08:00", prompt="T")
        create_schedule(conn, name="B", time="18:00", prompt="T")
        schedules = list_schedules(conn)
        output = format_schedule_list(schedules, "UTC")
        assert "A" in output
        assert "B" in output
        assert "2 total" in output
