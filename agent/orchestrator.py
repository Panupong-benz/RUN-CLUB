import json
import os
from typing import Optional

import google.generativeai as genai

from agent.tools.calorie_calc import calculate_calories, calories_to_distance
from agent.tools.waypoint_gen import generate_ellipse_waypoints, scale_waypoints
from agent.tools.route_compute import compute_route
from models.response import RouteResponse, Waypoint


TOOL_DEFINITIONS = {
    "function_declarations": [
        {
            "name": "generate_waypoints",
            "description": "Generate circular waypoints around a starting point for a running loop.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "lat": {"type": "NUMBER", "description": "Center latitude"},
                    "lon": {"type": "NUMBER", "description": "Center longitude"},
                    "target_km": {"type": "NUMBER", "description": "Desired total loop distance in km"},
                    "num_points": {"type": "INTEGER", "description": "Number of waypoints 3-6, default 4"},
                    "bearing_offset_deg": {"type": "NUMBER", "description": "Rotate the ellipse 0-360, default 0"},
                },
                "required": ["lat", "lon", "target_km"],
            },
        },
        {
            "name": "compute_route",
            "description": "Call OSRM to get the actual walking route through waypoints, looping back to start.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "start_lat": {"type": "NUMBER"},
                    "start_lon": {"type": "NUMBER"},
                    "waypoints": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "lat": {"type": "NUMBER"},
                                "lon": {"type": "NUMBER"},
                            },
                        },
                    },
                },
                "required": ["start_lat", "start_lon", "waypoints"],
            },
        },
        {
            "name": "adjust_waypoints",
            "description": "Scale waypoints outward (>1) or inward (<1) to adjust route distance.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "waypoints": {"type": "ARRAY", "items": {"type": "OBJECT"}},
                    "center_lat": {"type": "NUMBER"},
                    "center_lon": {"type": "NUMBER"},
                    "scale_factor": {"type": "NUMBER"},
                },
                "required": ["waypoints", "center_lat", "center_lon", "scale_factor"],
            },
        },
        {
            "name": "calculate_calories",
            "description": "Calculate calories burned for a running distance.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "distance_km": {"type": "NUMBER"},
                    "weight_kg": {"type": "NUMBER"},
                    "pace_min_per_km": {"type": "NUMBER"},
                },
                "required": ["distance_km", "weight_kg", "pace_min_per_km"],
            },
        },
        {
            "name": "finalize_route",
            "description": "Call when satisfied. Provide final waypoints, geometry (as JSON string), stats, and Thai summary.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "waypoints": {"type": "ARRAY", "items": {"type": "OBJECT"}},
                    "geometry_json": {"type": "STRING", "description": "Route geometry as JSON string: '[[lon,lat],[lon,lat],...]'"},
                    "total_km": {"type": "NUMBER"},
                    "estimated_calories": {"type": "NUMBER"},
                    "estimated_minutes": {"type": "INTEGER"},
                    "agent_summary": {"type": "STRING"},
                },
                "required": ["waypoints", "geometry_json", "total_km", "estimated_calories", "estimated_minutes", "agent_summary"],
            },
        },
    ]
}

SYSTEM_PROMPT = """You are a Bangkok running route planner AI. Create safe circular running routes.

Rules:
- Route MUST return to starting point (circular loop)
- Target distance tolerance: ±10%
- Use 4 waypoints for routes under 10 km, 5-6 for longer
- Try bearing_offset_deg=45 or 90 if first attempt is off target
- Max 6 tool calls — be efficient
- Write agent_summary in Thai (2-3 sentences about the route character)
- In finalize_route, geometry_json must be a JSON string of the geometry from compute_route, e.g. '[[100.5,13.7],[100.6,13.8],...]'

Workflow: generate_waypoints → compute_route → check distance → adjust if needed → calculate_calories → finalize_route"""


def _execute_tool(tool_name: str, tool_input: dict) -> str:
    if tool_name == "generate_waypoints":
        wps = generate_ellipse_waypoints(
            lat=tool_input["lat"],
            lon=tool_input["lon"],
            target_km=tool_input["target_km"],
            num_points=int(tool_input.get("num_points", 4)),
            bearing_offset_deg=float(tool_input.get("bearing_offset_deg", 0.0)),
        )
        return json.dumps({"waypoints": wps})

    elif tool_name == "compute_route":
        result = compute_route(
            start_lat=tool_input["start_lat"],
            start_lon=tool_input["start_lon"],
            waypoints=list(tool_input["waypoints"]),
        )
        return json.dumps(result)

    elif tool_name == "adjust_waypoints":
        scaled = scale_waypoints(
            waypoints=list(tool_input["waypoints"]),
            center_lat=tool_input["center_lat"],
            center_lon=tool_input["center_lon"],
            scale_factor=tool_input["scale_factor"],
        )
        return json.dumps({"waypoints": scaled})

    elif tool_name == "calculate_calories":
        cal = calculate_calories(
            distance_km=tool_input["distance_km"],
            weight_kg=tool_input["weight_kg"],
            pace_min_per_km=tool_input["pace_min_per_km"],
        )
        return json.dumps({"calories": cal})

    elif tool_name == "finalize_route":
        return json.dumps({"status": "finalized", "message": "Route finalized successfully"})

    return json.dumps({"error": f"Unknown tool: {tool_name}"})


def plan_route(lat, lon, target_km, weight_kg, pace_min_per_km) -> RouteResponse:
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash-preview-05-20",
        system_instruction=SYSTEM_PROMPT,
        tools=[TOOL_DEFINITIONS],
    )
    chat = model.start_chat()

    user_message = (
        f"Plan a circular running route starting at lat={lat}, lon={lon}. "
        f"Target distance: {target_km} km. "
        f"Runner weight: {weight_kg} kg, pace: {pace_min_per_km} min/km. "
        f"Generate waypoints, compute the route, adjust if needed, calculate calories, then finalize."
    )

    response = chat.send_message(user_message)
    final_tool_input: Optional[dict] = None

    for _ in range(10):
        function_calls = [p.function_call for p in response.parts if p.function_call]
        if not function_calls:
            break

        result_parts = []
        for fc in function_calls:
            tool_input = dict(fc.args)
            if fc.name == "finalize_route":
                final_tool_input = tool_input

            result_str = _execute_tool(fc.name, tool_input)
            result_parts.append(
                genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=fc.name,
                        response={"result": result_str},
                    )
                )
            )

        if final_tool_input is not None:
            break

        response = chat.send_message(result_parts)

    if final_tool_input is None:
        raise RuntimeError("Agent did not finalize a route. Please try again.")

    geometry = json.loads(final_tool_input["geometry_json"])

    return RouteResponse(
        waypoints=[Waypoint(lat=w["lat"], lon=w["lon"]) for w in final_tool_input["waypoints"]],
        geometry=geometry,
        total_km=final_tool_input["total_km"],
        estimated_calories=final_tool_input["estimated_calories"],
        estimated_minutes=int(final_tool_input["estimated_minutes"]),
        agent_summary=final_tool_input["agent_summary"],
    )
