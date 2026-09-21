import csv
from datetime import datetime
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
    return "Request timed out. Please try again or switch preset to 'Fast'."
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
  enhancer = ImageEnhance.Contrast(gray)
  high_contrast = enhancer.enhance(2.2)

  barcodes = zxingcpp.read_barcodes(
      high_contrast, try_rotate=True, try_downscale=True, try_invert=True
  )
  for b in barcodes:
    match = re.search(r"[A-HJ-NPR-Z0-9]{17}", b.text.upper())
    if match:
      return match.group(0)

  sharp = ImageEnhance.Sharpness(high_contrast).enhance(2.5)
  barcodes = zxingcpp.read_barcodes(
      sharp, try_rotate=True, try_downscale=True, try_invert=True
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

  # --- Customer Info Inputs ---
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

  # Display pinned summary badge if customer is entered
  if st.session_state.customer_name:
    st.markdown(f"""
        <div style="background-color: #1E232A; border-left: 4px solid #00FF66; padding: 12px 16px; border-radius: 6px; margin: 0.8rem 0 1.2rem 0;">
            <div style="font-size: 1.1rem; font-weight: 700; color: #FFFFFF;">👤 {st.session_state.customer_name}</div>
            <div style="color: #A0AEC0; font-size: 0.95rem;">📍 {st.session_state.customer_address or 'No address provided'}</div>
            <div style="color: #A0AEC0; font-size: 0.95rem;">📞 {st.session_state.customer_phone or 'No phone number'}</div>
        </div>
        """, unsafe_allow_html=True)

  st.write("---")
  st.markdown("#### 🚪 Vehicle VIN Barcode Scanner")

  col_cam, col_up = st.columns([1, 1])
  with col_cam:
    open_camera = st.toggle("📷 Open Camera Scanner", value=False)
    photo = None
    if open_camera:
      photo = st.camera_input("Snap door jamb barcode")

  with col_up:
    uploaded_label = st.file_uploader(
        "Or upload a photo of the barcode",
        type=["png", "jpg", "jpeg"],
        key="vin_upload",
    )

  active_image = photo or uploaded_label
  found_vin = ""

  if active_image:
    st.image(
        active_image, caption="Captured Barcode", use_container_width=True
    )
    img = Image.open(active_image)
    found_vin = scan_vin_barcode(img)

    if found_vin:
      st.session_state.active_vin = found_vin
      st.success(f"Barcode Detected! VIN: **{found_vin}**")
    else:
      st.warning(
          "No barcode detected. Tilt slightly to avoid glare or type VIN below."
      )

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
        f" `{st.session_state.customer_phone or 'No phone'}` | 📍"
        f" `{st.session_state.customer_address or 'No address'}`"
    )

  if st.session_state.vehicle_info:
    st.success(
        f"Active Vehicle: **{st.session_state.vehicle_info}** (VIN:"
        f" `{st.session_state.active_vin or 'Manual'}`)"
    )
  else:
    st.caption("Tip: Decode a vehicle in Tab 1 to carry vehicle specs over.")

  col_input, col_preset, col_btn = st.columns([3, 2, 1.5])
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

  with col_preset:
    preset_choice = st.selectbox(
        "Diagnostic Depth",
        options=["low", "medium", "fast"],
        index=0,
        format_func=lambda x: {
            "low": "Sonar Pro (Detailed TSBs & PIDs)",
            "medium": "Reasoning Pro (Deep Scope & Logic)",
            "fast": "Fast (Quick Overview)",
        }[x],
        help="Controls depth of diagnostic testing and live web research.",
    )
  with col_btn:
    st.write("")
    lookup_clicked = st.button("Run Diagnostic Tree", use_container_width=True)

  if code_input and lookup_clicked:
    vehicle = st.session_state.vehicle_info or "General OBD-II Vehicle"

    # Automatically save Customer, Phone, VIN, Vehicle, and Code to local log
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
        f"Querying Perplexity Agent API for {code_input} diagnostic tree..."
    ):
      result = query_perplexity(dtc_prompt, preset=preset_choice)
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
    if active_img:
      st.image(active_img, caption="Captured Scope / Meter Display")

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

  if st.button("🔍 Analyze Entered Test Results & Scope Data"):
    test_summary = f"""
Customer: {c_label}
Vehicle: {v_label}
Active DTC: {d_label}
Compression/Leakdown: {comp_data or 'Not tested'}
Fuel Pressure & Bleed-down: {fuel_data or 'Not tested'}
Voltage Drop / Electrical: {volt_data or 'Not tested'}
Scope Observations: {scope_notes or 'None reported'}
"""
    copilot_prompt = f"""
You are an expert diagnostic master technician. Analyze these real-world shop test results and scope observations:

{test_summary}

Provide a concise, direct diagnostic breakdown:
1. **Critical Findings:** Identify which values fail specifications or show circuit/mechanical defects.
2. **Component Condemnation or Next Check:** What specific part is failing, or what exact pinpoint test isolates the culprit?
3. **Common Trap to Avoid:** What mistake or misdiagnosis frequently happens with these specific readings?
"""
    with st.spinner("Analyzing test data..."):
      eval_res = query_perplexity(copilot_prompt, preset="low")
      st.markdown("### Diagnostic Evaluation")
      st.markdown(eval_res)

  st.write("---")
  st.markdown("#### 💬 Interactive Diagnostic Copilot")
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
      with st.spinner("Thinking..."):
        bot_reply = query_perplexity(chat_prompt, preset="low")
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
