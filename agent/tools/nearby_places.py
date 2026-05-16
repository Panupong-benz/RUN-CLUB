import httpx
import math

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

PLACE_TYPES = {
    "restaurant": ("🍛", "ร้านอาหาร"),
    "fast_food": ("🍜", "ฟาสต์ฟู้ด"),
    "food_court": ("🍱", "ฟู้ดคอร์ท"),
    "cafe": ("☕", "คาเฟ่"),
    "bar": ("🧃", "บาร์/ร้านเครื่องดื่ม"),
    "convenience": ("🏪", "ร้านสะดวกซื้อ"),
    "supermarket": ("🛒", "ซุปเปอร์มาร์เก็ต"),
    "drinking_water": ("💧", "น้ำดื่มฟรี"),
    "juice_bar": ("🥤", "ร้านน้ำผลไม้"),
}


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    R = 6371000
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def get_nearby_places(lat: float, lon: float, radius_m: int = 500) -> list[dict]:
    """Query OSM Overpass for nearby food & drink places."""
    query = f"""
    [out:json][timeout:15];
    (
      node["amenity"~"restaurant|fast_food|food_court|cafe|bar|drinking_water"](around:{radius_m},{lat},{lon});
      node["shop"~"convenience|supermarket|juice_bar"](around:{radius_m},{lat},{lon});
    );
    out body 20;
    """

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(OVERPASS_URL, data={"data": query})
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []

    places = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        amenity = tags.get("amenity", "")
        shop = tags.get("shop", "")
        kind = amenity or shop

        icon, label = PLACE_TYPES.get(kind, ("📍", kind))
        name = tags.get("name") or tags.get("name:th") or tags.get("name:en") or label
        dist = int(_haversine_m(lat, lon, el["lat"], el["lon"]))

        places.append({
            "name": name,
            "kind": kind,
            "label": label,
            "icon": icon,
            "lat": el["lat"],
            "lon": el["lon"],
            "distance_m": dist,
        })

    # Sort by distance, deduplicate by name
    seen = set()
    unique = []
    for p in sorted(places, key=lambda x: x["distance_m"]):
        key = p["name"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(p)

    return unique[:15]
