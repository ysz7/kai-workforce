"""Plan storage: the decomposition and its edges, saved together.

A plan row on its own is a revision number and a rationale. What makes it a plan
is which tasks it contains and which of them wait for which - so `save` writes
the edges in the same transaction, and `get` refuses to hand back a plan whose
tasks it could not read.

The tasks themselves live in `tasks` and are written when somebody is given
one. This does not duplicate them: a plan holds their ids through its dependency
edges and through `tasks.plan_id`, and reads them back from the one place they
are stored. Two copies of a task's status would eventually disagree, and the
copy inside the plan would be the stale one - which is exactly what a plan
saved again at the end of a run would write back, since the tasks in a `Plan`
value are the ones the planner proposed and never moved on.

So a plan read back mid-run holds the tasks that have started, in plan order,
with their current state. Before any of them has, it holds its edges and no
tasks; what KAI intends is on the progress stream by then, and what it did is
here afterwards.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import replace
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from domain.errors import StorageError, StorageNotInitializedError
from domain.tasks.repository import TaskRepository
from domain.workforce.protocols import Plan, PlanStatus
from domain.workspace.models import WorkspaceId
from infrastructure.persistence.mappers import row_to_task
from infrastructure.persistence.models import PlanRow, PlanTaskDependencyRow, TaskRow
from infrastructure.persistence.session import session_scope


class SqlitePlanRepository:
    """Implements `domain.workforce.repository.PlanRepository`."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[AsyncSession]:
        try:
            async with session_scope(self._session_factory) as session:
                yield session
        except OperationalError as error:
            message = str(error.orig)
            if "no such table" in message or "unable to open database file" in message:
                raise StorageNotInitializedError(
                    "The local database has no schema yet."
                ) from error
            raise StorageError(message) from error

    async def save(self, plan: Plan) -> None:
        values = {
            "id": str(plan.id),
            "workspace_id": str(plan.workspace_id),
            "objective_id": str(plan.objective_id),
            "revision": plan.revision,
            "status": plan.status.value,
            "rationale": plan.rationale,
        }
        async with self._session() as session:
            statement = sqlite_insert(PlanRow).values(**values)
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[PlanRow.id],
                    set_={k: v for k, v in values.items() if k != "id"},
                )
            )
            # Edges are replaced wholesale rather than merged: a plan saved
            # twice has one set of dependencies, and a partial update would
            # leave an edge from a revision that no longer exists.
            await session.execute(
                delete(PlanTaskDependencyRow).where(
                    PlanTaskDependencyRow.plan_id == str(plan.id)
                )
            )
            known = {task.id for task in plan.tasks}
            for task_id, depends_on in plan.dependencies:
                # An edge to a task outside this plan cannot be satisfied and
                # would fail the foreign key anyway; dropping it here says so.
                if task_id in known and depends_on in known:
                    session.add(
                        PlanTaskDependencyRow(
                            plan_id=str(plan.id),
                            task_id=str(task_id),
                            depends_on=str(depends_on),
                        )
                    )

    async def get(self, plan_id: UUID) -> Plan | None:
        async with self._session() as session:
            row = await session.get(PlanRow, str(plan_id))
            if row is None:
                return None
            return await self._hydrate(session, row)

    async def for_objective(self, objective_id: UUID) -> list[Plan]:
        async with self._session() as session:
            rows = await session.scalars(
                select(PlanRow)
                .where(PlanRow.objective_id == str(objective_id))
                .order_by(PlanRow.revision.desc())
            )
            return [await self._hydrate(session, row) for row in rows]

    async def _hydrate(self, session: AsyncSession, row: PlanRow) -> Plan:
        tasks = await session.scalars(
            select(TaskRow)
            .where(TaskRow.plan_id == row.id)
            # Plan order, not creation order: the planner sets a descending
            # priority so the first task it wrote reads first here too.
            .order_by(TaskRow.priority.desc(), TaskRow.created_at)
        )
        edges = await session.scalars(
            select(PlanTaskDependencyRow).where(PlanTaskDependencyRow.plan_id == row.id)
        )
        return Plan(
            id=UUID(row.id),
            objective_id=UUID(row.objective_id),
            tasks=tuple(row_to_task(task) for task in tasks),
            dependencies=tuple(
                (UUID(edge.task_id), UUID(edge.depends_on)) for edge in edges
            ),
            revision=row.revision,
            status=PlanStatus(row.status),
            rationale=row.rationale,
            workspace_id=WorkspaceId(row.workspace_id),
        )


class InMemoryPlanRepository:
    """Implements `domain.workforce.repository.PlanRepository`.

    Give it the task repository and it behaves like the SQLite one: a plan holds
    ids, each task's current state is read back from where tasks are stored, and
    a task with no row yet is not in the plan at all - which is the state of
    every plan between being proposed and being started. Without it, the tasks
    are whatever was saved: fine for a test that only cares about revisions,
    wrong for one that expects a status to have moved on. The argument exists so
    the fake can be held to the same contract, which is the only thing that
    makes a paired test worth writing.
    """

    def __init__(self, tasks: TaskRepository | None = None) -> None:
        self._plans: dict[UUID, Plan] = {}
        self._tasks = tasks

    async def save(self, plan: Plan) -> None:
        self._plans[plan.id] = deepcopy(plan)

    async def get(self, plan_id: UUID) -> Plan | None:
        found = self._plans.get(plan_id)
        return await self._fresh(found) if found else None

    async def _fresh(self, plan: Plan) -> Plan:
        if self._tasks is None:
            return deepcopy(plan)
        tasks = []
        for task in plan.tasks:
            stored = await self._tasks.get(task.id)
            if stored is not None:
                tasks.append(stored)
        return replace(deepcopy(plan), tasks=tuple(tasks))

    async def for_objective(self, objective_id: UUID) -> list[Plan]:
        return [
            await self._fresh(plan)
            for plan in sorted(
                self._plans.values(), key=lambda p: p.revision, reverse=True
            )
            if plan.objective_id == objective_id
        ]
