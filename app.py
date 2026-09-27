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
    "📊 Live Telemetry & Mode $06",
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
# --- TAB 2: LIVE TELEMETRY & MODE $06 (DEDICATED) ---
# ========================================================
with tab2:
  st.subheader("📊 Live Telemetry, Mode $06 & AI Data Analysis")

  c_tag = st.session_state.customer_name or "None"
  v_tag = st.session_state.vehicle_info or "No Vehicle Selected"
  d_tag = st.session_state.active_dtc or "None Specified"
  st.info(
      f"📋 **Context:** Customer: `{c_tag}` | Vehicle: `{v_tag}` | Active"
      f" DTC: `{d_tag}`"
  )

  gemini_api_key = get_gemini_key()

  ble_dashboard_template = """
    <div style="background-color: #1A1F26; border: 1px solid #00FF66; padding: 14px; border-radius: 8px; margin-bottom: 1rem;">
        <!-- Control Action Bar -->
        <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 10px;">
            <button id="bleBtn" style="background-color: #00FF66; color: #0E1117; font-weight: 700; font-size: 0.9rem; border: none; padding: 9px 15px; border-radius: 5px; cursor: pointer; display: flex; align-items: center; gap: 6px;">
                <span>⚡</span> Connect Veepeak BLE+
            </button>
            <button id="liveBtn" disabled style="background-color: #2D3748; color: #718096; font-weight: 700; font-size: 0.9rem; border: 1px solid #4A5568; padding: 9px 15px; border-radius: 5px; cursor: not-allowed;">
                ▶️ Start Live Data
            </button>
            <button id="mode6Btn" disabled style="background-color: #2D3748; color: #718096; font-weight: 700; font-size: 0.9rem; border: 1px solid #4A5568; padding: 9px 15px; border-radius: 5px; cursor: not-allowed;">
                🔍 Run Mode $06 Scan
            </button>
            <button id="aiCheckBtn" disabled style="background-color: #2D3748; color: #718096; font-weight: 700; font-size: 0.9rem; border: 1px solid #4A5568; padding: 9px 15px; border-radius: 5px; cursor: not-allowed;">
                🤖 AI Check All Data
            </button>
            <button id="pullVinBtn" disabled style="background-color: #2D3748; color: #718096; font-weight: 700; font-size: 0.9rem; border: 1px solid #4A5568; padding: 9px 15px; border-radius: 5px; cursor: not-allowed;">
                📋 Sync VIN & DTCs
            </button>
        </div>
        <div id="bleStatus" style="color: #A0AEC0; font-family: monospace; font-size: 0.85rem; margin-bottom: 12px;">Status: Ready to pair</div>

        <!-- 18 Real-Time Telemetry PIDs -->
        <div style="font-weight: 700; font-size: 0.9rem; color: #00FF66; margin-bottom: 6px;">📈 LIVE SENSOR TELEMETRY (MODE 01)</div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 8px; max-height: 250px; overflow-y: auto; padding-right: 4px; margin-bottom: 14px;">
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Engine RPM</div>
                <div id="valRpm" style="font-size: 1.2rem; font-weight: 700; color: #00FF66;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Engine Load</div>
                <div id="valLoad" style="font-size: 1.2rem; font-weight: 700; color: #38BDF8;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Speed</div>
                <div id="valSpd" style="font-size: 1.2rem; font-weight: 700; color: #38BDF8;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Throttle (TPS)</div>
                <div id="valTps" style="font-size: 1.2rem; font-weight: 700; color: #E2E8F0;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Coolant (ECT)</div>
                <div id="valEct" style="font-size: 1.2rem; font-weight: 700; color: #F59E0B;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Intake Air (IAT)</div>
                <div id="valIat" style="font-size: 1.2rem; font-weight: 700; color: #F59E0B;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">MAP Sensor</div>
                <div id="valMap" style="font-size: 1.2rem; font-weight: 700; color: #00FF66;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">MAF Flow</div>
                <div id="valMaf" style="font-size: 1.2rem; font-weight: 700; color: #00FF66;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">STFT Bank 1</div>
                <div id="valStft" style="font-size: 1.2rem; font-weight: 700; color: #FBBF24;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">LTFT Bank 1</div>
                <div id="valLtft" style="font-size: 1.2rem; font-weight: 700; color: #FBBF24;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">STFT Bank 2</div>
                <div id="valStft2" style="font-size: 1.2rem; font-weight: 700; color: #FBBF24;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">LTFT Bank 2</div>
                <div id="valLtft2" style="font-size: 1.2rem; font-weight: 700; color: #FBBF24;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Ign Timing</div>
                <div id="valTime" style="font-size: 1.2rem; font-weight: 700; color: #EC4899;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div id="lblO21" style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">O2 B1S1 (V)</div>
                <div id="valO21" style="font-size: 1.2rem; font-weight: 700; color: #A855F7;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">O2 B1S2 (V)</div>
                <div id="valO22" style="font-size: 1.2rem; font-weight: 700; color: #A855F7;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Fuel Pressure</div>
                <div id="valFp" style="font-size: 1.2rem; font-weight: 700; color: #10B981;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Baro Press</div>
                <div id="valBaro" style="font-size: 1.2rem; font-weight: 700; color: #64748B;">--</div>
            </div>
            <div style="background: #111418; border: 1px solid #2D3748; padding: 8px 4px; border-radius: 6px; text-align: center;">
                <div style="font-size: 0.7rem; color: #A0AEC0; text-transform: uppercase;">Battery Volt</div>
                <div id="valVolt" style="font-size: 1.2rem; font-weight: 700; color: #E2E8F0;">--</div>
            </div>
        </div>

        <!-- Mode $06 On-Board Diagnostics Grid -->
        <div style="font-weight: 700; font-size: 0.9rem; color: #38BDF8; margin-bottom: 6px;">📊 MODE $06 ON-BOARD MONITORS & MISFIRE COUNTERS</div>
        <div id="mode6Box" style="background: #111418; border: 1px solid #2D3748; border-radius: 6px; padding: 10px; min-height: 70px; max-height: 200px; overflow-y: auto; font-family: monospace; font-size: 0.85rem; color: #A0AEC0; margin-bottom: 14px;">
            Mode $06 data not scanned yet. Tap "Run Mode $06 Scan" while connected.
        </div>

        <!-- AI Diagnostic Verdict Display Card -->
        <div style="font-weight: 700; font-size: 0.9rem; color: #F59E0B; margin-bottom: 6px;">🤖 AI MASTER TECH TELEMETRY EVALUATION</div>
        <div id="aiVerdictBox" style="background: #111418; border: 1px solid #F59E0B; border-radius: 6px; padding: 12px; min-height: 90px; max-height: 320px; overflow-y: auto; font-size: 0.9rem; line-height: 1.45; color: #FFFFFF;">
            Click "AI Check All Data" to run instantaneous Master Tech cross-correlation on all active PIDs and Mode $06 results.
        </div>
    </div>

    <script>
    const GEMINI_API_KEY = "___GEMINI_KEY___";
    const VEHICLE_CONTEXT = "___VEHICLE_INFO___";
    const DTC_CONTEXT = "___ACTIVE_DTC___";

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
    let supportedPids = new Set();
    let activeO2Cmd = null;
    let activeO2Type = null;
    let mode6RawData = "";

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

    async function sendCmd(cmd, timeoutMs = 1500) {
        while (isBusy) {
            await new Promise(r => setTimeout(r, 20));
        }
        isBusy = true;
        return new Promise(async (resolve) => {
            resolver = resolve;
            responseBuffer = "";
            const enc = new TextEncoder().encode(cmd + "\\r");
            try {
                await rxChar.writeValue(enc);
            } catch (err) {
                isBusy = false;
                resolve("");
                return;
            }
            setTimeout(() => {
                if (resolver) {
                    const fallback = responseBuffer;
                    responseBuffer = "";
                    resolver = null;
                    isBusy = false;
                    resolve(fallback);
                }
            }, timeoutMs);
        });
    }

    function parseCleanHex(raw) {
        return raw.replace(/\\s+/g, '').toUpperCase();
    }

    function parsePidBytes(hexStr, basePid) {
        let clean = parseCleanHex(hexStr);
        let m = clean.match(new RegExp("41" + basePid + "([0-9A-F]{8})"));
        if (m) {
            let bytesHex = m[1];
            let baseNum = parseInt(basePid, 16);
            for (let b = 0; b < 4; b++) {
                let byteVal = parseInt(bytesHex.substr(b * 2, 2), 16);
                for (let bit = 0; bit < 8; bit++) {
                    if ((byteVal & (0x80 >> bit)) !== 0) {
                        let pidNum = baseNum + 1 + (b * 8) + bit;
                        let pidHex = pidNum.toString(16).toUpperCase().padStart(2, '0');
                        supportedPids.add(pidHex);
                    }
                }
            }
        }
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

    async function runLiveLoop() {
        while (isStreaming) {
            // RPM
            if (supportedPids.has("0C") || supportedPids.size === 0) {
                let res = await sendCmd("010C", 600);
                let m = parseCleanHex(res).match(/410C([0-9A-F]{4})/);
                if (m) {
                    let a = parseInt(m[1].substr(0, 2), 16);
                    let b = parseInt(m[1].substr(2, 2), 16);
                    document.getElementById('valRpm').innerText = Math.round(((a * 256) + b) / 4) + " RPM";
                }
            }
            if (!isStreaming) break;

            // Load
            if (supportedPids.has("04")) {
                let res = await sendCmd("0104", 600);
                let m = parseCleanHex(res).match(/4104([0-9A-F]{2})/);
                if (m) document.getElementById('valLoad').innerText = Math.round((parseInt(m[1], 16) * 100) / 255) + "%";
            }
            if (!isStreaming) break;

            // TPS
            if (supportedPids.has("11")) {
                let res = await sendCmd("0111", 600);
                let m = parseCleanHex(res).match(/4111([0-9A-F]{2})/);
                if (m) document.getElementById('valTps').innerText = Math.round((parseInt(m[1], 16) * 100) / 255) + "%";
            }
            if (!isStreaming) break;

            // ECT (Coolant)
            if (supportedPids.has("05") || supportedPids.size === 0) {
                let res = await sendCmd("0105", 600);
                let m = parseCleanHex(res).match(/4105([0-9A-F]{2})/);
                if (m) document.getElementById('valEct').innerText = Math.round((parseInt(m[1], 16) - 40) * 1.8 + 32) + " °F";
            }
            if (!isStreaming) break;

            // IAT (Intake Air)
            if (supportedPids.has("0F")) {
                let res = await sendCmd("010F", 600);
                let m = parseCleanHex(res).match(/410F([0-9A-F]{2})/);
                if (m) document.getElementById('valIat').innerText = Math.round((parseInt(m[1], 16) - 40) * 1.8 + 32) + " °F";
            }
            if (!isStreaming) break;

            // STFT / LTFT Bank 1
            if (supportedPids.has("06")) {
                let res = await sendCmd("0106", 600);
                let m = parseCleanHex(res).match(/4106([0-9A-F]{2})/);
                if (m) {
                    let s = (((parseInt(m[1], 16) - 128) * 100) / 128).toFixed(1);
                    document.getElementById('valStft').innerText = (s > 0 ? "+" : "") + s + "%";
                }
            }
            if (!isStreaming) break;

            if (supportedPids.has("07")) {
                let res = await sendCmd("0107", 600);
                let m = parseCleanHex(res).match(/4107([0-9A-F]{2})/);
                if (m) {
                    let l = (((parseInt(m[1], 16) - 128) * 100) / 128).toFixed(1);
                    document.getElementById('valLtft').innerText = (l > 0 ? "+" : "") + l + "%";
                }
            }
            if (!isStreaming) break;

            // STFT / LTFT Bank 2
            if (supportedPids.has("08")) {
                let res = await sendCmd("0108", 600);
                let m = parseCleanHex(res).match(/4108([0-9A-F]{2})/);
                if (m) {
                    let s2 = (((parseInt(m[1], 16) - 128) * 100) / 128).toFixed(1);
                    document.getElementById('valStft2').innerText = (s2 > 0 ? "+" : "") + s2 + "%";
                }
            }
            if (!isStreaming) break;

            if (supportedPids.has("09")) {
                let res = await sendCmd("0109", 600);
                let m = parseCleanHex(res).match(/4109([0-9A-F]{2})/);
                if (m) {
                    let l2 = (((parseInt(m[1], 16) - 128) * 100) / 128).toFixed(1);
                    document.getElementById('valLtft2').innerText = (l2 > 0 ? "+" : "") + l2 + "%";
                }
            }
            if (!isStreaming) break;

            // MAF & Speed
            if (supportedPids.has("10")) {
                let res = await sendCmd("0110", 600);
                let m = parseCleanHex(res).match(/4110([0-9A-F]{4})/);
                if (m) {
                    let a = parseInt(m[1].substr(0, 2), 16);
                    let b = parseInt(m[1].substr(2, 2), 16);
                    document.getElementById('valMaf').innerText = (((a * 256) + b) / 100).toFixed(1) + " g/s";
                }
            }
            if (!isStreaming) break;

            if (supportedPids.has("0D")) {
                let res = await sendCmd("010D", 600);
                let m = parseCleanHex(res).match(/410D([0-9A-F]{2})/);
                if (m) document.getElementById('valSpd').innerText = Math.round(parseInt(m[1], 16) * 0.621371) + " MPH";
            }
            if (!isStreaming) break;

            // Timing Advance
            if (supportedPids.has("0E")) {
                let res = await sendCmd("010E", 600);
                let m = parseCleanHex(res).match(/410E([0-9A-F]{2})/);
                if (m) document.getElementById('valTime').innerText = ((parseInt(m[1], 16) / 2) - 64).toFixed(1) + "°";
            }
            if (!isStreaming) break;

            // Upstream O2 B1S1 (Narrowband or Wideband Lambda)
            if (activeO2Cmd) {
                let res = await sendCmd(activeO2Cmd, 600);
                let clean = parseCleanHex(res);
                if (activeO2Type === "14") {
                    let m = clean.match(/4114([0-9A-F]{2})/);
                    if (m) document.getElementById('valO21').innerText = (parseInt(m[1], 16) / 200).toFixed(2) + "V";
                } else {
                    let pfx = "41" + activeO2Cmd.substr(2, 2);
                    let m = clean.match(new RegExp(pfx + "([0-9A-F]{4})"));
                    if (m) {
                        let a = parseInt(m[1].substr(0, 2), 16);
                        let b = parseInt(m[1].substr(2, 2), 16);
                        let lambda = (((a * 256) + b) / 32768).toFixed(2);
                        document.getElementById('valO21').innerText = "λ " + lambda;
                    }
                }
            }
            if (!isStreaming) break;

            // Downstream O2 B1S2
            if (supportedPids.has("15")) {
                let res = await sendCmd("0115", 600);
                let m = parseCleanHex(res).match(/4115([0-9A-F]{2})/);
                if (m) document.getElementById('valO22').innerText = (parseInt(m[1], 16) / 200).toFixed(2) + "V";
            }
            if (!isStreaming) break;

            // Baro Press
            if (supportedPids.has("33")) {
                let res = await sendCmd("0133", 600);
                let m = parseCleanHex(res).match(/4133([0-9A-F]{2})/);
                if (m) document.getElementById('valBaro').innerText = (parseInt(m[1], 16) * 0.2953).toFixed(1) + " inHg";
            }
            if (!isStreaming) break;

            // Charging Voltage
            let resVolt = await sendCmd("ATRV", 600);
            let vMatch = resVolt.match(/([0-9]+\.[0-9]+)/);
            if (vMatch) document.getElementById('valVolt').innerText = vMatch[1] + "V";

            await new Promise(r => setTimeout(r, 40));
        }
    }

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

            log("Handshaking with ECM...");
            await sendCmd("ATZ");
            await sendCmd("ATE0");
            await sendCmd("ATL0");
            await sendCmd("ATSP0");
            await sendCmd("ATST32"); // fast response timeout

            log("Detecting vehicle supported PIDs...");
            supportedPids.clear();
            let p00 = await sendCmd("0100", 1000);
            parsePidBytes(p00, "00");
            let p20 = await sendCmd("0120", 1000);
            parsePidBytes(p20, "20");

            // Auto-Detect Upstream O2 Sensor Format (Narrowband vs Wideband Lambda)
            activeO2Cmd = null;
            activeO2Type = null;
            for (let probe of [
                {cmd: "0114", type: "14", isWide: false},
                {cmd: "0124", type: "24", isWide: true},
                {cmd: "0134", type: "34", isWide: true},
                {cmd: "0122", type: "22", isWide: true},
                {cmd: "0132", type: "32", isWide: true}
            ]) {
                let r = await sendCmd(probe.cmd, 700);
                if (parseCleanHex(r).includes("41" + probe.cmd.substr(2, 2))) {
                    activeO2Cmd = probe.cmd;
                    activeO2Type = probe.type;
                    if (probe.isWide) {
                        document.getElementById('lblO21').innerText = "O2 B1S1 (A/F λ)";
                    }
                    break;
                }
            }

            // Mark truly unsupported PIDs as N/A on UI
            if (supportedPids.size > 0) {
                if (!supportedPids.has("0B")) document.getElementById('valMap').innerText = "N/A";
                if (!supportedPids.has("10")) document.getElementById('valMaf').innerText = "N/A";
                if (!supportedPids.has("08")) document.getElementById('valStft2').innerText = "N/A (1 Bank)";
                if (!supportedPids.has("09")) document.getElementById('valLtft2').innerText = "N/A (1 Bank)";
                if (!supportedPids.has("0A")) document.getElementById('valFp').innerText = "N/A";
                if (!supportedPids.has("33")) document.getElementById('valBaro').innerText = "N/A";
                if (!activeO2Cmd) document.getElementById('valO21').innerText = "N/A";
                if (!supportedPids.has("15")) document.getElementById('valO22').innerText = "N/A";
            }

            log("Connected to ECM! Telemetry & Mode $06 Ready (" + supportedPids.size + " PIDs active).");

            // Activate Buttons
            const liveBtn = document.getElementById('liveBtn');
            liveBtn.disabled = false;
            liveBtn.style.backgroundColor = '#38BDF8';
            liveBtn.style.color = '#0E1117';
            liveBtn.style.cursor = 'pointer';

            const m6Btn = document.getElementById('mode6Btn');
            m6Btn.disabled = false;
            m6Btn.style.backgroundColor = '#10B981';
            m6Btn.style.color = '#0E1117';
            m6Btn.style.cursor = 'pointer';

            const aiBtn = document.getElementById('aiCheckBtn');
            aiBtn.disabled = false;
            aiBtn.style.backgroundColor = '#F59E0B';
            aiBtn.style.color = '#0E1117';
            aiBtn.style.cursor = 'pointer';

            const pullBtn = document.getElementById('pullVinBtn');
            pullBtn.disabled = false;
            pullBtn.style.backgroundColor = '#A855F7';
            pullBtn.style.color = '#FFFFFF';
            pullBtn.style.cursor = 'pointer';

        } catch (err) {
            log("Error: " + err.message);
        }
    });

    document.getElementById('liveBtn').addEventListener('click', () => {
        const liveBtn = document.getElementById('liveBtn');
        if (!isStreaming) {
            isStreaming = true;
            liveBtn.innerText = "⏸️ Pause Stream";
            liveBtn.style.backgroundColor = "#EF4444";
            liveBtn.style.color = "#FFFFFF";
            log("Streaming live telemetry...");
            runLiveLoop();
        } else {
            isStreaming = false;
            liveBtn.innerText = "▶️ Start Live Data";
            liveBtn.style.backgroundColor = "#38BDF8";
            liveBtn.style.color = "#0E1117";
            log("Stream paused.");
        }
    });

    document.getElementById('mode6Btn').addEventListener('click', async () => {
        const wasStreaming = isStreaming;
        isStreaming = false;
        document.getElementById('liveBtn').innerText = "▶️ Start Live Data";
        document.getElementById('liveBtn').style.backgroundColor = "#38BDF8";

        log("Pausing telemetry to scan Mode $06...");
        while (isBusy) {
            await new Promise(r => setTimeout(r, 25));
        }

        const m6Box = document.getElementById('mode6Box');
        m6Box.innerHTML = "<div style='color: #F59E0B; padding: 4px;'>⚡ Fast Scanning Cylinder Misfire Monitors (Mode $06)...</div>";

        await sendCmd("ATST32", 500);

        // Step 1: Query which cylinder MIDs exist via $A0 bitmask
        let a0Res = await sendCmd("06A0", 800);
        let cleanA0 = a0Res.replace(/^[0-9A-F]{1,2}:/gm, '').replace(/[\\r\\n\\s>]+/g, '').toUpperCase();
        let targetMids = [];

        let a0Match = cleanA0.match(/46A0([0-9A-F]{8})/);
        if (a0Match) {
            let b1 = parseInt(a0Match[1].substr(0, 2), 16);
            let b2 = parseInt(a0Match[1].substr(2, 2), 16);
            if ((b1 & 0x40) !== 0) targetMids.push("06A2");
            if ((b1 & 0x20) !== 0) targetMids.push("06A3");
            if ((b1 & 0x10) !== 0) targetMids.push("06A4");
            if ((b1 & 0x08) !== 0) targetMids.push("06A5");
            if ((b1 & 0x04) !== 0) targetMids.push("06A6");
            if ((b1 & 0x02) !== 0) targetMids.push("06A7");
            if ((b1 & 0x01) !== 0) targetMids.push("06A8");
            if ((b2 & 0x80) !== 0) targetMids.push("06A9");
        }

        // Fallback: If 06A0 bitmask wasn't returned, query cylinders matching engine bank layout
        if (targetMids.length === 0) {
            let hasBank2 = supportedPids.has("08") || supportedPids.has("09") || (document.getElementById('valStft2').innerText !== "N/A" && document.getElementById('valStft2').innerText !== "--");
            targetMids = hasBank2 ? ["06A2", "06A3", "06A4", "06A5", "06A6", "06A7"] : ["06A2", "06A3", "06A4", "06A5"];
        }

        const cylMap = {
            'A2': 'Cylinder 1', 'A3': 'Cylinder 2', 'A4': 'Cylinder 3', 'A5': 'Cylinder 4',
            'A6': 'Cylinder 5', 'A7': 'Cylinder 6', 'A8': 'Cylinder 7', 'A9': 'Cylinder 8'
        };

        let htmlGrid = "<div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 8px;'>";
        let foundAny = false;
        mode6RawData = "";

        for (let midCmd of targetMids) {
            let midCode = midCmd.substr(2, 2);
            log("Reading " + cylMap[midCode] + " misfires (" + midCmd + ")...");

            let res = await sendCmd(midCmd, 900);
            mode6RawData += "\\n" + res;

            let clean = res.replace(/^[0-9A-F]{1,2}:/gm, '').replace(/[\\r\\n\\s>]+/g, '').toUpperCase();
            let m = clean.match(/46(A[2-9])([0-9A-F]{2})([0-9A-F]{2})([0-9A-F]{4})/);

            if (m) {
                foundAny = true;
                let count = parseInt(m[4], 16);
                let color = count === 0 ? "#00FF66" : "#EF4444";
                let statusText = count === 0 ? "PASS (0 ct)" : "MISFIRES: " + count;
                htmlGrid += "<div style='background: #1A1F26; border: 1px solid " + color + "; padding: 8px; border-radius: 6px; text-align: center;'>";
                htmlGrid += "<div style='color: #38BDF8; font-weight: 700; font-size: 0.85rem;'>" + cylMap[m[1]] + "</div>";
                htmlGrid += "<div style='color: " + color + "; font-size: 1.05rem; font-weight: 700;'>" + statusText + "</div>";
                htmlGrid += "</div>";
                m6Box.innerHTML = htmlGrid + "</div>";
            }
        }

        if (!foundAny) {
            m6Box.innerHTML = "<div style='color: #A0AEC0; padding: 4px;'>Raw Mode $06 Output:<br><pre style='white-space: pre-wrap; font-size: 0.75rem;'>" + (mode6RawData.trim() || "No response bytes from ECM.") + "</pre></div>";
        }

        log("Mode $06 complete. " + (foundAny ? "All misfire monitors verified." : ""));

        if (wasStreaming) {
            isStreaming = true;
            document.getElementById('liveBtn').innerText = "⏸️ Pause Stream";
            document.getElementById('liveBtn').style.backgroundColor = "#EF4444";
            runLiveLoop();
        }
    });

    document.getElementById('aiCheckBtn').addEventListener('click', async () => {
        const vBox = document.getElementById('aiVerdictBox');
        if (!GEMINI_API_KEY) {
            vBox.innerHTML = "<span style='color: #EF4444;'>Error: GEMINI_API_KEY is missing from Streamlit Secrets.</span>";
            return;
        }

        vBox.innerHTML = "<span style='color: #F59E0B;'>🤖 Gemini 2.5 Flash is analyzing live telemetry and Mode $06 data...</span>";

        const pids = {
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
            "Timing": document.getElementById('valTime').innerText,
            "O2_B1S1": document.getElementById('valO21').innerText,
            "O2_B1S2": document.getElementById('valO22').innerText,
            "FuelPressure": document.getElementById('valFp').innerText,
            "Baro": document.getElementById('valBaro').innerText,
            "Voltage": document.getElementById('valVolt').innerText
        };

        const prompt = `
You are an expert ASE Master / L1 Diagnostic Technician.
Perform a full diagnostic telemetry check for this vehicle:
Vehicle: ${VEHICLE_CONTEXT}
Active DTC: ${DTC_CONTEXT}

LIVE STREAMING SENSOR DATA (MODE 01):
${JSON.stringify(pids, null, 2)}

MODE $06 RAW & PARSED DATA:
${mode6RawData || "No Mode 6 scanned yet"}

DIAGNOSTIC TASK:
1. Fuel Control & Trim Analysis: Total Trim (STFT + LTFT) on Bank 1 & 2. Lean vs Rich condition, vacuum leak (high trim at idle, drops at 2500 RPM) vs fuel starvation (lean under load) vs MAF under-reporting.
2. Air & Pressure Integrity: Is MAF/MAP plausible for the current RPM and calculated load?
3. O2 Sensor Health & Catalyst State: Upstream switching vs downstream cat holding steady.
4. Mode $06 / Misfire Evaluation: Any individual cylinder misfire spikes or monitor failures.
5. Exact Condemnation or Next Isolation Step: Precise mechanical/electrical check to perform next.

Format clearly with bold sections. Keep it direct and shop-focused.
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

  components.html(ble_html, height=820)

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
