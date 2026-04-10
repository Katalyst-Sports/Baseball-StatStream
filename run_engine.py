import json
from datetime import datetime
from urllib.request import urlopen
from zoneinfo import ZoneInfo

BASE = "https://statsapi.mlb.com/api"
MLB_TZ = ZoneInfo("America/New_York")
NOW = datetime.now(MLB_TZ)
TODAY = NOW.date().isoformat()
SEASON = NOW.year

# ---------------- UTIL ----------------

def fetch(url):
    with urlopen(url) as r:
        return json.loads(r.read().decode("utf-8"))

def n(x):
    return x if x is not None else 0

# ---------------- PITCHERS ----------------

def pitcher_hand(pid):
    try:
        return fetch(f"{BASE}/v1/people/{pid}")["people"][0]["pitchHand"]["code"]
    except:
        return "N/A"

def pitcher_era(pid):
    try:
        return fetch(
            f"{BASE}/v1/people/{pid}/stats?stats=season&group=pitching&season={SEASON}"
        )["stats"][0]["splits"][0]["stat"].get("era", "N/A")
    except:
        return "N/A"

def pitcher_last5(pid):
    try:
        data = fetch(
            f"{BASE}/v1/people/{pid}/stats?stats=gameLog&group=pitching&season={SEASON}"
        )
        splits = data["stats"][0].get("splits", [])
        if not splits:
            raise ValueError

        logs = splits[:5]
        ip = k = bb = h = er = 0.0

        for g in logs:
            raw = g["stat"].get("inningsPitched", "0")
            if "." in raw:
                w, f = raw.split(".")
                ip += int(w) + int(f)/3
            else:
                ip += float(raw)

            k  += n(g["stat"].get("strikeOuts"))
            bb += n(g["stat"].get("baseOnBalls"))
            h  += n(g["stat"].get("hits"))
            er += n(g["stat"].get("earnedRuns"))

        games = len(logs)
        whip = (h + bb) / ip if ip else None
        kbb = round(k / bb, 2) if bb else "∞"

        return {
            "avg_ip": round(ip / games, 2),
            "avg_k": round(k / games, 2),
            "avg_bb": round(bb / games, 2),
            "whip": round(whip, 2) if whip else "N/A",
            "k_bb": kbb,
            "command": (
                "Elite Command" if kbb == "∞" or kbb >= 4 else
                "Strong Command" if kbb >= 3 else
                "Average Command" if kbb >= 2 else
                "Below Average Command"
            ),
            "quality": ip / games >= 6 and er / games <= 3,
            "elite": ip / games >= 7 and k / games >= 8 and whip is not None and whip <= 1.00
        }

    except:
        return {
            "avg_ip": "N/A",
            "avg_k": "N/A",
            "avg_bb": "N/A",
            "whip": "N/A",
            "k_bb": "N/A",
            "command": "N/A",
            "quality": False,
            "elite": False
        }

# ---------------- HITTERS ----------------

def hitter_season(pid):
    try:
        s = fetch(
            f"{BASE}/v1/people/{pid}/stats?stats=season&group=hitting&season={SEASON}"
        )["stats"][0]["splits"][0]["stat"]

        ab = n(s.get("atBats"))
        so = n(s.get("strikeOuts"))
        bb = n(s.get("baseOnBalls"))
        hr = n(s.get("homeRuns"))
        avg = s.get("avg", "N/A")

        pa = ab + bb
        bip = ab - so - hr

        return {
            "avg": avg,
            "k_rate": round((so/pa)*100,1) if pa else None,
            "bb_rate": round((bb/pa)*100,1) if pa else None,
            "bip_pa": round(bip/pa,2) if pa else "N/A"
        }
    except:
        return {"avg":"N/A","k_rate":None,"bb_rate":None,"bip_pa":"N/A"}

def last10_ab_overall(pid):
    try:
        logs = fetch(
            f"{BASE}/v1/people/{pid}/stats?stats=gameLog&group=hitting&season={SEASON}"
        )["stats"][0]["splits"]

        ab = hits = 0
        for g in logs:
            if ab >= 10:
                break
            game_ab = n(g["stat"].get("atBats"))
            game_hits = n(g["stat"].get("hits"))
            take = min(10-ab, game_ab)
            ab += take
            hits += min(game_hits, take)

        return {"ab":ab,"hits":hits,"avg":round(hits/ab,3) if ab else "N/A"}
    except:
        return {"ab":0,"hits":0,"avg":"N/A"}

def hit_streak(pid):
    try:
        logs = fetch(
            f"{BASE}/v1/people/{pid}/stats?stats=gameLog&group=hitting&season={SEASON}"
        )["stats"][0]["splits"]
        streak=0
        for g in logs:
            if n(g["stat"].get("hits"))>0:
                streak+=1
            else:
                break
        return streak
    except:
        return 0

def risp(pid):
    try:
        s = fetch(
            f"{BASE}/v1/people/{pid}/stats?stats=season&group=hitting&sitCodes=risp&season={SEASON}"
        )["stats"][0]["splits"][0]["stat"]
        return {"avg":s.get("avg","N/A"),"hits":s.get("hits","N/A")}
    except:
        return {"avg":"N/A","hits":"N/A"}

def team_hitters(team_id):
    try:
        roster = fetch(f"{BASE}/v1/teams/{team_id}/roster")["roster"]
        return [
            {"id":p["person"]["id"],"name":p["person"]["fullName"]}
            for p in roster if p["position"]["type"]!="Pitcher"
        ][:9]
    except:
        return []

# ---------------- BUILD DAILY ----------------

schedule = fetch(
    f"{BASE}/v1/schedule?sportId=1&date={TODAY}&hydrate=probablePitcher"
)

daily = []

for d in schedule.get("dates", []):
    for g in d.get("games", []):
        away = g["teams"]["away"]["team"]
        home = g["teams"]["home"]["team"]
        ap = g["teams"]["away"].get("probablePitcher")
        hp = g["teams"]["home"].get("probablePitcher")

        game = {
            "away_team": away["name"],
            "home_team": home["name"],
            "venue": g["venue"]["name"],
            "start": g["gameDate"],
            "away_pitcher": {},
            "home_pitcher": {},
            "away_hitters": [],
            "home_hitters": []
        }

        if ap:
            game["away_pitcher"] = {
                "name": ap["fullName"],
                "hand": pitcher_hand(ap["id"]),
                "era": pitcher_era(ap["id"]),
                **pitcher_last5(ap["id"])
            }

        if hp:
            game["home_pitcher"] = {
                "name": hp["fullName"],
                "hand": pitcher_hand(hp["id"]),
                "era": pitcher_era(hp["id"]),
                **pitcher_last5(hp["id"])
            }

        for side, team in [("away_hitters", away), ("home_hitters", home)]:
            for h in team_hitters(team["id"]):
                stats = hitter_season(h["id"])
                streak = hit_streak(h["id"])
                game[side].append({
                    "name": h["name"],
                    "tier": (
                        "Top‑Order" if stats["avg"]!="N/A" and float(stats["avg"])>=0.285 else
                        "Middle‑Order" if stats["k_rate"] and stats["k_rate"]<=25 else
                        "Bottom‑Order"
                    ),
                    "stats": stats,
                    "last10": last10_ab_overall(h["id"]),
                    "streak": streak,
                    "risp": risp(h["id"])
                })

        daily.append(game)

json.dump({"updated_at":NOW.isoformat(),"games":daily}, open("daily.json","w"), indent=2)
