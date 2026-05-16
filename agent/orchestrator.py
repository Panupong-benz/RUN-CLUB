import json
import os
from typing import Optional

import anthropic

from agent.tools.calorie_calc import calculate_calories
from agent.tools.waypoint_gen import generate_ellipse_waypoints, scale_waypoints
from agent.tools.route_compute import compute_route
from models.response import RouteResponse, Waypoint


TOOL_DEFINITIONS = [
    {
        "name": "generate_waypoints",
        "description": "Generate circular waypoints around a starting point for a running loop.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "Center latitude"},
                "lon": {"type": "number", "description": "Center longitude"},
                "target_km": {"type": "number", "description": "Desired total loop distance in km"},
                "num_points": {"type": "integer", "description": "Number of waypoints 3-6, default 4"},
                "bearing_offset_deg": {"type": "number", "description": "Rotate ellipse 0-360, default 0"},
            },
            "required": ["lat", "lon", "target_km"],
        },
    },
    {
        "name": "compute_route",
        "description": "Call OSRM to get the actual walking route through waypoints, looping back to start. Returns total_km, geometry_json, duration_seconds.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_lat": {"type": "number"},
                "start_lon": {"type": "number"},
                "waypoints_json": {"type": "string", "description": 'Waypoints as JSON string: \'[{"lat":13.7,"lon":100.5},...]\'' },
            },
            "required": ["start_lat", "start_lon", "waypoints_json"],
        },
    },
    {
        "name": "adjust_waypoints",
        "description": "Scale waypoints outward (>1) or inward (<1) to adjust route distance.",
        "input_schema": {
            "type": "object",
            "properties": {
                "waypoints_json": {"type": "string", "description": "Current waypoints as JSON string"},
                "center_lat": {"type": "number"},
                "center_lon": {"type": "number"},
                "scale_factor": {"type": "number", "description": "1.2 to expand 20%, 0.9 to shrink"},
            },
            "required": ["waypoints_json", "center_lat", "center_lon", "scale_factor"],
        },
    },
    {
        "name": "calculate_calories",
        "description": "Calculate calories burned for a running distance.",
        "input_schema": {
            "type": "object",
            "properties": {
                "distance_km": {"type": "number"},
                "weight_kg": {"type": "number"},
                "pace_min_per_km": {"type": "number"},
            },
            "required": ["distance_km", "weight_kg", "pace_min_per_km"],
        },
    },
    {
        "name": "finalize_route",
        "description": "Call when satisfied with the route. Provide all final data and a Thai summary.",
        "input_schema": {
            "type": "object",
            "properties": {
                "waypoints_json": {"type": "string", "description": 'Final waypoints JSON string: \'[{"lat":...,"lon":...}]\''},
                "geometry_json": {"type": "string", "description": "Geometry string from compute_route result"},
                "total_km": {"type": "number"},
                "estimated_calories": {"type": "number"},
                "estimated_minutes": {"type": "integer"},
                "agent_summary": {"type": "string", "description": "2-3 sentences in Thai about the route character"},
            },
            "required": ["waypoints_json", "geometry_json", "total_km", "estimated_calories", "estimated_minutes", "agent_summary"],
        },
    },
]

SYSTEM_PROMPT = """You are a Bangkok running route planner AI. Create safe circular running routes.

Rules:
- Route MUST return to starting point (circular loop)
- Target distance tolerance: ±15%
- Use 4 waypoints for routes under 10 km, 5-6 for longer
- Try bearing_offset_deg=45 or 90 if first attempt is off target
- You MUST always call finalize_route at the end — never stop without it
- Write agent_summary in Thai (2-3 sentences about the route character)
- waypoints_json and geometry_json must be valid JSON strings

Workflow: generate_waypoints → compute_route → check distance → adjust if needed (max 1 adjustment) → calculate_calories → finalize_route

IMPORTANT: After at most 2 compute_route attempts, call finalize_route with whatever result you have."""

NIGHT_MODE_ADDON = """

🌙 NIGHT RUNNING MODE: Prioritize well-lit, safe roads.
- Prefer highway=secondary, highway=tertiary (main roads with street lights)
- Prefer routes near BTS/MRT stations and 24-hour convenience stores
- Avoid dark unnamed sois and unlit footpaths
- Mention night safety tips in agent_summary (Thai)"""


def _execute_tool(name: str, inp: dict) -> str:
    if name == "generate_waypoints":
        wps = generate_ellipse_waypoints(
            lat=inp["lat"], lon=inp["lon"], target_km=inp["target_km"],
            num_points=int(inp.get("num_points", 4)),
            bearing_offset_deg=float(inp.get("bearing_offset_deg", 0.0)),
            smart=True,
        )
        return json.dumps({"waypoints_json": json.dumps(wps)})

    elif name == "compute_route":
        waypoints = json.loads(inp["waypoints_json"])
        result = compute_route(inp["start_lat"], inp["start_lon"], waypoints)
        result["geometry_json"] = json.dumps(result.pop("geometry"))
        return json.dumps(result)

    elif name == "adjust_waypoints":
        waypoints = json.loads(inp["waypoints_json"])
        scaled = scale_waypoints(waypoints, inp["center_lat"], inp["center_lon"], inp["scale_factor"])
        return json.dumps({"waypoints_json": json.dumps(scaled)})

    elif name == "calculate_calories":
        cal = calculate_calories(inp["distance_km"], inp["weight_kg"], inp["pace_min_per_km"])
        return json.dumps({"calories": cal})

    elif name == "finalize_route":
        return json.dumps({"status": "finalized"})

    return json.dumps({"error": f"Unknown tool: {name}"})


def plan_route(lat, lon, target_km, weight_kg, pace_min_per_km,
               night_mode: bool = False, tolerance_pct: float = 15.0) -> RouteResponse:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    system = SYSTEM_PROMPT + (NIGHT_MODE_ADDON if night_mode else "")

    messages = [{
        "role": "user",
        "content": (
            f"Plan a circular running route starting at lat={lat}, lon={lon}. "
            f"Target distance: {target_km} km. "
            f"Runner weight: {weight_kg} kg, pace: {pace_min_per_km} min/km. "
            + ("This is a NIGHT RUN — prioritize lit roads and safety. " if night_mode else "")
            + "Generate waypoints, compute the route, adjust if needed, calculate calories, then finalize."
        ),
    }]

    final_input: Optional[dict] = None
    last_route_result: Optional[dict] = None  # track last compute_route output for fallback
    last_waypoints_json: Optional[str] = None
    total_tokens_used: int = 0

    for _ in range(12):
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            system=system,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )
        total_tokens_used += response.usage.input_tokens + response.usage.output_tokens

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            break

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == "finalize_route":
                final_input = block.input
            # track last successful compute_route for fallback
            if block.name == "compute_route":
                last_waypoints_json = block.input.get("waypoints_json")
            result_str = _execute_tool(block.name, block.input)
            if block.name == "compute_route":
                try:
                    last_route_result = json.loads(result_str)
                except Exception:
                    pass
            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result_str})

        messages.append({"role": "user", "content": tool_results})

        if final_input is not None:
            break

    # Fallback: agent looped without calling finalize_route — build result from last route
    if final_input is None:
        if last_route_result and last_route_result.get("geometry_json") and last_waypoints_json:
            cal = calculate_calories(last_route_result["total_km"], weight_kg, pace_min_per_km)
            final_input = {
                "waypoints_json": last_waypoints_json,
                "geometry_json": last_route_result["geometry_json"],
                "total_km": last_route_result["total_km"],
                "estimated_calories": cal,
                "estimated_minutes": int(last_route_result["total_km"] * pace_min_per_km),
                "agent_summary": "เส้นทางวงกลมรอบจุดเริ่มต้น วิ่งได้ปลอดภัย",
            }
        else:
            raise RuntimeError("ไม่สามารถวางแผนเส้นทางได้ — กรุณาลองใหม่อีกครั้ง")

    # ── Python-level distance correction (reliable, up to 5 iterations) ──
    _tol = tolerance_pct / 100.0  # e.g. 15% → 0.15
    _wps = json.loads(final_input["waypoints_json"])
    _actual_km = float(final_input["total_km"])
    for _i in range(5):
        _ratio = target_km / _actual_km if _actual_km > 0 else 1.0
        if (1 - _tol) <= _ratio <= (1 + _tol):
            break
        _scale = _ratio ** 0.7  # damped to avoid overshoot
        _wps = scale_waypoints(_wps, lat, lon, _scale)
        try:
            _r = compute_route(lat, lon, _wps)
            _actual_km = _r["total_km"]
            _cal = calculate_calories(_actual_km, weight_kg, pace_min_per_km)
            final_input.update({
                "waypoints_json": json.dumps(_wps),
                "geometry_json": json.dumps(_r["geometry"]),
                "total_km": _actual_km,
                "estimated_calories": _cal,
                "estimated_minutes": int(_actual_km * pace_min_per_km),
            })
        except Exception:
            break

    waypoints = json.loads(final_input["waypoints_json"])
    geometry_raw = final_input["geometry_json"]
    # geometry_json may be a JSON string or already a list (agent occasionally returns a list)
    geometry = json.loads(geometry_raw) if isinstance(geometry_raw, str) else geometry_raw

    if not geometry or not isinstance(geometry, list):
        raise RuntimeError("Agent returned invalid geometry. Please try again.")

    return RouteResponse(
        waypoints=[Waypoint(lat=w["lat"], lon=w["lon"]) for w in waypoints],
        geometry=geometry,
        total_km=float(final_input["total_km"]),
        estimated_calories=float(final_input["estimated_calories"]),
        estimated_minutes=int(final_input["estimated_minutes"]),
        agent_summary=final_input.get("agent_summary", ""),
        tokens_used=total_tokens_used,
    )
