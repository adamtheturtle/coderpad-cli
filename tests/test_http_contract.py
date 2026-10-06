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
from tests.test_cli import USAGE_ERROR, write_files

_URL = "https://app.coderpad.io/api/questions/123456"
_VARIANT_URL = f"{_URL}/variants/7"
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
@pytest.mark.parametrize(argnames="variant", argvalues=[False, True])
def test_api_failure_over_default_httpx(
    status: HTTPStatus, tmp_path: Path, *, variant: bool
) -> None:
    """HTTP errors retain SDK semantics and never disclose response
    secrets.
    """
    source = tmp_path / "starter.py"
    _ = source.write_text(data="pass")
    with respx.mock(assert_all_mocked=True) as router:
        route = router.put(url=_VARIANT_URL if variant else _URL).respond(
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
                *(["--variant-id", "7"] if variant else []),
            ],
            env={"CODERPAD_API_KEY": "synthetic-secret"},
        )
        assert result.exit_code == 1
        assert (
            result.output
            == f"Error: CoderPad rejected the upload (HTTP {status.value}).\n"
        )
        assert route.call_count == 1


@pytest.mark.parametrize(argnames="variant", argvalues=[False, True])
def test_timeout_over_default_httpx(tmp_path: Path, *, variant: bool) -> None:
    """The default SDK transport's network failures are handled safely."""
    source = tmp_path / "starter.py"
    _ = source.write_text(data="pass")
    with respx.mock(assert_all_mocked=True) as router:
        route = router.put(url=_VARIANT_URL if variant else _URL).mock(
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
                *(["--variant-id", "7"] if variant else []),
            ],
            env={"CODERPAD_API_KEY": "synthetic-secret"},
        )
        assert result.exit_code == 1
        assert result.output == (
            "Error: Could not reach CoderPad. Check your network connection.\n"
        )
        assert route.call_count == 1


@pytest.mark.parametrize(argnames="mode", argvalues=["directory", "file"])
@pytest.mark.parametrize(argnames="variant", argvalues=[False, True])
def test_offline_dry_run_at_http_boundary(
    mode: str, tmp_path: Path, *, variant: bool
) -> None:
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
                *(["--variant-id", "7"] if variant else []),
            ],
            env={"CODERPAD_API_KEY": None},
        )
        assert result.exit_code == 0, result.output
        target = "123456 variant 7" if variant else "123456"
        selected = "starter.py" if mode == "directory" else str(object=source)
        assert result.output == (
            "Would update https://app.coderpad.io/dashboard/questions/all/"
            f"{target}\n  {selected}\n"
        )
        assert len(router.calls) == 0


def _variant_response() -> dict[str, JSONValue]:
    """Use the SDK contract's project-variant response example."""
    return {
        **_contract_section(
            "paths",
            "/api/questions/{question_id}/variants/{variant_id}",
            "put",
            "responses",
            "200",
            "content",
            "application/json",
            "example",
        ),
        "question_id": 123456,
    }


def _validate_variant_request(
    request: httpx.Request, expected: dict[str, JSONValue]
) -> None:
    """Check the JSON contract and the exact starter-only update."""
    schema = _contract_section(
        "paths",
        "/api/questions/{question_id}/variants/{variant_id}",
        "put",
        "requestBody",
        "content",
        "application/json",
        "schema",
    )
    validator = _validator(
        schema={**schema, "components": _contract_section("components")}
    )
    body = dict[str, JSONValue](json.loads(s=request.content))
    validator.validate(instance=body)
    assert body == expected
    assert request.method == "PUT"
    assert str(object=request.url) == _VARIANT_URL
    assert request.headers["content-type"] == "application/json"
    assert request.headers["authorization"] == 'Token token="synthetic-secret"'


@pytest.mark.parametrize(
    argnames="contents",
    argvalues=["", "\ufeff# input-begin\r\nπ = 3  \r\n\r\n", "pass"],
)
def test_variant_file(contents: str, tmp_path: Path) -> None:
    """Preserve exact file text without touching variant metadata."""
    source = tmp_path / "starter.py"
    _ = source.write_bytes(data=contents.encode(encoding="utf-8"))

    def update(request: httpx.Request) -> httpx.Response:
        """Accept only a contents update for the selected variant."""
        _validate_variant_request(
            request=request, expected={"contents": contents}
        )
        return httpx.Response(
            status_code=HTTPStatus.OK,
            json={**_variant_response(), "language": "python"},
        )

    with respx.mock(assert_all_mocked=True) as router:
        route = router.put(url=_VARIANT_URL).mock(side_effect=update)
        result = CliRunner().invoke(
            cli=main,
            args=[
                "questions",
                "upload",
                "123456",
                "--variant-id",
                "7",
                "--file",
                str(object=source),
            ],
            env={"CODERPAD_API_KEY": "synthetic-secret"},
        )
        assert result.exit_code == 0, result.output
        assert route.call_count == 1
        assert len(router.calls) == 1
    assert result.output == (
        "Updated https://app.coderpad.io/dashboard/questions/all/"
        "123456 variant 7\n"
    )


def test_variant_directory(tmp_path: Path) -> None:
    """Send selected UTF-8 project files as JSON rather than a ZIP."""
    write_files(
        root=tmp_path,
        files={
            ".gitignore": b"*.tmp\n",
            ".git/config": b"private",
            "main.py": b"pass\r\n",
            "nested/empty.py": b"",
            "nested/prompt.tsx": "\ufeffπ = 3  \r\n".encode(encoding="utf-8"),
            "ignored.tmp": b"ignored",
            "bundle.zip": b"excluded",
        },
    )
    expected: dict[str, JSONValue] = {
        "file_contents": [
            {"path": ".gitignore", "contents": "*.tmp\n"},
            {"path": "main.py", "contents": "pass\r\n"},
            {"path": "nested/empty.py", "contents": ""},
            {"path": "nested/prompt.tsx", "contents": "\ufeffπ = 3  \r\n"},
        ],
    }

    def update(request: httpx.Request) -> httpx.Response:
        """Accept only project files, leaving environment and code omitted."""
        _validate_variant_request(request=request, expected=expected)
        return httpx.Response(
            status_code=HTTPStatus.OK, json=_variant_response()
        )

    with respx.mock(assert_all_mocked=True) as router:
        route = router.put(url=_VARIANT_URL).mock(side_effect=update)
        result = CliRunner().invoke(
            cli=main,
            args=[
                "questions",
                "upload",
                "123456",
                "--variant-id",
                "7",
                "--directory",
                str(object=tmp_path),
                "--exclude",
                "*.zip",
            ],
            env={"CODERPAD_API_KEY": "synthetic-secret"},
        )
        assert result.exit_code == 0, result.output
        assert route.call_count == 1
        assert len(router.calls) == 1
    assert result.output == (
        "Updated https://app.coderpad.io/dashboard/questions/all/"
        "123456 variant 7\n"
    )


@pytest.mark.parametrize(argnames="dry_run", argvalues=[False, True])
def test_variant_directory_rejects_binary(
    tmp_path: Path, *, dry_run: bool
) -> None:
    """Reject non-UTF-8 variant files even in credential-free dry runs."""
    write_files(
        root=tmp_path,
        files={"valid.py": b"pass", "nested/invalid.bin": b"\xff"},
    )
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        result = CliRunner().invoke(
            cli=main,
            args=[
                "questions",
                "upload",
                "123456",
                "--variant-id",
                "7",
                "--directory",
                str(object=tmp_path),
                *(["--dry-run"] if dry_run else []),
            ],
            env={"CODERPAD_API_KEY": None},
        )
        assert result.exit_code == 1
        assert result.output == (
            "Error: Source text and .gitignore files must be valid UTF-8.\n"
        )
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


@pytest.mark.parametrize(
    argnames=("language", "mode", "contents"),
    argvalues=[
        ("python3", "default", None),
        ("multifile_python", "default", None),
        ("javascript", "file", ""),
        ("python3", "file", "\ufeffπ = 3  \r\n\r\n"),
        ("multifile_python", "directory", "pass\r\n"),
    ],
)
@pytest.mark.parametrize(argnames="dry_run", argvalues=[False, True])
def test_create_variant(
    language: str,
    mode: str,
    contents: str | None,
    tmp_path: Path,
    *,
    dry_run: bool,
) -> None:
    """Create through the shared POST contract or plan entirely
    offline.
    """
    arguments = [
        "questions",
        "variants",
        "create",
        "123456",
        "--language",
        language,
    ]
    expected: dict[str, JSONValue] = {"language": language}
    selected: list[str] = []
    if contents is not None:
        source = tmp_path / "starter.py"
        _ = source.write_bytes(data=contents.encode(encoding="utf-8"))
        if mode == "directory":
            write_files(
                root=tmp_path,
                files={
                    ".gitignore": b"*.tmp\n",
                    "ignored.tmp": b"ignored",
                    "excluded.zip": b"excluded",
                    ".git/config": b"private",
                },
            )
            arguments.extend(
                [
                    "--directory",
                    str(object=tmp_path),
                    "--exclude",
                    "*.zip",
                    "--exclude",
                    ".gitignore",
                ]
            )
            expected["file_contents"] = [
                {"path": "starter.py", "contents": contents},
            ]
            selected = ["starter.py"]
        else:
            arguments.extend(["--file", str(object=source)])
            expected["contents"] = contents
            selected = [str(object=source)]
    if dry_run:
        arguments.append("--dry-run")

    def create(request: httpx.Request) -> httpx.Response:
        """Validate an isolated creation, with no parent or sibling writes."""
        schema = _contract_section(
            "paths",
            "/api/questions/{question_id}/variants",
            "post",
            "requestBody",
            "content",
            "application/json",
            "schema",
        )
        validator = _validator(
            schema={
                **schema,
                "components": _contract_section("components"),
            }
        )
        body = dict[str, JSONValue](json.loads(s=request.content))
        validator.validate(instance=body)
        assert body == expected
        assert request.method == "POST"
        assert str(object=request.url) == f"{_URL}/variants"
        assert request.headers["content-type"] == "application/json"
        assert request.headers["authorization"] == (
            'Token token="synthetic-secret"'
        )
        response = _variant_response()
        if language != "multifile_python":
            response.update(
                {
                    "language": language,
                    "project_template_id": None,
                    "project_template_slug": None,
                }
            )
        return httpx.Response(status_code=HTTPStatus.OK, json=response)

    with respx.mock(assert_all_mocked=True) as router:
        if not dry_run:
            _ = router.post(url=f"{_URL}/variants").mock(side_effect=create)
        result = CliRunner().invoke(
            cli=main,
            args=arguments,
            env={"CODERPAD_API_KEY": None if dry_run else "synthetic-secret"},
        )
        assert result.exit_code == 0, result.output
        assert result.stderr == ""
        if dry_run:
            assert json.loads(s=result.stdout) == {
                "operation": "create_variant",
                "question_id": 123456,
                "language": language,
                "files": selected,
            }
            assert len(router.calls) == 0
        else:
            assert json.loads(s=result.stdout) == {
                "question_id": 123456,
                "variant_id": 7,
            }
            assert len(router.calls) == 1


@pytest.mark.parametrize(
    argnames="arguments",
    argvalues=[
        ["123456"],
        ["123456", "--language="],
        ["123456", "--language= "],
        ["123456", "--language= python3"],
        ["0", "--language=python3"],
        ["abc", "--language=python3"],
        ["\uff11\uff12\uff13", "--language=python3"],
        ["123456", "--language=python3", "--file=a", "--directory=b"],
        ["123456", "--language=python3", "--exclude=*.zip"],
        ["123456", "--language=python3", "--file=a", "--exclude=*.zip"],
    ],
)
def test_create_invalid_arguments(arguments: list[str]) -> None:
    """Reject invalid creation options before any authentication or
    I/O.
    """
    with respx.mock(assert_all_mocked=True) as router:
        result = CliRunner().invoke(
            cli=main,
            args=["questions", "variants", "create", *arguments],
            env={"CODERPAD_API_KEY": None},
        )
        assert result.exit_code == USAGE_ERROR
        assert result.stdout == ""
        assert len(router.calls) == 0


@pytest.mark.parametrize(argnames="key", argvalues=[None, "", "   "])
def test_create_missing_key(key: str | None) -> None:
    """Creation needs a nonempty credential only when actually
    requested.
    """
    with respx.mock(assert_all_mocked=True) as router:
        result = CliRunner().invoke(
            cli=main,
            args=[
                "questions",
                "variants",
                "create",
                "123456",
                "--language=python3",
            ],
            env={"CODERPAD_API_KEY": key},
        )
        assert result.exit_code == 1
        assert result.stdout == ""
        assert result.stderr == (
            "Error: CODERPAD_API_KEY is missing or empty. "
            "Set it in the environment.\n"
        )
        assert len(router.calls) == 0


@pytest.mark.parametrize(
    argnames="failure",
    argvalues=["api", "timeout", "invalid-response", "invalid-json"],
)
def test_create_failures_without_retry(failure: str) -> None:
    """Never retry creation or expose response bodies in errors."""
    with respx.mock(assert_all_mocked=True) as router:
        route = router.post(url=f"{_URL}/variants")
        if failure == "api":
            _ = route.respond(status_code=503, json={"message": "secret"})
            message = "CoderPad rejected the variant creation (HTTP 503)."
        elif failure == "timeout":
            _ = route.mock(side_effect=httpx.ReadTimeout(message="secret"))
            message = (
                "Could not reach CoderPad. Check your network connection."
            )
        else:
            if failure == "invalid-json":
                _ = route.respond(status_code=200, text="secret")
            else:
                _ = route.respond(status_code=200, json={"id": "secret"})
            message = (
                "CoderPad returned an invalid variant response. "
                "Creation may have succeeded. Check the question "
                "before retrying."
            )
        result = CliRunner().invoke(
            cli=main,
            args=[
                "questions",
                "variants",
                "create",
                "123456",
                "--language=python3",
            ],
            env={"CODERPAD_API_KEY": "synthetic-secret"},
        )
        assert result.exit_code == 1
        assert result.stdout == ""
        assert result.stderr == f"Error: {message}\n"
        assert route.call_count == 1
        assert len(router.calls) == 1


@pytest.mark.parametrize(argnames="dry_run", argvalues=[False, True])
@pytest.mark.parametrize(argnames="mode", argvalues=["file", "directory"])
def test_create_invalid_utf8(
    tmp_path: Path,
    mode: str,
    *,
    dry_run: bool,
) -> None:
    """Reject binary creation sources before any network mutation."""
    source = tmp_path / "binary"
    _ = source.write_bytes(data=b"\xff")
    path = source if mode == "file" else tmp_path
    with respx.mock(assert_all_mocked=True) as router:
        result = CliRunner().invoke(
            cli=main,
            args=[
                "questions",
                "variants",
                "create",
                "123456",
                "--language=multifile_python",
                f"--{mode}",
                str(object=path),
                *(["--dry-run"] if dry_run else []),
            ],
            env={"CODERPAD_API_KEY": None},
        )
        assert result.exit_code == 1
        assert result.stdout == ""
        assert result.stderr == (
            "Error: Source text and .gitignore files must be valid UTF-8.\n"
        )
        assert len(router.calls) == 0


@pytest.mark.parametrize(argnames="command", argvalues=["list", "get"])
def test_variant_discovery(command: str) -> None:
    """Reads emit full JSON with parent and project-template identity."""
    response = _variant_response()
    with respx.mock() as router:
        route = router.get(
            url=f"{_URL}/variants" if command == "list" else _VARIANT_URL
        ).respond(json=[response] if command == "list" else response)
        result = CliRunner().invoke(
            cli=main,
            args=[
                "questions",
                "variants",
                command,
                "123456",
                *(["7"] if command == "get" else []),
            ],
            env={"CODERPAD_API_KEY": "synthetic-secret"},
        )
        assert result.exit_code == 0, result.output
        output = dict[str, JSONValue](json.loads(s=result.output))
        variant: JSONValue
        if command == "list":
            assert output["question_id"] == response["question_id"]
            variants = output["variants"]
            assert isinstance(variants, list)
            variant = variants[0]
        else:
            variant = output
        assert isinstance(variant, dict)
        assert variant["question_id"] == response["question_id"]
        assert variant["id"] == response["id"]
        assert variant["language"] == response["language"]
        assert (
            variant["project_template_id"] == response["project_template_id"]
        )
        assert route.call_count == 1
        assert (
            route.calls.last.request.headers["Authorization"]
            == 'Token token="synthetic-secret"'
        )


@pytest.mark.parametrize(argnames="dry_run", argvalues=[False, True])
def test_delete_variant(*, dry_run: bool) -> None:
    """Deletion touches only the selected endpoint, or makes no
    request.
    """
    with respx.mock(assert_all_called=False) as router:
        route = router.delete(url=_VARIANT_URL).respond(
            status_code=HTTPStatus.NO_CONTENT
        )
        result = CliRunner().invoke(
            cli=main,
            args=[
                "questions",
                "variants",
                "delete",
                "123456",
                "7",
                *(["--dry-run"] if dry_run else []),
            ],
            env={"CODERPAD_API_KEY": None if dry_run else "synthetic-secret"},
        )
        assert result.exit_code == 0, result.output
        assert json.loads(s=result.output) == {
            "operation": "delete_variant",
            "question_id": 123456,
            "variant_id": 7,
        }
        assert route.call_count == (0 if dry_run else 1)
        assert len(router.calls) == (0 if dry_run else 1)


@pytest.mark.parametrize(
    argnames="arguments",
    argvalues=[
        ["list", "0"],
        ["get", "0", "7"],
        ["get", "123456", "0"],
        ["delete", "0", "7"],
        ["delete", "123456", "0"],
    ],
)
def test_variant_discovery_rejects_invalid_ids(arguments: list[str]) -> None:
    """Invalid parent and child IDs fail before authentication or
    network.
    """
    with respx.mock(assert_all_called=False) as router:
        result = CliRunner().invoke(
            cli=main,
            args=["questions", "variants", *arguments],
            env={"CODERPAD_API_KEY": None},
        )
        assert result.exit_code == USAGE_ERROR
        assert len(router.calls) == 0


def test_variant_delete_error_is_safe_and_not_retried() -> None:
    """Mutation errors stay nonzero, secret-free, and single-request."""
    with respx.mock() as router:
        route = router.delete(url=_VARIANT_URL).respond(
            status_code=HTTPStatus.FORBIDDEN,
            json={"message": "synthetic-secret"},
        )
        result = CliRunner().invoke(
            cli=main,
            args=["questions", "variants", "delete", "123456", "7"],
            env={"CODERPAD_API_KEY": "synthetic-secret"},
        )
        assert result.exit_code == 1
        assert (
            result.output
            == "Error: CoderPad rejected the variant deletion (HTTP 403).\n"
        )
        assert route.call_count == 1


@pytest.mark.parametrize(argnames="command", argvalues=["list", "get"])
def test_variant_discovery_malformed_response_is_safe(command: str) -> None:
    """Malformed server data does not appear in error output."""
    with respx.mock() as router:
        payload = {"id": "synthetic-secret"}
        route = router.get(
            url=f"{_URL}/variants" if command == "list" else _VARIANT_URL
        ).respond(json=[payload] if command == "list" else payload)
        result = CliRunner().invoke(
            cli=main,
            args=[
                "questions",
                "variants",
                command,
                "123456",
                *(["7"] if command == "get" else []),
            ],
            env={"CODERPAD_API_KEY": "synthetic-secret"},
        )
        assert result.exit_code == 1
        assert (
            result.output
            == "Error: CoderPad returned an invalid variant response.\n"
        )
        assert route.call_count == 1


def _variant_edit_case(
    *, mode: str, tmp_path: Path
) -> tuple[list[str], dict[str, JSONValue], list[JSONValue], str, str | None]:
    """Prepare an edit and its independently expected wire attributes."""
    arguments = ["questions", "variants", "update", "123456", "7"]
    expected: dict[str, JSONValue] = {}
    paths: list[JSONValue] = []
    action = "omit"
    kind: str | None = None
    if mode in {"file", "blank", "language-source"}:
        contents = "" if mode == "blank" else "new code\r\n"
        path = tmp_path / "starter.py"
        _ = path.write_bytes(data=contents.encode(encoding="utf-8"))
        arguments.extend(["--file", str(object=path)])
        expected["contents"] = contents
        paths = [str(object=path)]
        action, kind = "replace", "single_file"
    elif mode == "directory":
        path = tmp_path / "project"
        write_files(
            root=path,
            files={"main.py": b"new code\r\n", "ignored.tmp": b"ignore"},
        )
        arguments.extend(
            ["--directory", str(object=path), "--exclude", "*.tmp"]
        )
        expected["file_contents"] = [
            {"path": "main.py", "contents": "new code\r\n"}
        ]
        paths = ["main.py"]
        action, kind = "replace", "project"
    elif mode in {"overlay", "overlay-empty"}:
        entries: list[dict[str, JSONValue]] = (
            []
            if mode == "overlay-empty"
            else [
                {
                    "path": "hidden.py",
                    "contents": "secret",
                    "hidden": True,
                    "deleted": False,
                },
                {"path": "old.py", "deleted": True},
            ]
        )
        path = tmp_path / "files.json"
        _ = path.write_text(data=json.dumps(obj=entries), encoding="utf-8")
        arguments.extend(["--file-contents-json", str(object=path)])
        expected["file_contents"] = json.dumps(obj=entries)
        paths = [] if mode == "overlay-empty" else ["hidden.py", "old.py"]
        action, kind = (
            ("reset" if mode == "overlay-empty" else "replace"),
            "project",
        )
    elif mode == "reset-code":
        arguments.append("--reset-code")
        expected["contents"] = None
        action, kind = "reset", "single_file"
    elif mode == "reset-project":
        arguments.append("--reset-project")
        expected["file_contents"] = list[JSONValue]()
        action, kind = "reset", "project"
    solution_path = tmp_path / "solution.py"
    if mode == "solution":
        _ = solution_path.write_bytes(data=b"reference\r\n")
        arguments.extend(["--solution-file", str(object=solution_path)])
        expected["solution"] = "reference\r\n"
    if mode in {"language", "language-source"}:
        arguments.extend(["--language", "python3"])
        expected["language"] = "python3"
    return arguments, expected, paths, action, kind


@pytest.mark.parametrize(
    argnames="mode",
    argvalues=[
        "file",
        "blank",
        "directory",
        "overlay",
        "overlay-empty",
        "reset-code",
        "reset-project",
        "solution",
        "language",
        "language-source",
    ],
)
@pytest.mark.parametrize(argnames="dry_run", argvalues=[False, True])
def test_explicit_variant_update(
    mode: str, tmp_path: Path, *, dry_run: bool
) -> None:
    """Edits distinguish omission, blank replacements, and explicit resets."""
    arguments, expected, paths, action, kind = _variant_edit_case(
        mode=mode, tmp_path=tmp_path
    )
    solution_path = tmp_path / "solution.py"
    if dry_run:
        arguments.append("--dry-run")
    with respx.mock(assert_all_called=False) as router:
        route = router.put(url=_VARIANT_URL).mock(
            return_value=httpx.Response(
                status_code=200, json=_variant_response()
            )
        )
        result = CliRunner().invoke(
            cli=main,
            args=arguments,
            env={"CODERPAD_API_KEY": None if dry_run else "synthetic-secret"},
        )
        assert result.exit_code == 0, result.output
        if dry_run:
            plan: dict[str, JSONValue] = {
                "operation": "update_variant",
                "question_id": 123456,
                "variant_id": 7,
                "content": {"action": action, "kind": kind, "files": paths},
            }
            if mode in {"language", "language-source"}:
                plan["language"] = "python3"
            if mode == "solution":
                plan["solution_file"] = str(object=solution_path)
            assert json.loads(s=result.stdout) == plan
            assert route.call_count == 0
        else:
            assert json.loads(s=route.calls.last.request.content) == expected
            assert (
                route.calls.last.request.headers["Authorization"]
                == 'Token token="synthetic-secret"'
            )
            assert json.loads(s=result.stdout) == {
                "question_id": 123456,
                "variant_id": 7,
            }
            assert route.call_count == 1


@pytest.mark.parametrize(argnames="dry_run", argvalues=[False, True])
def test_variant_creation_with_solution_and_overlay(
    tmp_path: Path, *, dry_run: bool
) -> None:
    """Creation retains solution bytes and supplied overlay flags."""
    solution = tmp_path / "solution.py"
    overlay = tmp_path / "overlay.json"
    _ = solution.write_bytes(data=b"reference\r\n")
    entries = [
        {"path": "hidden.py", "hidden": True},
        {"path": "old.py", "deleted": True},
    ]
    _ = overlay.write_text(data=json.dumps(obj=entries), encoding="utf-8")
    with respx.mock(assert_all_called=False) as router:
        route = router.post(url=f"{_URL}/variants").mock(
            return_value=httpx.Response(
                status_code=200, json=_variant_response()
            )
        )
        result = CliRunner().invoke(
            cli=main,
            args=[
                "questions",
                "variants",
                "create",
                "123456",
                "--language",
                "multifile_python",
                "--solution-file",
                str(object=solution),
                "--file-contents-json",
                str(object=overlay),
                *(["--dry-run"] if dry_run else []),
            ],
            env={"CODERPAD_API_KEY": None if dry_run else "synthetic-secret"},
        )
        assert result.exit_code == 0, result.output
        if dry_run:
            assert json.loads(s=result.stdout) == {
                "operation": "create_variant",
                "question_id": 123456,
                "language": "multifile_python",
                "files": ["hidden.py", "old.py"],
                "solution_file": str(object=solution),
            }
            assert route.call_count == 0
        else:
            assert json.loads(s=route.calls.last.request.content) == {
                "language": "multifile_python",
                "solution": "reference\r\n",
                "file_contents": json.dumps(obj=entries),
            }
            assert route.call_count == 1


@pytest.mark.parametrize(
    argnames="options",
    argvalues=[
        [],
        ["--language="],
        ["--language= "],
        ["--language= python3"],
        ["--file", "file", "--directory", "directory"],
        ["--file", "file", "--file-contents-json", "files.json"],
        ["--reset-code", "--reset-project"],
        ["--reset-code", "--file", "file"],
        ["--language", "python3", "--exclude", "*.tmp"],
    ],
)
def test_invalid_variant_edit_options(options: list[str]) -> None:
    """Conflicting options fail before file reads, credentials, or
    requests.
    """
    with respx.mock() as router:
        result = CliRunner().invoke(
            cli=main,
            args=["questions", "variants", "update", "123456", "7", *options],
            env={"CODERPAD_API_KEY": None},
        )
        assert result.exit_code == USAGE_ERROR
        assert len(router.calls) == 0
        assert "CODERPAD_API_KEY" not in result.output


@pytest.mark.parametrize(argnames="command", argvalues=["create", "update"])
@pytest.mark.parametrize(
    argnames="text",
    argvalues=[
        "not JSON synthetic-secret",
        '{"path":"synthetic-secret"}',
        '[{"path":1}]',
    ],
)
def test_bad_variant_overlay_is_safe(
    command: str, text: str, tmp_path: Path
) -> None:
    """Malformed local JSON is rejected without quoting its contents."""
    path = tmp_path / "files.json"
    _ = path.write_text(data=text, encoding="utf-8")
    arguments = ["questions", "variants", command, "123456"]
    arguments.extend(
        ["--language", "python3"] if command == "create" else ["7"]
    )
    with respx.mock() as router:
        result = CliRunner().invoke(
            cli=main,
            args=[*arguments, "--file-contents-json", str(object=path)],
            env={"CODERPAD_API_KEY": None},
        )
        assert result.exit_code == USAGE_ERROR
        assert (
            "Project file JSON must be an array of valid file entries."
            in result.output
        )
        assert "synthetic-secret" not in result.output
        assert len(router.calls) == 0


@pytest.mark.parametrize(
    argnames="status", argvalues=[HTTPStatus.OK, HTTPStatus.FORBIDDEN]
)
def test_variant_update_errors_are_safe(status: HTTPStatus) -> None:
    """Malformed responses and rejected writes never retry or expose
    data.
    """
    with respx.mock() as router:
        route = router.put(url=_VARIANT_URL).mock(
            return_value=httpx.Response(
                status_code=status, json={"id": "synthetic-secret"}
            )
        )
        result = CliRunner().invoke(
            cli=main,
            args=[
                "questions",
                "variants",
                "update",
                "123456",
                "7",
                "--language",
                "python3",
            ],
            env={"CODERPAD_API_KEY": "synthetic-secret"},
        )
        assert result.exit_code == 1
        assert "synthetic-secret" not in result.output
        assert route.call_count == 1


def test_creation_rejects_conflicting_overlay() -> None:
    """An overlay cannot be combined with a file or directory on
    creation.
    """
    result = CliRunner().invoke(
        cli=main,
        args=[
            "questions",
            "variants",
            "create",
            "123456",
            "--language",
            "python3",
            "--file-contents-json",
            "files.json",
            "--file",
            "starter.py",
        ],
        env={"CODERPAD_API_KEY": None},
    )
    assert result.exit_code == USAGE_ERROR
    assert "cannot be combined" in result.output
