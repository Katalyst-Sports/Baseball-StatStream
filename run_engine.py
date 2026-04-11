print("### RUN_ENGINE MAIN BRANCH EXECUTING ###")
print("### GROQ ENGINE VERSION RUNNING ###")

import json
import os
from datetime import datetime
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from groq import Groq

# =====================================================
# CONFIG
# =====================================================

BASE = "https://statsapi.mlb.com/api"
MLB_TZ = ZoneInfo("America/New_York")
NOW = datetime.now(MLB_TZ)
TODAY = NOW.date().isoformat()
SEASON = NOW.year

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# =====================================================
# UTILITIES
# =====================================================

def fetch(url):
    with urlopen(url) as r:
        return json.loads(r.read().decode("utf-8"))

def safe(x):
    return x if x is not None else 0

# =====================================================
# PITCHER HELPERS
# =====================================================

def pitcher_stats(pid):
    out = {
        "hand": "N/A",
        "era": "N/A",
        "last5": "N/A"
    }
    try:
        profile = fetch(f"{BASE}/v1/people/{pid}")["people"][0]
        out["hand"] = profile["pitchHand"]["code"]
    except:
        pass

    try:
        s = fetch(
            f"{BASE}/v1/people/{pid}/stats?stats=season&group=pitching&season={SEASON}"
        )["stats"][0]["splits"][0]["stat"]
        out["era"] = s.get("era", "N/A")
    except:
        pass

    return out

# =====================================================
# HITTER HELPERS
# =====================================================

def hitter_stats(pid):
    try:
        s = fetch(
            f"{BASE}/v1/people/{pid}/stats?stats=season&group=hitting&season={SEASON}"
        )["stats"][0]["splits"][0]["stat"]

        return {
            "avg": s.get("avg", "N/A"),
            "hr": s.get("homeRuns", 0),
            "rbi": s.get("rbi", 0)
        }
    except:
        return {"avg": "N/A", "hr": 0, "rbi": 0}

# =====================================================
# BUILD DAILY / LIVE / POSTGAME
# =====================================================

schedule = fetch(
    f"{BASE}/v1/schedule?sportId=1&date={TODAY}&hydrate=probablePitcher"
)

daily = []
live = []
postgame = []

for d in schedule.get("dates", []):
    for g in d.get("games", []):

        away = g["teams"]["away"]["team"]
        home = g["teams"]["home"]["team"]
        status = g["status"]["abstractGameState"]

        ap = g["teams"]["away"].get("probablePitcher")
        hp = g["teams"]["home"].get("probablePitcher")

        game = {
            "away_team": away["name"],
            "home_team": home["name"],
            "venue": g["venue"]["name"],
            "start": g["gameDate"],
            "away_pitcher": pitcher_stats(ap["id"]) if ap else {},
            "home_pitcher": pitcher_stats(hp["id"]) if hp else {},
        }

        daily.append(game)

        # ---------------- LIVE ----------------
        if status in ["Live", "In Progress"]:
            feed = fetch(f"{BASE}/v1.1/game/{g['gamePk']}/feed/live")
            lines = feed["liveData"]["linescore"]
            box = feed["liveData"]["boxscore"]

            hot = []
            dom = []

            for side in ["away", "home"]:
                for bid in box["teams"][side]["batters"]:
                    b = box["teams"][side]["players"][f"ID{bid}"]["stats"]["batting"]
                    if safe(b.get("hits")) >= 2:
                        hot.append(
                            box["teams"][side]["players"][f"ID{bid}"]["person"]["fullName"]
                        )

                for pid in box["teams"][side]["pitchers"][-1:]:
                    p = box["teams"][side]["players"][f"ID{pid}"]["stats"]["pitching"]
                    if safe(p.get("strikeOuts")) >= 6:
                        dom.append(
                            box["teams"][side]["players"][f"ID{pid}"]["person"]["fullName"]
                        )

            live.append({
                "game": f"{away['name']} @ {home['name']}",
                "score": f"{lines['teams']['away']['runs']}–{lines['teams']['home']['runs']}",
                "inning": lines.get("currentInningOrdinal"),
                "hot_hitters": hot,
                "top_pitchers": dom
            })

        # ---------------- FINAL ----------------
        if status == "Final":
            feed = fetch(f"{BASE}/v1.1/game/{g['gamePk']}/feed/live")
            lines = feed["liveData"]["linescore"]
            box = feed["liveData"]["boxscore"]

            away_runs = lines["teams"]["away"]["runs"]
            home_runs = lines["teams"]["home"]["runs"]

            winner = away["name"] if away_runs > home_runs else home["name"]
            loser = home["name"] if away_runs > home_runs else away["name"]

            hitters = []
            pitchers = []

            for side in ["away", "home"]:
                for bid in box["teams"][side]["batters"]:
                    b = box["teams"][side]["players"][f"ID{bid}"]["stats"]["batting"]
                    if safe(b.get("hits")) >= 2 or safe(b.get("homeRuns")) >= 1:
                        hitters.append(
                            box["teams"][side]["players"][f"ID{bid}"]["person"]["fullName"]
                        )

                for pid in box["teams"][side]["pitchers"][:1]:
                    p = box["teams"][side]["players"][f"ID{pid}"]["stats"]["pitching"]
                    if safe(p.get("strikeOuts")) >= 6:
                        pitchers.append(
                            box["teams"][side]["players"][f"ID{pid}"]["person"]["fullName"]
                        )

            postgame.append({
                "game": f"{away['name']} @ {home['name']}",
                "winner": winner,
                "loser": loser,
                "final_score": f"{away_runs}–{home_runs}",
                "hitters": hitters,
                "pitchers": pitchers
            })

# =====================================================
# DAILY RECAP — GROQ
# =====================================================

recap = None

if postgame and client:
    try:
        games_text = "\n".join([
            f"{g['winner']} beat {g['loser']} ({g['final_score']})"
            for g in postgame
        ])

        prompt = f"""
You are a professional MLB beat writer.

Write a DAILY MLB recap with:
- A strong headline
- One paragraph per game
- Mentions of key hitters and pitchers
- A short "What It Means" section

Games:
{games_text}
"""

        response = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6
        )

        recap = {
            "date": TODAY,
            "headline": f"MLB Daily Recap — {NOW.strftime('%B %d, %Y')}",
            "article": response.choices[0].message.content.strip()
        }

    except Exception as e:
        recap = {
            "date": TODAY,
            "headline": f"MLB Daily Recap — {NOW.strftime('%B %d, %Y')}",
            "article": f"Groq error: {str(e)}"
        }

if not recap and postgame:
    recap = {
        "date": TODAY,
        "headline": f"MLB Daily Recap — {NOW.strftime('%B %d, %Y')}",
        "article": "One or more MLB games have gone final today. Recap generation will retry automatically."
    }

# =====================================================
# WRITE FILES (FORCE OVERWRITE)
# =====================================================

with open("daily_recap.json", "w") as f:
    json.dump(recap, f, indent=2)

json.dump({"updated_at": NOW.isoformat(), "games": daily}, open("daily.json", "w"), indent=2)
json.dump({"updated_at": NOW.isoformat(), "games": live}, open("live.json", "w"), indent=2)
json.dump({"updated_at": NOW.isoformat(), "games": postgame}, open("postgame.json", "w"), indent=2)
