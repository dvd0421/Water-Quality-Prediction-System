import streamlit as st
import requests
import json
from datetime import datetime, timedelta
import pandas as pd
import plotly.graph_objects as go
from geopy.geocoders import Nominatim
import os

# Page configuration
st.set_page_config(
    page_title="Water Safety Monitor",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    /* General layout */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1100px;
    }

    /* Main header */
    .main-header {
        font-size: 2.8rem;
        font-weight: 800;
        text-align: center;
        color: #FFFFFF;
        margin-bottom: 1.5rem;
    }

    h2, h3, h4 {
        color: #FFFFFF;
        font-weight: 600;
    }

    /* Risk panels */
    .risk-safe, .risk-caution, .risk-unsafe {
        padding: 1.2rem 1.5rem;
        border-radius: 10px;
        margin: 1.2rem 0;
        color: #333;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    .risk-safe {
        background: linear-gradient(90deg, #eafaf1, #d4edda);
        border-left: 6px solid #28a745;
    }
    .risk-caution {
        background: linear-gradient(90deg, #fff8e1, #fff3cd);
        border-left: 6px solid #ffc107;
    }
    .risk-unsafe {
        background: linear-gradient(90deg, #fdecea, #f8d7da);
        border-left: 6px solid #dc3545;
    }

    /* Metric cards */
    div[data-testid="stMetricValue"] {
        font-size: 1.6rem;
        color: #0d6efd;
    }

    /* Buttons */
    div.stButton > button {
        background: linear-gradient(90deg, #1f77b4, #0d6efd);
        color: white;
        border: none;
        border-radius: 8px;
        font-size: 1rem;
        padding: 0.5rem 1rem;
        transition: 0.2s;
    }
    div.stButton > button:hover {
        transform: scale(1.02);
        background: linear-gradient(90deg, #0d6efd, #1f77b4);
    }

    /* Expander styling */
    details > summary {
        font-weight: 600;
        color: #0d6efd;
    }

    /* Footer */
    .footer {
        text-align: center;
        color: #777;
        padding: 2rem 0;
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)


# Data storage file
HISTORY_FILE = "water_safety_history.json"

# Initialize session state
if 'history' not in st.session_state:
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as f:
            st.session_state.history = json.load(f)
    else:
        st.session_state.history = []

if 'last_location' not in st.session_state:
    st.session_state.last_location = None

# Functions
def get_coordinates_from_city(city_name):
    """Convert city name to coordinates using geopy"""
    try:
        geolocator = Nominatim(user_agent="water_safety_monitor")
        location = geolocator.geocode(city_name)
        if location:
            return location.latitude, location.longitude, location.address
        return None, None, None
    except Exception as e:
        st.error(f"Error getting coordinates: {e}")
        return None, None, None

def fetch_weather_data(latitude, longitude):
    """Fetch weather data from Open-Meteo API"""
    try:
        url = f"https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,precipitation,rain,weather_code",
            "hourly": "precipitation,temperature_2m",
            "timezone": "auto",
            "past_days": 3
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching weather data: {e}")
        return None

def calculate_risk_score(weather_data, user_observations):
    """
    Calculate water contamination risk based on scientific factors
    
    Risk factors:
    - Heavy rainfall: increases runoff contamination
    - High temperature: accelerates bacterial growth
    - High humidity: creates conditions for microbial proliferation
    - Recent precipitation accumulation
    - User observations
    """
    risk_score = 0
    risk_factors = []
    
    if not weather_data:
        return 50, ["Unable to fetch weather data"], "Caution"
    
    current = weather_data.get('current', {})
    hourly = weather_data.get('hourly', {})
    
    # Temperature risk (optimal bacterial growth: 20-45°C)
    temp = current.get('temperature_2m', 0)
    if 20 <= temp <= 45:
        temp_risk = min(25, (temp - 20) / 25 * 25)
        risk_score += temp_risk
        risk_factors.append(f"Temperature ({temp}°C) in bacterial growth range")
    elif temp > 45:
        risk_score += 15
        risk_factors.append(f"Very high temperature ({temp}°C)")
    
    # Humidity risk (high humidity promotes bacterial growth)
    humidity = current.get('relative_humidity_2m', 0)
    if humidity > 70:
        humidity_risk = min(15, (humidity - 70) / 30 * 15)
        risk_score += humidity_risk
        risk_factors.append(f"High humidity ({humidity}%)")
    
    # Current precipitation
    current_rain = current.get('precipitation', 0) or current.get('rain', 0)
    if current_rain > 0:
        rain_risk = min(20, current_rain * 4)
        risk_score += rain_risk
        risk_factors.append(f"Active rainfall ({current_rain} mm)")
    
    # Calculate 24-hour and 72-hour precipitation accumulation
    if hourly and 'precipitation' in hourly:
        precip_data = hourly['precipitation'][-72:]  # Last 72 hours
        
        # 24-hour accumulation
        precip_24h = sum([p for p in precip_data[-24:] if p is not None])
        if precip_24h > 10:
            rain_24h_risk = min(25, (precip_24h - 10) / 40 * 25)
            risk_score += rain_24h_risk
            risk_factors.append(f"Heavy rain in last 24h ({precip_24h:.1f} mm)")
        elif precip_24h > 5:
            risk_score += 10
            risk_factors.append(f"Moderate rain in last 24h ({precip_24h:.1f} mm)")
        
        # 72-hour accumulation
        precip_72h = sum([p for p in precip_data if p is not None])
        if precip_72h > 50:
            risk_score += 15
            risk_factors.append(f"Prolonged rainfall over 3 days ({precip_72h:.1f} mm)")
    
    # User observation risks
    obs_risk_map = {
        "Water looks cloudy/murky": 15,
        "Unusual smell": 20,
        "Visible contamination": 25,
        "Nearby flooding": 20,
        "Dead fish/animals nearby": 25,
        "Industrial discharge observed": 30,
        "Sewage overflow": 35
    }
    
    for obs, risk_value in obs_risk_map.items():
        if obs in user_observations:
            risk_score += risk_value
            risk_factors.append(f"Observation: {obs}")
    
    # Cap risk score at 100
    risk_score = min(100, risk_score)
    
    # Determine risk level
    if risk_score < 30:
        risk_level = "Safe"
    elif risk_score < 60:
        risk_level = "Caution"
    else:
        risk_level = "Unsafe"
    
    return risk_score, risk_factors, risk_level

def get_recommendations(risk_level, risk_score):
    """Provide safety recommendations based on risk level"""
    recommendations = {
        "Safe": {
            "title": "✅ Water Appears Safe",
            "actions": [
                "Water quality indicators are within normal parameters",
                "Standard water usage is acceptable",
                "Continue monitoring conditions regularly",
                "Follow local water authority guidelines"
            ],
            "color": "safe"
        },
        "Caution": {
            "title": "⚠️ Exercise Caution",
            "actions": [
                "**Boil water for at least 1 minute before drinking**",
                "Use bottled water for drinking and cooking if available",
                "Wash hands thoroughly after water contact",
                "Monitor for any health symptoms",
                "Avoid using water for infant formula preparation",
                "Check with local water authorities for updates"
            ],
            "color": "caution"
        },
        "Unsafe": {
            "title": "🚫 Water Quality Alert - High Risk",
            "actions": [
                "**DO NOT drink tap water**",
                "Use only bottled or commercially treated water",
                "Avoid water contact with open wounds",
                "Do not use for cooking, brushing teeth, or ice making",
                "Boiling may not remove all contaminants",
                "Contact local health authorities immediately",
                "Consider evacuation if contamination is severe",
                "Monitor official advisories closely"
            ],
            "color": "unsafe"
        }
    }
    
    rec = recommendations.get(risk_level, recommendations["Caution"])
    
    # Add risk score context
    if risk_score >= 80:
        rec["actions"].insert(0, "⚠️ **CRITICAL**: Risk score is very high - take immediate action")
    
    return rec

def save_to_history(location_name, lat, lon, weather_data, risk_score, risk_level, risk_factors, observations):
    """Save assessment to history"""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "location": location_name,
        "latitude": lat,
        "longitude": lon,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_factors": risk_factors,
        "observations": observations,
        "temperature": weather_data.get('current', {}).get('temperature_2m'),
        "humidity": weather_data.get('current', {}).get('relative_humidity_2m'),
        "precipitation": weather_data.get('current', {}).get('precipitation', 0)
    }
    
    st.session_state.history.append(entry)
    
    # Keep only last 30 days
    cutoff_date = datetime.now() - timedelta(days=30)
    st.session_state.history = [
        h for h in st.session_state.history 
        if datetime.fromisoformat(h['timestamp']) > cutoff_date
    ]
    
    # Save to file
    with open(HISTORY_FILE, 'w') as f:
        json.dump(st.session_state.history, f)

def display_risk_gauge(risk_score, risk_level):
    """Create a gauge chart for risk visualization"""
    colors = {
        "Safe": "#28a745",
        "Caution": "#ffc107",
        "Unsafe": "#dc3545"
    }
    
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=risk_score,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': f"Risk Score: {risk_level}", 'font': {'size': 24}},
        delta={'reference': 30},
        gauge={
            'axis': {'range': [None, 100], 'tickwidth': 1, 'tickcolor': "darkgray"},
            'bar': {'color': colors[risk_level]},
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [0, 30], 'color': '#d4edda'},
                {'range': [30, 60], 'color': '#fff3cd'},
                {'range': [60, 100], 'color': '#f8d7da'}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': 90
            }
        }
    ))
    
    fig.update_layout(
        paper_bgcolor="white",
        font={'color': "darkgray", 'family': "Arial"},
        height=300
    )
    
    return fig

# Main App
st.markdown('<h1 class="main-header">Water Safety Monitor</h1>', unsafe_allow_html=True)
st.info("💡 Assess environmental and weather-based water contamination risk in real time.")

# Optional decorative icon row
col_left, col_right = st.columns([1.5, 1])
with col_left:
    st.header("📊 Current Risk Assessment Overview")
with col_right:
    st.image("https://static.vecteezy.com/system/resources/previews/000/579/853/original/water-drop-logo-template-vector.jpg", width=250)

# Sidebar - Location Input
st.sidebar.markdown("### ⚙️ Configuration")
st.sidebar.divider()
st.sidebar.markdown("### 🧭 Location Input")


location_method = st.sidebar.radio(
    "Choose location method:",
    ["Enter City Name", "Enter Coordinates"]
)

if location_method == "Enter City Name":
    city_name = st.sidebar.text_input(
        "City Name",
        value=st.session_state.last_location if st.session_state.last_location else "",
        placeholder="e.g., Abu Dhabi, London, New York"
    )
    
    if st.sidebar.button("Get Location", type="primary"):
        if city_name:
            with st.spinner("Getting coordinates..."):
                lat, lon, address = get_coordinates_from_city(city_name)
                if lat and lon:
                    st.session_state.latitude = lat
                    st.session_state.longitude = lon
                    st.session_state.location_name = address
                    st.session_state.last_location = city_name
                    st.sidebar.success(f"✅ Location found: {address}")
                else:
                    st.sidebar.error("Could not find location. Please try again.")
        else:
            st.sidebar.warning("Please enter a city name")
else:
    col1, col2 = st.sidebar.columns(2)
    lat_input = col1.number_input("Latitude", value=24.4539, format="%.4f")
    lon_input = col2.number_input("Longitude", value=54.3773, format="%.4f")
    
    if st.sidebar.button("Use Coordinates", type="primary"):
        st.session_state.latitude = lat_input
        st.session_state.longitude = lon_input
        st.session_state.location_name = f"Lat: {lat_input}, Lon: {lon_input}"
        st.sidebar.success("✅ Coordinates set")

# User Observations
st.sidebar.header("👁️ Water Observations")
observations = st.sidebar.multiselect(
    "Select any observations:",
    [
        "Water looks cloudy/murky",
        "Unusual smell",
        "Visible contamination",
        "Nearby flooding",
        "Dead fish/animals nearby",
        "Industrial discharge observed",
        "Sewage overflow"
    ]
)

additional_notes = st.sidebar.text_area(
    "Additional notes (optional)",
    placeholder="Any other observations or concerns..."
)

# Main content
if 'latitude' in st.session_state and 'longitude' in st.session_state:
    st.info(f"📍 Current Location: {st.session_state.location_name}")
    
    if st.button("🔍 Analyze Water Safety", type="primary", use_container_width=True):
        with st.spinner("Fetching weather data and analyzing risk..."):
            # Fetch weather data
            weather_data = fetch_weather_data(
                st.session_state.latitude,
                st.session_state.longitude
            )
            
            if weather_data:
                # Calculate risk
                risk_score, risk_factors, risk_level = calculate_risk_score(
                    weather_data,
                    observations
                )
                
                # Store in session state
                st.session_state.current_assessment = {
                    'weather_data': weather_data,
                    'risk_score': risk_score,
                    'risk_level': risk_level,
                    'risk_factors': risk_factors,
                    'timestamp': datetime.now()
                }
                
                # Save to history
                save_to_history(
                    st.session_state.location_name,
                    st.session_state.latitude,
                    st.session_state.longitude,
                    weather_data,
                    risk_score,
                    risk_level,
                    risk_factors,
                    observations
                )
                
                st.success("✅ Analysis complete!")
    
    # Display current assessment
    if 'current_assessment' in st.session_state:
        assessment = st.session_state.current_assessment
        
        st.markdown("---")
        st.header("📊 Current Risk Assessment")
        
        # Display timestamp
        st.caption(f"Last updated: {assessment['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Risk gauge
        col1, col2 = st.columns([1, 2])
        
        with col1:
            fig = display_risk_gauge(assessment['risk_score'], assessment['risk_level'])
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Weather metrics
            st.subheader("🌤️ Current Weather Conditions")
            current = assessment['weather_data'].get('current', {})
            
            metric_col1, metric_col2, metric_col3 = st.columns(3)
            metric_col1.metric(
                "Temperature",
                f"{current.get('temperature_2m', 'N/A')}°C"
            )
            metric_col2.metric(
                "Humidity",
                f"{current.get('relative_humidity_2m', 'N/A')}%"
            )
            metric_col3.metric(
                "Precipitation",
                f"{current.get('precipitation', 0)} mm"
            )
            
            # Risk factors
            st.subheader("⚠️ Risk Factors Detected")
            if assessment['risk_factors']:
                for factor in assessment['risk_factors']:
                    st.markdown(f"• {factor}")
            else:
                st.success("No significant risk factors detected")
        
        # Recommendations
        st.markdown("---")
        recommendations = get_recommendations(
            assessment['risk_level'],
            assessment['risk_score']
        )
        
        st.markdown(f'<div class="risk-{recommendations["color"]}">', unsafe_allow_html=True)
        st.subheader(recommendations['title'])
        for action in recommendations['actions']:
            st.markdown(f"• {action}")
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Precipitation chart
        if 'hourly' in assessment['weather_data'] and 'precipitation' in assessment['weather_data']['hourly']:
            st.markdown("---")
            st.subheader("📈 Precipitation History (Last 72 Hours)")
            
            hourly_data = assessment['weather_data']['hourly']
            precip = hourly_data['precipitation'][-72:]
            
            df_precip = pd.DataFrame({
                'Hour': range(len(precip)),
                'Precipitation (mm)': precip
            })
            
            st.line_chart(df_precip.set_index('Hour'))

# History View
st.markdown("---")
st.header("📜 Assessment History")

if st.session_state.history:
    # Convert to DataFrame
    history_df = pd.DataFrame(st.session_state.history)
    history_df['timestamp'] = pd.to_datetime(history_df['timestamp'])
    history_df = history_df.sort_values('timestamp', ascending=False)
    
    # Summary statistics
    col1, col2, col3, col4 = st.columns(4)
    
    col1.metric("Total Checks", len(history_df))
    col2.metric(
        "High Risk Days",
        len(history_df[history_df['risk_level'] == 'Unsafe'])
    )
    col3.metric(
        "Avg Risk Score",
        f"{history_df['risk_score'].mean():.1f}"
    )
    col4.metric(
        "Last Check",
        history_df['timestamp'].iloc[0].strftime('%m/%d')
    )
    
    # Show recent history
    st.subheader("Recent Assessments")
    
    for idx, row in history_df.head(10).iterrows():
        risk_class = {
            'Safe': 'safe',
            'Caution': 'caution',
            'Unsafe': 'unsafe'
        }[row['risk_level']]
        
        with st.expander(
            f"{row['timestamp'].strftime('%Y-%m-%d %H:%M')} - "
            f"{row['location']} - "
            f"{row['risk_level']} (Score: {row['risk_score']})"
        ):
            col1, col2 = st.columns(2)
            
            with col1:
                st.write(f"**Risk Level:** {row['risk_level']}")
                st.write(f"**Risk Score:** {row['risk_score']}")
                st.write(f"**Temperature:** {row['temperature']}°C")
                st.write(f"**Humidity:** {row['humidity']}%")
            
            with col2:
                st.write("**Risk Factors:**")
                for factor in row['risk_factors']:
                    st.write(f"• {factor}")
    
    # Risk trend chart
    if len(history_df) > 1:
        st.subheader("📊 Risk Score Trend")
        
        trend_df = history_df[['timestamp', 'risk_score']].copy()
        trend_df = trend_df.sort_values('timestamp')
        
        st.line_chart(trend_df.set_index('timestamp'))
    
    # Clear history button
    if st.button("🗑️ Clear History", type="secondary"):
        st.session_state.history = []
        if os.path.exists(HISTORY_FILE):
            os.remove(HISTORY_FILE)
        st.success("History cleared!")
        st.rerun()
else:
    st.info("No assessment history yet. Perform your first analysis to start tracking data.")

# Footer
st.markdown("""
<div class='footer'>
    <strong>💧 Water Safety Monitor</strong><br>
    <span>Powered by Open-Meteo API | Built with Streamlit</span><br>
    <small>⚠️ For informational purposes only. Follow official water safety advisories.</small>
</div>
""", unsafe_allow_html=True)










