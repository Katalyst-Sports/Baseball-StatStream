print("### RUN_ENGINE MAIN BRANCH EXECUTING ###")
print("### GROQ ENGINE VERSION RUNNING ###")

import json
import os
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from groq import Groq

# =====================================================
# CONFIG
# =====================================================

BASE = "https://statsapi.mlb.com/api"
MLB_TZ = ZoneInfo("America/New_York")
NOW = datetime.now(MLB_TZ)

TODAY = NOW.date().isoformat()
YESTERDAY = (NOW - timedelta(days=1)).date().isoformat()
SEASON = NOW.year

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


# =====================================================
# UTILITIES
# =====================================================

def fetch(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def safe_number(value, default=0):
    return value if value is not None else default


def get_player_stat_block(team, player_id, stat_group):
    player = team.get("players", {}).get(f"ID{player_id}", {})
    return player.get("stats", {}).get(stat_group, {})


def get_player_name(team, player_id):
    player = team.get("players", {}).get(f"ID{player_id}", {})
    return player.get("person", {}).get("fullName", "Unknown Player")


def write_json(path, payload):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


# =====================================================
# PLAYER STAT HELPERS (SEASON-TO-DATE)
# =====================================================

def pitcher_summary(pitcher):
    if not pitcher:
        return {}

    out = {
        "id": pitcher.get("id"),
        "name": pitcher.get("fullName", "Unknown Pitcher"),
        "hand": "N/A",
        "era": "N/A",
    }

    pitcher_id = pitcher.get("id")
    if not pitcher_id:
        return out

    try:
        people = fetch(f"{BASE}/v1/people/{pitcher_id}").get("people", [])
        if people:
            out["hand"] = people[0].get("pitchHand", {}).get("code", "N/A")
    except Exception as exc:
        out["profile_error"] = str(exc)

    try:
        stats = fetch(
            f"{BASE}/v1/people/{pitcher_id}/stats"
            f"?stats=season&group=pitching&season={SEASON}"
        ).get("stats", [])
        splits = stats[0].get("splits", []) if stats else []
        if splits:
            out["era"] = splits[0].get("stat", {}).get("era", "N/A")
    except Exception as exc:
        out["stats_error"] = str(exc)

    return out


def build_live_or_final_highlights(boxscore, pick_final_pitcher=False):
    hitters = []
    pitchers = []

    for side in ["away", "home"]:
        team = boxscore.get("teams", {}).get(side, {})

        for batter_id in team.get("batters", []):
            batting = get_player_stat_block(team, batter_id, "batting")
            if safe_number(batting.get("hits")) >= 2 or safe_number(batting.get("homeRuns")) >= 1:
                hitters.append(get_player_name(team, batter_id))

        pitcher_ids = team.get("pitchers", [])
        selected_ids = pitcher_ids[:1] if pick_final_pitcher else pitcher_ids[-1:]

        for pitcher_id in selected_ids:
            pitching = get_player_stat_block(team, pitcher_id, "pitching")
            if safe_number(pitching.get("strikeOuts")) >= 6:
                pitchers.append(get_player_name(team, pitcher_id))

    return hitters, pitchers


# =====================================================
# BUILD TODAY (PRE-GAME / LIVE / FINAL)
# =====================================================

schedule_today = fetch(
    f"{BASE}/v1/schedule?sportId=1&date={TODAY}&hydrate=probablePitcher"
)

daily = []
live = []
postgame_today = []
errors = []

for date_block in schedule_today.get("dates", []):
    for game in date_block.get("games", []):
        try:
            away = game["teams"]["away"]["team"]["name"]
            home = game["teams"]["home"]["team"]["name"]
            venue = game["venue"]["name"]
            start = game["gameDate"]
            status = game["status"]["abstractGameState"]

            away_pitcher = game["teams"]["away"].get("probablePitcher")
            home_pitcher = game["teams"]["home"].get("probablePitcher")

            daily.append({
                "gamePk": game.get("gamePk"),
                "away_team": away,
                "home_team": home,
                "venue": venue,
                "start": start,
                "status": status,
                "away_pitcher": pitcher_summary(away_pitcher),
                "home_pitcher": pitcher_summary(home_pitcher),
            })

            if status in ["Live", "In Progress"]:
                feed = fetch(f"{BASE}/v1.1/game/{game['gamePk']}/feed/live")
                lines = feed.get("liveData", {}).get("linescore", {})
                box = feed.get("liveData", {}).get("boxscore", {})
                hot_hitters, top_pitchers = build_live_or_final_highlights(box, pick_final_pitcher=False)

                live.append({
                    "gamePk": game.get("gamePk"),
                    "game": f"{away} @ {home}",
                    "score": f"{lines.get('teams', {}).get('away', {}).get('runs', 0)}-{lines.get('teams', {}).get('home', {}).get('runs', 0)}",
                    "inning": lines.get("currentInningOrdinal"),
                    "hot_hitters": hot_hitters,
                    "top_pitchers": top_pitchers,
                })

            if status == "Final":
                feed = fetch(f"{BASE}/v1.1/game/{game['gamePk']}/feed/live")
                lines = feed.get("liveData", {}).get("linescore", {})
                box = feed.get("liveData", {}).get("boxscore", {})

                away_runs = lines.get("teams", {}).get("away", {}).get("runs", 0)
                home_runs = lines.get("teams", {}).get("home", {}).get("runs", 0)
                winner = away if away_runs > home_runs else home
                loser = home if away_runs > home_runs else away
                hitters, pitchers = build_live_or_final_highlights(box, pick_final_pitcher=True)

                postgame_today.append({
                    "gamePk": game.get("gamePk"),
                    "game": f"{away} @ {home}",
                    "winner": winner,
                    "loser": loser,
                    "final_score": f"{away_runs}-{home_runs}",
                    "hitters": hitters,
                    "pitchers": pitchers,
                })
        except Exception as exc:
            errors.append({
                "gamePk": game.get("gamePk"),
                "stage": "today_schedule_loop",
                "error": str(exc),
            })


# =====================================================
# BUILD YESTERDAY (FINAL + AI RECAP)
# =====================================================

schedule_yesterday = fetch(
    f"{BASE}/v1/schedule?sportId=1&date={YESTERDAY}"
)

yesterday_postgame = []

for date_block in schedule_yesterday.get("dates", []):
    for game in date_block.get("games", []):
        if game.get("status", {}).get("abstractGameState") != "Final":
            continue

        try:
            away = game["teams"]["away"]["team"]["name"]
            home = game["teams"]["home"]["team"]["name"]

            feed = fetch(f"{BASE}/v1.1/game/{game['gamePk']}/feed/live")
            lines = feed.get("liveData", {}).get("linescore", {})
            box = feed.get("liveData", {}).get("boxscore", {})

            away_runs = lines.get("teams", {}).get("away", {}).get("runs", 0)
            home_runs = lines.get("teams", {}).get("home", {}).get("runs", 0)
            winner = away if away_runs > home_runs else home
            loser = home if away_runs > home_runs else away
            hitters, pitchers = build_live_or_final_highlights(box, pick_final_pitcher=True)

            yesterday_postgame.append({
                "gamePk": game.get("gamePk"),
                "game": f"{away} @ {home}",
                "winner": winner,
                "loser": loser,
                "final_score": f"{away_runs}-{home_runs}",
                "hitters": hitters,
                "pitchers": pitchers,
            })
        except Exception as exc:
            errors.append({
                "gamePk": game.get("gamePk"),
                "stage": "yesterday_schedule_loop",
                "error": str(exc),
            })


# =====================================================
# YESTERDAY AI RECAP (GROQ)
# =====================================================

yesterday_recap = {
    "date": YESTERDAY,
    "headline": f"MLB Daily Recap - {datetime.fromisoformat(YESTERDAY).strftime('%B %d, %Y')}",
    "article": "No recap generated yet.",
}

if yesterday_postgame and client:
    try:
        games_text = "\n".join(
            [
                (
                    f"Game: {game['game']}\n"
                    f"Final: {game['final_score']}\n"
                    f"Winner: {game['winner']}\n"
                    f"Loser: {game['loser']}\n"
                    f"Hitters: {', '.join(game['hitters']) if game['hitters'] else 'Multiple contributors'}\n"
                    f"Pitchers: {', '.join(game['pitchers']) if game['pitchers'] else 'Staff effort'}\n"
                )
                for game in yesterday_postgame
            ]
        )

        prompt = f"""
You are a professional MLB columnist.

Write a YESTERDAY MLB recap with:
- A strong headline
- One paragraph per game
- Specific stats and reasons
- End with a section titled "Biggest Story of the Day"

Avoid generic language.

Games:
{games_text}
"""

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
        )

        yesterday_recap["article"] = response.choices[0].message.content.strip()
    except Exception as exc:
        yesterday_recap["article"] = f"Groq error: {str(exc)}"
elif yesterday_postgame and not client:
    yesterday_recap["article"] = "Groq recap skipped because GROQ_API_KEY is not set."
else:
    yesterday_recap["article"] = "No final games were available for yesterday."


# =====================================================
# WRITE FILES
# =====================================================

timestamp = NOW.isoformat()

write_json("daily.json", {"updated_at": timestamp, "games": daily, "errors": errors})
write_json("live.json", {"updated_at": timestamp, "games": live, "errors": errors})
write_json("postgame.json", {"updated_at": timestamp, "games": postgame_today, "errors": errors})
write_json("yesterday_postgame.json", {"updated_at": timestamp, "games": yesterday_postgame, "errors": errors})
write_json("yesterday_recap.json", yesterday_recap)

print(f"Wrote daily.json with {len(daily)} games")
print(f"Wrote live.json with {len(live)} games")
print(f"Wrote postgame.json with {len(postgame_today)} games")
print(f"Wrote yesterday_postgame.json with {len(yesterday_postgame)} games")
print("Wrote yesterday_recap.json")
