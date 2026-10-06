"""Explicit variant edits with omission and reset actions."""

import json
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from pathlib import Path

import click
from coderpad.client import CoderPad
from coderpad.transports import Transport
from coderpad.types import QuestionVariantFileContent, QuestionVariantUnset
from pydantic import TypeAdapter, ValidationError

from coderpad_cli._sources import (
    PreparedSource,
    prepare_source,
    reject_symlinks,
    require_regular_file,
)


@dataclass(frozen=True, kw_only=True)
class VariantOverlay:
    """Validated JSON with exact supplied fields and paths for a plan."""

    json: str
    paths: tuple[str, ...]


def optional_text(path: Path | None) -> str | None:
    """Read regular UTF-8 input without translating newlines."""
    if path is None:
        return None
    reject_symlinks(path=path.absolute())
    require_regular_file(path=path)
    return path.read_bytes().decode(encoding="utf-8")


def optional_overlay(path: Path | None) -> VariantOverlay | None:
    """Validate project overlays without inventing omitted contents."""
    text = optional_text(path=path)
    if text is None:
        return None
    adapter = TypeAdapter(type=list[QuestionVariantFileContent])
    try:
        files = adapter.validate_json(text)
    except ValidationError:
        message = "Project file JSON must be an array of valid file entries."
        raise click.UsageError(message=message) from None
    return VariantOverlay(
        json=json.dumps(
            obj=[
                file.model_dump(exclude_unset=True, exclude_none=True)
                for file in files
            ]
        ),
        paths=tuple(file.path for file in files),
    )


@dataclass(frozen=True, kw_only=True)
class VariantInputs:
    """Local inputs and explicit reset choices for a variant edit."""

    source_file: Path | None
    directory: Path | None
    file_contents_json: Path | None
    solution_file: Path | None
    language: str | None
    exclude: tuple[str, ...]
    reset_code: bool
    reset_project: bool

    def validate(self) -> None:
        """Reject conflicting or empty edits before credentials and
        I/O.
        """
        content_choices = sum(
            (
                self.source_file is not None,
                self.directory is not None,
                self.file_contents_json is not None,
                self.reset_code,
                self.reset_project,
            )
        )
        if content_choices > 1:
            message = "Choose at most one content input or reset action."
            raise click.UsageError(message=message)
        if (
            content_choices == 0
            and self.language is None
            and self.solution_file is None
        ):
            message = (
                "Provide a language, solution, content input, or reset action."
            )
            raise click.UsageError(message=message)
        if len(self.exclude) > 0 and self.directory is None:
            message = "--exclude requires --directory."
            raise click.UsageError(message=message)
        if self.language is not None and (
            self.language == "" or self.language.strip() != self.language
        ):
            message = "Provide a nonempty language or project-template slug."
            raise click.BadParameter(message=message, param_hint="--language")

    def prepared(self) -> AbstractContextManager[PreparedSource]:
        """Keep local preparation alive until the mutation has
        finished.
        """
        if self.directory is not None or self.source_file is not None:
            return prepare_source(
                directory=self.directory,
                file=self.source_file,
                excludes=self.exclude,
            )
        return nullcontext(
            enter_result=PreparedSource(
                contents=None, directory=None, files=()
            )
        )


@dataclass(frozen=True, kw_only=True)
class VariantCreation:
    """Creation identity and optional local metadata inputs."""

    question_id: str
    language: str
    solution_file: Path | None
    file_contents_json: Path | None


@dataclass(frozen=True, kw_only=True)
class VariantEdit:
    """A prepared edit and descriptive actions for an offline plan."""

    contents: str | QuestionVariantUnset | None
    file_contents: list[QuestionVariantFileContent] | str | None
    solution: str | None
    paths: tuple[str, ...]
    action: str
    kind: str | None


def prepare_edit(
    *, inputs: VariantInputs, source: PreparedSource
) -> VariantEdit:
    """Decode all local inputs before credentials or requests are
    needed.
    """
    solution = optional_text(path=inputs.solution_file)
    overlay = optional_overlay(path=inputs.file_contents_json)
    contents: str | QuestionVariantUnset | None = QuestionVariantUnset.OMITTED
    files: list[QuestionVariantFileContent] | str | None = None
    paths = source.files
    action = "omit"
    kind: str | None = None
    if inputs.reset_code:
        contents = None
        action, kind = "reset", "single_file"
    elif inputs.reset_project:
        files = []
        action, kind = "reset", "project"
    elif overlay is not None:
        files = overlay.json
        paths = overlay.paths
        action, kind = ("replace" if len(paths) > 0 else "reset"), "project"
    elif source.directory is not None:
        files = [
            QuestionVariantFileContent(
                path=path,
                contents=(source.directory / path)
                .read_bytes()
                .decode(encoding="utf-8"),
            )
            for path in source.files
        ]
        action, kind = "replace", "project"
    elif source.contents is not None:
        contents = source.contents
        action, kind = "replace", "single_file"
    return VariantEdit(
        contents=contents,
        file_contents=files,
        solution=solution,
        paths=paths,
        action=action,
        kind=kind,
    )


def register_variant_update(
    *,
    group: click.Group,
    transport: Transport | None,
    validate_id: Callable[[str, str], None],
    api_key: Callable[[], str],
    request_errors: Callable[[str], AbstractContextManager[None]],
) -> None:
    """Register one opt-in edit command through the released SDK."""

    @click.argument("question_id")
    @click.argument("variant_id")
    @click.option("--language", help="Language or project-template slug.")
    @click.option(
        "--solution-file",
        type=click.Path(path_type=Path, readable=False),
        help="UTF-8 reference solution.",
    )
    @click.option(
        "--file",
        "source_file",
        type=click.Path(path_type=Path, readable=False),
        help="UTF-8 starter code, including blank code.",
    )
    @click.option(
        "--directory",
        type=click.Path(path_type=Path, readable=False),
        help="UTF-8 project directory.",
    )
    @click.option(
        "--file-contents-json",
        type=click.Path(path_type=Path, readable=False),
        help="Structured project files with hidden/deleted flags.",
    )
    @click.option(
        "--reset-code",
        is_flag=True,
        help="Restore single-file default code using explicit null.",
    )
    @click.option(
        "--reset-project",
        is_flag=True,
        help="Restore project template files using an empty list.",
    )
    @click.option(
        "--exclude",
        multiple=True,
        help="Additional directory Gitignore pattern. Repeatable.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print a JSON plan without credentials or network access.",
    )
    def update(  # noqa: PLR0913 - Each argument is a distinct Click option.
        question_id: str,
        variant_id: str,
        *,
        language: str | None,
        solution_file: Path | None,
        source_file: Path | None,
        directory: Path | None,
        file_contents_json: Path | None,
        exclude: tuple[str, ...],
        reset_code: bool,
        reset_project: bool,
        dry_run: bool,
    ) -> None:
        """Edit a variant, preserving omitted fields and explicit
        resets.
        """
        validate_id("QUESTION_ID", question_id)
        validate_id("VARIANT_ID", variant_id)
        inputs = VariantInputs(
            source_file=source_file,
            directory=directory,
            file_contents_json=file_contents_json,
            solution_file=solution_file,
            language=language,
            exclude=exclude,
            reset_code=reset_code,
            reset_project=reset_project,
        )
        inputs.validate()
        with request_errors("variant update"), inputs.prepared() as source:
            edit = prepare_edit(inputs=inputs, source=source)
            plan: dict[str, object] = {
                "operation": "update_variant",
                "question_id": int(question_id),
                "variant_id": int(variant_id),
                "content": {
                    "action": edit.action,
                    "kind": edit.kind,
                    "files": edit.paths,
                },
            }
            if language is not None:
                plan["language"] = language
            if solution_file is not None:
                plan["solution_file"] = str(object=solution_file)
            if dry_run:
                click.echo(message=json.dumps(obj=plan))
                return
            with CoderPad(api_key=api_key(), transport=transport) as client:
                try:
                    variant = client.questions.variants.update(
                        question_id=question_id,
                        variant_id=variant_id,
                        language=language,
                        solution=edit.solution,
                        contents=edit.contents,
                        file_contents=edit.file_contents,
                    )
                except ValueError:
                    message = (
                        "CoderPad returned an invalid variant response. "
                        "Update may have succeeded. Check before retrying."
                    )
                    raise click.ClickException(message=message) from None
            click.echo(
                message=json.dumps(
                    obj={
                        "question_id": int(question_id),
                        "variant_id": variant.id,
                    }
                )
            )

    _ = group.command(name="update")(update)
