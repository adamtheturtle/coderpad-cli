"""Inspect real SDK responses without modifying remote resources."""

import json
from collections.abc import Sequence

import httpx
import pytest
import respx
from click.testing import CliRunner

from coderpad_cli import main

type JSONValue = (
    bool | int | float | str | list[JSONValue] | dict[str, JSONValue] | None
)

_QUESTION_URL = "https://app.coderpad.io/api/questions/123456"
_USER_URL = "https://app.coderpad.io/api/user"
_SCREEN_US = "https://screen.coderpad.io/assessment/api/v1.1/campaigns"
_SCREEN_EU = "https://www.codingame.eu/assessment/api/v1.1/campaigns"
_INTERVIEW_KEY = "synthetic-interview-key"
_SCREEN_KEY = "synthetic-screen-key"


def _question() -> dict[str, JSONValue]:
    """A synthetic project question with an empty file and a removed
    file.
    """
    return {
        "id": 123456,
        "title": "Project",
        "owner_email": "owner@example.com",
        "language": "multifile_python",
        "candidate_instructions": [],
        "shared": True,
        "used": 0,
        "take_home": False,
        "test_cases_enabled": False,
        "pad_type": "live",
        "is_draft": False,
        "author_name": "Example",
        "organization_name": "Example",
        "custom_files": [],
        "contents": None,
        "created_at": "2026-10-29T10:00:00Z",
        "updated_at": "2026-10-29T10:00:00Z",
        "file_contents": [
            {"path": "src/main.py", "contents": "π = 3\r\n", "hidden": True},
            {"path": "empty.py", "contents": ""},
            {"path": "removed.py", "deleted": True},
        ],
        "question_variants": [
            {
                "id": 7,
                "language": None,
                "project_template_id": 79,
                "project_template_slug": "multifile_python",
                "display": "Python Project",
            }
        ],
    }


def _object(text: str) -> dict[str, JSONValue]:
    """Parse command JSON into a typed object."""
    return dict[str, JSONValue](json.loads(s=text))


def test_question_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """Question GET retains text, hidden/deleted flags, and template
    summaries.
    """
    monkeypatch.setenv(name="CODERPAD_API_KEY", value=_INTERVIEW_KEY)
    with respx.mock() as router:
        route = router.get(url=_QUESTION_URL).respond(json=_question())
        result = CliRunner().invoke(
            cli=main,
            args=["questions", "get", "123456"],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    assert result.stderr == ""
    output = _object(text=result.stdout)
    files = output["file_contents"]
    assert isinstance(files, list)
    first, empty, removed = files
    assert isinstance(first, dict)
    assert first["contents"] == "π = 3\r\n"
    assert first["hidden"] is True
    assert isinstance(empty, dict)
    assert empty["contents"] == ""
    assert isinstance(removed, dict)
    assert removed["deleted"] is True
    assert removed["contents"] is None
    variants = output["question_variants"]
    assert isinstance(variants, list)
    variant = variants[0]
    assert isinstance(variant, dict)
    assert variant["project_template_slug"] == "multifile_python"
    request = route.calls.last.request
    assert (
        request.headers["Authorization"] == f'Token token="{_INTERVIEW_KEY}"'
    )
    assert "API-Key" not in request.headers
    assert request.content == b""


def test_user_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """The available key-owner identity preserves a false capability."""
    monkeypatch.setenv(name="CODERPAD_API_KEY", value=_INTERVIEW_KEY)
    payload = {
        "name": "Ada",
        "analytics_id": "anonymous",
        "allow_pad_creation": False,
    }
    with respx.mock() as router:
        route = router.get(url=_USER_URL).respond(json=payload)
        result = CliRunner().invoke(
            cli=main, args=["user", "get"], catch_exceptions=False
        )
    assert result.exit_code == 0
    assert _object(text=result.stdout) == payload
    assert result.stderr == ""
    assert route.calls.last.request.content == b""


@pytest.mark.parametrize(argnames="region", argvalues=["us", "eu"])
@pytest.mark.parametrize(argnames="operation", argvalues=["list", "get"])
def test_screen_reads(
    region: str, operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both regions use Screen credentials without requiring an Interview
    key.
    """
    monkeypatch.delenv(name="CODERPAD_API_KEY", raising=False)
    monkeypatch.setenv(name="CODERPAD_SCREEN_API_KEY", value=_SCREEN_KEY)
    url = _SCREEN_EU if region == "eu" else _SCREEN_US
    arguments = ["screen", "campaigns", operation]
    payload: JSONValue
    if operation == "get":
        url += "/121"
        arguments.append("121")
        payload = {
            "id": 121,
            "name": "Assessment",
            "team_id": "example-team",
            "questions": [{"type": "QUESTION", "question_id": "question-id"}],
            "settings": {
                "ai_assist_enabled": False,
                "enabled_coding_agents": "",
            },
        }
    else:
        payload = [{"id": 121, "name": "Assessment"}]
    with respx.mock() as router:
        route = router.get(url=url).respond(json=payload)
        result = CliRunner().invoke(
            cli=main,
            args=[*arguments, "--region", region],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    assert result.stderr == ""
    if operation == "get":
        settings = _object(text=result.stdout)["settings"]
        assert isinstance(settings, dict)
        assert settings["ai_assist_enabled"] is False
        assert settings["enabled_coding_agents"] == ""
    else:
        assert json.loads(s=result.stdout)[0]["name"] == "Assessment"
    request = route.calls.last.request
    assert request.headers["API-Key"] == _SCREEN_KEY
    assert "Authorization" not in request.headers
    assert request.content == b""


@pytest.mark.parametrize(argnames="key", argvalues=[None, "", " \t"])
@pytest.mark.parametrize(
    argnames=("arguments", "environment"),
    argvalues=[
        (["user", "get"], "CODERPAD_API_KEY"),
        (["screen", "campaigns", "list"], "CODERPAD_SCREEN_API_KEY"),
    ],
)
def test_missing_keys(
    arguments: list[str],
    environment: str,
    key: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing keys fail locally even when the other product has a key."""
    monkeypatch.setenv(name="CODERPAD_API_KEY", value=_INTERVIEW_KEY)
    monkeypatch.setenv(name="CODERPAD_SCREEN_API_KEY", value=_SCREEN_KEY)
    if key is None:
        monkeypatch.delenv(name=environment)
    else:
        monkeypatch.setenv(name=environment, value=key)
    with respx.mock() as router:
        result = CliRunner().invoke(
            cli=main, args=arguments, catch_exceptions=False
        )
        assert router.calls.call_count == 0
    assert result.exit_code != 0
    assert environment in result.stderr
    assert _INTERVIEW_KEY not in result.output
    assert _SCREEN_KEY not in result.output


@pytest.mark.parametrize(
    argnames="arguments",
    argvalues=[
        ["questions", "get", "0"],
        ["questions", "get", "not-an-id"],
        ["screen", "campaigns", "get", "0"],
        ["screen", "campaigns", "list", "--region", "invalid"],
    ],
)
def test_invalid_read_arguments(arguments: list[str]) -> None:
    """Invalid identities and regions fail before any request."""
    with respx.mock() as router:
        result = CliRunner().invoke(
            cli=main, args=arguments, catch_exceptions=False
        )
        assert router.calls.call_count == 0
    assert result.exit_code != 0


@pytest.mark.parametrize(
    argnames=("arguments", "url", "malformed"),
    argvalues=[
        (
            ["questions", "get", "123456"],
            _QUESTION_URL,
            {"id": _INTERVIEW_KEY},
        ),
        (["user", "get"], _USER_URL, {"name": _INTERVIEW_KEY}),
        (
            ["screen", "campaigns", "get", "121"],
            _SCREEN_US + "/121",
            {"id": _SCREEN_KEY},
        ),
        (["screen", "campaigns", "list"], _SCREEN_US, [{"name": _SCREEN_KEY}]),
    ],
)
@pytest.mark.parametrize(
    argnames="response_kind", argvalues=["malformed", "http", "transport"]
)
def test_read_errors(
    arguments: Sequence[str],
    url: str,
    malformed: JSONValue,
    response_kind: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Server bodies and malformed data never appear in error output."""
    monkeypatch.setenv(name="CODERPAD_API_KEY", value=_INTERVIEW_KEY)
    monkeypatch.setenv(name="CODERPAD_SCREEN_API_KEY", value=_SCREEN_KEY)
    with respx.mock() as router:
        route = router.get(url=url)
        if response_kind == "transport":
            _ = route.mock(side_effect=httpx.ConnectError(message=_SCREEN_KEY))
        elif response_kind == "http":
            _ = route.respond(
                status_code=403, json={"message": _INTERVIEW_KEY}
            )
        else:
            _ = route.respond(json=malformed)
        result = CliRunner().invoke(
            cli=main, args=arguments, catch_exceptions=False
        )
    assert result.exit_code != 0
    assert result.stdout == ""
    assert _INTERVIEW_KEY not in result.stderr
    assert _SCREEN_KEY not in result.stderr
