from mcp.server.fastmcp import FastMCP
import httpx
import os

PORT = int(os.environ.get("PORT", 8000))

mcp = FastMCP(
    "아참!",
    host="0.0.0.0",
    port=PORT,
    stateless_http=True,
)

CITY_MAP = {
    "서울": "Seoul", "부산": "Busan", "인천": "Incheon", "대구": "Daegu",
    "대전": "Daejeon", "광주": "Gwangju", "수원": "Suwon", "울산": "Ulsan",
    "제주": "Jeju", "춘천": "Chuncheon", "전주": "Jeonju", "청주": "Cheongju",
    "창원": "Changwon", "포항": "Pohang", "천안": "Cheonan", "성남": "Seongnam",
    "안양": "Anyang", "고양": "Goyang", "용인": "Yongin", "평택": "Pyeongtaek",
}

FORMAL_KEYWORDS = ["발표", "미팅", "회의", "면접", "포멀", "세미나", "강의", "수업", "행사", "식"]
OUTDOOR_KEYWORDS = ["외근", "야외", "현장", "출장", "등산", "운동", "캠핑"]
ITEM_KEYWORDS = ["챙겨", "챙기", "가져", "준비", "잊지", "놓치지", "필요"]


@mcp.tool(
    description="아참!(Ahcham) recommends outfit and items to bring based on today's weather and calendar schedule. Provide city name and date (today/tomorrow), and optionally today's schedule. If city is unknown, ask the user which city to use.",
    annotations={
        "title": "Get Outfit & Checklist based on Weather and Schedule",
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": True,
        "idempotentHint": True,
    }
)
async def daily_checklist(city: str = "", date: str = "today", schedule: str = "") -> str:
    """
    Args:
        city: 도시명 (예: 서울, 부산, 제주). 비어있으면 사용자에게 되물음.
        date: 오늘(today) 또는 내일(tomorrow)
        schedule: 캘린더 일정 전체 텍스트 (예: "오후 2시 팀 미팅 / 서류 챙기기")
    """
    if not city.strip():
        return "어느 도시 기준으로 알려드릴까요? (예: 서울, 부산, 제주)"

    city_en = CITY_MAP.get(city.strip(), city.strip())
    city_display = city.strip()
    date_label = "오늘" if date == "today" else "내일"

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

    temp_max = daily["temperature_2m_max"][idx]
    temp_min = daily["temperature_2m_min"][idx]
    rain_prob = daily["precipitation_probability_max"][idx]
    wind_speed = daily["windspeed_10m_max"][idx]
    weather_code = daily["weathercode"][idx]

    weather_desc = parse_weather_code(weather_code)
    schedule_comment, calendar_items, schedule_list = parse_schedule(schedule)
    outfit_list, items_list = recommend(temp_max, temp_min, rain_prob, wind_speed, weather_code, schedule)

    # 캘린더 준비물 추가
    for item in calendar_items:
        items_list.append(f"{item} (캘린더 등록 항목)")

    # 출력
    result = f"[아참! 나가기 전에 확인할 체크리스트]\n"
    result += f"📍 {city_display} · {date_label}\n"

    # 날씨
    result += f"\n✅ {date_label} 날씨:\n"
    result += f"* {weather_desc}\n"
    result += f"* 기온: 최고 {temp_max}°C / 최저 {temp_min}°C\n"
    result += f"* 강수 확률: {rain_prob}%\n"
    result += f"* 바람: {wind_speed} km/h\n"

    # 일정
    result += f"\n✅ {date_label} 일정:\n"
    if schedule_list:
        for s in schedule_list:
            result += f"* {s}\n"
    else:
        result += "* 등록된 일정이 없어요.\n"

    # 옷차림
    result += f"\n✅ 옷차림 추천:\n"
    for o in outfit_list:
        result += f"* {o}\n"
    if schedule_comment:
        result += f"* {schedule_comment}\n"

    # 준비물
    result += f"\n✅ 챙겨야 할 준비물:\n"
    if items_list:
        for item in items_list:
            result += f"* {item}\n"
    else:
        result += "* 특별히 챙길 것 없어요, 가볍게 출발하세요 ✨\n"

    return result


def parse_schedule(schedule: str):
    if not schedule:
        return "", [], []

    s = schedule.lower()
    comment = ""
    calendar_items = []

    if any(kw in s for kw in FORMAL_KEYWORDS):
        comment = "미팅이 있으니 포멀한 스타일을 추천해요"
    elif any(kw in s for kw in OUTDOOR_KEYWORDS):
        comment = "야외 활동이 있으니 활동하기 편한 옷차림을 추천해요"

    # 일정 목록 파싱
    entries = [e.strip() for e in schedule.replace(",", "/").replace("·", "/").split("/") if e.strip()]

    # 준비물 감지
    for entry in entries:
        if any(kw in entry for kw in ITEM_KEYWORDS):
            cleaned = entry
            for kw in ["챙겨야 함", "챙겨야함", "챙기기", "챙겨", "가져오기", "준비", "잊지 말기", "놓치지 말기"]:
                cleaned = cleaned.replace(kw, "").strip()
            if cleaned:
                calendar_items.append(cleaned)

    return comment, calendar_items, entries


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
        outfit_parts.append("반팔, 반바지 또는 얇은 원피스")
    elif avg_temp >= 20:
        outfit_parts.append("얇은 긴팔 또는 가디건")
    elif avg_temp >= 12:
        outfit_parts.append("자켓 또는 맨투맨")
    elif avg_temp >= 5:
        outfit_parts.append("코트 또는 두꺼운 니트")
    else:
        outfit_parts.append("패딩 또는 두꺼운 코트")
        items_parts.append("핫팩 🔥")

    if rain_prob >= 60 or weather_code in [61, 63, 65, 80, 81, 82]:
        outfit_parts.append("일교차가 크니 방수 소재 아우터를 권장해요")
        items_parts.append("우산 (강수 확률 높음) ☂️")
        items_parts.append("여벌 양말")
    elif rain_prob >= 30:
        items_parts.append("접이식 우산 (혹시 모르니)")

    if wind_speed >= 30:
        outfit_parts.append("바람막이 또는 목도리 추천")
        items_parts.append("목도리 🧣")

    if schedule:
        s = schedule.lower()
        if any(kw in s for kw in OUTDOOR_KEYWORDS):
            items_parts.append("편한 신발 👟")
            items_parts.append("보조배터리 🔋")

    return outfit_parts, items_parts


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
