from pydantic import BaseModel


class Waypoint(BaseModel):
    lat: float
    lon: float


class RouteResponse(BaseModel):
    waypoints: list[Waypoint]
    geometry: list[list[float]]
    total_km: float
    estimated_calories: float
    estimated_minutes: int
    agent_summary: str
