#!/usr/bin/env python3
"""
Research task management for the Gradient Research Assistant.

Allows agents and users to create, list, update, and delete research tasks.
Tasks can be assigned to specific agents and linked to tickers.

Usage (called by OpenClaw):
    python3 tasks.py --add --title "Research mRNA therapies" --symbol BNTX --agent luna
    python3 tasks.py --list
    python3 tasks.py --list --status pending --agent luna
    python3 tasks.py --update 1 --status completed --result "Found 3 key studies"
    python3 tasks.py --delete 1
    python3 tasks.py --show 1
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any, Optional

from db import get_connection, init_db


# ─── Valid values ─────────────────────────────────────────────────

VALID_STATUSES = {"pending", "in_progress", "completed", "failed"}
VALID_AGENTS = {"max", "nova", "luna", "ace"}


# ─── CRUD Operations ─────────────────────────────────────────────


def create_task(
    conn,
    title: str,
    symbol: Optional[str] = None,
    description: Optional[str] = None,
    assigned_agent: Optional[str] = None,
    priority: int = 5,
) -> dict:
    """Create a new research task.

    Args:
        conn: Database connection
        title: Task title (required)
        symbol: Optional ticker symbol to link to
        description: Optional longer description
        assigned_agent: Optional agent name (max, nova, luna, ace)
        priority: Priority 1-10 (default 5)

    Returns:
        dict with 'success', 'message', and 'task_id'.
    """
    if not title or not title.strip():
        return {"success": False, "message": "Task title cannot be empty.", "task_id": None}

    if assigned_agent and assigned_agent.lower() not in VALID_AGENTS:
        return {
            "success": False,
            "message": f"Unknown agent '{assigned_agent}'. Valid agents: {', '.join(sorted(VALID_AGENTS))}",
            "task_id": None,
        }

    if not (1 <= priority <= 10):
        return {"success": False, "message": "Priority must be between 1 and 10.", "task_id": None}

    normalized_symbol = symbol.upper().lstrip("$").strip() if symbol else None
    normalized_agent = assigned_agent.lower() if assigned_agent else None

    cursor = conn.execute(
        """INSERT INTO research_tasks (symbol, title, description, assigned_agent, priority)
           VALUES (?, ?, ?, ?, ?)""",
        (
            normalized_symbol,
            title.strip(),
            description.strip() if description else None,
            normalized_agent,
            priority,
        ),
    )
    conn.commit()

    task_id = cursor.lastrowid
    msg = f"Created task #{task_id}: {title.strip()}"
    if normalized_symbol:
        msg += f" (${normalized_symbol})"
    if normalized_agent:
        msg += f" → assigned to {normalized_agent}"

    return {"success": True, "message": msg, "task_id": task_id}


def list_tasks(
    conn,
    status: Optional[str] = None,
    agent: Optional[str] = None,
    symbol: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """List research tasks with optional filters.

    Returns list of task dicts.
    """
    query = "SELECT * FROM research_tasks WHERE 1=1"
    params: list = []

    if status:
        query += " AND status = ?"
        params.append(status)
    if agent:
        query += " AND assigned_agent = ?"
        params.append(agent.lower())
    if symbol:
        query += " AND symbol = ?"
        params.append(symbol.upper().lstrip("$"))

    query += " ORDER BY priority DESC, created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_task(conn, task_id: int) -> Optional[dict]:
    """Get a single task by ID."""
    row = conn.execute(
        "SELECT * FROM research_tasks WHERE id = ?", (task_id,)
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def update_task(
    conn,
    task_id: int,
    status: Optional[str] = None,
    result_summary: Optional[str] = None,
    assigned_agent: Optional[str] = None,
    priority: Optional[int] = None,
) -> dict:
    """Update a research task.

    Returns:
        dict with 'success' and 'message'.
    """
    task = get_task(conn, task_id)
    if task is None:
        return {"success": False, "message": f"Task #{task_id} not found."}

    updates = {}
    changes = []

    if status is not None:
        if status not in VALID_STATUSES:
            return {
                "success": False,
                "message": f"Invalid status '{status}'. Valid: {', '.join(sorted(VALID_STATUSES))}",
            }
        updates["status"] = status
        changes.append(f"status → {status}")
        if status == "completed":
            updates["completed_at"] = datetime.now(timezone.utc).isoformat()

    if result_summary is not None:
        updates["result_summary"] = result_summary.strip()
        changes.append("result updated")

    if assigned_agent is not None:
        if assigned_agent.lower() not in VALID_AGENTS:
            return {
                "success": False,
                "message": f"Unknown agent '{assigned_agent}'. Valid: {', '.join(sorted(VALID_AGENTS))}",
            }
        updates["assigned_agent"] = assigned_agent.lower()
        changes.append(f"assigned → {assigned_agent.lower()}")

    if priority is not None:
        if not (1 <= priority <= 10):
            return {"success": False, "message": "Priority must be between 1 and 10."}
        updates["priority"] = priority
        changes.append(f"priority → {priority}")

    if not updates:
        return {"success": False, "message": "No changes specified."}

    set_clauses = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [task_id]
    conn.execute(f"UPDATE research_tasks SET {set_clauses} WHERE id = ?", values)
    conn.commit()

    return {
        "success": True,
        "message": f"Updated task #{task_id}: {', '.join(changes)}",
    }


def delete_task(conn, task_id: int) -> dict:
    """Delete a research task.

    Returns:
        dict with 'success' and 'message'.
    """
    cursor = conn.execute(
        "DELETE FROM research_tasks WHERE id = ?", (task_id,)
    )
    conn.commit()

    if cursor.rowcount == 0:
        return {"success": False, "message": f"Task #{task_id} not found."}

    return {"success": True, "message": f"Deleted task #{task_id}."}


# ─── Display ─────────────────────────────────────────────────────


STATUS_EMOJI = {
    "pending": "⏳",
    "in_progress": "🔄",
    "completed": "✅",
    "failed": "❌",
}


def format_task(task: dict) -> str:
    """Format a single task for display."""
    emoji = STATUS_EMOJI.get(task["status"], "❓")
    lines = [
        f"{emoji} **Task #{task['id']}**: {task['title']}",
    ]

    if task.get("symbol"):
        lines.append(f"  📊 Ticker: ${task['symbol']}")
    if task.get("assigned_agent"):
        lines.append(f"  🤖 Agent: {task['assigned_agent']}")
    lines.append(f"  📋 Status: {task['status']} | Priority: {task['priority']}/10")
    lines.append(f"  🕐 Created: {task['created_at']}")

    if task.get("description"):
        lines.append(f"  📝 {task['description']}")
    if task.get("result_summary"):
        lines.append(f"  💡 Result: {task['result_summary']}")
    if task.get("completed_at"):
        lines.append(f"  ✅ Completed: {task['completed_at']}")

    return "\n".join(lines)


def format_task_list(tasks: list[dict]) -> str:
    """Format a list of tasks for display."""
    if not tasks:
        return "No tasks found."

    lines = [f"📋 **Research Tasks** ({len(tasks)} total)\n"]
    for task in tasks:
        lines.append(format_task(task))
        lines.append("")

    return "\n".join(lines)


# ─── CLI Interface ────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Manage research tasks")
    parser.add_argument("--db", default=None, help="Path to database file")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--add", action="store_true", help="Create a new task")
    group.add_argument("--list", action="store_true", help="List tasks")
    group.add_argument("--show", type=int, metavar="ID", help="Show task details")
    group.add_argument("--update", type=int, metavar="ID", help="Update a task")
    group.add_argument("--delete", type=int, metavar="ID", help="Delete a task")

    # For --add
    parser.add_argument("--title", help="Task title (required with --add)")
    parser.add_argument("--description", help="Task description")
    parser.add_argument("--symbol", help="Ticker symbol")
    parser.add_argument("--agent", help="Assigned agent (max, nova, luna, ace)")
    parser.add_argument("--priority", type=int, default=5, help="Priority 1-10 (default 5)")

    # For --list filtering
    parser.add_argument("--status", help="Filter by status")

    # For --update
    parser.add_argument("--result", help="Result summary (with --update)")

    args = parser.parse_args()

    conn = get_connection(args.db)
    init_db(conn)

    if args.add:
        if not args.title:
            print("Error: --title is required when adding a task.", file=sys.stderr)
            sys.exit(1)
        result = create_task(
            conn,
            title=args.title,
            symbol=args.symbol,
            description=args.description,
            assigned_agent=args.agent,
            priority=args.priority,
        )
        print(result["message"])
        if not result["success"]:
            sys.exit(1)

    elif args.list:
        tasks = list_tasks(
            conn,
            status=args.status,
            agent=args.agent,
            symbol=args.symbol,
        )
        print(format_task_list(tasks))

    elif args.show is not None:
        task = get_task(conn, args.show)
        if task is None:
            print(f"Task #{args.show} not found.", file=sys.stderr)
            sys.exit(1)
        print(format_task(task))

    elif args.update is not None:
        result = update_task(
            conn,
            args.update,
            status=args.status,
            result_summary=args.result,
            assigned_agent=args.agent,
            priority=args.priority,
        )
        print(result["message"])
        if not result["success"]:
            sys.exit(1)

    elif args.delete is not None:
        result = delete_task(conn, args.delete)
        print(result["message"])
        if not result["success"]:
            sys.exit(1)


if __name__ == "__main__":
    main()
