"""Upload starter code using the released CoderPad SDK."""

import os
from contextlib import AbstractContextManager
from importlib.metadata import version
from pathlib import Path

import click
import httpx
from coderpad.client import CoderPad
from coderpad.exceptions import CoderPadError
from coderpad.transports import Transport
from coderpad.types import QuestionVariantFileContent

from coderpad_cli._sources import PreparedSource, prepare_source


def create_cli(*, transport: Transport | None = None) -> click.Group:
    """Create the CLI, optionally using a supported SDK transport."""

    @click.group(name="coderpad")
    @click.version_option(
        version=version(distribution_name="coderpad-cli"), prog_name="coderpad"
    )
    def cli() -> None:
        """Upload starter code to existing CoderPad questions."""

    @cli.group()
    def questions() -> None:
        """Manage question starter code."""

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
    return cli


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
        if identifier is not None and (
            not identifier.isascii()
            or not identifier.isdecimal()
            or int(identifier) < 1
        ):
            msg = f"{name} must be a positive decimal integer."
            raise click.BadParameter(message=msg, param_hint=name)
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
    try:
        with prepared as source:
            target = f"https://app.coderpad.io/dashboard/questions/all/{question_id}"
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
    except CoderPadError as error:
        # Response bodies can contain secrets; only report the status.
        msg = f"CoderPad rejected the upload (HTTP {error.status_code})."
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
