# WalkLah Backend Handoff

## Run it (Windows PowerShell)
```
cd backend
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```
- API: http://127.0.0.1:8000 — interactive docs at http://127.0.0.1:8000/docs
- The graph loads from `tests/backend/data/walklah.graphml` when `data/` has no copy (no download).
- Reports, confirmations, audits and opt-in route statistics live in `data/walklah.db` (SQLite,
  gitignored), so restarts and `--reload` keep the demo data.
- Operator actions need `X-Operator-Key` (env `WALKLAH_OPERATOR_KEY`; demo default `walklah-demo`).
- Tests: `.venv\Scripts\python.exe -m pytest -q` (in-memory database).

Full API: `docs/API_CONTRACT.md` (v2).

## What changed in v2 (feat/backend-comfort)
- `GET /routes`: any two points → Shortest (baseline), Practical (necessity walkers) and Enjoyable
  (choice walkers) routes with reasons, shade/lighting/crossings/steps and warnings for unverified reports.
- Shade by time of day: NOAA sun position + building shadows (OSM footprints) + Meta/WRI 1 m tree canopy +
  covered walkways. Lighting: team audit > OSM `lit` > street lamps > unknown.
- Walking-condition layer in `comfort/` built by `scripts/build_comfort.py` (OSM via Overpass, cached in
  `comfort/osm_raw/`; canopy via `scripts/fetch_canopy.py`, needs `pip install rasterio`).
- Reports: SQLite, verification history, community confirmations, automatic expiry of temporary hazards,
  operator closures, snapping limited to 60 m.
- Insights: S.T.E.P. overview, ranked issues, hypothetical intervention scenarios, audit upload, walk feedback.

## Measured data coverage (UM graph, 18 Oct 2026)
Sidewalk status known 29% · lighting known 4% · covered 7% · tree canopy 13% · real building heights 8.5%.
The lighting audit (`GET /audit/template`) is what turns "unknown" into evidence.

## Demo story
1. Route LRT Universiti (3.114548, 101.661702) → Dewan Tunku Canselor at 13:00 and 17:30: Enjoyable is ~60%+
   shaded vs ~32% on the shortest route.
2. Report a blocked walkway at 3.11916, 101.65565 → pending = warning only.
3. Verify it (operator) → Practical/Enjoyable avoid it (Kantin → Dewan Tunku Canselor 558 m → ~681 m).
4. Insights › Prioritise: scenario "remove barrier" shows the metres saved per place pair (hypothetical).
5. Mark cleared → routes return.
