import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.routing import segment_id

client = TestClient(app)

# a. GET /route start_1 -> destination_1 baseline
response = client.get("/route?start_id=start_1&destination_id=destination_1&mode=baseline")
assert response.status_code == 200
baseline_distance = response.json()['distance_m']
print(f"baseline distance: {baseline_distance} m")

# b. POST /reports with segment_id "2825690661-11257976450"
report_data = {
    "segment_id": segment_id(2825690661, 11257976450),
    "category": "blocked_path",
    "description": "Demo obstacle",
    "latitude": 3.11916,
    "longitude": 101.65565,
}
response = client.post("/reports", json=report_data)
assert response.status_code == 201, f"{response.status_code}: {response.text}"
report_id = response.json()['id']
print(f"report status: {response.json()['status']}")

# c. GET /route walklah
response = client.get("/route?start_id=start_1&destination_id=destination_1&mode=walklah")
assert response.status_code == 200
walklah_distance = response.json()['distance_m']
print(f"walklah distance: {walklah_distance} m")

# d. PATCH verify -> verified_active
response = client.patch(
    f"/reports/{report_id}/verify",
    json={"status": "verified_active"}
)
assert response.status_code == 200
print(f"report status: {response.json()['status']}")

# e. GET /route walklah and baseline
response = client.get("/route?start_id=start_1&destination_id=destination_1&mode=walklah")
assert response.status_code == 200
walklah_distance = response.json()['distance_m']
affected_segments = response.json()['affected_segment_ids']
print(f"walklah distance: {walklah_distance} m")
print(f"affected segments: {affected_segments}")

response = client.get("/route?start_id=start_1&destination_id=destination_1&mode=baseline")
assert response.status_code == 200
baseline_distance = response.json()['distance_m']
print(f"baseline distance: {baseline_distance} m")

# f. PATCH -> verified_cleared
response = client.patch(
    f"/reports/{report_id}/verify",
    json={"status": "verified_cleared"}
)
assert response.status_code == 200
print(f"report status: {response.json()['status']}")

# GET /route walklah again
response = client.get("/route?start_id=start_1&destination_id=destination_1&mode=walklah")
assert response.status_code == 200
walklah_distance = response.json()['distance_m']
print(f"walklah distance: {walklah_distance} m")

# g. GET /insights/summary
response = client.get("/insights/summary")
assert response.status_code == 200
print(f"insights summary: {response.json()}")