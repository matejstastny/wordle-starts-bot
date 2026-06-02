import re
from typing import Dict, List, Tuple

# Matches lines like: "👑 3/6: <@123>" or "X/6: <@456> <@789>" or "4/6: @Cinnamon <@111>"
SCORE_LINE = re.compile(r'^[👑\s]*([1-6X])/6:\s*(.+)', re.UNICODE)
DISCORD_MENTION = re.compile(r'<@!?(\d+)>')
PLAIN_MENTION = re.compile(r'@([^\s<@>]+)')


def parse_daily_summary(content: str, mentions_map: Dict[str, str]) -> List[Tuple[str, str, int]]:
    """
    Parse a Wordle APP daily summary message.
    Handles both Discord mentions (<@ID>) and plain-text mentions (@Name).
    X/6 (failed all guesses) counts as 7.
    Returns list of (player_id, player_name, guesses).
    """
    results = []
    for line in content.splitlines():
        m = SCORE_LINE.match(line.strip())
        if not m:
            continue
        score_str, players_str = m.group(1), m.group(2)
        guesses = 7 if score_str == "X" else int(score_str)

        # Discord mentions: <@123456>
        for match in DISCORD_MENTION.finditer(players_str):
            player_id = match.group(1)
            player_name = mentions_map.get(player_id, f"Unknown ({player_id})")
            results.append((player_id, player_name, guesses))

        # Plain-text mentions: @Cinnamon (after removing Discord mentions to avoid double-counting)
        remaining = DISCORD_MENTION.sub("", players_str)
        for match in PLAIN_MENTION.finditer(remaining):
            name = match.group(1)
            results.append((f"@{name}", name, guesses))

    return results
