from typing import List
import osmnx as ox
from fastapi import APIRouter, HTTPException

from .report_store import store
from .routing import parse_segment_id, segment_id
from .schemas import ReportCreate, VerifyRequest



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

    def resolve_segment(body: ReportCreate) -> str:
        if graph_service.graph is None:
            graph_service.load_graph()
        graph = graph_service.graph

        if body.segment_id:
            try:
                u, v = parse_segment_id(body.segment_id)
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
            u, v, _key = ox.distance.nearest_edges(
                graph, body.longitude, body.latitude
            )
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Could not snap the location to a footpath.",
            )
        return segment_id(u, v)

    @router.post("/reports", status_code=201)
    def create_report(body: ReportCreate):
        return store.create(
            segment_id=resolve_segment(body),
            category=body.category,
            description=body.description,
            latitude=body.latitude,
            longitude=body.longitude,
        )

    @router.get("/reports")
    def list_reports():
        return {"reports": store.list()}

    @router.patch("/reports/{report_id}/verify")
    def verify_report(report_id: str, body: VerifyRequest):
        report = store.update_status(report_id, body.status)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found.")
        return report

    return router