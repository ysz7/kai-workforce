"""Domain values as JSON, in one place.

Kept apart from the routes so the shape the browser sees is defined once and can
be read without reading the server. It is a projection, not a serialization
format: the interface shows what a person needs to judge a run - what it did,
what it cost, what went wrong - and nothing that only the runtime cares about.

Two omissions are deliberate. The transcript is not exposed: it is the model's
working memory, it is large, and a page that renders it becomes a log viewer,
which is exactly the thing Phase 6 exists to stop the developer reading. And
nothing here reaches into `execution.state`, so the interface does not become a
second consumer of the resume cursor's shape.
"""

from __future__ import annotations

from typing import Any

from domain.approvals.models import Approval, ApprovalRequest
from domain.employees.definition import EmployeeDefinition
from domain.tasks.task import Task, TaskEvent
from domain.tools.telemetry import ToolCallRecord


def task_summary(task: Task, *, running: bool = False) -> dict[str, Any]:
    """One line of history: enough to list, not enough to inspect."""
    return {
        "id": str(task.id),
        "goal": task.goal,
        "status": task.status.value,
        "running": running,
        "step": task.execution.step,
        "cost_usd": round(task.cost_usd, 6),
        "attempts": task.attempts,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "employee_id": str(task.assigned_employee_id) if task.assigned_employee_id else None,
    }


def task_detail(
    task: Task,
    *,
    running: bool = False,
    calls: list[ToolCallRecord] | None = None,
    events: list[TaskEvent] | None = None,
    employee: str | None = None,
) -> dict[str, Any]:
    """A past or present run, opened.

    The tool calls come from the stored log rather than the live stream, which
    is what makes an execution from last week open the same way as the one
    running now.
    """
    return {
        **task_summary(task, running=running),
        "employee": employee,
        "plan": task.plan.to_dict() if task.plan else None,
        "result": (
            {
                "summary": task.result.summary,
                "artifacts": list(task.result.artifacts),
            }
            if task.result
            else None
        ),
        "error": (
            {"kind": task.error.kind, "message": task.error.message} if task.error else None
        ),
        "calls": [tool_call(call) for call in calls or ()],
        "events": [
            {
                "from": event.from_status.value if event.from_status else None,
                "to": event.to_status.value,
                "at": event.created_at.isoformat(),
            }
            for event in events or ()
        ],
    }


def tool_call(call: ToolCallRecord) -> dict[str, Any]:
    """One action, as it was recorded - arguments already redacted on the way in."""
    return {
        "tool": call.tool,
        "success": call.success,
        "interface": call.interface.value,
        "latency_ms": call.latency_ms,
        "arguments": call.input_data,
        "output": call.output,
        "error": call.error,
        "at": call.created_at.isoformat(),
    }


def approval(request: ApprovalRequest, *, live: bool = True) -> dict[str, Any]:
    """A question waiting on a person.

    `live` says whether this process is the one parked on the answer. A PENDING
    row left behind by a killed run can still be recorded as decided, but no
    tool call is going to resume from it, and saying so beats implying it.
    """
    safe = request.redacted()
    return {
        "id": str(safe.id),
        "task_id": str(safe.task_id),
        "action": safe.action,
        "risk": safe.risk_level.value,
        "reason": safe.reason,
        "payload": safe.payload,
        "requested_at": safe.requested_at.isoformat(),
        "live": live,
    }


def stored_approval(record: Approval, *, live: bool = False) -> dict[str, Any]:
    return {**approval(record.request, live=live), "state": record.state.value}


def employee(definition: EmployeeDefinition) -> dict[str, Any]:
    return {
        "id": str(definition.id),
        "name": definition.name,
        "title": definition.role.title,
        "description": definition.role.description,
        "tools": sorted(definition.allowed_tools),
        "limits": {
            "max_steps": definition.limits.max_steps,
            "max_cost_usd": definition.limits.max_cost_usd,
            "max_wall_time_seconds": definition.limits.max_wall_time_seconds,
        },
    }
