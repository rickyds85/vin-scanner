import os
import re
from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    RateLimitError,
)
from PIL import Image
import requests
import streamlit as st
import zxingcpp

st.set_page_config(
    page_title="Pro Auto Diagnostic Tool", page_icon="🔧", layout="wide"
)
st.title("🚗 Pro Auto Diagnostic & VIN Tool")

# Store vehicle info across tabs
if "vehicle_info" not in st.session_state:
  st.session_state.vehicle_info = ""

tab1, tab2 = st.tabs(["📷 VIN Scanner", "🔧 In-Depth Diagnostic Strategy"])

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

  col_input, col_model, col_btn = st.columns([3, 2, 1.5])
  with col_input:
    code_input = (
        st.text_input("Enter OBD-II DTC (e.g., P0316, P0300, U0100, P0420):")
        .strip()
        .upper()
    )
  with col_model:
    model_choice = st.selectbox(
        "AI Diagnostic Model",
        options=["sonar-pro", "sonar"],
        index=0,
        help=(
            "Sonar Pro pulls comprehensive real-world diagnostic trees and"
            " known TSBs."
        ),
    )
  with col_btn:
    st.write("")
    lookup_clicked = st.button("Run Diagnostic Tree", use_container_width=True)

  if code_input and lookup_clicked:
    # Safely load API key from environment or Streamlit secrets
    api_key = os.environ.get("PERPLEXITY_API_KEY")
    if not api_key and hasattr(st, "secrets"):
      api_key = st.secrets.get("PERPLEXITY_API_KEY")

    if not api_key:
      st.error("PERPLEXITY_API_KEY is not configured in Streamlit Secrets.")
    else:
      vehicle = st.session_state.vehicle_info or "General OBD-II Vehicle"
      prompt = f"""
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

      with st.spinner(f"Generating diagnostic tree for {code_input}..."):
        try:
          client = OpenAI(
              api_key=api_key,
              base_url="https://api.perplexity.ai",
          )

          response = client.chat.completions.create(
              model=model_choice,
              messages=[
                  {
                      "role": "system",
                      "content": (
                          "You are an expert automotive diagnostic technician."
                          " Provide precise, actionable diagnostic trees."
                      ),
                  },
                  {"role": "user", "content": prompt},
              ],
          )

          if response.choices and len(response.choices) > 0:
            st.markdown(response.choices[0].message.content)
          else:
            st.warning("No diagnostic data returned.")

        except AuthenticationError:
          st.error(
              "Authentication failed (HTTP 401). Check your PERPLEXITY_API_KEY"
              " in Streamlit secrets."
          )
        except BadRequestError as e:
          st.error(f"Bad Request (HTTP 400): {e.message}")
        except RateLimitError:
          st.error(
              "Rate limit reached (HTTP 429). Please wait a moment and try"
              " again."
          )
        except APIStatusError as e:
          st.error(f"API Error ({e.status_code}): {e.message}")
        except APIConnectionError:
          st.error(
              "Network connection error to Perplexity. Check internet"
              " connectivity."
          )
        except Exception as e:
          st.error(f"Unexpected error: {e}")
