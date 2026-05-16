def met_for_pace(pace_min_per_km: float) -> float:
    if pace_min_per_km >= 8.0:
        return 6.0
    elif pace_min_per_km >= 6.0:
        return 8.3
    elif pace_min_per_km >= 5.0:
        return 9.8
    else:
        return 11.0


def calculate_calories(distance_km: float, weight_kg: float, pace_min_per_km: float) -> float:
    met = met_for_pace(pace_min_per_km)
    duration_hours = (distance_km * pace_min_per_km) / 60.0
    return round(met * weight_kg * duration_hours, 1)


def calories_to_distance(calories: float, weight_kg: float, pace_min_per_km: float) -> float:
    met = met_for_pace(pace_min_per_km)
    duration_hours = calories / (met * weight_kg)
    return round(duration_hours * (60.0 / pace_min_per_km), 2)
