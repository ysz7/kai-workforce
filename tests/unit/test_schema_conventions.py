"""Schema-level rules that are cheap now and expensive to retrofit."""

from __future__ import annotations

from domain.tasks.task import TaskStatus
from infrastructure.persistence.models import Base, EmployeeRow, TaskRow

#: Tables that are infrastructure bookkeeping rather than user-owned data, plus
#: one join table. `plan_task_dependencies` holds nothing but three foreign
#: keys; its workspace is whatever the plan's is, and a copy of that column
#: would be a second answer to a question the plan already answers.
NON_USER_TABLES = {"task_events", "llm_calls", "tool_calls", "plan_task_dependencies"}


def test_every_user_table_carries_a_workspace_id() -> None:
    missing = [
        table.name
        for table in Base.metadata.tables.values()
        if table.name not in NON_USER_TABLES and "workspace_id" not in table.columns
    ]
    assert not missing, f"tables without workspace_id: {missing}"


def test_workspace_id_defaults_to_the_single_local_workspace() -> None:
    for row in (TaskRow, EmployeeRow):
        column = row.__table__.columns["workspace_id"]
        assert column.default is not None
        assert column.default.arg == "default"


def test_task_status_check_constraint_matches_the_enum() -> None:
    constraint = next(
        c for c in TaskRow.__table__.constraints if getattr(c, "name", "") == "ck_tasks_status"
    )
    text = str(constraint.sqltext)
    for status in TaskStatus:
        assert f"'{status.value}'" in text
