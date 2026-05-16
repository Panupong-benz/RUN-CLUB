import math

EARTH_RADIUS_KM = 6371.0


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


def generate_ellipse_waypoints(lat, lon, target_km, num_points=4, bearing_offset_deg=0.0):
    radius_km = target_km / (2 * math.pi)
    waypoints = []
    for i in range(num_points):
        bearing = bearing_offset_deg + (360.0 / num_points) * i
        wlat, wlon = _offset_point(lat, lon, bearing, radius_km)
        waypoints.append({"lat": wlat, "lon": wlon})
    return waypoints


def scale_waypoints(waypoints, center_lat, center_lon, scale_factor):
    return [
        {
            "lat": center_lat + (wp["lat"] - center_lat) * scale_factor,
            "lon": center_lon + (wp["lon"] - center_lon) * scale_factor,
        }
        for wp in waypoints
    ]
