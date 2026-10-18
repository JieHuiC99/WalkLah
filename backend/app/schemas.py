from pydantic import BaseModel, Field
from typing import List, Optional, Literal
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


class ReportCreate(BaseModel):
    """Schema for creating a new report. segment_id is optional: if it is
    missing, the server snaps latitude/longitude to the nearest footpath."""
    segment_id: Optional[str] = None
    category: str = Field(min_length=1, max_length=40)
    description: Optional[str] = Field(default=None, max_length=280)
    latitude: float
    longitude: float
    temporary_or_permanent: Optional[Literal["temporary", "permanent"]] = None


class VerifyRequest(BaseModel):
    """Schema for the operator verify action."""
    status: Literal["verified_active", "verified_cleared", "disputed", "stale"]
    evidence: Optional[str] = Field(default=None, max_length=280)


class ConfirmRequest(BaseModel):
    """A walker's 'still there' / 'cleared' vote. device is a random ID kept on the phone."""
    still_there: bool
    device: str = Field(min_length=8, max_length=64)


class OperatorClosure(BaseModel):
    """Closure or works entered by the township operator (verified on creation)."""
    category: str
    description: Optional[str] = Field(default=None, max_length=280)
    latitude: float
    longitude: float
    segment_id: Optional[str] = None


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
