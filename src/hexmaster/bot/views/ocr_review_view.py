# Copyright (c) 2024-2025 Gary Kuepper
# Licensed under the MIT License.

import discord
from discord.ui import Modal, TextInput, View, button


def build_review_embed(draft_payload: dict, status_msg: str | None = None, is_committed: bool = False) -> discord.Embed:
    """Builds a formatted embed previewing the OCR-detected snapshot draft."""
    town = draft_payload.get("town", "Unknown").title()
    struct_type = draft_payload.get("struct_type", "Unknown")
    stockpile_name = draft_payload.get("stockpile_name", "Public")
    items = draft_payload.get("items", [])

    color = discord.Color.green() if is_committed else discord.Color.blue()
    title = status_msg if status_msg else f"🔍 Intelligence Report Preview — {town}"

    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="Structure", value=struct_type, inline=True)
    embed.add_field(name="Stockpile", value=stockpile_name, inline=True)
    embed.add_field(name="Items Count", value=str(len(items)), inline=True)

    if items:
        table_header = f"{'Item':<22} | {'Form':<7} | {'Qty':<6} | {'Total':<6}\n" + "-" * 50 + "\n"
        table_lines = []
        for item in items[:15]:
            name = item.get("item_name", "Unknown")[:20]
            form = "Crate" if item.get("is_crated") else "Loose"
            qty = item.get("quantity", 0)
            total = item.get("total", 0)
            table_lines.append(f"{name:<22} | {form:<7} | {qty:<6} | {total:<6}")

        table_str = f"```\n{table_header}" + "\n".join(table_lines) + "\n```"
        if len(items) > 15:
            table_str += f"\n*+ {len(items) - 15} additional item(s)*"
        embed.add_field(name="Detected Items", value=table_str, inline=False)
    else:
        embed.add_field(name="Detected Items", value="*No items detected*", inline=False)

    if not is_committed:
        embed.set_footer(text="Review items above. Click Confirm to save or Edit to adjust quantities.")

    return embed


class OCREditModal(Modal, title="Edit OCR Detected Quantities"):
    def __init__(self, draft_payload: dict, parent_view: "OCRReviewView"):
        super().__init__()
        self.draft_payload = draft_payload
        self.parent_view = parent_view
        self.inputs: list[tuple[dict, TextInput]] = []

        items = draft_payload.get("items", [])[:5]  # Discord limits modals to 5 inputs
        for item in items:
            name = item.get("item_name", "Item")[:40]
            curr_qty = str(item.get("quantity", 0))
            txt_input: TextInput = TextInput(
                label=f"{name} ({'Crated' if item.get('is_crated') else 'Loose'})",
                default=curr_qty,
                required=True,
                max_length=10,
            )
            self.add_item(txt_input)
            self.inputs.append((item, txt_input))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        for item, txt_input in self.inputs:
            try:
                new_qty = max(0, int(txt_input.value.strip()))
                item["quantity"] = new_qty
                per_crate = item.get("per_crate", 1) or 1
                if item.get("is_crated"):
                    item["total"] = new_qty * per_crate
                else:
                    item["total"] = new_qty
            except ValueError:
                pass  # Keep existing value if invalid integer input

        embed = build_review_embed(self.draft_payload, status_msg="✏️ Updated Quantities (Draft)")
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class OCRReviewView(View):
    def __init__(
        self,
        service,
        guild_id: int,
        draft_payload: dict,
        war_number: int | None = None,
        timeout: float = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.service = service
        self.guild_id = guild_id
        self.draft_payload = draft_payload
        self.war_number = war_number

    @button(label="Confirm & Save", style=discord.ButtonStyle.success, emoji="🟢", custom_id="ocr_review_confirm")
    async def confirm_button(self, interaction: discord.Interaction, btn: discord.ui.Button) -> None:
        await interaction.response.defer()
        try:
            snapshot_id, item_count, struct_type = await self.service.commit_snapshot_draft(
                self.guild_id, self.draft_payload, self.war_number
            )
            success_msg = f"✅ Snapshot #{snapshot_id} Saved ({item_count} items)"
            embed = build_review_embed(self.draft_payload, status_msg=success_msg, is_committed=True)

            for child in self.children:
                if hasattr(child, "disabled"):
                    setattr(child, "disabled", True)

            await interaction.edit_original_response(embed=embed, view=self)
        except Exception as e:
            await interaction.followup.send(f"Error saving snapshot: {str(e)}", ephemeral=True)

    @button(label="Edit Quantities", style=discord.ButtonStyle.primary, emoji="✏️", custom_id="ocr_review_edit")
    async def edit_button(self, interaction: discord.Interaction, btn: discord.ui.Button) -> None:
        modal = OCREditModal(self.draft_payload, self)
        await interaction.response.send_modal(modal)

    @button(label="Discard", style=discord.ButtonStyle.danger, emoji="❌", custom_id="ocr_review_discard")
    async def discard_button(self, interaction: discord.Interaction, btn: discord.ui.Button) -> None:
        for child in self.children:
            if hasattr(child, "disabled"):
                setattr(child, "disabled", True)

        embed = build_review_embed(self.draft_payload, status_msg="❌ Intelligence Report Discarded", is_committed=True)
        await interaction.response.edit_message(embed=embed, view=self)
