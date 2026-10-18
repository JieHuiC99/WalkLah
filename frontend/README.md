# WalkLah frontend

React + TypeScript + Vite + MapLibre GL JS. One codebase, two products (proposal §9):

| App | URL | For | Layout |
| --- | --- | --- | --- |
| **WalkLah Go** | `/` | Walkers | Always a phone UI: inside a phone frame on a laptop/projector, full-screen on a real phone |
| **WalkLah Insights** | `/?app=insights` | Township / campus operators (operator key) | Desktop workspace; S.T.E.P. is the navigation |

Every route line and number comes from the backend API. Unknown conditions are shown as unknown.

## WalkLah Go (walkers)

- **Home:** start and destination (search OpenStreetMap places, your location, or a pin on the map), "to get somewhere" vs "for the walk", and step-free.
- **Explore:** a "Leave at" time picker (Now, 8 am … 9 pm) with the sun position and Open-Meteo weather. Three routes:
  - **Shortest:** distance only (the transparent baseline).
  - **Practical:** avoids verified barriers, busy roads, and unknown or missing sidewalks.
  - **Enjoyable:** shade by day (sun position, building shadows, tree canopy, covered walkways), lighting after dark, quiet and green paths.

  Each card shows the reasons and any unverified reports on the way. The selected route is coloured shade/sun by day and lit/unlit/unknown at night; tap a coloured path for its condition card.
- **Report:** drop a pin. If two different paths are close (e.g. a road and its sidewalk) you choose which one. Pick a category (duration is inferred) and add an optional description.
- **Community:** reports with **Still there / Cleared** votes. Temporary issues expire unless reconfirmed.
- **How WalkLah works:** plain-language S.T.E.P., what the map knows, credits, and opt-in anonymous route stats.

## WalkLah Insights (operators)

- **S · Survey:** coverage of the condition layer, the audit CSV template and upload (the team's on-foot checks override OSM), and sources.
- **T · Track:** a verification queue with evidence notes and history, official closures placed on the map, and the demo reset.
- **E · Explore:** opt-in route statistics (detours caused by barriers, shade difference) and after-walk feedback.
- **P · Prioritise:** ranked issues (with the formula shown) and **hypothetical intervention scenarios**: fix a verified barrier or draw a new walkway, then see the before/after distances between the station, bus stops and key places. The live map never changes.

Demo operator key: `walklah-demo` (set `WALKLAH_OPERATOR_KEY` on the backend for anything public). The key is typed into the app; it is never put in a `VITE_*` variable or the URL.

## Run

Prerequisites: Node.js 20.19+ or 22.12+ (developed on Node 24). Start the backend first (`backend/HANDOFF.md`):

```powershell
cd backend
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
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
| `VITE_DEMO_MODE` | `true` | Shows "Use rehearsed demo spot" in the report form |

Scripts: `npm run build` (type-check + build), `npm run lint` (oxlint), `npm run preview`.

## Demo stories

**A · Necessity walker, transit first/last mile**
1. Open `/?tab=explore&from=3.114548,101.661702&fn=LRT%20Universiti%20(KJ19)&to=3.121464,101.656556&tn=Dewan%20Tunku%20Canselor&t=13`.
   Practical and Enjoyable are about 60% shaded vs about 32% on the shortest route, for about 20 m more.
2. Switch 1 pm → 5 pm: the shade shares change with the sun. Switch to 9 pm: the cards show lighting, and most of the route is "lighting unknown" until the team audit.

**B · Report → verify → reroute → prioritise**
1. Insights › Track › Reset demo data.
2. Go › Report › "Use rehearsed demo spot" › Blocked walkway › Submit. Explore Kantin Fakulti Kejuruteraan → Dewan Tunku Canselor: the route shows a warning but is not rerouted.
3. Insights › Track › Verify as active (add an evidence note). Go › Explore: Practical and Enjoyable avoid it (558 m → ~681–686 m), with a reason shown.
4. Go › Community › Still there. Insights › Prioritise: the issue ranks first. Run "Fix a verified barrier" to see the hypothetical savings (e.g. 183 m and 123 m on two place pairs).

**C · Any location:** in Go, choose "Choose on map" for both ends. Pins far from any path (> 150 m) get a clear message.

## Data credits

Map data © OpenStreetMap contributors (ODbL) · tiles OpenFreeMap / OpenMapTiles · tree canopy: Meta & World
Resources Institute, Global Canopy Height 1 m (CC BY 4.0), imagery © Maxar · weather: Open-Meteo.com (CC BY 4.0) ·
sun position: NOAA equations · fonts: Plus Jakarta Sans and Caveat (SIL OFL 1.1, `public/fonts/`).

## Structure

```
src/
  main.tsx            picks WalkLah Go or WalkLah Insights (?app=insights)
  api/walklahApi.ts   all HTTP calls (API v2), timeouts, operator key header, ApiError
  go/                 walker app: GoApp, DeviceFrame, screens/, LocationPicker, sheets, go.css
  insights/           operator app: InsightsApp, stages/ (Survey, Track, Explore, Prioritise), insights.css
  components/         shared: MapView, StepRail, StatusBadge, CategoryIcon, icons, BackendStatus
  map/                MapLibre layers: palette, routes (per-segment colouring), reports, popups
  config/             map bounds/style/colours, categories, statuses, demo point
```
