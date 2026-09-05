"""The composition root: settings, adapters and the runtime meet here.

`infrastructure/container.py` builds adapters and knows nothing above itself.
Assembling the employee runtime needs both `application` and `infrastructure`,
and this is the one place allowed to see both - which is what a composition root
is for. See docs/adr/0001.
"""

from __future__ import annotations

from app.config.settings import Settings, get_settings
from application.employee_runtime.approvals import ApprovalGate
from application.employee_runtime.executor import Executor
from application.employee_runtime.planner import Planner
from application.employee_runtime.runtime import EmployeeRuntime, RuntimeDependencies
from application.employee_runtime.verifier import Verifier
from application.task_runner import TaskRunner
from domain.employees.definition import EmployeeDefinition
from infrastructure.container import Container


def build_container(settings: Settings | None = None, *, in_memory: bool = False) -> Container:
    return Container(settings or get_settings(), in_memory=in_memory)


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
            ),
            verifier=Verifier(container.llm_for(*Verifier.routing())),
            tasks=container.task_repository,
            tools=container.tool_registry,
            limits=definition.limits,
            system_prompt=definition.system_prompt,
        ),
    )


def build_task_runner(container: Container) -> TaskRunner:
    async def _runtime(definition: EmployeeDefinition) -> EmployeeRuntime:
        return await build_runtime(container, definition)

    return TaskRunner(
        tasks=container.task_repository,
        assignments=container.assignment_repository,
        registry=container.employee_registry,
        build_runtime=_runtime,
    )
