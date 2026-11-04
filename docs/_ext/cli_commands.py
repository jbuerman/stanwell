"""Generate CLI command documentation from the Typer application."""

from docutils import nodes
from docutils.parsers.rst import Directive

from stanwell.ui.cli.cli import app


class CliCommandsDirective(Directive):
    """Render registered Typer commands as a definition list."""

    has_content = False

    def run(self) -> list[nodes.Node]:
        """Build the definition list containing the registered CLI commands."""
        definition_list = nodes.definition_list()

        for command_info in app.registered_commands:
            command_name = command_info.name
            command_help = command_info.help
            callback = command_info.callback

            if command_name is None or callback is None:
                continue

            target = (
                f"{callback.__module__}."
                f"{callback.__name__}"
            )

            item = nodes.definition_list_item()
            term = nodes.term()

            reference_nodes, messages = self.state.inline_text(
                f":py:func:`{command_name} <{target}>`",
                self.lineno,
            )
            term.extend(reference_nodes)

            definition = nodes.definition()
            definition += nodes.paragraph(
                text=command_help or "",
            )

            item += term
            item += definition
            definition_list += item

            definition_list.extend(messages)

        return [definition_list]


def setup(app):
    """Register the CLI command directive."""
    app.add_directive(
        "cli-commands",
        CliCommandsDirective,
    )

    return {
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
