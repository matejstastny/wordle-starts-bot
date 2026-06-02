import os
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

from database import add_score, get_leaderboard, has_been_posted, init_db, mark_posted
from parser import parse_daily_summary

load_dotenv()

TOKEN = os.environ["DISCORD_TOKEN"]
WORDLE_CHANNEL_ID = int(os.environ["WORDLE_CHANNEL_ID"])
LEADERBOARD_CHANNEL_ID = int(os.environ["LEADERBOARD_CHANNEL_ID"])
WORDLE_BOT_NAME = os.getenv("WORDLE_BOT_NAME", "Wordle")
MOD_ROLE = os.getenv("MOD_ROLE", "Program Staff")
MIN_GAMES = int(os.getenv("MIN_GAMES", "5"))
TOP_N = int(os.getenv("TOP_N", "7"))
POST_HOUR_UTC = int(os.getenv("POST_HOUR_UTC", "9"))

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


def build_leaderboard_message(year_month: str) -> str:
    try:
        dt = datetime.strptime(year_month, "%Y-%m")
    except ValueError:
        return f"Invalid month: {year_month}"

    month_name = dt.strftime("%B %Y")
    rows = get_leaderboard(year_month, min_games=MIN_GAMES, top_n=TOP_N)

    if not rows:
        return (
            f"🏆 **Wordle Leaderboard — {month_name}**\n\n"
            f"No qualifying players yet (minimum {MIN_GAMES} games required)."
        )

    medals = ["🥇", "🥈", "🥉"]
    lines = [
        f"🏆 **Wordle Leaderboard — {month_name}** 🏆",
        f"*Ranked by avg guesses • minimum {MIN_GAMES} games to qualify • X/6 = 7*\n",
    ]
    for i, (name, avg, games) in enumerate(rows, start=1):
        prefix = medals[i - 1] if i <= 3 else f"**{i}.**"
        lines.append(f"{prefix} {name} — `{avg:.2f}` avg ({games} games)")

    return "\n".join(lines)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    init_db()
    monthly_post.start()
    await bot.tree.sync()
    print("Slash commands synced")


@bot.event
async def on_message(message: discord.Message):
    await bot.process_commands(message)

    if message.channel.id != WORDLE_CHANNEL_ID:
        return
    if not message.author.bot:
        return
    if WORDLE_BOT_NAME.lower() not in message.author.name.lower():
        return
    if "yesterday's results" not in message.content.lower():
        return

    # The summary always refers to the previous day's games
    game_date = message.created_at.date() - timedelta(days=1)
    mentions_map = {str(m.id): m.display_name for m in message.mentions}

    scores = parse_daily_summary(message.content, mentions_map)
    recorded = sum(
        1
        for player_id, player_name, guesses in scores
        if add_score(player_id, player_name, guesses, game_date)
    )
    print(f"[{message.created_at.date()}] Recorded {recorded}/{len(scores)} scores for {game_date}")


@bot.command(name="leaderboard")
@commands.has_permissions(administrator=True)
async def cmd_leaderboard(ctx, month: str = None):
    """Post leaderboard for a given month (YYYY-MM). Defaults to last month."""
    if month is None:
        now = datetime.now(timezone.utc)
        month = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    await ctx.send(build_leaderboard_message(month))


def is_mod(interaction: discord.Interaction) -> bool:
    return any(r.name == MOD_ROLE for r in interaction.user.roles)


@bot.tree.command(name="leaderboard", description="Show the Wordle leaderboard (Program Staff only)")
@discord.app_commands.describe(month="Month to show (YYYY-MM). Defaults to current month.")
async def slash_leaderboard(interaction: discord.Interaction, month: str = None):
    if not is_mod(interaction):
        await interaction.response.send_message("You need the Program Staff role to use this command.", ephemeral=True)
        return
    if interaction.channel_id != LEADERBOARD_CHANNEL_ID:
        await interaction.response.send_message(
            f"This command only works in <#{LEADERBOARD_CHANNEL_ID}>.", ephemeral=True
        )
        return
    if month is None:
        now = datetime.now(timezone.utc)
        month = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    await interaction.response.send_message(build_leaderboard_message(month))


@bot.command(name="backfill")
@commands.has_permissions(administrator=True)
async def cmd_backfill(ctx, limit: int = 1000):
    """Scan the last <limit> messages in #wordle and import historical scores."""
    channel = bot.get_channel(WORDLE_CHANNEL_ID)
    if channel is None:
        await ctx.send("Wordle channel not found. Check WORDLE_CHANNEL_ID.")
        return

    await ctx.send(f"Scanning up to {limit} messages in <#{WORDLE_CHANNEL_ID}>...")

    recorded_total = 0
    async for message in channel.history(limit=limit, oldest_first=True):
        if not message.author.bot:
            continue
        if WORDLE_BOT_NAME.lower() not in message.author.name.lower():
            continue
        if "yesterday's results" not in message.content.lower():
            continue

        game_date = message.created_at.date() - timedelta(days=1)
        mentions_map = {str(m.id): m.display_name for m in message.mentions}
        scores = parse_daily_summary(message.content, mentions_map)
        for player_id, player_name, guesses in scores:
            if add_score(player_id, player_name, guesses, game_date):
                recorded_total += 1

    await ctx.send(f"Done! Imported {recorded_total} new score entries.")


@tasks.loop(hours=1)
async def monthly_post():
    now = datetime.now(timezone.utc)
    if now.day != 1 or now.hour != POST_HOUR_UTC:
        return

    prev = now.replace(day=1) - timedelta(days=1)
    year_month = prev.strftime("%Y-%m")

    if has_been_posted(year_month):
        return

    channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
    if channel:
        await channel.send(build_leaderboard_message(year_month))
        mark_posted(year_month)
        print(f"Posted leaderboard for {year_month}")


@monthly_post.before_loop
async def before_monthly_post():
    await bot.wait_until_ready()


bot.run(TOKEN)
