"""
Tests for tasks.py — Research task management.

Tests cover:
- Creating tasks with various options
- Listing tasks with filters
- Getting individual tasks
- Updating task status, agent, priority, result
- Deleting tasks
- Input validation
- Display formatting
"""

import pytest
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent / "skills" / "gradient-research-assistant"
sys.path.insert(0, str(SKILL_DIR))

from db import get_connection, init_db
from tasks import (
    create_task,
    list_tasks,
    get_task,
    update_task,
    delete_task,
    format_task,
    format_task_list,
)


@pytest.fixture
def conn():
    """In-memory database with schema initialized."""
    c = get_connection(":memory:")
    init_db(c)
    yield c
    c.close()


# ─── Creating Tasks ──────────────────────────────────────────────


class TestCreateTask:
    def test_create_basic_task(self, conn):
        result = create_task(conn, "Research mRNA therapies")
        assert result["success"] is True
        assert result["task_id"] is not None
        assert "mRNA" in result["message"]

    def test_create_with_all_fields(self, conn):
        result = create_task(
            conn,
            title="Deep dive on $BNTX pipeline",
            symbol="BNTX",
            description="Focus on Phase 3 trials in China",
            assigned_agent="luna",
            priority=8,
        )
        assert result["success"] is True
        task = get_task(conn, result["task_id"])
        assert task["title"] == "Deep dive on $BNTX pipeline"
        assert task["symbol"] == "BNTX"
        assert task["description"] == "Focus on Phase 3 trials in China"
        assert task["assigned_agent"] == "luna"
        assert task["priority"] == 8
        assert task["status"] == "pending"

    def test_create_empty_title_fails(self, conn):
        result = create_task(conn, "")
        assert result["success"] is False

    def test_create_invalid_agent_fails(self, conn):
        result = create_task(conn, "Test", assigned_agent="bob")
        assert result["success"] is False
        assert "unknown" in result["message"].lower()

    def test_create_invalid_priority_fails(self, conn):
        result = create_task(conn, "Test", priority=0)
        assert result["success"] is False
        result = create_task(conn, "Test", priority=11)
        assert result["success"] is False

    def test_create_normalizes_symbol(self, conn):
        result = create_task(conn, "Test", symbol="$cake")
        assert result["success"] is True
        task = get_task(conn, result["task_id"])
        assert task["symbol"] == "CAKE"

    def test_create_normalizes_agent(self, conn):
        result = create_task(conn, "Test", assigned_agent="LUNA")
        assert result["success"] is True
        task = get_task(conn, result["task_id"])
        assert task["assigned_agent"] == "luna"


# ─── Listing Tasks ───────────────────────────────────────────────


class TestListTasks:
    def test_list_empty(self, conn):
        tasks = list_tasks(conn)
        assert tasks == []

    def test_list_all(self, conn):
        create_task(conn, "Task 1")
        create_task(conn, "Task 2")
        create_task(conn, "Task 3")
        tasks = list_tasks(conn)
        assert len(tasks) == 3

    def test_filter_by_status(self, conn):
        r1 = create_task(conn, "Task 1")
        create_task(conn, "Task 2")
        update_task(conn, r1["task_id"], status="completed")

        pending = list_tasks(conn, status="pending")
        assert len(pending) == 1

        completed = list_tasks(conn, status="completed")
        assert len(completed) == 1

    def test_filter_by_agent(self, conn):
        create_task(conn, "Luna task", assigned_agent="luna")
        create_task(conn, "Nova task", assigned_agent="nova")

        luna_tasks = list_tasks(conn, agent="luna")
        assert len(luna_tasks) == 1
        assert luna_tasks[0]["assigned_agent"] == "luna"

    def test_filter_by_symbol(self, conn):
        create_task(conn, "CAKE task", symbol="CAKE")
        create_task(conn, "HOG task", symbol="HOG")

        cake_tasks = list_tasks(conn, symbol="CAKE")
        assert len(cake_tasks) == 1
        assert cake_tasks[0]["symbol"] == "CAKE"

    def test_ordered_by_priority(self, conn):
        create_task(conn, "Low", priority=1)
        create_task(conn, "High", priority=9)
        create_task(conn, "Medium", priority=5)

        tasks = list_tasks(conn)
        priorities = [t["priority"] for t in tasks]
        assert priorities == sorted(priorities, reverse=True)


# ─── Getting Tasks ───────────────────────────────────────────────


class TestGetTask:
    def test_get_existing_task(self, conn):
        result = create_task(conn, "Test task")
        task = get_task(conn, result["task_id"])
        assert task is not None
        assert task["title"] == "Test task"

    def test_get_nonexistent_returns_none(self, conn):
        assert get_task(conn, 9999) is None


# ─── Updating Tasks ──────────────────────────────────────────────


class TestUpdateTask:
    def test_update_status(self, conn):
        r = create_task(conn, "Test")
        result = update_task(conn, r["task_id"], status="in_progress")
        assert result["success"] is True
        task = get_task(conn, r["task_id"])
        assert task["status"] == "in_progress"

    def test_update_to_completed_sets_timestamp(self, conn):
        r = create_task(conn, "Test")
        update_task(conn, r["task_id"], status="completed")
        task = get_task(conn, r["task_id"])
        assert task["completed_at"] is not None

    def test_update_result_summary(self, conn):
        r = create_task(conn, "Test")
        update_task(conn, r["task_id"], result_summary="Found 3 studies")
        task = get_task(conn, r["task_id"])
        assert task["result_summary"] == "Found 3 studies"

    def test_update_agent(self, conn):
        r = create_task(conn, "Test")
        update_task(conn, r["task_id"], assigned_agent="nova")
        task = get_task(conn, r["task_id"])
        assert task["assigned_agent"] == "nova"

    def test_update_priority(self, conn):
        r = create_task(conn, "Test")
        update_task(conn, r["task_id"], priority=9)
        task = get_task(conn, r["task_id"])
        assert task["priority"] == 9

    def test_update_nonexistent_fails(self, conn):
        result = update_task(conn, 9999, status="completed")
        assert result["success"] is False

    def test_update_invalid_status_fails(self, conn):
        r = create_task(conn, "Test")
        result = update_task(conn, r["task_id"], status="bogus")
        assert result["success"] is False

    def test_update_invalid_agent_fails(self, conn):
        r = create_task(conn, "Test")
        result = update_task(conn, r["task_id"], assigned_agent="bob")
        assert result["success"] is False

    def test_update_no_changes_fails(self, conn):
        r = create_task(conn, "Test")
        result = update_task(conn, r["task_id"])
        assert result["success"] is False


# ─── Deleting Tasks ──────────────────────────────────────────────


class TestDeleteTask:
    def test_delete_existing(self, conn):
        r = create_task(conn, "Test")
        result = delete_task(conn, r["task_id"])
        assert result["success"] is True
        assert get_task(conn, r["task_id"]) is None

    def test_delete_nonexistent_fails(self, conn):
        result = delete_task(conn, 9999)
        assert result["success"] is False


# ─── Formatting ──────────────────────────────────────────────────


class TestFormatting:
    def test_format_task(self, conn):
        r = create_task(conn, "Test task", symbol="CAKE", assigned_agent="luna")
        task = get_task(conn, r["task_id"])
        output = format_task(task)
        assert "Test task" in output
        assert "$CAKE" in output
        assert "luna" in output

    def test_format_empty_list(self, conn):
        output = format_task_list([])
        assert "No tasks" in output

    def test_format_task_list(self, conn):
        create_task(conn, "Task 1")
        create_task(conn, "Task 2")
        tasks = list_tasks(conn)
        output = format_task_list(tasks)
        assert "Task 1" in output
        assert "Task 2" in output
        assert "2 total" in output
