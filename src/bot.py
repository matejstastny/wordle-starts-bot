import os
from datetime import UTC, datetime, timedelta

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
from src.database import add_score, get_leaderboard, has_been_posted, init_db, mark_posted
from src.parser import parse_daily_summary

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


def valid_months_window() -> list[str]:
    """Return YYYY-MM strings for the 3 calendar months before the current month."""
    today = datetime.now(UTC).date()
    months = []
    d = today.replace(day=1)
    for _ in range(3):
        d -= timedelta(days=1)
        months.append(d.strftime("%Y-%m"))
        d = d.replace(day=1)
    return months


def month_num_to_year_month(month_num: int) -> str | None:
    """Convert a month number (1-12) to YYYY-MM if within the 3-month window, else None."""
    for ym in valid_months_window():
        if int(ym[5:7]) == month_num:
            return ym
    return None


def build_leaderboard_message(year_months: list[str]) -> str:
    month_names = []
    for ym in year_months:
        try:
            month_names.append(datetime.strptime(ym, "%Y-%m").strftime("%B %Y"))
        except ValueError:
            return f"Invalid month: {ym}"

    if len(month_names) == 1:
        label = month_names[0]
    elif len(month_names) == 2:
        label = " & ".join(month_names)
    else:
        label = ", ".join(month_names[:-1]) + " & " + month_names[-1]

    rows = get_leaderboard(year_months, min_games=MIN_GAMES, top_n=TOP_N)

    if not rows:
        return (
            f"**Wordle Leaderboard - {label}**\n\n"
            f"No qualifying players yet (minimum {MIN_GAMES} games required)."
        )

    medals = ["🥇", "🥈", "🥉"]
    lines = [
        f"**Wordle Leaderboard - {label}** 🏆",
        f"*Ranked by avg guesses • minimum {MIN_GAMES} games to qualify • X/6 = 7*\n",
    ]
    for i, (name, avg, games) in enumerate(rows, start=1):
        prefix = medals[i - 1] if i <= 3 else f"**{i}.**"
        lines.append(f"{prefix} {name} - `{avg:.2f}` avg ({games} games)")

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
    if not message.author.bot and not message.webhook_id:
        return
    if WORDLE_BOT_NAME.lower() not in message.author.name.lower():
        return
    text = message.content
    if not text and message.embeds:
        text = message.embeds[0].description or ""

    if "yesterday" not in text.lower():
        return

    # The summary always refers to the previous day's games
    game_date = message.created_at.date() - timedelta(days=1)
    mentions_map = {str(m.id): m.display_name for m in message.mentions}

    scores = parse_daily_summary(text, mentions_map)
    recorded = sum(
        1
        for player_id, player_name, guesses in scores
        if add_score(player_id, player_name, guesses, game_date)
    )
    print(f"[{message.created_at.date()}] Recorded {recorded}/{len(scores)} scores for {game_date}")


@bot.command(name="leaderboard")
@commands.has_permissions(administrator=True)
async def cmd_leaderboard(ctx, month: str = None):
    """Post leaderboard. No arg = last month only. Optional YYYY-MM must be within 3 months."""
    valid = valid_months_window()
    if month is None:
        await ctx.send(build_leaderboard_message([valid[0]]))
    else:
        if month not in valid:
            await ctx.send(f"Month `{month}` is outside the allowed window. Valid: {', '.join(valid)}")
            return
        await ctx.send(build_leaderboard_message([month]))


def is_mod(interaction: discord.Interaction) -> bool:
    return any(r.name == MOD_ROLE for r in interaction.user.roles)


@bot.tree.command(
    name="leaderboard", description="Show the Wordle leaderboard (Program Staff only)"
)
@discord.app_commands.describe(month="Month to show (YYYY-MM). Defaults to last month.")
async def slash_leaderboard(interaction: discord.Interaction, month: str = None):
    if not is_mod(interaction):
        await interaction.response.send_message(
            "You need the Program Staff role to use this command.", ephemeral=True
        )
        return
    if interaction.channel_id != LEADERBOARD_CHANNEL_ID:
        await interaction.response.send_message(
            f"This command only works in <#{LEADERBOARD_CHANNEL_ID}>.", ephemeral=True
        )
        return
    valid = valid_months_window()
    target_month = month or valid[0]

    if target_month not in valid:
        await interaction.response.send_message(
            f"Month `{target_month}` is outside the allowed 3-month window. Valid: {', '.join(valid)}",
            ephemeral=True,
        )
        return

    month_name = datetime.strptime(target_month, "%Y-%m").strftime("%B %Y")
    await interaction.response.send_message(f"Loading data for {month_name}...")
    await interaction.followup.send(build_leaderboard_message([target_month]))


@bot.command(name="debug")
@commands.has_permissions(administrator=True)
async def cmd_debug(ctx, month_num: int = None):
    """Scan a month's Wordle messages and DM per-day breakdown. No DB writes."""
    valid = valid_months_window()
    if month_num is None:
        await ctx.send(
            f"Usage: `!debug <month>` (month number, e.g. `!debug 5`)\n"
            f"Valid months: {', '.join(valid)}"
        )
        return

    target_ym = month_num_to_year_month(month_num)
    if target_ym is None:
        await ctx.send(
            f"Month `{month_num}` is not within the allowed 3-month window. Valid: {', '.join(valid)}"
        )
        return

    month_name = datetime.strptime(target_ym, "%Y-%m").strftime("%B %Y")
    channel = bot.get_channel(WORDLE_CHANNEL_ID)
    if channel is None:
        await ctx.send("Wordle channel not found. Check WORDLE_CHANNEL_ID.")
        return

    total = 0
    name_matched = 0
    had_yesterday = 0
    daily_groups = {}

    async for message in channel.history(limit=None):
        total += 1

        msg_ym = message.created_at.strftime("%Y-%m")
        if msg_ym < target_ym:
            break
        if msg_ym != target_ym:
            continue

        is_bot = message.author.bot
        is_webhook = bool(message.webhook_id)
        author_name = message.author.name

        if not is_bot and not is_webhook:
            continue

        if WORDLE_BOT_NAME.lower() not in author_name.lower():
            continue
        name_matched += 1

        text = message.content
        if not text and message.embeds:
            text = message.embeds[0].description or ""

        if "yesterday" not in text.lower():
            continue
        had_yesterday += 1

        game_date = message.created_at.date() - timedelta(days=1)
        if game_date.strftime("%Y-%m") != target_ym:
            continue

        mentions_map = {str(m.id): m.display_name for m in message.mentions}
        scores = parse_daily_summary(text, mentions_map)

        if game_date not in daily_groups:
            daily_groups[game_date] = (message.jump_url, [])
        daily_groups[game_date][1].extend(scores)

    # Build per-day blocks, then send in DM chunks that fit under Discord's 2000-char limit
    day_blocks = []
    for game_date in sorted(daily_groups.keys()):
        jump_url, scores = daily_groups[game_date]
        block_lines = [f"--- {game_date} ({jump_url}) ---"]
        for player_id, player_name, guesses in scores:
            score = "X/6" if guesses == 7 else f"{guesses}/6"
            block_lines.append(f"  {score}  {player_name} (id: {player_id})")
        day_blocks.append("\n".join(block_lines))

    summary = (
        f"Debug complete — {month_name}\n"
        f"Messages scanned: {total} | Matched Wordle bot: {name_matched} | Had 'yesterday': {had_yesterday}"
    )

    try:
        dm = await ctx.author.create_dm()
        await dm.send(f"Scanning {month_name} in <#{WORDLE_CHANNEL_ID}>...\n")
        chunk = []
        chunk_len = 0
        for block in day_blocks:
            if chunk_len + len(block) + 2 > 1900:
                await dm.send("\n\n".join(chunk))
                chunk = []
                chunk_len = 0
            chunk.append(block)
            chunk_len += len(block) + 2
        if chunk:
            await dm.send("\n\n".join(chunk))
        await dm.send(summary)
    except discord.Forbidden:
        await ctx.send("❌ Couldn't DM you — enable DMs from server members.")


@bot.command(name="backfill")
@commands.has_permissions(administrator=True)
async def cmd_backfill(ctx, *month_args: int):
    """Backfill scores for specific months by number. Usage: !backfill 4 5 (April and May)."""
    valid = valid_months_window()
    if not month_args:
        await ctx.send(
            f"Usage: `!backfill <month> [month ...]` (month numbers, e.g. `!backfill 4 5`)\n"
            f"Valid months: {', '.join(valid)}"
        )
        return

    target_months = []
    for num in month_args:
        ym = month_num_to_year_month(num)
        if ym is None:
            await ctx.send(
                f"Month `{num}` is not within the allowed 3-month window. Valid: {', '.join(valid)}"
            )
            return
        target_months.append(ym)

    target_months = sorted(set(target_months))
    earliest_ym = target_months[0]
    month_labels = [datetime.strptime(ym, "%Y-%m").strftime("%B %Y") for ym in target_months]

    channel = bot.get_channel(WORDLE_CHANNEL_ID)
    if channel is None:
        await ctx.send("Wordle channel not found. Check WORDLE_CHANNEL_ID.")
        return

    await ctx.send(f"Scanning for {', '.join(month_labels)} in <#{WORDLE_CHANNEL_ID}>...")

    total = 0
    non_human = 0
    name_matched = 0
    had_yesterday = 0
    recorded_total = 0
    all_author_names = set()

    async for message in channel.history(limit=None):
        total += 1

        # Stop once we've passed all requested months (history is newest-first)
        if message.created_at.strftime("%Y-%m") < earliest_ym:
            break

        is_bot = message.author.bot
        is_webhook = bool(message.webhook_id)
        author_name = message.author.name

        if not is_bot and not is_webhook:
            continue
        non_human += 1
        all_author_names.add(f"{author_name}(bot={is_bot},wh={is_webhook})")

        if WORDLE_BOT_NAME.lower() not in author_name.lower():
            continue
        name_matched += 1

        text = message.content
        if not text and message.embeds:
            text = message.embeds[0].description or ""

        if "yesterday" not in text.lower():
            continue
        had_yesterday += 1

        game_date = message.created_at.date() - timedelta(days=1)
        game_ym = game_date.strftime("%Y-%m")

        if game_ym not in target_months:
            continue

        mentions_map = {str(m.id): m.display_name for m in message.mentions}
        scores = parse_daily_summary(text, mentions_map)
        for player_id, player_name, guesses in scores:
            if add_score(player_id, player_name, guesses, game_date):
                recorded_total += 1

    names_str = ", ".join(f"`{n}`" for n in sorted(all_author_names)) or "none"
    await ctx.send(
        f"**Backfill complete**\n"
        f"Months: {', '.join(month_labels)}\n"
        f"Total messages scanned: {total}\n"
        f"Non-human (bot/webhook): {non_human}\n"
        f"Matched name `{WORDLE_BOT_NAME}`: {name_matched}\n"
        f"Had 'yesterday': {had_yesterday}\n"
        f"Imported: {recorded_total}\n"
        f"All non-human authors: {names_str}"
    )


@bot.command(name="wipe")
@commands.has_permissions(administrator=True)
async def cmd_wipe(ctx):
    """Purge all messages from the leaderboard channel. Only works when called from leaderboard channel."""
    if ctx.channel.id != LEADERBOARD_CHANNEL_ID:
        try:
            await ctx.author.send(f"❌ !wipe can only be used inside <#{LEADERBOARD_CHANNEL_ID}>.")
        except discord.Forbidden:
            pass
        return

    channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
    if channel is None:
        await ctx.send("Leaderboard channel not found. Check LEADERBOARD_CHANNEL_ID.")
        return

    deleted = 0
    async for msg in channel.history(limit=None):
        try:
            await msg.delete()
            deleted += 1
        except discord.NotFound:
            pass

    try:
        await ctx.author.send(f"✅ Wiped <#{LEADERBOARD_CHANNEL_ID}> — {deleted} messages deleted.")
    except discord.Forbidden:
        pass


@tasks.loop(hours=1)
async def monthly_post():
    now = datetime.now(UTC)
    if now.day != 1 or now.hour != POST_HOUR_UTC:
        return

    prev = now.replace(day=1) - timedelta(days=1)
    year_month = prev.strftime("%Y-%m")

    if has_been_posted(year_month):
        return

    channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
    if channel:
        await channel.send(build_leaderboard_message([year_month]))
        mark_posted(year_month)
        print(f"Posted leaderboard for {year_month}")


@monthly_post.before_loop
async def before_monthly_post():
    await bot.wait_until_ready()


bot.run(TOKEN)
