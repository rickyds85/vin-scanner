import os
import re
from PIL import Image
import requests
import streamlit as st
import zxingcpp

st.set_page_config(
    page_title="Pro Auto Diagnostic Tool", page_icon="🔧", layout="wide"
)
st.title("🚗 Pro Auto Diagnostic & VIN Tool")

# Store persistent session state across tabs
if "vehicle_info" not in st.session_state:
  st.session_state.vehicle_info = ""
if "active_dtc" not in st.session_state:
  st.session_state.active_dtc = ""
if "chat_history" not in st.session_state:
  st.session_state.chat_history = []

tab1, tab2, tab3 = st.tabs([
    "📷 VIN Scanner",
    "🔧 In-Depth Diagnostic Strategy",
    "⚡ Copilot & Scope Lab",
])


# Helper function to call Perplexity Agent API
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
    return (
        "Request timed out. Please try again or switch to 'Fast' preset in"
        " Tab 2."
    )
  except Exception as e:
    return f"Unexpected error: {e}"


# ========================================================
# --- TAB 1: VIN SCANNER ---
# ========================================================
with tab1:
  st.subheader("Vehicle Identification")

  def decode_vin(vin_code: str) -> dict | None:
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/{vin_code}?format=json"
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

  photo = st.camera_input("Snap a photo of the door jamb barcode")
  found_vin = ""

  if photo:
    st.image(photo, caption="Captured Image", use_container_width=True)
    img = Image.open(photo)
    barcodes = zxingcpp.read_barcodes(img)
    for b in barcodes:
      match = re.search(r"[A-HJ-NPR-Z0-9]{17}", b.text.upper())
      if match:
        found_vin = match.group(0)
        break

    if found_vin:
      st.success(f"Barcode Detected! VIN: **{found_vin}**")
    else:
      st.warning("No barcode detected. Ensure barcode is centered and clear.")

  vin = st.text_input(
      "Enter 17-digit VIN manually:", value=found_vin, max_chars=17
  )
  active_vin = vin.strip().upper()

  if active_vin and (found_vin or st.button("Decode VIN")):
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

  if st.session_state.vehicle_info:
    st.success(f"Active Vehicle: **{st.session_state.vehicle_info}**")
  else:
    st.caption("Tip: Decode a vehicle in Tab 1 to carry vehicle specs over.")

  col_input, col_preset, col_btn = st.columns([3, 2, 1.5])
  with col_input:
    code_input = (
        st.text_input(
            "Enter OBD-II DTC (e.g., P0316, P0300, U0100, P0420):",
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
    dtc_prompt = f"""
You are a master ASE-certified automotive diagnostic technician. Provide an in-depth, practical field diagnostic testing workflow for fault code {code_input} on a {vehicle}.

Format strictly using these Markdown sections:

### Code Definition & Severity
- Exact Code Definition
- Severity level and drivability symptoms

### 1. PIDs & Scan Tool Verification
- Top 4-5 live data PIDs to graph and their normal expected values
- Step-by-step scan tool strategy (Mode $06, freeze frame checks, idle vs 2500 RPM rules)

### 2. Electrical & Scope Testing (DMM / Scope)
- Step-by-step multimeter and oscilloscope checks (voltage drop thresholds, ground tests, sensor signal wire specs)
- Expected waveforms or current ramp specs (if applicable)

### 3. Mechanical & Physical Testing
- Physical tests (smoke testing, fuel pressure hold/leakdown tests, relative compression, vacuum checks)

### 4. Known Platform Pattern Failures & TSBs
- Specific common real-world failure points, harness rub spots, or known TSBs for {vehicle}
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
  st.info(f"📋 **Context:** Vehicle: `{v_label}` | Active DTC: `{d_label}`")

  col_scope, col_scratch = st.columns([1, 1])

  with col_scope:
    st.markdown("#### 📸 Scope & Meter Display Capture")
    scope_capture = st.camera_input(
        "Capture oscilloscope screen or meter reading"
    )
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
              " only 35V; CKP missing tooth has uneven spacing during crank"
          ),
          height=70,
      )

  # Button to evaluate all scratchpad data
  if st.button("🔍 Analyze Entered Test Results & Scope Data"):
    test_summary = f"""
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

  # Display chat history
  for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
      st.markdown(msg["content"])

  user_question = st.chat_input(
      "Ask a diagnostic question (e.g., 'How do I isolate a leaking injector"
      " from a bad pump check valve?')"
  )

  if user_question:
    # Add user message to UI
    st.session_state.chat_history.append(
        {"role": "user", "content": user_question}
    )
    with st.chat_message("user"):
      st.markdown(user_question)

    # Build conversation context
    history_context = ""
    for m in st.session_state.chat_history[-6:]:  # Keep recent turns
      history_context += f"{m['role'].upper()}: {m['content']}\n"

    chat_prompt = f"""
You are an expert automotive diagnostic technician assisting a mechanic in the field.
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
