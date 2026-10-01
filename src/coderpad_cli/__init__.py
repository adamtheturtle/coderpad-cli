"""Upload starter code using the released CoderPad SDK."""

import os
from importlib.metadata import version
from pathlib import Path

import click
import httpx
from coderpad.client import CoderPad
from coderpad.exceptions import CoderPadError
from coderpad.transports import Transport

from coderpad_cli._sources import prepare_source


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
    def upload(
        question_id: str,
        directory: Path | None,
        source_file: Path | None,
        exclude: tuple[str, ...],
        *,
        dry_run: bool,
    ) -> None:
        """Replace starter code while preserving question metadata."""
        _upload(
            question_id=question_id,
            directory=directory,
            source_file=source_file,
            exclude=exclude,
            dry_run=dry_run,
            transport=transport,
        )

    _ = questions.command()(upload)
    return cli


def _validate_upload(
    question_id: str,
    directory: Path | None,
    source_file: Path | None,
    exclude: tuple[str, ...],
) -> None:
    """Validate command combinations and the question identifier."""
    if (directory is None) == (source_file is None):
        msg = "Provide exactly one of --directory or --file."
        raise click.UsageError(message=msg)
    if (
        not question_id.isascii()
        or not question_id.isdecimal()
        or int(question_id) < 1
    ):
        msg = "QUESTION_ID must be a positive decimal integer."
        raise click.BadParameter(message=msg, param_hint="QUESTION_ID")
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


def _upload(  # noqa: PLR0913 - Click options plus the SDK transport boundary.
    question_id: str,
    directory: Path | None,
    source_file: Path | None,
    exclude: tuple[str, ...],
    *,
    dry_run: bool,
    transport: Transport | None,
) -> None:
    """Prepare input, call the SDK if requested, and report safe
    errors.
    """
    _validate_upload(
        question_id=question_id,
        directory=directory,
        source_file=source_file,
        exclude=exclude,
    )
    try:
        with prepare_source(
            directory=directory, file=source_file, excludes=exclude
        ) as source:
            target = f"https://app.coderpad.io/dashboard/questions/all/{question_id}"
            if dry_run:
                click.echo(message=f"Would update {target}")
                for path in source.files:
                    click.echo(message=f"  {path}")
                return
            api_key = _api_key()
            with CoderPad(api_key=api_key, transport=transport) as client:
                client.questions.update(
                    question_id=question_id,
                    contents=source.contents,
                    directory=source.directory,
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
