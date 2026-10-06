"""Upload starter code using the released CoderPad SDK."""

import json
import os
from collections.abc import Generator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from importlib.metadata import version
from pathlib import Path

import click
import httpx
from coderpad.client import CoderPad
from coderpad.exceptions import CoderPadError
from coderpad.transports import Transport
from coderpad.types import QuestionVariantFileContent, QuestionVariantUnset

from coderpad_cli._sources import PreparedSource, prepare_source
from coderpad_cli._variant_commands import register_variant_commands
from coderpad_cli._variant_update import (
    VariantCreation,
    optional_overlay,
    optional_text,
    register_variant_update,
)


def create_cli(*, transport: Transport | None = None) -> click.Group:
    """Create the CLI, optionally using a supported SDK transport."""

    @click.group(name="coderpad")
    @click.version_option(
        version=version(distribution_name="coderpad-cli"), prog_name="coderpad"
    )
    def cli() -> None:
        """Upload starter code and create CoderPad question variants."""

    @cli.group()
    def questions() -> None:
        """Manage question starter code and variants."""

    @click.argument("question_id")
    @click.option(
        "--variant-id",
        help="Update this variant instead of the question's starter code.",
    )
    @click.option(
        "--directory",
        type=click.Path(path_type=Path, readable=False),
        help="Project directory.",
    )
    @click.option(
        "--file",
        "source_file",
        type=click.Path(path_type=Path, readable=False),
        help="UTF-8 starter code file.",
    )
    @click.option(
        "--exclude",
        multiple=True,
        help="Additional Gitignore pattern at the upload root. Repeatable.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Validate and list files without credentials or network access.",
    )
    def upload(  # noqa: PLR0913 - Click options plus the SDK transport boundary.
        question_id: str,
        directory: Path | None,
        source_file: Path | None,
        exclude: tuple[str, ...],
        *,
        dry_run: bool,
        variant_id: str | None,
    ) -> None:
        """Replace starter code while preserving question metadata."""
        _validate_upload(
            question_id=question_id,
            directory=directory,
            source_file=source_file,
            exclude=exclude,
            variant_id=variant_id,
        )
        _upload(
            question_id=question_id,
            prepared=prepare_source(
                directory=directory, file=source_file, excludes=exclude
            ),
            dry_run=dry_run,
            variant_id=variant_id,
            transport=transport,
        )

    _ = questions.command()(upload)

    @questions.group()
    def variants() -> None:
        """Manage variants of an existing question."""

    @click.argument("question_id")
    @click.option(
        "--language", required=True, help="Language or project-template slug."
    )
    @click.option(
        "--directory",
        type=click.Path(path_type=Path, readable=False),
        help="UTF-8 project directory to layer over the template.",
    )
    @click.option(
        "--file",
        "source_file",
        type=click.Path(path_type=Path, readable=False),
        help="UTF-8 starter code file. An empty file creates blank code.",
    )
    @click.option(
        "--solution-file",
        type=click.Path(path_type=Path, readable=False),
        help="UTF-8 reference solution.",
    )
    @click.option(
        "--file-contents-json",
        type=click.Path(path_type=Path, readable=False),
        help="Structured project overlay with hidden/deleted flags.",
    )
    @click.option(
        "--exclude",
        multiple=True,
        help="Additional Gitignore pattern at the upload root. Repeatable.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print a JSON plan without credentials or network access.",
    )
    def create(  # noqa: PLR0913
        question_id: str,
        *,
        solution_file: Path | None,
        file_contents_json: Path | None,
        language: str,
        directory: Path | None,
        source_file: Path | None,
        exclude: tuple[str, ...],
        dry_run: bool,
    ) -> None:
        """Create a variant and print its question and variant IDs as JSON.

        Omit --file and --directory to use default starter content.
        Save the returned variant ID for subsequent uploads.
        Each invocation creates a new variant; creation is never retried.
        """
        _validate_id(name="QUESTION_ID", identifier=question_id)
        if language == "" or language.strip() != language:
            msg = "Provide a nonempty language or project-template slug."
            raise click.BadParameter(message=msg, param_hint="--language")
        if file_contents_json is not None and (
            directory is not None or source_file is not None
        ):
            msg = (
                "--file-contents-json cannot be combined "
                "with --file or --directory."
            )
            raise click.UsageError(message=msg)
        prepared: AbstractContextManager[PreparedSource]
        if directory is not None or source_file is not None:
            _validate_upload(
                question_id=question_id,
                directory=directory,
                source_file=source_file,
                exclude=exclude,
                variant_id=None,
            )
            prepared = prepare_source(
                directory=directory,
                file=source_file,
                excludes=exclude,
            )
        else:
            if len(exclude) > 0:
                msg = "--exclude requires --directory."
                raise click.UsageError(message=msg)
            prepared = nullcontext(
                enter_result=PreparedSource(
                    contents=None,
                    directory=None,
                    files=(),
                ),
            )
        _create_variant(
            creation=VariantCreation(
                question_id=question_id,
                language=language,
                solution_file=solution_file,
                file_contents_json=file_contents_json,
            ),
            prepared=prepared,
            dry_run=dry_run,
            transport=transport,
        )

    _ = variants.command()(create)
    register_variant_commands(
        group=variants,
        transport=transport,
        validate_id=_validate_id,
        api_key=_api_key,
        request_errors=_request_errors,
    )
    register_variant_update(
        group=variants,
        transport=transport,
        validate_id=_validate_id,
        api_key=_api_key,
        request_errors=_request_errors,
    )
    return cli


def _validate_id(name: str, identifier: str) -> None:
    """Reject identifiers that cannot address a question or variant."""
    if (
        not identifier.isascii()
        or not identifier.isdecimal()
        or int(identifier) < 1
    ):
        msg = f"{name} must be a positive decimal integer."
        raise click.BadParameter(message=msg, param_hint=name)


def _validate_upload(
    question_id: str,
    directory: Path | None,
    source_file: Path | None,
    exclude: tuple[str, ...],
    *,
    variant_id: str | None,
) -> None:
    """Validate command combinations and target identifiers."""
    if (directory is None) == (source_file is None):
        msg = "Provide exactly one of --directory or --file."
        raise click.UsageError(message=msg)
    for name, identifier in (
        ("QUESTION_ID", question_id),
        ("--variant-id", variant_id),
    ):
        if identifier is not None:
            _validate_id(name=name, identifier=identifier)
    if len(exclude) > 0 and directory is None:
        msg = "--exclude requires --directory."
        raise click.UsageError(message=msg)


def _api_key() -> str:
    """Read a nonempty API key without printing its value."""
    api_key = os.environ.get(key="CODERPAD_API_KEY")
    if api_key is None or api_key.strip() == "":
        msg = (
            "CODERPAD_API_KEY is missing or empty. Set it in the environment."
        )
        raise click.ClickException(message=msg)
    return api_key


def _variant_files(
    source: PreparedSource,
) -> list[QuestionVariantFileContent] | None:
    """Decode every staged variant file before making any request."""
    directory = source.directory
    if directory is None:
        return None
    return [
        QuestionVariantFileContent(
            path=path,
            contents=(directory / path).read_bytes().decode(encoding="utf-8"),
        )
        for path in source.files
    ]


def _update(
    client: CoderPad,
    question_id: str,
    variant_id: str | None,
    source: PreparedSource,
    file_contents: list[QuestionVariantFileContent] | None,
) -> None:
    """Update only the selected question or variant's starter code."""
    if variant_id is None:
        client.questions.update(
            question_id=question_id,
            contents=source.contents,
            directory=source.directory,
        )
    elif file_contents is None:
        _ = client.questions.variants.update(
            question_id=question_id,
            variant_id=variant_id,
            contents=source.contents,
        )
    else:
        _ = client.questions.variants.update(
            question_id=question_id,
            variant_id=variant_id,
            file_contents=file_contents,
        )


def _upload(
    question_id: str,
    prepared: AbstractContextManager[PreparedSource],
    *,
    dry_run: bool,
    variant_id: str | None,
    transport: Transport | None,
) -> None:
    """Prepare input, call the SDK if requested, and report safe
    errors.
    """
    with _request_errors(operation="upload"), prepared as source:
        target = (
            f"https://app.coderpad.io/dashboard/questions/all/{question_id}"
        )
        file_contents = None
        if variant_id is not None:
            target += f" variant {variant_id}"
            file_contents = _variant_files(source=source)
        if dry_run:
            click.echo(message=f"Would update {target}")
            for path in source.files:
                click.echo(message=f"  {path}")
            return
        api_key = _api_key()
        with CoderPad(api_key=api_key, transport=transport) as client:
            _update(
                client=client,
                question_id=question_id,
                variant_id=variant_id,
                source=source,
                file_contents=file_contents,
            )
        click.echo(message=f"Updated {target}")


def _create_variant(
    creation: VariantCreation,
    prepared: AbstractContextManager[PreparedSource],
    *,
    dry_run: bool,
    transport: Transport | None,
) -> None:
    """Prepare an optional source and create exactly one variant."""
    with _request_errors(operation="variant creation"), prepared as source:
        file_contents: list[QuestionVariantFileContent] | str | None = (
            _variant_files(source=source)
        )
        overlay = optional_overlay(path=creation.file_contents_json)
        solution = optional_text(path=creation.solution_file)
        if overlay is not None:
            file_contents = overlay.json
        if dry_run:
            plan: dict[str, object] = {
                "operation": "create_variant",
                "question_id": int(creation.question_id),
                "language": creation.language,
                "files": source.files if overlay is None else overlay.paths,
            }
            if creation.solution_file is not None:
                plan["solution_file"] = str(object=creation.solution_file)
            click.echo(message=json.dumps(obj=plan))
            return
        with CoderPad(api_key=_api_key(), transport=transport) as client:
            try:
                variant = client.questions.variants.create(
                    question_id=creation.question_id,
                    language=creation.language,
                    solution=solution,
                    contents=source.contents
                    if source.contents is not None
                    else QuestionVariantUnset.OMITTED,
                    file_contents=file_contents,
                )
            except ValueError:
                msg = (
                    "CoderPad returned an invalid variant response. "
                    "Creation may have succeeded. Check the question "
                    "before retrying."
                )
                raise click.ClickException(message=msg) from None
        click.echo(
            message=json.dumps(
                obj={
                    "question_id": int(creation.question_id),
                    "variant_id": variant.id,
                }
            )
        )


@contextmanager
def _request_errors(operation: str) -> Generator[None]:
    """Translate preparation and SDK failures without exposing secrets."""
    try:
        yield
    except CoderPadError as error:
        msg = f"CoderPad rejected the {operation} (HTTP {error.status_code})."
        raise click.ClickException(message=msg) from None
    except httpx.TransportError:
        msg = "Could not reach CoderPad. Check your network connection."
        raise click.ClickException(message=msg) from None
    except UnicodeError:
        msg = "Source text and .gitignore files must be valid UTF-8."
        raise click.ClickException(message=msg) from None
    except OSError as error:
        msg = f"Could not prepare upload files ({type(error).__name__})."
        raise click.ClickException(message=msg) from None
    except ValueError as error:
        raise click.ClickException(message=str(object=error)) from None


main: click.Group = create_cli()
