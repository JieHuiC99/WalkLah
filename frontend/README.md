# WalkLah frontend

React + TypeScript + Vite + MapLibre GL JS client for the WalkLah prototype ("Waze for Walking"),
built around the S.T.E.P. framework:

| Stage | Screen | What it shows |
| --- | --- | --- |
| **S** · Survey | Map data sheet (layers button) | Where the walking network comes from and what has not been surveyed yet |
| **T** · Track | Report, Community | Submit an obstacle (always starts as *pending*); see every report and its status |
| **E** · Explore | Explore | Usual (shortest) path vs WalkLah route, which avoids *verified active* obstacles |
| **P** · Prioritise | Operator | Summary cards, verification actions, and which place-to-place connections are affected |

Every route line and number comes from the backend API. Nothing is mocked.

## Prerequisites

- Node.js **20.19+ or 22.12+** (developed on Node 24)
- The WalkLah backend running on `http://127.0.0.1:8000` (see below)

## Run the backend (needed for everything)

From the repository root, in PowerShell:

```powershell
cd backend
py -m venv .venv                     # Python 3.10+; tested with 3.14
.venv\Scripts\python.exe -m pip install -r requirements.txt scikit-learn
Copy-Item tests\backend\data\walklah.graphml data\walklah.graphml
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

- **scikit-learn** is needed by OSMnx to find the nearest path node. Without it every `/route`
  call returns 404 "No pedestrian route found."
- **Copying the graph** avoids downloading a fresh 2 km OpenStreetMap graph on the first request.
  The copy is gitignored.
- **No `--reload`:** reports are kept in memory, so any restart or reload clears them.

Check `http://127.0.0.1:8000/health` returns `{"status":"ok"}`.

## Run the frontend

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local
npm run dev        # http://localhost:5173
```

The dev server is pinned to port **5173** (`strictPort`) because the backend's CORS only allows
`http://localhost:5173` and `http://127.0.0.1:5173`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | Backend address |
| `VITE_MAP_STYLE_URL` | OpenFreeMap Positron | MapLibre style (keyless, OpenStreetMap-based) |
| `VITE_DEMO_MODE` | `true` | Shows the "Use rehearsed demo spot" shortcut in the report form |

Never put secrets in `VITE_*` variables: they are bundled into the browser code.

Other scripts: `npm run build` (type-check + production build), `npm run lint` (oxlint),
`npm run preview` (serve the build on 5173).

## Rehearsed demo

Open `http://localhost:5173/?tab=explore&from=start_1&to=destination_2`, then:

1. **Operator → Reset demo data.** Explore shows 558 m for both routes.
2. **Report → Use rehearsed demo spot → Blocked walkway → Submit report.** The report is
   *Pending* and WalkLah stays at 558 m.
3. **Operator → Verify as active obstacle.** Explore shows WalkLah at about 681 m, going around
   the red obstacle, while the usual path stays at 558 m.
4. **Operator → Mark cleared.** WalkLah returns to 558 m.

The Operator screen's **Check 15 pairs** runs the same comparison for every pair of demo places.

## Resilience

- **Backend unreachable:** a banner appears with a **Retry** button. The app also retries when
  the window regains focus.
- **Base map unavailable:** if the base map style can't load (for example, venue wifi is down),
  the map falls back to a plain background. Routes and reports still draw.
- **Failed submit or verify:** errors show inline, and the form keeps what the user entered.

## Structure

```
src/
  api/walklahApi.ts      all HTTP calls, timeouts (30 s for /route), ApiError
  app/navigation.ts      tabs + URL query sync (?tab=&from=&to=)
  components/            MapView, StepRail, TripCard, StatusBadge, BottomNav, ...
  config/                map bounds/style, categories, statuses, demo point
  hooks/                 useRoutes (baseline + WalkLah in parallel), useConnectionCheck
  map/                   MapLibre layers: palette, routes, reports, popups
  pages/                 Home, Navigate (Explore), Report, Community, Dashboard (Operator)
```

Map data © OpenStreetMap contributors (ODbL). Map tiles by OpenFreeMap / OpenMapTiles.
