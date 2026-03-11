import click

from . import __version__


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "--version", "-V")
def main() -> None:
    """Brownfield Cartographer CLI."""


@main.command("hello")
@click.option("--name", default="world", show_default=True)
def hello(name: str) -> None:
    """Sanity-check command."""

    click.echo(f"Hello, {name}!")
