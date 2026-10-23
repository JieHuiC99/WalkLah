# WalkLah API Contract

Version: 3.0 (`feat/backend-comfort`; v1 endpoints are unchanged unless noted)
Status: For review by both developers

## 1. Base URL and conventions

- Local backend: `http://127.0.0.1:8000` (frontend: `VITE_API_BASE_URL`).
- JSON bodies. GeoJSON coordinates are `[longitude, latitude]`.
- Distances in metres, durations in minutes (1.2 m/s walking pace).
- Timestamps are ISO 8601. A date-time without an offset means Malaysia time (UTC+8).
- Errors are `{"detail": string}`; validation errors (422) have `detail` as a list of `{loc, msg, type}`.
- Unexpected server errors return `500 {"detail": "Internal server error."}` **with** CORS headers.
- Operator endpoints are open by default. If the server sets `WALKLAH_OPERATOR_KEY`, they need the header
  `X-Operator-Key` and return `401` without it (recommended for any public deployment).
- Community writes are rate limited per phone and per IP (default 10 reports and 60 votes per hour;
  `WALKLAH_RATE_LIMITS="reports=10,votes=60"` or `off`). Over the limit: `429`.
- Operator views accept `bbox=west,south,east,north` to limit them to one area.

Coverage: all of Malaysia (plus Singapore and Brunei, which are in the same OpenStreetMap extract) when the
national database is built (`scripts/build_malaysia.py`); otherwise the UM pilot graph only.

Routing rules (proposal §6):
- `shortest` is the transparent baseline: distance only, ignores reports and conditions.
- `practical`/`enjoyable` avoid `verified_active` reports and **community-confirmed** temporary hazards
  (3+ different phones say "still there", more than say "cleared", and no operator decision yet).
- Other `pending` reports never reroute; they are returned as route `warnings`.
- Unknown attributes are reported as unknown and never treated as good.
- No straight-line or invented routes: if no route exists the API says so.

## 2. Health, places and map coverage

### GET /health
`200 {"status": "ok"}`

### GET /destinations (v1, unchanged)
`{"destinations": [{id, name, latitude, longitude}]}`

### GET /places?q=&lat=&lon=&limit=
Stations, shops, branches and other named places from OpenStreetMap and Overture Maps.
`lat`/`lon` (map centre or the walker's position) rank nearby results first. An empty `q` returns the rail
stations within 4 km of `lat`/`lon`.
`{"places": [{id, name, brand, category, kind, area, latitude, longitude, source, distance_m?}]}`
- `category`: `transit | food | shopping | campus | health | leisure | civic | other`
- `kind`: `rail_station | station_entrance | bus_stop | null`
- `area`: neighbourhood and town, e.g. `"Bandar Puteri Puchong, Puchong"` — tells branches apart.
- Matching is by word prefix on name, brand, area and aliases (e.g. `mcd`, `bk5` for "BK 5").

### GET /places/nearby?lat&lon&kind=&category=&radius_m=2000&limit=8
Closest places of one kind or category, nearest first.

### GET /reverse?lat&lon
Name for a dropped pin: `{name, label, area, place | null}` — `label` is "Near ZUS Coffee" (a place within
~60 m), else the street name, else "Dropped pin".

### GET /pilot
Map coverage and the team-audited area:
`{coverage_area: "malaysia" | "pilot", bounds, audited_area{anchor, radius_m, label}, anchor, radius_m,
featured[], coverage{}, audited_coverage{}, sources[], built_at}`
- `coverage`: Malaysia-wide OSM coverage when the national database exists (`network_km`,
  `sidewalk_known_pct`, `lighting_tagged_pct`, `covered_tagged_pct`, `building_heights_real_pct`, `places`, …).
- `audited_coverage`: the UM area, where the team audits lighting and sidewalks on foot.

## 3. Routes

### GET /route?start_id&destination_id&mode=baseline|walklah (v1, unchanged)

### GET /routes
Query: `start_lat, start_lon, end_lat, end_lon`, `at` (optional ISO date-time), `step_free` (bool),
`rain` (`auto` | `on` | `off`, default `auto`), `share_stats` (bool, only when the walker opted in).
Walks up to 15 km in a straight line.

```
{
  "start": {"latitude", "longitude", "snapped": [lon, lat], "snap_distance_m", "in_pilot_area"},
  "end":   { ...same... },
  "at": "2026-10-18T13:00+08:00",
  "sun": {"altitude", "azimuth", "daylight"},
  "step_free": false,
  "rain": {"probability", "forced", "source"} | null,          // set when rain cover is applied
  "weather": {"rain_mode", "rain_cover", "rain_probability", "precipitation_mm", "source", "note"},
  "routes": [
    {
      "mode": "shortest" | "practical" | "enjoyable",
      "available": true,
      "distance_m", "estimated_minutes",
      "geometry": {GeoJSON LineString},
      "segments": [{"id", "coordinates", "length_m", "shade": 0..1 | null, "lit": "yes|no|unknown", "sidewalk"}],
      "exposure": {"shaded_m", "sun_m", "shade_pct"} | null,      // null after dark
      "lighting": {"lit_m", "unlit_m", "unknown_m"},
      "covered_m", "covered_pct",
      "sidewalk_unknown_m", "busy_road_m", "steps_count",
      "crossings": {"signalised", "marked", "unknown"},
      "affected_segment_ids": [...],   // blocked segments on the shortest path (statistics)
      "avoided_segment_ids": [...],    // blocked segments this route avoids
      "warnings": [{"type": "unverified_report", "report_id", "category", "segment_id"}],
      "reasons": ["Avoids 1 hazard confirmed by walkers", "62% shaded vs 32% on the shortest route", ...],
      "long_detour": false,             // > 1.5 × shortest
      "steps": [{"type": "depart|turn|continue|steps|arrive", "modifier": "left|right|slight left|…" | null,
                 "instruction", "name" | null, "way" | null, "direction" | null,
                 "distance_m", "at_m", "location": [lon, lat]}],
      "alerts": [{"type": "sun|unlit|light_unknown|uncovered|steps|crossing|hazard",
                  "at_m", "length_m" | null, "text", "location": [lon, lat], "category"?}]
    },
    {"mode": "practical", "available": false, "reason": "No walkable alternative — ..."}
  ],
  "data_notes": {"estimated_building_height_pct", "lighting_known_pct", "sidewalk_known_pct", "canopy_source"}
}
```
- Rain cover: with `rain=auto` it applies when Open-Meteo gives ≥ 60% for the start hour; `on` always;
  `off` never. Uncovered metres then cost more for Practical and Enjoyable.
- `at_m` is metres from the start, for walk mode. `instruction` is English; `name`/`way`/`direction`/`modifier`
  let the app phrase it in other languages.
- Errors: `400` outside the covered area, a trip over 15 km, bad `at`, a point more than 150 m from a
  mapped path, the same spot, or no mapped connection.

### GET /segments/near?lat&lon
Up to 3 candidate path segments within 25 m (for confirming which path a report belongs to).
`{"segments": [{segment_id, distance_m, name, highway, sidewalk}]}`

### GET /segments/{segment_id}?at=
Condition card: `{id, name, highway, length_m, sidewalk, steps, traffic_stress, lighting{status, source},
crossings[], covered_pct, tree_canopy_pct, green_pct, shade_now_pct | null, sun{}, reports[]}`

## 4. Reports (T · Track)

Report object:
```
{id, segment_id, category, description | null, status, latitude, longitude, created_at,
 temporary_or_permanent, expires_at | null, has_photo, photo_url | null,
 source: "community" | "operator" | "sample", confirmations: {still_there, cleared, last_at},
 community_confirmed: bool}
```
Statuses: `pending | verified_active | verified_cleared | disputed | stale`.
Temporary categories (`blocked_walkway`, `flooding`, `construction`, `lighting_out`) expire to `stale`
after 6 h (env `WALKLAH_TEMP_EXPIRY_HOURS`) unless verified again or confirmed "still there".

### GET /reports
`{"reports": [Report]}`

### POST /reports → 201 Report + `merged`
`{category, description?, latitude, longitude, segment_id?, temporary_or_permanent?, device?, photo?}`.
`photo` is a data URL (`data:image/jpeg|png|webp;base64,…`, at most 1.5 MB decoded; checked by its bytes):
`400` if it is not an image, `413` if too large. The app resizes and re-encodes photos, which removes EXIF
location data. A merged report gets the photo if it had none.
`description` ≤ 280 characters. Without `segment_id` the server snaps to the nearest path; points more than
60 m from a path are rejected (400). The reporting phone (`device`) counts as the first "still there".
An open report of the same category within 30 m is not duplicated: the request becomes a "still there"
vote on it and the response has `"merged": true`.

### POST /reports/{id}/confirm → Report
`{"still_there": bool, "device": string(8–64)}` — one vote per device. Enough "still there" votes on a
temporary hazard set `community_confirmed`, which reroutes Practical/Enjoyable until an operator decides.

### GET /reports/{id}/photo
The report's photo (`image/jpeg|png|webp`), `404` if none. Public, like the report itself.

### POST /reports/{id}/photo → Report
`{"photo": data URL, "device"?}` — add a photo to a report that has none (walk-mode quick reports);
`409` if it already has one. Rate limited like votes. Recorded in the history as `photo_added`.

### GET /reports/{id}/history
`{"report_id", "events": [{event_type, verifier_role, time, evidence_reference}]}`

### PATCH /reports/{id}/verify  (operator) → Report
`{"status": "verified_active" | "verified_cleared" | "disputed" | "stale", "evidence"?: string}`

### POST /operator/closures  (operator) → 201 Report
Official closure or works: `{category, description?, latitude, longitude, segment_id?}`; created as
`verified_active` with `source: "operator"`.

## 5. Insights (P · Prioritise) — operator unless noted; all accept `bbox`

### GET /insights/summary (public, v1)
`{total_reports, pending_reports, active_obstacles, cleared_reports, affected_segments}`

### GET /insights/overview
`{area, survey{coverage, audited_coverage, sources, built_at}, track{reports_by_status, total_reports,
operator_closures, community_confirmed, still_there_votes, cleared_votes}, explore{route_requests_30d,
requests_hitting_barriers, detour_m_caused_by_barriers, average_shade_gain_pct, feedback{yes, partly, no},
consent_note}, prioritise{top_issues[], formula}}`

### GET /insights/issues
Ranked open issues: `{issues: [{report, path_name, trips_affected, average_detour_m, still_there_votes,
priority}], formula}`. Priority = trips affected × average detour (m) ÷ 100 + 2 × "still there" votes + 5 if verified.

### GET /insights/heat?kind=reports|trips
`{kind, points: [{latitude, longitude, weight}]}` — open reports (votes and verification add weight), or
~1 km cells of opted-in trips that met a barrier or a reported hazard.

### GET /insights/trends
`{weeks: ["YYYY-MM-DD" (Mondays)…8], series: {reports[], resolved[], route_comparisons[]}}`

### GET /insights/export.csv
Every report in the area with votes, trips affected and priority. UTF-8 with BOM (opens in Excel).

### POST /scenarios/evaluate
Planning scenario computed on a copy of the walking network around the change (the live map never changes):
- `{"type": "remove_barrier", "segment_id", "label"?, "cost_rm"?}` or
- `{"type": "add_link", "start": {latitude, longitude}, "end": {latitude, longitude}, "label"?, "cost_rm"?}`

Returns `{hypothetical: true, label, description, link_length_m, pairs_checked, pairs_improved,
newly_connected, total_saved_m, cost{cost_rm, rm_per_metre_saved, metres_saved_per_rm_1000, source} | null,
rows[{from, to, before_m, after_m, saved_m, newly_connected}], assumptions[]}` for every pair among the rail
stations, bus stops and everyday destinations near the change (UM pilot places without the national data).

### GET /scenarios/candidates
`{"barriers": [{segment_id, report_id, category, path_name, latitude, longitude}]}`

### GET /reports/{id}/full
`{report, history}`

## 6. Survey (S) and validation

### GET /audit/template (public)
CSV header + example: `segment_id,lit,sidewalk,checked_at,auditor,note`

### POST /audit  (operator)
`{"rows": [{segment_id, lit?: "yes"|"no", sidewalk?: "yes"|"no"|"footpath", checked_at, auditor?, note?}]}`
Any segment in Malaysia. Audit values override OSM-derived values immediately and after restarts.

### GET /audit  (operator)
`{"rows": [...]}`

### POST /feedback (public) → 201
"After your walk": `{"mode", "passable": "yes" | "partly" | "no", "note"?, "device", "latitude"?, "longitude"?}`
— the position is stored only as a ~1 km cell.

### GET /insights/feedback  (operator)

## 7. Administration

### POST /admin/reset  (operator)
Clears reports, verification events and confirmations. Route statistics, feedback and audits are kept.
(`/demo/reset` remains as a hidden alias for older scripts.) Uploaded photos of cleared reports are deleted.

### POST /admin/sample-data  (operator)
Loads (or reloads) about ten labelled sample reports with `source: "sample"`: pending, confirmed by walkers,
verified, cleared, stale and an official closure, each with a history and most with an openly licensed photo.
They behave like real reports (maps, rerouting) but add no trip statistics. Reports outside the loaded map
are skipped: `{loaded, skipped[], report_ids[]}`.

### DELETE /admin/sample-data  (operator)
Removes only sample reports: `{removed}`.

### GET /sample-data/credits
Authors and licences of the sample photos (`backend/sample_data/CREDITS.md`).

## 8. Data and licences

- © OpenStreetMap contributors (ODbL) — network, buildings, covers, lighting tags, crossings, places
  (Geofabrik extract `malaysia-singapore-brunei`).
- Overture Maps Foundation places (CDLA-Permissive-2.0).
- Tree canopy: Meta and World Resources Institute, Global Canopy Height 1 m (CC BY 4.0), source imagery
  © 2016 Maxar (UM area); ESA WorldCover 10 m 2021 (CC BY 4.0) elsewhere.
- Weather: Open-Meteo.com (CC BY 4.0). Sun position: NOAA solar calculator equations.
- Sample report photos: Wikimedia Commons, CC0 / CC BY 2.0 / CC BY-SA 2.0 (`backend/sample_data/CREDITS.md`).
- Build: `python scripts/build_malaysia.py --pbf …osm.pbf --overture` (see `backend/HANDOFF.md`).
