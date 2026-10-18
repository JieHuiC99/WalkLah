
# WalkLah API Contract

Version: 2.0 (proposed in the `feat/backend-comfort` PR; v1 endpoints are unchanged unless noted)
Status: For review by both developers

## 1. Base URL and conventions

- Local backend: `http://127.0.0.1:8000` (frontend: `VITE_API_BASE_URL`).
- JSON bodies. GeoJSON coordinates are `[longitude, latitude]`.
- Distances in metres, durations in minutes (1.2 m/s walking pace).
- Timestamps are ISO 8601. A date-time without an offset means Malaysia time (UTC+8).
- Errors are `{"detail": string}`; validation errors (422) have `detail` as a list of `{loc, msg, type}`.
- Unexpected server errors return `500 {"detail": "Internal server error."}` **with** CORS headers.
- Operator endpoints need the header `X-Operator-Key` (env `WALKLAH_OPERATOR_KEY`, demo default
  `walklah-demo`); missing or wrong key returns `401`.

Routing rules (proposal §6):
- `shortest` is the transparent baseline: distance only, ignores reports and conditions.
- Only `verified_active` reports remove a path from `practical`/`enjoyable` routing.
- `pending` reports never reroute; they are returned as route `warnings`.
- Unknown attributes are reported as unknown and never treated as good.
- No straight-line or invented routes: if no route exists the API says so.

## 2. Health and places

### GET /health
`200 {"status": "ok"}`

### GET /destinations (v1, unchanged)
`{"destinations": [{id, name, latitude, longitude}]}`

### GET /places?q=
Named places from OpenStreetMap plus the demo destinations. An empty `q` returns the featured quick picks.
`{"places": [{id, name, category, kind, latitude, longitude}]}`
- `category`: `transit | campus | daily | leisure | health | other`
- `kind`: `rail_station | bus_stop | null`

### GET /pilot
`{anchor, radius_m, bounds, featured[], coverage{}, sources[], built_at}`
- `anchor`: LRT Universiti (KJ19). `radius_m`: 1700 (campus core is 1.2–1.7 km from the station; team to confirm).
- `coverage`: percentages of the network with known sidewalk, lighting, cover, canopy, real building heights, etc.

## 3. Routes

### GET /route?start_id&destination_id&mode=baseline|walklah (v1, unchanged)

### GET /routes
Query: `start_lat, start_lon, end_lat, end_lon` (inside the map bounds), `at` (optional ISO date-time),
`step_free` (bool), `share_stats` (bool, only when the walker opted in).

```
{
  "start": {"latitude", "longitude", "snapped": [lon, lat], "snap_distance_m", "in_pilot_area"},
  "end":   { ...same... },
  "at": "2026-10-18T13:00+08:00",
  "sun": {"altitude", "azimuth", "daylight"},
  "step_free": false,
  "routes": [
    {
      "mode": "shortest" | "practical" | "enjoyable",
      "available": true,
      "distance_m", "estimated_minutes",
      "geometry": {GeoJSON LineString},
      "segments": [{"id", "coordinates", "length_m", "shade": 0..1 | null, "lit": "yes|no|unknown", "sidewalk"}],
      "exposure": {"shaded_m", "sun_m", "shade_pct"} | null,      // null after dark
      "lighting": {"lit_m", "unlit_m", "unknown_m"},
      "sidewalk_unknown_m", "busy_road_m", "steps_count",
      "crossings": {"signalised", "marked", "unknown"},
      "affected_segment_ids": [...],   // verified barriers on the shortest path that this route avoids
      "warnings": [{"type": "unverified_report", "report_id", "category", "segment_id"}],
      "reasons": ["62% shaded vs 32% on the shortest route", ...],
      "long_detour": false              // > 1.5 × shortest
    },
    {"mode": "practical", "available": false, "reason": "No walkable alternative — ..."}
  ],
  "data_notes": {"estimated_building_height_pct", "lighting_known_pct", "sidewalk_known_pct", "canopy_source"}
}
```
Errors: `400` outside the map, bad `at`, a point more than 150 m from a mapped path, the same spot,
or no mapped connection.

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
 temporary_or_permanent, expires_at | null, has_photo, source: "community" | "operator",
 confirmations: {still_there, cleared, last_at}}
```
Statuses: `pending | verified_active | verified_cleared | disputed | stale`.
Temporary categories (`blocked_walkway`, `flooding`, `construction`, `lighting_out`) expire to `stale`
after 6 h (env `WALKLAH_TEMP_EXPIRY_HOURS`) unless verified again or confirmed "still there".

### GET /reports
`{"reports": [Report]}`

### POST /reports → 201 Report
`{category, description?, latitude, longitude, segment_id?, temporary_or_permanent?}`.
`description` ≤ 280 characters. Without `segment_id` the server snaps to the nearest path; points more than
60 m from a path are rejected (400). `temporary_or_permanent` is inferred from the category if omitted.

### POST /reports/{id}/confirm → Report
`{"still_there": bool, "device": string(8–64)}` — one vote per device. Never changes status or routing.

### GET /reports/{id}/history
`{"report_id", "events": [{event_type, verifier_role, time, evidence_reference}]}`

### PATCH /reports/{id}/verify  (operator) → Report
`{"status": "verified_active" | "verified_cleared" | "disputed" | "stale", "evidence"?: string}`

### POST /operator/closures  (operator) → 201 Report
Official closure or works: `{category, description?, latitude, longitude, segment_id?}`; created as
`verified_active` with `source: "operator"`.

## 5. Insights (P · Prioritise)  — operator unless noted

### GET /insights/summary (public, v1)
`{total_reports, pending_reports, active_obstacles, cleared_reports, affected_segments}`

### GET /insights/overview
`{survey{coverage, sources, built_at}, track{reports_by_status, ...}, explore{route_requests_30d,
requests_hitting_barriers, detour_m_caused_by_barriers, average_shade_gain_pct, feedback{yes, partly, no}},
prioritise{top_issues[], formula}}`

### GET /insights/issues
Ranked open issues: `{issues: [{report, path_name, trips_affected, average_detour_m, still_there_votes,
priority}], formula}`. Priority = trips affected × average detour (m) ÷ 100 + 2 × "still there" votes + 5 if verified.

### POST /scenarios/evaluate
Hypothetical intervention, computed on a copy of the graph (the live map never changes):
- `{"type": "remove_barrier", "segment_id"}` or
- `{"type": "add_link", "start": {latitude, longitude}, "end": {latitude, longitude}, "label"?}`

Returns `{hypothetical: true, label, description, link_length_m, pairs_checked, pairs_improved,
newly_connected, total_saved_m, rows[{from, to, before_m, after_m, saved_m, newly_connected}], assumptions[]}`
for every pair among the station, nearest pilot bus stops and featured destinations.

### GET /scenarios/candidates
`{"barriers": [{segment_id, report_id, category, path_name, latitude, longitude}]}`

### GET /reports/{id}/full
`{report, history}`

## 6. Survey (S) and validation

### GET /audit/template (public)
CSV header + example: `segment_id,lit,sidewalk,checked_at,auditor,note`

### POST /audit  (operator)
`{"rows": [{segment_id, lit?: "yes"|"no", sidewalk?: "yes"|"no"|"footpath", checked_at, auditor?, note?}]}`
Audit values override OSM-derived values immediately and after restarts.

### GET /audit  (operator)
`{"rows": [...]}`

### POST /feedback (public) → 201
"After your walk": `{"mode", "passable": "yes" | "partly" | "no", "note"?, "device"}`

### GET /insights/feedback  (operator)

## 7. Demo helpers

### POST /demo/reset  (operator)
Clears reports, verification events and confirmations. Route statistics, feedback and audits are kept.

## 8. Data and licences

- © OpenStreetMap contributors (ODbL) — network, buildings, covers, lighting tags, crossings, places.
- Meta and World Resources Institute, Global Canopy Height 1 m (CC BY 4.0), source imagery © 2016 Maxar.
- Sun position: NOAA solar calculator equations.
- Rebuild the condition layer with `python scripts/build_comfort.py --canopy data/canopy_um.tif`
  (canopy clip: `python scripts/fetch_canopy.py`).
