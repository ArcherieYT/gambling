# main.py
import discord
from discord.ext import commands
import json
import asyncio
import random
import os
import time

# For the keepalive web server
from threading import Thread
from http.server import HTTPServer, SimpleHTTPRequestHandler

# --- Configuration ---
# Your bot token will be loaded from a Render Environment Variable, NOT from config.json.
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

# Data file to store user money and careers
# This file (users.json) will be created and managed by Render's ephemeral storage.
# IMPORTANT: Data stored in users.json on Render's free tier is NOT persistent.
# It will be reset every time your bot restarts or redeploys.
# For persistent data, a database solution would be required.
USER_DATA_FILE = 'users.json'

# Cooldowns in seconds
WORK_COOLDOWN = 3600 # 1 hour
CAREER_COOLDOWN = 86400 # 24 hours

# --- Bot Initialization ---
# Define intents. Message Content Intent is CRITICAL for reading commands.
intents = discord.Intents.default()
intents.message_content = True
intents.members = True # Good practice for user interactions, especially with UI components later

# IMPORTANT CHANGE: Define bot with `commands.Bot` as before
bot = commands.Bot(command_prefix='/', intents=intents)

# --- Helper Functions for Data Management ---

def load_user_data():
    """Loads user data from the JSON file."""
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print(f"Error: Could not decode JSON from {USER_DATA_FILE}. Returning empty data.")
                return {}
    return {}

def save_user_data(data):
    """Saves user data to the JSON file."""
    with open(USER_DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def get_user_data(user_id):
    """Retrieves a user's data, initializing if they are new."""
    data = load_user_data()
    user_id_str = str(user_id)
    if user_id_str not in data:
        # Initialize new user with default values
        data[user_id_str] = {
            "money": 0,
            "career": "homeless",
            "last_work_time": 0,
            "last_career_roll_time": 0
        }
        save_user_data(data)
    else:
        # Ensure all fields are present for existing users (for new fields added later)
        if "last_work_time" not in data[user_id_str]:
            data[user_id_str]["last_work_time"] = 0
            # Note: We save immediately to ensure the new field is added for existing users.
            # This can be optimized if you have many users, but fine for a bot.
            save_user_data(data)
        if "last_career_roll_time" not in data[user_id_str]:
            data[user_id_str]["last_career_roll_time"] = 0
            save_user_data(data)
    return data[user_id_str]

# --- Keepalive Web Server ---
class MyHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_server():
    port = int(os.environ.get("PORT", 8080)) # Get port from environment variable or default to 8080
    server = HTTPServer(('0.0.0.0', port), MyHandler)
    print(f"Starting keepalive server on port {port}")
    server.serve_forever()

def keep_alive():
    """Starts the web server in a separate thread."""
    server_thread = Thread(target=run_server)
    server_thread.daemon = True # Allows the main program to exit even if this thread is running
    server_thread.start()


# --- Bot Events ---

@bot.event
async def on_ready():
    """Called when the bot successfully connects to Discord."""
    print(f'Logged in as {bot.user.name}')
    print(f'Bot ID: {bot.user.id}')
    print('Bot is ready!')
    # Optionally set bot's activity
    # await bot.change_presence(activity=discord.Game(name="with your money!"))


# --- Commands ---

@bot.command(name='work')
async def work(ctx):
    """Allows a user to work and earn money based on their career."""
    user_id = str(ctx.author.id)
    user_data = get_user_data(user_id)

    # Check cooldown
    current_time = time.time()
    time_since_last_work = current_time - user_data["last_work_time"]

    if time_since_last_work < WORK_COOLDOWN:
        remaining_time = WORK_COOLDOWN - time_since_last_work
        hours, remainder = divmod(remaining_time, 3600)
        minutes, seconds = divmod(remainder, 60)
        await ctx.send(
            f"You need to rest! You can work again in "
            f"{int(hours)}h {int(minutes)}m {int(seconds)}s."
        )
        return

    # Calculate earnings
    career_name = user_data["career"]
    career_info = CAREERS.get(career_name, CAREERS["homeless"]) # Default to homeless if career not found
    
    base_pay = career_info["base_pay"]
    multiplier = career_info["multiplier"]
    earnings = int(base_pay * multiplier * (random.uniform(0.8, 1.2))) # Randomize earnings a bit

    user_data["money"] += earnings
    user_data["last_work_time"] = current_time
    save_user_data(load_user_data()) # Save all data after update

    await ctx.send(
        f"You worked as a **{career_name}** and earned **${earnings:,}**! "
        f"You now have **${user_data['money']:,}**."
    )

# CORRECTED: Define career as a commands.Group
@bot.group(name='career', invoke_without_command=True)
async def career(ctx):
    """
    Displays your current career or attempts to advance your career.
    Usage: /career (to display) or /career roll (to attempt advance)
    """
    user_id = str(ctx.author.id)
    user_data = get_user_data(user_id)

    # This block executes if /career is called without a subcommand (like just "/career")
    if ctx.invoked_subcommand is None:
        current_career = user_data["career"]
        current_career_info = CAREERS.get(current_career, CAREERS["homeless"])
        
        response = f"Your current career is **{current_career}** ({current_career_info['description']}).\n"
        response += f"You earn **${int(current_career_info['base_pay'] * current_career_info['multiplier']):,}** per work."

        # Find the next career in the ordered list
        current_career_index = CAREER_ORDER.index(current_career)
        if current_career_index < len(CAREER_ORDER) - 1:
            next_career_name = CAREER_ORDER[current_career_index + 1]
            next_career_info = CAREERS.get(next_career_name)
            response += (
                f"\nYour next career is **{next_career_name}** ({next_career_info['description']}). "
                f"You can try to advance by typing `/career roll`."
            )
        else:
            response += "\nYou are at the highest career level!"
        
        await ctx.send(response)

@career.command(name='roll')
async def career_roll(ctx):
    """Attempts to advance your career."""
    user_id = str(ctx.author.id)
    user_data = get_user_data(user_id)

    current_career_name = user_data["career"]
    current_career_index = CAREER_ORDER.index(current_career_name)

    # Check if user is already at the highest career
    if current_career_index == len(CAREER_ORDER) - 1:
        await ctx.send(f"You are already at the highest career: **{current_career_name}**! There's no higher to go.")
        return

    # Check cooldown
    current_time = time.time()
    time_since_last_roll = current_time - user_data["last_career_roll_time"]

    if time_since_last_roll < CAREER_COOLDOWN:
        remaining_time = CAREER_COOLDOWN - time_since_last_roll
        hours, remainder = divmod(remaining_time, 3600)
        minutes, seconds = divmod(remainder, 60)
        await ctx.send(
            f"You can't roll for a new career yet! Try again in "
            f"{int(hours)}h {int(minutes)}m {int(seconds)}s."
        )
        return

    user_data["last_career_roll_time"] = current_time # Update cooldown time regardless of success
    
    # Attempt to advance career
    if random.random() < CAREER_ADVANCEMENT_CHANCE: # Check if random number is less than the chance (e.g., 0.10 for 10%)
        next_career_index = current_career_index + 1
        new_career_name = CAREER_ORDER[next_career_index]
        user_data["career"] = new_career_name
        save_user_data(load_user_data())
        await ctx.send(
            f"Congratulations! 🎉 You've been promoted from **{current_career_name}** "
            f"to **{new_career_name}**! "
            f"You now earn **${int(CAREERS[new_career_name]['base_pay'] * CAREERS[new_career_name]['multiplier']):,}** per work."
        )
    else:
        save_user_data(load_user_data()) # Still save cooldown even if failed
        await ctx.send(
            f"You tried to advance your career from **{current_career_name}**, "
            f"but you weren't successful this time. Better luck next time!"
        )

# --- Blackjack Game Logic ---

SUITS = ['♠️', '♥️', '♦️', '♣️']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

def create_deck():
    """Creates a standard 52-card deck."""
    return [(rank, suit) for suit in SUITS for rank in RANKS]

def get_card_value(card):
    """Returns the numerical value of a card in Blackjack."""
    rank = card[0]
    if rank in ['J', 'Q', 'K']:
        return 10
    elif rank == 'A':
        return 11 # Ace will be handled as 1 or 11 in hand value calculation
    else:
        return int(rank)

def calculate_hand_value(hand):
    """Calculates the value of a Blackjack hand, accounting for Aces."""
    value = 0
    num_aces = 0
    for card in hand:
        card_value = get_card_value(card)
        if card_value == 11: # It's an Ace
            num_aces += 1
        value += card_value

    while value > 21 and num_aces > 0:
        value -= 10 # Change Ace from 11 to 1
        num_aces -= 1
    return value

def hand_to_string(hand):
    """Converts a hand (list of cards) to a human-readable string."""
    return ', '.join([f"{rank}{suit}" for rank, suit in hand])

# --- Blackjack Command (Initial Version - without buttons yet) ---
@bot.command(name='blackjack', aliases=['bj'])
async def blackjack(ctx, bet: int):
    """
    Starts a game of Blackjack against the dealer.
    Usage: /blackjack <bet_amount>
    """
    user_id = str(ctx.author.id)
    user_data = get_user_data(user_id)

    if bet <= 0:
        await ctx.send("You must bet a positive amount of money.")
        return

    if user_data["money"] < bet:
        await ctx.send(f"You don't have enough money! You have **${user_data['money']:,}** but tried to bet **${bet:,}**.")
        return

    # Deduct bet at the start of the game
    user_data["money"] -= bet
    save_user_data(load_user_data()) # Save all data

    deck = create_deck()
    random.shuffle(deck)

    player_hand = []
    dealer_hand = []

    # Deal initial cards
    player_hand.append(deck.pop())
    dealer_hand.append(deck.pop())
    player_hand.append(deck.pop())
    dealer_hand.append(deck.pop())

    player_value = calculate_hand_value(player_hand)
    dealer_up_card = dealer_hand[0] # Dealer's face-up card

    # Check for immediate Blackjacks
    if player_value == 21:
        dealer_value = calculate_hand_value(dealer_hand)
        if dealer_value == 21:
            # Both have Blackjack - Push
            user_data["money"] += bet # Return bet
            save_user_data(load_user_data())
            await ctx.send(
                f"**Blackjack!** 🥳\n"
                f"Your hand: {hand_to_string(player_hand)} (Value: 21)\n"
                f"Dealer's hand: {hand_to_string(dealer_hand)} (Value: {dealer_value})\n"
                f"It's a push! Your bet of **${bet:,}** has been returned. You now have **${user_data['money']:,}**."
            )
            return
        else:
            # Player Blackjack - Win 1.5x bet
            win_amount = int(bet * 1.5)
            user_data["money"] += (bet + win_amount)
            save_user_data(load_user_data())
            await ctx.send(
                f"**Blackjack!** 🎉 You win **${win_amount:,}**!\n"
                f"Your hand: {hand_to_string(player_hand)} (Value: 21)\n"
                f"Dealer's up card: {hand_to_string([dealer_up_card])}\n"
                f"You now have **${user_data['money']:,}**."
            )
            return

    # Start the game loop (for hit/hold) - This will be interactive with buttons later
    # For now, let's just make the player hit or stand directly in the command
    game_message = await ctx.send(
        f"**Blackjack Game Started!** (Bet: **${bet:,}**)\n"
        f"Your hand: {hand_to_string(player_hand)} (Value: {player_value})\n"
        f"Dealer's up card: {hand_to_string([dealer_up_card])} and one hidden card."
        "\n\nType `/hit` to draw another card or `/hold` to stick with your current hand."
    )

    # --- Wait for player's choice ---
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ['/hit', '/hold']

    while True:
        try:
            # Wait for either /hit or /hold command from the user
            msg = await bot.wait_for('message', check=check, timeout=30.0) # 30-second timeout for a response
            
            # Delete the user's hit/hold message to keep chat clean (optional)
            try:
                await msg.delete()
            except discord.HTTPException:
                pass # Bot might not have permissions to delete messages

        except asyncio.TimeoutError:
            # User timed out, treat as a stand and they lose their bet
            await ctx.send(f"Time's up! You automatically stood. You lost your bet of **${bet:,}**. You now have **${user_data['money']:,}**.")
            player_value = calculate_hand_value(player_hand) # Recalculate just in case, though it should be same as last check
            break # Exit the loop to proceed to dealer's turn

        if msg.content.lower() == '/hit':
            new_card = deck.pop()
            player_hand.append(new_card)
            player_value = calculate_hand_value(player_hand)
            await ctx.send(f"You hit and got {new_card[0]}{new_card[1]}! Your hand: {hand_to_string(player_hand)} (Value: {player_value})")

            if player_value > 21:
                # Player busts
                await ctx.send(f"**BUST!** 😭 Your hand value is over 21. You lost **${bet:,}**.\nYou now have **${user_data['money']:,}**.")
                save_user_data(load_user_data())
                return # End the game
            elif player_value == 21:
                await ctx.send("You hit 21! Standing automatically.")
                break # Player hits 21, automatically stands
        elif msg.content.lower() == '/hold':
            await ctx.send("You chose to hold.")
            break # Exit loop to proceed to dealer's turn

    # --- Dealer's Turn ---
    dealer_value = calculate_hand_value(dealer_hand)
    await ctx.send(f"Dealer's turn. Dealer's hand: {hand_to_string(dealer_hand)} (Value: {dealer_value})")

    while dealer_value < 17:
        new_card = deck.pop()
        dealer_hand.append(new_card)
        dealer_value = calculate_hand_value(dealer_hand)
        await ctx.send(f"Dealer hits and gets {new_card[0]}{new_card[1]}! Dealer's hand: {hand_to_string(dealer_hand)} (Value: {dealer_value})")
        await asyncio.sleep(1) # Small delay for better readability

    # --- Determine Winner ---
    if dealer_value > 21:
        # Dealer busts
        win_amount = bet * 2
        user_data["money"] += win_amount
        save_user_data(load_user_data())
        await ctx.send(
            f"**DEALER BUSTS!** 🎉 Dealer's hand value is over 21. You win **${bet:,}**!\n"
            f"You now have **${user_data['money']:,}**."
        )
    elif dealer_value < player_value:
        # Player has higher value than dealer (and not busted)
        win_amount = bet * 2
        user_data["money"] += win_amount
        save_user_data(load_user_data())
        await ctx.send(
            f"**YOU WIN!** 🎉 Your hand ({player_value}) is higher than the dealer's ({dealer_value}). You win **${bet:,}**!\n"
            f"You now have **${user_data['money']:,}**."
        )
    elif dealer_value > player_value:
        # Dealer has higher value than player
        # Bet already deducted at start, so no money change needed.
        save_user_data(load_user_data()) # Ensure user data is saved
        await ctx.send(
            f"**DEALER WINS!** 😭 Dealer's hand ({dealer_value}) is higher than yours ({player_value}). You lost **${bet:,}**.\n"
            f"You now have **${user_data['money']:,}**."
        )
    else: # dealer_value == player_value
        # Push
        user_data["money"] += bet # Return bet
        save_user_data(load_user_data())
        await ctx.send(
            f"**PUSH!** 🤝 Both you and the dealer have {player_value}. Your bet of **${bet:,}** has been returned.\n"
            f"You now have **${user_data['money']:,}**."
        )

@bot.command(name='rank')
async def rank(ctx, member: discord.Member = None):
    """
    Displays your current career or the career of another member.
    Usage: /rank (to see your own) or /rank @username (to see someone else's)
    """
    target_member = member if member else ctx.author # If no member is provided, default to the command author
    
    target_user_id = str(target_member.id)
    target_user_data = get_user_data(target_user_id)
    
    career_name = target_user_data["career"]
    
    if target_member == ctx.author:
        await ctx.send(f"{ctx.author.display_name} is currently a **{career_name}**.")
    else:
        await ctx.send(f"{target_member.display_name} is currently a **{career_name}**.")

# --- Run the bot ---
if __name__ == '__main__':
    # Start the keepalive web server
    keep_alive() # This ensures Render keeps the service alive

    # Load bot token from environment variables (for Render deployment)
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("Error: DISCORD_BOT_TOKEN environment variable not set.")
        print("Please set this variable on your Render dashboard.")
        exit()

    bot.run(token)
