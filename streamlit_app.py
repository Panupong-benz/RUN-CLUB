import streamlit as st
import folium
from folium.plugins import AntPath, PolyLineTextPath
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation
import qrcode
from io import BytesIO
import json
import os
from datetime import date, datetime
from dotenv import load_dotenv

load_dotenv()

if "ANTHROPIC_API_KEY" in st.secrets:
    os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
if "OSRM_URL" in st.secrets:
    os.environ["OSRM_URL"] = st.secrets["OSRM_URL"]

from agent.orchestrator import plan_route
from agent.tools.calorie_calc import calories_to_distance
from agent.tools.weather import get_weather
from agent.tools.air_quality import get_air_quality
from agent.tools.nearby_places import get_nearby_places
from agent.tools.nutrition import get_nutrition_advice
from agent.tools.training_plan import generate_training_plan, DAY_COLORS
from db.stats import (init_db, save_profile, get_profile, save_run, get_runs, get_stats,
                      get_streak, get_weekly_leaderboard, get_alltime_leaderboard,
                      save_route, get_saved_routes, delete_saved_route,
                      save_training_plan, get_latest_training_plan,
                      save_meetup, get_upcoming_meetups, clear_runs, delete_account)

init_db()

st.set_page_config(page_title="GEO RUN CLUB", page_icon="🏃", layout="wide")

st.markdown("""
<style>
/* ── Mobile responsive ───────────────────────────────────────── */
@media (max-width: 768px) {

    /* ลด padding ของ container หลัก */
    .block-container {
        padding: 0.75rem 0.75rem 3rem !important;
        max-width: 100% !important;
    }

    /* Stack columns แนวตั้งบนมือถือ */
    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
        gap: 0 !important;
    }
    [data-testid="column"] {
        min-width: 100% !important;
        width: 100% !important;
        flex: 1 1 100% !important;
    }

    /* Header ขนาดเล็กลง */
    h1 { font-size: 1.6rem !important; }
    h2 { font-size: 1.2rem !important; }
    h3 { font-size: 1.05rem !important; }

    /* Tab labels — กะทัดรัดขึ้น */
    .stTabs [data-baseweb="tab"] {
        font-size: 0.72rem !important;
        padding: 0.4rem 0.4rem !important;
    }

    /* Metric values */
    [data-testid="stMetricValue"] { font-size: 1.4rem !important; }
    [data-testid="stMetricLabel"] { font-size: 0.72rem !important; }

    /* ปุ่ม — touch target ใหญ่ขึ้น */
    .stButton > button {
        min-height: 2.8rem !important;
        font-size: 0.95rem !important;
    }

    /* Radio buttons แนวตั้ง */
    [data-testid="stRadio"] > div {
        flex-direction: column !important;
        gap: 0.25rem !important;
    }

    /* Expander */
    [data-testid="stExpander"] summary {
        font-size: 0.9rem !important;
    }

    /* Caption เล็กลงนิด */
    .stCaptionContainer p { font-size: 0.72rem !important; }

    /* Divider margin */
    hr { margin: 0.5rem 0 !important; }
}
</style>
""", unsafe_allow_html=True)

# ── Session state defaults ──────────────────────────────────────
for key, default in [
    ("username", None), ("last_route", None), ("last_lat", None),
    ("last_lon", None), ("last_places", []), ("show_nutrition", False),
    ("nutrition_data", None), ("screen_width", 1200),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ตรวจจับขนาดหน้าจอ (ทำครั้งเดียวตอน load)
_sw = streamlit_js_eval(js_expressions="window.innerWidth", key="get_screen_width")
if _sw:
    st.session_state.screen_width = int(_sw)

IS_MOBILE = st.session_state.screen_width < 768
MAP_HEIGHT = 320 if IS_MOBILE else 480

# ── Login gate ──────────────────────────────────────────────────
if st.session_state.username is None:
    st.title("🏃 GEO RUN CLUB")
    st.subheader("เข้าสู่ระบบ / สมัครสมาชิก")
    col1, col2 = st.columns([1, 1])
    with col1:
        uname = st.text_input("ชื่อผู้ใช้ (username)", placeholder="เช่น Panupong")
        dname = st.text_input("ชื่อที่แสดง", placeholder="เช่น Benz")
        weight = st.number_input("น้ำหนัก (kg)", 30, 200, 65)
        pace = st.number_input("เพซเป้าหมาย (นาที/km)", 3.0, 15.0, 7.0, 0.5)
        if st.button("เข้าสู่ระบบ / สร้างโปรไฟล์", type="primary", use_container_width=True):
            if uname.strip():
                save_profile(uname.strip(), dname.strip() or uname.strip(), weight, pace)
                st.session_state.username = uname.strip()
                st.rerun()
            else:
                st.error("กรุณาใส่ชื่อผู้ใช้")
    with col2:
        st.info("**GEO RUN CLUB** ช่วยวางแผนเส้นทางวิ่งวงกลมในกรุงเทพฯ ด้วย AI\n\n"
                "✅ วางแผนเส้นทางอัตโนมัติ\n\n"
                "✅ ตรวจจับตำแหน่ง GPS\n\n"
                "✅ แชร์เส้นทางกับเพื่อนผ่าน QR Code\n\n"
                "✅ แผนฝึกวิ่งส่วนตัว + นัดวิ่งกลุ่ม")
    st.stop()

# ── Load profile ────────────────────────────────────────────────
profile = get_profile(st.session_state.username) or {}

# ── Header ──────────────────────────────────────────────────────
streak_data = get_streak(st.session_state.username)
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    if IS_MOBILE:
        st.markdown("### 🏃 GEO RUN CLUB")
    else:
        st.title("🏃 GEO RUN CLUB")
    streak = streak_data["current"]
    if streak >= 7:
        st.markdown(f"🔥🔥🔥 **{streak} วัน**" if IS_MOBILE else f"🔥🔥🔥 **Streak {streak} วัน** — ยอดเยี่ยมมาก!")
    elif streak >= 3:
        st.markdown(f"🔥🔥 **{streak} วัน**" if IS_MOBILE else f"🔥🔥 **Streak {streak} วัน** — keep it up!")
    elif streak >= 1:
        st.markdown(f"🔥 **{streak} วัน**" if IS_MOBILE else f"🔥 **Streak {streak} วัน** — เริ่มต้นดี!")
with col_h2:
    st.caption(f"👤 {profile.get('display_name', st.session_state.username)}")
    if st.button("ออกจากระบบ", use_container_width=True):
        st.session_state.username = None
        st.session_state.last_route = None
        st.rerun()

# ── Check for shared route in URL params ────────────────────────
params = st.query_params
shared_lat = float(params["lat"]) if "lat" in params else None
shared_lon = float(params["lon"]) if "lon" in params else None
shared_km = float(params["km"]) if "km" in params else None

# ── Shared route banner — แจ้งเตือนเพื่อนที่สแกน QR ────────────
if shared_lat and shared_lon and shared_km and not st.session_state.last_route:
    st.warning(
        f"📲 **เพื่อนแชร์เส้นทาง {shared_km} km มาให้!**  \n"
        f"กด **🗺️ วางแผนเส้นทางวิ่ง** ในแท็บแรก เพื่อสร้างเส้นทางเดียวกัน"
    )
    if st.button("🗺️ สร้างเส้นทางนี้เลย!", type="primary", use_container_width=True):
        if not os.getenv("ANTHROPIC_API_KEY"):
            st.error("❌ ไม่พบ ANTHROPIC_API_KEY")
        else:
            weight_kg = profile.get("weight_kg", 65)
            pace_val = profile.get("pace_min_per_km", 7.0)
            with st.spinner(f"⏳ AI กำลังสร้างเส้นทาง {shared_km} km..."):
                try:
                    result = plan_route(shared_lat, shared_lon, shared_km,
                                        weight_kg, pace_val)
                    st.session_state.last_route = result
                    st.session_state.last_lat = shared_lat
                    st.session_state.last_lon = shared_lon
                    st.session_state.last_places = get_nearby_places(
                        shared_lat, shared_lon, radius_m=1000)
                    save_run(st.session_state.username, result.total_km,
                             result.estimated_calories, result.estimated_minutes,
                             {"lat": shared_lat, "lon": shared_lon, "km": result.total_km})
                    st.query_params.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ {e}")

# ── Tabs ────────────────────────────────────────────────────────
tab_plan, tab_saved, tab_group, tab_board, tab_profile, tab_train = st.tabs([
    "🗺️ วางแผนเส้นทาง", "❤️ Route โปรด", "👥 วิ่งกลุ่ม & นัดวิ่ง",
    "🏆 Leaderboard", "📊 โปรไฟล์ & สถิติ", "📅 แผนการฝึก"
])


# ════════════════════════════════════════════════════════════════
# TAB 1: วางแผนเส้นทาง
# ════════════════════════════════════════════════════════════════
with tab_plan:
    col_form, col_map = st.columns([1, 2])

    # ── Weather banner ──
    weather_lat = st.session_state.get("gps_lat") or 13.7294
    weather_lon = st.session_state.get("gps_lon") or 100.5418
    try:
        wx = get_weather(weather_lat, weather_lon)
        if wx["warning"] == "danger":
            st.error(f"{wx['icon']} **{wx['description']}** | {wx['temperature']}°C "
                     f"(รู้สึกเหมือน {wx['feels_like']}°C) | 💧 {wx['humidity']}% | "
                     f"🌧️ โอกาสฝน {wx['rain_prob_next3h']}%\n\n{wx['warning_msg']}")
        elif wx["warning"] == "warning":
            st.warning(f"{wx['icon']} **{wx['description']}** | {wx['temperature']}°C "
                       f"(รู้สึกเหมือน {wx['feels_like']}°C) | 💧 {wx['humidity']}% | "
                       f"🌧️ โอกาสฝน {wx['rain_prob_next3h']}%\n\n{wx['warning_msg']}")
        else:
            st.success(f"{wx['icon']} **{wx['description']}** | {wx['temperature']}°C "
                       f"(รู้สึกเหมือน {wx['feels_like']}°C) | 💧 {wx['humidity']}% | "
                       f"💨 {wx['wind_speed']} km/h | {wx['warning_msg']}")
    except Exception:
        st.info("🌡️ ไม่สามารถโหลดสภาพอากาศได้ในขณะนี้")

    # ── Air quality banner ──
    try:
        aq = get_air_quality(weather_lat, weather_lon)
        aq_text = (f"🌫️ **ฝุ่น PM2.5: {aq['pm25']} µg/m³** | PM10: {aq['pm10']} µg/m³ | "
                   f"AQI: {aq['aqi']} | {aq['color_label']}\n\n{aq['advice']}")
        if aq["warning"] == "danger":
            st.error(aq_text)
        elif aq["warning"] in ("warning", "info"):
            st.warning(aq_text)
        else:
            st.success(aq_text)
    except Exception:
        pass

    with col_form:
        st.subheader("📍 ตำแหน่งเริ่มต้น")

        if st.button("📡 ใช้ตำแหน่ง GPS ปัจจุบัน", use_container_width=True):
            st.session_state["request_gps"] = True

        gps_lat, gps_lon = None, None
        if st.session_state.get("request_gps"):
            with st.spinner("กำลังดึงตำแหน่ง GPS..."):
                loc = get_geolocation()
            if loc and "coords" in loc:
                gps_lat = loc["coords"]["latitude"]
                gps_lon = loc["coords"]["longitude"]
                st.session_state["gps_lat"] = gps_lat
                st.session_state["gps_lon"] = gps_lon
                st.session_state["request_gps"] = False
                st.success(f"✅ GPS: {gps_lat:.5f}, {gps_lon:.5f}")

        stored_lat = st.session_state.get("gps_lat")
        stored_lon = st.session_state.get("gps_lon")

        default_lat = shared_lat or stored_lat or 13.7294
        default_lon = shared_lon or stored_lon or 100.5418

        lat = st.number_input("Latitude", value=float(default_lat), format="%.5f", step=0.0001)
        lon = st.number_input("Longitude", value=float(default_lon), format="%.5f", step=0.0001)

        if stored_lat:
            st.caption(f"🛰️ GPS ล่าสุด: {stored_lat:.5f}, {stored_lon:.5f}")
        else:
            st.caption("ค่าเริ่มต้น = สวนลุมพินี")

        st.divider()
        st.subheader("🎯 เป้าหมาย")

        if shared_km:
            st.info(f"📲 รับเส้นทางจากเพื่อน: {shared_km} km")

        mode = st.radio("โหมด", ["📏 ระยะทาง (km)", "🔥 แคลอรี่ (kcal)"])

        weight_kg = profile.get("weight_kg", 65)
        pace_val = profile.get("pace_min_per_km", 7.0)

        if "ระยะทาง" in mode:
            # clamp shared_km to slider range to avoid crash
            default_km = float(min(30.0, max(1.0, shared_km))) if shared_km else 5.0
            target_km = st.slider("ระยะทาง (km)", 1.0, 30.0, default_km, 0.5)
            target_calories = None
        else:
            target_calories = st.slider("แคลอรี่ (kcal)", 100, 1000, 300, 50)
            target_km = None

        # 🌙 Night Running Mode
        night_mode = st.toggle("🌙 Night Running Mode", value=False,
                               help="AI จะเลือกเส้นทางที่มีแสงสว่าง ใกล้ BTS/MRT และร้านสะดวกซื้อ 24 ชม.")

        with st.expander("⚙️ ตั้งค่าผู้วิ่ง"):
            weight_kg = st.number_input("น้ำหนัก (kg)", 30, 200, int(weight_kg))
            pace_val = st.number_input("เพซ (นาที/km)", 3.0, 15.0, float(pace_val), 0.5)

        run_btn = st.button("🗺️ วางแผนเส้นทางวิ่ง", type="primary", use_container_width=True)

    with col_map:
        def base_map(clat, clon):
            m = folium.Map(location=[clat, clon], zoom_start=14)
            folium.Marker([clat, clon], popup="จุดเริ่มต้น",
                          icon=folium.Icon(color="green", icon="play")).add_to(m)
            return m

        food_color = {"restaurant": "orange", "fast_food": "orange", "food_court": "orange",
                      "cafe": "purple", "bar": "purple", "juice_bar": "purple",
                      "convenience": "blue", "supermarket": "blue", "drinking_water": "blue"}

        if st.session_state.last_route and st.session_state.last_lat:
            route = st.session_state.last_route
            m = base_map(st.session_state.last_lat, st.session_state.last_lon)
            route_color = "#1e40af" if st.session_state.get("last_night_mode") else "#16a34a"
            line = [[p[1], p[0]] for p in route.geometry]
            # เส้นเส้นทางวิ่ง
            route_line = folium.PolyLine(
                line, color=route_color, weight=5, opacity=0.85)
            route_line.add_to(m)
            # หัวลูกศรแสดงทิศทางวิ่ง
            PolyLineTextPath(
                route_line,
                "        ►",
                repeat=True,
                offset=0,
                attributes={
                    "fill": "#ffffff",
                    "font-weight": "bold",
                    "font-size": "14",
                },
            ).add_to(m)
            for i, wp in enumerate(route.waypoints):
                folium.CircleMarker([wp.lat, wp.lon], radius=6,
                                    color=route_color, fill=True, fill_color=route_color,
                                    tooltip=f"จุดที่ {i+1}").add_to(m)
            for p in st.session_state.get("last_places", []):
                color = food_color.get(p["kind"], "gray")
                folium.Marker(
                    [p["lat"], p["lon"]],
                    popup=f"{p['icon']} {p['name']} ({p['distance_m']}m)",
                    tooltip=f"{p['icon']} {p['name']}",
                    icon=folium.Icon(color=color,
                                     icon="cutlery" if color == "orange" else "coffee", prefix="fa"),
                ).add_to(m)
            if line:
                lats = [p[0] for p in line]
                lons = [p[1] for p in line]
                m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])
            st_folium(m, width=None, height=MAP_HEIGHT, key="map_with_route")

            # ── Route stats (always visible from session state) ──────
            st.divider()
            c1, c2, c3 = st.columns(3)
            c1.metric("📏 ระยะทาง", f"{route.total_km} km")
            c2.metric("🔥 แคลอรี่", f"{int(route.estimated_calories)} kcal")
            c3.metric("⏱️ เวลา", f"{route.estimated_minutes} นาที")
            if route.agent_summary:
                st.info(f"**AI แนะนำ:** {route.agent_summary}")

            # ── Save route form (persistent — never disappears) ──────
            with st.expander("💾 บันทึกเส้นทางนี้", expanded=False):
                route_name = st.text_input("ตั้งชื่อเส้นทาง",
                                           placeholder="เช่น เส้นลุมพินีเช้าวันจันทร์",
                                           key="route_name_input")
                if st.button("❤️ บันทึก Route โปรด", use_container_width=True,
                             key="save_route_btn"):
                    if route_name.strip():
                        _lat = st.session_state.last_lat
                        _lon = st.session_state.last_lon
                        save_route(
                            username=st.session_state.username,
                            name=route_name.strip(),
                            lat=_lat, lon=_lon,
                            total_km=route.total_km,
                            geometry_json=json.dumps(route.geometry),
                            waypoints_json=json.dumps([{"lat": w.lat, "lon": w.lon}
                                                       for w in route.waypoints]),
                            agent_summary=route.agent_summary,
                        )
                        st.success("❤️ บันทึกแล้ว!")
                    else:
                        st.warning("กรุณาตั้งชื่อเส้นทางก่อน")
        else:
            st_folium(base_map(lat, lon), width=None, height=MAP_HEIGHT, key="map_default")

    if run_btn:
        if not os.getenv("ANTHROPIC_API_KEY"):
            st.error("❌ ไม่พบ ANTHROPIC_API_KEY")
            st.stop()

        final_km = (calories_to_distance(target_calories, weight_kg, pace_val)
                    if target_calories else target_km)

        label = "🌙 " if night_mode else ""
        with st.spinner(f"⏳ AI กำลังวางแผนเส้นทาง {label}{final_km:.1f} km..."):
            try:
                result = plan_route(lat, lon, final_km, weight_kg, pace_val, night_mode=night_mode)
            except Exception as e:
                st.error(f"❌ {e}")
                st.stop()

        st.session_state.last_route = result
        st.session_state.last_lat = lat
        st.session_state.last_lon = lon
        st.session_state.last_night_mode = night_mode
        st.session_state.last_places = get_nearby_places(lat, lon, radius_m=1000)

        save_run(st.session_state.username, result.total_km, result.estimated_calories,
                 result.estimated_minutes, {"lat": lat, "lon": lon, "km": result.total_km})

        nutri = get_nutrition_advice(result.total_km, result.estimated_calories, weight_kg)
        st.session_state.nutrition_data = nutri
        st.session_state.show_nutrition = True

        st.toast("✅ วางแผนสำเร็จ!" + (" 🌙 Night Mode" if night_mode else ""))
        st.rerun()

    # ── Nearby food & drink (shown from session state after rerun) ──
    if st.session_state.last_route:
        st.subheader("🍛 ร้านอาหาร & ร้านน้ำใกล้เส้นทาง")
        nearby_places = st.session_state.get("last_places", [])

        if not nearby_places:
            st.info("ไม่พบร้านอาหารหรือร้านน้ำในรัศมี 1 km จาก OSM — "
                    "อาจเป็นเพราะพื้นที่นี้ยังไม่มีคนลงข้อมูลใน OpenStreetMap")
            if st.button("🔄 ค้นหาร้านอีกครั้ง", key="retry_places"):
                with st.spinner("กำลังค้นหา..."):
                    new_places = get_nearby_places(
                        st.session_state.last_lat, st.session_state.last_lon, radius_m=1500)
                st.session_state.last_places = new_places
                st.rerun()
        else:
            food = [p for p in nearby_places if p["kind"] not in ("drinking_water", "convenience", "supermarket")]
            drink = [p for p in nearby_places if p["kind"] in ("cafe", "juice_bar", "bar", "drinking_water")]
            shop = [p for p in nearby_places if p["kind"] in ("convenience", "supermarket")]
            tabs_nearby = st.tabs(["🍛 ร้านอาหาร", "☕ เครื่องดื่ม/คาเฟ่", "🏪 ร้านสะดวกซื้อ"])
            for tab_n, group in zip(tabs_nearby, [food, drink, shop]):
                with tab_n:
                    if group:
                        for p in group[:8]:
                            st.write(f"{p['icon']} **{p['name']}** — {p['distance_m']} เมตร")
                    else:
                        st.caption("ไม่พบในรัศมี 1 km")

    # ── Post-workout Nutrition (shown after route generated) ──
    if st.session_state.show_nutrition and st.session_state.nutrition_data:
        nutri = st.session_state.nutrition_data
        st.divider()
        st.subheader("🍽️ โภชนาการหลังวิ่ง")
        intensity_color = {"เบา": "success", "ปานกลาง": "warning", "หนัก": "error"}.get(
            nutri["intensity"], "info")
        getattr(st, intensity_color)(
            f"**ความหนัก: {nutri['intensity']}** | {nutri['window_msg']}")

        nc1, nc2, nc3 = st.columns(3)
        nc1.metric("🥩 โปรตีนที่ต้องการ", f"{nutri['protein_target_g']} g")
        nc2.metric("🍚 คาร์บที่ต้องการ", f"{nutri['carb_target_g']} g")
        nc3.metric("💧 น้ำที่ควรดื่ม", f"{nutri['water_ml']} ml")

        col_p, col_c = st.columns(2)
        with col_p:
            st.write("**🥩 อาหารโปรตีนแนะนำ**")
            for f in nutri["protein_foods"]:
                st.write(f"• **{f['name']}** — {f['protein_g']}g โปรตีน, {f['cal']} kcal")
                st.caption(f"  {f['note']}")
        with col_c:
            st.write("**🍚 อาหารคาร์บแนะนำ**")
            for f in nutri["carb_foods"]:
                st.write(f"• **{f['name']}** — {f['carb_g']}g คาร์บ, {f['cal']} kcal")
                st.caption(f"  {f['note']}")

        with st.expander("💧 เครื่องดื่มแนะนำ + สิ่งที่ควรหลีกเลี่ยง"):
            st.write("**ควรดื่ม:**")
            for h in nutri["hydration"]:
                st.write(f"• **{h['name']}** — {h['note']}")
            st.write("**ควรหลีกเลี่ยง:**")
            for a in nutri["avoid"]:
                st.write(f"• {a}")


# ════════════════════════════════════════════════════════════════
# TAB 2: Route โปรด
# ════════════════════════════════════════════════════════════════
with tab_saved:
    st.subheader("❤️ เส้นทางที่บันทึกไว้")
    saved = get_saved_routes(st.session_state.username)

    if not saved:
        st.info("ยังไม่มีเส้นทางที่บันทึก — วางแผนเส้นทางแล้วกด 'บันทึก Route โปรด'")
    else:
        for r in saved:
            with st.container(border=True):
                col_info, col_act = st.columns([3, 1])
                with col_info:
                    st.write(f"**{r['name']}**")
                    st.caption(f"📏 {r['total_km']} km | 📍 {r['lat']:.4f}, {r['lon']:.4f} | 🗓️ {r['created_at'][:10]}")
                    if r.get("agent_summary"):
                        st.caption(f"💬 {r['agent_summary'][:80]}...")
                with col_act:
                    if st.button("▶️ โหลดเส้นทางนี้", key=f"load_{r['id']}", use_container_width=True):
                        from models.response import RouteResponse, Waypoint
                        loaded = RouteResponse(
                            waypoints=[Waypoint(**w) for w in json.loads(r["waypoints_json"])],
                            geometry=json.loads(r["geometry_json"]),
                            total_km=r["total_km"],
                            estimated_calories=0,
                            estimated_minutes=0,
                            agent_summary=r.get("agent_summary", ""),
                        )
                        st.session_state.last_route = loaded
                        st.session_state.last_lat = r["lat"]
                        st.session_state.last_lon = r["lon"]
                        save_run(st.session_state.username, r["total_km"], 0, 0,
                                 {"lat": r["lat"], "lon": r["lon"], "km": r["total_km"]})
                        st.success(f"โหลด '{r['name']}' แล้ว!")
                        st.rerun()
                    if st.button("🗑️ ลบ", key=f"del_{r['id']}", use_container_width=True):
                        delete_saved_route(r["id"], st.session_state.username)
                        st.rerun()


# ════════════════════════════════════════════════════════════════
# TAB 3: วิ่งกลุ่ม & นัดวิ่ง
# ════════════════════════════════════════════════════════════════
with tab_group:
    subtab_qr, subtab_meetup = st.tabs(["📲 แชร์เส้นทาง (QR)", "📆 นัดวิ่งกลุ่ม"])

    # ── QR Share ──
    with subtab_qr:
        st.subheader("👥 แชร์เส้นทางให้เพื่อนวิ่งด้วยกัน")
        route = st.session_state.last_route
        lat_s = st.session_state.last_lat
        lon_s = st.session_state.last_lon

        if route is None:
            st.info("🗺️ วางแผนเส้นทางก่อน แล้วกลับมาแชร์ที่นี่")
        else:
            st.success(f"เส้นทางปัจจุบัน: **{route.total_km} km** | {int(route.estimated_calories)} kcal")
            app_url = st.secrets.get("APP_URL") or "https://your-app.streamlit.app"
            share_url = f"{app_url}?lat={lat_s}&lon={lon_s}&km={route.total_km}"

            col_qr, col_info = st.columns([1, 1])
            with col_qr:
                st.write("**QR Code สำหรับเพื่อน**")
                qr = qrcode.QRCode(version=1, box_size=8, border=4)
                qr.add_data(share_url)
                qr.make(fit=True)
                img = qr.make_image(fill_color="#15803d", back_color="white")
                buf = BytesIO()
                img.save(buf, format="PNG")
                st.image(buf.getvalue(), width=250)
                st.caption("ให้เพื่อนสแกน QR Code นี้เพื่อโหลดเส้นทางเดียวกัน")
            with col_info:
                st.write("**ลิงก์แชร์**")
                st.code(share_url, language=None)
                st.markdown("""
**วิธีใช้:**
1. ให้เพื่อนสแกน QR Code ด้วยกล้องโทรศัพท์
2. หรือ copy ลิงก์ส่งให้เพื่อนผ่าน LINE / WhatsApp
3. เพื่อนจะเห็นเส้นทางเดียวกันบนแผนที่
4. นัดเจอที่จุดเริ่มต้น แล้ววิ่งด้วยกัน! 🏃‍♂️🏃‍♀️
                """)

            st.divider()
            m = folium.Map(location=[lat_s, lon_s], zoom_start=14)
            folium.Marker([lat_s, lon_s], popup="จุดนัดพบ",
                          icon=folium.Icon(color="green", icon="flag")).add_to(m)
            line = [[p[1], p[0]] for p in route.geometry]
            group_line = folium.PolyLine(line, color="#16a34a", weight=5, opacity=0.85)
            group_line.add_to(m)
            PolyLineTextPath(
                group_line, "        ►", repeat=True, offset=0,
                attributes={"fill": "#ffffff", "font-weight": "bold", "font-size": "14"},
            ).add_to(m)
            if line:
                lats = [p[0] for p in line]
                lons = [p[1] for p in line]
                m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])
            st_folium(m, width=None, height=MAP_HEIGHT - 60, key="map_group")

    # ── Meetup Scheduling ──
    with subtab_meetup:
        st.subheader("📆 สร้างการนัดวิ่งกลุ่ม")

        with st.form("meetup_form"):
            mt_title = st.text_input("ชื่อการนัดวิ่ง", placeholder="เช่น วิ่งเช้าวันเสาร์ที่สวนลุม")
            col_d, col_t = st.columns(2)
            with col_d:
                mt_date = st.date_input("วันที่", value=date.today(), min_value=date.today())
            with col_t:
                mt_time = st.time_input("เวลา", value=datetime.strptime("06:00", "%H:%M").time())

            route_now = st.session_state.last_route
            lat_now = st.session_state.last_lat or 13.7294
            lon_now = st.session_state.last_lon or 100.5418
            route_km_now = route_now.total_km if route_now else 0.0

            if route_now:
                st.info(f"ใช้เส้นทางปัจจุบัน: **{route_km_now} km** "
                        f"| จุดนัด: {lat_now:.4f}, {lon_now:.4f}")
            else:
                st.caption("ยังไม่มีเส้นทาง — จะนัดที่พิกัดปัจจุบัน (สวนลุมพินี)")

            mt_desc = st.text_area("รายละเอียด (ไม่บังคับ)",
                                   placeholder="เช่น ใส่รองเท้าวิ่ง น้ำไป 1 ขวด นัดที่ประตูหลัก")
            submitted = st.form_submit_button("📆 สร้างการนัดวิ่ง", type="primary",
                                              use_container_width=True)
            if submitted:
                if mt_title.strip():
                    save_meetup(
                        creator=st.session_state.username,
                        title=mt_title.strip(),
                        meetup_date=mt_date.isoformat(),
                        meetup_time=mt_time.strftime("%H:%M"),
                        lat=lat_now, lon=lon_now,
                        route_km=route_km_now,
                        description=mt_desc.strip(),
                    )
                    st.toast("✅ สร้างการนัดวิ่งแล้ว!")
                    st.rerun()
                else:
                    st.warning("กรุณาใส่ชื่อการนัดวิ่ง")

        st.divider()
        st.subheader("📋 การนัดวิ่งที่กำลังจะมาถึง")
        meetups = get_upcoming_meetups()
        if meetups:
            for mu in meetups:
                with st.container(border=True):
                    col_mi, col_mm = st.columns([3, 1])
                    with col_mi:
                        st.write(f"**{mu['title']}**")
                        st.caption(
                            f"📅 {mu['meetup_date']} | ⏰ {mu['meetup_time']} | "
                            f"📏 {mu['route_km'] or 0:.1f} km | 👤 โดย {mu['creator']}"
                        )
                        if mu.get("description"):
                            st.caption(f"📝 {mu['description']}")
                    with col_mm:
                        # QR for meetup with location
                        app_url = st.secrets.get("APP_URL") or "https://your-app.streamlit.app"
                        mu_url = f"{app_url}?lat={mu['lat']}&lon={mu['lon']}&km={mu['route_km'] or 0}"
                        if st.button("📲 QR นัดวิ่ง", key=f"mu_qr_{mu['id']}", use_container_width=True):
                            st.session_state[f"show_mu_qr_{mu['id']}"] = True
                    if st.session_state.get(f"show_mu_qr_{mu['id']}"):
                        qr2 = qrcode.QRCode(version=1, box_size=6, border=3)
                        qr2.add_data(mu_url)
                        qr2.make(fit=True)
                        img2 = qr2.make_image(fill_color="#1d4ed8", back_color="white")
                        buf2 = BytesIO()
                        img2.save(buf2, format="PNG")
                        st.image(buf2.getvalue(), width=180,
                                 caption=f"QR สำหรับ '{mu['title']}'")
        else:
            st.info("ยังไม่มีการนัดวิ่ง — สร้างการนัดวิ่งแรกได้เลย!")


# ════════════════════════════════════════════════════════════════
# TAB 4: Leaderboard
# ════════════════════════════════════════════════════════════════
with tab_board:
    st.subheader("🏆 Leaderboard")
    board_mode = st.radio("ดูอันดับ", ["📅 สัปดาห์นี้", "🏅 ตลอดกาล"], horizontal=True)

    if "สัปดาห์" in board_mode:
        board = get_weekly_leaderboard()
        km_col, runs_col = "week_km", "week_runs"
        st.caption("นับตั้งแต่วันจันทร์ของสัปดาห์นี้")
    else:
        board = get_alltime_leaderboard()
        km_col, runs_col = "total_km", "total_runs"

    medals = ["🥇", "🥈", "🥉"]
    my_user = st.session_state.username

    for i, row in enumerate(board):
        medal = medals[i] if i < 3 else f"#{i+1}"
        is_me = row["username"] == my_user
        km = row[km_col]
        runs = row[runs_col]
        with st.container(border=is_me):
            col_rank, col_name, col_km, col_runs = st.columns([1, 3, 2, 2])
            col_rank.markdown(f"### {medal}")
            name_label = f"**{row['display_name']}** 👈" if is_me else row['display_name']
            col_name.markdown(name_label)
            col_km.metric("km", f"{km:.1f}")
            col_runs.metric("ครั้ง", f"{runs}")

    if not board:
        st.info("ยังไม่มีข้อมูล — ไปวิ่งกันก่อนเลย!")


# ════════════════════════════════════════════════════════════════
# TAB 5: โปรไฟล์ & สถิติ
# ════════════════════════════════════════════════════════════════
with tab_profile:
    col_prof, col_stats = st.columns([1, 1])

    with col_prof:
        st.subheader("👤 โปรไฟล์ของฉัน")
        s = streak_data
        sc1, sc2 = st.columns(2)
        sc1.metric("🔥 Streak ปัจจุบัน", f"{s['current']} วัน",
                   delta="วิ่งวันนี้แล้ว ✅" if s['ran_today'] else "ยังไม่ได้วิ่งวันนี้")
        sc2.metric("🏅 Streak สูงสุด", f"{s['longest']} วัน")
        st.divider()
        with st.form("profile_form"):
            new_name = st.text_input("ชื่อที่แสดง", value=profile.get("display_name", ""))
            new_weight = st.number_input("น้ำหนัก (kg)", 30, 200, int(profile.get("weight_kg", 65)))
            new_pace = st.number_input("เพซเป้าหมาย (นาที/km)", 3.0, 15.0,
                                       float(profile.get("pace_min_per_km", 7.0)), 0.5)
            if st.form_submit_button("💾 บันทึกโปรไฟล์", use_container_width=True):
                save_profile(st.session_state.username, new_name, new_weight, new_pace)
                st.success("✅ บันทึกแล้ว!")
                st.rerun()

        st.divider()
        with st.expander("⚠️ ลบบัญชี", expanded=False):
            st.warning("ลบบัญชีและข้อมูลทั้งหมดของคุณออกจากระบบ (ไม่สามารถกู้คืนได้)")
            if st.button("🗑️ ลบบัญชีของฉัน", use_container_width=True):
                st.session_state["confirm_delete_account"] = True
            if st.session_state.get("confirm_delete_account"):
                st.error("ยืนยันจะลบบัญชี **ถาวร** ใช่ไหม?")
                da1, da2 = st.columns(2)
                if da1.button("✅ ลบเลย", use_container_width=True, type="primary"):
                    uname_to_delete = st.session_state.username
                    delete_account(uname_to_delete)
                    st.session_state.username = None
                    st.session_state.last_route = None
                    st.session_state["confirm_delete_account"] = False
                    st.rerun()
                if da2.button("❌ ยกเลิก", use_container_width=True):
                    st.session_state["confirm_delete_account"] = False
                    st.rerun()

    with col_stats:
        st.subheader("📊 สถิติรวม")
        stats = get_stats(st.session_state.username)
        if stats and stats.get("total_runs", 0) > 0:
            s1, s2 = st.columns(2)
            s1.metric("🏃 จำนวนครั้งที่วิ่ง", f"{stats['total_runs']} ครั้ง")
            s2.metric("📏 ระยะทางรวม", f"{stats['total_km']:.1f} km")
            s3, s4 = st.columns(2)
            s3.metric("🔥 แคลอรี่รวม", f"{int(stats['total_calories'])} kcal")
            s4.metric("📈 เฉลี่ย/ครั้ง", f"{stats['avg_km']:.1f} km")
        else:
            st.info("ยังไม่มีสถิติ — ไปวางแผนเส้นทางแรกได้เลย! 🏃")

    st.divider()
    hcol1, hcol2 = st.columns([3, 1])
    hcol1.subheader("📋 ประวัติการวิ่ง")
    with hcol2:
        if st.button("🗑️ ล้างประวัติทั้งหมด", use_container_width=True):
            st.session_state["confirm_clear"] = True
    if st.session_state.get("confirm_clear"):
        st.warning("⚠️ ยืนยันจะลบประวัติการวิ่งทั้งหมดของคุณ? (ไม่สามารถกู้คืนได้)")
        cc1, cc2 = st.columns(2)
        if cc1.button("✅ ยืนยัน ลบเลย", use_container_width=True, type="primary"):
            clear_runs(st.session_state.username)
            st.session_state["confirm_clear"] = False
            st.toast("🗑️ ล้างประวัติแล้ว!")
            st.rerun()
        if cc2.button("❌ ยกเลิก", use_container_width=True):
            st.session_state["confirm_clear"] = False
            st.rerun()

    runs = get_runs(st.session_state.username)
    if runs:
        for run in runs:
            with st.container():
                rc1, rc2, rc3, rc4 = st.columns([2, 1, 1, 1])
                rc1.write(f"📅 {run['date']}")
                rc2.write(f"📏 {run['total_km']} km")
                rc3.write(f"🔥 {int(run['calories'])} kcal")
                rc4.write(f"⏱️ {run['minutes']} นาที")
        st.caption(f"แสดง {len(runs)} รายการล่าสุด")
    else:
        st.info("ยังไม่มีประวัติการวิ่ง")


# ════════════════════════════════════════════════════════════════
# TAB 6: แผนการฝึก
# ════════════════════════════════════════════════════════════════
with tab_train:
    st.subheader("📅 สร้างแผนการฝึกวิ่งส่วนตัว")

    col_tf, col_tp = st.columns([1, 2])

    with col_tf:
        with st.form("training_plan_form"):
            goal = st.selectbox("เป้าหมายการแข่งขัน", ["5K", "10K", "21K (Half Marathon)", "42K (Full Marathon)"])
            weeks = st.slider("จำนวนสัปดาห์", 4, 24, 8)
            current_km = st.number_input("ปัจจุบันวิ่งได้สบายๆ (km/ครั้ง)", 0.5, 30.0, 5.0, 0.5)
            submitted_plan = st.form_submit_button("📅 สร้างแผนการฝึก", type="primary",
                                                   use_container_width=True)

        if submitted_plan:
            if not os.getenv("ANTHROPIC_API_KEY"):
                st.error("❌ ไม่พบ ANTHROPIC_API_KEY")
            else:
                goal_clean = goal.split(" ")[0]  # "5K", "10K", "21K", "42K"
                with st.spinner(f"⏳ AI กำลังสร้างแผนฝึก {goal_clean} {weeks} สัปดาห์..."):
                    try:
                        plan = generate_training_plan(goal_clean, weeks, current_km)
                        save_training_plan(
                            username=st.session_state.username,
                            goal=goal_clean,
                            weeks=weeks,
                            current_km=current_km,
                            plan_json=json.dumps(plan, ensure_ascii=False),
                            start_date=date.today().isoformat(),
                        )
                        st.session_state["training_plan"] = plan
                        st.toast(f"✅ สร้างแผนฝึก {goal_clean} แล้ว!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ {e}")

        # Load existing plan button
        existing = get_latest_training_plan(st.session_state.username)
        if existing and "training_plan" not in st.session_state:
            if st.button("📂 โหลดแผนล่าสุด", use_container_width=True):
                st.session_state["training_plan"] = json.loads(existing["plan_json"])
                st.rerun()

    with col_tp:
        plan_data = st.session_state.get("training_plan")

        if plan_data is None and existing:
            plan_data = json.loads(existing["plan_json"])

        if plan_data:
            st.write(f"### 🎯 แผนฝึก {plan_data.get('goal', '')} — {plan_data.get('weeks', 0)} สัปดาห์")
            if plan_data.get("summary"):
                st.info(plan_data["summary"])

            plan_weeks = plan_data.get("plan", [])
            if plan_weeks:
                week_labels = [f"สัปดาห์ {w['week']}" for w in plan_weeks]
                selected_week_label = st.selectbox("เลือกดูสัปดาห์", week_labels, key="plan_week_sel")
                selected_week_idx = week_labels.index(selected_week_label)
                week_data = plan_weeks[selected_week_idx]

                st.write(f"**โฟกัส:** {week_data.get('focus', '')} | "
                         f"**รวม:** {week_data.get('total_km', 0)} km")

                days = week_data.get("days", [])
                for day in days:
                    day_type = day.get("type", "rest")
                    color_dot = DAY_COLORS.get(day_type, "⚪")
                    km_text = f"{day['km']} km" if day.get("km", 0) > 0 else "พัก"
                    with st.container(border=True):
                        dc1, dc2, dc3 = st.columns([2, 1, 4])
                        dc1.write(f"**{day.get('day', '')}**")
                        dc2.write(f"{color_dot} {km_text}")
                        dc3.caption(day.get("note", ""))
        else:
            st.info("สร้างแผนการฝึกด้วยฟอร์มด้านซ้าย หรือโหลดแผนที่มีอยู่")
            st.markdown("""
**ประเภทวันฝึก:**
- 🟢 Easy — วิ่งเบา ควบคุมลมหายใจ
- 🟡 Tempo — วิ่งเร็วปานกลาง 70% effort
- 🔵 Long Run — วิ่งระยะยาว สร้างความอดทน
- ⚪ Rest — พักฟื้น / ยืดเหยียด
- 🔴 Race — วันแข่ง
            """)
