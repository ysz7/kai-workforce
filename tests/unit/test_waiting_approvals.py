"""An approval answered from somewhere other than the terminal.

The rule under test is the same one the console confirmer follows: anything but
an explicit yes is a no. What changes is who says it and when.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from domain.approvals.models import ApprovalRequest, ApprovalState
from domain.policies.models import RiskLevel
from infrastructure.approvals.service import LocalApprovalService
from infrastructure.approvals.waiting import WaitingConfirmer
from infrastructure.persistence.approval_repository import InMemoryApprovalRepository
from infrastructure.progress.broadcaster import InMemoryProgressBroadcaster


def request(task_id=None) -> ApprovalRequest:
    return ApprovalRequest.create(
        task_id=task_id or uuid4(),
        action="fs.write overwrites report.md",
        risk_level=RiskLevel.HIGH,
        reason="The file already exists.",
    )


async def _park(confirmer: WaitingConfirmer, action: ApprovalRequest) -> asyncio.Task[bool]:
    waiting = asyncio.create_task(confirmer(action))
    for _ in range(100):
        if action.id in {item.id for item in confirmer.pending()}:
            return waiting
        await asyncio.sleep(0)
    raise AssertionError("the confirmer never parked")


async def test_the_call_waits_until_someone_answers() -> None:
    confirmer = WaitingConfirmer()
    action = request()

    waiting = await _park(confirmer, action)
    assert not waiting.done(), "an irreversible action does not proceed unanswered"
    assert [item.id for item in confirmer.pending()] == [action.id]

    assert confirmer.decide(action.id, True)
    assert await asyncio.wait_for(waiting, timeout=1) is True
    assert confirmer.pending() == []


async def test_a_rejection_is_delivered_the_same_way() -> None:
    confirmer = WaitingConfirmer()
    action = request()
    waiting = await _park(confirmer, action)

    confirmer.decide(action.id, False)
    assert await asyncio.wait_for(waiting, timeout=1) is False


async def test_nobody_answering_is_a_refusal_not_a_hang() -> None:
    confirmer = WaitingConfirmer(timeout_seconds=0.01)
    assert await confirmer(request()) is False


async def test_cancelling_the_task_releases_its_questions() -> None:
    confirmer = WaitingConfirmer()
    task_id = uuid4()
    first = await _park(confirmer, request(task_id))
    second = await _park(confirmer, request(task_id))
    elsewhere = await _park(confirmer, request(uuid4()))

    assert confirmer.release(task_id) == 2
    assert await asyncio.wait_for(first, timeout=1) is False
    assert await asyncio.wait_for(second, timeout=1) is False
    assert not elsewhere.done(), "another task's question is not answered for it"

    elsewhere.cancel()


async def test_deciding_a_question_this_process_is_not_holding_says_so() -> None:
    """A row left by a killed run has to be settled somewhere else."""
    confirmer = WaitingConfirmer()
    assert confirmer.decide(uuid4(), True) is False


async def test_the_question_is_announced_so_a_parked_run_does_not_look_hung() -> None:
    progress = InMemoryProgressBroadcaster()
    confirmer = WaitingConfirmer(progress=progress)
    action = request()

    waiting = await _park(confirmer, action)
    announced = progress.recent(action.task_id)
    assert [event.message for event in announced] == [action.action]
    assert announced[0].payload["approval_id"] == str(action.id)

    confirmer.decide(action.id, False)
    await waiting


async def test_the_service_records_what_the_interface_decided() -> None:
    """The whole path: the gate asks, a browser answers, the row says so."""
    repository = InMemoryApprovalRepository()
    confirmer = WaitingConfirmer()
    service = LocalApprovalService(
        repository, mode="prompt", confirmer=confirmer, is_interactive=lambda: True
    )
    action = request()

    asking = asyncio.create_task(service.request(action))
    for _ in range(100):
        if confirmer.pending():
            break
        await asyncio.sleep(0)

    pending = await repository.list_pending()
    assert [item.id for item in pending] == [action.id], "written down before it is answered"

    confirmer.decide(action.id, True)
    assert await asyncio.wait_for(asking, timeout=1) is ApprovalState.APPROVED

    stored = await repository.get(action.id)
    assert stored is not None and stored.state is ApprovalState.APPROVED
    assert await repository.list_pending() == []
