"""Create pads from a template, question, or staged starter code."""

import json
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path

import click
from coderpad import CoderPad
from coderpad.transports import Transport

from coderpad_cli._read_commands import required_key, response_errors
from coderpad_cli._sources import PreparedSource, prepare_source


def register_pad_commands(
    *,
    cli: click.Group,
    transport: Transport | None,
    request_errors: Callable[[str], AbstractContextManager[None]],
) -> None:
    """Register creation with preparation and preview before mutation."""

    @cli.group()
    def pads() -> None:
        """Create Interview pads."""

    @pads.command()
    @click.option("--title", help="Optional pad title.")
    @click.option(
        "--language", help="Single-file language key or project-template slug."
    )
    @click.option(
        "--question-id",
        type=click.IntRange(min=1),
        help="Seed from an existing question.",
    )
    @click.option(
        "--directory",
        type=click.Path(path_type=Path, readable=False),
        help="Project directory, respecting Git ignores.",
    )
    @click.option(
        "--file",
        "source_file",
        type=click.Path(path_type=Path, readable=False),
        help="Single-file starter code.",
    )
    @click.option(
        "--exclude",
        multiple=True,
        help="Additional directory exclusion. Repeatable.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Validate and preview without credentials or network access.",
    )
    def create(  # noqa: PLR0913 - Click passes independent options by name.
        *,
        title: str | None,
        language: str | None,
        question_id: int | None,
        directory: Path | None,
        source_file: Path | None,
        exclude: tuple[str, ...],
        dry_run: bool,
    ) -> None:
        """Create a pad and print its JSON response."""
        if (
            sum(
                value is not None
                for value in (question_id, directory, source_file)
            )
            > 1
        ):
            raise click.UsageError(message="Use only one content source.")
        if len(exclude) > 0 and directory is None:
            raise click.UsageError(message="--exclude requires --directory.")
        if language is not None and (
            language.strip() == "" or language.strip() != language
        ):
            raise click.BadParameter(
                message="Use a nonempty environment identifier.",
                param_hint="--language",
            )
        prepared = (
            prepare_source(
                directory=directory, file=source_file, excludes=exclude
            )
            if directory is not None or source_file is not None
            else nullcontext(
                enter_result=PreparedSource(
                    contents=None, directory=None, files=()
                )
            )
        )
        with (
            response_errors(
                operation="pad creation", request_errors=request_errors
            ),
            prepared as source,
        ):
            if dry_run:
                click.echo(
                    message=json.dumps(
                        obj={
                            "dry_run": True,
                            "method": "POST",
                            "path": "/api/pads/",
                            "title": title,
                            "language": language,
                            "question_id": question_id,
                            "files": list(source.files),
                            "contents": source.contents,
                        }
                    )
                )
                return
            with CoderPad(
                api_key=required_key(name="CODERPAD_API_KEY"),
                transport=transport,
            ) as client:
                result = client.pads.create(
                    title=title,
                    language=language,
                    question_id=question_id,
                    contents=source.contents,
                    directory=source.directory,
                )
            click.echo(message=result.model_dump_json())
