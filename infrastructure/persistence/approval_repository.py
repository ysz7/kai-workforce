"""Approval storage. SQL does not leave this package."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from domain.approvals.models import Approval, ApprovalRequest, ApprovalState
from domain.errors import StorageError, StorageNotInitializedError
from domain.policies.models import RiskLevel
from domain.workspace.models import DEFAULT_WORKSPACE_ID, WorkspaceId
from infrastructure.persistence.models import ApprovalRow
from infrastructure.persistence.session import session_scope


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _to_values(approval: Approval) -> dict:
    request = approval.request
    return {
        "id": str(request.id),
        "workspace_id": str(request.workspace_id),
        "task_id": str(request.task_id),
        "requested_by_employee_id": (
            str(request.requested_by_employee_id) if request.requested_by_employee_id else None
        ),
        "action": request.action,
        "payload": request.payload,
        "risk_level": request.risk_level.value,
        "state": approval.state.value,
        "reason": request.reason,
        "requested_at": request.requested_at,
        "resolved_at": approval.resolved_at,
        "resolved_by": approval.resolved_by,
        "comment": approval.comment,
    }


def _to_approval(row: ApprovalRow) -> Approval:
    return Approval(
        request=ApprovalRequest(
            id=UUID(row.id),
            task_id=UUID(row.task_id),
            action=row.action,
            payload=row.payload or {},
            risk_level=RiskLevel(row.risk_level),
            workspace_id=WorkspaceId(row.workspace_id),
            requested_by_employee_id=(
                UUID(row.requested_by_employee_id) if row.requested_by_employee_id else None
            ),
            requested_at=_aware(row.requested_at),  # type: ignore[arg-type]
            reason=row.reason or "",
        ),
        state=ApprovalState(row.state),
        resolved_at=_aware(row.resolved_at),
        resolved_by=row.resolved_by,
        comment=row.comment or "",
    )


class SqliteApprovalRepository:
    """Implements `domain.approvals.protocols.ApprovalRepository`."""

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
                raise StorageNotInitializedError("The local database has no schema yet.") from error
            raise StorageError(message) from error

    async def save(self, approval: Approval) -> None:
        values = _to_values(approval)
        async with self._session() as session:
            statement = sqlite_insert(ApprovalRow).values(**values)
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[ApprovalRow.id],
                    set_={k: v for k, v in values.items() if k not in ("id", "requested_at")},
                )
            )

    async def get(self, approval_id: UUID) -> Approval | None:
        async with self._session() as session:
            row = await session.get(ApprovalRow, str(approval_id))
            return _to_approval(row) if row else None

    async def list_pending(
        self, workspace_id: WorkspaceId = DEFAULT_WORKSPACE_ID
    ) -> list[Approval]:
        async with self._session() as session:
            rows = await session.scalars(
                select(ApprovalRow)
                .where(
                    ApprovalRow.state == ApprovalState.PENDING.value,
                    ApprovalRow.workspace_id == str(workspace_id),
                )
                .order_by(ApprovalRow.requested_at)
            )
            return [_to_approval(row) for row in rows]


class InMemoryApprovalRepository:
    """Implements `domain.approvals.protocols.ApprovalRepository`."""

    def __init__(self) -> None:
        self._approvals: dict[UUID, Approval] = {}

    async def save(self, approval: Approval) -> None:
        self._approvals[approval.id] = approval

    async def get(self, approval_id: UUID) -> Approval | None:
        return self._approvals.get(approval_id)

    async def list_pending(
        self, workspace_id: WorkspaceId = DEFAULT_WORKSPACE_ID
    ) -> list[Approval]:
        return sorted(
            (
                approval
                for approval in self._approvals.values()
                if approval.is_pending and approval.request.workspace_id == workspace_id
            ),
            key=lambda approval: approval.request.requested_at,
        )
