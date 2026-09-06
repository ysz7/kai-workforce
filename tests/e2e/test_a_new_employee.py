"""Phase 8's Definition of Done: adding an employee is adding a directory.

*`git diff` after adding an employee contains only `employees/<name>/**`.*

That is a claim about the whole platform, and it is checked here the only way
that means anything: by adding one - in a temporary directory, with no import,
no registration and no edit to anything - and then having KAI find it, choose
it for work that suits it, and run it.

The declaration below is written out in full on purpose. It is the entire
change. If this test ever needs a line of Python added somewhere else to pass,
the Definition of Done has been broken and this is where it shows.
"""

from __future__ import annotations

import json
from pathlib import Path

from application.kai.delegation import CapabilityDelegator
from application.kai.intent import IntentReader
from application.kai.manager import KaiManager
from application.kai.planner import ObjectivePlanner
from application.kai.supervisor import Supervisor
from application.kai.synthesis import Synthesizer
from application.kai.verification import ObjectiveVerifier
from domain.capabilities.models import Capability, CapabilityRequirement
from domain.workforce.protocols import ObjectiveStatus
from infrastructure.employees.yaml_registry import YamlEmployeeRegistry
from infrastructure.persistence.objective_repository import InMemoryObjectiveRepository
from infrastructure.persistence.plan_repository import InMemoryPlanRepository
from tests.fakes.llm import FakeLLM, reply
from tests.fakes.workforce import RecordingExecution

#: A new employee, entire. Nothing else about it exists anywhere.
TRANSLATOR = """
name: translator
role: Translator
role_description: >
  Turns a document from one language into another, keeping what it says.

goals:
  - text: Say what the original says, not what it would have said in the target language.
    priority: 1

allowed_tools:
  - fs.read
  - fs.write

capabilities:
  - FILE_ACCESS

model_profile:
  capabilities: [TEXT_REASONING, LONG_CONTEXT]
  temperature: 0.1

limits:
  max_steps: 8
  max_cost_usd: 0.50
  max_wall_time_seconds: 300
"""

ANALYST = """
name: number-cruncher
role: Number Cruncher
role_description: Computes answers from data that is already on this machine.
allowed_tools: [fs.read, code.run]
capabilities: [CODE, FILE_ACCESS]
model_profile:
  capabilities: [TEXT_REASONING, CODE]
"""


def declare(root: Path, name: str, body: str, *, prompt: str = "") -> Path:
    """Everything adding an employee consists of."""
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "employee.yaml").write_text(body, encoding="utf-8")
    if prompt:
        (directory / "prompts").mkdir()
        (directory / "prompts" / "system.md").write_text(prompt, encoding="utf-8")
    return directory


def manager_for(registry, llm: FakeLLM, execution: RecordingExecution) -> KaiManager:
    return KaiManager(
        intent=IntentReader(llm),
        planner=ObjectivePlanner(llm),
        supervisor=Supervisor(
            execution=execution,
            delegator=CapabilityDelegator(llm, registry),
            max_attempts=1,
        ),
        verifier=ObjectiveVerifier(llm),
        synthesizer=Synthesizer(llm),
        registry=registry,
        objectives=InMemoryObjectiveRepository(),
        plans=InMemoryPlanRepository(),
    )


# --- Discovery ----------------------------------------------------------------


def test_a_declared_directory_is_all_it_takes_to_exist(tmp_path: Path) -> None:
    declare(tmp_path, "translator", TRANSLATOR, prompt="You translate. Keep the meaning.")

    registry = YamlEmployeeRegistry(tmp_path)
    translator = registry.get("translator")

    assert translator.role.title == "Translator"
    assert translator.allowed_tools == frozenset({"fs.read", "fs.write"})
    assert translator.capabilities == frozenset({Capability.FILE_ACCESS})
    assert translator.system_prompt.startswith("You translate")
    assert [d.name for d in registry.list()] == ["translator"]


def test_it_is_found_by_the_work_it_says_it_can_do(tmp_path: Path) -> None:
    declare(tmp_path, "translator", TRANSLATOR)
    declare(tmp_path, "number-cruncher", ANALYST)
    registry = YamlEmployeeRegistry(tmp_path)

    needs_code = registry.find_by_capability(
        CapabilityRequirement(required=frozenset({Capability.CODE}))
    )
    needs_files = registry.find_by_capability(
        CapabilityRequirement(required=frozenset({Capability.FILE_ACCESS}))
    )

    assert [d.name for d in needs_code] == ["number-cruncher"]
    assert [d.name for d in needs_files] == ["number-cruncher", "translator"]


def test_the_closest_fit_is_ranked_first(tmp_path: Path) -> None:
    """Both qualify; the one that also offers what was preferred comes first."""
    declare(tmp_path, "translator", TRANSLATOR)
    declare(tmp_path, "number-cruncher", ANALYST)
    registry = YamlEmployeeRegistry(tmp_path)

    ranked = registry.find_by_capability(
        CapabilityRequirement(
            required=frozenset({Capability.FILE_ACCESS}),
            preferred=frozenset({Capability.CODE}),
        )
    )

    assert [d.name for d in ranked] == ["number-cruncher", "translator"]


# --- KAI uses it, with no edit to KAI -----------------------------------------


async def test_kai_gives_work_to_a_newly_declared_employee(tmp_path: Path) -> None:
    declare(tmp_path, "translator", TRANSLATOR)
    registry = YamlEmployeeRegistry(tmp_path)
    execution = RecordingExecution()
    llm = FakeLLM(
        [
            reply(json.dumps({"restatement": "translate it", "needs_work": True,
                              "acceptance_criteria": ["the file is in French"]})),
            reply(json.dumps({"tasks": [{"id": "t1", "goal": "Translate notes.md into French",
                                         "needs": ["FILE_ACCESS"]}]})),
            reply(json.dumps({"passed": True, "reason": "done"})),
            reply("notes.md is now in French."),
        ]
    )
    manager = manager_for(registry, llm, execution)

    objective = await manager.receive("Put my notes into French")
    result = await manager.handle_objective(objective)

    assert result.status is ObjectiveStatus.DONE
    assert execution.employees == [registry.get("translator").id]
    assert result.output["tasks"][0]["employee"] == "translator"


async def test_the_work_goes_to_whoever_declares_what_it_needs(tmp_path: Path) -> None:
    """Two employees, and the capability decides - with no model call to choose.

    This is the whole of what a declared capability buys: the field narrows to
    one, and the manager spends nothing being told what was already true.
    """
    declare(tmp_path, "translator", TRANSLATOR)
    declare(tmp_path, "number-cruncher", ANALYST)
    registry = YamlEmployeeRegistry(tmp_path)
    execution = RecordingExecution()
    llm = FakeLLM(
        [
            reply(json.dumps({"restatement": "count them", "needs_work": True,
                              "acceptance_criteria": ["a number"]})),
            reply(json.dumps({"tasks": [{"id": "t1", "goal": "Compute the totals in sales.csv",
                                         "needs": ["CODE"]}]})),
            reply(json.dumps({"passed": True, "reason": "done"})),
            reply("The total is 41."),
        ]
    )
    manager = manager_for(registry, llm, execution)

    result = await manager.handle_objective(await manager.receive("Total up my sales"))

    assert result.status is ObjectiveStatus.DONE
    assert result.output["tasks"][0]["employee"] == "number-cruncher"
    # Four calls: read the request, plan it, verify it, write the answer. None
    # of them was "who should do this".
    assert llm.call_count == 4


async def test_a_capability_nobody_declares_falls_back_to_the_whole_workforce(
    tmp_path: Path,
) -> None:
    """A missing declaration is usually the fault, and it must not stop the work."""
    declare(tmp_path, "translator", TRANSLATOR)
    registry = YamlEmployeeRegistry(tmp_path)
    execution = RecordingExecution()
    llm = FakeLLM(
        [
            reply(json.dumps({"restatement": "look it up", "needs_work": True,
                              "acceptance_criteria": ["an answer"]})),
            reply(json.dumps({"tasks": [{"id": "t1", "goal": "Look up the exchange rate",
                                         "needs": ["WEB_BROWSING"]}]})),
            reply(json.dumps({"passed": True, "reason": "done"})),
            reply("It is 1.08."),
        ]
    )
    manager = manager_for(registry, llm, execution)

    result = await manager.handle_objective(await manager.receive("What is the rate?"))

    assert result.status is ObjectiveStatus.DONE
    assert result.output["tasks"][0]["employee"] == "translator"


# --- And the shipped workforce is discoverable the same way -------------------


def test_the_shipped_employees_are_each_findable_by_what_they_do() -> None:
    """The four that ship, found by capability rather than by name."""
    root = Path(__file__).resolve().parents[2] / "employees"
    registry = YamlEmployeeRegistry(root)

    def names(*capabilities: Capability) -> list[str]:
        return [
            d.name
            for d in registry.find_by_capability(
                CapabilityRequirement(required=frozenset(capabilities))
            )
        ]

    assert names(Capability.CODE) == ["analyst"]
    assert names(Capability.COMPUTER_USE) == ["operator"]
    assert "researcher" in names(Capability.WEB_BROWSING)
    assert set(names(Capability.FILE_ACCESS)) == {
        "analyst",
        "operator",
        "organizer",
        "researcher",
    }
