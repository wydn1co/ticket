import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv
import database
import asyncio

load_dotenv()

class TicketBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix=".", intents=intents, help_command=None)

    async def setup_hook(self):
        await database.init_db()
        self.add_view(TicketPanelView())
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} commands globally.")
        except Exception as e:
            print(f"Failed to sync commands: {e}")
        print(f"Logged in as {self.user}")

    async def on_ready(self):
        print(f"Bot is ready. Prefix: {self.command_prefix}")

bot = TicketBot()

# --- Views ---

class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Purchase 💰", style=discord.ButtonStyle.green, custom_id="persistent:purchase")
    async def purchase(self, interaction: discord.Interaction, button: discord.ui.Button):
        await create_ticket(interaction, "purchase")

    @discord.ui.button(label="Support ❓", style=discord.ButtonStyle.blurple, custom_id="persistent:support")
    async def support(self, interaction: discord.Interaction, button: discord.ui.Button):
        await create_ticket(interaction, "support")

class SetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)
        self.panel_channel = None
        self.purchase_category = None
        self.support_category = None
        self.staff_role = None

    def update_embed(self):
        embed = discord.Embed(
            title="Ticket Bot Interactive Setup",
            description="Please select the required channels and roles using the menus below.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Panel Channel", value=self.panel_channel.mention if self.panel_channel else "Not selected", inline=True)
        embed.add_field(name="Staff Role", value=self.staff_role.mention if self.staff_role else "Not selected", inline=True)
        embed.add_field(name="Purchase Category", value=self.purchase_category.name if self.purchase_category else "Not selected", inline=False)
        embed.add_field(name="Support Category", value=self.support_category.name if self.support_category else "Not selected", inline=False)
        return embed

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Select Panel Channel", channel_types=[discord.ChannelType.text])
    async def select_panel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        self.panel_channel = select.values[0]
        await interaction.response.edit_message(embed=self.update_embed(), view=self)

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Select Purchase Category", channel_types=[discord.ChannelType.category])
    async def select_purchase(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        self.purchase_category = select.values[0]
        await interaction.response.edit_message(embed=self.update_embed(), view=self)

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Select Support Category", channel_types=[discord.ChannelType.category])
    async def select_support(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        self.support_category = select.values[0]
        await interaction.response.edit_message(embed=self.update_embed(), view=self)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Select Staff Role")
    async def select_role(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        self.staff_role = select.values[0]
        await interaction.response.edit_message(embed=self.update_embed(), view=self)

    @discord.ui.button(label="Confirm Setup", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not all([self.panel_channel, self.purchase_category, self.support_category, self.staff_role]):
            return await interaction.response.send_message("❌ Please complete all selections first!", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        
        try:
            await database.update_settings(
                interaction.guild_id,
                panel_channel_id=self.panel_channel.id,
                purchase_category_id=self.purchase_category.id,
                support_category_id=self.support_category.id,
                staff_role_id=self.staff_role.id
            )

            # Send panel
            embed = discord.Embed(
                title="Open a Ticket",
                description="Click the buttons below to open a ticket for Purchase or Support.",
                color=discord.Color.blue()
            )
            await self.panel_channel.send(embed=embed, view=TicketPanelView())

            await interaction.followup.send(f"✅ Setup complete! Panel sent to {self.panel_channel.mention}", ephemeral=True)
            self.stop()
        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred: {e}", ephemeral=True)

class ProductSelectionView(discord.ui.View):
    def __init__(self, products):
        super().__init__(timeout=None)
        self.products = products
        options = [
            discord.SelectOption(label=f"{p[2]} - ${p[3]}", value=str(p[0]), description=p[5] if p[4] == 'text' else "Redirect link")
            for p in products
        ]
        self.add_item(ProductSelect(options))

class ProductSelect(discord.ui.Select):
    def __init__(self, options):
        super().__init__(placeholder="Select products to purchase...", min_values=1, max_values=len(options), options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_ids = [int(v) for v in self.values]
        all_products = await database.get_products(interaction.guild_id)
        selected_products = [p for p in all_products if p[0] in selected_ids]
        
        total_price = sum(p[3] for p in selected_products)
        
        embed = discord.Embed(title="Order Summary", color=discord.Color.green())
        description = ""
        view = discord.ui.View()
        for p in selected_products:
            description += f"**{p[2]}**: ${p[3]}"
            if p[4] == 'text':
                description += f"\n> *Info: {p[5]}*\n"
            else:
                description += "\n"
                view.add_item(discord.ui.Button(label=f"Link: {p[2]}", url=p[5]))
        
        description += f"\n**Total Order Amount: ${total_price:.2f}**"
        embed.description = description
        
        await interaction.response.send_message(embed=embed, view=view if len(view.children) > 0 else None, ephemeral=True)

async def create_ticket(interaction: discord.Interaction, ticket_type: str):
    guild_id = interaction.guild_id
    settings = await database.get_settings(guild_id)
    
    if not settings:
        return await interaction.response.send_message("Bot not set up! Please use /setup.", ephemeral=True)
    
    # settings: (guild_id, panel_channel_id, purchase_category_id, support_category_id, staff_role_id)
    category_id = settings[2] if ticket_type == "purchase" else settings[3]
    staff_role_id = settings[4]
    
    category = interaction.guild.get_channel(category_id)
    if not category:
        return await interaction.response.send_message("Category not found! Please check setup.", ephemeral=True)

    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    
    if staff_role_id:
        staff_role = interaction.guild.get_role(staff_role_id)
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    channel_name = f"{ticket_type}-{interaction.user.name}"
    channel = await interaction.guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites)
    
    await interaction.response.send_message(f"Ticket created: {channel.mention}", ephemeral=True)
    
    # Welcome message
    ping_str = f"<@&{staff_role_id}> " if staff_role_id else ""
    welcome_msg = f"{ping_str}{interaction.user.mention}, Support will be with you shortly!"
    
    if ticket_type == "purchase":
        products = await database.get_products(guild_id)
        if products:
            view = ProductSelectionView(products)
            embed = discord.Embed(title="Payment & Products", description="Select the products you wish to purchase below.", color=discord.Color.gold())
            await channel.send(welcome_msg, embed=embed, view=view)
        else:
            await channel.send(welcome_msg + "\n\n*No products configured yet.*")
    else:
        await channel.send(welcome_msg)

# --- Prefix Commands ---

@bot.command(name="help")
async def help_prefix(ctx):
    embed = discord.Embed(
        title="Ticket Bot Help",
        description="Here are the available commands. You can use either `.` prefix or `/` slash commands.",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="Setup",
        value="`.setup` - Opens an interactive form to configure categories, channels, and roles.",
        inline=False
    )
    
    embed.add_field(
        name="Products",
        value=(
            "`.buttons \"Name\" Price text/redirect \"Value\"`\n"
            "Adds a product. Example:\n"
            "`.buttons \"Pro Plan\" 10.0 text \"Access granted\"`"
        ),
        inline=False
    )
    
    embed.add_field(
        name="Sync",
        value="`.sync` - Syncs slash commands if they aren't showing up.",
        inline=False
    )
    
    await ctx.send(embed=embed)

@bot.command(name="setup")
async def setup_prefix(ctx):
    if not ctx.author.guild_permissions.administrator:
        return
    
    embed = discord.Embed(
        title="Ticket Bot Interactive Setup",
        description="Please select the required channels and roles using the menus below.",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed, view=SetupView())

@bot.command(name="buttons")
async def buttons_prefix(ctx, name: str, price: float, action_type: str, action_value: str):
    if not ctx.author.guild_permissions.administrator:
        return
    
    if action_type.lower() not in ['text', 'redirect']:
        return await ctx.send("❌ Action type must be either `text` or `redirect`.")
    
    await database.add_product(ctx.guild.id, name, price, action_type.lower(), action_value)
    await ctx.send(f"✅ Product '{name}' added successfully!")

# --- Slash Commands ---

@bot.tree.command(name="setup", description="Configure the ticket bot settings via an interactive form")
async def setup(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("You need Administrator permissions to use this command.", ephemeral=True)
    
    embed = discord.Embed(
        title="Ticket Bot Interactive Setup",
        description="Please select the required channels and roles using the menus below.",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed, view=SetupView(), ephemeral=True)

@bot.tree.command(name="panel", description="Send the ticket panel in the configured channel")
async def panel(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("You need Administrator permissions to use this command.", ephemeral=True)
    
    settings = await database.get_settings(interaction.guild_id)
    if not settings or not settings[1]:
        return await interaction.response.send_message("Panel channel not configured! Use /setup first.", ephemeral=True)
    
    channel = interaction.guild.get_channel(settings[1])
    if not channel:
        return await interaction.response.send_message("Configured panel channel not found!", ephemeral=True)
    
    embed = discord.Embed(
        title="Open a Ticket",
        description="Click the buttons below to open a ticket for Purchase or Support.",
        color=discord.Color.blue()
    )
    
    await channel.send(embed=embed, view=TicketPanelView())
    await interaction.response.send_message("Panel sent!", ephemeral=True)

@bot.tree.command(name="buttons", description="Manage product buttons")
@app_commands.choices(action_type=[
    app_commands.Choice(name="Text", value="text"),
    app_commands.Choice(name="Redirect", value="redirect")
])
async def buttons(interaction: discord.Interaction, name: str, price: float, action_type: str, action_value: str):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("You need Administrator permissions to use this command.", ephemeral=True)
    
    await database.add_product(interaction.guild_id, name, price, action_type, action_value)
    await interaction.response.send_message(f"Product '{name}' added successfully!", ephemeral=True)

@bot.command(name="sync")
async def sync_prefix(ctx):
    if not ctx.author.guild_permissions.administrator:
        return
    
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"Synced {len(synced)} slash commands globally!")
    except Exception as e:
        await ctx.send(f"Failed to sync: {e}")

@bot.tree.command(name="sync", description="Sync slash commands")
async def sync(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("You need Administrator permissions to use this command.", ephemeral=True)
    
    await bot.tree.sync()
    await interaction.response.send_message("Slash commands synced!", ephemeral=True)

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("Please provide a DISCORD_TOKEN in the .env file.")
