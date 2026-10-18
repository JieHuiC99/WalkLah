from typing import List

import osmnx as ox
from fastapi import APIRouter, Depends, HTTPException, Request

from .rate_limit import enforce
from .region import REGIONS
from .report_store import store
from .routing import parse_segment_id, segment_id
from .schemas import ConfirmRequest, OperatorClosure, ReportCreate, VerifyRequest
from .security import require_operator

# Reports further than this from any mapped path are rejected instead of being
# attached to some distant edge.
MAX_SNAP_DISTANCE_M = 60


def _valid(ids) -> List[str]:
    """Malformed IDs are skipped so one bad report can never break routing."""
    out = []
    for seg in ids:
        try:
            parse_segment_id(seg)
        except ValueError:
            continue
        out.append(seg)
    return sorted(out)


def active_blocked_segments() -> List[str]:
    """Segments of verified_active reports (operator-verified or official closures)."""
    return _valid(store.verified_segment_ids())


def community_blocked_segments() -> List[str]:
    """Temporary hazards confirmed by enough walkers, not yet decided by an operator."""
    return _valid(store.community_blocked_segment_ids() - store.verified_segment_ids())


def create_reports_router(graph_service) -> APIRouter:
    router = APIRouter()

    def resolve_segment(segment: str | None, latitude: float, longitude: float) -> str:
        if REGIONS.available:
            if segment:
                try:
                    u, v = parse_segment_id(segment)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid segment_id. Expected 'nodeA-nodeB'.")
                if REGIONS.db.edge_by_nodes(u, v) is None:
                    raise HTTPException(status_code=400, detail="segment_id is not in the walking network.")
                return segment_id(u, v)
            near = REGIONS.near_segments(latitude, longitude, radius_m=MAX_SNAP_DISTANCE_M, limit=1)
            if not near:
                raise HTTPException(status_code=400,
                                    detail=f"That spot is more than {MAX_SNAP_DISTANCE_M} m from any mapped path.")
            return near[0]["segment_id"]

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
    def create_report(body: ReportCreate, request: Request):
        """New report, or a 'still there' vote on an open report of the same kind within 30 m."""
        enforce("reports", request, body.device)
        duplicate = store.find_duplicate(body.category, body.latitude, body.longitude)
        if duplicate is not None:
            report = store.confirm(duplicate["id"], body.device, True) if body.device else duplicate
            return {**report, "merged": True}
        report = store.create(
            segment_id=resolve_segment(body.segment_id, body.latitude, body.longitude),
            category=body.category,
            description=body.description,
            latitude=body.latitude,
            longitude=body.longitude,
            temporary_or_permanent=body.temporary_or_permanent,
            device=body.device,
        )
        return {**report, "merged": False}

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
    def confirm_report(report_id: str, body: ConfirmRequest, request: Request):
        """Community 'still there' / 'cleared' vote. Enough 'still there' votes on a temporary
        hazard make Practical and Enjoyable routes avoid it until an operator decides."""
        enforce("votes", request, body.device)
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
