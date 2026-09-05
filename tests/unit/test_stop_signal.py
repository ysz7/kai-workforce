"""The brake, and the one thing that must never happen: a stop that is not seen."""

from __future__ import annotations

from pathlib import Path

import pytest

from domain.computer.constraints import ComputerConstraints
from domain.errors import StopRequestedError
from infrastructure.computer.guarded import GuardedComputer
from infrastructure.computer.stop import FileStopSignal, NoStopSignal
from tests.fakes.computer import FakeComputer


def test_no_file_means_no_stop(tmp_path: Path) -> None:
    assert not FileStopSignal(tmp_path / "STOP").engaged()


def test_engaging_it_carries_the_users_words_to_the_employee(tmp_path: Path) -> None:
    signal = FileStopSignal(tmp_path / "STOP")

    signal.engage("stop, that is the wrong window")

    assert signal.engaged()
    assert signal.reason == "stop, that is the wrong window"


def test_an_empty_stop_file_still_stops(tmp_path: Path) -> None:
    path = tmp_path / "STOP"
    path.write_text("   ", encoding="utf-8")

    signal = FileStopSignal(path)

    assert signal.engaged()
    assert signal.reason


def test_an_unreadable_brake_is_a_brake_that_is_on(tmp_path: Path) -> None:
    """The alternative is deciding an I/O error means "carry on clicking"."""
    directory = tmp_path / "STOP"
    directory.mkdir()

    signal = FileStopSignal(directory)

    assert signal.engaged()
    assert "could not be read" in signal.reason


def test_releasing_it_says_whether_there_was_anything_to_release(tmp_path: Path) -> None:
    signal = FileStopSignal(tmp_path / "STOP")

    assert signal.release() is False
    signal.engage()
    assert signal.release() is True
    assert not signal.engaged()


def test_a_stop_set_while_nothing_was_running_still_holds(tmp_path: Path) -> None:
    """It is a file so that it survives the process it was meant to stop."""
    path = tmp_path / "STOP"
    FileStopSignal(path).engage("wait")

    assert FileStopSignal(path).engaged()


async def test_the_guard_reads_the_file_before_every_action(tmp_path: Path) -> None:
    signal = FileStopSignal(tmp_path / "STOP")
    computer = FakeComputer()
    guard = GuardedComputer(
        computer, ComputerConstraints(applies_to_applications=False), stop_signal=signal
    )

    await guard.click(1, 1)
    signal.engage("enough")

    with pytest.raises(StopRequestedError, match="enough"):
        await guard.click(2, 2)
    assert computer.names() == ["click"]


def test_the_null_brake_is_never_on() -> None:
    assert not NoStopSignal().engaged()
