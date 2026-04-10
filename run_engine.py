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

        if kbb == "∞" or kbb >= 4:
            command = "Elite Command"
        elif kbb >= 3:
            command = "Strong Command"
        elif kbb >= 2:
            command = "Average Command"
        else:
            command = "Below Average Command"

        return {
            "avg_ip": round(ip / games, 2),
            "avg_k": round(k / games, 2),
            "avg_bb": round(bb / games, 2),
            "whip": round(whip, 2) if whip else "N/A",
            "k_bb": kbb,
            "command": command,
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

def batting_tier(stats):
    if stats["avg"]!="N/A" and float(stats["avg"])>=0.285 and stats["k_rate"]<=18:
        return "Top‑Order"
    if stats["k_rate"] and stats["k_rate"]<=25:
        return "Middle‑Order"
    return "Bottom‑Order"

def hit_streak(pid):
    try:
        logs = fetch(
            f"{BASE}/v1/people/{pid}/stats?stats=gameLog&group=hitting&season={SEASON}"
        )["stats"][0]["splits"]
        streak=0
        for g in logs:
            if n(g["stat"].get("hits"))>0: streak+=1
            else: break
        return streak
    except:
        return 0

def last10_ab_vs_hand(pid, hand):
    try:
        logs = fetch(
            f"{BASE}/v1/people/{pid}/stats?stats=gameLog&group=hitting&season={SEASON}"
        )["stats"][0]["splits"]

        ab = hits = 0
        for g in logs:
            if ab >= 10:
                break
            opp = g.get("opponent", {})
            if opp.get("pitcherHand") != hand:
                continue
            game_ab = n(g["stat"].get("atBats"))
            game_hits = n(g["stat"].get("hits"))
            take = min(10-ab, game_ab)
            ab += take
            hits += min(game_hits, take)

        return {"ab":ab,"hits":hits,"avg":round(hits/ab,3) if ab else "N/A"}
    except:
        return {"ab":0,"hits":0,"avg":"N/A"}

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
live = []

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
                game[side].append({
                    "name": h["name"],
                    "tier": batting_tier(stats),
                    "stats": stats,
                    "vsRHP": last10_ab_vs_hand(h["id"], "R"),
                    "vsLHP": last10_ab_vs_hand(h["id"], "L"),
                    "streak": hit_streak(h["id"]),
                    "risp": risp(h["id"])
                })

        daily.append(game)

        if g["status"]["abstractGameState"] in ["Live","In Progress"]:
            feed = fetch(f"{BASE}/v1.1/game/{g['gamePk']}/feed/live")
            lines = feed["liveData"]["linescore"]
            box = feed["liveData"]["boxscore"]

            hot = []
            dom = []

            for side in ["away","home"]:
                for bid in box["teams"][side]["batters"]:
                    b = box["teams"][side]["players"][f"ID{bid}"]["stats"]["batting"]
                    tb = n(b.get("hits"))+n(b.get("doubles"))+2*n(b.get("triples"))+3*n(b.get("homeRuns"))
                    if b.get("hits",0)>=2 or tb>=3:
                        hot.append(box["teams"][side]["players"][f"ID{bid}"]["person"]["fullName"])

                for pid in box["teams"][side]["pitchers"][-1:]:
                    p = box["teams"][side]["players"][f"ID{pid}"]["stats"]["pitching"]
                    if p.get("strikeOuts",0)>=6 and p.get("earnedRuns",0)<=2:
                        dom.append(box["teams"][side]["players"][f"ID{pid}"]["person"]["fullName"])

            live.append({
                "score": f"{lines['teams']['away']['runs']}–{lines['teams']['home']['runs']}",
                "inning": lines.get("currentInningOrdinal"),
                "hot_hitters": hot,
                "top_pitchers": dom
            })

json.dump({"updated_at":NOW.isoformat(),"games":daily}, open("daily.json","w"), indent=2)
json.dump({"updated_at":NOW.isoformat(),"games":live}, open("live.json","w"), indent=2)
