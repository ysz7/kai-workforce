"""The English-only rule is enforced, not merely stated."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_checker() -> ModuleType:
    """Load the standalone script by path; it is not an importable package."""
    spec = importlib.util.spec_from_file_location(
        "check_english_only", REPO_ROOT / "scripts" / "check_english_only.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scan = _load_checker().scan


def test_latin_source_passes(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text('log.info("task.completed", cost_usd=0.01)\n', encoding="utf-8")
    assert scan(tmp_path) == []


def test_non_latin_identifier_is_reported(tmp_path: Path) -> None:
    # Written as escapes so this test file stays Latin-only and passes its own check.
    cyrillic = "\u0433\u043e\u0442\u043e\u0432\u043e"
    (tmp_path / "bad.py").write_text(f'STATUS = "{cyrillic}"\n', encoding="utf-8")
    violations = scan(tmp_path)
    assert len(violations) == 1
    assert violations[0][0] == Path("bad.py")


def test_unscanned_file_types_are_left_alone(tmp_path: Path) -> None:
    (tmp_path / "data.txt").write_text("\u043e\u0442\u0447\u0451\u0442\n", encoding="utf-8")
    assert scan(tmp_path) == [], "runtime data may be in any language"
