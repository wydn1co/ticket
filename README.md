# Discord Ticket Bot

A professional and easy-to-use Discord ticket bot with purchase and support capabilities.

## Features
- **Ticket System**: Separate categories for Purchase and Support tickets.
- **Product Management**: Add products with prices and custom actions (text response or redirect link).
- **Payment Calculation**: Automatically calculates the total price when multiple products are selected.
- **Role Pinging**: Automatically pings staff roles when a ticket is created.
- **Persistent Buttons**: Buttons work even after bot restarts.

## Commands
- `/setup`: Configure categories, panel channel, and staff role.
- `/panel`: Send the ticket creation panel.
- `/buttons`: Add a product with a name, price, and action (text or redirect).
- `/sync`: Sync slash commands with Discord.

## Setup Instructions

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment**:
   - Rename `.env.example` to `.env`.
   - Add your Discord Bot Token to the `DISCORD_TOKEN` field.

3. **Run the Bot**:
   ```bash
   python bot.py
   ```

4. **Initial Configuration in Discord**:
   - Use `/sync` to make sure all slash commands are visible.
   - Use `/setup` to configure your server's channels and roles.
   - Use `/buttons` to add your products.
   - Use `/panel` to send the ticket panel to your desired channel.

## Requirements
- Python 3.8+
- `discord.py`
- `aiosqlite`
- `python-dotenv`
