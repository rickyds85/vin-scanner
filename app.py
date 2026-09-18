from PIL import Image
import re
import requests
import streamlit as st
import zxingcpp

st.set_page_config(
    page_title="Pro Auto Diagnostic Tool", page_icon="🔧", layout="wide"
)
st.title("🚗 Pro Auto Diagnostic & VIN Tool")

# Initialize session state for vehicle info across tabs
if "vehicle_info" not in st.session_state:
  st.session_state.vehicle_info = ""

tab1, tab2 = st.tabs(["📷 VIN Scanner", "🔧 In-Depth Diagnostic Strategy"])

# ========================================================
# --- TAB 1: VIN SCANNER ---
# ========================================================
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

  DTC_DEEP_DIVE = {
      "P0300": {
          "title": "Random / Multiple Cylinder Misfire Detected",
          "severity": (
              "High (Flashing MIL indicates active catalyst-damaging misfire)"
          ),
          "pids": [
              "Cylinder 1-8 Live Misfire Counters (Mode $06 TID $0B / $0C)",
              (
                  "Long Term & Short Term Fuel Trims (LTFT / STFT) Bank 1 &"
                  " Bank 2"
              ),
              "Mass Air Flow (g/s) & Calculated Engine Load",
              "Fuel Rail Pressure (Actual vs Desired)",
          ],
          "phase1_scan": (
              "1. Check Mode $06 misfire counters to identify if one cylinder"
              " is dominating the misfire.\n2. Observe fuel trims at idle vs"
              " 2,500 RPM:\n   - LTFT high (+15% or more) at idle that"
              " drops/corrects at 2,500 RPM = **Vacuum leak**.\n   - LTFT high"
              " across both idle and load = **Fuel delivery problem (weak pump,"
              " clogged filter/injectors)**."
          ),
          "phase2_electrical": (
              "1. **Ignition Testing:** Check primary current ramps with a"
              " low-amp current probe on the coil ground/power feed. Verify 6-8A"
              " peak current and consistent burn time (1.2ms - 2.0ms).\n2."
              " **Injector Waveforms:** Check injector voltage peak spike (~60V"
              " - 80V on port injection) and verify pintle-closing hump."
          ),
          "phase3_mechanical": (
              "1. Perform a **Relative Compression test** with an amp clamp"
              " around the main battery cable during 5 seconds of cranking"
              " (disable fuel/spark).\n2. If uneven peaks appear, run a physical"
              " manual compression check and cylinder leak-down test."
          ),
          "pattern_failures": [
              (
                  "Intake manifold gaskets leaking unmetered air on cold starts"
                  " (GM 5.3L / Ford 4.6L / Toyota 1.8L)."
              ),
              "Carbon buildup on intake valves (Direct-Injection GDI engines).",
              "Weak valve springs causing intermittent high-RPM misfires.",
          ],
      },
      "P0420": {
          "title": "Catalyst System Efficiency Below Threshold (Bank 1)",
          "severity": "Medium (Emissions failure; non-stranding unless plugged)",
          "pids": [
              "Upstream Air/Fuel (A/F) Sensor Voltage or Current (mA)",
              "Downstream Oxygen Sensor Voltage (O2S2 Bank 1)",
              "Engine Coolant Temperature (ECT)",
              "Long Term Fuel Trim (LTFT Bank 1)",
          ],
          "phase1_scan": (
              "1. Ensure engine is in closed loop with ECT above 185°F (85°C).\n2."
              " Bring engine to 2,000 RPM steady cruise:\n   - **Normal"
              " Converter:** Downstream O2 sensor should hold a steady, stable"
              " voltage (typically 0.55V to 0.75V) with minimal oscillation.\n  "
              " - **Failed Converter:** Downstream O2 mirrors the upstream"
              " sensor, actively switching rapidly between 0.1V and 0.8V."
          ),
          "phase2_electrical": (
              "1. Verify downstream O2 heater circuit resistance (typically 5"
              " to 15 ohms across heater terminals).\n2. Confirm sensor ground"
              " drops less than 50mV to battery negative."
          ),
          "phase3_mechanical": (
              "1. **Exhaust Leak Inspection:** Inspect exhaust manifold, flex"
              " pipe, and gaskets within 12 inches of the catalytic converter."
              " Any pinhole leak draws in outside oxygen and triggers P0420.\n2."
              " **Thermal Test:** Use an infrared pyrometer on the catalytic"
              " converter shell. An active converter's outlet should be 50°F to"
              " 100°F hotter than its inlet."
          ),
          "pattern_failures": [
              (
                  "Fix upstream misfires or oil/coolant consumption BEFORE"
                  " installing a new converter, or the new converter will fail"
                  " within months."
              ),
              "Cracked exhaust manifold near weld joints (Subaru / Nissan 2.5L).",
              "Exhaust flange gasket blown out upstream of cat.",
          ],
      },
      "P0171": {
          "title": "System Too Lean (Bank 1)",
          "severity": "Medium-High (May cause bucking, detonation, and misfire)",
          "pids": [
              "Short Term Fuel Trim (STFT 1) & Long Term Fuel Trim (LTFT 1)",
              "Mass Air Flow (g/s) & Calculated Load",
              "Manifold Absolute Pressure (MAP in Hg / kPa)",
              "Fuel Pressure / Rail Pressure Sensor",
          ],
          "phase1_scan": (
              "1. **Isolate Idle vs Load:**\n   - High positive trim (+18% to"
              " +25%) that drops toward 0% at 2,500 RPM = **Vacuum leak**.\n  "
              " - Trim stays lean or gets worse under heavy load = **Fuel pump /"
              " filter / restricted injector delivery issue**.\n2. **MAF"
              " Sanity Check:** At idle, MAF g/s should roughly equal engine"
              " displacement in liters (e.g., 2.0L engine ≈ 2.0 g/s ± 0.5 g/s)."
          ),
          "phase2_electrical": (
              "1. Check 5V reference and sensor ground circuits to MAF/MAP"
              " sensors.\n2. Measure fuel pump current draw at fuel pump relay"
              " terminal using an amp clamp (look for ripple pattern anomalies"
              " or high amperage indicating a seizing pump motor)."
          ),
          "phase3_mechanical": (
              "1. Connect a **Smoke Machine** to the intake manifold vacuum port"
              " and inspect for leaks around intake gaskets, PCV hoses, throttle"
              " body seals, and brake booster diaphragm.\n2. Connect a manual"
              " fuel pressure gauge to the test port and perform a deadhead/"
              " volume delivery test."
          ),
          "pattern_failures": [
              (
                  "Torn intake accordion air boot after the MAF sensor (BMW /"
                  " Toyota)."
              ),
              "Stuck-open PCV valve or cracked crankcase breather tube.",
              "Contaminated hot-wire in the MAF sensor (clean with MAF cleaner).",
          ],
      },
      "U0100": {
          "title": "Lost Communication With ECM / PCM 'A'",
          "severity": "High (No-crank / no-start / limp home mode)",
          "pids": [
              "CAN-H Voltage (~2.5V recessive, ~3.5V dominant)",
              "CAN-L Voltage (~2.5V recessive, ~1.5V dominant)",
              "DLC Pin 16 Battery Voltage",
              "Module Scan Communication Status across all nodes",
          ],
          "phase1_scan": (
              "1. Perform an **All-Module Network Scan**:\n   - If only the ECM"
              " is missing while TCM, ABS, and BCM are communicating and"
              " reporting U0100, the CAN bus is alive, but the ECM is"
              " dead/unpowered.\n   - If multiple modules fail to communicate,"
              " suspect a bus wire shorted to power or ground."
          ),
          "phase2_electrical": (
              "1. **Terminating Resistance Test:** Turn ignition OFF, disconnect"
              " battery negative, measure resistance across DLC Pin 6 (CAN-H)"
              " and Pin 14 (CAN-L):\n   - **60 Ω:** Normal (both 120 Ω"
              " terminating resistors are present and connected).\n   - **120"
              " Ω:** One terminating resistor or module connector is open/cut."
              "\n   - **0-10 Ω:** Short circuit between CAN-H and CAN-L wires."
              "\n2. **ECM Power & Ground:** Verify 12V under load on all main"
              " ECM power feeds and less than 50mV voltage drop across all ECM"
              " grounds."
          ),
          "phase3_mechanical": (
              "1. Inspect engine bay main harness routing near exhaust"
              " manifolds, pulleys, or sharp bracket edges for chafing.\n2."
              " Check ECM connector pins for water intrusion, fretting"
              " corrosion, or bent terminal pins."
          ),
          "pattern_failures": [
              "Corroded main ECM relay or blown ECM/IGN fuse in underhood fuse box.",
              "Water leak into footwell soaking BCM or Gateway module connectors.",
              "Rodent damage to engine wiring harness behind cylinder heads.",
          ],
      },
      "P0128": {
          "title": "Coolant Thermostat Below Regulating Temperature",
          "severity": (
              "Low-Medium (Poor heater performance, fuel richness, disables"
              " EVAP monitor)"
          ),
          "pids": [
              "Engine Coolant Temperature (ECT)",
              "Intake Air Temperature (IAT)",
              "Vehicle Speed Sensor (VSS)",
          ],
          "phase1_scan": (
              "1. Cold-soak sanity check: Before cold startup, ECT and IAT"
              " readings should match within 3°F of ambient shop temp.\n2. Start"
              " engine and monitor ECT temperature rise rate while idling or"
              " driving."
          ),
          "phase2_electrical": (
              "1. Measure ECT resistance across sensor pins with connector"
              " unplugged (NTC thermistor should decrease resistance as"
              " temperature rises).\n2. Verify 5.0V reference on sensor harness"
              " with key on, engine off."
          ),
          "phase3_mechanical": (
              "1. **Hose Temperature Check:** Use an infrared thermometer on"
              " the upper and lower radiator hoses during warm-up. If the upper"
              " hose warms up immediately from cold idle, the thermostat is"
              " stuck open or missing."
          ),
          "pattern_failures": [
              "Rubber seal on thermostat deteriorated and jamming the valve open.",
              "Corroded pins at the ECT pigtail causing high circuit resistance.",
          ],
      },
  }

  col_input, col_btn = st.columns([3, 1])
  with col_input:
    code_input = (
        st.text_input("Enter OBD-II DTC (e.g., P0300, P0420, P0171, U0100):")
        .strip()
        .upper()
    )
  with col_btn:
    st.write("")
    lookup_clicked = st.button("Run Diagnostic Tree", use_container_width=True)

  if code_input and (lookup_clicked or code_input):
    first_char = code_input[0] if len(code_input) > 0 else ""
    systems = {
        "P": "Powertrain (Engine, Transmission, Emissions)",
        "B": "Body (Airbags, BCM, Lighting, HVAC, Doors)",
        "C": "Chassis (ABS, Traction Control, Steering, Suspension)",
        "U": "Network (CAN Bus, Serial Data, Module Communications)",
    }

    if first_char in systems:
      st.info(f"**System Subsystem:** {systems[first_char]}")

    if code_input in DTC_DEEP_DIVE:
      data = DTC_DEEP_DIVE[code_input]
      st.markdown(f"### {code_input} — {data['title']}")
      st.warning(f"**Severity Level:** {data['severity']}")

      # Display structured tabs for testing phases
      dtab1, dtab2, dtab3, dtab4 = st.tabs([
          "📊 1. PIDs & Scan Tool",
          "⚡ 2. Electrical & Scope",
          "🔧 3. Mechanical & Physical",
          "⚠️ 4. Known Pattern Failures",
      ])

      with dtab1:
        st.write("#### Key Live PIDs to Monitor")
        for pid in data["pids"]:
          st.write(f"- {pid}")
        st.write("---")
        st.write("#### Scan Tool Verification Strategy")
        st.markdown(data["phase1_scan"])

      with dtab2:
        st.write("#### Circuit & Component Testing (DMM / Scope)")
        st.markdown(data["phase2_electrical"])

      with dtab3:
        st.write("#### Mechanical & Physical Testing")
        st.markdown(data["phase3_mechanical"])

      with dtab4:
        st.write("#### Field Notes & Common Pattern Failures")
        for pf in data["pattern_failures"]:
          st.write(f"- {pf}")

    else:
      st.warning(f"Detailed field tree for **{code_input}** is not pre-loaded.")
      st.write("### Standard SAE Diagnostic Flow")
      st.markdown(
          """
            1. **Verify Freeze Frame:** Check engine RPM, engine load, vehicle speed, and loop status when the code set.
            2. **Inspect Wiring & Harness:** Check sensor power (typically 5V ref or 12V), ground drop (<50mV), and signal line integrity.
            3. **Component Resistance:** Test actuator or sensor winding resistance against OE specifications at room temperature.
            4. **Clean & Verify Grounds:** Ensure all engine block, chassis, and ECM grounding lugs are clean, bare metal, and tight.
            """
      )
