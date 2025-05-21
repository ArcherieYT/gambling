# main.py
import discord
from discord.ext import commands
import os
import time
import asyncio
import random
from threading import Thread
from http.server import HTTPServer, SimpleHTTPRequestHandler

# --- Database Imports ---
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure

# --- Configuration ---
# Your bot token will be loaded from a Render Environment Variable.
# Get your MongoDB Atlas Connection String from Render Environment Variables.
# Name the environment variable: MONGODB_URI
# Example URI: mongodb+srv://your_user:your_password@your_cluster.mongodb.net/?retryWrites=true&w=majority
MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = "discord_gambling_bot" # Your database name on MongoDB Atlas
COLLECTION_NAME = "users" # Collection to store user data

# Define careers and their multipliers
CAREERS = {
    "homeless": {"multiplier": 0.5, "base_pay": 50, "description": "the starting career"},
    "maid": {"multiplier": 0.7, "base_pay": 50, "description": "the next one up"},
    "minor": {"multiplier": 1.0, "base_pay": 50, "description": "mines ore"},
    "farmer": {"multiplier": 1.3, "base_pay": 50, "description": "farms"},
    "alchemist": {"multiplier": 1.5, "base_pay": 50, "description": "alchemies"},
    "architect": {"multiplier": 1.8, "base_pay": 50, "description": "is an architect"},
    "doctor": {"multiplier": 2.0, "base_pay": 50, "description": "is a doctor"}
}

# Ordered list of careers for progression logic (derived from CAREERS keys)
CAREER_ORDER = list(CAREERS.keys())

# Career advancement chances (1 in 10 chance = 10%)
CAREER_ADVANCEMENT_CHANCE = 0.10

# Cooldowns in seconds (1 hour = 3600 seconds)
WORK_COOLDOWN = 3600 # 1 hour
ROLL_COOLDOWN = 3600 # 1 hour for career roll

# --- Bot Initialization ---
# Define intents. Message Content Intent is CRITICAL for reading commands.
intents = discord.Intents.default()
intents.message_content = True
intents.members = True # Essential for fetching members for commands like /rank and /balance

# For Slash Commands, we initialize with a specific command_prefix but also use app_commands.
# The command_prefix here is mostly for legacy or if you want to mix with traditional commands.
# Slash commands don't use prefixes.
bot = commands.Bot(command_prefix='!', intents=intents) # Changed prefix to '!' as slash commands don't use it.
# bot.tree is the command tree for slash commands

# --- Database Connection ---
client = None # MongoDB client
db = None     # MongoDB database

def connect_to_db():
    global client, db
    try:
        client = MongoClient(MONGODB_URI)
        client.admin.command('ping') # Test connection
        db = client[DB_NAME]
        print("Successfully connected to MongoDB Atlas!")
    except ConnectionFailure as e:
        print(f"MongoDB connection failed: {e}")
        exit(1) # Exit if connection fails, bot cannot function without DB
    except OperationFailure as e:
        print(f"MongoDB operation failed (authentication/authorization?): {e}")
        exit(1)
    except Exception as e:
        print(f"An unexpected error occurred during MongoDB connection: {e}")
        exit(1)


# --- Helper Functions for Data Management (using MongoDB) ---

async def get_user_data(user_id):
    """Retrieves a user's data from MongoDB, initializing if they are new."""
    if db is None:
        print("Database not connected in get_user_data. Reattempting connection...")
        connect_to_db()
        if db is None: # If still not connected, raise error
            raise ConnectionFailure("Database not connected.")

    users_collection = db[COLLECTION_NAME]
    user_data = await asyncio.to_thread(users_collection.find_one, {"_id": str(user_id)})

    if user_data is None:
        # Initialize new user with default values
        new_user_data = {
            "_id": str(user_id), # Use Discord user ID as primary key
            "money": 0,
            "career": "homeless",
            "last_work_time": 0,
            "last_career_roll_time": 0
        }
        await asyncio.to_thread(users_collection.insert_one, new_user_data)
        return new_user_data
    else:
        # Ensure all fields are present for existing users (for new fields added later)
        # This part ensures backwards compatibility if you add new fields to the user data structure
        user_updated = False
        if "money" not in user_data:
            user_data["money"] = 0
            user_updated = True
        if "career" not in user_data:
            user_data["career"] = "homeless"
            user_updated = True
        if "last_work_time" not in user_data:
            user_data["last_work_time"] = 0
            user_updated = True
        if "last_career_roll_time" not in user_data:
            user_data["last_career_roll_time"] = 0
            user_updated = True
        
        if user_updated:
            await asyncio.to_thread(users_collection.update_one, {"_id": str(user_id)}, {"$set": user_data})
        return user_data

async def update_user_data(user_id, data_to_update):
    """Updates a user's data in MongoDB."""
    if db is None:
        print("Database not connected in update_user_data. Reattempting connection...")
        connect_to_db()
        if db is None:
            raise ConnectionFailure("Database not connected.")

    users_collection = db[COLLECTION_NAME]
    # $set updates only the fields provided, leaving others intact
    await asyncio.to_thread(users_collection.update_one, {"_id": str(user_id)}, {"$set": data_to_update})


# --- Keepalive Web Server ---
class MyHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), MyHandler)
    print(f"Starting keepalive server on port {port}")
    server.serve_forever()

def keep_alive():
    """Starts the web server in a separate thread."""
    server_thread = Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()


# --- Bot Events ---

@bot.event
async def on_ready():
    """Called when the bot successfully connects to Discord."""
    print(f'Logged in as {bot.user.name}')
    print(f'Bot ID: {bot.user.id}')
    print('Bot is ready!')
    connect_to_db() # Connect to database when bot is ready

    # !!! IMPORTANT for Slash Commands !!!
    # This line syncs your commands with Discord.
    # Run it once after major command changes. You might want to comment it out
    # after the first successful sync to avoid rate limits on subsequent restarts.
    # For initial deployment, keep it uncommented.
    try:
        await bot.tree.sync()
        print("Slash commands synced successfully!")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")

    # Optionally set bot's activity
    # await bot.change_presence(activity=discord.Game(name="with your money!"))


# --- Slash Commands ---

@bot.tree.command(name='work', description='Work to earn money based on your career.')
async def work_slash(interaction: discord.Interaction):
    """Allows a user to work and earn money based on their career."""
    user_id = str(interaction.user.id)
    user_data = await get_user_data(user_id) # Fetch user data from DB

    current_time = time.time()
    time_since_last_work = current_time - user_data["last_work_time"]

    if time_since_last_work < WORK_COOLDOWN:
        remaining_time = WORK_COOLDOWN - time_since_last_work
        hours, remainder = divmod(remaining_time, 3600)
        minutes, seconds = divmod(remainder, 60)
        await interaction.response.send_message(
            f"You need to rest! You can work again in "
            f"{int(hours)}h {int(minutes)}m {int(seconds)}s.", ephemeral=True # ephemeral makes it only visible to user
        )
        return

    career_name = user_data["career"]
    career_info = CAREERS.get(career_name, CAREERS["homeless"])
    
    base_pay = career_info["base_pay"]
    multiplier = career_info["multiplier"]
    earnings = int(base_pay * multiplier * (random.uniform(0.8, 1.2))) 

    user_data["money"] += earnings
    user_data["last_work_time"] = current_time

    await update_user_data(user_id, {"money": user_data["money"], "last_work_time": user_data["last_work_time"]})

    await interaction.response.send_message(
        f"You worked as a **{career_name}** and earned **${earnings:,}**! "
        f"You now have **${user_data['money']:,}**."
    )

@bot.tree.command(name='career', description='Displays your current career and potential next steps.')
async def career_slash(interaction: discord.Interaction):
    """Displays your current career."""
    user_id = str(interaction.user.id)
    user_data = await get_user_data(user_id)

    current_career = user_data["career"]
    current_career_info = CAREERS.get(current_career, CAREERS["homeless"])
    
    response = f"Your current career is **{current_career}** ({current_career_info['description']}).\n"
    response += f"You earn **${int(current_career_info['base_pay'] * current_career_info['multiplier']):,}** per work."

    current_career_index = CAREER_ORDER.index(current_career)
    if current_career_index < len(CAREER_ORDER) - 1:
        next_career_name = CAREER_ORDER[current_career_index + 1]
        next_career_info = CAREERS.get(next_career_name)
        response += (
            f"\nYour next career is **{next_career_name}** ({next_career_info['description']}). "
            f"You can try to advance by typing `/roll`."
        )
    else:
        response += "\nYou are at the highest career level!"
    
    await interaction.response.send_message(response)

@bot.tree.command(name='roll', description='Attempt to roll for a new, better career.')
async def roll_slash(interaction: discord.Interaction):
    """Attempts to advance your career."""
    user_id = str(interaction.user.id)
    user_data = await get_user_data(user_id)

    current_career_name = user_data["career"]
    current_career_index = CAREER_ORDER.index(current_career_name)

    if current_career_index == len(CAREER_ORDER) - 1:
        await interaction.response.send_message(
            f"You are already at the highest career: **{current_career_name}**! There's no higher to go.", ephemeral=True
        )
        return

    current_time = time.time()
    time_since_last_roll = current_time - user_data["last_career_roll_time"]

    if time_since_last_roll < ROLL_COOLDOWN: # Using ROLL_COOLDOWN (1 hour)
        remaining_time = ROLL_COOLDOWN - time_since_last_roll
        hours, remainder = divmod(remaining_time, 3600)
        minutes, seconds = divmod(remainder, 60)
        await interaction.response.send_message(
            f"You can't roll for a new career yet! Try again in "
            f"{int(hours)}h {int(minutes)}m {int(seconds)}s.", ephemeral=True
        )
        return

    user_data["last_career_roll_time"] = current_time # Update cooldown time regardless of success
    
    if random.random() < CAREER_ADVANCEMENT_CHANCE:
        next_career_index = current_career_index + 1
        new_career_name = CAREER_ORDER[next_career_index]
        user_data["career"] = new_career_name
        
        await interaction.response.send_message(
            f"Congratulations! 🎉 You've been promoted from **{current_career_name}** "
            f"to **{new_career_name}**! "
            f"You now earn **${int(CAREERS[new_career_name]['base_pay'] * CAREERS[new_career_name]['multiplier']):,}** per work."
        )
    else:
        await interaction.response.send_message(
            f"You tried to advance your career from **{current_career_name}**, "
            f"but you weren't successful this time. Better luck next time!"
        )
    
    await update_user_data(user_id, {"career": user_data["career"], "last_career_roll_time": user_data["last_career_roll_time"]})


SUITS = ['♠️', '♥️', '♦️', '♣️']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

def create_deck():
    return [(rank, suit) for suit in SUITS for rank in RANKS]

def get_card_value(card):
    rank = card[0]
    if rank in ['J', 'Q', 'K']:
        return 10
    elif rank == 'A':
        return 11
    else:
        return int(rank)

def calculate_hand_value(hand):
    value = 0
    num_aces = 0
    for card in hand:
        card_value = get_card_value(card)
        if card_value == 11:
            num_aces += 1
        value += card_value

    while value > 21 and num_aces > 0:
        value -= 10
        num_aces -= 1
    return value

def hand_to_string(hand):
    return ', '.join([f"{rank}{suit}" for rank, suit in hand])

@bot.tree.command(name='blackjack', description='Play a game of blackjack against the dealer.')
@discord.app_commands.describe(bet='The amount of money to bet.')
async def blackjack_slash(interaction: discord.Interaction, bet: int):
    """Starts a game of Blackjack against the dealer."""
    user_id = str(interaction.user.id)
    user_data = await get_user_data(user_id)

    if bet <= 0:
        await interaction.response.send_message("You must bet a positive amount of money.", ephemeral=True)
        return

    if user_data["money"] < bet:
        await interaction.response.send_message(
            f"You don't have enough money! You have **${user_data['money']:,}** but tried to bet **${bet:,}**.", ephemeral=True
        )
        return

    user_data["money"] -= bet
    await update_user_data(user_id, {"money": user_data["money"]})

    deck = create_deck()
    random.shuffle(deck)

    player_hand = []
    dealer_hand = []

    player_hand.append(deck.pop())
    dealer_hand.append(deck.pop())
    player_hand.append(deck.pop())
    dealer_hand.append(deck.pop())

    player_value = calculate_hand_value(player_hand)
    dealer_up_card = dealer_hand[0]

    if player_value == 21:
        dealer_value = calculate_hand_value(dealer_hand)
        if dealer_value == 21:
            user_data["money"] += bet
            await update_user_data(user_id, {"money": user_data["money"]})
            await interaction.response.send_message(
                f"**Blackjack!** 🥳\n"
                f"Your hand: {hand_to_string(player_hand)} (Value: 21)\n"
                f"Dealer's hand: {hand_to_string(dealer_hand)} (Value: {dealer_value})\n"
                f"It's a push! Your bet of **${bet:,}** has been returned. You now have **${user_data['money']:,}**."
            )
            return
        else:
            win_amount = int(bet * 1.5)
            user_data["money"] += (bet + win_amount)
            await update_user_data(user_id, {"money": user_data["money"]})
            await interaction.response.send_message(
                f"**Blackjack!** 🎉 You win **${win_amount:,}**!\n"
                f"Your hand: {hand_to_string(player_hand)} (Value: 21)\n"
                f"Dealer's up card: {hand_to_string([dealer_up_card])}\n"
                f"You now have **${user_data['money']:,}**."
            )
            return

    await interaction.response.send_message(
        f"**Blackjack Game Started!** (Bet: **${bet:,}**)\n"
        f"Your hand: {hand_to_string(player_hand)} (Value: {player_value})\n"
        f"Dealer's up card: {hand_to_string([dealer_up_card])} and one hidden card."
        "\n\nType `/hit` to draw another card or `/hold` to stick with your current hand."
        "\n*(Note: For now, you type `/hit` or `/hold` as separate commands. Future update will add buttons!)*"
    )

    # For slash commands, you can't use bot.wait_for directly on follow-up messages
    # as easily as with prefix commands. It's usually better to use buttons or
    # persistent views for game interactions with slash commands.
    # For now, I'm keeping the original wait_for approach, but be aware this
    # isn't the ideal way for long-running slash command interactions.
    def check(m):
        return m.author == interaction.user and m.channel == interaction.channel and m.content.lower() in ['/hit', '/hold']

    # Keep a reference to the original message for follow-ups
    original_message = await interaction.original_response()

    while True:
        try:
            msg = await bot.wait_for('message', check=check, timeout=30.0)
            try:
                await msg.delete()
            except discord.HTTPException:
                pass

        except asyncio.TimeoutError:
            await original_message.edit(content=f"Time's up! You automatically stood. You lost your bet of **${bet:,}**. You now have **${user_data['money']:,}**.")
            return

        if msg.content.lower() == '/hit':
            new_card = deck.pop()
            player_hand.append(new_card)
            player_value = calculate_hand_value(player_hand)
            await interaction.followup.send(f"You hit and got {new_card[0]}{new_card[1]}! Your hand: {hand_to_string(player_hand)} (Value: {player_value})")

            if player_value > 21:
                await interaction.followup.send(f"**BUST!** 😭 Your hand value is over 21. You lost **${bet:,}**.\nYou now have **${user_data['money']:,}**.")
                return
            elif player_value == 21:
                await interaction.followup.send("You hit 21! Standing automatically.")
                break
        elif msg.content.lower() == '/hold':
            await interaction.followup.send("You chose to hold.")
            break

    dealer_value = calculate_hand_value(dealer_hand)
    await interaction.followup.send(f"Dealer's turn. Dealer's hand: {hand_to_string(dealer_hand)} (Value: {dealer_value})")

    while dealer_value < 17:
        new_card = deck.pop()
        dealer_hand.append(new_card)
        dealer_value = calculate_hand_value(dealer_hand)
        await interaction.followup.send(f"Dealer hits and gets {new_card[0]}{new_card[1]}! Dealer's hand: {hand_to_string(dealer_hand)} (Value: {dealer_value})")
        await asyncio.sleep(1)

    if dealer_value > 21:
        win_amount = bet * 2
        user_data["money"] += win_amount
        await interaction.followup.send(
            f"**DEALER BUSTS!** 🎉 Dealer's hand value is over 21. You win **${bet:,}**!\n"
            f"You now have **${user_data['money']:,}**."
        )
    elif dealer_value < player_value:
        win_amount = bet * 2
        user_data["money"] += win_amount
        await interaction.followup.send(
            f"**YOU WIN!** 🎉 Your hand ({player_value}) is higher than the dealer's ({dealer_value}). You win **${bet:,}**!\n"
            f"You now have **${user_data['money']:,}**."
        )
    elif dealer_value > player_value:
        await interaction.followup.send(
            f"**DEALER WINS!** 😭 Dealer's hand ({dealer_value}) is higher than yours ({player_value}). You lost **${bet:,}**.\n"
            f"You now have **${user_data['money']:,}**."
        )
    else:
        user_data["money"] += bet
        await interaction.followup.send(
            f"**PUSH!** 🤝 Both you and the dealer have {player_value}. Your bet of **${bet:,}** has been returned.\n"
            f"You now have **${user_data['money']:,}**."
        )
    
    await update_user_data(user_id, {"money": user_data["money"]})


@bot.tree.command(name='rank', description='Displays your current career or the career of another member.')
@discord.app_commands.describe(member='The member whose career you want to check (optional).')
async def rank_slash(interaction: discord.Interaction, member: discord.Member = None):
    """
    Displays your current career or the career of another member.
    Usage: /rank (to see your own) or /rank @username (to see someone else's)
    """
    target_member = member if member else interaction.user
    
    target_user_id = str(target_member.id)
    target_user_data = await get_user_data(target_user_id)
    
    career_name = target_user_data["career"]
    
    if target_member == interaction.user:
        await interaction.response.send_message(f"{interaction.user.display_name} is currently a **{career_name}**.")
    else:
        await interaction.response.send_message(f"{target_member.display_name} is currently a **{career_name}**.")

@bot.tree.command(name='balance', description='Displays your current money or the money of another member.')
@discord.app_commands.describe(member='The member whose balance you want to check (optional).')
async def balance_slash(interaction: discord.Interaction, member: discord.Member = None):
    """
    Displays your current money or the money of another member.
    Usage: /balance (to see your own) or /balance @username (to see someone else's)
    """
    target_member = member if member else interaction.user
    
    target_user_id = str(target_member.id)
    target_user_data = await get_user_data(target_user_id)
    
    money = target_user_data["money"]
    
    if target_member == interaction.user:
        await interaction.response.send_message(f"{interaction.user.display_name}, you currently have **${money:,}**.")
    else:
        await interaction.response.send_message(f"{target_member.display_name} currently has **${money:,}**.")


# --- Run the bot ---
if __name__ == '__main__':
    keep_alive()

    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("Error: DISCORD_BOT_TOKEN environment variable not set.")
        print("Please set this variable on your Render dashboard.")
        exit()

    bot.run(token)
