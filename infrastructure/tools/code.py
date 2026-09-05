"""Running code the employee wrote, with the brakes on.

What isolation means here is stated plainly, because a tool called "sandbox"
that is not one is worse than no tool. The child is a normal OS process; what it
gets is:

* a scratch directory of its own as the working directory, thrown away after;
* a stripped environment - no inherited variables, so a provider key on this
  machine cannot be read by generated code and printed into a transcript;
* wall-clock, CPU, memory and output caps, so a runaway loop stops on its own;
* `-I`, so nothing from the user's site-packages or PYTHONPATH is importable.

What it does not get is a kernel boundary. The process can still reach the
network and the filesystem, which is why the tool is declared irreversible and
every run goes through the approval gate. A container or VM backend is the
Phase 10 upgrade, and it slots in behind the same `ToolSpec`.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

from domain.capabilities.models import Capability
from domain.policies.models import RiskLevel
from domain.tools.models import ToolResult, ToolSpec
from domain.tools.schema import Param
from infrastructure.observability.logging import get_logger

log = get_logger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_TIMEOUT_SECONDS = 300.0
#: Output beyond this is truncated: the model has to read it, and a script that
#: prints a megabyte has already told us what went wrong in the first lines.
MAX_OUTPUT_CHARS = 20_000
DEFAULT_MEMORY_MB = 512


def _limits(memory_mb: int, cpu_seconds: int):
    """Per-process resource caps, applied in the child before it runs anything."""

    def apply() -> None:  # pragma: no cover - runs in the forked child
        import contextlib
        import resource

        limit_bytes = memory_mb * 1024 * 1024
        caps = ((resource.RLIMIT_AS, limit_bytes), (resource.RLIMIT_DATA, limit_bytes),
                (resource.RLIMIT_CPU, cpu_seconds))
        for kind, value in caps:
            # A platform that will not take one of these still gets the others,
            # and the wall-clock timeout applies everywhere regardless.
            with contextlib.suppress(ValueError, OSError):
                resource.setrlimit(kind, (value, value))

    return apply


class CodeExecutionTool:
    """Implements `domain.tools.protocols.Tool`.

    Not built on `BaseTool`: the timing, the truncation and the temporary
    directory are all specific to running a subprocess, and inheriting the
    generic wrapper would only hide where the failure came from.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        memory_mb: int = DEFAULT_MEMORY_MB,
        interpreter: str | None = None,
    ) -> None:
        self._timeout = min(timeout_seconds, MAX_TIMEOUT_SECONDS)
        self._memory_mb = memory_mb
        self._interpreter = interpreter or sys.executable
        self._spec = ToolSpec.of(
            "code.run",
            "Run a short Python program and get back what it printed. The program "
            "runs in an empty scratch directory with no access to your environment, "
            "and is stopped if it takes too long. Needs the user's confirmation.",
            Param("code", description="The Python source to run. Print what you need to see."),
            Param(
                "timeout_seconds",
                type="integer",
                required=False,
                default=int(DEFAULT_TIMEOUT_SECONDS),
                description="How long it may run before being stopped.",
            ),
            risk_level=RiskLevel.HIGH,
            capabilities=frozenset({Capability.CODE}),
            reversible=False,
        )

    @property
    def spec(self) -> ToolSpec:
        return self._spec

    async def execute(self, input_data: dict[str, object]) -> ToolResult:
        from domain.errors import DomainError

        try:
            arguments = self._spec.parameters.validate(input_data)
        except DomainError as error:
            return ToolResult.failure(str(error))

        source = str(arguments["code"])
        timeout = min(float(arguments.get("timeout_seconds", self._timeout)), self._timeout)
        directory = Path(tempfile.mkdtemp(prefix="kai-code-"))
        try:
            return await self._run(source, directory, timeout)
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    async def _run(self, source: str, directory: Path, timeout: float) -> ToolResult:
        script = directory / "main.py"
        script.write_text(source, encoding="utf-8")

        # A minimal environment, built rather than filtered: a deny-list of
        # variable names is one new secret away from being out of date.
        environment = {
            "PATH": os.defpath,
            "HOME": str(directory),
            "TMPDIR": str(directory),
            "LANG": "C.UTF-8",
            "PYTHONIOENCODING": "utf-8",
        }
        kwargs = {}
        if os.name == "posix":
            kwargs["preexec_fn"] = _limits(self._memory_mb, int(timeout) + 1)

        process = await asyncio.create_subprocess_exec(
            self._interpreter,
            "-I",
            "-B",
            str(script),
            cwd=directory,
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **kwargs,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError:
            process.kill()
            await process.wait()
            log.warning("code.timeout", timeout_seconds=timeout)
            return ToolResult.failure(
                f"The program was stopped after {timeout:.0f} seconds without finishing."
            )

        return ToolResult(
            success=process.returncode == 0,
            output={
                "stdout": _clip(stdout),
                "stderr": _clip(stderr),
                "exit_code": process.returncode,
            },
            error=None if process.returncode == 0 else f"exited with {process.returncode}",
        )


def _clip(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace")
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS] + f"\n... [truncated, {len(text)} characters total]"
