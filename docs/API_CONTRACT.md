
# WalkLah API Contract

Version: 1.0
Status: Agreed MVP specification

## 1. Base URL

Local backend:
http://127.0.0.1:8000

Frontend environment variable:
VITE_API_BASE_URL=http://127.0.0.1:8000

## 2. Shared conventions

- JSON is used for request and response bodies.
- Coordinates use [longitude, latitude] in GeoJSON.
- Distances are measured in metres.
- Estimated durations are measured in minutes.
- Timestamps use ISO 8601 format.
- Only verified_active reports can block routes.
- Pending reports must never affect route calculations.
- Route geometry must follow the pedestrian network.
- Do not return a fake straight-line route when routing fails.

## 3. GET /health

Purpose:
Check whether the backend is running.

Success response: 200

{
  "status": "ok"
}

## 4. GET /destinations

Purpose:
Return the locations available in the demo.

Success response: 200

{
  "destinations": [
    {
      "id": "start_1",
      "name": "Demo Start",
      "latitude": 3.115,
      "longitude": 101.662
    },
    {
      "id": "destination_1",
      "name": "Demo Destination",
      "latitude": 3.118,
      "longitude": 101.665
    }
  ]
}

Replace the example coordinates and labels with actual
locations inside the downloaded demo area.

## 5. GET /route

Query parameters:
- start_id: string
- destination_id: string
- mode: baseline or walklah

Example:
GET /route?start_id=start_1&destination_id=destination_1&mode=walklah

Success response: 200

{
  "route_type": "walklah",
  "start_id": "start_1",
  "destination_id": "destination_1",
  "distance_m": 620.0,
  "estimated_minutes": 8.0,
  "verification": "network_route",
  "affected_segment_ids": [],
  "geometry": {
    "type": "LineString",
    "coordinates": [
      [101.662, 3.115],
      [101.663, 3.116],
      [101.665, 3.118]
    ]
  }
}

Rules:
- route_type is baseline or walklah.
- mode=baseline ignores obstacle reports.
- mode=walklah avoids verified active blocked segments.
- Coordinates are [longitude, latitude].
- geometry must contain the actual pedestrian route.
- affected_segment_ids lists relevant segments affected by
  verified active obstacles.
- If no route exists, return an appropriate 404 response.
- Do not return invented distance or geometry.

## 6. GET /reports

Purpose:
Return reports visible on the map and dashboard.

Success response: 200

{
  "reports": [
    {
      "id": "report_1",
      "segment_id": "segment_123",
      "category": "blocked_path",
      "description": "Temporary obstruction",
      "status": "pending",
      "latitude": 3.116,
      "longitude": 101.663,
      "created_at": "2026-10-16T08:00:00Z"
    }
  ]
}

Allowed statuses:
- pending
- verified_active
- verified_cleared
- disputed
- stale

## 7. POST /reports

Purpose:
Submit a new obstacle report.

Request body:

{
  "segment_id": "segment_123",
  "category": "blocked_path",
  "description": "Temporary obstruction",
  "latitude": 3.116,
  "longitude": 101.663
}

Success response: 201

{
  "id": "report_1",
  "segment_id": "segment_123",
  "category": "blocked_path",
  "description": "Temporary obstruction",
  "status": "pending",
  "latitude": 3.116,
  "longitude": 101.663,
  "created_at": "2026-10-16T08:00:00Z"
}

Rules:
- Validate required fields.
- The server assigns the ID, timestamp, and pending status.
- Never let the client submit a report as verified_active.

## 8. PATCH /reports/{report_id}/verify

Purpose:
Update a report's status through the demo operator workflow.

Request body:

{
  "status": "verified_active"
}

Allowed requested statuses:
- verified_active
- verified_cleared
- disputed
- stale

Success response: 200

Return the updated report.

Rules:
- Return 404 if the report does not exist.
- Invalid status values must be rejected.
- For the MVP, this is a demo operator action.
- Before public deployment, protect this endpoint with
  authentication and authorization.

## 9. GET /insights/summary

Purpose:
Return dashboard metrics.

Success response: 200

{
  "total_reports": 10,
  "pending_reports": 3,
  "active_obstacles": 4,
  "cleared_reports": 2,
  "affected_segments": 4
}

Metrics must be calculated from the same report data used
by the map and routing service.

## 10. Error responses

Use a consistent JSON structure, for example:

{
  "detail": "No pedestrian route found."
}

Suggested HTTP statuses:
- 200: successful GET/PATCH
- 201: report created
- 400: invalid request or unsupported mode
- 404: unknown location/report or no route
- 422: request validation error
- 500: unexpected server error

## 11. Integration acceptance criteria

1. The frontend can fetch destinations and reports.
2. The frontend can request baseline and WalkLah routes.
3. A new report is initially pending.
4. Pending reports do not change routing.
5. Verifying a report can change routing if its segment
   is actually part of the route.
6. Clearing the report restores route availability when
   the original route is still the best valid route.
7. Dashboard metrics reflect the report records.