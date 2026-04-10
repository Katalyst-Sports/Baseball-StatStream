import json
from datetime import datetime
from urllib.request import urlopen
from zoneinfo import ZoneInfo

BASE = "https://statsapi.mlb.com/api"
MLB_TZ = ZoneInfo("America/New_York")
NOW = datetime.now(MLB_TZ)
TODAY = NOW.date().isoformat()
SEASON = NOW.year

# ============================================================================
# Helpers
# ============================================================================

def fetch(url):
    with urlopen(url) as r:
        return json.loads(r.read().decode("utf-8"))

def pitcher_hand(pid):
    try:
        return fetch(f"{BASE}/v1/people/{pid}")["people"][0]["pitchHand"]["code"]
    except:
        return "N/A"

def pitcher_last5(pid):
    try:
        logs = fetch(
            f"{BASE}/v1/people/{pid}/stats"
            f"?stats=gameLog&group=pitching&season={SEASON}"
        )["stats"][0]["splits"][:5]

        outs = k = bb = 0
        for g in logs:
            ip = g["stat"].get("inningsPitched", "0")
            if "." in ip:
                w, f = ip.split(".")
                outs += int(w) * 3 + int(f)
            else:
                outs += int(ip) * 3
            k += int(g["stat"].get("strikeOuts", 0))
            bb += int(g["stat"].get("baseOnBalls", 0))

        return {
            "avg_ip": round((outs / 3) / len(logs), 2) if logs else "N/A",
            "avg_k": round(k / len(logs), 2) if logs else "N/A",
            "avg_bb": round(bb / len(logs), 2) if logs else "N/A"
        }
    except:
        return {"avg_ip":"N/A","avg_k":"N/A","avg_bb":"N/A"}

def pitcher_era(pid):
    try:
        return fetch(
            f"{BASE}/v1/people/{pid}/stats"
            f"?stats=season&group=pitching&season={SEASON}"
        )["stats"][0]["splits"][0]["stat"]["era"]
    except:
        return "N/A"

def team_hitters(team_id):
    try:
        roster = fetch(f"{BASE}/v1/teams/{team_id}/roster")["roster"]
        return [
            {"id": p["person"]["id"], "name": p["person"]["fullName"]}
            for p in roster if p["position"]["type"] != "Pitcher"
        ][:9]
    except:
        return []

def hitter_split(pid, hand):
    sit = "vr" if hand == "R" else "vl"
    try:
        s = fetch(
            f"{BASE}/v1/people/{pid}/stats"
            f"?stats=statSplits&group=hitting&sitCodes={sit}&season={SEASON}"
        )["stats"][0]["splits"]
        if not s:
            return {"avg":"N/A","hits":"N/A"}
        st = s[0]["stat"]
        return {"avg": st.get("avg","N/A"), "hits": st.get("hits","N/A")}
    except:
        return {"avg":"N/A","hits":"N/A"}

def hit_streak(pid):
    try:
        logs = fetch(
            f"{BASE}/v1/people/{pid}/stats"
            f"?stats=gameLog&group=hitting&season={SEASON}"
        )["stats"][0]["splits"]
        streak = 0
        for g in logs[:5]:
            if int(g["stat"].get("hits",0)) > 0:
                streak += 1
            else:
                break
        return streak if streak >= 3 else 0
    except:
        return 0

# ============================================================================
# DAILY BASELINE (daily.json)
# ============================================================================

schedule = fetch(
    f"{BASE}/v1/schedule?sportId=1&date={TODAY}&hydrate=probablePitcher"
)

games = []

for d in schedule.get("dates", []):
    for g in d.get("games", []):
        away = g["teams"]["away"]["team"]
        home = g["teams"]["home"]["team"]

        ap = g["teams"]["away"].get("probablePitcher")
        hp = g["teams"]["home"].get("probablePitcher")

        ah = pitcher_hand(ap["id"]) if ap else "R"
        hh = pitcher_hand(hp["id"]) if hp else "R"

        away_hitters = team_hitters(away["id"])
        home_hitters = team_hitters(home["id"])

        games.append({
            "start_time": g["gameDate"],
            "venue": g["venue"]["name"],
            "away_team": away["name"],
            "home_team": home["name"],

            "away_pitcher": {
                "name": ap["fullName"] if ap else "TBD",
                "hand": ah,
                "era": pitcher_era(ap["id"]) if ap else "N/A",
                "last5": pitcher_last5(ap["id"]) if ap else {}
            },

            "home_pitcher": {
                "name": hp["fullName"] if hp else "TBD",
                "hand": hh,
                "era": pitcher_era(hp["id"]) if hp else "N/A",
                "last5": pitcher_last5(hp["id"]) if hp else {}
            },

            "away_hitters": [
                {
                    "name": h["name"],
                    "vsRHP": hitter_split(h["id"], "R"),
                    "vsLHP": hitter_split(h["id"], "L"),
                    "hot_streak": hit_streak(h["id"])
                } for h in away_hitters
            ],

            "home_hitters": [
                {
                    "name": h["name"],
                    "vsRHP": hitter_split(h["id"], "R"),
                    "vsLHP": hitter_split(h["id"], "L"),
                    "hot_streak": hit_streak(h["id"])
                } for h in home_hitters
            ]
        })

with open("daily.json","w") as f:
    json.dump({"updated_at":NOW.isoformat(),"games":games}, f, indent=2)

# ============================================================================
# LIVE GAMES (live.json)
# ============================================================================

live_games = []

for d in schedule.get("dates", []):
    for g in d.get("games", []):
        if g["status"]["abstractGameState"] == "Live":
            feed = fetch(f"{BASE}/v1.1/game/{g['gamePk']}/feed/live")
            box = feed["liveData"]["boxscore"]
            lines = feed["liveData"]["linescore"]

            hot_hitters = []
            top_pitchers = []

            for side in ["away","home"]:
                for bid in box["teams"][side]["batters"]:
                    b = box["teams"][side]["players"][f"ID{bid}"]["stats"]["batting"]
                    if b.get("hits",0) >= 2:
                        hot_hitters.append({
                            "name": box["teams"][side]["players"][f"ID{bid}"]["person"]["fullName"],
                            "hits": b["hits"]
                        })

                pitchers = box["teams"][side]["pitchers"]
                players = box["teams"][side]["players"]

                if pitchers:
                    sp = pitchers[0]
                    cp = pitchers[-1]
                    bullpen = sp != cp
                    ps = players[f"ID{cp}"]["stats"]["pitching"]
                    if ps.get("strikeOuts",0) >= 6 and ps.get("earnedRuns",0) <= 2:
                        top_pitchers.append({
                            "name": players[f"ID{cp}"]["person"]["fullName"],
                            "k": ps["strikeOuts"],
                            "er": ps["earnedRuns"]
                        })

            live_games.append({
                "score": f"{lines['teams']['away']['runs']} – {lines['teams']['home']['runs']}",
                "inning": lines.get("currentInningOrdinal"),
                "hot_hitters": hot_hitters,
                "top_pitchers": top_pitchers,
                "bullpen_active": False
            })

with open("live.json","w") as f:
    json.dump({"updated_at":NOW.isoformat(),"games":live_games}, f, indent=2)

# ============================================================================
# POSTGAME SUMMARIES (postgame.json)
# ============================================================================

postgames = []

for d in schedule.get("dates", []):
    for g in d.get("games", []):
        if g["status"]["abstractGameState"] == "Final":
            feed = fetch(f"{BASE}/v1.1/game/{g['gamePk']}/feed/live")
            lines = feed["liveData"]["linescore"]

            postgames.append({
                "game": f"{g['teams']['away']['team']['name']} @ {g['teams']['home']['team']['name']}",
                "score": f"{lines['teams']['away']['runs']} – {lines['teams']['home']['runs']}"
            })

with open("postgame.json","w") as f:
    json.dump({"updated_at":NOW.isoformat(),"games":postgames}, f, indent=2)
