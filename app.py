import base64
import csv
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile

from PIL import Image, ImageEnhance, ImageOps
import requests
import streamlit as st
import streamlit.components.v1 as components
import zxingcpp

st.set_page_config(page_title="Test Don't Guess", page_icon="⚡", layout="wide")

st.markdown(
    """
<div style="display: flex; align-items: center; gap: 14px; margin-bottom: 1.5rem;">
  <svg width="65" height="42" viewBox="0 0 120 70" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M 5 45 L 22 45 L 24 60 L 42 60 L 43 5 L 46 36 Q 48 34 54 36 T 64 36 T 74 35 T 80 36 Q 84 18 88 50 Q 92 24 96 44 Q 100 32 104 42 L 118 42"
          stroke="#00FF66" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"
          style="filter: drop-shadow(0px 0px 5px #00FF66);"/>
  </svg>
  <h1 style="margin: 0; padding: 0; font-size: 2.2rem; font-weight: 700;">Test Don't Guess</h1>
</div>
""",
    unsafe_allow_html=True,
)

# ========================================================
# --- CONSTANTS ---
# ========================================================
LOG_FILE = "scan_history.csv"
LOG_COLUMNS = ["Timestamp", "Customer", "Phone", "VIN", "Vehicle", "Fault Code (DTC)"]
VIN_RE = re.compile(r"[A-HJ-NPR-Z0-9]{17}")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

# NHTSA "Make" -> enhanced-PID profile used by the Bluetooth dashboard
MAKE_PROFILES = {
    "HONDA": "HONDA", "ACURA": "HONDA",
    "TOYOTA": "TOYOTA", "LEXUS": "TOYOTA", "SCION": "TOYOTA",
    "NISSAN": "NISSAN", "INFINITI": "NISSAN",
    "HYUNDAI": "HYUNDAI", "KIA": "HYUNDAI", "GENESIS": "HYUNDAI",
    "SUBARU": "SUBARU", "MAZDA": "MAZDA",
    "FORD": "FORD", "LINCOLN": "FORD", "MERCURY": "FORD",
    "CHEVROLET": "GM", "GMC": "GM", "CADILLAC": "GM", "BUICK": "GM", "PONTIAC": "GM", "SATURN": "GM",
    "CHRYSLER": "CHRYSLER", "DODGE": "CHRYSLER", "JEEP": "CHRYSLER", "RAM": "CHRYSLER",
}

# ========================================================
# --- SESSION STATE ---
# ========================================================
ss = st.session_state
DEFAULTS = {
    "customer_name": "", "customer_phone": "", "customer_address": "",
    "vin_input": "", "active_vin": "", "vehicle_info": "", "vehicle_make": "",
    "vehicle_details": {}, "vin_error": "", "active_dtc": "", "sel_codes": [], "manual_dtc": "", "scan_data": {},
    "chat_history": [], "dtc_result": None, "scope_result": None, "symptoms": "",
    "man_make": "", "man_make_other": "", "man_model": "", "man_trim": "", "man_engine": "",
    "ble_ai": None, "ble_last_event": None, "ble_dtcs": {},
}
for _k, _v in DEFAULTS.items():
    ss.setdefault(_k, _v)

# Widget values can only be changed BEFORE the widget is drawn, so updates
# coming from buttons/Bluetooth are queued, then applied here on the rerun.
for _k, _v in ss.pop("_pending", {}).items():
    ss[_k] = _v
if _toast := ss.pop("_toast", None):
    st.toast(_toast)

DTC_RE = re.compile(r"[PCBU][0-3][0-9A-F]{3}")


def current_codes() -> list[str]:
  """Codes picked from the scanner plus any typed in by hand."""
  codes = list(ss.get("sel_codes") or [])
  for c in re.split(r"[,\s;/]+", (ss.get("manual_dtc") or "").upper()):
    if DTC_RE.fullmatch(c) and c not in codes:
      codes.append(c)
  return codes


ss.active_dtc = ", ".join(current_codes())


def queue_update(toast: str | None = None, **values):
  ss.setdefault("_pending", {}).update(values)
  if toast:
    ss._toast = toast
  st.rerun()


# ========================================================
# --- HELPERS ---
# ========================================================
class AIError(Exception):
  pass


def secret(name: str) -> str:
  val = os.environ.get(name)
  if not val:
    try:
      val = st.secrets.get(name)
    except Exception:  # no secrets.toml
      val = None
  return val or ""


@st.cache_resource
def http() -> requests.Session:
  return requests.Session()  # keep-alive: faster repeat API calls


def img_part(img: Image.Image) -> dict:
  im = img.convert("RGB")
  im.thumbnail((1600, 1600))  # smaller upload = faster + cheaper, still sharp enough
  b = io.BytesIO()
  im.save(b, format="JPEG", quality=85)
  return {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(b.getvalue()).decode()}}


def gemini(parts: list, *, json_mode: bool = False, timeout: int = 45) -> str:
  key = secret("GEMINI_API_KEY")
  if not key:
    raise AIError("GEMINI_API_KEY is missing from Streamlit Secrets.")
  payload = {"contents": [{"parts": parts}]}
  if json_mode:
    payload["generationConfig"] = {"response_mime_type": "application/json"}
  try:
    res = http().post(GEMINI_URL, headers={"x-goog-api-key": key}, json=payload, timeout=timeout)
  except requests.RequestException as e:
    raise AIError(f"Gemini connection error: {e}") from e
  if res.status_code != 200:
    raise AIError(f"Gemini API error ({res.status_code}): {res.text[:300]}")
  try:
    return res.json()["candidates"][0]["content"]["parts"][0]["text"]
  except (KeyError, IndexError, ValueError) as e:
    raise AIError("Gemini returned no text (the request may have been blocked).") from e


def ask_gemini(prompt: str) -> str:
  try:
    return gemini([{"text": prompt}])
  except AIError as e:
    return f"⚠️ {e}"


def ask_perplexity(prompt: str, preset: str = "low") -> str:
  key = secret("PERPLEXITY_API_KEY")
  if not key:
    return "⚠️ PERPLEXITY_API_KEY is not configured in Streamlit Secrets."
  try:
    res = http().post(
        "https://api.perplexity.ai/v1/responses",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"preset": preset, "input": prompt},
        timeout=60,
    )
  except requests.exceptions.Timeout:
    return "⚠️ Request timed out. Please try again."
  except requests.RequestException as e:
    return f"⚠️ Perplexity connection error: {e}"
  if res.status_code != 200:
    return f"⚠️ Perplexity API error ({res.status_code}): {res.text[:300]}"
  data = res.json()
  if data.get("output_text"):
    return data["output_text"]
  text = "".join(
      c.get("text", "")
      for item in data.get("output", []) if item.get("type") == "message"
      for c in item.get("content", [])
  )
  return text or "No response text received."


# --- VIN ---
_VIN_VALUES = dict(zip("ABCDEFGHJKLMNPRSTUVWXYZ", [1, 2, 3, 4, 5, 6, 7, 8, 1, 2, 3, 4, 5, 7, 9, 2, 3, 4, 5, 6, 7, 8, 9]))
_VIN_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]


def vin_check_digit_ok(vin: str) -> bool:
  total = sum((int(c) if c.isdigit() else _VIN_VALUES.get(c, 0)) * w for c, w in zip(vin, _VIN_WEIGHTS))
  r = total % 11
  return vin[8] == ("X" if r == 10 else str(r))


def scan_vin_barcode(img: Image.Image) -> str:
  for candidate in (img, ImageEnhance.Contrast(ImageOps.grayscale(img)).enhance(2.2)):
    for b in zxingcpp.read_barcodes(candidate, try_rotate=True, try_downscale=True, try_invert=True):
      m = VIN_RE.search(b.text.upper())
      if m:
        return m.group(0)
  return ""


@st.cache_data(show_spinner=False, max_entries=50)
def find_vin(img_bytes: bytes) -> tuple[str, str]:
  """Barcode first (free, instant), AI text read only if that fails. Cached per photo."""
  img = ImageOps.exif_transpose(Image.open(io.BytesIO(img_bytes)))
  vin = scan_vin_barcode(img)
  if vin:
    return vin, "Barcode"
  text = gemini(
      [
          {"text": "Locate the 17-character Vehicle Identification Number (VIN) in this image. VINs use digits and"
                   " uppercase letters except I, O and Q. Return ONLY the VIN, or NONE if there isn't one."},
          img_part(img),
      ],
      timeout=25,
  )
  m = VIN_RE.search(text.upper())
  return (m.group(0), "AI photo text") if m else ("", "")


@st.cache_data(show_spinner=False, max_entries=20)
def extract_customer(img_bytes: bytes) -> dict:
  img = ImageOps.exif_transpose(Image.open(io.BytesIO(img_bytes)))
  raw = gemini(
      [
          {"text": "Read this work order / invoice. Extract ONLY the customer name, address and phone number."
                   " Return a JSON object with keys 'customer_name', 'address', 'phone' (empty string if missing)."},
          img_part(img),
      ],
      json_mode=True,
      timeout=25,
  )
  return json.loads(raw)


@st.cache_data(ttl=7 * 86400, show_spinner=False, max_entries=500)
def decode_vin(vin: str) -> dict:
  r = http().get(f"https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/{vin}?format=json", timeout=10)
  r.raise_for_status()
  wanted = [
      "Model Year", "Make", "Model", "Trim", "Displacement (L)", "Engine Number of Cylinders",
      "Engine Model", "Fuel Type - Primary", "Drive Type", "Transmission Style", "Vehicle Type",
  ]
  found = {i["Variable"]: i["Value"] for i in r.json().get("Results", []) if i.get("Value") and i.get("Variable") in wanted}
  return {k: found[k] for k in wanted if k in found}


def load_vehicle(vin: str) -> bool:
  """Decode a VIN and make it the active vehicle. Returns True on success."""
  try:
    d = decode_vin(vin)
  except Exception as e:
    ss.vin_error, ss._failed_vin = f"VIN decode failed ({e}). Check your connection and try again.", vin
    return False
  if not d.get("Make"):
    ss.vin_error, ss._failed_vin = "NHTSA couldn't decode this VIN. Double-check the characters.", vin
    return False
  disp = d.get("Displacement (L)", "")
  try:
    disp = f"{float(disp):.1f}"
  except ValueError:
    pass
  ss.active_vin = vin
  ss.vehicle_details = d
  ss.vehicle_make = d.get("Make", "").upper()
  ss.vehicle_info = " ".join(x for x in (d.get("Model Year"), d.get("Make"), d.get("Model")) if x) + (f" ({disp}L)" if disp else "")
  ss.vin_error = ""
  return True


MANUAL_MAKES = [
    "Acura", "Buick", "Cadillac", "Chevrolet", "Chrysler", "Dodge", "Ford", "Genesis", "GMC", "Honda", "Hyundai",
    "Infiniti", "Jeep", "Kia", "Lexus", "Lincoln", "Mazda", "Mercury", "Mitsubishi", "Nissan", "Pontiac", "Ram",
    "Saturn", "Scion", "Subaru", "Toyota", "Other...",
]


@st.cache_data(ttl=30 * 86400, show_spinner=False, max_entries=300)
def models_for(make: str, year: int) -> list[str]:
  """Model list from NHTSA for the dropdown (empty list if the lookup fails)."""
  try:
    r = http().get(f"https://vpic.nhtsa.dot.gov/api/vehicles/GetModelsForMakeYear/make/{make}/modelyear/{year}?format=json",
                   timeout=10)
    r.raise_for_status()
    return sorted({m["Model_Name"].strip() for m in r.json().get("Results", []) if m.get("Model_Name")})
  except Exception:
    return []


def set_manual_vehicle(year: str, make: str, model: str, trim: str, engine: str):
  engine = engine.strip()
  if engine and re.fullmatch(r"\d+(\.\d+)?", engine):
    engine += "L"
  d = {"Model Year": year, "Make": make, "Model": model}
  if trim.strip():
    d["Trim"] = trim.strip()
  if engine:
    d["Engine"] = engine
  ss.vehicle_details = d
  ss.vehicle_make = make.upper()
  ss.vehicle_info = " ".join(x for x in (year, make, model, trim.strip()) if x) + (f" ({engine})" if engine else "")
  ss.active_vin = ""
  ss.vin_error = ""


def make_profile() -> str:
  return MAKE_PROFILES.get(ss.vehicle_make, "GENERIC")


# --- LOG ---
def append_to_log(vin: str, vehicle: str, dtc: str, customer: str = "", phone: str = ""):
  new = not os.path.isfile(LOG_FILE)
  try:
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
      w = csv.writer(f)
      if new:
        w.writerow(LOG_COLUMNS)
      w.writerow([datetime.now().strftime("%Y-%m-%d %I:%M %p"), customer or "N/A", phone or "N/A",
                  vin or "N/A", vehicle or "Unknown Vehicle", dtc or "N/A"])
  except OSError:
    pass


def load_log() -> list[dict]:
  try:
    with open(LOG_FILE, encoding="utf-8") as f:
      return list(csv.DictReader(f))[::-1]
  except OSError:
    return []


def context_bar():
  st.info(
      f"📋 **Context:** Customer: `{ss.customer_name or 'None'}` | Vehicle: `{ss.vehicle_info or 'No Vehicle Selected'}`"
      f" | Active DTC: `{ss.active_dtc or 'None Specified'}`"
  )


# Legacy links from the old "Sync" button (?ble_vin=...&ble_dtc=...): use once, then clear
if "ble_vin" in st.query_params or "ble_dtc" in st.query_params:
  _qv = st.query_params.get("ble_vin", "").upper().strip()
  _qd = st.query_params.get("ble_dtc", "").upper().strip()
  st.query_params.clear()
  _upd = {}
  if VIN_RE.fullmatch(_qv) and load_vehicle(_qv):
    _upd["vin_input"] = _qv
  if _qd:
    _upd["manual_dtc"] = _qd
  queue_update(**_upd)


tab1, tab2, tab3, tab5 = st.tabs([
    "📷 VIN & Customer Info",
    "📊 Live Telemetry, Mode $06 & Monitors",
    "🔧 Diagnose (Strategy, Scope & Copilot)",
    "📋 Vehicle & DTC Log",
])

# ========================================================
# --- TAB 1: VIN & CUSTOMER INFO ---
# ========================================================
with tab1:
  st.subheader("Customer & Vehicle Identification")

  st.markdown("#### 👤 Customer Information")
  col_c1, col_c2 = st.columns(2)
  with col_c1:
    st.text_input("Customer Name:", key="customer_name", placeholder="e.g. ROTAE LLC")
    st.text_input("Phone Number:", key="customer_phone", placeholder="e.g. 678-365-2146")
  with col_c2:
    st.text_area("Address:", key="customer_address", height=108,
                 placeholder="e.g. 6428 DAWSON BLVD, STE 1730, NORCROSS, GA, 30093")

  st.write("---")
  st.markdown("#### 📸 Camera / Photo VIN Scanner")
  col_cam, col_up = st.columns(2)
  with col_cam:
    photo = st.camera_input("Snap VIN sticker, plate, or paperwork") if st.toggle("📷 Open Camera") else None
  with col_up:
    uploaded = st.file_uploader("Or upload photo from phone gallery", type=["png", "jpg", "jpeg"], key="vin_upload")

  active_image = photo or uploaded
  if active_image:
    img_bytes = active_image.getvalue()
    photo_id = hashlib.md5(img_bytes).hexdigest()
    st.image(img_bytes, caption="Captured Image")

    found_vin, method = "", ""
    try:
      with st.spinner("Reading VIN (barcode, then AI text)..."):
        found_vin, method = find_vin(img_bytes)
    except AIError as e:
      st.warning(f"Barcode not found and AI read failed: {e}")

    if found_vin:
      st.success(f"VIN Detected ({method}): **{found_vin}**")
      if ss.get("_applied_photo") != photo_id:  # apply each photo once so manual edits stick
        ss._applied_photo = photo_id
        load_vehicle(found_vin)
        queue_update(vin_input=found_vin)
    else:
      st.warning("Could not detect a 17-character VIN. Enter it manually below.")

    if st.button("📄 Extract Customer Details from this Image"):
      try:
        with st.spinner("Extracting customer name, address, and phone..."):
          info = extract_customer(img_bytes)
      except (AIError, ValueError) as e:
        st.error(f"Couldn't read customer details: {e}")
      else:
        upd = {k: str(info.get(j, "")).strip() for k, j in
               (("customer_name", "customer_name"), ("customer_address", "address"), ("customer_phone", "phone"))
               if str(info.get(j, "")).strip()}
        if upd:
          queue_update(toast="Customer info updated", **upd)
        st.warning("No customer details found in this image.")

  vin_typed = st.text_input("Vehicle VIN (17 characters) — decodes automatically:", key="vin_input", max_chars=17)
  vin_clean = vin_typed.strip().upper()
  if len(vin_clean) == 17 and vin_clean != ss.active_vin and vin_clean != ss.get("_failed_vin"):
    with st.spinner("Decoding VIN..."):
      load_vehicle(vin_clean)
  elif 0 < len(vin_clean) < 17:
    st.caption(f"{len(vin_clean)}/17 characters")

  if ss.vin_error and vin_clean == ss.get("_failed_vin"):
    st.error(ss.vin_error)
    if st.button("🔁 Retry decode"):
      ss._failed_vin = ""
      st.rerun()

  with st.expander("🚗 No VIN? Enter the vehicle by hand", expanded=not ss.vehicle_details):
    this_year = datetime.now().year
    m1, m2, m3 = st.columns(3)
    man_year = m1.selectbox("Year", [str(y) for y in range(this_year + 1, 1980, -1)], index=None, placeholder="Year",
                            key="man_year")
    man_make = m2.selectbox("Make", MANUAL_MAKES, index=None, placeholder="Make", key="man_make_sel")
    if man_make == "Other...":
      man_make = m2.text_input("Type the make", key="man_make_other").strip().title()
    model_list = models_for(man_make, int(man_year)) if man_year and man_make else []
    if model_list:
      man_model = m3.selectbox("Model", model_list, index=None, placeholder="Model", key="man_model_sel")
    else:
      man_model = m3.text_input("Model", key="man_model", placeholder="e.g. Accord")
    m4, m5 = st.columns(2)
    man_trim = m4.text_input("Submodel / trim (optional)", key="man_trim", placeholder="e.g. EX-L, LT, SR5")
    man_engine = m5.text_input("Engine size (optional)", key="man_engine", placeholder="e.g. 2.4L, 5.3L V8")
    ready = bool(man_year and man_make and man_model)
    if st.button("✅ Use this vehicle", disabled=not ready, type="primary"):
      set_manual_vehicle(man_year, man_make, (man_model or "").strip(), man_trim, man_engine)
      queue_update(toast=f"Vehicle set: {ss.vehicle_info}", vin_input="")

  if ss.vehicle_details:
    if ss.active_vin and not vin_check_digit_ok(ss.active_vin):
      st.warning("⚠️ VIN check digit (9th character) doesn't match. One character may be misread"
                 " (common with photos). Non-North-American VINs can ignore this.")
    st.subheader(f"{ss.vehicle_info}  ·  " + (f"`{ss.active_vin}`" if ss.active_vin else "entered by hand (no VIN)"))
    col1, col2 = st.columns(2)
    for i, (k, v) in enumerate(ss.vehicle_details.items()):
      (col1 if i % 2 == 0 else col2).write(f"**{k}:** {v}")
    st.caption(f"Bluetooth enhanced-PID profile: **{make_profile()}**")

# ========================================================
# --- TAB 2: LIVE TELEMETRY, ENHANCED PIDS, MONITORS & MODE 06 ---
# ========================================================
BLE_DASHBOARD_HTML = r'''<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { --bg:#1A1F26; --card:#111418; --line:#2D3748; --muted:#A0AEC0; --g:#00FF66; --b:#38BDF8; --o:#F59E0B; --y:#FBBF24; --p:#EC4899; --v:#A855F7; --t:#10B981; --r:#EF4444; --s:#64748B; --w:#E2E8F0; }
  * { box-sizing:border-box; }
  body { margin:0; background:transparent; color:#fff; font-family:"Source Sans Pro",system-ui,sans-serif; }
  .wrap { background:var(--bg); border:1px solid var(--g); padding:14px; border-radius:8px; }
  .bar { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:10px; }
  button { font-weight:700; font-size:.88rem; border:1px solid var(--line); padding:9px 14px; border-radius:5px; cursor:pointer; color:#0E1117; }
  button:disabled { background:#2D3748 !important; color:#718096 !important; cursor:not-allowed; }
  #bleBtn { background:var(--g); border:none; } #pauseBtn { background:var(--r); color:#fff; } #driveBtn { background:var(--t); }
  #readBtn { background:var(--b); } #clearBtn { background:var(--r); color:#fff; } #aiBtn { background:var(--o); } #syncBtn { background:var(--v); color:#fff; }
  .oem { margin-left:auto; display:flex; align-items:center; gap:6px; font-size:.8rem; color:var(--muted); }
  select { background:var(--card); color:var(--g); border:1px solid var(--g); padding:6px 8px; border-radius:4px; font-weight:700; }
  #status { color:var(--muted); font-family:monospace; font-size:.85rem; margin-bottom:12px; }
  #driveBanner { display:none; background:#0F172A; border-left:4px solid var(--b); padding:8px 12px; border-radius:4px; margin-bottom:12px; font-size:.85rem; color:var(--b); }
  h3 { font-size:.95rem; margin:0 0 6px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(112px,1fr)); gap:8px; margin-bottom:16px; }
  .tile { background:var(--card); border:1px solid var(--line); padding:8px 4px; border-radius:6px; text-align:center; }
  .tile .l { font-size:.68rem; color:var(--muted); text-transform:uppercase; }
  .tile .v { font-size:1.12rem; font-weight:700; }
  .tile.na { display:none; }   /* hide PIDs this vehicle does not support */
  .enh .tile { border-color:var(--p); }
  .grp { font-size:.75rem; color:var(--p); font-weight:700; text-transform:uppercase; margin:6px 0 4px; }
  .box { background:var(--card); border:1px solid var(--line); border-radius:6px; padding:10px; margin-bottom:16px; font-size:.85rem; color:var(--muted); }
  .chips { display:flex; flex-wrap:wrap; gap:6px; }
  .chip { padding:4px 10px; border-radius:12px; font-weight:700; font-family:monospace; font-size:.9rem; border:1px solid; }
  .mon { background:var(--bg); border:1px solid; padding:6px; border-radius:5px; text-align:center; }
  .mon .l { font-size:.74rem; color:var(--muted); } .mon .v { font-size:.88rem; font-weight:700; }
  #aiBox { border-color:var(--o); color:#fff; font-size:.9rem; line-height:1.45; min-height:80px; }
  #aiBox h4 { color:var(--g); margin:8px 0 4px; }
  .tile { cursor:pointer; user-select:none; }
  .tile:hover { border-color:var(--muted); }
  .tile.sel { outline:2px solid var(--w); outline-offset:-2px; }
  #graphs { margin-bottom:12px; }
  .gbar { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:8px; font-size:.8rem; color:var(--muted); }
  .gbar button { padding:4px 10px; font-size:.78rem; background:var(--card); color:var(--w); border:1px solid var(--line); }
  .gbar button.on { border-color:var(--g); color:var(--g); }
  .chart { background:var(--card); border:1px solid var(--line); border-radius:6px; padding:6px 8px 4px; margin-bottom:8px; }
  .chart .hd { display:flex; justify-content:space-between; align-items:baseline; gap:8px; font-size:.8rem; color:var(--muted); }
  .chart .hd b { color:var(--w); font-size:.95rem; }
  .chart .hd .x { cursor:pointer; padding:0 4px; color:var(--muted); }
  .chart canvas { width:100%; height:120px; display:block; touch-action:pan-y; }
  .note { font-size:.72rem; color:var(--s); font-weight:400; }
</style>
</head>
<body>
<div class="wrap">
  <div class="bar">
    <button id="bleBtn">⚡ Connect &amp; Auto-Scan</button>
    <button id="pauseBtn" disabled>⏸️ Pause</button>
    <button id="driveBtn" disabled>🚗 Test Drive Audio</button>
    <button id="readBtn" disabled>🔎 Re-read Codes</button>
    <button id="clearBtn" disabled>🗑️ Clear Codes</button>
    <button id="aiBtn" disabled>🤖 AI Check</button>
    <button id="syncBtn" disabled>📋 Send VIN &amp; Codes to App</button>
    <div class="oem">OEM Profile:
      <select id="oemSel">
        <option value="AUTO">Auto-Detect</option><option value="HONDA">Honda / Acura</option>
        <option value="TOYOTA">Toyota / Lexus / Scion</option><option value="NISSAN">Nissan / Infiniti</option>
        <option value="HYUNDAI">Hyundai / Kia / Genesis</option><option value="SUBARU">Subaru</option>
        <option value="MAZDA">Mazda</option><option value="FORD">Ford / Lincoln / Mercury</option>
        <option value="GM">GM</option><option value="CHRYSLER">Chrysler / Dodge / Jeep / Ram</option>
        <option value="GENERIC">Generic (OBD-II only)</option>
      </select>
    </div>
  </div>
  <div id="status">Status: Ready. Key ON (or engine running), then tap Connect.</div>
  <div id="driveBanner">🚗 <strong>Test Drive Audio ON:</strong> screen stays awake; spoken alerts for fuel trim, coolant temp and charging voltage; AI check every 60 s.</div>

  <h3 style="color:var(--r)">🚨 FAULT CODES</h3>
  <div id="dtcBox" class="box">Codes are read automatically on connect.</div>
  <div id="clearWarn" class="box" style="display:none;border-color:var(--o);color:var(--o);font-weight:700"></div>

  <h3 style="color:var(--g)">📈 LIVE DATA (MODE 01) <span id="rate" class="note"></span></h3>
  <div id="graphs">
    <div class="gbar" id="gbar">📈 Tap any reading to graph it live (up to 4 at once).</div>
    <div id="charts"></div>
  </div>
  <div id="liveGrid" class="grid"></div>

  <h3 style="color:var(--o)">🕓 HISTORY COUNTERS <span class="note">read every ~30 s; spot cars with freshly cleared codes</span></h3>
  <div id="histGrid" class="grid"></div>

  <h3 style="color:var(--p)">🏭 OEM ENHANCED DATA <span id="enhNote" class="note">connect to scan this vehicle's modules</span></h3>
  <div id="enhBox" class="enh"><div class="box">Factory-level readings appear here as each module answers.</div></div>
  <div class="note" style="margin:-10px 0 16px">Definitions from the open OBD database (OBDb, github.com/OBDb). Some are model-year specific, so sanity-check new readings against a factory scan tool.</div>

  <h3 style="color:var(--b)">📋 I/M READINESS</h3>
  <div id="readyBox" class="box">Loads automatically on connect.</div>

  <h3 style="color:var(--b)">📊 MODE $06 TEST RESULTS</h3>
  <div id="m6Box" class="box">Loads automatically on connect.</div>

  <h3 style="color:var(--o)">🤖 AI MASTER TECH EVALUATION</h3>
  <div id="aiBox" class="box">Connect, let it stream for a few seconds, then tap AI Check.</div>
</div>

<script>
// ===================== Streamlit bridge (no npm needed) =====================
function toStreamlit(type, data) { window.parent.postMessage(Object.assign({ isStreamlitMessage: true, type }, data || {}), "*"); }
const sendValue = (value) => toStreamlit("streamlit:setComponentValue", { value, dataType: "json" });
let lastHeight = 0;
function fitHeight() { const h = document.documentElement.scrollHeight; if (h !== lastHeight) { lastHeight = h; toStreamlit("streamlit:setFrameHeight", { height: h }); } }
new ResizeObserver(fitHeight).observe(document.body);

let ARGS = { vehicle: "", make: "GENERIC", year: "", ai: null };
let lastAiShown = null;
window.addEventListener("message", (e) => {
  if (!e.data || e.data.type !== "streamlit:render") return;
  const a = e.data.args || {};
  const changed = a.make !== ARGS.make || String(a.year) !== String(ARGS.year);
  ARGS = a;
  if (changed && connected) buildEnhanced();
  if (a.ai && a.ai.id && a.ai.id !== lastAiShown) {
    lastAiShown = a.ai.id;
    if (a.ai.id === aiPendingId) aiPendingId = null;
    showAi(a.ai.text, a.ai.label);
  }
  fitHeight();
});
toStreamlit("streamlit:componentReady", { apiVersion: 1 });

// ===================== UI helpers =====================
const $ = (id) => document.getElementById(id);
const log = (m) => { $("status").textContent = "Status: " + m; };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const LIVE_TILES = [
  ["rpm", "Engine RPM", "g"], ["load", "Engine Load", "b"], ["spd", "Vehicle Speed", "b"], ["tps", "Throttle (TPS)", "w"],
  ["app", "Pedal (APP)", "w"], ["ect", "Coolant (ECT)", "o"], ["iat", "Intake Air (IAT)", "o"], ["aat", "Ambient Temp", "o"],
  ["eot", "Oil Temp", "o"], ["map", "MAP", "g"], ["maf", "MAF Flow", "g"], ["baro", "Baro", "s"],
  ["frp", "Fuel Rail Press", "t"], ["fli", "Fuel Level", "t"], ["stft1", "STFT B1", "y"], ["ltft1", "LTFT B1", "y"],
  ["stft2", "STFT B2", "y"], ["ltft2", "LTFT B2", "y"], ["timing", "Ign Timing", "p"], ["o2b1s1", "O2 B1S1", "v"],
  ["o2b1s2", "O2 B1S2", "v"], ["o2b2s1", "O2 B2S1", "v"], ["o2b2s2", "O2 B2S2", "v"], ["evap", "EVAP Purge", "w"],
  ["volt", "Battery Volt", "w"], ["fss", "Fuel System", "g"], ["absload", "Absolute Load", "b"],
  ["cmdlam", "Commanded λ", "v"], ["fuelrate", "Fuel Rate", "t"], ["cmv", "ECM Voltage", "w"],
  ["cat1", "Cat Temp B1", "o"], ["cat2", "Cat Temp B2", "o"], ["egrcmd", "EGR Commanded", "w"],
  ["egrerr", "EGR Error", "w"], ["evapvp", "EVAP Vapor Press", "w"], ["eth", "Ethanol", "t"],
  ["frpabs", "Fuel Rail (abs)", "t"], ["boost", "Boost (abs)", "g"], ["egt", "EGT B1 S1", "o"],
  ["runtime", "Run Time", "s"],
];
const HIST_TILES = [
  ["clrDist", "Miles Since Codes Cleared", "o"], ["clrTime", "Run Time Since Cleared", "o"],
  ["warmups", "Warm-ups Since Cleared", "o"], ["milDist", "Miles With MIL On", "r"],
  ["milTime", "Run Time With MIL On", "r"], ["odo", "Odometer", "w"],
];
const LABEL = {};
function makeTiles(gridId, tiles, color) {
  $(gridId).innerHTML = tiles.map(([id, label, c]) => {
    LABEL[id] = label;
    return `<div class="tile" id="t_${id}"><div class="l">${label}</div><div class="v" id="v_${id}" style="color:var(--${c || color})">--</div></div>`;
  }).join("");
}
makeTiles("liveGrid", LIVE_TILES);
makeTiles("histGrid", HIST_TILES);

const shown = {};   // tile id -> display text
const num = {};     // tile id -> numeric value (for alerts)
function setTile(id, text, n) {
  shown[id] = text;
  recordHist(id, text);
  if (n !== undefined) num[id] = n;
  const v = $("v_" + id); if (!v) return;
  v.textContent = text;
  $("t_" + id).classList.toggle("na", text === "N/A");
}

// ===================== Live graphs =====================
// Every numeric reading is recorded (last ~10 min), so a graph opened later already has history.
const HIST = {}, HIST_MAX = 4000, MAX_CHARTS = 4;
let graphSel = [], graphWin = 60, frozenAt = null, hoverT = null;
function toNumber(text) {
  const t = String(text).replace(/,/g, "");
  if (/^(ON|YES|Locked)$/i.test(t)) return 1;
  if (/^(OFF|NO|Unlocked)$/i.test(t)) return 0;
  const mm = t.match(/^(\d+):(\d\d)$/);              // run time m:ss -> minutes
  if (mm) return +mm[1] + mm[2] / 60;
  const m = t.match(/-?\d+(\.\d+)?/);
  return m ? parseFloat(m[0]) : null;
}
function recordHist(id, text) {
  if (text === "--" || text === "N/A") return;
  const v = toNumber(text);
  if (v == null || !isFinite(v)) return;
  const h = HIST[id] || (HIST[id] = []);
  h.push([performance.now() / 1000, v]);
  if (h.length > HIST_MAX) h.splice(0, h.length - HIST_MAX);
}
function unitOf(id) { const t = shown[id] || ""; const u = t.replace(/,/g, "").replace(/^[^0-9-]*-?[0-9.]+\s*/, "").trim(); return u.length <= 8 ? u : ""; }
function fmtNum(v) { const a = Math.abs(v); return a >= 100 ? Math.round(v).toString() : a >= 10 ? v.toFixed(1) : v.toFixed(2); }
function renderGraphBar() {
  const wins = [[30, "30 s"], [60, "1 min"], [180, "3 min"], [600, "10 min"]];
  $("gbar").innerHTML = graphSel.length
    ? wins.map(([w, l]) => `<button data-win="${w}" class="${w === graphWin ? "on" : ""}">${l}</button>`).join("") +
      `<button id="gFreeze" class="${frozenAt ? "on" : ""}">${frozenAt ? "▶ Resume" : "⏸ Freeze"}</button>` +
      `<button id="gClear">Clear graphs</button><span>Tap a reading to add or remove it.</span>`
    : "📈 Tap any reading to graph it live (up to 4 at once).";
}
function toggleGraph(id) {
  const i = graphSel.indexOf(id);
  if (i >= 0) graphSel.splice(i, 1);
  else { if (graphSel.length >= MAX_CHARTS) graphSel.shift(); graphSel.push(id); }
  document.querySelectorAll(".tile.sel").forEach((t) => t.classList.remove("sel"));
  graphSel.forEach((g) => { const t = $("t_" + g); if (t) t.classList.add("sel"); });
  $("charts").innerHTML = graphSel.map((g) => `<div class="chart" data-id="${g}"><div class="hd"><span><b>${esc(LABEL[g] || g)}</b> <span class="cur"></span></span><span><span class="rng"></span> <span class="x" title="Remove">✕</span></span></div><canvas></canvas></div>`).join("");
  renderGraphBar();
  drawCharts();
}
document.addEventListener("click", (e) => {
  const tile = e.target.closest(".tile");
  if (tile && tile.id.startsWith("t_")) { toggleGraph(tile.id.slice(2)); return; }
  const x = e.target.closest(".chart .x");
  if (x) { toggleGraph(x.closest(".chart").dataset.id); return; }
  const wb = e.target.closest("[data-win]");
  if (wb) { graphWin = +wb.dataset.win; renderGraphBar(); drawCharts(); return; }
  if (e.target.id === "gFreeze") { frozenAt = frozenAt ? null : performance.now() / 1000; renderGraphBar(); drawCharts(); return; }
  if (e.target.id === "gClear") { graphSel.slice().forEach(toggleGraph); }
});
function pointerT(ev, canvas) {
  const r = canvas.getBoundingClientRect(), pt = ev.touches ? ev.touches[0] : ev;
  const f = Math.min(1, Math.max(0, (pt.clientX - r.left - 44) / (r.width - 52)));
  const now = frozenAt || performance.now() / 1000;
  return now - graphWin + f * graphWin;
}
["mousemove", "touchmove", "touchstart"].forEach((evn) => document.addEventListener(evn, (ev) => {
  const c = ev.target.closest && ev.target.closest(".chart canvas");
  hoverT = c ? pointerT(ev, c) : null;
  if (c) drawCharts();
}, { passive: true }));
document.addEventListener("mouseleave", () => { hoverT = null; });
function drawCharts() {
  const now = frozenAt || performance.now() / 1000, t0 = now - graphWin;
  const css = getComputedStyle(document.documentElement);
  const gridC = css.getPropertyValue("--line").trim(), textC = css.getPropertyValue("--muted").trim();
  document.querySelectorAll("#charts .chart").forEach((box) => {
    const id = box.dataset.id, cv = box.querySelector("canvas");
    const all = HIST[id] || [], pts = all.filter((p) => p[0] >= t0 && p[0] <= now);
    const color = getComputedStyle($("v_" + id) || box).color;
    const dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
    if (cv.width !== Math.round(W * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
    const g = cv.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
    const L = 44, R = 8, T = 6, B = 16, pw = W - L - R, ph = H - T - B;
    const u = unitOf(id);
    box.querySelector(".cur").textContent = shown[id] || "";
    if (!pts.length) { g.fillStyle = textC; g.font = "12px sans-serif"; g.fillText("Waiting for data…", L, T + ph / 2); box.querySelector(".rng").textContent = ""; return; }
    let lo = Math.min(...pts.map((p) => p[1])), hi = Math.max(...pts.map((p) => p[1]));
    box.querySelector(".rng").textContent = `min ${fmtNum(lo)} · max ${fmtNum(hi)}${u ? " " + u : ""}`;
    if (hi - lo < 1e-9) { lo -= 1; hi += 1; } else { const pad = (hi - lo) * 0.08; lo -= pad; hi += pad; }
    const X = (t) => L + (t - t0) / graphWin * pw, Y = (v) => T + (1 - (v - lo) / (hi - lo)) * ph;
    // recessive grid + y labels
    g.strokeStyle = gridC; g.lineWidth = 1; g.fillStyle = textC; g.font = "10px sans-serif"; g.textAlign = "right"; g.textBaseline = "middle";
    for (let k = 0; k <= 2; k++) { const v = lo + (hi - lo) * k / 2, y = Y(v); g.beginPath(); g.moveTo(L, y); g.lineTo(L + pw, y); g.stroke(); g.fillText(fmtNum(v), L - 4, y); }
    g.textAlign = "left"; g.textBaseline = "alphabetic"; g.fillText(`-${graphWin >= 60 ? graphWin / 60 + " min" : graphWin + " s"}`, L, H - 3);
    g.textAlign = "right"; g.fillText(frozenAt ? "frozen" : "now", L + pw, H - 3);
    // line
    g.strokeStyle = color; g.lineWidth = 2; g.lineJoin = "round"; g.beginPath();
    pts.forEach((p, i) => (i ? g.lineTo(X(p[0]), Y(p[1])) : g.moveTo(X(p[0]), Y(p[1])))); g.stroke();
    const last = pts[pts.length - 1];
    g.fillStyle = color; g.beginPath(); g.arc(X(last[0]), Y(last[1]), 4, 0, 7); g.fill();
    // synced crosshair + readout
    if (hoverT != null && hoverT >= t0) {
      let best = pts[0]; for (const p of pts) if (Math.abs(p[0] - hoverT) < Math.abs(best[0] - hoverT)) best = p;
      const x = X(best[0]);
      g.strokeStyle = textC; g.lineWidth = 1; g.beginPath(); g.moveTo(x, T); g.lineTo(x, T + ph); g.stroke();
      g.fillStyle = color; g.beginPath(); g.arc(x, Y(best[1]), 4, 0, 7); g.fill();
      const ago = Math.max(0, now - best[0]).toFixed(1);
      box.querySelector(".cur").textContent = `${fmtNum(best[1])}${u ? " " + u : ""} (${ago}s ago)`;
    }
  });
}
setInterval(() => { if (graphSel.length && !frozenAt) drawCharts(); }, 250);

// ===================== ELM327 transport =====================
const NORDIC = ["6e400001-b5a3-f393-e0a9-e50e24dcca9e", "6e400002-b5a3-f393-e0a9-e50e24dcca9e", "6e400003-b5a3-f393-e0a9-e50e24dcca9e"];
const FFF0 = ["0000fff0-0000-1000-8000-00805f9b34fb", "0000fff2-0000-1000-8000-00805f9b34fb", "0000fff1-0000-1000-8000-00805f9b34fb"];
const decoder = new TextDecoder();
let device = null, rxChar = null, txChar = null, connected = false;
let buf = "", pending = null;
let cmdChain = Promise.resolve(), txnChain = Promise.resolve();

function onData(ev) {
  buf += decoder.decode(ev.target.value, { stream: true });
  if (pending && buf.includes(">")) { const out = buf; buf = ""; pending(out); }
}
function rawSend(cmd, timeoutMs) {
  return new Promise((resolve) => {
    buf = "";
    let t;
    const done = (out) => { clearTimeout(t); pending = null; resolve(out); };
    t = setTimeout(() => done(buf), timeoutMs);
    pending = done;
    const data = new TextEncoder().encode(cmd + "\r");
    const w = rxChar.properties.writeWithoutResponse && rxChar.writeValueWithoutResponse
      ? rxChar.writeValueWithoutResponse(data)
      : (rxChar.writeValueWithResponse ? rxChar.writeValueWithResponse(data) : rxChar.writeValue(data));
    w.catch(() => done(""));
  });
}
// One command at a time on the wire
function sendCmd(cmd, timeoutMs = 1000) {
  if (!rxChar) return Promise.resolve("");
  const p = cmdChain.then(() => rawSend(cmd, timeoutMs));
  cmdChain = p.catch(() => {});
  return p;
}
// One multi-command "transaction" at a time (so header switches never interleave)
function txn(fn) { const p = txnChain.then(fn); txnChain = p.catch(() => {}); return p; }

const isErr = (raw) => !raw || /NO ?DATA|UNABLE|ERROR|STOPPED|\?|BUFFER/i.test(raw);

// Split an ELM reply into complete messages (handles ISO-TP multi-frame "0: 1: 2:" lines and multiple ECUs)
function messages(raw) {
  const out = []; let cur = null;
  for (let l of (raw || "").split(/[\r\n]+/)) {
    l = l.replace(/[\s>]/g, "").toUpperCase();
    if (!l) continue;
    if (/^[0-9A-F]{3}$/.test(l)) { cur = { hex: "", len: parseInt(l, 16) }; out.push(cur); continue; }
    const mf = l.match(/^([0-9A-F]):([0-9A-F]*)$/);
    if (mf) { if (cur) cur.hex += mf[2]; continue; }
    if (/^[0-9A-F]+$/.test(l)) out.push({ hex: l, len: 0 });
  }
  return out.map((m) => (m.len ? m.hex.slice(0, m.len * 2) : m.hex));
}
const bytesOf = (hex) => { const b = []; for (let i = 0; i + 2 <= hex.length; i += 2) b.push(parseInt(hex.substr(i, 2), 16)); return b; };
const respCode = (svc) => (parseInt(svc, 16) + 0x40).toString(16).toUpperCase().padStart(2, "0");

let isCan = false, curHeader = "7DF", baseHeader = "7DF", batchOK = false, fastOK = true;
let baseProto = "6", curProto = "6", curCra = "";
// Point the adapter at one module. 3-char headers are 11-bit CAN (e.g. 7E0, 700);
// 4-char headers like DA10 are 29-bit (18 DA 10 F1), used by Honda, newer Stellantis, etc.
async function setAddr(hdr, rax) {
  if (!isCan) return;
  const ext = hdr.length === 4;
  const base29 = baseProto === "7" || baseProto === "9";
  const want = ext ? (base29 ? baseProto : String(+baseProto + 1)) : (base29 ? String(+baseProto - 1) : baseProto);
  if (want !== curProto) {
    await sendCmd("ATSP" + want, 500);
    curProto = want; curHeader = ""; curCra = "?";
    if (ext) await sendCmd("ATCP18", 400);
  }
  const full = ext ? hdr + "F1" : hdr;
  if (full !== curHeader) { await sendCmd("ATSH" + full, 500); curHeader = full; }
  let cra = "";
  if (ext) cra = "18DAF1" + (rax || hdr.slice(2));
  else if (rax) cra = rax;
  else if (hdr !== "7DF" && !/^7E[0-7]$/.test(hdr)) cra = (parseInt(hdr, 16) + 8).toString(16).toUpperCase();
  if (cra !== curCra) { await sendCmd(cra ? "ATCRA" + cra : "ATCRA", 400); curCra = cra; }
}
const setHeader = (h) => setAddr(h, "");

// Supported-ID bitmaps (Mode 01 PIDs / Mode 06 MIDs) -> Set of "0C", "A2", ...
async function supported(svc, ranges) {
  const set = new Set(); let any = false;
  for (const r of ranges) {
    const raw = await sendCmd(svc + r, 2000);
    const pre = respCode(svc) + r;
    let bits = 0, found = false;
    for (const m of messages(raw)) {
      if (m.startsWith(pre) && m.length >= pre.length + 8) { bits = (bits | parseInt(m.substr(pre.length, 8), 16)) >>> 0; found = true; }
    }
    if (!found) break;
    any = true;
    for (let i = 0; i < 32; i++) if ((bits >>> (31 - i)) & 1) set.add((parseInt(r, 16) + i + 1).toString(16).toUpperCase().padStart(2, "0"));
    if (!(bits & 1)) break;
  }
  return any ? set : null;
}

// ===================== Mode 01 PID table =====================
const pct = (b) => Math.round(b[0] * 100 / 255) + "%";
const degF = (c) => Math.round(c * 1.8 + 32);
const tF = (b) => degF(b[0] - 40) + " °F";
const trimN = (b) => (b[0] - 128) * 100 / 128;
const trim = (b) => { const v = trimN(b); return (v > 0 ? "+" : "") + v.toFixed(1) + "%"; };
const o2v = (b) => (b[0] / 200).toFixed(3) + " V";
const lam = (b) => "λ " + ((b[0] * 256 + b[1]) / 32768).toFixed(3);
const u16 = (b, i = 0) => b[i] * 256 + b[i + 1];
const PIDS = {
  "0C": { tile: "rpm", tier: 1, len: 2, fn: (b) => Math.round(u16(b) / 4) + " RPM", n: (b) => u16(b) / 4 },
  "04": { tile: "load", tier: 1, len: 1, fn: pct },
  "11": { tile: "tps", tier: 1, len: 1, fn: pct },
  "0D": { tile: "spd", tier: 1, len: 1, fn: (b) => Math.round(b[0] * 0.621371) + " MPH" },
  "06": { tile: "stft1", tier: 2, len: 1, fn: trim, n: trimN },
  "07": { tile: "ltft1", tier: 2, len: 1, fn: trim, n: trimN },
  "08": { tile: "stft2", tier: 2, len: 1, fn: trim, n: trimN },
  "09": { tile: "ltft2", tier: 2, len: 1, fn: trim, n: trimN },
  "0E": { tile: "timing", tier: 2, len: 1, fn: (b) => (b[0] / 2 - 64).toFixed(1) + "°" },
  "10": { tile: "maf", tier: 2, len: 2, fn: (b) => (u16(b) / 100).toFixed(1) + " g/s" },
  "0B": { tile: "map", tier: 2, len: 1, fn: (b) => (b[0] * 0.145038).toFixed(1) + " PSI" },
  "49": { tile: "app", tier: 2, len: 1, fn: pct },
  "14": { tile: "o2b1s1", tier: 2, len: 2, fn: o2v }, "24": { tile: "o2b1s1", tier: 2, len: 4, fn: lam }, "34": { tile: "o2b1s1", tier: 2, len: 4, fn: lam },
  "15": { tile: "o2b1s2", tier: 2, len: 2, fn: o2v },
  "16": { tile: "o2b2s1", tier: 2, len: 2, fn: o2v }, "26": { tile: "o2b2s1", tier: 2, len: 4, fn: lam }, "36": { tile: "o2b2s1", tier: 2, len: 4, fn: lam },
  "17": { tile: "o2b2s2", tier: 2, len: 2, fn: o2v },
  "18": { tile: "o2b2s1", tier: 2, len: 2, fn: o2v }, "28": { tile: "o2b2s1", tier: 2, len: 4, fn: lam }, "38": { tile: "o2b2s1", tier: 2, len: 4, fn: lam },
  "19": { tile: "o2b2s2", tier: 2, len: 2, fn: o2v },
  "05": { tile: "ect", tier: 3, len: 1, fn: tF, n: (b) => degF(b[0] - 40) },
  "0F": { tile: "iat", tier: 3, len: 1, fn: tF },
  "46": { tile: "aat", tier: 3, len: 1, fn: tF },
  "5C": { tile: "eot", tier: 3, len: 1, fn: tF },
  "23": { tile: "frp", tier: 3, len: 2, fn: (b) => Math.round(u16(b) * 10 * 0.145038) + " PSI" },
  "0A": { tile: "frp", tier: 3, len: 1, fn: (b) => Math.round(b[0] * 3 * 0.145038) + " PSI" },
  "2F": { tile: "fli", tier: 3, len: 1, fn: pct },
  "2E": { tile: "evap", tier: 3, len: 1, fn: pct },
  "33": { tile: "baro", tier: 3, len: 1, fn: (b) => (b[0] * 0.2953).toFixed(1) + " inHg" },
  // --- extra SAE J1979 PIDs ---
  "03": { tile: "fss", tier: 2, len: 2, fn: (b) => { const f = (x) => ({ 1: "OL cold", 2: "CL", 4: "OL load/decel", 8: "OL fault", 16: "CL O2 fault" }[x] || (x ? "0x" + x.toString(16) : ""));
          return f(b[0]) + (b[1] ? " / " + f(b[1]) : ""); } },
  "43": { tile: "absload", tier: 2, len: 2, fn: (b) => Math.round(u16(b) * 100 / 255) + "%" },
  "44": { tile: "cmdlam", tier: 2, len: 2, fn: (b) => "λ " + (u16(b) / 32768).toFixed(3) },
  "5E": { tile: "fuelrate", tier: 2, len: 2, fn: (b) => (u16(b) / 20 * 0.264172).toFixed(2) + " gal/h" },
  "42": { tile: "cmv", tier: 3, len: 2, fn: (b) => (u16(b) / 1000).toFixed(2) + " V" },
  "3C": { tile: "cat1", tier: 3, len: 2, fn: (b) => degF(u16(b) / 10 - 40) + " °F" },
  "3D": { tile: "cat2", tier: 3, len: 2, fn: (b) => degF(u16(b) / 10 - 40) + " °F" },
  "2C": { tile: "egrcmd", tier: 3, len: 1, fn: pct },
  "2D": { tile: "egrerr", tier: 3, len: 1, fn: trim },
  "32": { tile: "evapvp", tier: 3, len: 2, fn: (b) => (s16(u16(b)) / 4 * 0.0040146).toFixed(2) + " inH2O" },
  "52": { tile: "eth", tier: 3, len: 1, fn: pct },
  "59": { tile: "frpabs", tier: 3, len: 2, fn: (b) => Math.round(u16(b) * 10 * 0.145038) + " PSI" },
  "70": { tile: "boost", tier: 3, len: 10, fn: (b) => (b[0] & 0x02) ? (u16(b, 3) * 0.03125 * 0.145038).toFixed(1) + " PSI" : null },
  "78": { tile: "egt", tier: 3, len: 9, fn: (b) => (b[0] & 0x01) ? degF(u16(b, 1) / 10 - 40) + " °F" : null },
  "1F": { tile: "runtime", tier: 3, len: 2, fn: (b) => mmss(u16(b)) },
  "31": { tile: "clrDist", tier: 4, len: 2, fn: (b) => Math.round(u16(b) * 0.621371) + " mi", n: (b) => u16(b) * 0.621371 },
  "4E": { tile: "clrTime", tier: 4, len: 2, fn: (b) => hrsMin(u16(b)) },
  "30": { tile: "warmups", tier: 4, len: 1, fn: (b) => String(b[0]), n: (b) => b[0] },
  "21": { tile: "milDist", tier: 4, len: 2, fn: (b) => Math.round(u16(b) * 0.621371) + " mi" },
  "4D": { tile: "milTime", tier: 4, len: 2, fn: (b) => hrsMin(u16(b)) },
  "A6": { tile: "odo", tier: 4, len: 4, fn: (b) => Math.round((((b[0] * 256 + b[1]) * 256 + b[2]) * 256 + b[3]) / 10 * 0.621371).toLocaleString() + " mi" },
};
const TIER_EVERY = { 1: 1, 2: 2, 3: 6, 4: 30 };
const mmss = (sec) => Math.floor(sec / 60) + ":" + String(sec % 60).padStart(2, "0");
const hrsMin = (min) => (min >= 60 ? Math.floor(min / 60) + " h " : "") + (min % 60) + " min";
let active = [];   // PIDs actually polled, chosen from what the ECM says it supports

function choosePids(sup) {
  const has = (p) => !sup || sup.has(p);
  const alt1D = sup && sup.has("1D") && !sup.has("13");   // 4-bank O2 layout
  const pick = {
    rpm: ["0C"], load: ["04"], tps: ["11"], spd: ["0D"], stft1: ["06"], ltft1: ["07"], stft2: ["08"], ltft2: ["09"],
    timing: ["0E"], maf: ["10"], map: ["0B"], app: ["49"], ect: ["05"], iat: ["0F"], aat: ["46"], eot: ["5C"],
    frp: ["23", "0A"], fli: ["2F"], evap: ["2E"], baro: ["33"],
    fss: ["03"], absload: ["43"], cmdlam: ["44"], fuelrate: ["5E"], cmv: ["42"], cat1: ["3C"], cat2: ["3D"],
    egrcmd: ["2C"], egrerr: ["2D"], evapvp: ["32"], eth: ["52"], frpabs: ["59"], boost: ["70"], egt: ["78"],
    runtime: ["1F"], clrDist: ["31"], clrTime: ["4E"], warmups: ["30"], milDist: ["21"], milTime: ["4D"], odo: ["A6"],
    o2b1s1: ["24", "34", "14"], o2b1s2: ["15"],
    o2b2s1: alt1D ? ["26", "36", "16"] : ["28", "38", "18"], o2b2s2: alt1D ? ["17"] : ["19"],
  };
  active = [];
  for (const [tile, cands] of Object.entries(pick)) {
    const p = cands.find(has);
    if (p) active.push(p); else setTile(tile, "N/A");
  }
}
function applyPid(pid, b) {
  const d = PIDS[pid]; if (!d || b.length < d.len) return;
  const text = d.fn(b);
  if (text == null) return;
  setTile(d.tile, text, d.n ? d.n(b) : undefined);
  if (pid === "31" || pid === "30") checkCleared();
}
// Warn when codes were cleared recently (common on cars that come in "with no codes")
function checkCleared() {
  const mi = num.clrDist, wu = num.warmups, el = $("clearWarn");
  const recent = (mi !== undefined && mi < 50) || (wu !== undefined && wu < 5);
  el.style.display = recent ? "block" : "none";
  if (recent) el.textContent = `⚠️ Codes were cleared recently: ${mi !== undefined ? Math.round(mi) + " miles" : ""}` +
    `${mi !== undefined && wu !== undefined ? " / " : ""}${wu !== undefined ? wu + " warm-up cycles" : ""} ago. ` +
    "Check readiness monitors; codes may not have had time to come back.";
}

function parse01(raw, wanted) {
  const got = {};
  for (const m of messages(raw)) {
    if (!m.startsWith("41")) continue;
    let i = 2;
    while (i + 2 <= m.length) {
      const pid = m.substr(i, 2), d = PIDS[pid];
      if (!d || !wanted.includes(pid) || got[pid]) break;
      const end = i + 2 + d.len * 2;
      if (end > m.length) break;
      got[pid] = bytesOf(m.slice(i + 2, end));
      i = end;
    }
  }
  return got;
}
async function pollPids(pids) {
  if (batchOK) {
    for (let i = 0; i < pids.length; i += 6) {
      const chunk = pids.slice(i, i + 6);
      const got = parse01(await sendCmd("01" + chunk.join(""), 1500), chunk);
      for (const [p, b] of Object.entries(got)) applyPid(p, b);
    }
    return;
  }
  for (const p of pids) {
    const fast = isCan && fastOK && PIDS[p].len <= 5;   // single-frame replies only
    let raw = await sendCmd("01" + p + (fast ? "1" : ""), 800);
    if (isCan && fastOK && /\?/.test(raw)) { fastOK = false; raw = await sendCmd("01" + p, 800); }
    const got = parse01(raw, [p]);
    if (got[p]) applyPid(p, got[p]);
  }
}

// ===================== OEM enhanced data (Service $22 / $21) =====================
// Source: OBDb community database (github.com/OBDb), collected from ~40 popular Asian & domestic models.
// Line format: hdr|rax|request|bitOffset|bitLen|mul|div|add|signed|littleEndian|unit|name|modelYears
const OEM_RAW = `#TOYOTA
700||221627|0|16|1|256|-40|0|0|C|trans fluid temp, pan v3|*
700||2210A7|0|8|1|1|0|0|0||Misfire count, cylinder 1|*
700||2210A7|8|8|1|1|0|0|0||Misfire count, cylinder 2|*
700||2210A7|16|8|1|1|0|0|0||Misfire count, cylinder 3|*
700||2210A7|24|8|1|1|0|0|0||Misfire count, cylinder 4|*
7E0||2145|24|8|1|1|0|0|0||Cylinder #1 misfire count|*
7E0||2145|32|8|1|1|0|0|0||Cylinder #2 misfire count|*
7E0||2145|40|8|1|1|0|0|0||Cylinder #3 misfire count|*
7E0||2145|48|8|1|1|0|0|0||Cylinder #4 misfire count|*
7E0||2145|56|8|1|1|0|0|0||All cylinders misfire count|*
700||221074|0|16|10|128|0|0|0|kPa|Engine oil pressure|*
700||22107B|192|8|1|1|-40|0|0|C|Engine oil temp|*
700||221F5C|0|8|1|1|-40|0|0|C|Engine oil temp, variation 2|*
7E0||2151|72|8|1|1|-40|0|0|C|Engine oil temp|*
700||221622|0|16|5333|21845000|0|0|0||trans shift state ratio|*
700||221628|0|16|1|256|-40|0|0|C|trans fluid post-converter temp v3|*
700||221638|0|8|1|1|-40|0|0|C|trans fluid temp|*
701||221622|0|16|5333|21845000|0|0|0||trans shift state ratio|*
701||221627|0|16|0.00703125|1|-40|0|0|F|trans fluid pan temp|*
701||221628|0|16|0.00703125|1|-40|0|0|F|trans fluid post-converter temp|*
7E0||2182|0|16|1|256|-40|0|0|C|trans temp, pan|*
7E0||2182|16|16|1|256|-40|0|0|C|trans temp, torque converter|*
7E0||21BD|0|8|50|1|0|0|0|rpm|trans output shaft speed|*
7E0||21BE|0|8|40|1|0|0|0|kPa|Continuously variable trans oil pressure|*
7E0||21D9|0|16|1|256|-40|0|0|C|trans fluid temp v14|*
7E0||21D9|24|8|1|1|-40|0|0|C|trans fluid temp v21|*
7E0||21D9|32|16|1|256|-40|0|0|C|trans fluid temp v5|*
7E0||21D9|48|16|1|256|-40|0|0|C|trans fluid temp v8|*
700||221620|7|1|1|1|0|0|0|onoff|Lock up state|*
700||221621|0|8|1|1|0|0|0||Gear|*
701||221620|7|1|1|1|0|0|0|onoff|Lock up state|*
7E0||21DA|0|8|1|1|0|0|0||Current gear|*
700||22105C|16|16|312.5|10000|-1024|0|0||Knock feedback value|*
700||221F6D|8|16|10|1|0|0|0|kPa|High fuel pressure, target|*
700||221F6D|24|16|10|1|0|0|0|kPa|High fuel pressure, actual|*
700||221F6D|64|16|10|1|0|0|0|kPa|Low fuel pressure|*
7D2||221040|16|8|1|1|-40|0|0|C|Transaxle oil temp|*
7E1||2182|0|16|1|256|-40|0|0|C|trans fluid temp v10|*
7E1||2182|16|16|1|256|-40|0|0|C|trans fluid temp v11|*
7E1||21D9|0|16|1|256|-40|0|0|C|trans fluid temp v14|*
7E1||21D9|24|8|1|1|-40|0|0|C|trans fluid temp v21|*
7E1||21D9|32|16|1|256|-40|0|0|C|trans fluid temp v9|*
7E1||21D9|48|16|1|256|-40|0|0|C|trans fluid temp v12|*
7E0||2185|0|8|1|1|0|0|0||Gear|*
7E0||2185|8|1|1|1|0|0|0|onoff|Gear lock-up|*
#NISSAN
7E1||2101|152|8|9|5|-67|0|0|F|trans fluid temp v1|*
7E1||2101|160|8|9|5|-67|0|0|F|trans fluid temp v2|*
7E1||2101|120|16|1|1|0|1|0|rpm|Torque converter slip|*
7E0||221137|0|8|1|2|-64|0|0|deg|Intake camshaft advance, bank 2|*
758|778|220201|0|8|1|4|0|0|0|psi|Front left tire pressure|*
758|778|220202|0|8|1|4|0|0|0|psi|Front right tire pressure|*
758|778|220203|0|8|1|4|0|0|0|psi|Rear right tire pressure|*
758|778|220204|0|8|1|4|0|0|0|psi|Rear left tire pressure|*
7E0||221124|0|8|1|1|-100|0|0|%|Air/fuel ratio adjustment, bank 2|*
7E0||221205|0|16|1|200|0|0|0|V|Mass air flow sensor voltage, bank 2|*
7E0||221307|1|1|1|1|0|0|0||Air conditioning compressor|*
7E0||221307|6|1|1|1|0|0|0||Idle control mode|*
7E0||221307|1|1|1|1|0|0|0|onoff|Air conditioning compressor|*
7E0||221307|6|1|1|1|0|0|0|onoff|Idle control mode|*
7E0||221186|0|8|1|1|0|0|0|L|Remaining fuel|*
#HONDA
DA1D|1D|222201|208|8|1|1|-40|0|0|C|Automatic trans fluid temp|*
DA1E|1E|222201|208|8|1|1|-40|0|0|C|trans fluid temp v4|*
DA1E|1E|223083|112|8|1|1|-40|0|0|C|trans fluid temp|*
DA11|11|222663|160|16|1|1|0|0|0||Misfire count #1 v3|*
DA11|11|222663|176|16|1|1|0|0|0||Misfire count #2 v3|*
DA11|11|222663|192|16|1|1|0|0|0||Misfire count #3 v3|*
DA11|11|222663|208|16|1|1|0|0|0||Misfire count #4 v3|*
DA11|11|222663|272|16|1|1|0|0|0||Misfire count #1 v2|*
DA11|11|222663|288|16|1|1|0|0|0||Misfire count #2 v2|*
DA11|11|222663|304|16|1|1|0|0|0||Misfire count #3 v2|*
DA11|11|222663|320|16|1|1|0|0|0||Misfire count #4 v2|*
DA11|11|22266C|48|8|1|1|0|0|0||Misfire count #1 v1|*
DA11|11|22266C|56|8|1|1|0|0|0||Misfire count #2 v1|*
DA11|11|22266C|64|8|1|1|0|0|0||Misfire count #3 v1|*
DA11|11|22266C|72|8|1|1|0|0|0||Misfire count #4 v1|*
DA10|10|222666|88|8|1|1|-40|0|0|C|Engine oil temp v3|*
DA10|10|222666|112|8|1|1|-40|0|0|C|Engine oil temp v4|*
DA60|60|227060|256|16|1|1|0|0|0||Maintenance, trans fluid|*
DA0E|0E|222612|352|8|1|1|0|0|0||Current gear v2|*
DA0E|0E|222612|368|8|1|1|0|0|0||Current gear v3|*
DA1D|1D|222663|272|16|1|1|0|0|0||Misfire count 1|*
DA1D|1D|222663|288|16|1|1|0|0|0||Misfire count 2|*
DA1D|1D|222663|304|16|1|1|0|0|0||Misfire count 3|*
DA1D|1D|222663|320|16|1|1|0|0|0||Misfire count 4|*
DA11|11|222663|224|16|1|1|0|0|0||Misfire count #5 v3|*
DA11|11|222663|240|16|1|1|0|0|0||Misfire count #6 v3|*
DA11|11|222663|336|16|1|1|0|0|0||Misfire count #5 v2|*
DA11|11|222663|352|16|1|1|0|0|0||Misfire count #6 v2|*
DA11|11|22266C|80|8|1|1|0|0|0||Misfire count #5 v1|*
DA11|11|22266C|88|8|1|1|0|0|0||Misfire count #6 v1|*
DA11|11|222662|80|8|1.99|255|0|0|0||Knock control|*
DA11|11|222666|88|8|1|1|-40|0|0|C|Engine oil temp v1|*
DA11|11|222666|112|8|1|1|-40|0|0|C|Engine oil temp v2|*
DA10|10|222663|272|16|1|1|0|0|0||Misfire count #1|*
DA10|10|222663|288|16|1|1|0|0|0||Misfire count #2|*
DA10|10|222663|304|16|1|1|0|0|0||Misfire count #3|*
DA10|10|222663|320|16|1|1|0|0|0||Misfire count #4|*
DA1D|1D|222221|184|8|1|1|0|0|0||Current gear|*
DA60|60|227060|224|16|1|1|0|0|0||Maintenance, tire rotation|*
DA0E|0E|222663|160|16|1|1|0|0|0||Misfire count #1 v3|*
DA0E|0E|222663|176|16|1|1|0|0|0||Misfire count #2 v3|*
DA0E|0E|222663|192|16|1|1|0|0|0||Misfire count #3 v3|*
DA0E|0E|222663|208|16|1|1|0|0|0||Misfire count #4 v3|*
DA0E|0E|222663|224|16|1|1|0|0|0||Misfire count #5 v3|*
DA0E|0E|222663|240|16|1|1|0|0|0||Misfire count #6 v3|*
#SUBARU
7A3||2210D2|0|8|1|1|-50|0|0|C|Continuously variable trans temp|*
7A3||22113D|0|8|256|65535|0|0|0||Target gear ratio|*
7A3||22113E|0|16|256|65535|0|0|0||Actual gear ratio|*
7E0||2210E7|0|8|1|1|-40|0|0|C|Engine oil temp|*
7E0||221299|0|8|1|1|0|0|0|%|trans lock-up|*
7E1||221017|0|8|1|1|-50|0|0|C|CVT fluid temp|2010-
7E1||221065|0|8|1|2|0|0|0|%|AWD transfer clutch duty|2010-
7E1||22300E|0|16|1|1|0|0|0|rpm|CVT primary pulley speed|2010-
7E1||2230D0|0|16|1|1|0|0|0|rpm|CVT secondary pulley speed|2010-
7E1||2230DA|0|16|1|255|0|0|0||CVT gear ratio, actual|2010-
7E1||2230F8|0|16|1|255|0|0|0||CVT gear ratio, target|2010-
7A2||220023|0|16|1|1|0|0|0|kPa|Fuel rail pressure|*
7E1||221045|0|8|1|2|0|0|0|%|Torque converter lock-up duty|2010-
7E0||2210EC|0|8|1|1|-50|0|0|deg|Exhaust VVT retard angle right|*
7E0||2210ED|0|8|1|1|-50|0|0|deg|Exhaust VVT retard angle left|*
7E0||221291|0|8|1|1|-50|0|0|deg|Exhaust VVT retard, target angle right|*
7E0||221292|0|8|1|1|-50|0|0|deg|Exhaust VVT retard, target angle left|*
7A2||22003C|0|16|1|1|0|0|0|C|Exhaust gas temp, catalyst inlet|*
7A2||22114B|0|8|5|1|-40|0|0|C|Estimated catalyst temp|*
7A2||2210AC|0|8|20|51|0|0|0|%|Primary boost control|*
7E0||2210AC|0|8|20|51|0|0|0|%|Primary boost control|*
7E0||22128F|0|8|1|1|-50|0|0|deg|Intake VVT advance, target angle right|*
7E0||221290|0|8|1|1|-50|0|0|deg|Intake VVT advance, target angle left|*
7E0||221352|0|8|20|51|0|0|0|%|Split ratio of fuel injection 1|*
7E0||221353|0|8|20|51|0|0|0|%|Split ratio of fuel injection 2|*
7E0||221354|0|8|20|51|0|0|0|%|Split ratio of fuel injection 3|*
7E0||221355|0|8|20|51|0|0|0|%|Split ratio of fuel injection 4|*
7E7||221037|0|8|25.5|255|0|0|0|V|12V aux battery voltage|*
7E7||221039|0|8|25.5|255|0|0|0|V|12V engine restart battery voltage|*
7A2||220005|0|8|1|1|-40|0|0|C|Coolant temp|*
7E0||220005|0|8|1|1|-40|0|0|C|Coolant temp|*
7A2||22003E|0|16|1|1|0|0|0|C|Exhaust gas temp at DPF inlet|*
7A2||2210A7|0|8|1|1|-40|0|0|C|Fuel temp|*
7A2||2210B3|0|8|100|255|0|0|0|%|Fuel pump duty|*
7A2||2210E6|0|16|1|100|0|0|0||Fuel tank air pressure|*
7A2||22111F|0|8|1|1|-40|0|0|C|Inlet air temp, after air filter|*
7A2||22114C|0|8|5|1|-40|0|0|C|Estimated DPF temp|*
7A2||221251|0|8|1|1|0|0|0||Sub fuel pump relay switch|*
7A2||22307A|0|8|1.8|1|-40|0|0|F|Inlet air temp|*
7E0||221276|0|8|1|50|0|0|0|V|Sub throttle sensor|*
7E0||221277|0|8|1|50|0|0|0|V|Main throttle sensor|*
7E0||221289|0|16|1|100|0|0|0|gps|Idle mass air flow|*
7E0||22128A|0|16|1|100|-300|0|0|gps|Idle mass air flow feedback correction|*
7E0||22128E|0|16|1|100|-300|0|0|gps|Idle dirty throttle correction|*
7E0||2212CE|0|8|1|2|-40|0|0|C|Ambient temp for sensor signal|*
#GM
7E0||22115C|0|8|3|5|-21.6|0|0|psi|Engine oil pressure 2|*
7E0||221940|0|8|1|1|-40|0|0|C|trans fluid temp v1|*
7E2||221940|0|8|1|1|-40|0|0|C|trans fluid temp|*
7E2||221941|0|16|1|4|0|1|0|rpm|trans input shaft speed, 2|*
7E2||22280D|0|8|1|1|-40|0|0|C|trans fluid temp v6|*
7E2||22199A|0|8|1|1|0|0|0||Current gear v2|*
7E0||2211EA|0|8|1|1|0|0|0||Misfires, current, cylinder 5|-2012;-2020;-2017
7E0||2211EB|0|8|1|1|0|0|0||Misfires, current, cylinder 6|-2012;-2020;-2017
7E0||221200|0|8|1|1|0|0|0||Total misfire|*
7E0||221205|0|8|1|1|0|0|0||Misfires, current, cylinder 2|*
7E0||221206|0|8|1|1|0|0|0||Misfires, current, cylinder 1|*
7E0||221207|0|8|1|1|0|0|0||Misfires, current, cylinder 3|*
7E0||221208|0|8|1|1|0|0|0||Misfires, current, cylinder 4|*
7E0||221154|0|8|1|1|-40|0|0|C|Calculated engine oil temp|*
7E0||221C1B|0|8|400|100|0|0|0|kPa|Calculated engine oil pressure|*
7E0||222344|0|8|400|100|0|0|0|kPa|Engine oil absolute pressure|*
7E0||222345|0|8|400|100|0|0|0|kPa|Engine oil pressure|*
7E0||223318|0|1|1|1|0|0|0|onoff|Engine oil pressure control solenoid valve command|*
7E0||22199A|0|8|1|1|0|0|0||Current gear|*
7E0||223201|0|8|1|1|0|0|0||Current gear v3|*
7E2||2219D4|0|16|1|4|0|1|0|rpm|Clutch slip, AT C3, ring|*
7E2||222851|0|16|1|4|0|1|0|rpm|Clutch slip, AT C1, ring|*
7E0||2211A6|0|8|22|100|0|0|0|deg|Knock retard|*
7E0||22125D|0|8|1|1|0|0|0|deg|Knock retard, alternate|*
7E0||2212D9|0|8|45|100|0|0|0|deg|Total knock retard|*
7E2||222862|0|16|1|1|0|1|0||trans pressure|*
241|641|224005|0|32|1|1|0|0|0|hex|Front left tire sensor ID|*
241|641|224006|0|32|1|1|0|0|0|hex|Front right tire sensor ID|*
241|641|224007|0|32|1|1|0|0|0|hex|Rear right tire sensor ID|*
241|641|224008|0|32|1|1|0|0|0|hex|Rear left tire sensor ID|*
241|641|225005|0|16|1|16|0|0|0|kPa|Front left tire pressure|*
241|641|225006|0|16|1|16|0|0|0|kPa|Front right tire pressure|*
241|641|225007|0|16|1|16|0|0|0|kPa|Rear right tire pressure|*
241|641|225008|0|16|1|16|0|0|0|kPa|Rear left tire pressure|*
7E0||2211EC|0|8|1|1|0|0|0||Misfire current, cylinder 7|-2020
7E0||2211ED|0|8|1|1|0|0|0||Misfire current, cylinder 8|-2020
7E2||2219A1|0|8|1|1|0|0|0||Gear ratio|*
7E0||22248E|0|8|1|1|0|0|0|psi|Left front tire pressure|*
7E0||22248F|0|8|1|1|0|0|0|psi|Right front tire pressure|*
7E0||222490|0|8|1|1|0|0|0|psi|Right rear tire pressure|*
7E0||222491|0|8|1|1|0|0|0|psi|Left rear tire pressure|*
7E0||22119E|0|8|1|10|0|0|0||Air/fuel ratio, commanded|*
7E0||22114B|0|8|1|51|0|0|0|V|Exhaust gas recirculation voltage|*
7E0||221170|0|8|1|2.55|0|0|0|%|Evaporative emissions purge|*
DA40|40|224005|0|32|1|1|0|0|0|hex|Front left tire sensor ID|*
#FORD
7DF||221E1C|0|16|1|16|0|0|0|C|trans temp|*
7E0||221E1A|0|16|2|1|0|1|0|kPa|trans pressure, commanded|*
7E0||220345|0|32|1|1|0|0|0||Misfire events, latest cycle|*
7E0||220382|0|8|1|64|0|1|0||Misfire acceleration, cylinder 1|*
7E0||220388|0|8|1|64|0|1|0||Misfire acceleration, cylinder 2|*
7E0||22038A|0|8|1|64|0|1|0||Misfire acceleration, cylinder 3|*
7E0||22038B|0|8|1|64|0|1|0||Misfire acceleration, cylinder 4|*
7E0||220398|0|8|1|64|0|1|0||Misfire acceleration, cylinder 6|*
7E0||220415|0|16|1|1|0|1|0|kPa|Oil pressure|*
7E0||221E1C|0|16|1|16|0|1|0|C|trans oil temp|*
7E0||221E16|0|16|1|4096|0|0|0||Axle gear ratio, measured|*
7E0||221E19|0|16|16|65535|0|0|0||Gear ratio, commanded|*
7E0||221E1F|0|8|1|1|0|0|0||Gear, engaged|*
726||222813|0|16|1|20|0|0|0|psi|Tire pressure, front left|*
726||222814|0|16|1|20|0|0|0|psi|Tire pressure, front right|*
726||222815|0|16|1|20|0|0|0|psi|Tire pressure, rear right outer|*
726||222816|0|16|1|20|0|0|0|psi|Tire pressure, rear left outer|*
726||222817|0|16|1|20|0|0|0|psi|Tire pressure, rear right inner|*
726||222818|0|16|1|20|0|0|0|psi|Tire pressure, rear left inner|*
7E0||22038C|0|8|1|64|0|1|0||Misfire acceleration, cylinder 5|2009-
7E0||220403|0|16|1|1|0|0|0||Knock sensor, 1|*
7E0||220404|0|16|1|1|0|0|0||Knock sensor, 2|*
7E0||2205AC|0|8|1|1|0|0|0||Knock counter, cylinder 1|*
7E0||2205AD|0|8|1|1|0|0|0||Knock counter, cylinder 2|*
7E0||2205AE|0|8|1|1|0|0|0||Knock counter, cylinder 3|*
7E0||2205AF|0|8|1|1|0|0|0||Knock counter, cylinder 4|*
7E0||220324|0|16|5|1023|0|0|0|V|Fuel rail sensor voltage, high pressure|*
7E0||2203DC|0|16|1.4503773969|1|0|0|0|psi|Fuel pressure, high desired|*
7E0||22041F|0|8|435|1000|0|0|0|psi|Fuel pressure, low desired|*
7E0||220548|0|16|10000|137892|0|1|0|psi|Fuel pressure, low actual|*
7E0||22054D|0|16|1|1024|0|1|0|V|Fuel pressure sensor voltage, low|*
7E0||2205B0|0|8|1|1|0|0|0||Knock counter, cylinder 5|2009-
7E0||2205B1|0|8|1|1|0|0|0||Knock counter, cylinder 6|2009-
7E0||220316|0|16|25|8192|0|0|0|%|Camshaft solenoid duty cycle, intake|*
7E0||220317|0|16|25|8192|0|0|0|%|Camshaft solenoid duty cycle, exhaust|*
7E0||220318|0|16|1|16|0|0|0|deg|Camshaft position, intake actual|*
7E0||220319|0|16|1|16|0|0|0|deg|Camshaft position, exhaust actual|*
7E0||22031A|0|16|1|16|0|1|0|deg|Camshaft position error, intake|*
7E0||22031B|0|16|1|16|0|0|0|deg|Camshaft position error, exhaust|*
7E0||2203BB|0|16|1|16|0|1|0|deg|Camshaft position, exhaust desired|*
7E0||2203BC|0|16|1|16|0|1|0|deg|Camshaft position, intake desired|*
7E0||220462|0|16|100|32768|0|0|0|%|Wastegate duty cycle|*
7E0||22F43C|0|16|1|10|-40|0|0|C|Catalyst temp|*
7E0||22046F|0|8|1|1|0|0|0||Injection mode|*
7E0||22030F|0|16|1|32768|0|0|0||Lambda, commanded|*
#CHRYSLER
7E0||213A|80|8|4|1|0|0|0|F|trans sump temp v1|*
7E0||213A|96|16|9|320|32|0|0|F|trans torque converter temp v1|*
7E0||21CA|80|8|4|1|0|0|0|F|trans sump temp v2|*
7E0||21CA|96|16|9|320|32|0|0|F|trans torque converter temp v2|*
7E0||22B010|0|16|1|64|0|0|0|F|trans fluid temp v3|*
7E1||210A|128|8|9|5|-58|0|0|F|trans temp v2|*
7E1||2130|88|8|1|1|-50|0|0|C|trans fluid temp v3|*
7E1||213A|72|16|1|64|0|0|0|F|trans sump temp|*
7E1||2172|32|16|1|64|0|0|0|F|trans fluid temp v1|*
7E1||2208DF|0|8|1|1|-40|0|0|C|trans fluid temp|*
7E1||225034|0|16|1|10|-40|0|0|bar|trans main cylinder pressure|*
7E1||225043|0|8|1|1|-40|0|0|C|trans fluid temp|*
DA18|18|2204FE|0|8|1|1|-40|0|0|C|trans fluid temp|*
DA18|18|221018|0|16|1|1|-500|0|0|Nm|trans-reported torque|*
7E0||212D|56|8|9|5|-83|0|0|F|Engine oil temp|*
7E0||22022A|0|8|29|50|0|0|0|psi|Engine oil pressure|*
7E1||2204FE|0|8|1.8|1|-40|0|0|F|trans temp|2011-2023;-2024
7E0||2118|0|16|1|64|0|0|0|F|trans fluid temp v.2|*
7E0||22A002|0|8|9|5|-58|0|0|F|trans fluid temp v2|*
7E0||22A09F|0|8|1|1|0|0|0||trans gear, commanded|*
7E0||22A0A0|0|8|1|1|0|0|0||trans gear, actual|*
7E0||22A0A3|0|16|9|640|0|0|0|F|trans sump temp|*
7E0||22A0A4|0|16|9|320|0|0|0|F|trans torque converter temp|*
7E1||223C22|0|8|1|10|0|0|0||Current gear|*
DA18|18|22051A|0|4|1|1|0|0|0||Desired gear|2024-;2025-;2020-
DA18|18|22051A|4|4|1|1|0|0|0||Current gear|2024-;2025-;2020-
7E0||2201A9|0|16|1|13107|0|0|0|V|Knock sensor 1|*
7E0||2201AA|0|16|1|13107|0|0|0|V|Knock sensor 2|*
7E0||2201AE|0|16|1|2|0|0|0|deg|Short term knock retard|*
7E0||21D2|56|8|1|1|-64|0|0|C|Engine oil temp|*
DA10|10|2118|0|16|1|4|0|1|0|F|trans oil temp|2025-
7E1||2204FE|0|8|1|1|-40|0|0|C|Automatic trans fluid temp|*
DA18||221D07|0|8|25|1|0|0|0|rpm|trans output speed|*
DA18||221D08|0|8|25|1|0|0|0|rpm|trans input speed|*
DA18||221D09|0|8|1|1|-50|0|0|C|Automatic trans temp|*
7E0||22B028|0|16|1|1|0|1|0|rpm|Torque converter slip|*
7E0||22A001|48|16|1|1|0|1|0|rpm|Torque converter slip v2|*
DA18|18|222102|0|16|1|4|0|0|0|rpm|Gearbox output speed|*
DAC7|C7|220123|0|32|1|1|0|0|0|hex|Front left tire sensor id|2024-;2025-;2020-
DAC7|C7|220124|0|32|1|1|0|0|0|hex|Front right tire sensor id|2024-;2025-;2020-
DAC7|C7|220125|0|32|1|1|0|0|0|hex|Rear left tire sensor id|2024-;2025-;2020-
DAC7|C7|220127|0|32|1|1|0|0|0|hex|Rear right tire sensor id|2024-;2025-;2020-
DAC7|C7|22012F|4|1|1|1|0|0|0|noyes|Rear left tire pressure invalid?|2024-;2025-;2020-
DAC7|C7|22012F|5|1|1|1|0|0|0|noyes|Rear right tire pressure invalid?|2024-;2025-;2020-
DAC7|C7|22012F|6|1|1|1|0|0|0|noyes|Front right tire pressure invalid?|2024-;2025-;2020-
#MAZDA
7E1||221E1C|0|16|9|80|32|0|0|F|trans temp|*
7E0||220415|0|16|1|1|0|1|0|kPa|Engine oil pressure|*
7E0||221310|0|16|1|100|-40|0|0|C|Engine oil temp|*
7E0||2182|0|16|1|256|-40|0|0|C|trans temp, pan|*
7E0||2182|16|16|1|256|-40|0|0|C|trans temp, torque converter|*
7E0||2211BD|0|16|9|80|32|0|0|F|trans temp v5|*
7E0||2217B3|0|8|42|25|-57|0|0|F|trans temp v1|*
7E0||221E1A|0|16|2|1|0|1|0|kPa|trans pressure, commanded|*
7E0||221E1C|0|16|1|16|0|1|0|C|trans oil temp|*
7E1||2211BD|0|16|9|80|32|0|0|F|trans temp v6|*
7E1||2217B3|0|8|42|25|-57|0|0|F|trans temp v5|*
7E0||221101|4|1|1|1|0|0|0|onoff|In gear switch|*
700||2210A5|0|8|1|1|0|0|0||Misfire count, all|*
700||2210A7|0|8|1|1|0|0|0||Misfire count, cylinder 1|*
700||2210A7|8|8|1|1|0|0|0||Misfire count, cylinder 2|*
700||2210A7|16|8|1|1|0|0|0||Misfire count, cylinder 3|*
700||2210A7|24|8|1|1|0|0|0||Misfire count, cylinder 4|*
7E0||220345|0|32|1|1|0|0|0||Misfire events, latest cycle|*
7E0||220382|0|8|1|64|0|1|0||Misfire acceleration, cylinder 1|*
7E0||220388|0|8|1|64|0|1|0||Misfire acceleration, cylinder 2|*
7E0||22038A|0|8|1|64|0|1|0||Misfire acceleration, cylinder 3|*
7E0||22038B|0|8|1|64|0|1|0||Misfire acceleration, cylinder 4|*
7E0||22038C|0|8|1|64|0|1|0||Misfire acceleration, cylinder 5|*
7E0||220398|0|8|1|64|0|1|0||Misfire acceleration, cylinder 6|*
7E0||22053B|0|8|1|1|0|0|0||Catalyst damaging misfires, cylinder 1|*
7E0||22053B|8|8|1|1|0|0|0||Catalyst damaging misfires, cylinder 2|*
7E0||22053B|16|8|1|1|0|0|0||Catalyst damaging misfires, cylinder 3|*
7E0||22053B|24|8|1|1|0|0|0||Catalyst damaging misfires, cylinder 4|*
7E0||22053B|64|8|1|1|0|0|0||Emission failure misfires, cylinder 1|*
7E0||22053B|72|8|1|1|0|0|0||Emission failure misfires, cylinder 2|*
7E0||22053B|80|8|1|1|0|0|0||Emission failure misfires, cylinder 3|*
7E0||22053B|88|8|1|1|0|0|0||Emission failure misfires, cylinder 4|*
7E0||221746|0|8|100|284|0|0|0|deg|Knock retard|*
700||221074|0|16|10|128|0|0|0|kPa|Engine oil pressure|*
700||221F5C|0|8|1|1|-40|0|0|C|Engine oil temp|*
7E0||2151|72|8|1|1|-40|0|0|C|Engine oil temp|*
7E0||22DA01|6|1|1|1|0|0|0|onoff|Oil pressure solenoid valve, open|*
7E0||22F45C|0|8|1|1|0|0|0||Engine oil pressure|*
7E0||221E16|0|16|1|4096|0|0|0||Axle gear ratio, measured|*
7E0||221E19|0|16|16|65535|0|0|0||Gear ratio, commanded|*
7E0||221E1F|0|8|1|1|0|0|0||Gear, engaged|*
7E1||221E12|0|8|1|1|0|0|0||Gear|*
7E1||221E24|0|8|1|1|0|0|0||Torque converter lock-up|*
7E0||2216F0|0|16|1|1|0|0|0||Tire revolutions per mile|*
7E0||220403|0|16|1|1|0|0|0||Knock sensor, 1|*
#HYUNDAI
7E0||210D|48|16|1|1|0|0|1||Emission-relevant misfires, cylinder #1|*
7E0||210D|64|16|1|1|0|0|1||Emission-relevant misfires, cylinder #2|*
7E0||210D|80|16|1|1|0|0|1||Emission-relevant misfires, cylinder #3|*
7E0||210D|96|16|1|1|0|0|1||Emission-relevant misfires, cylinder #4|*
7E0||210D|176|16|1|1|0|0|1||Misfires total counter, cylinder #1|*
7E0||210D|192|16|1|1|0|0|1||Misfires total counter, cylinder #2|*
7E0||210D|208|16|1|1|0|0|1||Misfires total counter, cylinder #3|*
7E0||210D|224|16|1|1|0|0|1||Misfires total counter, cylinder #4|*
7E0||210D|432|16|1|1|0|0|1||Misfires total counter, all cylinders|*
7E0||211D|32|16|1|1|0|0|1||Misfires, cylinder 1|*
7E0||211D|48|16|1|1|0|0|1||Misfires, cylinder 2|*
7E0||211D|64|16|1|1|0|0|1||Misfires, cylinder 3|*
7E0||211D|80|16|1|1|0|0|1||Misfires, cylinder 4|*
7E0||211D|160|16|1|1|0|0|1||Misfires harmful for catalyst cylinder 1|*
7E0||211D|176|16|1|1|0|0|1||Misfires harmful for catalyst cylinder 2|*
7E0||211D|192|16|1|1|0|0|1||Misfires harmful for catalyst cylinder 3|*
7E0||211D|208|16|1|1|0|0|1||Misfires harmful for catalyst cylinder 4|*
7E0||21A0|264|8|1|1|-40|0|0|C|trans fluid temp|*
7E1||21A0|104|8|1|1|-40|0|0|C|Automatic trans fluid temp|*
7E1||2201A0|104|8|1|1|-40|0|0|C|Automatic trans fluid temp|*
7E1||2201A5|32|8|1|1|0|0|0||Dual-clutch trans odd shaft, gear engaged|*
7E1||2201A5|40|8|1|1|0|0|0||Dual-clutch trans even shaft, gear engaged|*
7E1||2201A5|48|8|1|1|-40|0|0|C|Dual-clutch trans fluid temp 1|*
7E1||2201A5|56|8|1|1|-40|0|0|C|Dual-clutch trans fluid temp 2|*
7E1||2201A5|192|16|19.53|10000|0|0|0|bar|Dual-clutch trans clutch 1, pressure sensor A|*
7E1||2201A5|208|16|19.53|10000|0|0|0|bar|Dual-clutch trans clutch 2, pressure sensor B|*
7E1||2201A5|224|16|19.53|10000|0|0|0|bar|Dual-clutch trans line pressure, sensor C|*
770||22BC04|35|1|1|1|0|0|0|noyes|Reverse gear selected|*
7E0||2108|128|16|1|1|0|0|1||Emission relevant misfires total, cylinder 1|*
7E0||2108|144|16|1|1|0|0|1||Emission relevant misfires total, cylinder 2|*
7E0||2108|160|16|1|1|0|0|1||Emission relevant misfires total, cylinder 3|*
7E0||2108|176|16|1|1|0|0|1||Emission relevant misfires total, cylinder 4|*
7E0||2108|192|16|1|1|0|0|1||Emission relevant misfires total, cylinder 5|*
7E0||2108|208|16|1|1|0|0|1||Emission relevant misfires total, cylinder 6|*
7E0||2108|256|16|1|1|0|0|1||Catalyst damaging misfires total, cylinder 1|*
7E0||2108|272|16|1|1|0|0|1||Catalyst damaging misfires total, cylinder 2|*
7E0||2108|288|16|1|1|0|0|1||Catalyst damaging misfires total, cylinder 3|*
7E0||2108|304|16|1|1|0|0|1||Catalyst damaging misfires total, cylinder 4|*
7E0||2108|320|16|1|1|0|0|1||Catalyst damaging misfires total, cylinder 5|*
7E0||2108|336|16|1|1|0|0|1||Catalyst damaging misfires total, cylinder 6|*
7E0||2108|384|16|1|1|0|0|1||Emission relevant misfires total all cylinders|*
7E0||2108|400|16|1|1|0|0|1||Catalyst damaging misfires total all cylinders|*
7E0||2108|536|8|1|1|0|0|0||Misfires current, cylinder 1|*
7E0||2108|544|8|1|1|0|0|0||Misfires current, cylinder 2|*
7E0||2108|552|8|1|1|0|0|0||Misfires current, cylinder 3|*
#TOYOTA
7E0||2137|32|16|2048|65535|-1024|0|0|deg|Knock adjust|*
7E0||2137|48|16|2048|65535|-1024|0|0|deg|Knock feedback|*
7E0||21B2|0|16|2048|65535|-64|0|0|deg|Knock adjust|*
7E0||21B2|16|16|2048|65535|-64|0|0|deg|Knock feedback|*
700||22106F|0|16|639.9|65535|0|0|0|deg|Intake vvt target angle b1|*
700||221071|0|16|639.9|65535|0|0|0|deg|Exhaust vvt target angle b1|*
700||221087|0|16|639.9|65535|0|0|0|deg|Intake vvt change angle bank 1|*
700||221088|0|16|639.9|65535|0|0|0|deg|Exhaust VVT change angle, bank 1|*
700||2210CD|0|16|1|10|-3276.8|0|0|kPa|Low fuel pressure|*
700||22113C|0|16|10|1|0|0|0|kPa|Fuel pressure 1|*
700||22113C|16|16|10|1|0|0|0|kPa|Fuel pressure 2|*
700||22113C|32|16|10|1|0|0|0|kPa|Fuel pressure 3|*
700||22113C|48|16|10|1|0|0|0|kPa|Fuel pressure 4|*
700||2211C4|0|16|10|1|0|0|0|kPa|Fuel pressure 1|*
700||2211C4|16|16|10|1|0|0|0|kPa|Fuel pressure 2|*
700||2211C4|32|16|10|1|0|0|0|kPa|Fuel pressure 3|*
700||2211C4|48|16|10|1|0|0|0|kPa|Fuel pressure 4|*
700||2211C4|64|16|10|1|0|0|0|kPa|Fuel pressure 5|*
700||2211C4|80|16|10|1|0|0|0|kPa|Fuel pressure 6|*
700||221F3C|0|16|1|10|-40|0|0|C|Catalyst temp, bank 1 sensor 1|*
700||221F3E|0|16|1|10|-40|0|0|C|Catalyst temp, bank 1 sensor 2|*
7E0||2105|16|16|1|10|-40|0|0|C|Catalyst temp B1S1|*
#HONDA
DA10|10|222662|80|8|2|255|0|0|0||Knock control|*
DA0E|0E|222666|88|8|1|1|-40|0|0|C|Engine oil temp v3|*
DA0E|0E|222666|112|8|1|1|-40|0|0|C|Engine oil temp v4|*
DA11|11|222662|96|16|1|10|-40|0|0|C|Catalyst temp|*
DA26|26|226001|64|16|1|1|0|0|0|kPa|Front right tire pressure|*
DA26|26|226001|80|16|1|1|0|0|0|kPa|Front left tire pressure|*
DA26|26|226001|96|16|1|1|0|0|0|kPa|Rear right tire pressure|*
DA26|26|226001|112|16|1|1|0|0|0|kPa|Rear left tire pressure|*
DA01|01|22202C|1608|16|1|10|0|1|0|C|Engine coolant temp sensor 1|2023-
DA01|01|22202C|1624|16|1|10|0|1|0|C|Engine coolant temp sensor 2|2023-
DA01|01|22202C|1640|16|1|10|0|1|0|C|Engine coolant temp sensor 3|2023-
DA01|01|22202C|1656|16|1|10|0|1|0|C|Engine coolant temp sensor 4|2023-
#GM
7E2||221141|0|8|1|10|0|0|0|V|Ignition voltage|*
7E0||221C43|0|8|1|1|-40|0|0|C|Power electronics coolant temp|*
#FORD
7E0||22033C|0|16|5|1024|0|0|0|V|Throttle inlet pressure sensor voltage|*
7E0||22035A|0|16|5|1023|0|0|0|V|Barometric pressure sensor voltage|*
7E0||22035F|0|16|1|1024|0|0|0|V|O2 sensor voltage, rear|*
7E0||22038E|0|16|1|1000|0|0|0|V|Evaporative pressure sensor voltage|*
7E0||220460|0|16|1|1024|0|1|0|V|Charge air temp sensor voltage|*
7E0||221279|0|16|5|1023|0|0|0|V|Intake temp sensor voltage|*
7E0||22038F|0|16|1|64|0|1|0|C|Coolant temp|*
#CHRYSLER
7E0||22B028|0|16|9|640|0|1|0|rpm|Torque converter slip v1|-2024
DA10|10|22192D|0|8|1|1|0|0|0||Gear engaged|2025-
DA18||221D12|0|8|1|1|0|0|0||Gear|*
DAC7|C7|22013C|0|16|1|1000|0|0|0|bar|Front left tire pressure|2025-;2020-
DAC7|C7|22013D|0|16|1|1000|0|0|0|bar|Front right tire pressure|2025-;2020-
DAC7|C7|22013E|0|16|1|1000|0|0|0|bar|Rear left tire pressure|2025-;2020-
DAC7|C7|22013F|0|16|1|1000|0|0|0|bar|Rear right tire pressure|2025-;2020-
7E0||221F59|0|16|61|12500|0|0|0|V|Wastegate position sensor|*
DA10|10|221946|0|16|1|20|0|0|0|bar|Fuel rail pressure commanded|2025-
DA10|10|221947|0|16|1|20|0|0|0|bar|Fuel rail pressure measured|2025-
7E0||2202A1|24|8|29|200|0|0|0|psi|Fuel rail pressure|*
7E0||221D89|0|16|1|1000|0|0|0||Fuel rail pressure, target|*
7E0||22A067|8|16|2|1|0|0|0|bar|Fuel rail pressure|*
7DA||22A020|0|8|1541|4250|0|0|0|psi|Front left tire pressure|-2016
7DA||22A021|0|8|1541|4250|0|0|0|psi|Front right tire pressure|-2016
7DA||22A022|0|8|1541|4250|0|0|0|psi|Rear left tire pressure|-2016
7DA||22A023|0|8|1541|4250|0|0|0|psi|Rear right tire pressure|-2016
DA40|40|221004|0|8|1|10|0|0|0|V|Battery voltage, BCM|*
7E0||22059E|0|16|1|10|0|1|0|deg|Cam crank difference|-2024
DA10|10|22195A|0|16|1|10|-3276.8|0|0|kPa|Turbo boost pressure|2025-
7E0||21B2|32|16|1|441|0|0|0|psi|Boost pressure estimate|*
7E0||21DA|112|16|9|20|32|0|0|F|Variable geometry turbo compressor outlet air temp|*
#MAZDA
7E0||2205AD|0|8|1|1|0|0|0||Knock counter, cylinder 2|*
7E0||2205AE|0|8|1|1|0|0|0||Knock counter, cylinder 3|*
7E0||2205AF|0|8|1|1|0|0|0||Knock counter, cylinder 4|*
7E0||2205B0|0|8|1|1|0|0|0||Knock counter, cylinder 5|*
7E0||2205B1|0|8|1|1|0|0|0||Knock counter, cylinder 6|*
700||2210CD|0|16|1|10|-3276.75|0|0|kPa|Low fuel pressure sensor|*
7E0||22041F|0|8|435|1000|0|0|0|psi|Fuel pressure, low desired|*
7E0||220548|0|16|10000|137892|0|1|0|psi|Fuel pressure, low actual|*
7E0||22054D|0|16|1|1024|0|1|0|V|Fuel pressure sensor voltage, low|*
7E0||221410|0|16|1|125|0|0|0||Injector fuel pulse width|*
7E0||2203DF|0|16|100|65535|0|0|0|%|Variable geometry turbocharger open|*
7E0||220462|0|16|100|32768|0|0|0|%|Wastegate duty cycle|*
7E0||221305|0|16|1|6400|0|0|0|bar|Boost, desired|*
7E0||2216E1|0|8|25|64|0|0|0|%|Wastegate duty cycle|*
7E0||221723|0|8|5|8|-39.4|0|0|C|Boosted air temp|*
7E0||22F43C|0|16|1|10|-40|0|0|C|Catalyst temp|*
7E0||220301|0|16|1|1024|0|0|0|V|Map voltage|*
7E0||220914|0|16|1|1000|0|0|0|V|APP sensor 1 voltage|*
7E0||220915|0|16|1|1000|0|0|0|V|APP sensor 2 voltage|*
7E0||220917|0|16|1|1000|0|0|0|V|Throttle position 1 voltage|*
7E0||220918|0|16|1|1000|0|0|0|V|Throttle position 2 voltage|*
7E0||22097C|0|16|1|2048|0|0|0|V|Generator voltage desired|*
#HYUNDAI
7E0||2100|200|8|1|1|0|0|0||Knock detected|*
7E0||22E00A|96|8|1|5|0|1|0|deg|Knock retard, cylinder 1|*
7E0||22E00A|104|8|1|5|0|1|0|deg|Knock retard, cylinder 2|*
7E0||22E00A|112|8|1|5|0|1|0|deg|Knock retard, cylinder 3|*
7E0||22E00A|120|8|1|5|0|1|0|deg|Knock retard, cylinder 4|*
7E0||2101|272|8|0.75|1|-48|0|0|C|Engine oil temp|*
7E0||22E001|272|8|3|4|-48|0|0|C|Engine oil temp|*
7E0||22E011|304|8|1|1|-40|0|0|C|Calculated oil temp|*
7E0||2221A0|16|8|9|5|-40|0|0|F|trans fluid temp|*
7E0||21A0|104|16|1|4|-512|0|0|rpm|Torque converter slip|*
7E0||22ED05|176|8|1|1|0|0|0||Gear|*
7E1||21A1|32|8|1|1|0|0|0||Current gear|*
7E1||2201A0|128|16|1|4|-512|0|0|rpm|Torque converter slip|*
7E1||2201A0|160|8|1|1|0|0|0||Gear selector|*
7E1||2201A0|168|8|1|1|0|0|0||Current gear|*
7E1||2201A0|176|8|1|1|0|0|0||Commanded gear|*
7E1||2201A4|188|4|1|1|0|0|0||Current gear|*
7E1||2201A4|196|4|1|1|0|0|0||Next gear|*
7E0||2119|104|8|0.75|1|-191.25|0|0|deg|Ignition retard due to knock control 1|*
7E0||2119|112|8|0.75|1|-191.25|0|0|deg|Ignition retard due to knock control 2|*
7E0||2119|120|8|0.75|1|-191.25|0|0|deg|Ignition retard due to knock control 3|*
7E0||2119|128|8|0.75|1|-191.25|0|0|deg|Ignition retard due to knock control 4|*`;
const OEM_DB = {};
(function parseOem() {
  let prof = null;
  for (const line of OEM_RAW.split("\n")) {
    if (!line) continue;
    if (line[0] === "#") { prof = line.slice(1); OEM_DB[prof] = OEM_DB[prof] || []; continue; }
    const f = line.split("|");
    OEM_DB[prof].push({ hdr: f[0], rax: f[1], req: f[2], bix: +f[3], len: +f[4], mul: +f[5], div: +f[6], add: +f[7],
      sign: f[8] === "1", lsb: f[9] === "1", unit: f[10], name: f[11], yrs: f[12] });
  }
})();
function yearOk(yrs, year) {
  if (!yrs || yrs === "*" || !year) return true;
  return yrs.split(";").some((r) => {
    if (r.includes("/")) return r.split("/").map(Number).includes(year);
    const [a, b] = r.split("-");
    return (!a || year >= +a) && (!b || year <= +b);
  });
}
function extractBits(bytes, bix, len, lsb, sign) {
  if (bix + len > bytes.length * 8) return null;
  let v = 0;
  if (lsb && len % 8 === 0 && bix % 8 === 0) {
    for (let i = len / 8 - 1; i >= 0; i--) v = v * 256 + bytes[bix / 8 + i];
  } else {
    for (let i = 0; i < len; i++) { const bit = bix + i; v = v * 2 + ((bytes[bit >> 3] >> (7 - (bit & 7))) & 1); }
  }
  if (sign && v >= 2 ** (len - 1)) v -= 2 ** len;
  return v;
}
function fmtOem(sig, v) {
  const x = v * sig.mul / sig.div + sig.add;
  const r1 = (n) => (Math.abs(n) >= 100 ? Math.round(n) : Math.round(n * 10) / 10);
  switch (sig.unit) {
    case "C": return x <= -39.5 || x > 300 ? null : degF(x) + " °F";
    case "F": return x <= -39.5 || x > 570 ? null : Math.round(x) + " °F";
    case "kPa": return r1(x * 0.145038) + " psi";
    case "bar": return r1(x * 14.5038) + " psi";
    case "psi": return r1(x) + " psi";
    case "kph": return Math.round(x * 0.621371) + " mph";
    case "Nm": return Math.round(x * 0.737562) + " lb-ft";
    case "onoff": case "onoff2": return x ? "ON" : "OFF";
    case "yesno": case "noyes": return x ? "YES" : "NO";
    case "hex": return v.toString(16).toUpperCase();
    case "V": return x.toFixed(2) + " V";
    case "%": return r1(x) + "%";
    case "deg": return r1(x) + "°";
    case "": return String(r1(x));
    default: return r1(x) + " " + sig.unit;
  }
}
function cleanName(n) {
  n = n.replace(/,?\s*(v\.?\s?\d+|var\.?\s?\d+|variation \d+)\s*$/i, "").replace(/,\s*$/, "").trim();
  return n.charAt(0).toUpperCase() + n.slice(1);
}
function oemGroup(name) {
  if (/misfire/i.test(name)) return "Misfire counters";
  if (/tire/i.test(name)) return "Tire pressure (TPMS)";
  if (/trans|gear|cvt|torque converter|lock.?up|clutch|shaft|gearbox|transaxle|pulley|awd/i.test(name)) return "Transmission";
  if (/fuel|inject|rail|boost|turbo|wastegate|throttle|air|lambda|map |egr|purge|evap/i.test(name)) return "Fuel, air & boost";
  if (/volt|battery|generator/i.test(name)) return "Electrical";
  return "Engine, oil & knock";
}
const GROUP_ORDER = ["Transmission", "Engine, oil & knock", "Misfire counters", "Fuel, air & boost", "Tire pressure (TPMS)", "Electrical"];

let oemCmds = [], oemRR = 0, oemFound = 0;
function profile() { const s = $("oemSel").value; return s === "AUTO" ? (ARGS.make || "GENERIC") : s; }
function buildEnhanced() {
  const year = parseInt(ARGS.year, 10) || 0;
  const sigs = isCan ? (OEM_DB[profile()] || []).filter((g) => yearOk(g.yrs, year)) : [];
  const byCmd = new Map();
  sigs.forEach((g) => {
    const k = g.hdr + "|" + g.rax + "|" + g.req;
    if (!byCmd.has(k)) byCmd.set(k, { hdr: g.hdr, rax: g.rax, req: g.req, sigs: [], state: "new" });
    byCmd.get(k).sigs.push(g);
  });
  oemCmds = [...byCmd.values()];
  // Same request, same quantity at different byte offsets = layouts for different models.
  // Keep only the most widely used layout so we never show two conflicting values.
  oemCmds.forEach((c) => {
    const seen = new Set();
    c.sigs = c.sigs.filter((g) => { g.label = cleanName(g.name); if (seen.has(g.label)) return false; seen.add(g.label); return true; });
  });
  oemRR = 0; oemFound = 0;
  $("enhBox").innerHTML = '<div class="box">' + (oemCmds.length
    ? `Checking ${oemCmds.length} factory data requests for ${esc(profile())}…`
    : (isCan ? "No OEM definitions for this make yet — pick a profile above if Auto-Detect is wrong." : "OEM data needs a CAN vehicle (most 2008+).")) + "</div>";
  updateEnhNote();
}
function updateEnhNote() {
  const checked = oemCmds.filter((c) => c.state !== "new").length;
  $("enhNote").textContent = oemCmds.length
    ? `${profile()} · checked ${checked}/${oemCmds.length} requests · ${oemFound} readings found`
    : "";
}
function oemTile(sig) {
  if (sig.tile) return sig.tile;
  const box = $("enhBox");
  if (box.firstElementChild && box.firstElementChild.classList.contains("box")) box.innerHTML = "";
  const grp = oemGroup(sig.name);
  let sec = document.querySelector(`[data-grp="${grp}"]`);
  if (!sec) {
    sec = document.createElement("div");
    sec.dataset.grp = grp;
    sec.innerHTML = `<div class="grp">${esc(grp)}</div><div class="grid" style="margin-bottom:10px"></div>`;
    const after = [...box.children].find((c) => GROUP_ORDER.indexOf(c.dataset.grp) > GROUP_ORDER.indexOf(grp));
    box.insertBefore(sec, after || null);
  }
  const id = "oem" + (oemTile.n = (oemTile.n || 0) + 1);
  const label = sig.label || cleanName(sig.name);
  LABEL[id] = `${label} [OEM ${sig.hdr} ${sig.req}]`;
  sec.lastElementChild.insertAdjacentHTML("beforeend",
    `<div class="tile" id="t_${id}" title="${esc(sig.hdr + " " + sig.req)}"><div class="l">${esc(label)}</div><div class="v" id="v_${id}" style="color:var(--p)">--</div></div>`);
  sig.tile = id; oemFound++;
  return id;
}
async function readOem(cmd) {
  await setAddr(cmd.hdr, cmd.rax);
  const raw = await sendCmd(cmd.req, 500);
  if (isErr(raw)) return null;
  const pre = respCode(cmd.req.slice(0, 2)) + cmd.req.slice(2);
  for (const m of messages(raw)) if (m.startsWith(pre)) return bytesOf(m.slice(pre.length));
  return null;
}
async function pollEnhanced() {
  const fresh = oemCmds.filter((c) => c.state === "new").slice(0, 6);      // discovery: probe a few new requests
  const live = oemCmds.filter((c) => c.state === "live");
  const due = [];
  for (let i = 0; i < Math.min(4, live.length); i++) due.push(live[(oemRR + i) % live.length]);
  oemRR += 4;
  const jobs = [...fresh, ...due].sort((a, b) => (a.hdr + a.rax).localeCompare(b.hdr + b.rax));   // fewer module switches
  for (const c of jobs) {
    const bytes = await readOem(c);
    let any = false;
    if (bytes) for (const g of c.sigs) {
      const v = extractBits(bytes, g.bix, g.len, g.lsb, g.sign);
      const text = v == null ? null : fmtOem(g, v);
      if (text == null) continue;
      any = true;
      setTile(oemTile(g), text);
    }
    if (c.state === "new") { c.state = any ? "live" : "dead"; c.miss = 0; }
    else if (any) c.miss = 0;
    else if (++c.miss >= 3) c.state = "dead";
  }
  await setAddr(baseHeader, "");
  updateEnhNote();
  if (oemCmds.length && !oemFound && oemCmds.every((c) => c.state !== "new"))
    $("enhBox").innerHTML = '<div class="box">This vehicle did not answer any of the stored factory requests for this make.</div>';
}

// ===================== DTCs, VIN, Readiness, Mode $06 =====================
let dtcs = { stored: [], pending: [], permanent: [] }, vinRead = "";
function decodeDtc(h) {
  const b1 = parseInt(h.slice(0, 2), 16);
  return ("PCBU"[b1 >> 6] + ((b1 >> 4) & 3) + (b1 & 0xF).toString(16) + h.slice(2, 4)).toUpperCase();
}
function parseDtcs(raw, svc) {
  const pre = respCode(svc), out = new Set();
  for (const m of messages(raw)) {
    if (!m.startsWith(pre)) continue;
    let body = m.slice(2), n = 99;
    if (isCan) { n = parseInt(body.slice(0, 2), 16) || 0; body = body.slice(2); }   // CAN: first byte = number of codes
    for (let k = 0, i = 0; k < n && i + 4 <= body.length; k++, i += 4) {
      const h = body.substr(i, 4);
      if (h !== "0000") out.add(decodeDtc(h));
    }
  }
  return [...out];
}
async function readDtcs() {
  await setHeader("7DF");   // functional: every emissions module answers
  for (const [svc, key] of [["03", "stored"], ["07", "pending"], ["0A", "permanent"]]) {
    if (svc === "0A" && !isCan) { dtcs[key] = []; continue; }
    dtcs[key] = parseDtcs(await sendCmd(svc, 3000), svc);
  }
  await setHeader(baseHeader);
  renderDtcs();
}
function renderDtcs() {
  const row = (label, list, c) => `<div style="margin-bottom:6px"><span style="color:var(--muted)">${label}:</span> ` +
    (list.length ? `<span class="chips">${list.map((d) => `<span class="chip" style="color:var(--${c});border-color:var(--${c})">${d}</span>`).join("")}</span>` : `<span style="color:var(--g)">none</span>`) + "</div>";
  $("dtcBox").innerHTML = row("Stored (03)", dtcs.stored, "r") + row("Pending (07)", dtcs.pending, "o") + (isCan ? row("Permanent (0A)", dtcs.permanent, "v") : "");
}
async function readVin() {
  const raw = await sendCmd("0902", 3000);
  let hex = "";
  for (const m of messages(raw)) if (m.startsWith("4902")) hex += m.slice(6);
  const ascii = bytesOf(hex).map((c) => String.fromCharCode(c)).join("").toUpperCase();
  const m = ascii.match(/[A-HJ-NPR-Z0-9]{17}/);
  vinRead = m ? m[0] : "";
}

let readinessSummary = "";
async function loadReadiness() {
  const raw = await sendCmd("0101", 1500);
  const m = messages(raw).find((x) => x.startsWith("4101") && x.length >= 12);
  if (!m) { $("readyBox").innerHTML = `<span style="color:var(--r)">Could not read monitors (${esc(raw.trim() || "no reply")})</span>`; return; }
  const [A, B, C, D] = bytesOf(m.slice(4, 12));
  const diesel = (B & 0x08) !== 0;
  const mons = [["Misfire", B, 0, B, 4], ["Fuel System", B, 1, B, 5], ["Comprehensive", B, 2, B, 6]];
  const names = diesel
    ? ["NMHC Catalyst", "NOx / SCR", null, "Boost Pressure", null, "Exhaust Gas Sensor", "PM Filter", "EGR / VVT"]
    : ["Catalyst", "Heated Catalyst", "EVAP", "Secondary Air", "A/C Refrigerant", "O2 Sensor", "O2 Heater", "EGR / VVT"];
  names.forEach((n, bit) => { if (n) mons.push([n, C, bit, D, bit]); });
  const mil = (A & 0x80) !== 0, count = A & 0x7F;
  let html = `<div style="margin-bottom:8px;font-weight:700;color:${mil ? "var(--r)" : "var(--g)"}">MIL ${mil ? "ON" : "OFF"} · ${count} emissions code(s)${diesel ? " · Diesel" : ""}</div>`;
  html += `<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(130px,1fr));margin:0">`;
  readinessSummary = `MIL ${mil ? "ON" : "OFF"}, ${count} codes. `;
  for (const [n, sb, sbit, rb, rbit] of mons) {
    if (!((sb >> sbit) & 1)) continue;   // only show monitors this vehicle supports
    const ready = !((rb >> rbit) & 1);
    const c = ready ? "g" : "r", t = ready ? "COMPLETE" : "NOT READY";
    readinessSummary += `${n}: ${t}; `;
    html += `<div class="mon" style="border-color:var(--${c})"><div class="l">${n}</div><div class="v" style="color:var(--${c})">${t}</div></div>`;
  }
  $("readyBox").innerHTML = html + "</div>";
}

// SAE J1979 Mode $06 monitor IDs
const MID_NAMES = {
  "01": "O2 Sensor B1S1", "02": "O2 Sensor B1S2", "03": "O2 Sensor B1S3", "05": "O2 Sensor B2S1", "06": "O2 Sensor B2S2", "07": "O2 Sensor B2S3",
  "21": "Catalyst B1", "22": "Catalyst B2", "31": "EGR B1", "32": "EGR B2", "35": "VVT B1", "36": "VVT B2",
  "39": "EVAP Cap-Off / 0.150\"", "3A": "EVAP 0.090\"", "3B": "EVAP 0.040\"", "3C": "EVAP 0.020\"", "3D": "Purge Flow",
  "41": "O2 Heater B1S1", "42": "O2 Heater B1S2", "45": "O2 Heater B2S1", "46": "O2 Heater B2S2",
  "61": "Heated Cat B1", "62": "Heated Cat B2", "71": "Secondary Air 1", "81": "Fuel System B1", "82": "Fuel System B2",
  "A1": "Misfire (All Cyl)",
};
for (let c = 1; c <= 12; c++) MID_NAMES[(0xA1 + c).toString(16).toUpperCase()] = `Cylinder ${c} Misfire`;
const DEFAULT_MIDS = ["01", "02", "05", "06", "21", "22", "31", "35", "36", "39", "3A", "3B", "3C", "3D", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9"];
const s16 = (v) => (v & 0x8000 ? v - 0x10000 : v);
function parse06(raw, mid) {
  const recs = [];
  for (const m of messages(raw)) {
    if (!m.startsWith("46")) continue;
    const body = m.slice(2);
    for (let i = 0; i + 18 <= body.length; i += 18) {
      if (body.substr(i, 2) !== mid) break;
      const b = bytesOf(body.substr(i + 2, 16));   // TID, UASID, value(2), min(2), max(2)
      const sg = b[1] >= 0x80;
      let v = u16(b, 2), mn = u16(b, 4), mx = u16(b, 6);
      if (sg) { v = s16(v); mn = s16(mn); mx = s16(mx); }
      recs.push({ tid: b[0], v, mn, mx, pass: v >= mn && v <= mx });
    }
  }
  return recs;
}
let mode6Summary = "";
async function loadMode6() {
  const box = $("m6Box");
  if (!isCan) { box.textContent = "Mode $06 decoding needs a CAN vehicle (most 2008+)."; mode6Summary = "Not available (non-CAN)"; return; }
  box.innerHTML = `<span style="color:var(--o)">Reading supported monitors…</span>`;
  const sup = await supported("06", ["00", "20", "40", "60", "80", "A0"]);
  const mids = sup ? [...sup].filter((m) => MID_NAMES[m]) : DEFAULT_MIDS;
  let html = "", lines = [];
  for (const mid of mids) {
    const recs = parse06(await sendCmd("06" + mid, 1000), mid);
    if (!recs.length) continue;
    const name = MID_NAMES[mid];
    let text, color;
    if (mid >= "A1" && mid <= "AD") {
      const cur = recs.find((r) => r.tid === 0x0C), avg = recs.find((r) => r.tid === 0x0B);
      const c = cur ? cur.v : 0, a = avg ? avg.v : 0;
      color = c || a ? "r" : "g";
      text = `Now ${c} · Avg ${a}`;
      lines.push(`${name}: current-cycle ${c}, 10-cycle avg ${a}`);
    } else {
      const fails = recs.filter((r) => !r.pass).length;
      color = fails ? "r" : "g";
      text = fails ? `FAIL ${fails}/${recs.length}` : `PASS (${recs.length})`;
      lines.push(`${name}: ` + recs.map((r) => `TID $${r.tid.toString(16).toUpperCase().padStart(2, "0")} val ${r.v} [${r.mn}..${r.mx}] ${r.pass ? "PASS" : "FAIL"}`).join("; "));
    }
    html += `<div class="mon" style="border-color:var(--${color})"><div class="l">${name}</div><div class="v" style="color:var(--${color})">${text}</div></div>`;
    box.innerHTML = `<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(140px,1fr));margin:0">${html}</div>`;
  }
  mode6Summary = lines.join("\n") || "No Mode $06 results returned";
  if (!html) box.textContent = "ECM returned no Mode $06 results.";
}

// ===================== Live loop =====================
let loopToken = 0, streaming = false, driveOn = false, wakeLock = null, lastSpeak = 0, lastDriveAi = 0;
async function liveLoop(token) {
  let cycle = 0, t0 = performance.now(), cmds = 0;
  while (token === loopToken) {
    cycle++;
    const due = active.filter((p) => cycle === 1 || cycle % TIER_EVERY[PIDS[p].tier] === 0);
    await txn(() => pollPids(due));
    cmds += batchOK ? Math.ceil(due.length / 6) : due.length;
    if (token !== loopToken) break;
    if (cycle % 6 === 0) {
      const r = await txn(() => sendCmd("ATRV", 600));
      const m = (r || "").match(/(\d+\.\d+)/);
      if (m) setTile("volt", parseFloat(m[1]).toFixed(1) + " V", parseFloat(m[1]));
    }
    const discovering = oemCmds.some((c) => c.state === "new");
    if (oemCmds.length && cycle % (discovering ? 2 : 5) === 0) await txn(pollEnhanced);
    if (cycle % 10 === 0) {
      const secs = (performance.now() - t0) / 1000;
      $("rate").textContent = `· ${(cycle / secs).toFixed(1)} refresh/s${batchOK ? " · multi-PID" : ""}`;
    }
    driveChecks();
  }
}
function startStream() { streaming = true; loopToken++; liveLoop(loopToken); $("pauseBtn").textContent = "⏸️ Pause"; log("Streaming live data…"); }
function stopStream() { streaming = false; loopToken++; $("pauseBtn").textContent = "▶️ Resume"; }

function speak(text) {
  const now = Date.now(); if (now - lastSpeak < 18000) return; lastSpeak = now;
  if ("speechSynthesis" in window) { speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(text); u.rate = 1.05; speechSynthesis.speak(u); }
}
function driveChecks() {
  if (!driveOn) return;
  const t1 = (num.stft1 ?? 0) + (num.ltft1 ?? 0);
  const hasB2 = num.stft2 !== undefined;
  const t2 = (num.stft2 ?? 0) + (num.ltft2 ?? 0);
  if (t1 > 16) speak(`Bank 1 total fuel trim plus ${Math.round(t1)} percent. Lean.`);
  else if (t1 < -16) speak(`Bank 1 total fuel trim minus ${Math.abs(Math.round(t1))} percent. Rich.`);
  else if (hasB2 && t2 > 16) speak(`Bank 2 total fuel trim plus ${Math.round(t2)} percent. Lean.`);
  else if (hasB2 && t2 < -16) speak(`Bank 2 total fuel trim minus ${Math.abs(Math.round(t2))} percent. Rich.`);
  else if ((num.ect ?? 0) >= 225) speak(`High coolant temperature, ${num.ect} degrees.`);
  else if ((num.rpm ?? 0) > 500 && num.volt && num.volt < 13.0) speak(`Low charging voltage, ${num.volt.toFixed(1)} volts.`);
  if (Date.now() - lastDriveAi > 60000) { lastDriveAi = Date.now(); requestAi("drive"); }
}
async function wake(on) {
  try {
    if (on && "wakeLock" in navigator) wakeLock = await navigator.wakeLock.request("screen");
    else if (!on && wakeLock) { await wakeLock.release(); wakeLock = null; }
  } catch (_) {}
}
document.addEventListener("visibilitychange", () => { if (driveOn && document.visibilityState === "visible") wake(true); });

// ===================== AI (runs server-side in Python, key never reaches the browser) =====================
let aiPendingId = null;
function snapshot() {
  const s = {};
  for (const [id, t] of Object.entries(shown)) if (t && t !== "--" && t !== "N/A") s[LABEL[id] || id] = t;
  return s;
}
function requestAi(mode) {
  if (aiPendingId) return;
  aiPendingId = "ai-" + Date.now();
  if (mode === "full") $("aiBox").innerHTML = `<span style="color:var(--o)">🤖 Analyzing live data, codes, monitors and Mode $06…</span>`;
  sendValue({ type: "ai", id: aiPendingId, mode, at: new Date().toLocaleTimeString(), pids: snapshot(), dtcs, readiness: readinessSummary, mode6: mode6Summary });
  const id = aiPendingId;
  setTimeout(() => { if (aiPendingId === id) { aiPendingId = null; if (mode === "full") $("aiBox").textContent = "AI request timed out. Try again."; } }, 90000);
}
function showAi(text, label) {
  let h = esc(text || "")
    .replace(/^#{1,4}\s*(.+)$\n?/gm, "<h4>$1</h4>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/^\s*[-*]\s+/gm, "• ")
    .replace(/\n/g, "<br>");
  $("aiBox").innerHTML = (label ? `<div style="color:var(--g);font-size:.8rem;margin-bottom:4px">${esc(label)}</div>` : "") + h;
}

// ===================== Connect / setup =====================
const BTN_IDS = ["pauseBtn", "driveBtn", "readBtn", "clearBtn", "aiBtn", "syncBtn"];
const enableBtns = (on) => BTN_IDS.forEach((id) => { $(id).disabled = !on; });

function onDisconnect() {
  connected = false; stopStream(); enableBtns(false);
  if (driveOn) { driveOn = false; $("driveBanner").style.display = "none"; wake(false); }
  $("bleBtn").textContent = "🔄 Reconnect"; $("bleBtn").disabled = false;
  log("Adapter disconnected. Tap Reconnect.");
}

async function connectGatt() {
  const server = await device.gatt.connect();
  let svc;
  try { svc = await server.getPrimaryService(NORDIC[0]); rxChar = await svc.getCharacteristic(NORDIC[1]); txChar = await svc.getCharacteristic(NORDIC[2]); }
  catch (_) { svc = await server.getPrimaryService(FFF0[0]); rxChar = await svc.getCharacteristic(FFF0[1]); txChar = await svc.getCharacteristic(FFF0[2]); }
  await txChar.startNotifications();
  txChar.removeEventListener("characteristicvaluechanged", onData);
  txChar.addEventListener("characteristicvaluechanged", onData);
}

async function initVehicle() {
  isCan = false; curCra = "";
  log("Resetting adapter…");
  await sendCmd("ATZ", 2000);
  for (const c of ["ATE0", "ATL0", "ATS0", "ATH0", "ATAT1"]) await sendCmd(c, 500);
  curHeader = "7DF";

  log("Trying CAN (ATSP6)…");
  await sendCmd("ATSP6", 500);
  let r = await sendCmd("0100", 3000);
  if (!messages(r).some((m) => m.startsWith("4100"))) {
    log("Searching other protocols (ATSP0)…");
    await sendCmd("ATSP0", 500);
    r = await sendCmd("0100", 9000);
  }
  if (!messages(r).some((m) => m.startsWith("4100"))) return false;

  const dpn = (await sendCmd("ATDPN", 500)).replace(/[\s>]/g, "").toUpperCase();
  isCan = /^A?[6-9]$/.test(dpn);
  baseProto = curProto = dpn.slice(-1); curCra = "";
  batchOK = false; fastOK = true; baseHeader = "7DF";

  if (isCan) {   // talk to the engine computer directly: no duplicate replies from other modules, faster
    await setHeader("7E0");
    if (messages(await sendCmd("0100", 1500)).some((m) => m.startsWith("4100"))) baseHeader = "7E0";
    else await setHeader("7DF");
  }

  log("Reading supported PIDs…");
  const sup = await supported("01", ["00", "20", "40", "60", "80", "A0"]);
  choosePids(sup);

  if (isCan && active.length >= 2) {   // can this ECU answer several PIDs in one request?
    const test = active.slice(0, 3);
    batchOK = Object.keys(parse01(await sendCmd("01" + test.join(""), 1500), test)).length === test.length;
  }
  buildEnhanced();
  return true;
}

$("bleBtn").addEventListener("click", async () => {
  try {
    if (!navigator.bluetooth) { alert("Web Bluetooth isn't available here. Use Chrome on Android, Windows, macOS or ChromeOS (or Bluefy on iPhone)."); return; }
    if (!device) {
      log("Opening Bluetooth picker…");
      device = await navigator.bluetooth.requestDevice({
        filters: [{ namePrefix: "VEEPEAK" }, { namePrefix: "OBD" }, { namePrefix: "IOS-Vlink" }, { namePrefix: "vLink" }, { namePrefix: "Vgate" }, { namePrefix: "ELM" }],
        optionalServices: [NORDIC[0], FFF0[0]],
      });
      device.addEventListener("gattserverdisconnected", onDisconnect);
    }
    $("bleBtn").disabled = true;
    log("Connecting to " + device.name + "…");
    await connectGatt();
    if (!(await initVehicle())) {
      log("ECM not responding. Turn the key fully ON (or start the engine) and tap Connect again.");
      $("bleBtn").disabled = false; return;
    }
    connected = true; enableBtns(true);
    $("bleBtn").textContent = "✅ Connected";

    log("Reading VIN & codes…");
    await readVin(); await readDtcs();
    log("Reading I/M readiness…"); await loadReadiness();
    log("Reading Mode $06…"); await loadMode6();
    startStream();
    // give live data a few seconds to fill in, then push VIN + codes + snapshot into the app
    setTimeout(() => { if (connected) sendSync(true); }, 4000);   // push VIN + codes into the app automatically (no page reload)
  } catch (err) {
    log("Error: " + err.message);
  } finally {
    $("bleBtn").disabled = connected;
  }
});

function sendSync(auto) {
  sendValue({ type: "sync", id: "sync-" + Date.now(), vin: vinRead, dtcs, auto: !!auto,
    pids: snapshot(), readiness: readinessSummary, mode6: mode6Summary, at: new Date().toLocaleTimeString() });
  log(`Sent to app → VIN ${vinRead || "not reported"} · ${dtcs.stored.length} stored / ${dtcs.pending.length} pending code(s)`);
}

$("pauseBtn").addEventListener("click", () => { streaming ? (stopStream(), log("Paused.")) : startStream(); });
$("driveBtn").addEventListener("click", () => {
  driveOn = !driveOn;
  $("driveBanner").style.display = driveOn ? "block" : "none";
  $("driveBtn").textContent = driveOn ? "⏹️ Stop Test Drive" : "🚗 Test Drive Audio";
  wake(driveOn);
  lastSpeak = 0; speak(driveOn ? "Test drive monitoring on." : "Test drive monitoring off.");
  lastDriveAi = Date.now();
  if (driveOn && !streaming) startStream();
});
$("readBtn").addEventListener("click", async () => {
  log("Re-reading codes, readiness and Mode $06…");
  await txn(async () => { await readDtcs(); await loadReadiness(); });
  await txn(loadMode6);
  log(streaming ? "Streaming live data…" : "Codes refreshed.");
});
$("clearBtn").addEventListener("click", async () => {
  if (!confirm("Clear ALL fault codes and reset ALL readiness monitors?\n\nBest done key ON, engine OFF. Freeze frame data will be lost.")) return;
  log("Sending Mode 04…");
  const ok = await txn(async () => {
    await setHeader("7DF");
    const raw = await sendCmd("04", 5000);
    await setHeader(baseHeader);
    return messages(raw).some((m) => m.startsWith("44"));
  });
  if (ok) {
    log("Codes cleared. Re-reading…");
    await txn(async () => { await readDtcs(); await loadReadiness(); });
    log("Codes cleared and monitors reset.");
  } else {
    log("ECM did not confirm the clear. Try key ON, engine OFF.");
    alert("The ECM did not confirm the clear (no 44 response). Try again with key ON, engine OFF.");
  }
});
$("aiBtn").addEventListener("click", () => requestAi("full"));
$("syncBtn").addEventListener("click", async () => { if (!vinRead) await txn(readVin); sendSync(false); });
$("oemSel").addEventListener("change", () => { if (connected) buildEnhanced(); });
</script>
</body>
</html>
'''


def _ble_component_dir() -> str:
  """Write the dashboard page to a temp folder so the whole app lives in this one file."""
  d = Path(tempfile.gettempdir()) / "ble_dashboard"
  d.mkdir(exist_ok=True)
  f = d / "index.html"
  if not f.exists() or f.read_text(encoding="utf-8") != BLE_DASHBOARD_HTML:
    f.write_text(BLE_DASHBOARD_HTML, encoding="utf-8")
  return str(d)


_ble_dashboard = components.declare_component("ble_dashboard", path=_ble_component_dir())


def _fmt_dtcs(d: dict) -> str:
  return (f"Stored: {', '.join(d.get('stored') or []) or 'none'} | Pending: {', '.join(d.get('pending') or []) or 'none'}"
          f" | Permanent: {', '.join(d.get('permanent') or []) or 'none'}")


def handle_ble_event(ev: dict):
  if ev.get("type") == "sync":
    d = ev.get("dtcs") or {}
    ss.ble_dtcs = d
    ss.scan_data = {k: ev.get(k) for k in ("pids", "readiness", "mode6", "at")}
    codes = list(dict.fromkeys((d.get("stored") or []) + (d.get("pending") or [])))
    vin = (ev.get("vin") or "").upper()
    upd = {}
    if VIN_RE.fullmatch(vin):
      if vin == ss.active_vin or load_vehicle(vin):
        upd["vin_input"] = vin
    upd["sel_codes"] = codes  # scanned codes go straight into the Diagnose tab
    append_to_log(vin=vin or ss.active_vin, vehicle=ss.vehicle_info, dtc=", ".join(codes) or "No codes",
                  customer=ss.customer_name, phone=ss.customer_phone)
    queue_update(toast=f"Scanner synced: {vin or 'no VIN'} · {len(codes)} code(s) sent to the Diagnose tab", **upd)

  elif ev.get("type") == "ai":
    vehicle = ss.vehicle_info or "General OBD-II Vehicle"
    pids = json.dumps(ev.get("pids") or {}, indent=1)
    dtcs = _fmt_dtcs(ev.get("dtcs") or {})
    if ev.get("mode") == "drive":
      prompt = f"""You are an expert ASE Master / L1 Diagnostic Technician monitoring a live test drive.
Vehicle: {vehicle}
Codes: {dtcs}
LATEST SNAPSHOT UNDER ROAD LOAD ({ev.get('at')}):
{pids}

Give a concise 3-bullet live assessment, under 100 words total:
1. Fuel delivery & trim state (Bank 1 vs Bank 2 under the current load).
2. Drivetrain health (trans temp, oil pressure, TCC slip, knock) — only if those values are present.
3. Any anomaly to inspect back in the bay."""
      label = f"[Live Drive AI Check - {ev.get('at')}]"
    else:
      prompt = f"""You are an expert ASE Master / L1 Diagnostic Technician.
Vehicle: {vehicle}
Codes read from the vehicle: {dtcs}
Technician-entered DTC: {ss.active_dtc or 'None'}

LIVE DATA (Mode 01 + OEM enhanced PIDs; enhanced values are unverified beta, treat with caution):
{pids}

I/M READINESS: {ev.get('readiness') or 'Not read'}

MODE $06 RESULTS (value [min..max]):
{ev.get('mode6') or 'Not read'}

DIAGNOSTIC TASK:
1. Fuel control: total trim (STFT + LTFT) Bank 1 vs Bank 2; single- vs dual-bank pattern.
2. Powertrain/drivetrain health from whatever enhanced data is present.
3. Air metering & O2/AFR sensors: sensor activity vs catalyst storage on each bank.
4. Mode $06: cylinder misfire counts and any failing or marginal monitor tests.
5. Readiness: which monitors are incomplete and the drive-cycle conditions to set them.
6. The single most definitive next physical/electrical test to confirm the root cause.

Use clean bold section headers and direct shop-floor language. Skip sections with no data."""
      label = f"[Full AI Check - {ev.get('at')}]"
    with st.spinner("Gemini is analyzing the scan data..."):
      text = ask_gemini(prompt)
    ss.ble_ai = {"id": ev.get("id"), "text": text, "label": label}
    st.rerun()


with tab2:
  st.subheader("📊 Live Telemetry, OEM Enhanced PIDs & Monitors")
  context_bar()
  st.caption("Works in Chrome (Android, Windows, macOS, ChromeOS). Connecting reads the VIN and codes and fills them"
             " into the other tabs automatically. The Bluetooth link stays up while you use the rest of the app.")
  event = _ble_dashboard(vehicle=ss.vehicle_info, make=make_profile(),
                         year=ss.vehicle_details.get("Model Year", ""), ai=ss.ble_ai, key="ble", default=None)
  if isinstance(event, dict) and event.get("id") and event["id"] != ss.ble_last_event:
    ss.ble_last_event = event["id"]
    handle_ble_event(event)

# ========================================================
# --- TAB 3: DIAGNOSE (STRATEGY + SCOPE LAB + COPILOT) ---
# ========================================================
def scan_context() -> str:
  """Everything the scanner captured, for the AI prompts."""
  if not ss.ble_dtcs and not ss.scan_data:
    return "No scanner data (codes entered by hand)."
  sd = ss.scan_data or {}
  pids = json.dumps(sd.get("pids") or {}, indent=0) if sd.get("pids") else "not captured"
  return (f"Scanner codes: {_fmt_dtcs(ss.ble_dtcs)}\n"
          f"I/M readiness: {sd.get('readiness') or 'not read'}\n"
          f"Mode $06 results: {sd.get('mode6') or 'not read'}\n"
          f"Live data snapshot at sync ({sd.get('at') or '?'}): {pids}")


with tab3:
  st.subheader("🔧 Diagnose: Strategy, Scope Lab & Copilot")
  context_bar()

  # ---------- 1. Codes ----------
  st.markdown("#### 1 · Fault codes")
  d = ss.ble_dtcs or {}
  kinds = {}
  for kind in ("permanent", "pending", "stored"):  # stored wins if a code is in more than one list
    for c in d.get(kind) or []:
      kinds[c] = kind
  options = list(dict.fromkeys(list(kinds) + list(ss.sel_codes or [])))
  if options:
    st.multiselect(
        "Codes from the scanner (tap ✕ to leave one out):", options=options, key="sel_codes",
        format_func=lambda c: f"{c} · {kinds.get(c, 'added')}",
    )
  else:
    st.caption("Connect the scanner on the Live Telemetry tab — the codes it reads show up here automatically.")
  st.text_input("Add codes by hand (optional):", key="manual_dtc", placeholder="e.g. P0171, P0174")
  st.text_area("Symptoms / customer complaint (optional — works with or without codes):", key="symptoms", height=80,
               placeholder="e.g. Rough idle when cold, stumbles on hard acceleration, no check engine light")

  codes = current_codes()
  code_str = ", ".join(codes)
  col_engine, col_btn = st.columns([3, 1.4])
  with col_engine:
    ai_engine = st.selectbox(
        "AI engine",
        options=["gemini", "perplexity"],
        format_func={"gemini": "✨ Google Gemini 2.5 Flash (deep circuit logic)",
                     "perplexity": "🌐 Perplexity (live web, TSBs)"}.get,
    )
  with col_btn:
    st.write("")
    symptoms = ss.symptoms.strip()
    lookup_clicked = st.button("Run Diagnostic Tree", use_container_width=True, type="primary",
                               disabled=not (codes or symptoms))
  if not (codes or symptoms):
    st.caption("Add a code or describe the symptoms to build a test plan.")

  if lookup_clicked and not codes:
    vehicle = ss.vehicle_info or "General Vehicle"
    append_to_log(vin=ss.active_vin, vehicle=vehicle, dtc=f"No code - {symptoms[:60]}",
                  customer=ss.customer_name, phone=ss.customer_phone)
    sym_prompt = f"""
You are an expert ASE master diagnostic technician. There are NO trouble codes. Build a symptom-based diagnostic plan for a {vehicle}.

CUSTOMER COMPLAINT / SYMPTOMS:
{symptoms}

DATA FROM THE SHOP'S SCAN TOOL (if any):
{scan_context()}

Format strictly using these Markdown sections:

### 1. Most Likely Causes (ranked)
- Ranked list for THIS vehicle and THESE symptoms, with a one-line reason each. Lead with known pattern failures for this platform.

### 2. Questions to Ask / Conditions to Recreate
- When it happens (cold/hot, load, speed, weather) and how to reproduce it on a test drive.

### 3. Quick Checks First (cheap & fast)
- Visual checks, scan-data PIDs to watch (with expected values), Mode $06 / misfire counters to look at.

### 4. Pinpoint Tests to Confirm
- Specific DMM / scope / pressure / smoke tests that separate the top causes from each other.

### 5. Known Platform Pattern Failures & TSBs
- Real-world failure patterns and TSBs for {vehicle} matching these symptoms.
"""
    with st.spinner(f"Building a symptom-based test plan via {ai_engine.title()}..."):
      text = ask_gemini(sym_prompt) if ai_engine == "gemini" else ask_perplexity(sym_prompt)
    ss.dtc_result = {"title": f"Symptoms · {vehicle} · {ai_engine.title()}", "text": text}

  if lookup_clicked and codes:
    vehicle = ss.vehicle_info or "General OBD-II Vehicle"
    append_to_log(vin=ss.active_vin, vehicle=vehicle, dtc=code_str, customer=ss.customer_name, phone=ss.customer_phone)
    dtc_prompt = f"""
You are an expert ASE master diagnostic technician. Provide a laser-focused, code-specific diagnostic testing workflow for fault code(s) {code_str} on a {vehicle}.

CUSTOMER COMPLAINT / SYMPTOMS: {symptoms or 'not given'}

DATA FROM THE SHOP'S SCAN TOOL (use it to sharpen the plan; ignore if irrelevant):
{scan_context()}

STRICT SCOPE RULES:
- ONLY provide tests and checks for the exact subsystem, sensor, actuator, or circuit named in {code_str}.
- DO NOT provide generic boilerplate checks (fuel pressure, fuel trims, spark, compression) UNLESS the codes directly involve those systems.
- If several codes are given, say whether they likely share one root cause and which to diagnose first.
- If the scan data already points somewhere (a failing Mode $06 test, a misfire counter, a trim), say so up front.
- Focus on practical shop isolation: circuit vs computer vs mechanical component.

Format strictly using these Markdown sections:

### 1. Code Definition & Setting Criteria
- Exact technical definition and the conditions the ECM uses to set it.

### 2. What the Scan Data Already Tells Us
- Only if scanner data is present; otherwise skip this section.

### 3. Live Scan Data & Bi-Directional Active Tests
- Only the PIDs tied to this circuit/actuator (with expected values) and the functional test to command it.

### 4. Pinpoint Electrical & Circuit Checks (DMM / Scope)
- Connector pinout checks (reference, ground drop limit, feed, PWM duty) and component resistance specs.

### 5. Physical & Mechanical Inspection
- Visual/mechanical checks strictly for this mechanism.

### 6. Known Platform Pattern Failures & TSBs
- Real-world failure patterns for {vehicle} on this system.
"""
    with st.spinner(f"Building the {code_str} test plan via {ai_engine.title()}..."):
      text = ask_gemini(dtc_prompt) if ai_engine == "gemini" else ask_perplexity(dtc_prompt)
    ss.dtc_result = {"title": f"{code_str} · {vehicle} · {ai_engine.title()}", "text": text}

  if ss.dtc_result:  # stays on screen while you use other tabs
    with st.expander(f"📋 Test plan: {ss.dtc_result['title']}", expanded=True):
      st.markdown(ss.dtc_result["text"])

  # ---------- 2. Scope lab ----------
  st.write("---")
  st.markdown("#### 2 · Scope & test readings")
  col_scope, col_scratch = st.columns(2)
  with col_scope:
    scope_capture = st.camera_input("Capture oscilloscope or meter") if st.toggle("📷 Open Camera for Scope / Meter") else None
    scope_file = st.file_uploader("Or upload a scope / meter photo", type=["png", "jpg", "jpeg"], key="scope_upload")
    active_img = scope_capture or scope_file
    pil_scope_image = None
    if active_img:
      st.image(active_img.getvalue(), caption="Captured Scope / Meter Display")
      pil_scope_image = ImageOps.exif_transpose(Image.open(active_img))

  with col_scratch:
    comp_data = st.text_input("Compression / Leakdown (psi / % drop):",
                              placeholder="e.g., Cyl 1: 160, Cyl 2: 155, Cyl 3: 90, Cyl 4: 160")
    fuel_data = st.text_input("Fuel Pressure (Running / 5-min Bleed-down):",
                              placeholder="e.g., 55 psi running, drops to 12 psi in 3 mins")
    volt_data = st.text_input("Electrical / Voltage Drop:",
                              placeholder="e.g., Cranking battery drop 9.1V, engine ground drop 0.4V")
    scope_notes = st.text_area("Scope Waveform Observations:", height=70,
                               placeholder="e.g., Coil burn time 0.7ms; injector kick only 35V; CKP missing tooth uneven")

  if st.button("🔍 Analyze Readings & Scope Pattern"):
    prompt = f"""
You are an expert ASE Master / L1 diagnostic technician and automotive oscilloscope waveform specialist.
Analyze this oscilloscope or multimeter capture (if attached) alongside the physical shop test readings.

Vehicle: {ss.vehicle_info or 'General'}
Fault codes: {code_str or 'None'}
Symptoms: {ss.symptoms.strip() or 'not given'}
{scan_context()}

PHYSICAL TEST READINGS:
Compression/Leakdown: {comp_data or 'Not tested'}
Fuel Pressure & Bleed-down: {fuel_data or 'Not tested'}
Voltage Drop / Electrical: {volt_data or 'Not tested'}
Scope Observations: {scope_notes or 'None reported'}

TASK:
- Identify the signal type (secondary/primary ignition, injector voltage/current, CKP/CMP correlation, relative compression, PWM, sensor drop).
- Evaluate key signatures: firing/inductive kV, dwell, burn line slope & turbulence, coil oscillations, ground bounce, attenuation, missing-tooth spacing.
- Correlate waveform abnormalities with the physical readings, the fault codes and the scan data.

FORMAT STRICTLY AS:
### 1. Scope Waveform & Electrical Findings
### 2. Component Condemnation & Defect Root Cause
### 3. Immediate Pinpoint Verification Step
"""
    parts = [{"text": prompt}] + ([img_part(pil_scope_image)] if pil_scope_image else [])
    with st.spinner("Gemini Vision is analyzing waveform signatures and physical readings..."):
      try:
        ss.scope_result = gemini(parts)
      except AIError as e:
        ss.scope_result = f"⚠️ {e}"

  if ss.scope_result:
    with st.expander("🔬 Scope & readings evaluation", expanded=True):
      st.markdown(ss.scope_result)

  # ---------- 3. Copilot ----------
  st.write("---")
  st.markdown("#### 3 · Copilot chat")
  hcol1, hcol2 = st.columns([4, 1])
  hcol1.caption("Ask follow-ups about the codes, the test plan or your readings. It already knows the vehicle and scan data.")
  if ss.chat_history and hcol2.button("Clear chat"):
    ss.chat_history = []
    st.rerun()

  for msg in ss.chat_history:
    with st.chat_message(msg["role"]):
      st.markdown(msg["content"])

  user_question = st.chat_input("Ask a diagnostic question (e.g., 'How do I isolate a leaking injector from a bad pump check valve?')")
  if user_question:
    ss.chat_history.append({"role": "user", "content": user_question})
    with st.chat_message("user"):
      st.markdown(user_question)
    history = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in ss.chat_history[-6:])
    plan = (ss.dtc_result or {}).get("text", "")[:3000]
    chat_prompt = f"""
You are an expert automotive diagnostic technician assisting a mechanic in the field.
Vehicle: {ss.vehicle_info or 'General'}
Fault codes being worked: {code_str or 'None'}
Symptoms / complaint: {ss.symptoms.strip() or 'not given'}
{scan_context()}
Current test plan (if any): {plan or 'none yet'}
Latest scope/readings evaluation (if any): {(ss.scope_result or 'none')[:1500]}

Recent conversation:
{history}

Respond directly, practically, and concisely to the latest question. Focus on physical shop tests, circuit checks, and logical isolation.
"""
    with st.chat_message("assistant"):
      with st.spinner("Gemini thinking..."):
        reply = ask_gemini(chat_prompt)
      st.markdown(reply)
    ss.chat_history.append({"role": "assistant", "content": reply})

# ========================================================
# --- TAB 5: VEHICLE & DTC LOG ---
# ========================================================
with tab5:
  st.subheader("📋 Vehicle Diagnostic Scan History")
  st.caption("Logged automatically when the scanner syncs or you run a diagnostic tree. Note: on Streamlit Cloud this"
             " file resets whenever the app restarts, so export it regularly.")

  history = load_log()
  if history:
    st.dataframe(history, use_container_width=True)
    col_csv, col_del = st.columns(2)
    with col_csv:
      with open(LOG_FILE, "rb") as f:
        st.download_button("📥 Export Log to CSV", data=f.read(), file_name="diagnostic_scan_log.csv", mime="text/csv")
    with col_del:
      confirm = st.checkbox("Yes, delete all log entries")
      if st.button("🗑️ Clear Log History", disabled=not confirm):
        os.remove(LOG_FILE)
        queue_update(toast="Log cleared")
  else:
    st.info("No vehicles or DTCs logged yet. Connect the scanner (Live Telemetry tab) or run a diagnostic tree (Diagnose tab) to start logging.")
