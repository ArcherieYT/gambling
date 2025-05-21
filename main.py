# main.py
import discord
from discord.ext import commands
import json
import asyncio
import random
import os
import time

# --- Configuration ---
# You'll need to create a 'config.json' file in the same directory as this bot
# Example config.json:
# {
#     "DISCORD_BOT_TOKEN": "YOUR_BOT_TOKEN_HERE"
# }

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
USER_DATA_FILE = 'users.json'

# Cooldowns in seconds
WORK_COOLDOWN = 3600 # 1 hour
CAREER_COOLDOWN = 86400 # 24 hours

# --- Bot Initialization ---
# Define intents. Message Content Intent is CRITICAL for reading commands.
intents = discord.Intents.default()
intents.message_content = True
intents.members = True # Good practice for user interactions, especially with UI components later

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
            save_user_data(data)
        if "last_career_roll_time" not in data[user_id_str]:
            data[user_id_str]["last_career_roll_time"] = 0
            save_user_data(data)
    return data[user_id_str]

# --- Bot Events ---

@bot.event
async def on_ready():
    """Called when the bot successfully connects to Discord."""
    print(f'Logged in as {bot.user.name}')
    print(f'Bot ID: {bot.user.id}')
    print('Bot is ready!')
    # Optionally set bot's activity
    # await bot.change_presence(activity=discord.Game(name="with your money!"))


# --- Commands (Will be added in subsequent steps) ---
# This section will contain the /work, /career, and /blackjack commands.


# --- Run the bot ---
if __name__ == '__main__':
    # Load bot token from config.json
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        token = config.get("DISCORD_BOT_TOKEN")
        if not token:
            print("Error: 'DISCORD_BOT_TOKEN' not found in config.json. Please ensure it's correct.")
            exit()
    except FileNotFoundError:
        print("Error: config.json not found. Please create it in the same directory as main.py with your bot token.")
        exit()
    except json.JSONDecodeError:
        print("Error: Invalid JSON in config.json. Please check its format.")
        exit()

    bot.run(token)
