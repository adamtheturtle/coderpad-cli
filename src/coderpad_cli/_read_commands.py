"""Read Interview resources and Screen campaigns through the SDK."""

import json
import os
from collections.abc import Callable, Generator
from contextlib import AbstractContextManager, contextmanager

import click
from coderpad import SCREEN_EU_BASE_URL, SCREEN_US_BASE_URL, CoderPad
from coderpad.transports import JSONTransport, Transport


def register_read_commands(
    *,
    cli: click.Group,
    questions: click.Group,
    transport: Transport | None,
    screen_transport: JSONTransport | None,
    request_errors: Callable[[str], AbstractContextManager[None]],
) -> None:
    """Register JSON reads without changing any remote resource."""

    @click.argument("question_id", type=click.IntRange(min=1))
    def get_question(question_id: int) -> None:
        """Get a question, including starter files and template
        metadata.
        """
        with (
            _response_errors(
                operation="question retrieval", request_errors=request_errors
            ),
            CoderPad(
                api_key=_required_key(name="CODERPAD_API_KEY"),
                transport=transport,
            ) as client,
        ):
            result = client.questions.get(question_id=str(object=question_id))
        click.echo(message=result.model_dump_json())

    @cli.group()
    def user() -> None:
        """Inspect the Interview API key owner."""

    def get_user() -> None:
        """Get the key owner's name, anonymous ID, and pad capability."""
        with (
            _response_errors(
                operation="user retrieval", request_errors=request_errors
            ),
            CoderPad(
                api_key=_required_key(name="CODERPAD_API_KEY"),
                transport=transport,
            ) as client,
        ):
            result = client.user.get()
        click.echo(message=result.model_dump_json())

    @cli.group()
    def screen() -> None:
        """Inspect Screen using CODERPAD_SCREEN_API_KEY."""

    @screen.group()
    def campaigns() -> None:
        """Inspect reusable assessment campaign definitions."""

    @click.option(
        "--region",
        type=click.Choice(choices=["us", "eu"]),
        default="us",
        show_default=True,
        help="Screen server region.",
    )
    def list_campaigns(region: str) -> None:
        """List campaigns as JSON to discover their IDs."""
        with (
            _response_errors(
                operation="campaign listing", request_errors=request_errors
            ),
            _screen_client(
                region=region, transport=screen_transport
            ) as client,
        ):
            result = client.screen.campaigns.list()
        click.echo(
            message=json.dumps(
                obj=[item.model_dump(mode="json") for item in result]
            )
        )

    @click.argument("campaign_id", type=click.IntRange(min=1))
    @click.option(
        "--region",
        type=click.Choice(choices=["us", "eu"]),
        default="us",
        show_default=True,
        help="Screen server region.",
    )
    def get_campaign(campaign_id: int, region: str) -> None:
        """Get ordered questions, settings, and team identity as JSON."""
        with (
            _response_errors(
                operation="campaign retrieval", request_errors=request_errors
            ),
            _screen_client(
                region=region, transport=screen_transport
            ) as client,
        ):
            result = client.screen.campaigns.get(campaign_id=campaign_id)
        click.echo(message=result.model_dump_json())

    _ = questions.command(name="get")(get_question)
    _ = user.command(name="get")(get_user)
    _ = campaigns.command(name="list")(list_campaigns)
    _ = campaigns.command(name="get")(get_campaign)


def _required_key(name: str) -> str:
    """Require the correct product's key without exposing its value."""
    key = os.environ.get(key=name)
    if key is None or key.strip() == "":
        msg = f"{name} is missing or empty. Set it in the environment."
        raise click.ClickException(message=msg)
    return key


def _screen_client(
    *, region: str, transport: JSONTransport | None
) -> CoderPad:
    """Use the independent Screen key on a documented server origin."""
    return CoderPad(
        api_key="",
        screen_api_key=_required_key(name="CODERPAD_SCREEN_API_KEY"),
        screen_base_url=SCREEN_EU_BASE_URL
        if region == "eu"
        else SCREEN_US_BASE_URL,
        screen_transport=transport,
    )


@contextmanager
def _response_errors(
    *,
    operation: str,
    request_errors: Callable[[str], AbstractContextManager[None]],
) -> Generator[None]:
    """Keep malformed response contents out of error output."""
    with request_errors(operation):
        try:
            yield
        except (ValueError, TypeError, KeyError):
            msg = "CoderPad returned an invalid resource response."
            raise click.ClickException(message=msg) from None
