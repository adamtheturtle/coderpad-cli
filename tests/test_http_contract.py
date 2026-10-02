"""Exercise the default SDK HTTPX transport against its pinned API
contract.
"""

import json
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs
from zipfile import ZipFile

import httpx
import pytest
import respx
from click.testing import CliRunner
from jsonschema import Draft4Validator
from jsonschema.exceptions import ValidationError
from jsonschema.protocols import Validator
from respx.models import AllMockedAssertionError

from coderpad_cli import main
from tests.test_cli import write_files

_URL = "https://app.coderpad.io/api/questions/123456"
_CONTRACT = Path(__file__).parents[1] / "spec" / "openapi.json"


type JSONValue = (
    bool | int | float | str | list[JSONValue] | dict[str, JSONValue] | None
)


def _contract_section(*keys: str) -> dict[str, JSONValue]:
    """Read a dictionary section from the pinned shared contract."""
    value: JSONValue = dict[str, JSONValue](
        json.loads(s=_CONTRACT.read_text(encoding="utf-8")),
    )
    for key in keys:
        assert isinstance(value, dict)
        value = value[key]
    assert isinstance(value, dict)
    return value


def _validator(schema: dict[str, JSONValue]) -> Validator:
    """Build a checked validator through jsonschema's typed protocol."""
    Draft4Validator.check_schema(schema=schema)
    return Draft4Validator(schema=schema)


def _fields(request: httpx.Request) -> dict[str, str | bytes]:
    """Decode the wire request after SDK and HTTPX serialization."""
    content_type = request.headers["content-type"]
    if content_type == "application/x-www-form-urlencoded":
        fields = parse_qs(
            qs=request.content.decode(encoding="utf-8"),
            keep_blank_values=True,
            strict_parsing=True,
        )
        assert all(len(values) == 1 for values in fields.values())
        return {name: values[0] for name, values in fields.items()}
    message = BytesParser(policy=policy.default).parsebytes(
        text=b"Content-Type: "
        + content_type.encode(encoding="ascii")
        + b"\r\nMIME-Version: 1.0\r\n\r\n"
        + request.content,
    )
    assert message.is_multipart()
    result: dict[str, str | bytes] = {}
    for part in message.iter_parts():
        name = part.get_param(param="name", header="content-disposition")
        assert isinstance(name, str)
        assert name not in result
        payload = part.get_payload(decode=True)
        assert isinstance(payload, bytes)
        if part.get_filename() is None:
            result[name] = payload.decode(encoding="utf-8")
        else:
            assert part.get_filename() == "project.zip"
            assert part.get_content_type() == "application/zip"
            result[name] = payload
    return result


def _validate_contract(
    request: httpx.Request, fields: dict[str, str | bytes]
) -> None:
    """Validate fields and media type against the shared request
    schema.
    """
    media_definitions = _contract_section(
        "paths",
        "/api/questions/{id}",
        "put",
        "requestBody",
        "content",
    )
    media_type = request.headers["content-type"].partition(";")[0]
    assert media_type in media_definitions
    schema = _contract_section("components", "schemas", "QuestionForm")
    # OpenAPI binary fields have JSON Schema type string, with a binary format.
    # Keep original bytes for ZIP checks; decode only for schema validation.
    normalized = {
        name: value.decode(encoding="latin-1")
        if isinstance(value, bytes)
        else value
        for name, value in fields.items()
    }
    validator = _validator(schema=schema)
    validator.validate(instance=normalized)
    assert request.headers["authorization"] == 'Token token="synthetic-secret"'
    assert str(object=request.url) == _URL
    assert request.method == "PUT"


@pytest.mark.parametrize(
    argnames="contents",
    argvalues=["", "\ufeff# documentation-marker\r\nπ = 3  \r\n\r\n", "pass"],
)
def test_file_over_default_httpx(contents: str, tmp_path: Path) -> None:
    """Exact text survives URL encoding; metadata is absent from the
    wire.
    """
    source = tmp_path / "starter.py"
    _ = source.write_bytes(data=contents.encode(encoding="utf-8"))
    metadata = {
        "title": "Synthetic title",
        "description": "Existing notes",
        "solution": "Existing solution",
    }
    state = {**metadata, "contents": "old code"}

    def update(request: httpx.Request) -> httpx.Response:
        """Validate and apply only the supplied starter-code attribute."""
        fields = _fields(request=request)
        _validate_contract(request=request, fields=fields)
        assert fields == {"question[contents]": contents}
        state["contents"] = contents
        return httpx.Response(status_code=HTTPStatus.OK, json={"status": "OK"})

    with respx.mock(assert_all_mocked=True) as router:
        route = router.put(url=_URL).mock(side_effect=update)
        result = CliRunner().invoke(
            cli=main,
            args=[
                "questions",
                "upload",
                "123456",
                "--file",
                str(object=source),
            ],
            env={"CODERPAD_API_KEY": "synthetic-secret"},
        )
        assert result.exit_code == 0, result.output
        assert route.call_count == 1
        assert len(router.calls) == 1
    assert state == {**metadata, "contents": contents}


def test_directory_over_default_httpx(tmp_path: Path) -> None:
    """The default transport emits the SDK ZIP as a multipart file
    field.
    """
    source = tmp_path / "project"
    write_files(
        root=source,
        files={
            "main.py": b"pass\r\n",
            "sub/data.bin": b"\x00\xff",
            "bundle.zip": b"skip",
            ".git/config": b"private",
        },
    )
    metadata = {
        "title": "Synthetic title",
        "description": "Existing notes",
        "language": "python",
    }
    state = {**metadata, "files": {"old.py": b"old"}}
    uploaded = {"main.py": b"pass\r\n", "sub/data.bin": b"\x00\xff"}

    def update(request: httpx.Request) -> httpx.Response:
        """Apply the SDK-generated archive after checking its wire
        contract.
        """
        fields = _fields(request=request)
        _validate_contract(request=request, fields=fields)
        assert tuple(fields) == ("question[zip_file]",)
        archive_bytes = fields["question[zip_file]"]
        assert isinstance(archive_bytes, bytes)
        with ZipFile(file=BytesIO(initial_bytes=archive_bytes)) as archive:
            state["files"] = {
                name: archive.read(name=name) for name in archive.namelist()
            }
        return httpx.Response(status_code=HTTPStatus.OK, json={"status": "OK"})

    with respx.mock(assert_all_mocked=True) as router:
        route = router.put(url=_URL).mock(side_effect=update)
        result = CliRunner().invoke(
            cli=main,
            args=[
                "questions",
                "upload",
                "123456",
                "--directory",
                str(object=source),
                "--exclude",
                "*.zip",
            ],
            env={"CODERPAD_API_KEY": "synthetic-secret"},
        )
        assert result.exit_code == 0, result.output
        assert route.call_count == 1
        assert len(router.calls) == 1
    assert state == {**metadata, "files": uploaded}


@pytest.mark.parametrize(
    argnames="status",
    argvalues=[
        HTTPStatus.UNAUTHORIZED,
        HTTPStatus.FORBIDDEN,
        HTTPStatus.NOT_FOUND,
        HTTPStatus.TOO_MANY_REQUESTS,
        HTTPStatus.SERVICE_UNAVAILABLE,
    ],
)
def test_api_failure_over_default_httpx(
    status: HTTPStatus, tmp_path: Path
) -> None:
    """HTTP errors retain SDK semantics and never disclose response
    secrets.
    """
    source = tmp_path / "starter.py"
    _ = source.write_text(data="pass")
    with respx.mock(assert_all_mocked=True) as router:
        route = router.put(url=_URL).respond(
            status_code=status.value,
            json={"status": "ERROR", "message": "synthetic-secret"},
        )
        result = CliRunner().invoke(
            cli=main,
            args=[
                "questions",
                "upload",
                "123456",
                "--file",
                str(object=source),
            ],
            env={"CODERPAD_API_KEY": "synthetic-secret"},
        )
        assert result.exit_code == 1
        assert (
            result.output
            == f"Error: CoderPad rejected the upload (HTTP {status.value}).\n"
        )
        assert route.call_count == 1


def test_timeout_over_default_httpx(tmp_path: Path) -> None:
    """The default SDK transport's network failures are handled safely."""
    source = tmp_path / "starter.py"
    _ = source.write_text(data="pass")
    with respx.mock(assert_all_mocked=True) as router:
        route = router.put(url=_URL).mock(
            side_effect=httpx.ReadTimeout(message="synthetic-secret")
        )
        result = CliRunner().invoke(
            cli=main,
            args=[
                "questions",
                "upload",
                "123456",
                "--file",
                str(object=source),
            ],
            env={"CODERPAD_API_KEY": "synthetic-secret"},
        )
        assert result.exit_code == 1
        assert result.output == (
            "Error: Could not reach CoderPad. Check your network connection.\n"
        )
        assert route.call_count == 1


@pytest.mark.parametrize(argnames="mode", argvalues=["directory", "file"])
def test_offline_dry_run_at_http_boundary(mode: str, tmp_path: Path) -> None:
    """With no mock routes or key, dry runs still make zero requests."""
    source = tmp_path / "starter.py"
    _ = source.write_text(data="pass")
    path = tmp_path if mode == "directory" else source
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        result = CliRunner().invoke(
            cli=main,
            args=[
                "questions",
                "upload",
                "123456",
                f"--{mode}",
                str(object=path),
                "--dry-run",
            ],
            env={"CODERPAD_API_KEY": None},
        )
        assert result.exit_code == 0, result.output
        assert len(router.calls) == 0


def test_http_mock_fails_closed() -> None:
    """Any unexpected request is rejected rather than sent to CoderPad."""
    with (
        respx.mock(assert_all_mocked=True, assert_all_called=False),
        pytest.raises(expected_exception=AllMockedAssertionError),
    ):
        _ = httpx.get(url="https://app.coderpad.io/api/unexpected")


def test_contract_rejects_unknown_field() -> None:
    """The mock catches fields missing from the canonical upload
    schema.
    """

    def update(request: httpx.Request) -> httpx.Response:
        """Reject the misspelled form field at the HTTP boundary."""
        _validate_contract(request=request, fields=_fields(request=request))
        return httpx.Response(status_code=HTTPStatus.OK, json={"status": "OK"})

    with respx.mock(assert_all_mocked=True) as router:
        _ = router.put(url=_URL).mock(side_effect=update)
        with pytest.raises(
            expected_exception=ValidationError, match="Additional properties"
        ):
            _ = httpx.put(
                url=_URL,
                headers={"Authorization": 'Token token="synthetic-secret"'},
                data={"question[titel]": "mistake"},
            )
