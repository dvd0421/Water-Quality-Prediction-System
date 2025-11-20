# Water Safety Monitor — Polished UI/UX
# Drop-in replacement for your current app.py

import streamlit as st
import requests
import json
from datetime import datetime, timedelta
import pandas as pd
import plotly.graph_objects as go
from geopy.geocoders import Nominatim
import os

# ------------------------------------------------------------
# Page configuration
# ------------------------------------------------------------
st.set_page_config(
    page_title="Water Safety Monitor",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": "https://open-meteo.com/",
        "Report a bug": "mailto:example@example.com",
        "About": "Water Safety Monitor • Real-time risk insights powered by Open-Meteo"
    },
)

# ------------------------------------------------------------
# Global Styles (refined)
# ------------------------------------------------------------
st.markdown(
    """
<style>
:root{
  --brand:#2B66F6;
  --brand-600:#2452c5;
  --safe:#17a34a;     /* Tailwind-ish palette */
  --caution:#f59e0b;
  --unsafe:#ef4444;
  --bg-soft:rgba(0,0,0,0.03);
  --card-bg:rgba(255,255,255,0.7);
  --border:#e5e7eb;
}
html, body, [data-testid="stAppViewContainer"]{
  background: radial-gradient(1200px 600px at 25% -10%, rgba(43,102,246,0.08), transparent 60%),
              radial-gradient(800px 400px at 90% 0%, rgba(23,163,74,0.08), transparent 60%);
  backdrop-filter: saturate(1.1);
}
.main-header{
  font-size: clamp(2.2rem, 3vw, 3rem);
  font-weight: 800;
  letter-spacing: -0.02em;
  text-align: center;
  margin: 0 0 1.25rem 0;
  background: linear-gradient(90deg, var(--brand), #22c55e);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.subheader{
  text-align:center;
  color:#6b7280;
  margin-bottom:1.5rem;
}
.card{
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 1rem 1.25rem;
  box-shadow: 0 6px 24px rgba(0,0,0,0.04);
}
.metric-grid{
  display:grid;
  grid-template-columns: repeat(3, minmax(0,1fr));
  gap: .75rem;
}
.metric{
  border:1px dashed #e5e7eb;
  border-radius:12px;
  padding:.75rem;
  text-align:center;
  background: white;
}
.badge{
  display:inline-flex;
  align-items:center;
  gap:.5rem;
  font-weight:700;
  padding:.4rem .7rem;
  border-radius:999px;
  font-size:.9rem;
  border:1px solid var(--border);
  background:white;
}
.badge.safe    { color:var(--safe);    }
.badge.caution { color:var(--caution); }
.badge.unsafe  { color:var(--unsafe);  }
.notice{
  border-left: 6px solid var(--brand);
  background: #f8fafc;
  padding:.8rem 1rem;
  border-radius:8px;
}
.callout.safe{
  background:#ecfdf5; border-left:6px solid var(--safe);
}
.callout.caution{
  background:#fffbeb; border-left:6px solid var(--caution);
}
.callout.unsafe{
  background:#fef2f2; border-left:6px solid var(--unsafe);
}
.footer{
  text-align:center; color:#6b7280; padding:1.2rem 0;
}
hr{ margin: 1.5rem 0; }
</style>
""",
    unsafe_allow_html=True,
)

# ------------------------------------------------------------
# Data storage
# ------------------------------------------------------------
HISTORY_FILE = "water_safety_history.json"

# ------------------------------------------------------------
# Session state
# ------------------------------------------------------------
if "history" not in st.session_state:
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                st.session_state.history = json.load(f)
        except Exception:
            st.session_state.history = []
    else:
        st.session_state.history = []

st.session_state.setdefault("last_location", None)

# ------------------------------------------------------------
# Cached helpers (snappier UI)
# ------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=60 * 10)
def geocode_city(city_name: str):
    try:
        geolocator = Nominatim(user_agent="water_safety_monitor")
        location = geolocator.geocode(city_name)
        if location:
            return location.latitude, location.longitude, location.address
        return None, None, None
    except Exception:
        return None, None, None

@st.cache_data(show_spinner=False, ttl=60 * 5)
def fetch_weather_data(latitude, longitude):
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,precipitation,rain,weather_code",
            "hourly": "precipitation,temperature_2m",
            "timezone": "auto",
            "past_days": 3,
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None

# ------------------------------------------------------------
# Risk model (unchanged logic, tidied)
# ------------------------------------------------------------
def calculate_risk_score(weather_data, user_observations):
    risk_score = 0
    risk_factors = []

    if not weather_data:
        return 50, ["Unable to fetch weather data"], "Caution"

    current = weather_data.get("current", {})
    hourly = weather_data.get("hourly", {})

    # Temperature risk
    temp = current.get("temperature_2m", 0)
    if 20 <= temp <= 45:
        temp_risk = min(25, (temp - 20) / 25 * 25)
        risk_score += temp_risk
        risk_factors.append(f"Temperature ({temp}°C) in bacterial growth range")
    elif temp > 45:
        risk_score += 15
        risk_factors.append(f"Very high temperature ({temp}°C)")

    # Humidity risk
    humidity = current.get("relative_humidity_2m", 0)
    if humidity > 70:
        humidity_risk = min(15, (humidity - 70) / 30 * 15)
        risk_score += humidity_risk
        risk_factors.append(f"High humidity ({humidity}%)")

    # Current precipitation
    current_rain = current.get("precipitation", 0) or current.get("rain", 0)
    if current_rain and current_rain > 0:
        rain_risk = min(20, current_rain * 4)
        risk_score += rain_risk
        risk_factors.append(f"Active rainfall ({current_rain} mm)")

    # Accumulated precipitation
    if hourly and "precipitation" in hourly:
        precip_data = [p or 0 for p in hourly["precipitation"][-72:]]
        precip_24h = sum(precip_data[-24:])
        if precip_24h > 10:
            rain_24h_risk = min(25, (precip_24h - 10) / 40 * 25)
            risk_score += rain_24h_risk
            risk_factors.append(f"Heavy rain in last 24h ({precip_24h:.1f} mm)")
        elif precip_24h > 5:
            risk_score += 10
            risk_factors.append(f"Moderate rain in last 24h ({precip_24h:.1f} mm)")

        precip_72h = sum(precip_data)
        if precip_72h > 50:
            risk_score += 15
            risk_factors.append(f"Prolonged rainfall over 3 days ({precip_72h:.1f} mm)")

    # Observations
    obs_risk_map = {
        "Water looks cloudy/murky": 15,
        "Unusual smell": 20,
        "Visible contamination": 25,
        "Nearby flooding": 20,
        "Dead fish/animals nearby": 25,
        "Industrial discharge observed": 30,
        "Sewage overflow": 35,
    }
    for obs, risk_value in obs_risk_map.items():
        if obs in user_observations:
            risk_score += risk_value
            risk_factors.append(f"Observation: {obs}")

    risk_score = min(100, risk_score)

    if risk_score < 30:
        risk_level = "Safe"
    elif risk_score < 60:
        risk_level = "Caution"
    else:
        risk_level = "Unsafe"

    return risk_score, risk_factors, risk_level

def get_recommendations(risk_level, risk_score):
    recommendations = {
        "Safe": {
            "title": "Water Appears Safe",
            "actions": [
                "Water quality indicators are within normal parameters",
                "Standard water usage is acceptable",
                "Continue monitoring conditions regularly",
                "Follow local water authority guidelines",
            ],
            "color": "safe",
        },
        "Caution": {
            "title": "Exercise Caution",
            "actions": [
                "**Boil water for at least 1 minute before drinking**",
                "Use bottled water for drinking and cooking if available",
                "Wash hands thoroughly after water contact",
                "Monitor for any health symptoms",
                "Avoid using water for infant formula preparation",
                "Check with local water authorities for updates",
            ],
            "color": "caution",
        },
        "Unsafe": {
            "title": "Water Quality Alert - High Risk",
            "actions": [
                "**DO NOT drink tap water**",
                "Use only bottled or commercially treated water",
                "Avoid water contact with open wounds",
                "Do not use for cooking, brushing teeth, or ice making",
                "Boiling may not remove all contaminants",
                "Contact local health authorities immediately",
                "Consider evacuation if contamination is severe",
                "Monitor official advisories closely",
            ],
            "color": "unsafe",
        },
    }
    rec = recommendations.get(risk_level, recommendations["Caution"])
    if risk_score >= 80:
        rec["actions"].insert(0, "⚠️ **CRITICAL**: Risk score is very high - take immediate action")
    return rec

def save_to_history(location_name, lat, lon, weather_data, risk_score, risk_level, risk_factors, observations, notes=""):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "location": location_name,
        "latitude": lat,
        "longitude": lon,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_factors": risk_factors,
        "observations": observations,
        "notes": notes,
        "temperature": weather_data.get("current", {}).get("temperature_2m"),
        "humidity": weather_data.get("current", {}).get("relative_humidity_2m"),
        "precipitation": weather_data.get("current", {}).get("precipitation", 0),
    }
    st.session_state.history.append(entry)

    cutoff_date = datetime.now() - timedelta(days=30)
    st.session_state.history = [
        h for h in st.session_state.history if datetime.fromisoformat(h["timestamp"]) > cutoff_date
    ]
    with open(HISTORY_FILE, "w") as f:
        json.dump(st.session_state.history, f, indent=2)

def risk_gauge(risk_score, risk_level):
    colors = {"Safe": "#17a34a", "Caution": "#f59e0b", "Unsafe": "#ef4444"}
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=risk_score,
            title={"text": f"Risk Score • {risk_level}"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": colors[risk_level]},
                "steps": [
                    {"range": [0, 30], "color": "#d1fae5"},
                    {"range": [30, 60], "color": "#fef3c7"},
                    {"range": [60, 100], "color": "#fee2e2"},
                ],
                "threshold": {"line": {"color": "#ef4444", "width": 4}, "thickness": 0.7, "value": 90},
            },
        )
    )
    fig.update_layout(height=280, margin=dict(l=10, r=10, t=50, b=10))
    return fig

# ------------------------------------------------------------
# Header
# ------------------------------------------------------------
st.markdown('<h1 class="main-header">💧 Water Safety Monitor</h1>', unsafe_allow_html=True)
st.markdown('<div class="subheader">Real-time water contamination risk assessment based on environmental conditions</div>', unsafe_allow_html=True)

# ------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------
with st.sidebar:
    st.markdown("### 📍 Location")
    location_method = st.radio("Method", ["Enter City Name", "Enter Coordinates"], horizontal=True)

    if location_method == "Enter City Name":
        city_name = st.text_input(
            "City Name",
            value=st.session_state.last_location or "",
            placeholder="e.g., Abu Dhabi, London, New York",
        )
        if st.button("Get Location", type="primary"):
            with st.spinner("Geocoding…"):
                lat, lon, address = geocode_city(city_name)
            if lat and lon:
                st.session_state.latitude = lat
                st.session_state.longitude = lon
                st.session_state.location_name = address
                st.session_state.last_location = city_name
                st.success(f"Location found:\n\n{address}")
            else:
                st.error("Could not find location. Try a different name.")
    else:
        col1, col2 = st.columns(2)
        lat_input = col1.number_input("Latitude", value=24.4539, format="%.4f")
        lon_input = col2.number_input("Longitude", value=54.3773, format="%.4f")
        if st.button("Use Coordinates", type="primary"):
            st.session_state.latitude = lat_input
            st.session_state.longitude = lon_input
            st.session_state.location_name = f"Lat {lat_input}, Lon {lon_input}"
            st.success("Coordinates set")

    st.markdown("---")
    st.markdown("### 👁️ Observations")
    observations = st.multiselect(
        "Select any that apply",
        [
            "Water looks cloudy/murky",
            "Unusual smell",
            "Visible contamination",
            "Nearby flooding",
            "Dead fish/animals nearby",
            "Industrial discharge observed",
            "Sewage overflow",
        ],
    )
    additional_notes = st.text_area("Additional notes (optional)", placeholder="Any other observations or concerns…", height=80)

    st.markdown("---")
    left, right = st.columns([1, 1])
    with left:
        export_json = st.download_button(
            "⬇️ Export History (JSON)",
            data=json.dumps(st.session_state.history, indent=2),
            file_name="water_safety_history.json",
            mime="application/json",
            use_container_width=True,
        )
    with right:
        # CSV export
        df_export = pd.DataFrame(st.session_state.history) if st.session_state.history else pd.DataFrame()
        csv_bytes = df_export.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Export History (CSV)",
            data=csv_bytes,
            file_name="water_safety_history.csv",
            mime="text/csv",
            use_container_width=True,
        )

# ------------------------------------------------------------
# Main — Analyze / Results
# ------------------------------------------------------------
if "latitude" in st.session_state and "longitude" in st.session_state:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    colL, colR = st.columns([1.25, 2])

    with colL:
        st.markdown("#### Current Location")
        st.caption(st.session_state.location_name)
        st.map(pd.DataFrame({"lat": [st.session_state.latitude], "lon": [st.session_state.longitude]}))

        analyze = st.button("🔍 Analyze Water Safety", type="primary", use_container_width=True)

        if analyze:
            with st.spinner("Fetching weather and computing risk…"):
                weather_data = fetch_weather_data(st.session_state.latitude, st.session_state.longitude)
                if weather_data:
                    risk_score, risk_factors, risk_level = calculate_risk_score(weather_data, observations)
                    st.session_state.current_assessment = {
                        "weather_data": weather_data,
                        "risk_score": risk_score,
                        "risk_level": risk_level,
                        "risk_factors": risk_factors,
                        "timestamp": datetime.now(),
                    }
                    save_to_history(
                        st.session_state.location_name,
                        st.session_state.latitude,
                        st.session_state.longitude,
                        weather_data,
                        risk_score,
                        risk_level,
                        risk_factors,
                        observations,
                        additional_notes,
                    )
                    st.success("Analysis complete.")
                else:
                    st.error("Weather service unavailable. Try again shortly.")

    with colR:
        if "current_assessment" in st.session_state:
            assessment = st.session_state.current_assessment
            st.markdown(
                f"""<div class="badge {assessment['risk_level'].lower()}">● {assessment['risk_level']}</div>""",
                unsafe_allow_html=True,
            )
            st.caption(f"Last updated: {assessment['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")

            # Gauge + Metrics
            gcol, mcol = st.columns([1.1, 1.9])
            with gcol:
                st.plotly_chart(risk_gauge(assessment["risk_score"], assessment["risk_level"]), use_container_width=True)

            with mcol:
                st.markdown("##### Current Weather")
                current = assessment["weather_data"].get("current", {})
                st.markdown('<div class="metric-grid">', unsafe_allow_html=True)
                st.markdown(
                    f"""
                    <div class="metric">
                        <div style="font-size:.9rem;color:#6b7280;">Temperature</div>
                        <div style="font-size:1.4rem;font-weight:700;">{current.get('temperature_2m','N/A')}°C</div>
                    </div>
                    <div class="metric">
                        <div style="font-size:.9rem;color:#6b7280;">Humidity</div>
                        <div style="font-size:1.4rem;font-weight:700;">{current.get('relative_humidity_2m','N/A')}%</div>
                    </div>
                    <div class="metric">
                        <div style="font-size:.9rem;color:#6b7280;">Precipitation</div>
                        <div style="font-size:1.4rem;font-weight:700;">{current.get('precipitation',0)} mm</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.markdown("</div>", unsafe_allow_html=True)

            # Risk factors
            st.markdown("##### Risk Factors")
            if assessment["risk_factors"]:
                st.markdown(
                    '<div class="notice">' + "<br>".join([f"• {f}" for f in assessment["risk_factors"]]) + "</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.info("No significant risk factors detected.")

    st.markdown("</div>", unsafe_allow_html=True)  # end card

    # Recommendations
    if "current_assessment" in st.session_state:
        assessment = st.session_state.current_assessment
        rec = get_recommendations(assessment["risk_level"], assessment["risk_score"])
        st.markdown(
            f"""<div class="card callout {rec['color']}">""",
            unsafe_allow_html=True,
        )
        st.markdown(f"#### {rec['title']}")
        for a in rec["actions"]:
            st.markdown(f"- {a}")
        st.markdown("</div>", unsafe_allow_html=True)

        # Charts: Precip history (72h)
        hourly = assessment["weather_data"].get("hourly", {})
        if "precipitation" in hourly:
            st.markdown("#### 📈 Precipitation History (Last 72 Hours)")
            precip = hourly["precipitation"][-72:]
            df_precip = pd.DataFrame(
                {
                    "Hour": pd.date_range(
                        end=pd.Timestamp.now().floor("H"),
                        periods=len(precip),
                        freq="H",
                    ),
                    "Precipitation (mm)": precip,
                }
            ).set_index("Hour")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_precip.index, y=df_precip["Precipitation (mm)"], mode="lines"))
            fig.update_layout(
                height=300,
                margin=dict(l=10, r=10, t=20, b=10),
                yaxis_title="mm",
                xaxis_title="Time",
            )
            st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------
# History
# ------------------------------------------------------------
st.markdown("---")
st.markdown("### 📜 Assessment History")

if st.session_state.history:
    history_df = pd.DataFrame(st.session_state.history)
    history_df["timestamp"] = pd.to_datetime(history_df["timestamp"])
    history_df = history_df.sort_values("timestamp", ascending=False)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Checks", len(history_df))
    c2.metric("High Risk Days", int((history_df["risk_level"] == "Unsafe").sum()))
    c3.metric("Avg Risk Score", f"{history_df['risk_score'].mean():.1f}")
    c4.metric("Last Check", history_df["timestamp"].iloc[0].strftime("%Y-%m-%d"))

    # Recent list
    with st.expander("Show recent assessments", expanded=True):
        for _, row in history_df.head(10).iterrows():
            with st.container(border=True):
                top = st.columns([1.6, 1, 1, 1])
                top[0].markdown(f"**{row['timestamp'].strftime('%Y-%m-%d %H:%M')}** • {row['location']}")
                top[1].markdown(f"**Level:** {row['risk_level']}")
                top[2].markdown(f"**Score:** {row['risk_score']}")
                top[3].markdown(f"**Temp:** {row.get('temperature','–')}°C")
                st.caption("Risk factors: " + (", ".join(row["risk_factors"]) if row["risk_factors"] else "None"))
                if row.get("notes"):
                    st.caption(f"Notes: {row['notes']}")

    # Trend
    if len(history_df) > 1:
        st.markdown("#### 📊 Risk Score Trend")
        trend_df = history_df[["timestamp", "risk_score"]].sort_values("timestamp")
        fig_t = go.Figure()
        fig_t.add_trace(go.Scatter(x=trend_df["timestamp"], y=trend_df["risk_score"], mode="lines+markers"))
        fig_t.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10), yaxis_title="Risk Score", xaxis_title="Date")
        st.plotly_chart(fig_t, use_container_width=True)

    # Controls
    clear_col, space, prune_col = st.columns([1, 6, 2])
    with clear_col:
        if st.button("🗑️ Clear History", type="secondary", use_container_width=True):
            st.session_state.history = []
            if os.path.exists(HISTORY_FILE):
                os.remove(HISTORY_FILE)
            st.success("History cleared.")
            st.rerun()
    with prune_col:
        if st.button("🧹 Keep Last 10", use_container_width=True):
            st.session_state.history = st.session_state.history[:10]
            with open(HISTORY_FILE, "w") as f:
                json.dump(st.session_state.history, f, indent=2)
            st.success("Pruned to last 10 entries.")
else:
    st.info("No assessment history yet. Run your first analysis to start tracking.")

# ------------------------------------------------------------
# Footer
# ------------------------------------------------------------
st.markdown("---")
st.markdown(
    """
<div class="footer">
  <strong>Water Safety Monitor</strong> • Powered by Open-Meteo<br/>
  <span style='font-size:.9rem'>
  This tool provides risk assessments based on environmental factors. Always follow local water authority guidelines and official advisories.
  </span>
</div>
""",
    unsafe_allow_html=True,
)
