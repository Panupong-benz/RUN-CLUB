import json
import os
import anthropic


PLAN_PROMPT = """Generate a {weeks}-week running training plan for a {goal} race goal.
Current fitness: can run ~{current_km} km comfortably.

Return ONLY valid JSON (no markdown) in this exact structure:
{{
  "goal": "{goal}",
  "weeks": {weeks},
  "summary": "2 sentences in Thai about this plan",
  "plan": [
    {{
      "week": 1,
      "focus": "Thai focus description (e.g. ปรับสภาพร่างกาย)",
      "total_km": 15,
      "days": [
        {{"day": "จันทร์", "type": "easy", "km": 3, "note": "วิ่งเบาๆ ควบคุมหายใจ"}},
        {{"day": "อังคาร", "type": "rest", "km": 0, "note": "พักฟื้น"}},
        {{"day": "พุธ", "type": "tempo", "km": 4, "note": "วิ่งเร็วปานกลาง 70% effort"}},
        {{"day": "พฤหัส", "type": "rest", "km": 0, "note": "พักหรือยืดเหยียด"}},
        {{"day": "ศุกร์", "type": "easy", "km": 3, "note": "วิ่งเบา"}},
        {{"day": "เสาร์", "type": "long", "km": 5, "note": "Long run เพิ่มระยะทาง"}},
        {{"day": "อาทิตย์", "type": "rest", "km": 0, "note": "พักผ่อน"}}
      ]
    }}
  ]
}}

Generate all {weeks} weeks. Gradually increase distance each week. Week types: easy/tempo/long/rest/race"""

DAY_COLORS = {
    "easy": "🟢",
    "tempo": "🟡",
    "long": "🔵",
    "rest": "⚪",
    "race": "🔴",
}


def generate_training_plan(goal: str, weeks: int, current_km: float) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = PLAN_PROMPT.format(goal=goal, weeks=weeks, current_km=current_km)

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    # Strip markdown code blocks if present (handles ```json ... ``` and ``` ... ```)
    if text.startswith("```"):
        # Remove opening fence (```json or ```)
        first_newline = text.find("\n")
        text = text[first_newline + 1:] if first_newline != -1 else text[3:]
        # Remove closing fence
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return json.loads(text.strip())
