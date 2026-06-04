# execute using `python -m tests.parser-test`

from src.parser import parse_daily_summary

TEST_DATA = [
    """
**Your group is on a 10 day streak!** 🔥 Here are yesterday's results:
👑 5/6: <@1464385423802372167> <@576637164343787530>
6/6: <@1384949726683598878> <@1269824870137593877>
""",
    """
**Your group is on a 9 day streak!** 🔥 Here are yesterday's results:
👑 6/6: @Benson Huang @Maanya Sood
X/6: <@1287833400358731900>
""",
]


def main():
    for i, content in enumerate(TEST_DATA, 1):
        results = parse_daily_summary(content, {})
        lines = [f"--- Test {i} ---"]
        for player_id, player_name, guesses in results:
            score = "X/6" if guesses == 7 else f"{guesses}/6"
            lines.append(f"  {score}  {player_name} (id: {player_id})")
        print("\n".join(lines))


if __name__ == "__main__":
    main()
