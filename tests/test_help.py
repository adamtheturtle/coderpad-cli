"""Keep public help text and the binary entry point stable."""

import runpy
from collections.abc import Sequence
from pathlib import Path

import pytest
from click.testing import CliRunner
from pytest_regressions.file_regression import FileRegressionFixture

from coderpad_cli import main


def _argument_id(arguments: Sequence[str], /) -> str:
    """Name a command by its argument path."""
    command_path = "-".join(arguments)
    return "root" if command_path == "" else command_path


@pytest.mark.parametrize(
    argnames="arguments",
    argvalues=[
        [],
        ["questions"],
        ["questions", "upload"],
        ["questions", "get"],
        ["languages"],
        ["languages", "list"],
        ["languages", "get"],
        ["pads"],
        ["pads", "create"],
        ["user"],
        ["user", "get"],
        ["screen"],
        ["screen", "campaigns"],
        ["screen", "campaigns", "list"],
        ["screen", "campaigns", "get"],
        ["questions", "variants"],
        ["questions", "variants", "create"],
        ["questions", "variants", "list"],
        ["questions", "variants", "get"],
        ["questions", "variants", "delete"],
        ["questions", "variants", "update"],
    ],
    ids=_argument_id,
)
def test_help(
    arguments: list[str], file_regression: FileRegressionFixture
) -> None:
    """Compare all command help text with reviewed snapshots."""
    result = CliRunner().invoke(
        cli=main,
        args=[*arguments, "--help"],
        catch_exceptions=False,
        color=True,
    )
    assert result.exit_code == 0, (result.stdout, result.stderr)
    file_regression.check(contents=result.output)


def test_wrapper_does_not_run_on_import() -> None:
    """Importing the binary wrapper must not execute the command."""
    wrapper = Path(__file__).parent.parent / "bin" / "coderpad_wrapper.py"
    namespace = runpy.run_path(
        path_name=str(object=wrapper), run_name="not_main"
    )
    assert namespace["main"] is main
