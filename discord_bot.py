import discord
import json
import os
from discord.ext import commands, tasks
import tweepy
from dotenv import load_dotenv
import itertools

# Load environment variables
load_dotenv()

# Twitter API credentials
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")

# Set up Twitter API client
client = tweepy.Client(bearer_token=TWITTER_BEARER_TOKEN)

# Create bot instance
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Store threads to monitor
threads_to_monitor = {}

# File to store threads persistently
THREADS_FILE = "threads.json"

# Function to save monitored threads to a JSON file
def save_threads():
    with open(THREADS_FILE, "w") as f:
        json.dump(threads_to_monitor, f, indent=4)

# Function to load monitored threads from a JSON file
def load_threads():
    global threads_to_monitor
    if os.path.exists(THREADS_FILE):
        with open(THREADS_FILE, "r") as f:
            try:
                threads_to_monitor = json.load(f)
            except json.JSONDecodeError:
                threads_to_monitor = {}  # Reset if the file is corrupted
    else:
        threads_to_monitor = {}

# Event: Bot is ready
@bot.event
async def on_ready():
    load_threads()  # Load stored threads on bot startup
    print(f"{bot.user} has connected to Discord!")
    if not check_threads.is_running():
        check_threads.start()

# Command: Monitor Twitter thread
@bot.command()
async def monitor(ctx, url: str):
    try:
        tweet_id = url.split("/")[-1].split("?")[0]  # Extract tweet ID

        # Fetch conversation_id from Twitter API
        tweet = client.get_tweet(tweet_id, tweet_fields=["conversation_id"])

        if not tweet or not tweet.data:
            await ctx.send("Invalid tweet URL or tweet not accessible.")
            return

        conversation_id = tweet.data["conversation_id"]

        # Store the thread with conversation_id instead of tweet_id
        threads_to_monitor[conversation_id] = ctx.author.id

        save_threads()  # Save data to JSON file

        await ctx.send("Thread is being monitored! I'll notify you when it's updated.")
        print(f"Monitoring thread {conversation_id} for user {ctx.author.name}")

    except Exception as e:
        await ctx.send("Invalid URL. Please provide a valid Twitter thread link.")
        print(f"Error parsing URL: {e}")

# Define trigger words that indicate the thread has ended
END_WORDS = {"end", "completed", "complete", "finished", "done"}

# Iterator to cycle through monitored threads
thread_iterator = itertools.cycle([])

# Task: Poll Twitter for thread updates
@tasks.loop(minutes=15)  # Run every 15 minutes to avoid API rate limits
async def check_threads():
    global thread_iterator

    if not threads_to_monitor:
        print("No threads to check.")
        return


    try:
        # Get the next thread to check
        conversation_id, user_id = next(thread_iterator, (None, None))
        
        if conversation_id is None:
            print("No more threads to check, resetting iterator.")
            thread_iterator = itertools.cycle(list(threads_to_monitor.items()))
            return

        print(f"Checking thread with conversation ID: {conversation_id}")

        # Fetch all tweets in the thread using conversation_id
        response = client.search_recent_tweets(
            query=f"conversation_id:{conversation_id}",
            tweet_fields=["text"]
        )

        if response.data:
            for tweet in response.data:
                tweet_text = tweet.text.lower()  # Convert text to lowercase
                if any(word in tweet_text for word in END_WORDS):
                    user = await bot.fetch_user(user_id)
                    await user.send(f"The thread you are monitoring has ended! 🎉\nhttps://twitter.com/i/status/{conversation_id}")
                    del threads_to_monitor[conversation_id]  # Stop monitoring
                    save_threads()  # Save changes
                    thread_iterator = itertools.cycle(list(threads_to_monitor.items()))  # Reset iterator
                    break  # Stop processing once thread is marked complete

        else:
            print(f"No end words found in thread {conversation_id} yet.")

    except Exception as e:
        print(f"Error checking thread: {e}")

# Run the bot using the token from .env
discord_token = os.getenv("DISCORD_BOT_TOKEN")

if __name__ == "__main__":
    if discord_token:
        bot.run(discord_token)
    else:
        print("Error: DISCORD_BOT_TOKEN not found. Check your .env file.")
