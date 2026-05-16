import httpx
from datetime import datetime


WEATHER_CODES = {
    0: ("☀️", "ท้องฟ้าแจ่มใส"),
    1: ("🌤️", "มีเมฆบางส่วน"),
    2: ("⛅", "มีเมฆมาก"),
    3: ("☁️", "ครึ้มฟ้า"),
    45: ("🌫️", "หมอกลง"),
    48: ("🌫️", "หมอกน้ำแข็ง"),
    51: ("🌦️", "ฝนละออง (เบา)"),
    53: ("🌦️", "ฝนละออง (ปานกลาง)"),
    55: ("🌧️", "ฝนละออง (หนัก)"),
    61: ("🌧️", "ฝนตก (เบา)"),
    63: ("🌧️", "ฝนตก (ปานกลาง)"),
    65: ("🌧️", "ฝนตก (หนัก)"),
    80: ("🌦️", "ฝนตกเป็นช่วงๆ (เบา)"),
    81: ("🌧️", "ฝนตกเป็นช่วงๆ (ปานกลาง)"),
    82: ("⛈️", "ฝนตกหนัก"),
    95: ("⛈️", "พายุฝนฟ้าคะนอง"),
    96: ("⛈️", "พายุพร้อมลูกเห็บ"),
    99: ("⛈️", "พายุรุนแรงพร้อมลูกเห็บ"),
}


def get_weather(lat: float, lon: float) -> dict:
    """Fetch current weather + next 3-hour rain forecast from Open-Meteo (free, no API key)."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,weathercode,windspeed_10m,apparent_temperature",
        "hourly": "precipitation_probability,precipitation",
        "timezone": "Asia/Bangkok",
        "forecast_days": 1,
    }

    with httpx.Client(timeout=10.0) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    current = data["current"]
    hourly = data["hourly"]

    # Find current hour index
    now_str = datetime.now().strftime("%Y-%m-%dT%H:00")
    try:
        hour_idx = hourly["time"].index(now_str)
    except ValueError:
        hour_idx = 0

    # Next 3 hours rain probability
    next_3h_rain = hourly["precipitation_probability"][hour_idx: hour_idx + 3]
    max_rain_prob = max(next_3h_rain) if next_3h_rain else 0

    code = current.get("weathercode", 0)
    icon, description = WEATHER_CODES.get(code, ("🌡️", "ไม่ทราบสภาพอากาศ"))

    # Warning level
    if max_rain_prob >= 70 or code in (82, 95, 96, 99):
        warning = "danger"
        warning_msg = "⚠️ ระวัง! มีโอกาสฝนตกหนักหรือพายุ — ควรเลื่อนการวิ่งออกไป"
    elif max_rain_prob >= 40 or code in (61, 63, 80, 81):
        warning = "warning"
        warning_msg = "🌧️ มีโอกาสฝนตก — เตรียมเสื้อกันฝนหรือเลือกเส้นทางที่มีหลังคา"
    elif current["temperature_2m"] >= 35:
        warning = "warning"
        warning_msg = "🌡️ อากาศร้อนมาก — ดื่มน้ำเยอะๆ และหลีกเลี่ยงการวิ่งตอนกลางวัน"
    else:
        warning = "ok"
        warning_msg = "✅ สภาพอากาศเหมาะกับการวิ่ง!"

    return {
        "temperature": current["temperature_2m"],
        "feels_like": current["apparent_temperature"],
        "humidity": current["relative_humidity_2m"],
        "wind_speed": current["windspeed_10m"],
        "description": description,
        "icon": icon,
        "rain_prob_next3h": max_rain_prob,
        "warning": warning,
        "warning_msg": warning_msg,
    }
