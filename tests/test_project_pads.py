"""Discover starter context and prepare project-pad creation without live
writes.
"""

import json
from pathlib import Path

import httpx
import pytest
import respx
from click.testing import CliRunner
from coderpad.json_types import JsonValue

from coderpad_cli import main


def _pad_payload() -> dict[str, JsonValue]:
    """Provide a complete pad with optional access metadata."""
    return {
        "id": "abcdefgh",
        "title": "Interview",
        "state": "active",
        "owner_email": "owner@example.com",
        "language": "python3",
        "private": False,
        "execution_enabled": False,
        "contents": "",
        "participants": [],
        "events": "",
        "notes": "",
        "created_at": "2026-10-06T12:00:00Z",
        "updated_at": "2026-10-06T12:00:00Z",
        "ended_at": None,
        "url": "https://app.coderpad.io/abcdefgh",
        "playback": "https://app.coderpad.io/abcdefgh/playback",
        "drawing": None,
        "type": "interview",
        "question_ids": [123],
        "pad_environment_ids": [],
        "active_environment_id": None,
        "team": {"id": "team-1", "name": "Backend"},
        "allowed_interviewer_emails": [],
        "restrict_interviewer_access": False,
    }


@pytest.mark.parametrize(argnames="command", argvalues=["list", "get"])
def test_languages(command: str) -> None:
    """Return complete catalog JSON using authenticated GET requests."""
    path = "/api/languages" + ("/multifile_python" if command == "get" else "")
    payload = {"future_metadata": ["starter", None]}
    with respx.mock() as router:
        route = router.get(url="https://app.coderpad.io" + path).mock(
            return_value=httpx.Response(status_code=200, json=payload)
        )
        result = CliRunner().invoke(
            cli=main,
            args=[
                "languages",
                command,
                *(["multifile_python"] if command == "get" else []),
            ],
            env={"CODERPAD_API_KEY": "test-key"},
            catch_exceptions=False,
        )
        assert result.exit_code == 0, result.output
        assert json.loads(s=result.output) == payload
        assert route.calls.last.request.method == "GET"


@pytest.mark.parametrize(
    argnames="source", argvalues=["template", "directory", "file", "question"]
)
@pytest.mark.parametrize(argnames="dry_run", argvalues=[False, True])
def test_create_pad(source: str, *, dry_run: bool, tmp_path: Path) -> None:
    """Creation stages files and dry runs require neither a key nor a
    request.
    """
    project = tmp_path / "project"
    project.mkdir()
    starter = project / "main.py"
    _ = starter.write_bytes(data=b"print(1)\r\n")
    args = ["pads", "create", "--title", "Project"]
    if source == "question":
        args += ["--question-id", "123"]
    else:
        args += [
            "--language",
            "python3" if source == "file" else "multifile_python",
        ]
    if source == "directory":
        args += ["--directory", str(object=project), "--exclude", "*.zip"]
    elif source == "file":
        args += ["--file", str(object=starter)]
    if dry_run:
        args += ["--dry-run"]
    payload = _pad_payload()
    payload.update({"language": None, "contents": None})
    with respx.mock(assert_all_called=not dry_run) as router:
        route = router.post(url="https://app.coderpad.io/api/pads/").mock(
            return_value=httpx.Response(status_code=200, json=payload)
        )
        result = CliRunner().invoke(
            cli=main,
            args=args,
            env={"CODERPAD_API_KEY": "" if dry_run else "test-key"},
            catch_exceptions=False,
        )
        assert result.exit_code == 0, result.output
        value = json.loads(s=result.output)
        if dry_run:
            assert value["dry_run"] is True
            assert not route.called
        else:
            assert value["id"] == "abcdefgh"
            assert value["language"] is None
            request = route.calls.last.request
            if source == "directory":
                assert b"pad[zip_file]" in request.content
            else:
                assert request.method == "POST"


@pytest.mark.parametrize(
    argnames="options",
    argvalues=[
        ["--question-id", "1", "--directory", "."],
        ["--directory", ".", "--file", "starter.py"],
        ["--exclude", "*.zip"],
        ["--language", ""],
        ["--language", " python3 "],
    ],
)
def test_invalid_creation(options: list[str]) -> None:
    """Conflicting sources and malformed options fail before network
    access.
    """
    with respx.mock() as router:
        result = CliRunner().invoke(
            cli=main, args=["pads", "create", *options, "--dry-run"]
        )
        assert result.exit_code != 0
        assert len(router.calls) == 0
