import httpx


def get_air_quality(lat: float, lon: float) -> dict:
    """
    Fetch PM2.5, PM10, and AQI from Open-Meteo Air Quality API.
    Free, no API key required.
    """
    url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "pm2_5,pm10,us_aqi,dust",
        "timezone": "Asia/Bangkok",
    }

    with httpx.Client(timeout=10.0) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    current = data.get("current", {})
    pm25 = current.get("pm2_5", 0) or 0
    pm10 = current.get("pm10", 0) or 0
    aqi = current.get("us_aqi", 0) or 0
    dust = current.get("dust", 0) or 0

    # PM2.5 level classification (WHO / Thailand standard)
    if pm25 <= 12:
        level = "good"
        color_label = "🟢 ดีมาก"
        advice = "✅ คุณภาพอากาศดี วิ่งได้เลยไม่ต้องใส่หน้ากาก"
        warning = "ok"
    elif pm25 <= 35.4:
        level = "moderate"
        color_label = "🟡 ปานกลาง"
        advice = "😷 ผู้ที่แพ้ฝุ่นหรือมีโรคระบบทางเดินหายใจควรใส่หน้ากาก N95"
        warning = "info"
    elif pm25 <= 55.4:
        level = "unhealthy_sensitive"
        color_label = "🟠 มีผลต่อกลุ่มเสี่ยง"
        advice = "⚠️ ควรใส่หน้ากาก N95 และลดความหนักของการวิ่ง"
        warning = "warning"
    elif pm25 <= 150.4:
        level = "unhealthy"
        color_label = "🔴 ไม่ดีต่อสุขภาพ"
        advice = "🚨 ควรหลีกเลี่ยงการวิ่งกลางแจ้ง หรือวิ่งในที่ที่มีอากาศถ่ายเท"
        warning = "danger"
    else:
        level = "very_unhealthy"
        color_label = "🟣 อันตราย"
        advice = "🚫 ห้ามวิ่งกลางแจ้ง! ฝุ่นอยู่ในระดับอันตราย ควรอยู่ในอาคาร"
        warning = "danger"

    return {
        "pm25": round(pm25, 1),
        "pm10": round(pm10, 1),
        "aqi": int(aqi),
        "dust": round(dust, 1),
        "level": level,
        "color_label": color_label,
        "advice": advice,
        "warning": warning,
    }
