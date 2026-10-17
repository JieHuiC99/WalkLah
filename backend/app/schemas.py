from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class HealthResponse(BaseModel):
    """Response schema for /health endpoint."""
    status: str


class Destination(BaseModel):
    """Schema for location destinations."""
    id: str
    name: str
    latitude: float
    longitude: float


class DestinationsResponse(BaseModel):
    """Response schema for /destinations endpoint."""
    destinations: List[Destination]


class ReportBase(BaseModel):
    """Base schema for report creation."""
    segment_id: str
    category: str
    description: Optional[str] = None
    latitude: float
    longitude: float


class ReportCreate(ReportBase):
    """Schema for creating a new report."""
    pass


class Report(ReportBase):
    """Schema for a complete report with server-assigned fields."""
    id: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class ReportsResponse(BaseModel):
    """Response schema for listing reports."""
    reports: List[Report]


class RouteRequest(BaseModel):
    """Schema for route calculation request."""
    start_id: str
    destination_id: str
    mode: str  # "baseline" or "walklah"


class RouteResponse(BaseModel):
    """Schema for route response."""
    route_type: str
    start_id: str
    destination_id: str
    distance_m: float
    estimated_minutes: float
    verification: str
    affected_segment_ids: List[str]
    geometry: dict  # GeoJSON LineString


class InsightsSummary(BaseModel):
    """Schema for dashboard insights summary."""
    total_reports: int
    pending_reports: int
    active_obstacles: int
    cleared_reports: int
    affected_segments: int
