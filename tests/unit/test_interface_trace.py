"""Phase 5's Definition of Done: the trace says which level was used, and why.

Not a log line for its own sake. "Why did it click on a picture of a button
instead of calling something" is the first question anyone asks of a run that
went wrong, and it has to be answerable afterwards, from stored data, without
re-deriving it from a declaration that may since have changed.
"""

from __future__ import annotations

from application.employee_runtime.executor import Executor
from application.employee_runtime.transcript import Transcript
from domain.computer.interfaces import InterfaceLevel
from domain.llm.models import ToolCallRequest
from domain.tasks.task import Task
from infrastructure.persistence.tool_call_repository import InMemoryToolCallLog
from infrastructure.tools.registry import InMemoryToolRegistry
from tests.fakes.employees import definition
from tests.fakes.llm import FakeLLM, reply, tool_reply
from tests.fakes.tools import FakeTool


def a_run(*tools: FakeTool, calls: tuple[ToolCallRequest, ...]):
    task = Task.create("Get it done")
    employee = definition(tools=frozenset(tool.spec.name for tool in tools))
    llm = FakeLLM([tool_reply(*calls), reply("Done.")])
    log = InMemoryToolCallLog()
    executor = Executor(llm, InMemoryToolRegistry(list(tools)), call_log=log)
    transcript = Transcript(
        messages=Executor.opening_messages(task, employee, None, "be useful")
    )
    return task, employee, executor, transcript, log


async def test_every_call_is_stored_with_the_level_it_reached_the_world_at() -> None:
    screen = FakeTool("computer.click", interface_level=InterfaceLevel.COMPUTER_USE)
    files = FakeTool("fs.read")
    task, employee, executor, transcript, log = a_run(
        screen,
        files,
        calls=(
            ToolCallRequest(id="c1", name="fs.read", arguments={}),
            ToolCallRequest(id="c2", name="computer.click", arguments={}),
        ),
    )

    await executor.run(task, employee, transcript)

    assert [(c.tool, c.interface) for c in log.calls] == [
        ("fs.read", InterfaceLevel.API),
        ("computer.click", InterfaceLevel.COMPUTER_USE),
    ]


async def test_the_observation_of_a_step_carries_the_level_too() -> None:
    """The transcript is what a resumed run reads, and what a person reads first."""
    screen = FakeTool("desktop.click", interface_level=InterfaceLevel.DESKTOP)
    task, employee, executor, transcript, _ = a_run(
        screen, calls=(ToolCallRequest(id="c1", name="desktop.click", arguments={}),)
    )

    outcome = await executor.run(task, employee, transcript)

    assert outcome.transcript.observations[0].details["interface"] == "DESKTOP"


async def test_an_employee_with_a_choice_is_told_the_order_it_is_judged_against() -> None:
    employee = definition(tools=frozenset({"browser.open", "computer.click"}))
    registry = InMemoryToolRegistry(
        [
            FakeTool("browser.open", interface_level=InterfaceLevel.BROWSER),
            FakeTool("computer.click", interface_level=InterfaceLevel.COMPUTER_USE),
        ]
    )

    messages = Executor.opening_messages(
        Task.create("Do it"),
        employee,
        None,
        "You operate screens.",
        interfaces=tuple(
            spec.interface_level for spec in registry.list_specs(employee)
        ),
    )

    assert "BROWSER then COMPUTER_USE" in messages[0].content


async def test_an_employee_with_one_way_in_is_not_lectured_about_a_hierarchy() -> None:
    employee = definition(tools=frozenset({"fs.read"}))

    messages = Executor.opening_messages(
        Task.create("Do it"), employee, None, "You read files.",
        interfaces=(InterfaceLevel.API,),
    )

    assert "best first" not in messages[0].content
