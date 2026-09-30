import base64
import csv
from datetime import datetime
import io
import json
import os
import re
from PIL import Image, ImageEnhance, ImageOps
import requests
import streamlit as st
import streamlit.components.v1 as components
import zxingcpp

st.set_page_config(
    page_title="Test Don't Guess", page_icon="⚡", layout="wide"
)

# Header with custom ignition firing line scope waveform
firing_line_svg = """
<div style="display: flex; align-items: center; gap: 14px; margin-bottom: 1.5rem;">
  <svg width="65" height="42" viewBox="0 0 120 70" fill="none" xmlns="http://www.w3.org/2000/svg" style="vertical-align: middle;">
    <!-- Dwell, Firing Line Spike, Spark Burn Line, and Coil Ringing -->
    <path d="M 5 45 L 22 45 L 24 60 L 42 60 L 43 5 L 46 36 Q 48 34 54 36 T 64 36 T 74 35 T 80 36 Q 84 18 88 50 Q 92 24 96 44 Q 100 32 104 42 L 118 42" 
          stroke="#00FF66" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" 
          style="filter: drop-shadow(0px 0px 5px #00FF66);"/>
  </svg>
  <h1 style="margin: 0; padding: 0; font-size: 2.2rem; font-weight: 700;">Test Don't Guess</h1>
</div>
"""
st.markdown(firing_line_svg, unsafe_allow_html=True)

# Read query parameters from Web Bluetooth bridge redirect
if "ble_vin" in st.query_params and st.query_params["ble_vin"]:
  st.session_state.active_vin = st.query_params["ble_vin"].upper().strip()
if "ble_dtc" in st.query_params and st.query_params["ble_dtc"]:
  st.session_state.active_dtc = st.query_params["ble_dtc"].upper().strip()

# Persistent session state across tabs
if "vehicle_info" not in st.session_state:
  st.session_state.vehicle_info = ""
if "active_vin" not in st.session_state:
  st.session_state.active_vin = ""
if "active_dtc" not in st.session_state:
  st.session_state.active_dtc = ""
if "customer_name" not in st.session_state:
  st.session_state.customer_name = ""
if "customer_address" not in st.session_state:
  st.session_state.customer_address = ""
if "customer_phone" not in st.session_state:
  st.session_state.customer_phone = ""
if "chat_history" not in st.session_state:
  st.session_state.chat_history = []

LOG_FILE = "scan_history.csv"


# --- LOGGING HELPER FUNCTIONS ---
def append_to_log(
    vin: str, vehicle: str, dtc: str, customer: str = "", phone: str = ""
):
  file_exists = os.path.isfile(LOG_FILE)
  timestamp = datetime.now().strftime("%Y-%m-%d %I:%M %p")
  try:
    with open(LOG_FILE, mode="a", newline="", encoding="utf-8") as f:
      writer = csv.writer(f)
      if not file_exists:
        writer.writerow([
            "Timestamp",
            "Customer",
            "Phone",
            "VIN",
            "Vehicle",
            "Fault Code (DTC)",
        ])
      writer.writerow([
          timestamp,
          customer or "N/A",
          phone or "N/A",
          vin or "N/A",
          vehicle or "Unknown Vehicle",
          dtc or "N/A",
      ])
  except Exception:
    pass


def load_log():
  if not os.path.isfile(LOG_FILE):
    return []
  rows = []
  try:
    with open(LOG_FILE, mode="r", encoding="utf-8") as f:
      reader = csv.DictReader(f)
      for r in reader:
        rows.append(r)
  except Exception:
    return []
  return rows[::-1]


# --- GEMINI HELPERS ---
def get_gemini_key() -> str:
  key = os.environ.get("GEMINI_API_KEY")
  if not key and hasattr(st, "secrets"):
    key = st.secrets.get("GEMINI_API_KEY")
  return key or ""


def query_gemini(prompt_text: str, system_instruction: str = "") -> str:
  gemini_key = get_gemini_key()
  if not gemini_key:
    return "Error: GEMINI_API_KEY is missing from Streamlit Secrets."

  url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
  payload = {"contents": [{"parts": [{"text": prompt_text}]}]}
  if system_instruction:
    payload["system_instruction"] = {
        "parts": [{"text": system_instruction}]
    }

  try:
    res = requests.post(url, json=payload, timeout=45)
    if res.status_code == 200:
      return res.json()["candidates"][0]["content"]["parts"][0]["text"]
    else:
      return f"Gemini API Error ({res.status_code}): {res.text}"
  except Exception as e:
    return f"Gemini Error: {e}"


def analyze_scope_with_gemini(
    pil_img: Image.Image | None, test_summary: str
) -> str:
  gemini_key = get_gemini_key()
  if not gemini_key:
    return "Error: GEMINI_API_KEY is missing from Streamlit Secrets."

  prompt = f"""
You are an expert ASE Master / L1 diagnostic technician and automotive oscilloscope waveform specialist.
Analyze this oscilloscope or multimeter capture alongside physical shop test readings.

TEST CONTEXT:
{test_summary}

SCOPE / METER VISION TASK:
- Identify signal type (Secondary/Primary Ignition, Injector Voltage/Current, CKP/CMP correlation, Relative Compression, PWM, Sensor drop).
- Evaluate critical electrical signatures: peak firing/inductive spike kV, dwell duration, spark burn line slope & turbulence, coil oscillation count, ground bounce, signal attenuation, or missing-tooth spacing.
- Correlate waveform abnormalities directly with physical test readings.

FORMAT STRICTLY AS:
### 1. Scope Waveform & Electrical Findings
- Key observations, time-base/voltage scale notes, circuit anomalies observed in photo.
### 2. Component Condemnation & Defect Root Cause
- What exact component, circuit, or mechanical issue is failing.
### 3. Immediate Pinpoint Verification Step
- The single next test to 100% isolate and verify before condemning the part.
"""
  parts = [{"text": prompt}]

  if pil_img is not None:
    try:
      buffered = io.BytesIO()
      pil_img.convert("RGB").save(buffered, format="JPEG", quality=85)
      img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
      parts.append(
          {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
      )
    except Exception as e:
      return f"Image processing error: {e}"

  url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
  payload = {"contents": [{"parts": parts}]}

  try:
    res = requests.post(url, json=payload, timeout=45)
    if res.status_code == 200:
      return res.json()["candidates"][0]["content"]["parts"][0]["text"]
    else:
      return f"Gemini Vision Error ({res.status_code}): {res.text}"
  except Exception as e:
    return f"Scope Analysis Error: {e}"


def extract_vin_via_ai(pil_img: Image.Image) -> str:
  gemini_key = get_gemini_key()
  if not gemini_key:
    return ""

  try:
    buffered = io.BytesIO()
    pil_img.convert("RGB").save(buffered, format="JPEG", quality=85)
    img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
    payload = {
        "contents": [{
            "parts": [
                {
                    "text": (
                        "Locate and extract the 17-character Vehicle"
                        " Identification Number (VIN) from this vehicle image."
                        " Standard VINs only use digits and uppercase letters"
                        " excluding I, O, and Q. Return ONLY the 17-character"
                        " VIN. If none is found, return 'NONE'."
                    )
                },
                {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}},
            ]
        }]
    }

    res = requests.post(url, json=payload, timeout=20)
    if res.status_code == 200:
      raw_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
      match = re.search(r"[A-HJ-NPR-Z0-9]{17}", raw_text.upper())
      if match:
        return match.group(0)
  except Exception:
    pass
  return ""


def extract_customer_info(pil_img: Image.Image) -> dict:
  gemini_key = get_gemini_key()
  if not gemini_key:
    return {
        "error": "GEMINI_API_KEY is missing from Streamlit Secrets."
    }

  buffered = io.BytesIO()
  pil_img.convert("RGB").save(buffered, format="JPEG", quality=85)
  img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

  url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
  payload = {
      "contents": [{
          "parts": [
              {
                  "text": (
                      "Read this work order / invoice image. Extract ONLY: 1)"
                      " Customer Name, 2) Address, 3) Phone Number. Return"
                      " strictly a valid JSON object with keys:"
                      " 'customer_name', 'address', 'phone'. Do not include"
                      " markdown formatting."
                  )
              },
              {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}},
          ]
      }],
      "generationConfig": {"response_mime_type": "application/json"},
  }

  try:
    res = requests.post(url, json=payload, timeout=20)
    if res.status_code == 200:
      raw_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
      return json.loads(raw_text)
    else:
      return {"error": f"Vision API Error ({res.status_code}): {res.text}"}
  except Exception as e:
    return {"error": f"Failed to extract info: {e}"}


# --- PERPLEXITY AGENT API HELPER ---
def query_perplexity(prompt_text: str, preset: str = "low") -> str:
  api_key = os.environ.get("PERPLEXITY_API_KEY")
  if not api_key and hasattr(st, "secrets"):
    api_key = st.secrets.get("PERPLEXITY_API_KEY")

  if not api_key:
    return "Error: PERPLEXITY_API_KEY is not configured in Streamlit Secrets."

  headers = {
      "Authorization": f"Bearer {api_key}",
      "Content-Type": "application/json",
  }
  payload = {"preset": preset, "input": prompt_text}

  try:
    res = requests.post(
        "https://api.perplexity.ai/v1/responses",
        headers=headers,
        json=payload,
        timeout=60,
    )
    if res.status_code == 200:
      data = res.json()
      if "output_text" in data:
        return data["output_text"]
      elif "output" in data:
        text = ""
        for item in data["output"]:
          if item.get("type") == "message":
            for c in item.get("content", []):
              if "text" in c:
                text += c["text"]
        return text or "No response text received."
      return "No message content found in API output."
    else:
      return f"API Error ({res.status_code}): {res.text}"
  except requests.exceptions.Timeout:
    return "Request timed out. Please try again."
  except Exception as e:
    return f"Unexpected error: {e}"


def scan_vin_barcode(pil_img: Image.Image) -> str:
  barcodes = zxingcpp.read_barcodes(
      pil_img, try_rotate=True, try_downscale=True, try_invert=True
  )
  for b in barcodes:
    match = re.search(r"[A-HJ-NPR-Z0-9]{17}", b.text.upper())
    if match:
      return match.group(0)

  gray = ImageOps.grayscale(pil_img)
  high_contrast = ImageEnhance.Contrast(gray).enhance(2.2)
  barcodes = zxingcpp.read_barcodes(
      high_contrast, try_rotate=True, try_downscale=True, try_invert=True
  )
  for b in barcodes:
    match = re.search(r"[A-HJ-NPR-Z0-9]{17}", b.text.upper())
    if match:
      return match.group(0)

  return ""


def decode_vin(vin_code: str) -> dict | None:
  url = (
      f"https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/{vin_code}?format=json"
  )
  try:
    response = requests.get(url, timeout=10).json()
    details = {}
    for item in response.get("Results", []):
      if item.get("Value") and item.get("Variable") in [
          "Model Year",
          "Make",
          "Model",
          "Displacement (L)",
          "Engine Number of Cylinders",
          "Fuel Type - Primary",
          "Drive Type",
          "Vehicle Type",
      ]:
        details[item["Variable"]] = item["Value"]
    return details
  except Exception:
    return None


tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📷 VIN & Customer Info",
    "📊 Live Telemetry, Mode $06 & Monitors",
    "🔧 In-Depth Diagnostic Strategy",
    "⚡ Copilot & Scope Lab",
    "📋 Vehicle & DTC Log",
])

# ========================================================
# --- TAB 1: VIN & CUSTOMER INFO ---
# ========================================================
with tab1:
  st.subheader("Customer & Vehicle Identification")

  st.markdown("#### 👤 Customer Information")
  col_c1, col_c2 = st.columns([1, 1])
  with col_c1:
    cust_name = st.text_input(
        "Customer Name:",
        value=st.session_state.customer_name,
        placeholder="e.g. ROTAE LLC",
    )
    cust_phone = st.text_input(
        "Phone Number:",
        value=st.session_state.customer_phone,
        placeholder="e.g. 678-365-2146",
    )
  with col_c2:
    cust_address = st.text_area(
        "Address:",
        value=st.session_state.customer_address,
        placeholder="e.g. 6428 DAWSON BLVD, STE 1730, NORCROSS, GA, 30093",
        height=108,
    )

  st.session_state.customer_name = cust_name.strip()
  st.session_state.customer_phone = cust_phone.strip()
  st.session_state.customer_address = cust_address.strip()

  st.write("---")
  st.markdown("#### 📸 Camera / Photo VIN Scanner")

  col_cam, col_up = st.columns([1, 1])
  with col_cam:
    open_camera = st.toggle("📷 Open Camera", value=False)
    photo = None
    if open_camera:
      photo = st.camera_input("Snap VIN sticker, plate, or paperwork")

  with col_up:
    uploaded_label = st.file_uploader(
        "Or upload photo from phone gallery",
        type=["png", "jpg", "jpeg"],
        key="vin_upload",
    )

  active_image = photo or uploaded_label
  found_vin = ""

  if active_image:
    st.image(active_image, caption="Captured Image", use_container_width=True)
    img = Image.open(active_image)

    found_vin = scan_vin_barcode(img)
    detection_method = "Barcode"

    if not found_vin:
      with st.spinner("Scanning photo text with AI Vision for 17-digit VIN..."):
        found_vin = extract_vin_via_ai(img)
        detection_method = "AI Photo Text Recognition"

    if found_vin:
      st.session_state.active_vin = found_vin
      st.success(f"VIN Detected ({detection_method})! **{found_vin}**")
    else:
      st.warning("Could not detect a 17-digit VIN. Enter manually below.")

    if st.button("📄 Extract Customer Details from this Image"):
      with st.spinner("Extracting customer name, address, and phone..."):
        c_info = extract_customer_info(img)
        if "error" in c_info:
          st.error(c_info["error"])
        else:
          if c_info.get("customer_name"):
            st.session_state.customer_name = c_info["customer_name"]
          if c_info.get("address"):
            st.session_state.customer_address = c_info["address"]
          if c_info.get("phone"):
            st.session_state.customer_phone = c_info["phone"]
          st.success("Customer info updated!")
          st.rerun()

  vin = st.text_input(
      "Vehicle VIN (17 digits):",
      value=found_vin or st.session_state.active_vin,
      max_chars=17,
  )
  active_vin = vin.strip().upper()

  if active_vin and (found_vin or st.button("Decode VIN")):
    st.session_state.active_vin = active_vin
    details = decode_vin(active_vin)
    if details:
      year = details.get("Model Year", "")
      make = details.get("Make", "")
      model = details.get("Model", "")
      disp = details.get("Displacement (L)", "")
      st.session_state.vehicle_info = f"{year} {make} {model} ({disp}L)"

      st.subheader(f"Vehicle Specifications ({active_vin})")
      col1, col2 = st.columns(2)
      for i, (key, val) in enumerate(details.items()):
        if i % 2 == 0:
          col1.write(f"**{key}:** {val}")
        else:
          col2.write(f"**{key}:** {val}")
    else:
      st.error("Could not find vehicle details. Check the VIN and try again.")

# ========================================================
# --- TAB 2: LIVE TELEMETRY, ENHANCED PIDS, MONITORS & MODE 06 ---
# ========================================================
with tab2:
  st.subheader("📊 Live Telemetry, OEM Enhanced PIDs & Monitors")

  c_tag = st.session_state.customer_name or "None"
  v_tag = st.session_state.vehicle_info or "No Vehicle Selected"
  d_tag = st.session_state.active_dtc or "None Specified"
  st.info(
      f"📋 **Context:** Customer: `{c_tag}` | Vehicle: `{v_tag}` | Active"
      f" DTC: `{d_tag}`"
  )

  gemini_api_key = get_gemini_key()

  # Identify auto-detected vehicle make for enhanced DID routing
  detected_make = "GENERIC"
  if st.session_state.vehicle_info:
    v_upper = st.session_state.vehicle_info.upper()
    if any(m in v_upper for m in ["FORD", "LINCOLN", "MERCURY"]):
      detected_make = "FORD"
    elif any(
        m in v_upper for m in ["CHEVROLET", "CHEVY", "GMC", "CADILLAC", "BUICK"]
    ):
      detected_make = "GM"
    elif any(m in v_upper for m in ["TOYOTA", "LEXUS", "SCION"]):
      detected_make = "TOYOTA"
    elif any(
        m in v_upper for m in ["CHRYSLER", "DODGE", "JEEP", "RAM", "PLYMOUTH"]
    ):
      detected_make = "CHRYSLER"

  ble_dashboard_template = """
    <div style="background-color: #1A1F26; border: 1px solid #00FF66; padding: 14px; border-radius: 8px; margin-bottom: 1rem;">
        <!-- Action & Utility Bar -->
        <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 10px;">
            <button id="bleBtn" style="background-color: #00FF66; color: #0E1117; font-weight: 700; font-size: 0.95rem; border: none; padding: 10px 18px; border-radius: 5px; cursor: pointer; display: flex; align-items: center; gap: 6px;">
                <span>⚡</span> Connect & Auto-Scan
            </button>
            <button id="pauseBtn" disabled style="background-color: #2D3748; color: #718096; font-weight: 700; font-size: 0.9rem; border: 1px solid #4A5568; padding: 9px 15px; border-radius: 5px; cursor: not-allowed;">
                ⏸️ Pause Stream
            </button>
            <button id="testDriveBtn" disabled style="background-color: #2D3748; color: #718096; font-weight: 700; font-size: 0.9rem; border: 1px solid #4A5568; padding: 9px 15px; border-radius: 5px; cursor: not-allowed;">
                🚗 Test Drive Audio
            </button>
            <button id="clearDtcBtn" disabled style="background-color: #2D3748; color: #718096; font-weight: 700; font-size: 0.9rem; border: 1px solid #4A5568; padding: 9px 15px; border-radius: 5px; cursor: not-allowed;">
                🗑️ Clear DTCs (Mode 04)
            </button>
            <button id="aiCheckBtn" disabled style="background-color: #2D3748; color: #718096; font-weight: 700; font-size: 0.9rem; border: 1px solid #4A5568; padding: 9px 15px; border-radius: 5px; cursor: not-allowed;">
                🤖 AI Check Now
            </button>
            <button id="pullVinBtn" disabled style="background-color: #2D3748; color: #718096; font-weight: 700; font-size: 0.9rem; border: 1px solid #4A5568; padding: 9px 15px; border-radius: 5px; cursor: not-allowed;">
                📋 Sync VIN & DTCs
            </button>
            
            <div style="margin-left: auto; display: flex; align-items: center; gap: 6px;">
                <span style="font-size: 0.8rem; color: #A0AEC0;">OEM Profile:</span>
                <select id="oemProfileSelect" style="background: #111418; color: #00FF66; border: 1px solid #00FF66; padding: 6px 10px; border-radius: 4px; font-weight: 700; font-size: 0.85rem;">
                    <option value="AUTO">Auto-Detect</option>
                    <option value="FORD">Ford / Lincoln</option>
                    <option value="GM">GM / Chevrolet / GMC</option>
                    <option value="TOYOTA">Toyota / Lexus</option>
                    <option value="CHRYSLER">Chrysler / Dodge / Jeep</option>
                    <option value="GENERIC">Standard Generic</option>
                </select>
            </div>
        </div>
        <div id="bleStatus" style="color: #A0AEC0; font-family: monospace; font-size: 0.85rem; margin-bottom: 12px;">Status: Ready to pair. Tap "Connect & Auto-Scan" to auto-load Monitors, Mode $06, and start live telemetry.</div>

        <!-- TEST DRIVE AI ACTIVE BANNER -->
        <div id="driveBanner" style="display: none; background: #0F172A; border-left: 4px solid #38BDF8; padding: 8px 12px; border-radius: 4px; margin-bottom: 12px; font-size: 0.85rem; color: #38BDF8;">
            🚗 <strong>Test Drive AI Active:</strong> Screen Wake Lock ON (screen will not sleep). Real-time speech alerts active for Fuel Trim skews, thermal spikes, or misfires.
        </div>

        <!-- 1. LIVE SENSOR TELEMETRY (TOP) -->
        <div style="font-weight: 700; font-size: 0.95rem; color: #00FF66; margin-bottom: 6px;">📈 LIVE SENSOR TELEMETRY (MODE 01)</div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(115px, 1fr)); gap: 8px; max-height: 280px; overflow-y: auto; padding-right: 4px; margin-bottom: 16px;">
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Engine RPM</div>
                <div id="valRpm" style="font-size: 1.15rem; font-weight: 700; color: #00FF66;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Engine Load</div>
                <div id="valLoad" style="font-size: 1.15rem; font-weight: 700; color: #38BDF8;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Vehicle Speed</div>
                <div id="valSpd" style="font-size: 1.15rem; font-weight: 700; color: #38BDF8;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Throttle (TPS)</div>
                <div id="valTps" style="font-size: 1.15rem; font-weight: 700; color: #E2E8F0;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Pedal Pos (APP)</div>
                <div id="valApp" style="font-size: 1.15rem; font-weight: 700; color: #E2E8F0;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Coolant (ECT)</div>
                <div id="valEct" style="font-size: 1.15rem; font-weight: 700; color: #F59E0B;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Intake Air (IAT)</div>
                <div id="valIat" style="font-size: 1.15rem; font-weight: 700; color: #F59E0B;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Ambient Temp</div>
                <div id="valAat" style="font-size: 1.15rem; font-weight: 700; color: #F59E0B;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Oil Temp</div>
                <div id="valEot" style="font-size: 1.15rem; font-weight: 700; color: #F59E0B;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">MAP Sensor</div>
                <div id="valMap" style="font-size: 1.15rem; font-weight: 700; color: #00FF66;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">MAF Flow</div>
                <div id="valMaf" style="font-size: 1.15rem; font-weight: 700; color: #00FF66;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Baro Press</div>
                <div id="valBaro" style="font-size: 1.15rem; font-weight: 700; color: #64748B;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Fuel Rail Press</div>
                <div id="valFrp" style="font-size: 1.15rem; font-weight: 700; color: #10B981;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Fuel Level %</div>
                <div id="valFli" style="font-size: 1.15rem; font-weight: 700; color: #10B981;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">STFT Bank 1</div>
                <div id="valStft" style="font-size: 1.15rem; font-weight: 700; color: #FBBF24;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">LTFT Bank 1</div>
                <div id="valLtft" style="font-size: 1.15rem; font-weight: 700; color: #FBBF24;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">STFT Bank 2</div>
                <div id="valStft2" style="font-size: 1.15rem; font-weight: 700; color: #FBBF24;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">LTFT Bank 2</div>
                <div id="valLtft2" style="font-size: 1.15rem; font-weight: 700; color: #FBBF24;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Ign Timing</div>
                <div id="valTime" style="font-size: 1.15rem; font-weight: 700; color: #EC4899;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div id="lblO21" style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">O2 B1S1 (A/F)</div>
                <div id="valO21" style="font-size: 1.15rem; font-weight: 700; color: #A855F7;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">O2 B1S2 (V)</div>
                <div id="valO22" style="font-size: 1.15rem; font-weight: 700; color: #A855F7;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div id="lblO221" style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">O2 B2S1 (A/F)</div>
                <div id="valO221" style="font-size: 1.15rem; font-weight: 700; color: #A855F7;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">O2 B2S2 (V)</div>
                <div id="valO222" style="font-size: 1.15rem; font-weight: 700; color: #A855F7;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Evap Purge %</div>
                <div id="valEvap" style="font-size: 1.15rem; font-weight: 700; color: #E2E8F0;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Battery Volt</div>
                <div id="valVolt" style="font-size: 1.15rem; font-weight: 700; color: #E2E8F0;">--</div>
            </div>
        </div>

        <!-- 2. OEM ENHANCED PIDS (UDS SERVICE 0x22) -->
        <div style="font-weight: 700; font-size: 0.95rem; color: #EC4899; margin-bottom: 6px;">🏭 OEM ENHANCED PIDS (UDS 0x22 PROPRIETARY DATA)</div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 8px; max-height: 180px; overflow-y: auto; padding-right: 4px; margin-bottom: 16px;">
            <div style="background: #111418; border: 1px solid #EC4899; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Trans Fluid Temp</div>
                <div id="valTft" style="font-size: 1.15rem; font-weight: 700; color: #EC4899;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #EC4899; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Engine Oil Press</div>
                <div id="valEop" style="font-size: 1.15rem; font-weight: 700; color: #EC4899;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #EC4899; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Cyl Head Temp (CHT)</div>
                <div id="valCht" style="font-size: 1.15rem; font-weight: 700; color: #EC4899;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #EC4899; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">TCC Converter Slip</div>
                <div id="valTccSlip" style="font-size: 1.15rem; font-weight: 700; color: #EC4899;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #EC4899; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Commanded Gear</div>
                <div id="valGear" style="font-size: 1.15rem; font-weight: 700; color: #EC4899;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #EC4899; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Knock Retard (KR)</div>
                <div id="valKr" style="font-size: 1.15rem; font-weight: 700; color: #EC4899;">--</div>
            </div>
        </div>

        <!-- 3. I/M READINESS MONITORS (UNDER ENHANCED PIDS) -->
        <div style="font-weight: 700; font-size: 0.95rem; color: #38BDF8; margin-bottom: 6px;">📋 EMISSIONS INSPECTION (I/M) READINESS MONITORS</div>
        <div id="readinessBox" style="background: #111418; border: 1px solid #2D3748; border-radius: 6px; padding: 10px; margin-bottom: 16px;">
            <div style="color: #A0AEC0; font-size: 0.85rem;">Monitors will auto-load immediately upon connection.</div>
        </div>

        <!-- 4. FULL MODE $06 ON-BOARD MONITORS (UNDER READINESS) -->
        <div style="font-weight: 700; font-size: 0.95rem; color: #38BDF8; margin-bottom: 6px;">📊 COMPLETE ON-BOARD DIAGNOSTIC MONITORS (MODE $06)</div>
        <div id="mode6Box" style="background: #111418; border: 1px solid #2D3748; border-radius: 6px; padding: 10px; min-height: 80px; max-height: 240px; overflow-y: auto; font-family: monospace; font-size: 0.85rem; color: #A0AEC0; margin-bottom: 16px;">
            Mode $06 monitors will auto-load immediately upon connection.
        </div>

        <!-- 5. AI DIAGNOSTIC VERDICT (BOTTOM) -->
        <div style="font-weight: 700; font-size: 0.95rem; color: #F59E0B; margin-bottom: 6px;">🤖 AI MASTER TECH TELEMETRY EVALUATION</div>
        <div id="aiVerdictBox" style="background: #111418; border: 1px solid #F59E0B; border-radius: 6px; padding: 12px; min-height: 90px; max-height: 320px; overflow-y: auto; font-size: 0.9rem; line-height: 1.45; color: #FFFFFF;">
            Connect adapter to automatically analyze live telemetry and diagnostic monitors.
        </div>
    </div>

    <script>
    const GEMINI_API_KEY = "___GEMINI_KEY___";
    const VEHICLE_CONTEXT = "___VEHICLE_INFO___";
    const DTC_CONTEXT = "___ACTIVE_DTC___";
    const DETECTED_MAKE = "___DETECTED_MAKE___";

    const NORDIC_SERVICE = '6e400001-b5a3-f393-e0a9-e50e24dcca9e';
    const NORDIC_RX = '6e400002-b5a3-f393-e0a9-e50e24dcca9e';
    const NORDIC_TX = '6e400003-b5a3-f393-e0a9-e50e24dcca9e';

    const FFF0_SERVICE = '0000fff0-0000-1000-8000-00805f9b34fb';
    const FFF2_RX = '0000fff2-0000-1000-8000-00805f9b34fb';
    const FFF1_TX = '0000fff1-0000-1000-8000-00805f9b34fb';

    let rxChar = null;
    let txChar = null;
    let responseBuffer = "";
    let resolver = null;
    let isBusy = false;
    let isStreaming = false;
    let isTestDriveActive = false;
    let unsupportedPids = new Set();
    let o2B1Probe = null;
    let o2B2Probe = null;
    let loopCycle = 0;
    let mode6RawData = "";
    let readinessSummary = "";
    let wakeLockSentinel = null;
    let lastVoiceAlertTime = 0;
    let lastAiSnapshotTime = 0;

    function log(msg) {
        document.getElementById('bleStatus').innerText = "Status: " + msg;
    }

    function onData(event) {
        const val = new TextDecoder().decode(event.target.value);
        responseBuffer += val;
        if (responseBuffer.includes('>') && resolver) {
            const out = responseBuffer;
            responseBuffer = "";
            const r = resolver;
            resolver = null;
            isBusy = false;
            r(out);
        }
    }

    async function sendCmd(cmd, timeoutMs = 1200) {
        while (isBusy) {
            await new Promise(r => setTimeout(r, 20));
        }
        isBusy = true;

        return new Promise(async (resolve) => {
            responseBuffer = "";
            const timer = setTimeout(() => {
                if (resolver) {
                    const fallback = responseBuffer;
                    responseBuffer = "";
                    resolver = null;
                    isBusy = false;
                    resolve(fallback);
                }
            }, timeoutMs);

            resolver = (data) => {
                clearTimeout(timer);
                resolver = null;
                isBusy = false;
                resolve(data);
            };

            try {
                const enc = new TextEncoder().encode(cmd + "\\r");
                if (rxChar.writeValueWithResponse) {
                    await rxChar.writeValueWithResponse(enc);
                } else {
                    await rxChar.writeValue(enc);
                }
            } catch (err) {
                clearTimeout(timer);
                resolver = null;
                isBusy = false;
                resolve("");
            }
        });
    }

    function parseCleanHex(raw) {
        return (raw || '').replace(/\\s+/g, '').toUpperCase();
    }

    function parseDTC(raw) {
        const clean = parseCleanHex(raw);
        const m = clean.match(/43([0-9A-F]{4})/);
        if (m) {
            const hex = m[1];
            const byte1 = parseInt(hex.substr(0, 2), 16);
            let prefix = 'P';
            const type = (byte1 & 0xC0) >> 6;
            if (type === 1) prefix = 'C';
            if (type === 2) prefix = 'B';
            if (type === 3) prefix = 'U';
            const digit1 = (byte1 & 0x30) >> 4;
            const digit2 = (byte1 & 0x0F).toString(16);
            const rest = hex.substr(2, 2);
            return (prefix + digit1 + digit2 + rest).toUpperCase();
        }
        return "";
    }

    function parseVIN(raw) {
        const hexMatches = raw.match(/[0-9A-Fa-f]{2}/g);
        if (!hexMatches) return "";
        let ascii = "";
        for (let h of hexMatches) {
            const code = parseInt(h, 16);
            if (code >= 32 && code <= 126) ascii += String.fromCharCode(code);
        }
        const m = ascii.match(/[A-HJ-NPR-Z0-9]{17}/);
        return m ? m[0] : "";
    }

    async function queryPid(cmd, timeoutMs = 500) {
        if (unsupportedPids.has(cmd)) return "";
        let res = await sendCmd(cmd, timeoutMs);
        let clean = parseCleanHex(res);
        if (clean.includes("NODATA") || clean.includes("?") || clean.includes("UNABLE")) {
            unsupportedPids.add(cmd);
            return "";
        }
        return clean;
    }

    function getActiveOemProfile() {
        let sel = document.getElementById('oemProfileSelect').value;
        if (sel === "AUTO") {
            return DETECTED_MAKE;
        }
        return sel;
    }

    function speakAlert(text) {
        const now = Date.now();
        if (now - lastVoiceAlertTime < 18000) return;
        lastVoiceAlertTime = now;
        if ('speechSynthesis' in window) {
            window.speechSynthesis.cancel();
            const utter = new SpeechSynthesisUtterance(text);
            utter.rate = 1.05;
            utter.pitch = 1.0;
            window.speechSynthesis.speak(utter);
        }
    }

    async function enableWakeLock() {
        try {
            if ('wakeLock' in navigator) {
                wakeLockSentinel = await navigator.wakeLock.request('screen');
            }
        } catch (e) {}
    }

    function disableWakeLock() {
        if (wakeLockSentinel) {
            wakeLockSentinel.release().catch(() => {});
            wakeLockSentinel = null;
        }
    }

    async function evaluateTestDriveTriggers(s1, l1, s2, l2, ectVal, voltVal) {
        if (!isTestDriveActive) return;

        const total1 = s1 + l1;
        const total2 = s2 + l2;

        if (total1 > 16.0) speakAlert("Alert: Bank 1 Total Fuel Trim plus " + Math.round(total1) + " percent lean.");
        else if (total1 < -16.0) speakAlert("Alert: Bank 1 Total Fuel Trim negative " + Math.abs(Math.round(total1)) + " percent rich.");
        else if (total2 > 16.0 && s2 !== 0) speakAlert("Alert: Bank 2 Total Fuel Trim plus " + Math.round(total2) + " percent lean.");
        else if (total2 < -16.0 && s2 !== 0) speakAlert("Alert: Bank 2 Total Fuel Trim negative " + Math.abs(Math.round(total2)) + " percent rich.");
        else if (ectVal >= 225) speakAlert("High Coolant Temperature: " + ectVal + " degrees.");
        else if (voltVal > 0 && voltVal < 12.8) speakAlert("Low Battery Voltage under load: " + voltVal.toFixed(1) + " volts.");

        const now = Date.now();
        if (now - lastAiSnapshotTime >= 45000) {
            lastAiSnapshotTime = now;
            triggerBackgroundAiEvaluation();
        }
    }

    async function triggerBackgroundAiEvaluation() {
        if (!GEMINI_API_KEY) return;
        const vBox = document.getElementById('aiVerdictBox');
        
        const pids = {
            "Time": new Date().toLocaleTimeString(),
            "RPM": document.getElementById('valRpm').innerText,
            "Load": document.getElementById('valLoad').innerText,
            "Speed": document.getElementById('valSpd').innerText,
            "TPS": document.getElementById('valTps').innerText,
            "ECT": document.getElementById('valEct').innerText,
            "IAT": document.getElementById('valIat').innerText,
            "MAP": document.getElementById('valMap').innerText,
            "MAF": document.getElementById('valMaf').innerText,
            "STFT1": document.getElementById('valStft').innerText,
            "LTFT1": document.getElementById('valLtft').innerText,
            "STFT2": document.getElementById('valStft2').innerText,
            "LTFT2": document.getElementById('valLtft2').innerText,
            "TransTemp": document.getElementById('valTft').innerText,
            "OilPress": document.getElementById('valEop').innerText,
            "CHT": document.getElementById('valCht').innerText,
            "Timing": document.getElementById('valTime').innerText,
            "O2_B1S1": document.getElementById('valO21').innerText,
            "O2_B1S2": document.getElementById('valO22').innerText,
            "Voltage": document.getElementById('valVolt').innerText
        };

        const prompt = `
You are an expert ASE Master / L1 Diagnostic Technician monitoring a live vehicle test drive in real time.
Vehicle: ${VEHICLE_CONTEXT}
Active DTC: ${DTC_CONTEXT}

LATEST TELEMETRY SNAPSHOT DURING ROAD LOAD:
${JSON.stringify(pids, null, 2)}

Provide a concise 3-bullet live assessment:
1. Dynamic Fuel Delivery & Trim State (Bank 1 vs 2 balance under current load).
2. Transmission, Oil Pressure & Temperature Health.
3. Any immediate anomaly to inspect upon returning to the bay.
Keep it strictly under 100 words.
`;
        try {
            const url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + GEMINI_API_KEY;
            const res = await fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }] })
            });
            const data = await res.json();
            if (data.candidates && data.candidates[0].content.parts[0].text) {
                const text = data.candidates[0].content.parts[0].text
                    .replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>')
                    .replace(/\\n/g, '<br>');
                vBox.innerHTML = "<div style='color: #00FF66; font-size: 0.8rem; margin-bottom: 4px;'>[Live Drive AI Check - " + pids.Time + "]</div>" + text;
            }
        } catch (e) {}
    }

    // --- REUSABLE READINESS MONITORS FETCHER ---
    async function loadReadinessMonitors() {
        const rBox = document.getElementById('readinessBox');
        rBox.innerHTML = "<div style='color: #F59E0B;'>Reading emissions monitor status from ECM...</div>";

        let res = await sendCmd("0101", 1500);
        let clean = parseCleanHex(res);
        let m = clean.match(/4101([0-9A-F]{8})/);

        if (m) {
            let bB = parseInt(m[1].substr(2, 2), 16);
            let bC = parseInt(m[1].substr(4, 2), 16);
            let bD = parseInt(m[1].substr(6, 2), 16);

            const monitors = [
                {name: "Misfire Monitor", sup: (bB & 0x01) !== 0, rdy: (bB & 0x10) === 0},
                {name: "Fuel System", sup: (bB & 0x02) !== 0, rdy: (bB & 0x20) === 0},
                {name: "Comprehensive Components", sup: (bB & 0x04) !== 0, rdy: (bB & 0x40) === 0},
                {name: "Catalyst Monitor", sup: (bC & 0x01) !== 0, rdy: (bD & 0x01) === 0},
                {name: "Heated Catalyst", sup: (bC & 0x02) !== 0, rdy: (bD & 0x02) === 0},
                {name: "EVAP System", sup: (bC & 0x04) !== 0, rdy: (bD & 0x04) === 0},
                {name: "Secondary Air", sup: (bC & 0x08) !== 0, rdy: (bD & 0x08) === 0},
                {name: "O2 Sensor", sup: (bC & 0x20) !== 0, rdy: (bD & 0x20) === 0},
                {name: "O2 Sensor Heater", sup: (bC & 0x40) !== 0, rdy: (bD & 0x40) === 0},
                {name: "EGR / VVT System", sup: (bC & 0x80) !== 0, rdy: (bD & 0x80) === 0}
            ];

            let html = "<div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 8px;'>";
            readinessSummary = "";

            for (let mon of monitors) {
                let badge = "";
                let color = "";
                if (!mon.sup) {
                    badge = "N/A";
                    color = "#64748B";
                } else if (mon.rdy) {
                    badge = "READY / COMPLETE";
                    color = "#00FF66";
                } else {
                    badge = "NOT READY";
                    color = "#EF4444";
                }
                readinessSummary += `${mon.name}: ${badge}; `;
                html += `<div style='background: #1A1F26; border: 1px solid ${color}; padding: 6px; border-radius: 5px; text-align: center;'>
                    <div style='font-size: 0.75rem; color: #A0AEC0;'>${mon.name}</div>
                    <div style='font-size: 0.9rem; font-weight: 700; color: ${color};'>${badge}</div>
                </div>`;
            }
            html += "</div>";
            rBox.innerHTML = html;
        } else {
            rBox.innerHTML = "<div style='color: #EF4444;'>Could not read I/M monitors. Raw response: " + res + "</div>";
        }
    }

    // --- REUSABLE FULL MODE $06 FETCHER ---
    async function loadMode6Data() {
        const m6Box = document.getElementById('mode6Box');
        m6Box.innerHTML = "<div style='color: #F59E0B; padding: 4px;'>⚡ Scanning all supported vehicle monitors (Cylinders 1-8+, Catalyst Bank 1 & 2, O2 Sensors, EVAP, VVT, EGR)...</div>";

        const allMonitors = [
            {mid: "06A2", name: "Cylinder 1 Misfires", isCyl: true},
            {mid: "06A3", name: "Cylinder 2 Misfires", isCyl: true},
            {mid: "06A4", name: "Cylinder 3 Misfires", isCyl: true},
            {mid: "06A5", name: "Cylinder 4 Misfires", isCyl: true},
            {mid: "06A6", name: "Cylinder 5 Misfires", isCyl: true},
            {mid: "06A7", name: "Cylinder 6 Misfires", isCyl: true},
            {mid: "06A8", name: "Cylinder 7 Misfires", isCyl: true},
            {mid: "06A9", name: "Cylinder 8 Misfires", isCyl: true},
            {mid: "0621", name: "Catalyst Bank 1", isCyl: false},
            {mid: "0622", name: "Catalyst Bank 2", isCyl: false},
            {mid: "0601", name: "O2 Sensor B1S1 Monitor", isCyl: false},
            {mid: "0602", name: "O2 Sensor B1S2 Monitor", isCyl: false},
            {mid: "0605", name: "O2 Sensor B2S1 Monitor", isCyl: false},
            {mid: "0606", name: "O2 Sensor B2S2 Monitor", isCyl: false},
            {mid: "0635", name: "VVT / Cam Phasing Bank 1", isCyl: false},
            {mid: "0636", name: "VVT / Cam Phasing Bank 2", isCyl: false},
            {mid: "0639", name: "EVAP 0.040 Monitor", isCyl: false},
            {mid: "063A", name: "EVAP 0.020 Leak Monitor", isCyl: false},
            {mid: "063B", name: "EVAP Purge Flow Monitor", isCyl: false},
            {mid: "0651", name: "EGR Flow / Lift Monitor", isCyl: false}
        ];

        let htmlGrid = "<div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 8px;'>";
        let foundAny = false;
        mode6RawData = "";

        for (let t of allMonitors) {
            let res = await sendCmd(t.mid, 600);
            let clean = parseCleanHex(res);
            if (clean.includes("NODATA") || clean.includes("?") || clean.length < 6) continue;
            mode6RawData += `\\n${t.name} (${t.mid}): ${res}`;

            let color = "#00FF66";
            let statusText = "PASS";

            if (t.isCyl) {
                let m = clean.match(/46(A[2-9])([0-9A-F]{2})([0-9A-F]{2})([0-9A-F]{4})/);
                if (m) {
                    let count = parseInt(m[4], 16);
                    color = count === 0 ? "#00FF66" : "#EF4444";
                    statusText = count === 0 ? "PASS (0 ct)" : "MISFIRES: " + count;
                }
            } else {
                statusText = "MONITORED";
                color = "#38BDF8";
            }

            foundAny = true;
            htmlGrid += `<div style='background: #1A1F26; border: 1px solid ${color}; padding: 8px; border-radius: 6px; text-align: center;'>
                <div style='color: #A0AEC0; font-weight: 700; font-size: 0.8rem;'>${t.name}</div>
                <div style='color: ${color}; font-size: 1rem; font-weight: 700;'>${statusText}</div>
            </div>`;
            m6Box.innerHTML = htmlGrid + "</div>";
        }

        if (!foundAny) {
            m6Box.innerHTML = "<div style='color: #A0AEC0; padding: 4px;'>Raw Mode $06 Output:<br><pre style='white-space: pre-wrap; font-size: 0.75rem;'>" + (mode6RawData.trim() || "No response bytes from ECM.") + "</pre></div>";
        }
    }

    // --- REUSABLE OEM ENHANCED PIDS QUERY (UDS 0x22) ---
    async function queryEnhancedPids(oem) {
        if (oem === "GENERIC") return;

        // Switch to physical ECM address 7E0
        await sendCmd("ATSH 7E0", 300);

        if (oem === "FORD") {
            // Ford Transmission Fluid Temp (221E1C or 221674)
            let rTft = await queryPid("221E1C", 350);
            let mTft = rTft.match(/621E1C([0-9A-F]{4})/);
            if (mTft) {
                let a = parseInt(mTft[1].substr(0, 2), 16);
                let b = parseInt(mTft[1].substr(2, 2), 16);
                let degF = Math.round(((((a * 256) + b) / 16) - 40) * 1.8 + 32);
                document.getElementById('valTft').innerText = degF + " °F";
            } else if (unsupportedPids.has("221E1C")) {
                let r2 = await queryPid("221674", 350);
                let m2 = r2.match(/621674([0-9A-F]{4})/);
                if (m2) {
                    let a = parseInt(m2[1].substr(0, 2), 16);
                    let b = parseInt(m2[1].substr(2, 2), 16);
                    document.getElementById('valTft').innerText = Math.round(((((a * 256) + b) * 5 / 72) - 18) * 1.8 + 32) + " °F";
                } else if (unsupportedPids.has("221674")) document.getElementById('valTft').innerText = "N/A";
            }

            // Ford Cylinder Head Temp (221624)
            let rCht = await queryPid("221624", 350);
            let mCht = rCht.match(/621624([0-9A-F]{4})/);
            if (mCht) {
                let a = parseInt(mCht[1].substr(0, 2), 16);
                let b = parseInt(mCht[1].substr(2, 2), 16);
                let degF = Math.round(((((a * 256) + b) / 10) - 40) * 1.8 + 32);
                document.getElementById('valCht').innerText = degF + " °F";
            } else if (unsupportedPids.has("221624")) document.getElementById('valCht').innerText = "N/A";

            // Ford TCC Slip RPM (221E14)
            let rSlip = await queryPid("221E14", 350);
            let mSlip = rSlip.match(/621E14([0-9A-F]{4})/);
            if (mSlip) {
                let a = parseInt(mSlip[1].substr(0, 2), 16);
                let b = parseInt(mSlip[1].substr(2, 2), 16);
                document.getElementById('valTccSlip').innerText = Math.round(((a * 256) + b) / 4) + " RPM";
            } else if (unsupportedPids.has("221E14")) document.getElementById('valTccSlip').innerText = "N/A";

            // Ford Commanded Gear (221E12)
            let rGear = await queryPid("221E12", 350);
            let mGear = rGear.match(/621E12([0-9A-F]{2})/);
            if (mGear) document.getElementById('valGear').innerText = "Gear " + parseInt(mGear[1], 16);
            else if (unsupportedPids.has("221E12")) document.getElementById('valGear').innerText = "N/A";

        } else if (oem === "GM") {
            // GM Transmission Fluid Temp (221940)
            let rTft = await queryPid("221940", 350);
            let mTft = rTft.match(/621940([0-9A-F]{2})/);
            if (mTft) {
                let degF = Math.round((parseInt(mTft[1], 16) - 40) * 1.8 + 32);
                document.getElementById('valTft').innerText = degF + " °F";
            } else if (unsupportedPids.has("221940")) document.getElementById('valTft').innerText = "N/A";

            // GM Engine Oil Pressure (22115C)
            let rEop = await queryPid("22115C", 350);
            let mEop = rEop.match(/62115C([0-9A-F]{2})/);
            if (mEop) {
                let psi = Math.round(parseInt(mEop[1], 16) * 0.579);
                document.getElementById('valEop').innerText = psi + " PSI";
            } else if (unsupportedPids.has("22115C")) document.getElementById('valEop').innerText = "N/A";

            // GM Knock Retard (2211A6)
            let rKr = await queryPid("2211A6", 350);
            let mKr = rKr.match(/6211A6([0-9A-F]{2})/);
            if (mKr) {
                let kr = (parseInt(mKr[1], 16) * 0.1).toFixed(1);
                document.getElementById('valKr').innerText = kr + "°";
            } else if (unsupportedPids.has("2211A6")) document.getElementById('valKr').innerText = "N/A";

            // GM TCC Slip (221943)
            let rSlip = await queryPid("221943", 350);
            let mSlip = rSlip.match(/621943([0-9A-F]{4})/);
            if (mSlip) {
                let a = parseInt(mSlip[1].substr(0, 2), 16);
                let b = parseInt(mSlip[1].substr(2, 2), 16);
                document.getElementById('valTccSlip').innerText = Math.round(((a * 256) + b) / 8) + " RPM";
            } else if (unsupportedPids.has("221943")) document.getElementById('valTccSlip').innerText = "N/A";

        } else if (oem === "TOYOTA") {
            // Toyota A/T Pan Temp (221627)
            let rTft = await queryPid("221627", 350);
            let mTft = rTft.match(/621627([0-9A-F]{2})/);
            if (mTft) {
                let degF = Math.round((parseInt(mTft[1], 16) - 40) * 1.8 + 32);
                document.getElementById('valTft').innerText = degF + " °F";
            } else if (unsupportedPids.has("221627")) document.getElementById('valTft').innerText = "N/A";

        } else if (oem === "CHRYSLER") {
            // Chrysler Oil Pressure (221003)
            let rEop = await queryPid("221003", 350);
            let mEop = rEop.match(/621003([0-9A-F]{2})/);
            if (mEop) {
                let psi = Math.round(parseInt(mEop[1], 16) * 0.58);
                document.getElementById('valEop').innerText = psi + " PSI";
            } else if (unsupportedPids.has("221003")) document.getElementById('valEop').innerText = "N/A";

            // Chrysler Trans Temp (22B005)
            let rTft = await queryPid("22B005", 350);
            let mTft = rTft.match(/62B005([0-9A-F]{2})/);
            if (mTft) {
                let degF = Math.round((parseInt(mTft[1], 16) - 40) * 1.8 + 32);
                document.getElementById('valTft').innerText = degF + " °F";
            } else if (unsupportedPids.has("22B005")) document.getElementById('valTft').innerText = "N/A";
        }

        // Restore standard functional broadcast address
        await sendCmd("ATSH 7DF", 300);
    }

    async function runLiveLoop() {
        let lastS1 = 0, lastL1 = 0, lastS2 = 0, lastL2 = 0, lastEct = 0, lastVolt = 0;

        while (isStreaming) {
            loopCycle++;
            try {
                // Tier 1: Fast Engine Essentials (Every Cycle)
                let cRpm = await queryPid("010C", 350);
                let mRpm = cRpm.match(/410C([0-9A-F]{4})/);
                if (mRpm) {
                    let a = parseInt(mRpm[1].substr(0, 2), 16);
                    let b = parseInt(mRpm[1].substr(2, 2), 16);
                    document.getElementById('valRpm').innerText = Math.round(((a * 256) + b) / 4) + " RPM";
                }
                if (!isStreaming) break;

                let cLoad = await queryPid("0104", 300);
                let mLoad = cLoad.match(/4104([0-9A-F]{2})/);
                if (mLoad) document.getElementById('valLoad').innerText = Math.round((parseInt(mLoad[1], 16) * 100) / 255) + "%";
                if (!isStreaming) break;

                let cTps = await queryPid("0111", 300);
                let mTps = cTps.match(/4111([0-9A-F]{2})/);
                if (mTps) document.getElementById('valTps').innerText = Math.round((parseInt(mTps[1], 16) * 100) / 255) + "%";
                if (!isStreaming) break;

                let cSpd = await queryPid("010D", 300);
                let mSpd = cSpd.match(/410D([0-9A-F]{2})/);
                if (mSpd) document.getElementById('valSpd').innerText = Math.round(parseInt(mSpd[1], 16) * 0.621371) + " MPH";
                if (!isStreaming) break;

                // Tier 2: Fuel Trims & Both Cylinder Banks (Every 2nd Cycle)
                if (loopCycle % 2 === 0) {
                    let cStft = await queryPid("0106", 350);
                    let mStft = cStft.match(/4106([0-9A-F]{2})/);
                    if (mStft) {
                        lastS1 = ((parseInt(mStft[1], 16) - 128) * 100) / 128;
                        document.getElementById('valStft').innerText = (lastS1 > 0 ? "+" : "") + lastS1.toFixed(1) + "%";
                    }
                    if (!isStreaming) break;

                    let cLtft = await queryPid("0107", 350);
                    let mLtft = cLtft.match(/4107([0-9A-F]{2})/);
                    if (mLtft) {
                        lastL1 = ((parseInt(mLtft[1], 16) - 128) * 100) / 128;
                        document.getElementById('valLtft').innerText = (lastL1 > 0 ? "+" : "") + lastL1.toFixed(1) + "%";
                    }
                    if (!isStreaming) break;

                    let cStft2 = await queryPid("0108", 350);
                    let mStft2 = cStft2.match(/4108([0-9A-F]{2})/);
                    if (mStft2) {
                        lastS2 = ((parseInt(mStft2[1], 16) - 128) * 100) / 128;
                        document.getElementById('valStft2').innerText = (lastS2 > 0 ? "+" : "") + lastS2.toFixed(1) + "%";
                    } else if (unsupportedPids.has("0108")) {
                        document.getElementById('valStft2').innerText = "N/A";
                    }
                    if (!isStreaming) break;

                    let cLtft2 = await queryPid("0109", 350);
                    let mLtft2 = cLtft2.match(/4109([0-9A-F]{2})/);
                    if (mLtft2) {
                        lastL2 = ((parseInt(mLtft2[1], 16) - 128) * 100) / 128;
                        document.getElementById('valLtft2').innerText = (lastL2 > 0 ? "+" : "") + lastL2.toFixed(1) + "%";
                    } else if (unsupportedPids.has("0109")) {
                        document.getElementById('valLtft2').innerText = "N/A";
                    }
                    if (!isStreaming) break;

                    let cTime = await queryPid("010E", 300);
                    let mTime = cTime.match(/410E([0-9A-F]{2})/);
                    if (mTime) document.getElementById('valTime').innerText = ((parseInt(mTime[1], 16) / 2) - 64).toFixed(1) + "°";
                    if (!isStreaming) break;

                    let cMaf = await queryPid("0110", 300);
                    let mMaf = cMaf.match(/4110([0-9A-F]{4})/);
                    if (mMaf) {
                        let a = parseInt(mMaf[1].substr(0, 2), 16);
                        let b = parseInt(mMaf[1].substr(2, 2), 16);
                        document.getElementById('valMaf').innerText = (((a * 256) + b) / 100).toFixed(1) + " g/s";
                    } else if (unsupportedPids.has("0110")) {
                        document.getElementById('valMaf').innerText = "N/A";
                    }
                    if (!isStreaming) break;

                    let cMap = await queryPid("010B", 300);
                    let mMap = cMap.match(/410B([0-9A-F]{2})/);
                    if (mMap) {
                        document.getElementById('valMap').innerText = (parseInt(mMap[1], 16) * 0.145038).toFixed(1) + " PSI";
                    } else if (unsupportedPids.has("010B")) {
                        document.getElementById('valMap').innerText = "N/A";
                    }
                    if (!isStreaming) break;

                    // Bank 1 Sensor 1
                    if (!o2B1Probe) {
                        let c14 = await queryPid("0114", 300);
                        if (c14.includes("4114")) o2B1Probe = "14";
                        else {
                            let c24 = await queryPid("0124", 300);
                            if (c24.includes("4124")) o2B1Probe = "24";
                            else {
                                let c34 = await queryPid("0134", 300);
                                if (c34.includes("4134")) o2B1Probe = "34";
                            }
                        }
                    }
                    if (o2B1Probe === "14") {
                        let cO2 = await queryPid("0114", 300);
                        let m = cO2.match(/4114([0-9A-F]{2})/);
                        if (m) document.getElementById('valO21').innerText = (parseInt(m[1], 16) / 200).toFixed(2) + "V";
                    } else if (o2B1Probe) {
                        let cWb = await queryPid("01" + o2B1Probe, 300);
                        let m = cWb.match(new RegExp("41" + o2B1Probe + "([0-9A-F]{4})"));
                        if (m) {
                            let a = parseInt(m[1].substr(0, 2), 16);
                            let b = parseInt(m[1].substr(2, 2), 16);
                            document.getElementById('lblO21').innerText = "O2 B1S1 (A/F λ)";
                            document.getElementById('valO21').innerText = "λ " + (((a * 256) + b) / 32768).toFixed(2);
                        }
                    }

                    // Bank 1 Sensor 2
                    let cO22 = await queryPid("0115", 300);
                    let mO22 = cO22.match(/4115([0-9A-F]{2})/);
                    if (mO22) document.getElementById('valO22').innerText = (parseInt(mO22[1], 16) / 200).toFixed(2) + "V";
                    else if (unsupportedPids.has("0115")) document.getElementById('valO22').innerText = "N/A";
                    if (!isStreaming) break;

                    // Bank 2 Sensor 1
                    if (!o2B2Probe) {
                        let c18 = await queryPid("0118", 300);
                        if (c18.includes("4118")) o2B2Probe = "18";
                        else {
                            let c28 = await queryPid("0128", 300);
                            if (c28.includes("4128")) o2B2Probe = "28";
                            else {
                                let c38 = await queryPid("0138", 300);
                                if (c38.includes("4138")) o2B2Probe = "38";
                            }
                        }
                    }
                    if (o2B2Probe === "18") {
                        let cO2 = await queryPid("0118", 300);
                        let m = cO2.match(/4118([0-9A-F]{2})/);
                        if (m) document.getElementById('valO221').innerText = (parseInt(m[1], 16) / 200).toFixed(2) + "V";
                    } else if (o2B2Probe) {
                        let cWb = await queryPid("01" + o2B2Probe, 300);
                        let m = cWb.match(new RegExp("41" + o2B2Probe + "([0-9A-F]{4})"));
                        if (m) {
                            let a = parseInt(m[1].substr(0, 2), 16);
                            let b = parseInt(m[1].substr(2, 2), 16);
                            document.getElementById('lblO221').innerText = "O2 B2S1 (A/F λ)";
                            document.getElementById('valO221').innerText = "λ " + (((a * 256) + b) / 32768).toFixed(2);
                        }
                    } else if (unsupportedPids.has("0118") && unsupportedPids.has("0128")) {
                        document.getElementById('valO221').innerText = "N/A";
                    }
                    if (!isStreaming) break;

                    // Bank 2 Sensor 2
                    let cO222 = await queryPid("0119", 300);
                    let mO222 = cO222.match(/4119([0-9A-F]{2})/);
                    if (mO222) document.getElementById('valO222').innerText = (parseInt(mO222[1], 16) / 200).toFixed(2) + "V";
                    else if (unsupportedPids.has("0119")) document.getElementById('valO222').innerText = "N/A";
                    if (!isStreaming) break;

                    // Pedal Pos APP
                    let cApp = await queryPid("0149", 300);
                    let mApp = cApp.match(/4149([0-9A-F]{2})/);
                    if (mApp) document.getElementById('valApp').innerText = Math.round((parseInt(mApp[1], 16) * 100) / 255) + "%";
                    else if (unsupportedPids.has("0149")) document.getElementById('valApp').innerText = "N/A";
                }
                if (!isStreaming) break;

                // Tier 3: Temperatures, Rail Pressure & Battery (Every 4th Cycle)
                if (loopCycle % 4 === 0) {
                    let cEct = await queryPid("0105", 350);
                    let mEct = cEct.match(/4105([0-9A-F]{2})/);
                    if (mEct) {
                        lastEct = Math.round((parseInt(mEct[1], 16) - 40) * 1.8 + 32);
                        document.getElementById('valEct').innerText = lastEct + " °F";
                    }
                    if (!isStreaming) break;

                    let cIat = await queryPid("010F", 300);
                    let mIat = cIat.match(/410F([0-9A-F]{2})/);
                    if (mIat) document.getElementById('valIat').innerText = Math.round((parseInt(mIat[1], 16) - 40) * 1.8 + 32) + " °F";
                    else if (unsupportedPids.has("010F")) document.getElementById('valIat').innerText = "N/A";
                    if (!isStreaming) break;

                    let cAat = await queryPid("0146", 300);
                    let mAat = cAat.match(/4146([0-9A-F]{2})/);
                    if (mAat) document.getElementById('valAat').innerText = Math.round((parseInt(mAat[1], 16) - 40) * 1.8 + 32) + " °F";
                    else if (unsupportedPids.has("0146")) document.getElementById('valAat').innerText = "N/A";
                    if (!isStreaming) break;

                    let cEot = await queryPid("015C", 300);
                    let mEot = cEot.match(/415C([0-9A-F]{2})/);
                    if (mEot) document.getElementById('valEot').innerText = Math.round((parseInt(mEot[1], 16) - 40) * 1.8 + 32) + " °F";
                    else if (unsupportedPids.has("015C")) document.getElementById('valEot').innerText = "N/A";
                    if (!isStreaming) break;

                    // Fuel Rail Pressure
                    let cFrp = await queryPid("0123", 300);
                    let mFrp = cFrp.match(/4123([0-9A-F]{4})/);
                    if (mFrp) {
                        let a = parseInt(mFrp[1].substr(0, 2), 16);
                        let b = parseInt(mFrp[1].substr(2, 2), 16);
                        document.getElementById('valFrp').innerText = Math.round(((a * 256) + b) * 10 * 0.145038) + " PSI";
                    } else {
                        let cFrp2 = await queryPid("010A", 300);
                        let m2 = cFrp2.match(/410A([0-9A-F]{2})/);
                        if (m2) document.getElementById('valFrp').innerText = Math.round(parseInt(m2[1], 16) * 3 * 0.145038) + " PSI";
                        else if (unsupportedPids.has("0123") && unsupportedPids.has("010A")) document.getElementById('valFrp').innerText = "N/A";
                    }
                    if (!isStreaming) break;

                    let cFli = await queryPid("012F", 300);
                    let mFli = cFli.match(/412F([0-9A-F]{2})/);
                    if (mFli) document.getElementById('valFli').innerText = Math.round((parseInt(mFli[1], 16) * 100) / 255) + "%";
                    else if (unsupportedPids.has("012F")) document.getElementById('valFli').innerText = "N/A";
                    if (!isStreaming) break;

                    let cEvp = await queryPid("012E", 300);
                    let mEvp = cEvp.match(/412E([0-9A-F]{2})/);
                    if (mEvp) document.getElementById('valEvap').innerText = Math.round((parseInt(mEvp[1], 16) * 100) / 255) + "%";
                    else if (unsupportedPids.has("012E")) document.getElementById('valEvap').innerText = "N/A";
                    if (!isStreaming) break;

                    let cBaro = await queryPid("0133", 300);
                    let mBaro = cBaro.match(/4133([0-9A-F]{2})/);
                    if (mBaro) document.getElementById('valBaro').innerText = (parseInt(mBaro[1], 16) * 0.2953).toFixed(1) + " inHg";
                    else if (unsupportedPids.has("0133")) document.getElementById('valBaro').innerText = "N/A";
                    if (!isStreaming) break;

                    let resVolt = await sendCmd("ATRV", 350);
                    let vMatch = (resVolt || '').match(/([0-9]+\\.[0-9]+)/);
                    if (vMatch) {
                        lastVolt = parseFloat(vMatch[1]);
                        document.getElementById('valVolt').innerText = lastVolt.toFixed(1) + "V";
                    }

                    // Query OEM Enhanced PIDs (UDS 0x22)
                    let currentOem = getActiveOemProfile();
                    await queryEnhancedPids(currentOem);

                    evaluateTestDriveTriggers(lastS1, lastL1, lastS2, lastL2, lastEct, lastVolt);
                }
            } catch (err) {
                console.error("Telemetry error:", err);
            }
            await new Promise(r => setTimeout(r, 20));
        }
    }

    // --- ONE-TAP AUTOMATED CONNECTION, SCAN & STREAM SEQUENCE ---
    document.getElementById('bleBtn').addEventListener('click', async () => {
        try {
            log("Opening Bluetooth selector...");
            const device = await navigator.bluetooth.requestDevice({
                filters: [
                    { namePrefix: 'VEEPEAK' },
                    { namePrefix: 'OBD' },
                    { namePrefix: 'IOS-Vlink' }
                ],
                optionalServices: [NORDIC_SERVICE, FFF0_SERVICE]
            });

            log("Connecting to " + device.name + "...");
            const server = await device.gatt.connect();

            let service = null;
            try {
                service = await server.getPrimaryService(NORDIC_SERVICE);
                rxChar = await service.getCharacteristic(NORDIC_RX);
                txChar = await service.getCharacteristic(NORDIC_TX);
            } catch(e) {
                service = await server.getPrimaryService(FFF0_SERVICE);
                rxChar = await service.getCharacteristic(FFF2_RX);
                txChar = await service.getCharacteristic(FFF1_TX);
            }

            await txChar.startNotifications();
            txChar.addEventListener('characteristicvaluechanged', onData);

            log("Configuring Veepeak adapter...");
            await sendCmd("ATE0", 600);
            await sendCmd("ATL0", 500);
            await sendCmd("ATH0", 500);
            await sendCmd("ATSP0", 600);

            log("Connecting to vehicle ECM...");
            await sendCmd("0100", 4000);

            unsupportedPids.clear();
            o2B1Probe = null;
            o2B2Probe = null;

            // Activate All Utility Buttons
            ['pauseBtn', 'testDriveBtn', 'clearDtcBtn', 'aiCheckBtn', 'pullVinBtn'].forEach(id => {
                const b = document.getElementById(id);
                b.disabled = false;
                b.style.cursor = 'pointer';
            });
            document.getElementById('pauseBtn').style.backgroundColor = '#EF4444';
            document.getElementById('pauseBtn').style.color = '#FFFFFF';
            document.getElementById('testDriveBtn').style.backgroundColor = '#10B981';
            document.getElementById('testDriveBtn').style.color = '#0E1117';
            document.getElementById('clearDtcBtn').style.backgroundColor = '#EF4444';
            document.getElementById('clearDtcBtn').style.color = '#FFFFFF';
            document.getElementById('aiCheckBtn').style.backgroundColor = '#F59E0B';
            document.getElementById('aiCheckBtn').style.color = '#0E1117';
            document.getElementById('pullVinBtn').style.backgroundColor = '#A855F7';
            document.getElementById('pullVinBtn').style.color = '#FFFFFF';

            // 1. AUTO-LOAD I/M READINESS MONITORS
            log("Auto-loading I/M Readiness monitors (Mode 01 01)...");
            await loadReadinessMonitors();

            // 2. AUTO-LOAD MODE $06 ON-BOARD MONITORS
            log("Auto-scanning Mode $06 monitors & cylinder misfire counts...");
            await loadMode6Data();

            // 3. AUTO-START LIVE TELEMETRY & ENHANCED PIDS STREAM
            log("All diagnostic monitors loaded! Starting live telemetry stream...");
            isStreaming = true;
            runLiveLoop();

        } catch (err) {
            log("Error: " + err.message);
        }
    });

    // --- PAUSE / RESUME STREAM BUTTON ---
    document.getElementById('pauseBtn').addEventListener('click', () => {
        const btn = document.getElementById('pauseBtn');
        if (isStreaming) {
            isStreaming = false;
            btn.innerText = "▶️ Resume Live Stream";
            btn.style.backgroundColor = "#38BDF8";
            btn.style.color = "#0E1117";
            log("Live telemetry stream paused.");
        } else {
            isStreaming = true;
            btn.innerText = "⏸️ Pause Stream";
            btn.style.backgroundColor = "#EF4444";
            btn.style.color = "#FFFFFF";
            log("Streaming live telemetry...");
            runLiveLoop();
        }
    });

    // --- TEST DRIVE AI WATCHDOG TOGGLE ---
    document.getElementById('testDriveBtn').addEventListener('click', () => {
        const btn = document.getElementById('testDriveBtn');
        const banner = document.getElementById('driveBanner');

        if (!isTestDriveActive) {
            isTestDriveActive = true;
            btn.innerText = "⏹️ Stop Test Drive AI";
            btn.style.backgroundColor = "#EF4444";
            btn.style.color = "#FFFFFF";
            banner.style.display = "block";
            enableWakeLock();
            speakAlert("Test Drive AI Activated. Telemetry watchdog and speech alerts active.");

            if (!isStreaming) {
                isStreaming = true;
                const pauseBtn = document.getElementById('pauseBtn');
                pauseBtn.innerText = "⏸️ Pause Stream";
                pauseBtn.style.backgroundColor = "#EF4444";
                pauseBtn.style.color = "#FFFFFF";
                runLiveLoop();
            }
        } else {
            isTestDriveActive = false;
            btn.innerText = "🚗 Test Drive Audio";
            btn.style.backgroundColor = "#10B981";
            btn.style.color = "#0E1117";
            banner.style.display = "none";
            disableWakeLock();
            speakAlert("Test Drive AI Deactivated.");
        }
    });

    // --- MODE 04: CLEAR CODES & RESET MONITORS ---
    document.getElementById('clearDtcBtn').addEventListener('click', async () => {
        if (!confirm("⚠️ Are you sure you want to CLEAR all DTC fault codes and RESET all I/M emissions readiness monitors on this vehicle?")) {
            return;
        }

        const wasStreaming = isStreaming;
        isStreaming = false;
        document.getElementById('pauseBtn').innerText = "▶️ Resume Live Stream";
        document.getElementById('pauseBtn').style.backgroundColor = "#38BDF8";

        log("Sending Mode 04 Clear DTCs command to ECM...");
        let res = await sendCmd("04", 3000);
        let clean = parseCleanHex(res);

        if (clean.includes("44") || clean.includes("OK") || clean.includes(">")) {
            log("SUCCESS: Fault codes cleared and readiness monitors reset!");
            alert("✅ Mode 04 Successful: Fault codes cleared and emissions monitors reset.");
            document.getElementById('readinessBox').innerHTML = "<div style='color: #EF4444; font-weight: 700;'>Monitors have been RESET by Mode 04 command. Re-run or reconnect to verify.</div>";
        } else {
            log("Mode 04 command response: " + res);
            alert("Result: " + res);
        }

        if (wasStreaming) {
            isStreaming = true;
            document.getElementById('pauseBtn').innerText = "⏸️ Pause Stream";
            document.getElementById('pauseBtn').style.backgroundColor = "#EF4444";
            runLiveLoop();
        }
    });

    // --- MANUAL AI TELEMETRY, READINESS & MODE 06 EVALUATION ---
    document.getElementById('aiCheckBtn').addEventListener('click', async () => {
        const vBox = document.getElementById('aiVerdictBox');
        if (!GEMINI_API_KEY) {
            vBox.innerHTML = "<span style='color: #EF4444;'>Error: GEMINI_API_KEY is missing from Streamlit Secrets.</span>";
            return;
        }

        vBox.innerHTML = "<span style='color: #F59E0B;'>🤖 Gemini 2.5 Flash is analyzing live telemetry, OEM enhanced data, I/M monitors, and Mode $06 results...</span>";

        const pids = {
            "RPM": document.getElementById('valRpm').innerText,
            "Load": document.getElementById('valLoad').innerText,
            "Speed": document.getElementById('valSpd').innerText,
            "TPS": document.getElementById('valTps').innerText,
            "APP_Pedal": document.getElementById('valApp').innerText,
            "ECT": document.getElementById('valEct').innerText,
            "IAT": document.getElementById('valIat').innerText,
            "AAT_Ambient": document.getElementById('valAat').innerText,
            "OilTemp": document.getElementById('valEot').innerText,
            "MAP": document.getElementById('valMap').innerText,
            "MAF": document.getElementById('valMaf').innerText,
            "Baro": document.getElementById('valBaro').innerText,
            "FuelRailPressure": document.getElementById('valFrp').innerText,
            "FuelLevel": document.getElementById('valFli').innerText,
            "STFT1": document.getElementById('valStft').innerText,
            "LTFT1": document.getElementById('valLtft').innerText,
            "STFT2": document.getElementById('valStft2').innerText,
            "LTFT2": document.getElementById('valLtft2').innerText,
            "TransFluidTemp": document.getElementById('valTft').innerText,
            "EngineOilPress": document.getElementById('valEop').innerText,
            "CylHeadTemp": document.getElementById('valCht').innerText,
            "TCC_Slip": document.getElementById('valTccSlip').innerText,
            "CommandedGear": document.getElementById('valGear').innerText,
            "KnockRetard": document.getElementById('valKr').innerText,
            "Timing": document.getElementById('valTime').innerText,
            "O2_B1S1": document.getElementById('valO21').innerText,
            "O2_B1S2": document.getElementById('valO22').innerText,
            "O2_B2S1": document.getElementById('valO221').innerText,
            "O2_B2S2": document.getElementById('valO222').innerText,
            "EvapPurge": document.getElementById('valEvap').innerText,
            "Voltage": document.getElementById('valVolt').innerText
        };

        const prompt = `
You are an expert ASE Master / L1 Diagnostic Technician.
Perform a full diagnostic telemetry check for this vehicle:
Vehicle: ${VEHICLE_CONTEXT}
Active DTC: ${DTC_CONTEXT}

LIVE STREAMING SENSOR DATA (MODE 01 & UDS 0x22 ENHANCED PIDS):
${JSON.stringify(pids, null, 2)}

I/M READINESS MONITORS (MODE 01 01):
${readinessSummary || "Not checked yet"}

MODE $06 ON-BOARD TEST DATA:
${mode6RawData || "No Mode 6 scanned yet"}

DIAGNOSTIC TASK:
1. Fuel Control & Trim Analysis: Total Trim (STFT + LTFT) on Bank 1 vs Bank 2. Single-bank vs dual-bank discrepancy.
2. Powertrain & Drivetrain Health: Transmission fluid temp, engine oil pressure, CHT, torque converter slip, and knock retard.
3. Air Metering & O2/AFR Sensors: Sensor switching vs catalytic converter holding efficiency.
4. Mode $06 Misfire & Monitor Integrity: Evaluate cylinder-by-cylinder misfire counts and catalyst/EVAP/VVT monitors.
5. Emissions Readiness State: Which monitors are not ready, and what drive cycle conditions are needed to set them?
6. Immediate Master Tech Next Step: The single most definitive physical/electrical isolation test to condemn the root cause.

Format with clean bold sections and direct shop-floor language.
`;

        try {
            const url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + GEMINI_API_KEY;
            const payload = {
                contents: [{ parts: [{ text: prompt }] }]
            };
            const response = await fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const data = await response.json();
            if (data.candidates && data.candidates[0].content.parts[0].text) {
                let markdownText = data.candidates[0].content.parts[0].text;
                let formatted = markdownText
                    .replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>')
                    .replace(/### (.*?)\\n/g, '<h4 style="color:#00FF66; margin:8px 0 4px 0;">$1</h4>')
                    .replace(/\\n/g, '<br>');
                vBox.innerHTML = formatted;
            } else {
                vBox.innerHTML = "<span style='color: #EF4444;'>No diagnosis generated: " + JSON.stringify(data) + "</span>";
            }
        } catch(e) {
            vBox.innerHTML = "<span style='color: #EF4444;'>API Error: " + e.message + "</span>";
        }
    });

    document.getElementById('pullVinBtn').addEventListener('click', async () => {
        isStreaming = false;
        log("Querying 17-digit VIN (09 02)...");
        const vinRaw = await sendCmd("0902", 1500);
        const vin = parseVIN(vinRaw);

        log("Querying Stored DTCs (03)...");
        const dtcRaw = await sendCmd("03", 1500);
        const dtc = parseDTC(dtcRaw);

        log("Success! VIN: " + (vin || "Manual") + " | DTC: " + (dtc || "None") + ". Refreshing app...");

        setTimeout(() => {
            const targetUrl = new URL(window.top.location.href);
            if (vin) targetUrl.searchParams.set("ble_vin", vin);
            if (dtc) targetUrl.searchParams.set("ble_dtc", dtc);
            window.top.location.href = targetUrl.toString();
        }, 1000);
    });
    </script>
    """

  ble_html = ble_dashboard_template.replace("___GEMINI_KEY___", gemini_api_key)
  ble_html = ble_html.replace(
      "___VEHICLE_INFO___",
      (st.session_state.vehicle_info or "General OBD-II Vehicle").replace(
          '"', ""
      ),
  )
  ble_html = ble_html.replace(
      "___ACTIVE_DTC___",
      (st.session_state.active_dtc or "None").replace('"', ""),
  )
  ble_html = ble_html.replace("___DETECTED_MAKE___", detected_make)

  components.html(ble_html, height=1350)

# ========================================================
# --- TAB 3: IN-DEPTH DTC DIAGNOSTIC STRATEGY ---
# ========================================================
with tab3:
  st.subheader("Field Diagnostic Strategy & Testing Workflow")

  if st.session_state.customer_name:
    st.markdown(
        f"👤 Customer: **{st.session_state.customer_name}** | 📞"
        f" `{st.session_state.customer_phone or 'No phone'}`"
    )

  if st.session_state.vehicle_info:
    st.success(
        f"Active Vehicle: **{st.session_state.vehicle_info}** (VIN:"
        f" `{st.session_state.active_vin or 'Manual'}`)"
    )
  else:
    st.caption("Tip: Decode a vehicle in Tab 1 to carry vehicle specs over.")

  col_input, col_engine, col_btn = st.columns([2.5, 2.5, 1.5])
  with col_input:
    code_input = (
        st.text_input(
            "Enter OBD-II DTC (e.g., P200A, P0316, P0300):",
            value=st.session_state.active_dtc,
        )
        .strip()
        .upper()
    )
    if code_input:
      st.session_state.active_dtc = code_input

  with col_engine:
    ai_engine = st.selectbox(
        "Diagnostic AI Engine",
        options=["gemini", "perplexity"],
        index=0,
        format_func=lambda x: {
            "gemini": "✨ Google Gemini 2.5 Flash (Deep Logic)",
            "perplexity": "🌐 Perplexity Sonar Pro (Live Web & TSBs)",
        }[x],
        help=(
            "Gemini provides deep circuit & mechanical logic; Perplexity checks"
            " live technical databases and TSBs."
        ),
    )

  with col_btn:
    st.write("")
    lookup_clicked = st.button("Run Diagnostic Tree", use_container_width=True)

  if code_input and lookup_clicked:
    vehicle = st.session_state.vehicle_info or "General OBD-II Vehicle"

    append_to_log(
        vin=st.session_state.active_vin,
        vehicle=vehicle,
        dtc=code_input,
        customer=st.session_state.customer_name,
        phone=st.session_state.customer_phone,
    )

    dtc_prompt = f"""
You are an expert ASE master diagnostic technician. Provide a laser-focused, code-specific diagnostic testing workflow for fault code {code_input} on a {vehicle}.

STRICT SCOPE RULES:
- ONLY provide tests and checks for the exact subsystem, sensor, actuator, or circuit named in {code_input}.
- DO NOT provide generic boilerplate checks. (For example: do NOT mention fuel pressure, fuel trims, spark/glow plugs, or engine compression UNLESS {code_input} directly involves those systems).
- Focus on practical shop isolation: isolate circuit vs computer vs mechanical component.

Format strictly using these Markdown sections:

### 1. Code Definition & Setting Criteria
- Exact technical definition of {code_input}
- Exact conditions required for ECM to flag this fault (voltage out of range, commanded vs actual position mismatch, duty cycle threshold)

### 2. Live Scan Data & Bi-Directional Active Tests
- Only the specific live PIDs directly tied to this circuit/actuator (and their expected values)
- Bi-directional / functional test to command the actuator and what to observe

### 3. Pinpoint Electrical & Circuit Checks (DMM / Scope)
- Connector pinout checks at the component (e.g. 5V reference, ground drop limit, 12V feed, PWM control duty cycle)
- Component resistance specification (solenoid coil resistance, motor winding resistance, potentiometer sweep)

### 4. Physical & Mechanical Inspection
- Visual and mechanical tests strictly for this mechanism (carbon buildup, binding linkages, vacuum diaphragm leaks, broken arm)

### 5. Known Platform Pattern Failures & TSBs
- Specific real-world failure patterns for {vehicle} on this specific system
"""
    with st.spinner(
        f"Generating {code_input} strategy via {ai_engine.upper()}..."
    ):
      if ai_engine == "gemini":
        result = query_gemini(dtc_prompt)
      else:
        result = query_perplexity(dtc_prompt, preset="low")
      st.markdown(result)

# ========================================================
# --- TAB 4: DIAGNOSTIC COPILOT & SCOPE LAB ---
# ========================================================
with tab4:
  st.subheader("⚡ Diagnostic Copilot & Scope Lab")

  v_label = st.session_state.vehicle_info or "No Vehicle Selected (General)"
  d_label = st.session_state.active_dtc or "None Specified"
  c_label = st.session_state.customer_name or "None"
  st.info(
      f"📋 **Context:** Customer: `{c_label}` | Vehicle: `{v_label}` | Active"
      f" DTC: `{d_label}`"
  )

  col_scope, col_scratch = st.columns([1, 1])

  with col_scope:
    st.markdown("#### 📸 Scope & Meter Display Capture")
    open_scope_cam = st.toggle("📷 Open Camera for Scope / Meter", value=False)
    scope_capture = None
    if open_scope_cam:
      scope_capture = st.camera_input("Capture oscilloscope or meter")

    scope_file = st.file_uploader(
        "Or upload scope waveform file/image",
        type=["png", "jpg", "jpeg"],
        key="scope_upload",
    )

    active_img = scope_capture or scope_file
    pil_scope_image = None
    if active_img:
      st.image(active_img, caption="Captured Scope / Meter Display")
      pil_scope_image = Image.open(active_img)

  with col_scratch:
    st.markdown("#### 📝 Test Results Scratchpad")
    with st.expander("Enter Physical Test Readings", expanded=True):
      comp_data = st.text_input(
          "Compression / Leakdown (psi / % drop):",
          placeholder="e.g., Cyl 1: 160, Cyl 2: 155, Cyl 3: 90, Cyl 4: 160",
      )
      fuel_data = st.text_input(
          "Fuel Pressure (Running / 5-min Bleed-down):",
          placeholder="e.g., 55 psi running, drops to 12 psi in 3 mins",
      )
      volt_data = st.text_input(
          "Electrical / Voltage Drop:",
          placeholder="e.g., Cranking battery drop 9.1V, engine ground drop 0.4V",
      )
      scope_notes = st.text_area(
          "Scope Waveform Observations:",
          placeholder=(
              "e.g., Ignition coil burn time is 0.7ms; injector kick voltage is"
              " only 35V; CKP missing tooth has uneven spacing"
          ),
          height=70,
      )

  if st.button("🔍 Analyze Entered Test Results & Scope Pattern with Gemini"):
    test_summary = f"""
Customer: {c_label}
Vehicle: {v_label}
Active DTC: {d_label}
Compression/Leakdown: {comp_data or 'Not tested'}
Fuel Pressure & Bleed-down: {fuel_data or 'Not tested'}
Voltage Drop / Electrical: {volt_data or 'Not tested'}
Scope Observations: {scope_notes or 'None reported'}
"""
    with st.spinner(
        "Gemini Vision is analyzing waveform signatures and physical"
        " readings..."
    ):
      eval_res = analyze_scope_with_gemini(pil_scope_image, test_summary)
      st.markdown("### Diagnostic Evaluation")
      st.markdown(eval_res)

  st.write("---")
  st.markdown("#### 💬 Interactive Diagnostic Copilot (Gemini)")
  st.caption(
      "Ask follow-up questions, request specific pinout checks, or ask how to"
      " isolate an intermittent fault."
  )

  for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
      st.markdown(msg["content"])

  user_question = st.chat_input(
      "Ask a diagnostic question (e.g., 'How do I isolate a leaking injector"
      " from a bad pump check valve?')"
  )

  if user_question:
    st.session_state.chat_history.append(
        {"role": "user", "content": user_question}
    )
    with st.chat_message("user"):
      st.markdown(user_question)

    history_context = ""
    for m in st.session_state.chat_history[-6:]:
      history_context += f"{m['role'].upper()}: {m['content']}\n"

    chat_prompt = f"""
You are an expert automotive diagnostic technician assisting a mechanic in the field.
Customer: {c_label}
Current Vehicle: {v_label}
Active DTC: {d_label}

Recent Conversation & Test Data:
{history_context}

Respond directly, practically, and concisely to the latest question. Focus on physical shop tests, circuit checks, and logical isolation procedures.
"""
    with st.chat_message("assistant"):
      with st.spinner("Gemini Thinking..."):
        bot_reply = query_gemini(chat_prompt)
        st.markdown(bot_reply)
        st.session_state.chat_history.append(
            {"role": "assistant", "content": bot_reply}
        )

# ========================================================
# --- TAB 5: VEHICLE & DTC LOG ---
# ========================================================
with tab5:
  st.subheader("📋 Vehicle Diagnostic Scan History")
  st.caption("Tracks customer tickets, VINs, and diagnostic fault codes.")

  history = load_log()

  if history:
    st.dataframe(history, use_container_width=True)

    col_csv, col_del = st.columns([1, 1])
    with col_csv:
      csv_data = "Timestamp,Customer,Phone,VIN,Vehicle,Fault Code (DTC)\n"
      for r in history:
        csv_data += f'"{r.get("Timestamp","")}","{r.get("Customer","")}","{r.get("Phone","")}","{r.get("VIN","")}","{r.get("Vehicle","")}","{r.get("Fault Code (DTC)","")}"\n'
      st.download_button(
          label="📥 Export Log to CSV",
          data=csv_data,
          file_name="diagnostic_scan_log.csv",
          mime="text/csv",
      )
    with col_del:
      if st.button("🗑️ Clear Log History"):
        if os.path.exists(LOG_FILE):
          os.remove(LOG_FILE)
        st.success("Log cleared!")
        st.rerun()
  else:
    st.info(
        "No vehicles or DTCs logged yet. Run a code lookup in Tab 3 to start"
        " logging."
    )
