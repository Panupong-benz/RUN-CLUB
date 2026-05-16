import httpx
import os
import polyline as polyline_lib

OSRM_URL = os.getenv("OSRM_URL", "https://router.project-osrm.org")


def compute_route(start_lat: float, start_lon: float, waypoints: list) -> dict:
    points = [{"lat": start_lat, "lon": start_lon}] + waypoints + [{"lat": start_lat, "lon": start_lon}]
    coords = ";".join(f"{p['lon']},{p['lat']}" for p in points)
    url = f"{OSRM_URL}/route/v1/foot/{coords}"
    params = {"overview": "full", "geometries": "polyline", "steps": "false"}

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        raise ValueError("OSRM request timed out — ลองใหม่อีกครั้ง")
    except httpx.HTTPStatusError as e:
        raise ValueError(f"OSRM HTTP error: {e.response.status_code}")

    if data.get("code") != "Ok" or not data.get("routes"):
        raise ValueError(f"OSRM error: {data.get('code', 'unknown')} — ไม่พบเส้นทาง")

    route = data["routes"][0]
    decoded = polyline_lib.decode(route["geometry"])
    geometry = [[lon, lat] for lat, lon in decoded]

    return {
        "total_km": round(route["distance"] / 1000, 2),
        "geometry": geometry,
        "duration_seconds": int(route["duration"]),
    }
