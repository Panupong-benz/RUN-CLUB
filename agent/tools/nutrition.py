"""
Post-workout nutrition advisor — rule-based, no API cost.
"""


THAI_FOOD_DB = {
    "protein": [
        {"name": "ข้าวไข่ดาว", "protein_g": 12, "cal": 350, "note": "ง่าย หาได้ทุกที่"},
        {"name": "ข้าวหมูแดง", "protein_g": 25, "cal": 450, "note": "โปรตีนสูง คาร์บพอดี"},
        {"name": "ไข่ต้ม 2 ฟอง", "protein_g": 12, "cal": 150, "note": "ของว่างโปรตีนสูง"},
        {"name": "นมโปรตีนสูง/โยเกิร์ต", "protein_g": 15, "cal": 180, "note": "กินได้ทันทีหลังวิ่ง"},
        {"name": "อกไก่ย่าง + ข้าวกล้อง", "protein_g": 35, "cal": 420, "note": "มื้อหลักฟื้นฟูกล้ามเนื้อ"},
        {"name": "ปลาทูทอด + ข้าว", "protein_g": 28, "cal": 380, "note": "โอเมก้า 3 ช่วยลดการอักเสบ"},
    ],
    "carb": [
        {"name": "กล้วยหอม", "carb_g": 27, "cal": 105, "note": "กินได้ทันที เติม glycogen"},
        {"name": "ข้าวสวย 1 ถ้วย", "carb_g": 45, "cal": 200, "note": "คาร์บหลักฟื้นฟูพลังงาน"},
        {"name": "ขนมปังโฮลวีต", "carb_g": 30, "cal": 160, "note": "ดัชนีน้ำตาลต่ำ"},
        {"name": "มันเทศต้ม", "carb_g": 26, "cal": 115, "note": "วิตามินสูง ย่อยง่าย"},
    ],
    "hydration": [
        {"name": "น้ำเปล่า", "note": "ดื่มทันที อย่างน้อย 500 ml"},
        {"name": "น้ำมะพร้าว", "note": "เติม electrolyte ธรรมชาติ"},
        {"name": "นมช็อกโกแลต", "note": "โปรตีน + คาร์บ + electrolyte ครบ"},
        {"name": "เกลือแร่/ORS", "note": "ถ้าวิ่งนานกว่า 60 นาทีหรือเหงื่อออกมาก"},
    ],
    "avoid": [
        "อาหารมันจัด — ย่อยยากตอนร่างกายฟื้นตัว",
        "เครื่องดื่มแอลกอฮอล์ — ขัดขวางการฟื้นฟูกล้ามเนื้อ",
        "อาหารรสจัด/เผ็ดจัด — กระเพาะอาหารไวหลังออกกำลังกาย",
        "งดอาหารนาน — ควรกินภายใน 30-60 นาทีหลังวิ่ง",
    ],
}


def get_nutrition_advice(distance_km: float, calories_burned: float, weight_kg: float) -> dict:
    # Protein target: 0.25-0.4g per kg for recovery
    protein_target = round(weight_kg * 0.3)
    # Carb target: roughly 1g per kg for runs under 10km, 1.5g for longer
    carb_factor = 1.5 if distance_km >= 10 else 1.0
    carb_target = round(weight_kg * carb_factor)
    # Water: 500ml per km + base 500ml
    water_ml = round(distance_km * 500 + 500)

    # Intensity label
    if distance_km < 3:
        intensity = "เบา"
        window_msg = "กินของว่างเบาๆ ภายใน 1 ชั่วโมง"
    elif distance_km < 8:
        intensity = "ปานกลาง"
        window_msg = "กินภายใน 30–45 นาทีหลังวิ่ง เน้นโปรตีน + คาร์บ"
    else:
        intensity = "หนัก"
        window_msg = "กินโปรตีน + คาร์บภายใน 30 นาที — ร่างกายต้องการฟื้นฟูเร็ว"

    # Pick top 3 protein and 2 carb recommendations
    protein_recs = THAI_FOOD_DB["protein"][:3]
    carb_recs = THAI_FOOD_DB["carb"][:2]

    return {
        "intensity": intensity,
        "window_msg": window_msg,
        "protein_target_g": protein_target,
        "carb_target_g": carb_target,
        "water_ml": water_ml,
        "protein_foods": protein_recs,
        "carb_foods": carb_recs,
        "hydration": THAI_FOOD_DB["hydration"],
        "avoid": THAI_FOOD_DB["avoid"],
    }
