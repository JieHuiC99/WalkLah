# WalkLah Backend Handoff
```
Backend is ready on branch feat/backend-routing.

Run it:
  cd backend
  python -m uvicorn app.main:app --reload
API: http://127.0.0.1:8000    Try endpoints: http://127.0.0.1:8000/docs
CORS is enabled for localhost:5173 and 127.0.0.1:5173.

Endpoints:
  GET   /destinations
  GET   /route?start_id=...&destination_id=...&mode=baseline|walklah
  GET   /reports
  POST  /reports
  PATCH /reports/{id}/verify   body: {"status": "verified_active"}
  GET   /insights/summary
  POST  /demo/reset            (clears all reports, for rehearsals)

Changes from the API contract:
- POST /reports: send only category, description, latitude, longitude.
  segment_id is optional; the server snaps the click to the nearest
  footpath and returns the segment_id.
- Errors are {"detail": "..."}; for 422 the detail is a list.
- Route geometry coordinates are [longitude, latitude].
- Allowed verify statuses: verified_active, verified_cleared,
  disputed, stale. Only verified_active changes routing.

Destinations: start_1 Kantin Fakulti Kejuruteraan, destination_1 ZUS
Coffee (UM), destination_2 Dewan Tunku Canselor, destination_3 UM Bus
Terminal, destination_4 Masjid Ar-Rahman, destination_5 FSKTM.
Map centre: about lat 3.118, lon 101.655.

Demo story (please make this work end to end):
  Route: start_1 -> destination_2
  Baseline is 558 m. Report an obstacle at lat 3.11916, lon 101.65565,
  verify it as verified_active, and the walklah route becomes about
  681 m and goes around it. Baseline stays the same.
  Then verify the report as verified_cleared and walklah returns to 558 m.
  ```