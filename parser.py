import re
from typing import Dict, List, Tuple

# Matches lines like: "👑 3/6: <@123>" or "X/6: <@456> <@789>" or "4/6: <@111>"
SCORE_LINE = re.compile(r'^[👑\s]*([1-6X])/6:\s*(.+)', re.UNICODE)
MENTION = re.compile(r'<@!?(\d+)>')


def parse_daily_summary(content: str, mentions_map: Dict[str, str]) -> List[Tuple[str, str, int]]:
    """
    Parse a Wordle APP daily summary message.
    X/6 (failed all guesses) counts as 7. Lines without Discord mentions are skipped.
    Returns list of (player_id, player_name, guesses).
    """
    results = []
    for line in content.splitlines():
        m = SCORE_LINE.match(line.strip())
        if not m:
            continue
        score_str, players_str = m.group(1), m.group(2)
        mentions = MENTION.findall(players_str)
        if not mentions:
            continue
        guesses = 7 if score_str == "X" else int(score_str)
        for player_id in mentions:
            player_name = mentions_map.get(player_id, f"Unknown ({player_id})")
            results.append((player_id, player_name, guesses))
    return results
