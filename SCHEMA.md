# MLB DASHBOARD SCHEMA FREEZE (v1.0)

These files and fields MUST NOT be removed or renamed.

Files:
- run_engine.py
- index.html
- daily.json
- live.json
- postgame.json

Guaranteed data:
- Pitcher last 5 averages (IP, K, BB, WHIP)
- Pitcher Quality / Elite flags
- Hitter splits vs RHP and LHP
- Batting order tiers
- BIP/PA
- RISP hitting
- Live scoring tracker
- Postgame contact grades

New features must be ADDITIVE only.
