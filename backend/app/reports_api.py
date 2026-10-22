from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse

from . import photos, sample_data
from .rate_limit import enforce
from .region import REGIONS
from .report_store import store
from .routing import parse_segment_id, segment_id
from .schemas import ConfirmRequest, OperatorClosure, PhotoBody, ReportCreate, VerifyRequest
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
                if REGIONS.edge_info(segment_id(u, v)) is None:
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
            u, v, dist_m = graph_service.nearest_edge(latitude, longitude)
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Could not snap the location to a footpath.",
            )
        if dist_m > MAX_SNAP_DISTANCE_M:
            raise HTTPException(
                status_code=400,
                detail=f"That spot is more than {MAX_SNAP_DISTANCE_M} m from any mapped path.",
            )
        return segment_id(u, v)

    def store_photo(data_url: str) -> str:
        try:
            return photos.save_data_url(data_url)
        except photos.PhotoError as e:
            raise HTTPException(status_code=e.status, detail=str(e))

    @router.post("/reports", status_code=201)
    def create_report(body: ReportCreate, request: Request):
        """New report, or a 'still there' vote on an open report of the same kind within 30 m.
        An optional photo is stored with it (or added to the existing report if it has none)."""
        enforce("reports", request, body.device)
        duplicate = store.find_duplicate(body.category, body.latitude, body.longitude)
        if duplicate is not None:
            report = store.confirm(duplicate["id"], body.device, True) if body.device else duplicate
            if body.photo and not report["has_photo"]:
                name = store_photo(body.photo)
                report = store.set_photo(report["id"], name) or report
            return {**report, "merged": True}
        segment = resolve_segment(body.segment_id, body.latitude, body.longitude)
        photo_name = store_photo(body.photo) if body.photo else None
        report = store.create(
            segment_id=segment,
            category=body.category,
            description=body.description,
            latitude=body.latitude,
            longitude=body.longitude,
            temporary_or_permanent=body.temporary_or_permanent,
            photo_path=photo_name,
            device=body.device,
        )
        return {**report, "merged": False}

    @router.get("/reports/{report_id}/photo")
    def report_photo(report_id: str):
        found = photos.resolve(store.photo_path(report_id))
        if found is None:
            raise HTTPException(status_code=404, detail="No photo for this report.")
        path, media_type = found
        return FileResponse(path, media_type=media_type, headers={"Cache-Control": "public, max-age=86400"})

    @router.post("/reports/{report_id}/photo")
    def add_report_photo(report_id: str, body: PhotoBody, request: Request):
        """Add a photo to a report that has none yet (walk-mode quick reports)."""
        enforce("votes", request, body.device)
        report = store.get(report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found.")
        if report["has_photo"]:
            raise HTTPException(status_code=409, detail="This report already has a photo.")
        name = store_photo(body.photo)
        updated = store.set_photo(report_id, name)
        if updated is None:
            photos.delete(name)
            raise HTTPException(status_code=409, detail="This report already has a photo.")
        return updated

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

    # ---- labelled sample reports (Insights > Track > Sample reports) ----

    def snap_or_none(latitude: float, longitude: float):
        try:
            return resolve_segment(None, latitude, longitude)
        except HTTPException:
            return None  # outside the loaded map (e.g. no Malaysia database): skipped

    @router.post("/admin/sample-data", dependencies=[Depends(require_operator)])
    def load_sample_data():
        """Load (or reload) the labelled sample reports. They are tagged source='sample'."""
        return sample_data.load(snap_or_none)

    @router.delete("/admin/sample-data", dependencies=[Depends(require_operator)])
    def remove_sample_data():
        """Remove only the sample reports; real reports are untouched."""
        return sample_data.remove()

    @router.get("/sample-data/credits", response_class=PlainTextResponse)
    def sample_credits():
        """Authors and licences of the sample report photos."""
        return sample_data.credits()

    return router
