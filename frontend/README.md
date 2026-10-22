# WalkLah frontend

React + TypeScript + Vite + MapLibre GL JS. One codebase, two products (proposal §9):

| App | URL | For | Layout |
| --- | --- | --- | --- |
| **WalkLah Go** | `/` | Walkers anywhere in Malaysia | Always a phone UI: inside a phone frame on a laptop/projector, full-screen (and installable) on a phone |
| **WalkLah Insights** | `/?app=insights` | Township / campus operators | Desktop workspace; S.T.E.P. is the navigation |

Every route line and number comes from the backend API. Unknown conditions are shown as unknown.

## WalkLah Go (walkers)

- **Home:** start and destination, "to get somewhere" vs "for the walk", step-free, and an English / Bahasa
  Melayu switch.
- **Search:** stations, shops and branches across Malaysia (OpenStreetMap + Overture Maps), ranked around
  the map view, each with its area ("ZUS Coffee · Bandar Puteri Puchong") and distance. Quick chips for the
  nearest LRT/MRT, food, shopping and bus stops; recent places; your location; or a pin on the map (named
  after the nearest place or street).
- **Explore:** "Leave at" time, step-free and **rain cover** (auto from the forecast, on, off). Three routes:
  - **Shortest:** distance only (the transparent baseline).
  - **Practical:** avoids verified barriers, hazards confirmed by walkers, busy roads and unknown or missing sidewalks.
  - **Enjoyable:** shade by day (sun position, building shadows, tree canopy, covered walkways), lighting after
    dark, quiet and green paths.

  Each card explains itself ("Avoids 1 hazard confirmed by walkers", "57% shaded vs 32%"). The selected
  route is coloured shade/sun by day and lit/unlit/unknown at night; tap a path for its condition card.
- **Walk mode** (*Start walking*): follows GPS with a blue dot, shows the next turn and distance, a step
  list, and heads-ups before sunny, unlit or uncovered stretches, steps, crossings and reported hazards
  (optional voice). Leaving the route for 10 s plans a new one from where you are. One tap reports
  *Blocked / Flooded / Dark here* at your position; on arrival it asks whether the route was passable.
  *Preview* plays the walk along the route on a laptop without GPS.
- **Report:** drop a pin; if a road and its sidewalk are both close you choose which. **Take a photo** (or
  choose one) as evidence: it is resized on the phone and re-encoded, which removes its location data. A report
  of the same kind within 30 m becomes a confirmation instead of a duplicate. In walk mode, a one-tap report
  offers *Add photo* afterwards.
- **Community:** reports within 10 km (or all of Malaysia) with **Still there / Cleared** votes. When three
  phones confirm a temporary hazard, Practical and Enjoyable avoid it until an operator checks it.
- **Installable:** add to the home screen from Chrome/Edge/Safari; the app shell opens offline (routes and
  reports always come live).

## WalkLah Insights (operators)

Works on **the map area** (pan to your township) or all of Malaysia. *Export CSV* saves the area's reports;
*Print report* gives a one-page township summary (save as PDF). A heatmap shows open reports or trips that
met a barrier.

- **S · Survey:** Malaysia-wide OSM coverage next to the team-audited area, the audit CSV template and upload.
- **T · Track:** a verification queue with photos (walker-confirmed hazards are flagged), evidence notes and
  history, official closures placed on the map, weekly trends, **Sample reports** (load or remove labelled
  example reports with openly licensed photos; tagged *Sample* everywhere) and *Clear all reports*.
- **E · Explore:** opt-in route statistics (detours caused by barriers, shade difference), after-walk feedback.
- **P · Prioritise:** ranked issues (formula shown) and **planning scenarios**: fix a verified barrier or draw
  a new walkway and see before/after distances between the stations, bus stops and everyday destinations
  around it, with an optional cost estimate (RM per metre saved). The live map never changes.

Insights needs no key. A public deployment can require one by setting `WALKLAH_OPERATOR_KEY` on the backend;
the app then asks for it. The key is never put in a `VITE_*` variable or the URL.

## Run

Prerequisites: Node.js 20.19+ or 22.12+ (developed on Node 24). Start the backend first
(`backend/HANDOFF.md`; build the Malaysia database for nationwide routing):

```powershell
cd backend
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:WALKLAH_MY_DATA = "C:\walklah-data"
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Then:

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local
npm run dev        # http://localhost:5173
```

The dev server is pinned to port 5173 because the backend's CORS only allows that origin.

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | Backend address |
| `VITE_MAP_STYLE_URL` | OpenFreeMap Positron | MapLibre style (keyless, OSM-based) |

Scripts: `npm run build` (type-check + build), `npm run lint` (oxlint), `npm run preview` (production build,
with the service worker).

Shareable links keep the trip and language, e.g.
`/?lang=ms&tab=explore&from=3.114548,101.661702&fn=KJ19%20Universiti&to=3.121464,101.656556&tn=Dewan%20Tunku%20Canselor&t=13`.

## Walkthroughs

**A · Transit first/last mile, anywhere:** search "kinrara bk5" → SP22 Kinrara BK 5; destination "zus puteri"
→ ZUS Coffee, Bandar Puteri Puchong. Compare the three routes at 1 pm, then *Start walking* (or *Preview*).

**B · Rain and night:** with rain likely, *Rain: auto* turns on and the cards show how much of each route is
covered. Switch the time to 9 pm: the cards show lighting, and walk mode warns before unlit stretches.

**C · Report → confirm → reroute → prioritise:** report flooding on the Practical route, confirm it from two
more phones (Community › Still there): Practical now avoids it. In Insights › Track it is flagged as
confirmed by walkers; verify or clear it. Insights › Prioritise ranks it and a scenario shows what fixing it
would save.

**D · Bahasa Melayu:** tap *BM* on the home screen (or open a link with `?lang=ms`).

## Data credits

Map data © OpenStreetMap contributors (ODbL) · places: Overture Maps Foundation (CDLA-Permissive-2.0) · tiles
OpenFreeMap / OpenMapTiles · tree canopy: Meta & World Resources Institute, Global Canopy Height 1 m
(CC BY 4.0), imagery © Maxar; ESA WorldCover 10 m 2021 (CC BY 4.0) · weather: Open-Meteo.com (CC BY 4.0) ·
sun position: NOAA equations · fonts: Plus Jakarta Sans and Caveat (SIL OFL 1.1, `public/fonts/`).

## Structure

```
src/
  main.tsx            picks WalkLah Go or WalkLah Insights (?app=insights); registers the service worker
  api/walklahApi.ts   all HTTP calls (API v3), timeouts, optional operator key header, ApiError
  go/                 walker app: GoApp, screens/ (Home, Explore, Walk, Report, Community), LocationPicker,
                      sheets, walk.ts (route progress), i18n.ts + i18n.ms.ts (English / Bahasa Melayu)
  insights/           operator app: InsightsApp, stages/ (Survey, Track, Explore, Prioritise), Sparkline,
                      PrintReport, insights.css
  components/         shared: MapView (routes, reports, blue dot, heatmap), StepRail, StatusBadge, icons
  map/                MapLibre layers: palette, routes (per-segment colouring), heatmap, reports, popups
  config/             map bounds/style/colours, categories, statuses
public/               fonts, icons, manifest.webmanifest, sw.js
```
