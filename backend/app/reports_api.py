from typing import List
import osmnx as ox
from fastapi import APIRouter, Depends, HTTPException

from .report_store import store
from .routing import parse_segment_id, segment_id
from .schemas import ConfirmRequest, OperatorClosure, ReportCreate, VerifyRequest
from .security import require_operator

# Reports further than this from any mapped path are rejected instead of being
# attached to some distant edge.
MAX_SNAP_DISTANCE_M = 60


def active_blocked_segments() -> List[str]:
    """Segments of verified_active reports. Malformed IDs are skipped so
    one bad report can never break routing."""
    valid = []
    for seg in store.verified_segment_ids():
        try:
            parse_segment_id(seg)
        except ValueError:
            continue
        valid.append(seg)
    return sorted(valid)


def create_reports_router(graph_service) -> APIRouter:
    router = APIRouter()

    def resolve_segment(segment: str | None, latitude: float, longitude: float) -> str:
        if graph_service.graph is None:
            graph_service.load_graph()
        graph = graph_service.graph

        if segment:
            try:
                u, v = parse_segment_id(segment)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid segment_id. Expected 'nodeA-nodeB'.",
                )
            if not (graph.has_edge(u, v) or graph.has_edge(v, u)):
                raise HTTPException(
                    status_code=400,
                    detail="segment_id is not in the pedestrian graph.",
                )
            return segment_id(u, v)

        try:
            (u, v, _key), dist = ox.distance.nearest_edges(graph, longitude, latitude, return_dist=True)
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Could not snap the location to a footpath.",
            )
        # Unprojected graphs return the distance in degrees; ~111 km per degree near the equator.
        if float(dist) * 111_000 > MAX_SNAP_DISTANCE_M:
            raise HTTPException(
                status_code=400,
                detail=f"That spot is more than {MAX_SNAP_DISTANCE_M} m from any mapped path.",
            )
        return segment_id(u, v)

    @router.post("/reports", status_code=201)
    def create_report(body: ReportCreate):
        return store.create(
            segment_id=resolve_segment(body.segment_id, body.latitude, body.longitude),
            category=body.category,
            description=body.description,
            latitude=body.latitude,
            longitude=body.longitude,
            temporary_or_permanent=body.temporary_or_permanent,
        )

    @router.get("/reports")
    def list_reports():
        return {"reports": store.list()}

    @router.patch("/reports/{report_id}/verify", dependencies=[Depends(require_operator)])
    def verify_report(report_id: str, body: VerifyRequest):
        report = store.update_status(report_id, body.status, role="operator", evidence=body.evidence)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found.")
        return report

    @router.post("/reports/{report_id}/confirm")
    def confirm_report(report_id: str, body: ConfirmRequest):
        """Community 'still there' / 'cleared' vote. Never changes routing by itself."""
        report = store.confirm(report_id, body.device, body.still_there)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found.")
        return report

    @router.get("/reports/{report_id}/history")
    def report_history(report_id: str):
        events = store.history(report_id)
        if events is None:
            raise HTTPException(status_code=404, detail="Report not found.")
        return {"report_id": report_id, "events": events}

    @router.post("/operator/closures", status_code=201, dependencies=[Depends(require_operator)])
    def create_closure(body: OperatorClosure):
        """Official update from the township operator: active immediately, source=operator."""
        return store.create(
            segment_id=resolve_segment(body.segment_id, body.latitude, body.longitude),
            category=body.category,
            description=body.description,
            latitude=body.latitude,
            longitude=body.longitude,
            source="operator",
            status="verified_active",
        )

    return router
