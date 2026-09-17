import re
from PIL import Image
import requests
import streamlit as st
import zxingcpp

st.set_page_config(page_title="Auto Diagnostic Tool", page_icon="🚗")
st.title("🚗 Auto Diagnostic & VIN Tool")

# Tabs for easy switching between VIN Scanner and Code Lookup
tab1, tab2 = st.tabs(["📷 VIN Scanner", "🔧 DTC Code Lookup"])

# --- TAB 1: VIN SCANNER ---
with tab1:
  st.subheader("Vehicle Identification")


  def decode_vin(vin_code):
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
      st.subheader(f"Vehicle Specifications ({active_vin})")
      for key, val in details.items():
        st.write(f"**{key}:** {val}")
    else:
      st.error("Could not find vehicle details. Check the VIN and try again.")


# --- TAB 2: DTC CODE LOOKUP ---
with tab2:
  st.subheader("OBD-II Fault Code Diagnostic Lookup")

  DTC_DATABASE = {
      "P0300": {
          "name": "Random / Multiple Cylinder Misfire Detected",
          "causes": [
              "Worn spark plugs or ignition coils",
              "Vacuum leak / unmetered air",
              "Low fuel pressure or clogged injectors",
              "Low engine cylinder compression",
          ],
          "checks": (
              "Check live misfire counters per cylinder; inspect spark plug"
              " condition and fuel trims."
          ),
      },
      "P0420": {
          "name": "Catalyst System Efficiency Below Threshold (Bank 1)",
          "causes": [
              "Failing catalytic converter",
              "Exhaust leak before or near converter",
              "Downstream oxygen sensor bias",
              "Engine running excessively rich or lean",
          ],
          "checks": (
              "Graph upstream vs downstream O2 sensor voltages at operating"
              " temp; verify no exhaust leaks."
          ),
      },
      "P0171": {
          "name": "System Too Lean (Bank 1)",
          "causes": [
              "Intake boot crack or vacuum leak",
              "Dirty or contaminated Mass Air Flow (MAF) sensor",
              "Weak fuel pump or clogged fuel filter",
              "Stuck-open PCV valve",
          ],
          "checks": (
              "Check Long Term Fuel Trims (LTFT) at idle vs 2,500 RPM to"
              " isolate vacuum leaks from fuel delivery issues."
          ),
      },
      "P0174": {
          "name": "System Too Lean (Bank 2)",
          "causes": [
              "Intake manifold gasket leak",
              "Dirty MAF sensor",
              "Low fuel delivery / pressure",
              "Vacuum line leak",
          ],
          "checks": (
              "Compare Bank 1 vs Bank 2 fuel trims; perform a smoke test on the"
              " intake tract."
          ),
      },
      "P0128": {
          "name": "Coolant Thermostat (Coolant Temp Below Regulating Temp)",
          "causes": [
              "Thermostat stuck open",
              "Defective Engine Coolant Temperature (ECT) sensor",
              "Low engine coolant level",
          ],
          "checks": (
              "Monitor live ECT sensor data during warm-up; verify radiator"
              " hose temps with an infrared thermometer."
          ),
      },
      "P0442": {
          "name": "EVAP System Small Leak Detected",
          "causes": [
              "Worn, loose, or cracked gas cap seal",
              "Cracked EVAP canister vent or purge line",
              "Stuck or leaking EVAP purge solenoid",
          ],
          "checks": (
              "Inspect gas cap seal; smoke-test the EVAP service port to locate"
              " vapor leaks."
          ),
      },
      "P0455": {
          "name": "EVAP System Gross Leak Detected",
          "causes": [
              "Gas cap missing or completely loose",
              "EVAP canister purge valve stuck wide open",
              "Disconnected or broken EVAP vapor hose",
          ],
          "checks": (
              "Verify gas cap installation; check purge valve vacuum seal with"
              " ignition off."
          ),
      },
      "U0100": {
          "name": "Lost Communication With ECM / PCM 'A'",
          "causes": [
              "Blown ECM main power fuse or faulty relay",
              "Loose or corroded ECM ground terminal",
              "CAN bus wiring open or shorted to ground",
              "Faulty Engine Control Module",
          ],
          "checks": (
              "Check battery resting voltage; inspect ECM fuses/relays; test"
              " CAN bus terminating resistance (60 ohms across pin 6 and 14)."
          ),
      },
  }

  code_input = (
      st.text_input("Enter DTC (e.g., P0300, P0420, P0171):", max_chars=5)
      .strip()
      .upper()
  )

  if st.button("Lookup Code") and code_input:
    # 1. Parse standard SAE prefix categories
    systems = {
        "P": "Powertrain (Engine, Transmission, Emissions)",
        "B": "Body (Airbags, A/C, Lighting, Central Locking)",
        "C": "Chassis (ABS, Traction Control, Steering, Suspension)",
        "U": "Network (CAN Bus, Module Communications)",
    }
    first_char = code_input[0] if len(code_input) > 0 else ""

    if first_char in systems:
      st.info(f"**System Category:** {systems[first_char]}")

    # 2. Check database for specific causes and tests
    if code_input in DTC_DATABASE:
      data = DTC_DATABASE[code_input]
      st.success(f"**{code_input}:** {data['name']}")

      st.write("**Common Causes:**")
      for c in data["causes"]:
        st.write(f"- {c}")

      st.write(f"**Diagnostic Strategy:** {data['checks']}")
    else:
      st.warning(
          f"Code **{code_input}** received. No pre-loaded diagnostic notes"
          " found for this specific code, but system category is listed above."
      )
