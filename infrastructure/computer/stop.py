"""The brake, as a file.

A run that is clicking on the user's machine needs a way to be stopped by the
user, from outside, at a moment nobody scheduled. The process is busy; it may
have the screen; the terminal that started it may be gone. What is left that
still works is the filesystem.

So: a sentinel path. `kai stop` creates it, `kai stop --clear` removes it, and
every action on a screen reads it first. Its contents are the reason, shown back
to the model and written to the log, which is why the word matters - "stop,
wrong window" tells the employee something that a bare halt does not.

Deliberately a file rather than a signal or a socket: it survives the process it
stops, so a stop the user set while nothing was running still holds when the
next run starts, and Phase 6's interface sets it the same way the CLI does.
"""

from __future__ import annotations

from pathlib import Path

from infrastructure.observability.logging import get_logger

log = get_logger(__name__)

STOP_FILE_NAME = "STOP"
DEFAULT_REASON = "the user asked for computer use to stop"


class FileStopSignal:
    """Implements `domain.computer.protocols.StopSignal`."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._reason = DEFAULT_REASON

    def engaged(self) -> bool:
        try:
            text = self.path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return False
        except OSError as error:
            # An unreadable brake is a brake that is on. The alternative is
            # deciding that an I/O error means "carry on clicking".
            log.warning("computer.stop_file_unreadable", path=str(self.path), error=str(error))
            self._reason = f"the stop file at {self.path} could not be read"
            return True
        self._reason = text or DEFAULT_REASON
        return True

    @property
    def reason(self) -> str:
        return self._reason

    # --- Setting and clearing -------------------------------------------------

    def engage(self, reason: str = "") -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(reason.strip() or DEFAULT_REASON, encoding="utf-8")
        log.warning("computer.stop_engaged", path=str(self.path), reason=reason)
        return self.path

    def release(self) -> bool:
        try:
            self.path.unlink()
        except FileNotFoundError:
            return False
        log.info("computer.stop_released", path=str(self.path))
        return True


class NoStopSignal:
    """Implements `domain.computer.protocols.StopSignal`. Never engaged.

    For the surfaces and the tests where there is nothing to brake.
    """

    def engaged(self) -> bool:
        return False

    @property
    def reason(self) -> str:
        return ""
