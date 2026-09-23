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
  """Appends a diagnostic entry to local CSV log with customer info."""
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
  """Reads the CSV file and returns list of dictionaries."""
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


# --- GEMINI HELPERS (TEXT & VISION) ---
def get_gemini_key() -> str:
  key = os.environ.get("GEMINI_API_KEY")
  if not key and hasattr(st, "secrets"):
    key = st.secrets.get("GEMINI_API_KEY")
  return key or ""


def query_gemini(prompt_text: str, system_instruction: str = "") -> str:
  """Sends text prompt to Gemini 2.5 Flash."""
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
  """Uses Gemini Vision to visually inspect oscilloscope / meter images alongside physical test data."""
  gemini_key = get_gemini_key()
  if not gemini_key:
    return "Error: GEMINI_API_KEY is missing from Streamlit Secrets."

  prompt = f"""
You are an expert ASE Master / L1 diagnostic technician and automotive oscilloscope waveform specialist.
Analyze this oscilloscope or multimeter capture alongside the physical test readings from the shop floor.

PHYSICAL TEST DATA & CONTEXT:
{test_summary}

SCOPE / METER VISION TASK:
- If an image is provided: identify the signal type (Secondary/Primary Ignition, Injector Voltage/Current, CKP/CMP correlation, Relative Compression, PWM, Sensor 5V/Ground drop).
- Evaluate critical electrical signatures: peak firing/inductive spike kV, dwell/charge duration, spark burn line slope & turbulence, coil oscillations/ringing count, ground bounce, signal attenuation, or missing-tooth spacing.
- Correlate waveform abnormalities directly with the physical readings (compression, fuel pressure, voltage drop).

FORMAT STRICTLY AS:
### 1. Scope Waveform & Electrical Findings
- Key waveform observations, time-base / voltage scale notes, and circuit anomalies observed in the photo.
### 2. Component Condemnation & Defect Root Cause
- What exact component, circuit, or mechanical issue is failing based on this waveform and test data?
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
  """Uses Gemini Vision to read 17-digit printed VIN text from stickers, windshields, or paperwork."""
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
                        " Identification Number (VIN) from this vehicle image"
                        " (door jamb sticker, windshield plate, paperwork, or"
                        " registration). Standard VINs only use digits and"
                        " uppercase letters excluding I, O, and Q. Return ONLY"
                        " the 17-character VIN. If none is found, return 'NONE'."
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
  """Uses Gemini Vision to extract Customer Name, Address, and Phone Number from paperwork."""
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


tab1, tab2, tab3, tab4 = st.tabs([
    "📷 VIN & Customer Info",
    "🔧 In-Depth Diagnostic Strategy",
    "⚡ Copilot & Scope Lab",
    "📋 Vehicle & DTC Log",
])

# ========================================================
# --- TAB 1: VIN & CUSTOMER INFO ---
# ========================================================
with tab1:
  st.subheader("Customer & Vehicle Identification")

  # Customer Info Section
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
  st.markdown("#### 📸 Vehicle VIN Photo / Barcode Scanner")
  st.caption(
      "Snap or upload any photo of the door jamb sticker, windshield plate,"
      " registration, or work order."
  )

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

    # 1. Try barcode first
    found_vin = scan_vin_barcode(img)
    detection_method = "Barcode"

    # 2. If no barcode found, automatically run Gemini Vision OCR
    if not found_vin:
      with st.spinner("Scanning photo text with AI Vision for 17-digit VIN..."):
        found_vin = extract_vin_via_ai(img)
        detection_method = "AI Photo Text Recognition"

    if found_vin:
      st.session_state.active_vin = found_vin
      st.success(f"VIN Detected ({detection_method})! **{found_vin}**")
    else:
      st.warning(
          "Could not detect a 17-digit VIN. Make sure all characters are"
          " visible and legible, or enter manually below."
      )

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
      "Enter 17-digit VIN manually:",
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
# --- TAB 2: IN-DEPTH DTC DIAGNOSTIC STRATEGY ---
# ========================================================
with tab2:
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
        help="Gemini provides deep circuit & mechanical logic; Perplexity checks live technical databases and TSBs.",
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
    with st.spinner(f"Generating {code_input} strategy via {ai_engine.upper()}..."):
      if ai_engine == "gemini":
        result = query_gemini(dtc_prompt)
      else:
        result = query_perplexity(dtc_prompt, preset="low")
      st.markdown(result)

# ========================================================
# --- TAB 3: DIAGNOSTIC COPILOT & SCOPE LAB ---
# ========================================================
with tab3:
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
    with st.spinner("Gemini Vision is analyzing waveform signatures and physical readings..."):
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
# --- TAB 4: VEHICLE & DTC LOG ---
# ========================================================
with tab4:
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
        "No vehicles or DTCs logged yet. Run a code lookup in Tab 2 to start"
        " logging."
    )
