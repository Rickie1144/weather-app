import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
from streamlit_js_eval import get_geolocation

# 1. 페이지 설정
st.set_page_config(page_title="Global Weather Dash", page_icon="🌤️", layout="wide")

# API 키 설정 (secrets.toml에 저장된 키 사용)
try:
    API_KEY = st.secrets["WEATHER_API_KEY"]
except KeyError:
    st.error("API 키가 설정되지 않았습니다. .streamlit/secrets.toml 파일을 확인하세요.")
    st.stop()

BASE_URL = "http://api.weatherapi.com/v1"

# 디자인 CSS
st.markdown("""
    <style>
    .stMetric { background-color: #ffffff; padding: 20px; border-radius: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; height: 130px; }
    .big-font { font-size: 60px !important; font-weight: bold; margin-bottom: 0px; }
    .city-name { font-size: 26px; color: #2c3e50; font-weight: bold; }
    .warning-box { background-color: #ff4b4b; color: white; padding: 15px; border-radius: 10px; font-weight: bold; margin-bottom: 15px; }
    .forecast-card { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #eee; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

# 유틸리티 함수들
def get_moon_emoji(phase_text):
    moon_map = {
        "New Moon": "🌑 (신월)", "Waxing Crescent": "🌒 (초승달)", "First Quarter": "🌓 (상현달)",
        "Waxing Gibbous": "🌔 (상현망간의 달)", "Full Moon": "🌕 (보름달)", "Waning Gibbous": "🌖 (하현망간의 달)",
        "Last Quarter": "🌗 (하현달)", "Waning Crescent": "🌘 (그믐달)"
    }
    return moon_map.get(phase_text, "🌙")

def get_wind_direction_emoji(dir_text):
    if "N" in dir_text and "E" in dir_text: return "↗️ " + dir_text
    if "N" in dir_text and "W" in dir_text: return "↖️ " + dir_text
    if "S" in dir_text and "E" in dir_text: return "↘️ " + dir_text
    if "S" in dir_text and "W" in dir_text: return "↙️ " + dir_text
    if "N" in dir_text: return "⬆️ " + dir_text
    if "S" in dir_text: return "⬇️ " + dir_text
    if "E" in dir_text: return "➡️ " + dir_text
    if "W" in dir_text: return "⬅️ " + dir_text
    return dir_text

def get_weather_style(temp, condition, aqi, wind_kph):
    emoji, color, msg_list = "☀️", "#3498db", []
    cond = condition.lower()
    if "비" in cond or "rain" in cond: emoji, color = "☔", "#5d6d7e"
    elif "눈" in cond or "snow" in cond: emoji, color = "☃️", "#aeb6bf"
    elif "흐림" in cond or "cloudy" in cond or "overcast" in cond: emoji, color = "☁️", "#85929e"
    elif "맑음" in cond or "sunny" in cond or "clear" in cond: emoji, color = "☀️", "#f1c40f"
    
    if temp >= 30: msg_list.append("너무 더워요! 🥵")
    elif temp <= 0: msg_list.append("꽁꽁 얼어있는 날씨예요! 🥶")
    if aqi >= 3: msg_list.append("미세먼지 주의! 마스크 필수 😷")
    if wind_kph >= 40: msg_list.append(f"강풍 주의! 태풍급 바람({wind_kph}km/h) 🌪️")
    return emoji, " | ".join(msg_list), color

# 2. 위치 제어 로직
st.title("🌍 실시간 세계 날씨 & 7일 예보")
col_search1, col_search2 = st.columns([3, 1])

# [수정됨] 드롭다운 메뉴를 위한 도시 매핑 데이터
city_map = {
    "서울": "Seoul", "부산": "Busan", "인천": "Incheon", "대구": "Daegu", 
    "대전": "Daejeon", "광주": "Gwangju", "울산": "Ulsan", "세종": "Sejong",
    "제주": "Jeju", "수원": "Suwon", "성남": "Seongnam", "고양": "Goyang",
    "용인": "Yongin", "창원": "Changwon", "청주": "Cheongju", "전주": "Jeonju", 
    "천안": "Cheonan", "김해": "Gimhae", "포항": "Pohang", "진주": "Jinju",
    "원주": "Wonju", "춘천": "Chuncheon", "강릉": "Gangneung", "아산": "Asan"
}

with col_search2:
    st.subheader("📍 위치 설정")
    use_gps = st.checkbox("내 현재 위치(GPS) 사용")
    
    query = "Seoul" # 기본값 초기화

    if use_gps:
        loc = get_geolocation()
        if loc:
            query = f"{loc['coords']['latitude']},{loc['coords']['longitude']}"
            st.info("📍 GPS 좌표 사용 중")
        else:
            st.warning("GPS 정보를 가져오는 중입니다...")
    else:
        # [수정됨] 텍스트 입력 대신 드롭다운(Selectbox) 사용
        city_options = ["지역을 선택하세요"] + list(city_map.keys()) + ["직접 입력(해외/기타)"]
        selected_option = st.selectbox("지역 선택", city_options, index=0)
        
        if selected_option == "지역을 선택하세요":
            query = "Seoul" # 선택 안 하면 기본 서울
        elif selected_option == "직접 입력(해외/기타)":
            custom_city = st.text_input("도시 이름을 영어로 입력하세요", placeholder="London, New York...")
            if custom_city:
                query = custom_city
        else:
            # 한글 선택 -> 영어 쿼리로 변환
            query = city_map[selected_option]

# 3. 데이터 로드 (7일 예보 포함)
if query:
    try:
        # 1주일 뒤까지 데이터를 위해 days=7 설정
        forecast_url = f"{BASE_URL}/forecast.json?key={API_KEY}&q={query}&days=7&aqi=yes&lang=ko"
        res = requests.get(forecast_url).json()
        
        if "error" in res:
            st.error("도시를 찾을 수 없습니다. 올바른 이름을 입력해주세요.")
        else:
            current = res['current']
            location = res['location']
            forecast_days = res['forecast']['forecastday'] # 7일 데이터 리스트
            
            # 지난 3일 데이터 로드 (무료 플랜 제한 고려하여 예외처리)
            past_days_data = []
            try:
                for i in range(1, 4):
                    date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                    h_res = requests.get(f"{BASE_URL}/history.json?key={API_KEY}&q={query}&dt={date}&lang=ko").json()
                    if "error" not in h_res:
                        past_days_data.append(h_res)
            except Exception:
                pass # 과거 데이터 로드 실패 시 무시

            # 4. 화면 표시 (현재 날씨)
            aqi_val = current['air_quality']['us-epa-index']
            wind_kph = current['wind_kph']
            emoji, status_msg, theme_color = get_weather_style(current['temp_c'], current['condition']['text'], aqi_val, wind_kph)

            with col_search1:
                st.markdown(f"<p class='city-name'>{location['name']}, {location['country']}</p>", unsafe_allow_html=True)
                st.markdown(f"<div class='big-font' style='color:{theme_color};'>{emoji} {current['temp_c']}°C</div>", unsafe_allow_html=True)
                st.markdown(f"### 현재 상태: {current['condition']['text']}")
                if "강풍" in status_msg: st.markdown(f"<div class='warning-box'>{status_msg}</div>", unsafe_allow_html=True)
                elif status_msg: st.warning(status_msg)

            st.divider()

            # 상세 메트릭
            m1, m2, m3, m4, m5 = st.columns(5)
            with m1: st.markdown(f"<div class='stMetric'>🌡️ <b>체감</b><br>{current['feelslike_c']}°C</div>", unsafe_allow_html=True)
            with m2: st.markdown(f"<div class='stMetric'>💧 <b>습도</b><br>{current['humidity']}%</div>", unsafe_allow_html=True)
            with m3: st.markdown(f"<div class='stMetric'>🚩 <b>바람</b><br>{get_wind_direction_emoji(current['wind_dir'])}<br>{wind_kph}km/h</div>", unsafe_allow_html=True)
            with m4: st.markdown(f"<div class='stMetric'>☀️ <b>자외선</b><br>{current['uv']}</div>", unsafe_allow_html=True)
            with m5: st.markdown(f"<div class='stMetric'>🌗 <b>달 모양</b><br>{get_moon_emoji(forecast_days[0]['astro']['moon_phase'])}</div>", unsafe_allow_html=True)

            # 5. 향후 1주일(7일) 예보
            st.subheader("🗓️ 향후 7일간의 예보")
            f_cols = st.columns(7)
            for i, day in enumerate(forecast_days):
                with f_cols[i]:
                    date_obj = datetime.strptime(day['date'], '%Y-%m-%d')
                    weekday = ["월", "화", "수", "목", "금", "토", "일"][date_obj.weekday()]
                    p_emoji, _, _ = get_weather_style(day['day']['avgtemp_c'], day['day']['condition']['text'], 0, 0)
                    st.markdown(f"""
                    <div class='forecast-card'>
                        <span style='color:#777;'>{day['date'][5:]} ({weekday})</span><br>
                        <span style='font-size:30px;'>{p_emoji}</span><br>
                        <b>{day['day']['avgtemp_c']}°C</b><br>
                        <span style='font-size:12px;'>{day['day']['condition']['text']}</span>
                    </div>
                    """, unsafe_allow_html=True)

            # 6. 시간대별 차트 (오늘)
            st.subheader("⏰ 오늘 온도 변화 (1시간 간격)")
            if 'hour' in forecast_days[0]:
                df_hour = pd.DataFrame([{"시간": h['time'].split(" ")[1], "온도": h['temp_c']} for h in forecast_days[0]['hour']])
                st.line_chart(df_hour.set_index("시간"))

            # 7. 지난 3일 기록 (데이터가 있을 경우에만 표시)
            if past_days_data:
                st.subheader("📅 지난 3일간의 기록")
                p_cols = st.columns(3)
                for i, data in enumerate(past_days_data):
                    if i < 3: # 컬럼 개수 맞춤
                        day = data['forecast']['forecastday'][0]
                        p_emoji, _, _ = get_weather_style(day['day']['avgtemp_c'], day['day']['condition']['text'], 0, 0)
                        with p_cols[i]:
                            st.markdown(f"<div style='background-color:#eee; padding:15px; border-radius:10px; text-align:center;'><b>{day['date']}</b><br><span style='font-size:25px;'>{p_emoji}</span><br>{day['day']['avgtemp_c']}°C</div>", unsafe_allow_html=True)

    except Exception as e:
        st.error(f"데이터를 불러오는 데 실패했습니다. 잠시 후 다시 시도해주세요. ({e})")