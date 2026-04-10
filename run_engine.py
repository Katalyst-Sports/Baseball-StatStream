import json
from datetime import datetime
from urllib.request import urlopen
from zoneinfo import ZoneInfo

# -----------------------------------
# CONFIG
# -----------------------------------

MLB_TZ = ZoneInfo("America/New_York")
NOW = datetime.now(MLB_TZ)
TODAY = NOW.date().isoformat()
SEASON = NOW.year

BASE = "https://statsapi.mlb.com/api/v1"

# -----------------------------------
# HELPERS
# -----------------------------------

def fetch(url):
    with urlopen(url) as r:
        return json.loads(r.read().decode("utf-8"))

def get_pitcher_hand(pid):
    try:
        return fetch(f"{BASE}/people/{pid}")["people"][0]["pitchHand"]["code"]
    except:
        return "N/A"

def pitcher_last5(pid):
    try:
        logs = fetch(
            f"{BASE}/people/{pid}/stats?stats=gameLog&group=pitching&season={SEASON}"
        )["stats"][0]["splits"][:5]

        outs = k = bb = 0
        for g in logs:
            ip = g["stat"].get("inningsPitched", "0")
            if "." in ip:
                w, f = ip.split(".")
                outs += int(w)*3 + int(f)
            else:
                outs += int(ip)*3
            k += int(g["stat"].get("strikeOuts", 0))
            bb += int(g["stat"].get("baseOnBalls", 0))

        return {
            "avg_ip": round((outs / 3) / len(logs), 2) if logs else "N/A",
            "avg_k": round(k / len(logs), 2) if logs else "N/A",
            "avg_bb": round(bb / len(logs), 2) if logs else "N/A",
        }
    except:
        return {"avg_ip": "N/A", "avg_k": "N/A", "avg_bb": "N/A"}

def pitcher_era(pid):
    try:
        s = fetch(
            f"{BASE}/people/{pid}/stats?stats=season&group=pitching&season={SEASON}"
        )
        return s["stats"][0]["splits"][0]["stat"].get("era", "N/A")
    except:
        return "N/A"

def team_hitters(team_id):
    """Returns likely everyday starters from roster"""
    hitters = []
    try:
        roster = fetch(f"{BASE}/teams/{team_id}/roster")["roster"]
        for p in roster:
            if p["position"]["type"] != "Pitcher":
                hitters.append({
                    "id": p["person"]["id"],
                    "name": p["person"]["fullName"]
                })
        return hitters[:9]
    except:
        return []

def hitter_last10_vs_hand(pid, hand):
    sit = "vr" if hand == "R" else "vl"
    try:
        s = fetch(
            f"{BASE}/people/{pid}/stats?"
            f"stats=statSplits&group=hitting&sitCodes={sit}&season={SEASON}"
        )["stats"][0]["splits"]

        if not s:
            return {"pa": "N/A", "hits": "N/A", "avg": "N/A"}

        st = s[0]["stat"]
        if int(st.get("plateAppearances", 0)) < 10:
            return {"pa": "<10", "hits": st.get("hits", 0), "avg": st.get("avg", "N/A")}

        return {
            "pa": 10,
            "hits": st.get("hits", 0),
            "avg": st.get("avg", "N/A")
        }
    except:
        return {"pa": "N/A", "hits": "N/A", "avg": "N/A"}

# -----------------------------------
# MAIN — ALWAYS INCLUDE ALL GAMES
# -----------------------------------

schedule = fetch(f"{BASE}/schedule?sportId=1&date={TODAY}&hydrate=probablePitcher")

games = []

for d in schedule.get("dates", []):
    for g in d.get("games", []):

        away = g["teams"]["away"]["team"]
        home = g["teams"]["home"]["team"]

        away_p = g["teams"]["away"].get("probablePitcher")
        home_p = g["teams"]["home"].get("probablePitcher")

        def pitcher_block(prob):
            if not prob:
                return {
                    "name": "TBD",
                    "hand": "N/A",
                    "era": "N/A",
                    "last5": {"avg_ip":"N/A","avg_k":"N/A","avg_bb":"N/A"}
                }

            return {
                "name": prob["fullName"],
                "hand": get_pitcher_hand(prob["id"]),
                "era": pitcher_era(prob["id"]),
                "last5": pitcher_last5(prob["id"])
            }

        hand_away = get_pitcher_hand(away_p["id"]) if away_p else "R"
        hand_home = get_pitcher_hand(home_p["id"]) if home_p else "R"

        away_hitters = team_hitters(away["id"])
        home_hitters = team_hitters(home["id"])

        games.append({
            "start_time": g["gameDate"],
            "venue": g["venue"]["name"],
            "away_team": away["name"],
            "home_team": home["name"],
            "away_pitcher": pitcher_block(away_p),
            "home_pitcher": pitcher_block(home_p),

            "away_hitters": [
                {
                    "name": h["name"],
                    "vsRHP": hitter_last10_vs_hand(h["id"], "R"),
                    "vsLHP": hitter_last10_vs_hand(h["id"], "L")
                } for h in away_hitters
            ],
            "home_hitters": [
                {
                    "name": h["name"],
                    "vsRHP": hitter_last10_vs_hand(h["id"], "R"),
                    "vsLHP": hitter_last10_vs_hand(h["id"], "L")
                } for h in home_hitters
            ]
        })

with open("daily.json", "w") as f:
    json.dump({
        "updated_at": NOW.isoformat(),
        "games": games,
        "disclaimer":
            "All stats are descriptive and based on historical MLB data only."
    }, f, indent=2)
