# Wordle Leaderboard Bot

A Discord bot that automatically tracks Wordle scores from the Wordle app and posts monthly leaderboards. Currently used on the [UWB STARS programm](https://www.uwb.edu/student-academic-success/academic-initiatives/stars-program/)'s Discord server, and deployed on the free tier of [Railway](https://railway.com/).

## Admin commands

| Command | Description |
|---------|-------------|
| `!backfill [limit]` | Import historical scores from channel history |
| `!leaderboard [YYYY-MM]` | Post leaderboard for a specific month |
| `!debug` | Show raw content of recent Wordle messages |
| `/leaderboard [month]` | Slash command (mod role only, leaderboard channel only) |

## How it works

- Listens to the Wordle app's daily summary messages in a configured channel
- Stores each player's score in a local SQLite database
- Posts a leaderboard on the 1st of each month to a separate channel
- Ranks players by lowest average guesses (minimum 5 games to qualify)
- Failed games (X/6) count as 7 guesses

<details>
<summary><h2>Setup if you want to use it</h2></summary>

#### 1. Create a Discord bot

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications) → New Application
2. Go to **Bot** → enable **Message Content Intent**
3. Copy the token

#### 2. Invite the bot

Use OAuth2 → URL Generator with scopes `bot` + `applications.commands` and permissions:
- View Channels
- Send Messages
- Read Message History
- Use Slash Commands
- Embed Links

#### 3. Configure

```bash
cp .env.example .env
```

#### 4. Run

```bash
pip install -r requirements.txt
python bot.py
```

## Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DISCORD_TOKEN` | Bot token | required |
| `WORDLE_CHANNEL_ID` | Channel where Wordle app posts | required |
| `LEADERBOARD_CHANNEL_ID` | Channel to post leaderboards | required |
| `WORDLE_BOT_NAME` | Display name of the Wordle app | `Wordle` |
| `MIN_GAMES` | Minimum games to appear on leaderboard | `5` |
| `TOP_N` | Number of players on leaderboard | `7` |
| `POST_HOUR_UTC` | Hour (UTC) to post on the 1st | `9` |
| `MOD_ROLE` | Role that can use `/leaderboard` | `Program Staff` |
</details>

