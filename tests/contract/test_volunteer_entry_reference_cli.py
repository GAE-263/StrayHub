from __future__ import annotations

import io
from uuid import uuid4

import pytest
from scripts.issue_volunteer_entry_reference import emit_result


class _Stream(io.StringIO):
    def __init__(self, *, tty: bool) -> None:
        super().__init__()
        self.tty = tty

    def isatty(self) -> bool:
        return self.tty


def test_default_output_never_contains_raw_entry_reference() -> None:
    raw = "entry-sentinel-must-not-be-persisted"
    stdout = _Stream(tty=False)
    stderr = _Stream(tty=False)

    emit_result(uuid4(), raw, reveal=False, stdout=stdout, stderr=stderr, input_fn=lambda _: "")

    assert raw not in stdout.getvalue()
    assert raw not in stderr.getvalue()
    assert '"reference_issued": true' in stdout.getvalue()


def test_explicit_reveal_requires_an_interactive_terminal() -> None:
    raw = "entry-sentinel-must-not-be-persisted"
    stdout = _Stream(tty=False)
    stderr = _Stream(tty=False)

    with pytest.raises(ValueError, match="interactive terminal"):
        emit_result(
            uuid4(), raw, reveal=True, stdout=stdout, stderr=stderr, input_fn=lambda _: "REVEAL"
        )

    assert raw not in stdout.getvalue()
    assert raw not in stderr.getvalue()


def test_explicit_interactive_reveal_requires_confirmation_and_prints_once() -> None:
    raw = "entry-sentinel-shown-once"
    stdout = _Stream(tty=True)
    stderr = _Stream(tty=True)

    emit_result(
        uuid4(), raw, reveal=True, stdout=stdout, stderr=stderr, input_fn=lambda _: "REVEAL"
    )

    assert stdout.getvalue().count(raw) == 1
    assert raw not in stderr.getvalue()


def test_reveal_denial_and_revoke_output_do_not_emit_secret() -> None:
    raw = "entry-sentinel-must-stay-hidden"
    stdout = _Stream(tty=True)
    stderr = _Stream(tty=True)
    emit_result(uuid4(), raw, reveal=True, stdout=stdout, stderr=stderr, input_fn=lambda _: "NO")
    emit_result(
        uuid4(), None, reveal=True, stdout=stdout, stderr=stderr, input_fn=lambda _: "REVEAL"
    )

    assert raw not in stdout.getvalue()
    assert raw not in stderr.getvalue()
