import json
from datetime import datetime
from urllib.request import urlopen
from zoneinfo import ZoneInfo

BASE = "https://statsapi.mlb.com/api"
MLB_TZ = ZoneInfo("America/New_York")
NOW = datetime.now(MLB_TZ)
TODAY = NOW.date().isoformat()
SEASON = NOW.year

# =====================================================
# Utilities
# =====================================================

def fetch(url):
    with urlopen(url) as r:
        return json.loads(r.read().decode("utf-8"))

def n(x): return x if x is not None else 0

# =====================================================
# Pitcher Evaluation
# =====================================================

def pitcher_hand(pid):
    try:
        return fetch(f"{BASE}/v1/people/{pid}")["people"][0]["pitchHand"]["code"]
    except:
        return "N/A"

def pitcher_last5(pid):
    logs = fetch(
        f"{BASE}/v1/people/{pid}/stats"
        f"?stats=gameLog&group=pitching&season={SEASON}"
    )["stats"][0]["splits"][:5]

    ip = k = bb = h = er = 0
    for g in logs:
        ip += float(g["stat"].get("inningsPitched","0"))
        k  += n(g["stat"].get("strikeOuts"))
        bb += n(g["stat"].get("baseOnBalls"))
        h  += n(g["stat"].get("hits"))
        er += n(g["stat"].get("earnedRuns"))

    games = len(logs)
    whip = (h + bb) / ip if ip else None

    quality = games >= 3 and ip/games >= 6 and er/games <= 3
    elite = ip/games >= 7 and k/games >= 8 and whip is not None and whip <= 1.00

    return {
        "avg_ip": round(ip/games,2) if games else "N/A",
        "avg_k": round(k/games,2) if games else "N/A",
        "avg_bb": round(bb/games,2) if games else "N/A",
        "whip": round(whip,2) if whip else "N/A",
        "quality": quality,
        "elite": elite
    }

def pitcher_era(pid):
    try:
        return fetch(
            f"{BASE}/v1/people/{pid}/stats"
            f"?stats=season&group=pitching&season={SEASON}"
        )["stats"][0]["splits"][0]["stat"]["era"]
    except:
        return "N/A"

# =====================================================
# Hitter Evaluation
# =====================================================

def hitter_season_stats(pid):
    s = fetch(
        f"{BASE}/v1/people/{pid}/stats"
        f"?stats=season&group=hitting&season={SEASON}"
    )["stats"][0]["splits"][0]["stat"]

    ab = n(s.get("atBats"))
    so = n(s.get("strikeOuts"))
    bb = n(s.get("baseOnBalls"))
    hr = n(s.get("homeRuns"))
    avg = s.get("avg","N/A")

    pa = ab + bb
    bip = ab - so - hr
    bip_pa = round(bip/pa,2) if pa else "N/A"

    k_rate = round((so/pa)*100,1) if pa else None
    bb_rate = round((bb/pa)*100,1) if pa else None

    return {
        "avg": avg,
        "k_rate": k_rate,
        "bb_rate": bb_rate,
        "bip_pa": bip_pa,
        "so": so,
        "bb": bb
    }

def batting_order_tier(stats):
    if stats["avg"]!="N/A" and float(stats["avg"])>=.285 and stats["k_rate"]<=18:
        return "Top‑Order"
    if stats["k_rate"] and stats["k_rate"]<=25:
        return "Middle‑Order"
    return "Bottom‑Order"

def hit_streak(pid):
    logs = fetch(
        f"{BASE}/v1/people/{pid}/stats"
        f"?stats=gameLog&group=hitting&season={SEASON}"
    )["stats"][0]["splits"]
    streak=0
    for g in logs:
        if n(g["stat"].get("hits"))>0: streak+=1
        else: break
    return streak

def risp_stats(pid):
    try:
        s = fetch(
            f"{BASE}/v1/people/{pid}/stats"
            f"?stats=season&group=hitting&sitCodes=risp&season={SEASON}"
        )["stats"][0]["splits"][0]["stat"]
        return {"avg":s.get("avg","N/A"),"hits":s.get("hits","N/A")}
    except:
        return {"avg":"N/A","hits":"N/A"}

# =====================================================
# Team Hitters
# =====================================================

def team_hitters(team_id):
    roster = fetch(f"{BASE}/v1/teams/{team_id}/roster")["roster"]
    return [
        {"id":p["person"]["id"],"name":p["person"]["fullName"]}
        for p in roster if p["position"]["type"]!="Pitcher"
    ][:9]

# =====================================================
# DAILY JSON
# =====================================================

schedule = fetch(
    f"{BASE}/v1/schedule?sportId=1&date={TODAY}&hydrate=probablePitcher"
)

daily=[]

for d in schedule.get("dates",[]):
    for g in d.get("games",[]):
        away=g["teams"]["away"]["team"]
        home=g["teams"]["home"]["team"]
        ap=g["teams"]["away"].get("probablePitcher")
        hp=g["teams"]["home"].get("probablePitcher")

        game={
            "away_team":away["name"],
            "home_team":home["name"],
            "venue":g["venue"]["name"],
            "start":g["gameDate"],
            "away_pitcher":{},
            "home_pitcher":{},
            "away_hitters":[],
            "home_hitters":[]
        }

        if ap:
            game["away_pitcher"]={
                "name":ap["fullName"],
                "hand":pitcher_hand(ap["id"]),
                "era":pitcher_era(ap["id"]),
                **pitcher_last5(ap["id"])
            }
        if hp:
            game["home_pitcher"]={
                "name":hp["fullName"],
                "hand":pitcher_hand(hp["id"]),
                "era":pitcher_era(hp["id"]),
                **pitcher_last5(hp["id"])
            }

        for side,team in [("away_hitters",away),("home_hitters",home)]:
            for h in team_hitters(team["id"]):
                stats=hitter_season_stats(h["id"])
                game[side].append({
                    "name":h["name"],
                    "tier":batting_order_tier(stats),
                    "stats":stats,
                    "streak":hit_streak(h["id"]),
                    "risp":risp_stats(h["id"])
                })

        daily.append(game)

with open("daily.json","w") as f:
    json.dump({"updated_at":NOW.isoformat(),"games":daily},f,indent=2)
