"""Variant discovery and explicit deletion through the SDK boundary."""

import json
from collections.abc import Callable, Generator
from contextlib import AbstractContextManager, contextmanager

import click
from coderpad.client import CoderPad
from coderpad.transports import Transport


def register_variant_commands(
    *,
    group: click.Group,
    transport: Transport | None,
    validate_id: Callable[[str, str], None],
    api_key: Callable[[], str],
    request_errors: Callable[[str], AbstractContextManager[None]],
) -> None:
    """Register question-scoped reads and a deletion command."""

    @click.argument("question_id")
    def list_variants(question_id: str) -> None:
        """List a question's variants as JSON, including template identity."""
        validate_id("QUESTION_ID", question_id)
        with (
            _variant_response_errors(
                operation="variant listing", request_errors=request_errors
            ),
            CoderPad(api_key=api_key(), transport=transport) as client,
        ):
            variants = client.questions.variants.list(question_id=question_id)
        click.echo(
            message=json.dumps(
                obj={
                    "question_id": int(question_id),
                    "variants": [
                        variant.model_dump(mode="json") for variant in variants
                    ],
                }
            )
        )

    @click.argument("question_id")
    @click.argument("variant_id")
    def get_variant(question_id: str, variant_id: str) -> None:
        """Get one variant as JSON without changing it."""
        validate_id("QUESTION_ID", question_id)
        validate_id("VARIANT_ID", variant_id)
        with (
            _variant_response_errors(
                operation="variant retrieval", request_errors=request_errors
            ),
            CoderPad(api_key=api_key(), transport=transport) as client,
        ):
            variant = client.questions.variants.get(
                question_id=question_id, variant_id=variant_id
            )
        click.echo(message=variant.model_dump_json())

    @click.argument("question_id")
    @click.argument("variant_id")
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print a JSON plan without credentials or network access.",
    )
    def delete_variant(
        question_id: str, variant_id: str, *, dry_run: bool
    ) -> None:
        """Delete only this variant. Mutations are never retried."""
        validate_id("QUESTION_ID", question_id)
        validate_id("VARIANT_ID", variant_id)
        result = {
            "operation": "delete_variant",
            "question_id": int(question_id),
            "variant_id": int(variant_id),
        }
        if not dry_run:
            with (
                request_errors("variant deletion"),
                CoderPad(api_key=api_key(), transport=transport) as client,
            ):
                client.questions.variants.delete(
                    question_id=question_id, variant_id=variant_id
                )
        click.echo(message=json.dumps(obj=result))

    _ = group.command(name="list")(list_variants)
    _ = group.command(name="get")(get_variant)
    _ = group.command(name="delete")(delete_variant)


@contextmanager
def _variant_response_errors(
    *,
    operation: str,
    request_errors: Callable[[str], AbstractContextManager[None]],
) -> Generator[None]:
    """Keep malformed response data out of command error output."""
    with request_errors(operation):
        try:
            yield
        except ValueError:
            msg = "CoderPad returned an invalid variant response."
            raise click.ClickException(message=msg) from None
