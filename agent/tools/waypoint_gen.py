import math
import httpx

EARTH_RADIUS_KM = 6371.0
OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def _offset_point(lat: float, lon: float, bearing_deg: float, distance_km: float):
    lat_r = math.radians(lat)
    lon_r = math.radians(lon)
    bearing_r = math.radians(bearing_deg)
    d_r = distance_km / EARTH_RADIUS_KM

    new_lat_r = math.asin(
        math.sin(lat_r) * math.cos(d_r)
        + math.cos(lat_r) * math.sin(d_r) * math.cos(bearing_r)
    )
    new_lon_r = lon_r + math.atan2(
        math.sin(bearing_r) * math.sin(d_r) * math.cos(lat_r),
        math.cos(d_r) - math.sin(lat_r) * math.sin(new_lat_r),
    )
    return math.degrees(new_lat_r), math.degrees(new_lon_r)


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p)
         * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _fetch_green_nodes(lat: float, lon: float, radius_m: int) -> list[dict]:
    """Query OSM for park/footway nodes to snap waypoints toward."""
    query = f"""
    [out:json][timeout:10];
    (
      node["leisure"~"park|garden|pitch|track"](around:{radius_m},{lat},{lon});
      node["landuse"~"recreation_ground|grass|meadow"](around:{radius_m},{lat},{lon});
      node["highway"~"footway|path|pedestrian|cycleway"](around:{radius_m},{lat},{lon});
      way["leisure"~"park|garden"](around:{radius_m},{lat},{lon});
    );
    out center 40;
    """
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(OVERPASS_URL, data={"data": query})
            resp.raise_for_status()
            data = resp.json()
        nodes = []
        for el in data.get("elements", []):
            if el["type"] == "node":
                nodes.append({"lat": el["lat"], "lon": el["lon"]})
            elif el["type"] == "way" and "center" in el:
                nodes.append({"lat": el["center"]["lat"], "lon": el["center"]["lon"]})
        return nodes
    except Exception:
        return []


def _snap_to_nearest_green(wp_lat: float, wp_lon: float,
                            green_nodes: list[dict], max_snap_km: float) -> tuple[float, float]:
    """Snap a waypoint toward the nearest green node if within max_snap_km."""
    if not green_nodes:
        return wp_lat, wp_lon

    best = min(green_nodes, key=lambda n: _haversine_km(wp_lat, wp_lon, n["lat"], n["lon"]))
    dist = _haversine_km(wp_lat, wp_lon, best["lat"], best["lon"])

    if dist > max_snap_km:
        return wp_lat, wp_lon

    # Blend 60% toward the green node
    blend = 0.6
    new_lat = wp_lat + (best["lat"] - wp_lat) * blend
    new_lon = wp_lon + (best["lon"] - wp_lon) * blend
    return new_lat, new_lon


def generate_ellipse_waypoints(lat, lon, target_km, num_points=4,
                               bearing_offset_deg=0.0, smart=True):
    radius_km = target_km / (2 * math.pi)
    waypoints = []
    for i in range(num_points):
        bearing = bearing_offset_deg + (360.0 / num_points) * i
        wlat, wlon = _offset_point(lat, lon, bearing, radius_km)
        waypoints.append({"lat": wlat, "lon": wlon})

    if smart:
        # Fetch green/pedestrian nodes within 1.5× radius
        search_radius_m = int(radius_km * 1500)
        search_radius_m = max(300, min(search_radius_m, 2000))
        green_nodes = _fetch_green_nodes(lat, lon, search_radius_m)

        if green_nodes:
            max_snap = radius_km * 0.5  # snap at most 50% of radius
            waypoints = [
                {"lat": snl, "lon": snlo}
                for wp in waypoints
                for snl, snlo in [_snap_to_nearest_green(wp["lat"], wp["lon"],
                                                          green_nodes, max_snap)]
            ]

    return waypoints


def scale_waypoints(waypoints, center_lat, center_lon, scale_factor):
    return [
        {
            "lat": center_lat + (wp["lat"] - center_lat) * scale_factor,
            "lon": center_lon + (wp["lon"] - center_lon) * scale_factor,
        }
        for wp in waypoints
    ]
