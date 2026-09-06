"""The composition root: settings, adapters and the runtime meet here.

`infrastructure/container.py` builds adapters and knows nothing above itself.
Assembling the employee runtime needs both `application` and `infrastructure`,
and this is the one place allowed to see both - which is what a composition root
is for. See docs/adr/0001.
"""

from __future__ import annotations

from app.config.settings import Settings, get_settings
from application.computer.screen_reader import LLMScreenReader
from application.employee_runtime.approvals import ApprovalGate
from application.employee_runtime.executor import Executor
from application.employee_runtime.planner import Planner
from application.employee_runtime.runtime import EmployeeRuntime, RuntimeDependencies
from application.employee_runtime.verifier import Verifier
from application.kai.delegation import CapabilityDelegator
from application.kai.intent import IntentReader
from application.kai.manager import KaiManager
from application.kai.planner import ObjectivePlanner
from application.kai.supervisor import Supervisor
from application.kai.synthesis import Synthesizer
from application.kai.verification import ObjectiveVerifier
from application.task_runner import TaskRunner
from domain.employees.definition import EmployeeDefinition
from infrastructure.container import Container


def build_container(settings: Settings | None = None, *, in_memory: bool = False) -> Container:
    """Build the container, and hand it the one dependency it cannot build.

    Reading a screen needs an application component (`LLMScreenReader`) and a
    model that only the container can route to. Neither layer may reach the
    other, so the wire is made here and passed as a callable: nothing is built,
    and no model is routed, for a run that never looks at a screen.
    """
    container = Container(settings or get_settings(), in_memory=in_memory)
    container.use_screen_reader(
        lambda: LLMScreenReader(container.llm_for(*LLMScreenReader.routing()))
    )
    return container


async def build_runtime(container: Container, definition: EmployeeDefinition) -> EmployeeRuntime:
    """Assemble the one runtime for a given employee declaration.

    Every employee gets the same three stages and the same loop. What differs is
    the declaration passed in: role, goals, tools, model profile, limits.
    """
    return EmployeeRuntime(
        definition,
        RuntimeDependencies(
            planner=Planner(container.llm_for(*Planner.routing())),
            executor=Executor(
                container.llm_for(*Executor.routing(definition)),
                container.tool_registry,
                limits=definition.limits,
                approvals=ApprovalGate(container.approval_service),
                call_log=container.tool_call_log,
                progress=container.progress,
                cancellation=container.cancellations,
            ),
            verifier=Verifier(container.llm_for(*Verifier.routing())),
            tasks=container.task_repository,
            tools=container.tool_registry,
            limits=definition.limits,
            system_prompt=definition.system_prompt,
            progress=container.progress,
        ),
    )


def build_manager(container: Container) -> KaiManager:
    """Assemble KAI.

    Five model-facing components, each routed for what it is: comprehension and
    decomposition get a good model, choosing from a short list gets a cheap one,
    the answer the user reads gets a good one again. None of them names a model,
    and none of them names an employee - the workforce arrives from the registry
    and the work is done through `TaskExecution`, which is the task runner.
    """
    registry = container.employee_registry
    return KaiManager(
        intent=IntentReader(container.llm_for(*IntentReader.routing())),
        planner=ObjectivePlanner(container.llm_for(*ObjectivePlanner.routing())),
        supervisor=Supervisor(
            execution=build_task_runner(container),
            delegator=CapabilityDelegator(
                container.llm_for(*CapabilityDelegator.routing()), registry
            ),
            progress=container.progress,
        ),
        verifier=ObjectiveVerifier(container.llm_for(*ObjectiveVerifier.routing())),
        synthesizer=Synthesizer(container.llm_for(*Synthesizer.routing())),
        registry=registry,
        objectives=container.objective_repository,
        plans=container.plan_repository,
        progress=container.progress,
    )


def build_task_runner(container: Container) -> TaskRunner:
    async def _runtime(definition: EmployeeDefinition) -> EmployeeRuntime:
        return await build_runtime(container, definition)

    return TaskRunner(
        tasks=container.task_repository,
        assignments=container.assignment_repository,
        registry=container.employee_registry,
        build_runtime=_runtime,
        progress=container.progress,
    )
