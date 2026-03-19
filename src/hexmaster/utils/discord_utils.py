# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.
"""Utility functions for Discord interactions, including table rendering and paging."""

from typing import Any, List, Optional

import discord
from tabulate import tabulate

DISCORD_CHARACTER_LIMIT = 2000
EMBED_COLOR_SUCCESS = 0x2ECC71  # Green
EMBED_COLOR_ERROR = 0xE74C3C  # Red
EMBED_COLOR_INFO = 0x3498DB  # Blue


class PaginatorView(discord.ui.View):
    """A Discord view that provides pagination for long text content."""

    def __init__(
        self,
        pages: List[str],
        title: str,
        color: int,
        ephemeral: bool,
        interaction: discord.Interaction,
    ) -> None:
        """Initializes the PaginatorView."""
        super().__init__(timeout=300)
        self.pages = pages
        self.title = title
        self.color = color
        self.ephemeral = ephemeral
        self.interaction = interaction
        self.current_page = 0
        self._update_buttons()

    def _update_buttons(self) -> None:
        """Enables/disables buttons based on the current page."""
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page == len(self.pages) - 1

    async def _update_message(self, interaction: discord.Interaction) -> None:
        """Updates the message with the content of the current page."""
        embed = self._create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    def _create_embed(self) -> discord.Embed:
        """Creates an embed for the current page."""
        indicator = f" (Page {self.current_page + 1}/{len(self.pages)})" if len(self.pages) > 1 else ""
        return discord.Embed(
            title=f"{self.title}{indicator}",
            description=f"```ansi\n{self.pages[self.current_page]}\n```",
            color=self.color,
        )

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.gray)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Handles the 'Previous' button click."""
        self.current_page -= 1
        self._update_buttons()
        await self._update_message(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.gray)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Handles the 'Next' button click."""
        self.current_page += 1
        self._update_buttons()
        await self._update_message(interaction)


async def render_and_truncate_table(
    interaction: discord.Interaction,
    rows: List[List[Any]],
    headers: List[str],
    title: str,
    ephemeral: bool = True,
    as_embed: bool = True,
    color: Optional[int] = None,
    row_colors: Optional[List[str]] = None,
    max_rows: int = 20,
) -> None:
    """Renders a table using ANSI colors in a monospaced code block with pagination."""
    if not rows:
        await send_success(interaction, "No data to display.", title=title, ephemeral=ephemeral)
        return

    # Discord Description Limit is 4096. Use 3800 for safety.
    desc_limit = 3800
    full_table_str = tabulate(rows, headers=headers, tablefmt="simple")
    lines = full_table_str.split("\n")
    header_str = "\n".join([f"\u001b[1;37m{line}\u001b[0m" for line in lines[:2]]) + "\n"
    data_lines = lines[2:]

    pages = []
    current_page_lines: List[str] = []
    current_len = len(header_str)
    current_row_count = 0

    for i, line in enumerate(data_lines):
        colored_line = line
        if row_colors and i < len(row_colors) and row_colors[i]:
            colored_line = f"\u001b[0;{row_colors[i]}m{line}\u001b[0m"

        line_len = len(colored_line) + 1
        if current_page_lines and (current_len + line_len > desc_limit or current_row_count >= max_rows):
            pages.append(header_str + "\n".join(current_page_lines))
            current_page_lines = []
            current_len = len(header_str)
            current_row_count = 0

        current_page_lines.append(colored_line)
        current_len += line_len
        current_row_count += 1

    if current_page_lines:
        pages.append(header_str + "\n".join(current_page_lines))

    target_color = color or EMBED_COLOR_INFO
    if as_embed:
        await _send_embed_table(interaction, pages, title, target_color, ephemeral)
    else:
        msg = f"**{title}**\n```ansi\n{pages[0]}\n```"
        await send_response(interaction, content=msg, ephemeral=ephemeral)


async def _send_embed_table(
    interaction: discord.Interaction,
    pages: List[str],
    title: str,
    color: int,
    ephemeral: bool,
) -> None:
    """Helper to send the table as an embed, potentially with pagination."""
    if len(pages) > 1:
        view = PaginatorView(pages, title, color, ephemeral, interaction)
        embed = view._create_embed()
        await send_response(interaction, embed=embed, view=view, ephemeral=ephemeral)
    else:
        # Standardize title replacement
        clean_title = title.replace("**", "").replace("__", "").split("\n")[0]
        embed = discord.Embed(
            title=clean_title,
            description=f"```ansi\n{pages[0]}\n```",
            color=color,
        )
        await send_response(interaction, embed=embed, ephemeral=ephemeral)


async def send_response(
    interaction: discord.Interaction,
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    view: Optional[discord.ui.View] = None,
    ephemeral: bool = True,
) -> None:
    """Helper to handle response vs followup for Discord interactions."""
    kwargs: dict[str, Any] = {"ephemeral": ephemeral}
    if content:
        kwargs["content"] = content
    if embed:
        kwargs["embed"] = embed
    if view:
        kwargs["view"] = view

    if interaction.response.is_done():
        await interaction.followup.send(**kwargs)
    else:
        await interaction.response.send_message(**kwargs)


async def send_success(
    interaction: discord.Interaction,
    message: str,
    title: str = "Success",
    ephemeral: bool = True,
) -> None:
    """Sends a standardized success message."""
    embed = discord.Embed(title=f"✅ {title}", description=message, color=EMBED_COLOR_SUCCESS)
    await send_response(interaction, embed=embed, ephemeral=ephemeral)


async def send_error(
    interaction: discord.Interaction,
    message: str,
    title: str = "Error",
    ephemeral: bool = True,
) -> None:
    """Sends a standardized error message."""
    embed = discord.Embed(title=f"❌ {title}", description=message, color=EMBED_COLOR_ERROR)
    await send_response(interaction, embed=embed, ephemeral=ephemeral)
