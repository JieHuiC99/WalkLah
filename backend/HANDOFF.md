# WalkLah Backend Handoff

## Run it (Windows PowerShell)
```
cd backend
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt   # requirements.txt alone: just the API
$env:WALKLAH_MY_DATA = "C:\walklah-data"      # folder with walklah_my.sqlite (see below); optional
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```
- API: http://127.0.0.1:8000 — interactive docs at http://127.0.0.1:8000/docs
- With the Malaysia database, routes and search work anywhere in Malaysia. Without it, the API serves the
  UM pilot graph (`tests/backend/data/walklah.graphml`) exactly as before, and `/pilot` says so.
- Reports, confirmations, audits and opt-in route statistics live in `data/walklah.db` (SQLite, gitignored);
  report photos in `data/photos/` (or `WALKLAH_PHOTOS`), deleted when reports are cleared.
- Insights › Track › Sample reports loads labelled example reports with credited photos
  (`sample_data/`, `POST/DELETE /admin/sample-data`); they are tagged "Sample" and add no trip statistics.
- Insights is open by default. Set `WALKLAH_OPERATOR_KEY` to require the `X-Operator-Key` header for any
  public deployment. Community writes are rate limited (`WALKLAH_RATE_LIMITS`, default 10 reports and
  60 votes per phone per hour).
- No compiled GIS libraries are needed to run the API or tests: `app/geo.py` does UTM conversion, WKB
  polygons, point-in-polygon and distances with numpy/scipy, and `app/shade.py` uses a 2 m building-height
  grid. (Windows Smart App Control blocks the PROJ/GEOS DLLs in pyproj/shapely on some laptops.) The
  GIS stack is only needed for data builds: `pip install -r requirements-data.txt`.
- Tests: `.venv\Scripts\python.exe -m pytest -q` (in-memory database, synthetic Malaysia database; no download).

Full API: `docs/API_CONTRACT.md` (v3).

## Build the Malaysia database (once, ~35 min, ~1.6 GB)
Keep the data outside OneDrive/Dropbox folders (it is large and rewritten as a whole).
```
.venv\Scripts\python.exe -m pip install -r requirements-data.txt      # osmium, duckdb
# 1. OpenStreetMap extract (~250 MB):
#    https://download.geofabrik.de/asia/malaysia-singapore-brunei-latest.osm.pbf
# 2. Build (add --overture to merge Overture Maps places; downloads only Malaysia rows, ~60 MB)
.venv\Scripts\python.exe scripts\build_malaysia.py --pbf C:\walklah-data\src\malaysia-singapore-brunei-latest.osm.pbf --overture --out C:\walklah-data
# 3. Optional: cache tree cover for the main cities so first routes there are faster
$env:WALKLAH_MY_DATA = "C:\walklah-data"; .venv\Scripts\python.exe scripts\prefetch_canopy.py
```
- Build of 18 Oct 2026: 3.55 M path segments (419,565 km), 1.71 M buildings, 671,090 places
  (203,121 OSM + 467,969 Overture after de-duplication), 65,894 crossings, 2,488 street lamps.
- Search aliases can be recomputed without a rebuild: `scripts\build_malaysia.py --refresh-aliases --out …`.

## Deployed API (Vercel + Supabase, free tiers)
The 1.6 GB database does not fit a serverless function, so the deployed API uses pre-built pieces:
- **Routing tiles** for Klang Valley, Penang, Johor Bahru, Ipoh, Kota Kinabalu, Kuching and Melaka:
  `scripts\export_tiles.py C:\walklah-data\packs` (about 4 min, about 165 MB), uploaded to the public
  Supabase Storage bucket `tiles`. `WALKLAH_TILES_URL` points the API at them (a local folder works too);
  trips elsewhere get "WalkLah doesn't cover this area yet", and `/pilot` lists `covered_areas`.
- **Database**: `DATABASE_URL` (Supabase pooler, `postgresql://…`) switches reports, votes, audits and
  statistics to Postgres (`app/db.py`, pg8000), and search to a Postgres copy of the covered cities' places
  (`scripts\upload_places.py`).
  Use the **transaction pooler** address (port 6543): the session pooler allows only 15 clients, which a few
  serverless instances use up, and the direct `db.…supabase.co` address is IPv6-only. `app/db.py` sends each
  statement as one simple-protocol message with autocommit, because the transaction pooler may run the steps
  of a prepared statement on different server connections.
- **Photos**: with `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`, uploads go to the public bucket `photos`.
- **CORS**: `WALKLAH_CORS_ORIGINS` = the site's URL (comma-separated for several).
- Upload scripts read secrets from `backend\.env.deploy` (git-ignored; `DATABASE_URL`, `SUPABASE_URL`,
  `SUPABASE_SERVICE_KEY`) and never print them. The service key is server-only: never put it in a `VITE_*`
  variable.
- Vercel runs `app/main.py` with `requirements.txt` (runtime only); `vercel.json` leaves tests, scripts and
  docs out of the function but keeps the committed UM graph.

## How it works
- `scripts/build_malaysia.py` (pyosmium): pass 1 finds path junctions; pass 2 writes walkable edges split at
  junctions (same IDs as the pilot graph: sorted OSM node pair), buildings with heights, covers, green areas,
  lamps, trees, crossings and named places into one SQLite file with R*Tree and FTS5 indexes. Places get an
  area label ("Bandar Puteri, Puchong") from the nearest OSM neighbourhood and town.
- `app/region.py`: a trip loads only the 0.02° tiles in a corridor around it (walks up to 15 km). Each tile's
  condition layer uses the same rules as the UM build (`app/osm_rules.py`) and is cached; a first route in a
  new area takes ~1–2 s, then milliseconds.
- Tree canopy (`app/canopy.py`): Meta/WRI 1 m around UM, ESA WorldCover 10 m elsewhere (read on demand,
  cached under `WALKLAH_MY_DATA/worldcover`), or reported as unavailable.
- `app/search.py`: FTS5 prefix search ranked by name match and distance to the map view; reverse lookup.
- `app/directions.py`: turn-by-turn steps and ahead alerts for walk mode.
- `app/weather.py`: Open-Meteo rain chance for rain cover (cached 30 min).

## Measured data coverage
- Malaysia (OSM): sidewalk status known 28.7% · lighting tagged 1.6% · covered ways tagged 0.3% · real building
  heights 12.2%. Lamps add lighting per area; everything else stays "unknown".
- UM audited area: sidewalk 29% · lighting 4% · covered 7% · canopy 13% · real building heights 8.5%.
  The audit CSV (`GET /audit/template`) turns "unknown" into evidence anywhere in Malaysia.

## Walkthrough
1. `GET /places?q=kinrara bk5` → SP22 Kinrara BK 5; `q=zus puteri&lat=3.045&lon=101.62` → ZUS Coffee,
   Bandar Puteri Puchong.
2. Route KOMTAR → Padang Kota Lama (George Town) at 13:00: three routes with reasons, steps and alerts.
3. Report flooding on the Practical route from three phones (`device`) → `community_confirmed`; Practical
   now avoids it ("Avoids 1 hazard confirmed by walkers"). Operator marks it cleared → routes return.
4. Insights with `bbox` of George Town: overview, heatmap, trends, CSV export; scenario with `cost_rm`.
5. LRT Universiti (3.114548, 101.661702) → Dewan Tunku Canselor at 13:00: Enjoyable ~57% shaded vs ~32%
   on the shortest route (Meta 1 m canopy + building shadows).
