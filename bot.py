import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv
import database
import asyncio

load_dotenv()

async def refresh_panel(guild: discord.Guild):
    settings = await database.get_settings(guild.id)
    if not settings or not settings[1] or not settings[7]: # panel_channel_id and panel_message_id
        return

    channel = guild.get_channel(settings[1])
    if not channel:
        return

    try:
        message = await channel.fetch_message(settings[7])
        embed = discord.Embed(
            title="Open a Ticket",
            description="Click the buttons below to open a ticket for Purchase or Support.",
            color=discord.Color.blue()
        )
        await message.edit(embed=embed, view=TicketPanelView())
    except Exception:
        # Message might have been deleted, send a new one
        embed = discord.Embed(
            title="Open a Ticket",
            description="Click the buttons below to open a ticket for Purchase or Support.",
            color=discord.Color.blue()
        )
        new_msg = await channel.send(embed=embed, view=TicketPanelView())
        await database.update_settings(guild.id, panel_message_id=new_msg.id)

class TicketBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix=".", intents=intents, help_command=None)

    async def setup_hook(self):
        await database.init_db()
        self.add_view(TicketPanelView())
        self.add_view(ReviewPanelView())
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

class ReviewPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Post Review ⭐", style=discord.ButtonStyle.danger, custom_id="persistent:post_review")
    async def post_review(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = await database.get_settings(interaction.guild_id)
        if not settings or not settings[6]: # review_role_id
            return await interaction.response.send_message("Review system not fully set up!", ephemeral=True)
        
        review_role = interaction.guild.get_role(settings[6])
        if review_role not in interaction.user.roles:
            return await interaction.response.send_message(f"Only users with the {review_role.mention} role can post reviews!", ephemeral=True)
            
        await interaction.response.send_modal(ReviewModal())

class ReviewModal(discord.ui.Modal, title="Submit Your Review"):
    rating = discord.ui.TextInput(label="Rating (1-5)", placeholder="Enter 1, 2, 3, 4, or 5", min_length=1, max_length=1)
    feedback = discord.ui.TextInput(label="Feedback", placeholder="Tell us what you think...", style=discord.TextStyle.paragraph, min_length=10)
    image_url = discord.ui.TextInput(label="Image URL (Optional)", placeholder="Paste a link to an image...", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            rating_val = int(self.rating.value)
            if not 1 <= rating_val <= 5:
                raise ValueError()
        except ValueError:
            return await interaction.response.send_message("❌ Rating must be a number between 1 and 5!", ephemeral=True)

        settings = await database.get_settings(interaction.guild_id)
        channel_id = settings[5] # review_channel_id
        channel = interaction.guild.get_channel(channel_id)
        
        if not channel:
            return await interaction.response.send_message("❌ Review channel not found!", ephemeral=True)

        stars = "⭐" * rating_val
        embed = discord.Embed(title="New Review!", color=discord.Color.red())
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.add_field(name="Rating", value=stars, inline=False)
        embed.add_field(name="Feedback", value=self.feedback.value, inline=False)
        
        if self.image_url.value:
            embed.set_image(url=self.image_url.value)
            
        embed.set_footer(text=f"User ID: {interaction.user.id}")
        
        await channel.send(embed=embed, view=ReviewPanelView())
        await interaction.response.send_message("✅ Thank you for your review!", ephemeral=True)

class ReviewSetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)
        self.review_channel = None
        self.review_role = None

    def update_embed(self):
        embed = discord.Embed(
            title="Review System Setup",
            description="Select the channel where reviews will be posted and the role allowed to post them.",
            color=discord.Color.red()
        )
        channel_text = f"<#{self.review_channel.id}>" if self.review_channel else "Not selected"
        role_text = f"<@&{self.review_role.id}>" if self.review_role else "Not selected"
        embed.add_field(name="Post Channel", value=channel_text, inline=True)
        embed.add_field(name="Reviewer Role", value=role_text, inline=True)
        return embed

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Select Review Post Channel", channel_types=[discord.ChannelType.text])
    async def select_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        self.review_channel = select.values[0]
        await interaction.response.edit_message(embed=self.update_embed(), view=self)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Select Reviewer Role")
    async def select_role(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        self.review_role = select.values[0]
        await interaction.response.edit_message(embed=self.update_embed(), view=self)

    @discord.ui.button(label="Confirm Review Setup", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.review_channel or not self.review_role:
            return await interaction.response.send_message("Please select both a channel and a role!", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        
        try:
            await database.update_settings(
                interaction.guild_id,
                review_channel_id=self.review_channel.id,
                review_role_id=self.review_role.id
            )

            # Get actual channel
            actual_channel = interaction.guild.get_channel(self.review_channel.id)
            if not actual_channel:
                actual_channel = await interaction.guild.fetch_channel(self.review_channel.id)

            embed = discord.Embed(
                title="Customer Reviews",
                description="Have you purchased from us? Click the button below to leave a review!",
                color=discord.Color.red()
            )
            await actual_channel.send(embed=embed, view=ReviewPanelView())
            await interaction.followup.send(f"✅ Review system set up in {actual_channel.mention}!", ephemeral=True)
            self.stop()
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

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
        # AppCommandChannel doesn't always have .mention, use ID formatting instead
        panel_text = f"<#{self.panel_channel.id}>" if self.panel_channel else "Not selected"
        role_text = f"<@&{self.staff_role.id}>" if self.staff_role else "Not selected"
        purchase_text = f"<#{self.purchase_category.id}>" if self.purchase_category else "Not selected"
        support_text = f"<#{self.support_category.id}>" if self.support_category else "Not selected"

        embed.add_field(name="Panel Channel", value=panel_text, inline=True)
        embed.add_field(name="Staff Role", value=role_text, inline=True)
        embed.add_field(name="Purchase Category", value=purchase_text, inline=False)
        embed.add_field(name="Support Category", value=support_text, inline=False)
        return embed

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Select Panel Channel", channel_types=[discord.ChannelType.text])
    async def select_panel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        try:
            self.panel_channel = select.values[0]
            await interaction.response.edit_message(embed=self.update_embed(), view=self)
        except Exception as e:
            print(f"Error in select_panel: {e}")

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Select Purchase Category", channel_types=[discord.ChannelType.category])
    async def select_purchase(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        try:
            self.purchase_category = select.values[0]
            await interaction.response.edit_message(embed=self.update_embed(), view=self)
        except Exception as e:
            print(f"Error in select_purchase: {e}")

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Select Support Category", channel_types=[discord.ChannelType.category])
    async def select_support(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        try:
            self.support_category = select.values[0]
            await interaction.response.edit_message(embed=self.update_embed(), view=self)
        except Exception as e:
            print(f"Error in select_support: {e}")

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Select Staff Role")
    async def select_role(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        try:
            self.staff_role = select.values[0]
            await interaction.response.edit_message(embed=self.update_embed(), view=self)
        except Exception as e:
            print(f"Error in select_role: {e}")

    @discord.ui.button(label="Confirm Setup", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not all([self.panel_channel, self.purchase_category, self.support_category, self.staff_role]):
            return await interaction.response.send_message("❌ Please complete all selections first!", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get actual channel and category objects since select menus return partial objects
            actual_panel_channel = interaction.guild.get_channel(self.panel_channel.id)
            if not actual_panel_channel:
                actual_panel_channel = await interaction.guild.fetch_channel(self.panel_channel.id)

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
            panel_msg = await actual_panel_channel.send(embed=embed, view=TicketPanelView())

            await database.update_settings(
                interaction.guild_id,
                panel_message_id=panel_msg.id
            )

            await interaction.followup.send(f"✅ Setup complete! Panel sent to {actual_panel_channel.mention}", ephemeral=True)
            self.stop()
        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred: {e}", ephemeral=True)

class ProductModal(discord.ui.Modal, title="Add New Product"):
    category = discord.ui.TextInput(label="Category/Main Product", placeholder="e.g. Nitro", min_length=1, max_length=50)
    name = discord.ui.TextInput(label="Variant Name", placeholder="e.g. 1 Month", min_length=1, max_length=50)
    price = discord.ui.TextInput(label="Price", placeholder="e.g. 10.00", min_length=1)
    action_type = discord.ui.TextInput(label="Action Type (text or redirect)", placeholder="Type 'text' or 'redirect'", min_length=4, max_length=8)
    action_value = discord.ui.TextInput(label="Value", placeholder="The message text or the URL link", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price_val = float(self.price.value.replace('$', ''))
            a_type = self.action_type.value.lower().strip()
            
            if a_type not in ['text', 'redirect']:
                return await interaction.response.send_message("❌ Action type must be 'text' or 'redirect'!", ephemeral=True)

            await database.add_product(interaction.guild_id, self.category.value, self.name.value, price_val, a_type, self.action_value.value)
            await interaction.response.send_message(f"✅ Product '{self.name.value}' added to category '{self.category.value}' successfully!", ephemeral=True)
            await refresh_panel(interaction.guild)
        except ValueError:
            await interaction.response.send_message("❌ Invalid price! Please enter a number.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

class ProductDeleteView(discord.ui.View):
    def __init__(self, products):
        super().__init__(timeout=600)
        options = [
            discord.SelectOption(label=f"[{p[2]}] {p[3]} - ${p[4]}", value=str(p[0]))
            for p in products
        ]
        self.add_item(ProductDeleteSelect(options))

class ProductDeleteSelect(discord.ui.Select):
    def __init__(self, options):
        super().__init__(placeholder="Select a product to delete...", options=options)

    async def callback(self, interaction: discord.Interaction):
        product_id = int(self.values[0])
        await database.delete_product(product_id)
        await interaction.response.send_message("✅ Product deleted successfully!", ephemeral=True)
        await refresh_panel(interaction.guild)

class ProductSelectionView(discord.ui.View):
    def __init__(self, products):
        super().__init__(timeout=None)
        self.all_products = products
        self.categories = sorted(list(set(p[2] for p in products)))
        
        options = [discord.SelectOption(label=cat, value=cat) for cat in self.categories]
        self.add_item(CategorySelect(options, self.all_products))

class CategorySelect(discord.ui.Select):
    def __init__(self, options, all_products):
        super().__init__(placeholder="Select a product category...", options=options)
        self.all_products = all_products

    async def callback(self, interaction: discord.Interaction):
        selected_cat = self.values[0]
        variants = [p for p in self.all_products if p[2] == selected_cat]
        
        # Update the view to show variants
        new_view = discord.ui.View(timeout=None)
        variant_options = [
            discord.SelectOption(label=f"{v[3]} - ${v[4]}", value=str(v[0]), description=v[6] if v[5] == 'text' else "Redirect link")
            for v in variants
        ]
        new_view.add_item(VariantSelect(variant_options, self.all_products))
        
        embed = discord.Embed(title=f"Category: {selected_cat}", description="Now select the variant(s) you want to purchase:", color=discord.Color.blue())
        await interaction.response.edit_message(embed=embed, view=new_view)

class VariantSelect(discord.ui.Select):
    def __init__(self, options, all_products):
        # Allow multiple selection as before
        super().__init__(placeholder="Select variants to purchase...", min_values=1, max_values=len(options), options=options)
        self.all_products = all_products

    async def callback(self, interaction: discord.Interaction):
        selected_ids = [int(v) for v in self.values]
        selected_products = [p for p in self.all_products if p[0] in selected_ids]
        
        total_price = sum(p[4] for p in selected_products)
        
        embed = discord.Embed(title="Order Summary", color=discord.Color.green())
        description = ""
        view = discord.ui.View()
        for p in selected_products:
            description += f"**{p[3]}**: ${p[4]}"
            if p[5] == 'text':
                description += f"\n> *Info: {p[6]}*\n"
            else:
                description += "\n"
                view.add_item(discord.ui.Button(label=f"Link: {p[3]}", url=p[6]))
        
        description += f"\n**Total Order Amount: ${total_price:.2f}**"
        embed.description = description
        
        # Add a back button to return to category selection
        back_btn = discord.ui.Button(label="Back to Categories", style=discord.ButtonStyle.secondary)
        async def back_callback(back_inter: discord.Interaction):
            await back_inter.response.edit_message(embed=discord.Embed(title="Payment & Products", description="Select the products you wish to purchase below.", color=discord.Color.gold()), view=ProductSelectionView(self.all_products))
        back_btn.callback = back_callback
        view.add_item(back_btn)
        
        await interaction.response.edit_message(embed=embed, view=view)

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
            "`.buttons` - Interactive form to add a product.\n"
            "`.delete_product` - Interactive form to delete a product."
        ),
        inline=False
    )
    
    embed.add_field(
        name="Sync",
        value="`.sync` - Syncs slash commands if they aren't showing up.",
        inline=False
    )
    
    embed.add_field(
        name="Review Setup",
        value="`.review_setup` - Interactive setup for the review system.",
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
async def buttons_prefix(ctx):
    if not ctx.author.guild_permissions.administrator:
        return
    
    view = discord.ui.View()
    add_btn = discord.ui.Button(label="Add Product", style=discord.ButtonStyle.green)
    
    async def add_callback(interaction: discord.Interaction):
        await interaction.response.send_modal(ProductModal())
        
    add_btn.callback = add_callback
    view.add_item(add_btn)
    
    await ctx.send("Click the button below to add a new product via form:", view=view)

@bot.command(name="delete_product")
async def delete_product_prefix(ctx):
    if not ctx.author.guild_permissions.administrator:
        return
    
    products = await database.get_products(ctx.guild.id)
    if not products:
        return await ctx.send("❌ No products found to delete!")
    
    await ctx.send("Select a product to delete:", view=ProductDeleteView(products))

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

@bot.tree.command(name="buttons", description="Add a new product button via an interactive form")
async def buttons_slash(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admin only!", ephemeral=True)
    await interaction.response.send_modal(ProductModal())

@bot.tree.command(name="delete_product", description="Delete an existing product button")
async def delete_product_slash(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admin only!", ephemeral=True)
    
    products = await database.get_products(interaction.guild_id)
    if not products:
        return await interaction.response.send_message("❌ No products found to delete!", ephemeral=True)
    
    await interaction.response.send_message("Select a product to delete:", view=ProductDeleteView(products), ephemeral=True)

@bot.command(name="panel")
async def panel_prefix(ctx):
    if not ctx.author.guild_permissions.administrator:
        return
    
    settings = await database.get_settings(ctx.guild.id)
    if not settings or not settings[1]:
        return await ctx.send("❌ Panel channel not configured! Use `.setup` first.")
    
    channel = ctx.guild.get_channel(settings[1])
    if not channel:
        return await ctx.send("❌ Configured panel channel not found!")
    
    embed = discord.Embed(
        title="Open a Ticket",
        description="Click the buttons below to open a ticket for Purchase or Support.",
        color=discord.Color.blue()
    )
    
    await channel.send(embed=embed, view=TicketPanelView())
    await ctx.send("✅ Panel sent!")

@bot.tree.command(name="sync", description="Sync slash commands globally")
async def sync_slash(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admin only!", ephemeral=True)
    await bot.tree.sync()
    await interaction.response.send_message("✅ Slash commands synced!", ephemeral=True)

@bot.tree.command(name="review_setup", description="Setup the review system via an interactive form")
async def review_setup_slash(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admin only!", ephemeral=True)
    
    embed = discord.Embed(
        title="Review System Setup",
        description="Select the channel where reviews will be posted and the role allowed to post them.",
        color=discord.Color.red()
    )
    await interaction.response.send_message(embed=embed, view=ReviewSetupView(), ephemeral=True)

@bot.command(name="review_setup")
async def review_setup_prefix(ctx):
    if not ctx.author.guild_permissions.administrator:
        return
    
    embed = discord.Embed(
        title="Review System Setup",
        description="Select the channel where reviews will be posted and the role allowed to post them.",
        color=discord.Color.red()
    )
    await ctx.send(embed=embed, view=ReviewSetupView())

@bot.command(name="sync")
async def sync_prefix(ctx):
    if not ctx.author.guild_permissions.administrator:
        return
    
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"✅ Synced {len(synced)} slash commands globally!")
    except Exception as e:
        await ctx.send(f"❌ Failed to sync: {e}")

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("Please provide a DISCORD_TOKEN in the .env file.")
