from mcp.server.fastmcp import FastMCP
import httpx
import os

PORT = int(os.environ.get("PORT", 8000))

mcp = FastMCP(
    "날씨요정",
    host="0.0.0.0",
    port=PORT,
    stateless_http=True,
)

# 한글 도시명 → 영문 변환 테이블
CITY_MAP = {
    "서울": "Seoul", "부산": "Busan", "인천": "Incheon", "대구": "Daegu",
    "대전": "Daejeon", "광주": "Gwangju", "수원": "Suwon", "울산": "Ulsan",
    "제주": "Jeju", "춘천": "Chuncheon", "전주": "Jeonju", "청주": "Cheongju",
    "창원": "Changwon", "포항": "Pohang", "천안": "Cheonan", "성남": "Seongnam",
    "안양": "Anyang", "고양": "Goyang", "용인": "Yongin", "평택": "Pyeongtaek",
}

@mcp.tool(
    description="Recommends outfit and items to prepare based on weather and today's schedule from 날씨요정(날씨요정). Provide city name and date (today/tomorrow), and optionally today's schedule for context-aware recommendations.",
    annotations={
        "title": "Get Weather-based Outfit & Checklist",
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": True,
        "idempotentHint": True,
    }
)
async def get_weather_advice(city: str, date: str = "today", schedule: str = "") -> str:
    """
    Args:
        city: 도시명 (예: 서울, 부산, 제주, Seoul)
        date: 오늘(today) 또는 내일(tomorrow)
        schedule: 오늘 일정 (선택사항, 예: 오후 외근, 중요한 발표)
    """
    # 한글 도시명 영문 변환
    city_en = CITY_MAP.get(city.strip(), city.strip())
    city_display = city.strip()

    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_en}&count=1&language=ko"

    async with httpx.AsyncClient(timeout=10) as client:
        geo_res = await client.get(geo_url)
        geo_data = geo_res.json()

        if not geo_data.get("results"):
            return f"'{city}' 도시를 찾을 수 없어요. 다시 입력해 주세요. (예: 서울, 부산, 제주)"

        lat = geo_data["results"][0]["latitude"]
        lon = geo_data["results"][0]["longitude"]

        weather_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,windspeed_10m_max,weathercode"
            f"&timezone=Asia/Seoul&forecast_days=2"
        )
        weather_res = await client.get(weather_url)
        weather_data = weather_res.json()

    daily = weather_data["daily"]
    idx = 0 if date == "today" else 1
    date_label = "오늘" if date == "today" else "내일"

    temp_max = daily["temperature_2m_max"][idx]
    temp_min = daily["temperature_2m_min"][idx]
    rain_prob = daily["precipitation_probability_max"][idx]
    wind_speed = daily["windspeed_10m_max"][idx]
    weather_code = daily["weathercode"][idx]

    weather_desc = parse_weather_code(weather_code)
    outfit, items = recommend(temp_max, temp_min, rain_prob, wind_speed, weather_code, schedule)

    result = f"""🧚 날씨요정의 {date_label} 브리핑 ({city_display})

🌤️ 날씨: {weather_desc}
🌡️ 기온: 최고 {temp_max}°C / 최저 {temp_min}°C
🌧️ 강수 확률: {rain_prob}%
💨 바람: {wind_speed} km/h

👗 옷차림 추천
{outfit}

🎒 챙겨야 할 것들
{items}"""

    if schedule:
        result += f"\n\n📅 일정 고려: {schedule} 일정을 반영했어요!"

    return result


def parse_weather_code(code: int) -> str:
    if code == 0:
        return "맑음 ☀️"
    elif code in [1, 2, 3]:
        return "구름 조금 🌤️"
    elif code in [45, 48]:
        return "안개 🌫️"
    elif code in [51, 53, 55]:
        return "이슬비 🌦️"
    elif code in [61, 63, 65]:
        return "비 🌧️"
    elif code in [71, 73, 75]:
        return "눈 ❄️"
    elif code in [80, 81, 82]:
        return "소나기 ⛈️"
    elif code in [95, 96, 99]:
        return "뇌우 ⛈️"
    else:
        return "흐림 ☁️"


def recommend(temp_max, temp_min, rain_prob, wind_speed, weather_code, schedule):
    outfit_parts = []
    items_parts = []

    avg_temp = (temp_max + temp_min) / 2
    if avg_temp >= 27:
        outfit_parts.append("- 반팔, 반바지 또는 얇은 원피스")
    elif avg_temp >= 20:
        outfit_parts.append("- 얇은 긴팔 또는 가디건")
    elif avg_temp >= 12:
        outfit_parts.append("- 자켓 또는 맨투맨")
    elif avg_temp >= 5:
        outfit_parts.append("- 코트 또는 두꺼운 니트")
    else:
        outfit_parts.append("- 패딩 또는 두꺼운 코트")
        items_parts.append("- 핫팩 🔥")

    if rain_prob >= 60 or weather_code in [61, 63, 65, 80, 81, 82]:
        outfit_parts.append("- 방수 소재 아우터 권장")
        items_parts.append("- 우산 ☂️ (강수 확률 높음)")
        items_parts.append("- 여벌 양말")
    elif rain_prob >= 30:
        items_parts.append("- 접이식 우산 (혹시 모르니)")

    if wind_speed >= 30:
        outfit_parts.append("- 바람막이 또는 목도리 추천")
        items_parts.append("- 목도리 🧣")

    if schedule:
        schedule_lower = schedule.lower()
        if any(kw in schedule_lower for kw in ["발표", "미팅", "회의", "면접", "포멀"]):
            outfit_parts.append("- 포멀한 스타일 추천 (중요한 일정 고려)")
        if any(kw in schedule_lower for kw in ["외근", "야외", "현장"]):
            items_parts.append("- 편한 신발 👟 (외근 일정)")
            items_parts.append("- 보조배터리 🔋")

    if not items_parts:
        items_parts.append("- 특별히 챙길 것 없어요, 가볍게 출발하세요 ✨")

    return "\n".join(outfit_parts), "\n".join(items_parts)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
