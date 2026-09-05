"""Running generated code: what it can do, and what it is stopped from doing."""

from __future__ import annotations

from domain.policies.models import RiskLevel
from infrastructure.tools.code import CodeExecutionTool


async def test_a_program_runs_and_its_output_comes_back() -> None:
    result = await CodeExecutionTool().execute({"code": "print(6 * 7)"})

    assert result.success
    assert result.output["stdout"].strip() == "42"
    assert result.output["exit_code"] == 0


async def test_a_program_that_fails_reports_the_traceback_instead_of_raising() -> None:
    result = await CodeExecutionTool().execute({"code": "raise ValueError('nope')"})

    assert not result.success
    assert "ValueError" in result.output["stderr"]


async def test_a_runaway_program_is_stopped() -> None:
    result = await CodeExecutionTool(timeout_seconds=2).execute({"code": "while True: pass"})

    assert not result.success
    assert "stopped after" in result.error


async def test_the_environment_is_not_inherited(monkeypatch) -> None:
    """A key on this machine must not be readable by code the model wrote."""
    monkeypatch.setenv("KAI_LLM_API_KEY", "sk-do-not-leak")

    result = await CodeExecutionTool().execute(
        {"code": "import os; print(list(os.environ.keys()))"}
    )

    assert "KAI_LLM_API_KEY" not in result.output["stdout"]


async def test_output_is_truncated_rather_than_flooding_the_context() -> None:
    result = await CodeExecutionTool().execute({"code": "print('x' * 100000)"})

    assert result.success
    assert "truncated" in result.output["stdout"]
    assert len(result.output["stdout"]) < 25_000


async def test_each_run_gets_an_empty_directory_of_its_own() -> None:
    tool = CodeExecutionTool()

    first = await tool.execute({"code": "open('left-behind.txt', 'w').write('x')"})
    second = await tool.execute({"code": "import os; print(os.listdir('.'))"})

    assert first.success
    assert "left-behind.txt" not in second.output["stdout"]


def test_running_code_always_needs_a_person() -> None:
    """Isolation here is limits, not a kernel boundary - so a human confirms."""
    spec = CodeExecutionTool().spec

    assert spec.reversible is False
    assert spec.risk_level is RiskLevel.HIGH


async def test_a_call_with_no_code_is_reported_to_the_model() -> None:
    result = await CodeExecutionTool().execute({})

    assert not result.success
    assert "code" in result.error
