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
    "vehicle_details": {}, "vin_error": "", "active_dtc": "",
    "chat_history": [], "dtc_result": None, "scope_result": None,
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
    _upd["active_dtc"] = _qd
  queue_update(**_upd)


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

  if ss.active_vin and ss.vehicle_details:
    if not vin_check_digit_ok(ss.active_vin):
      st.warning("⚠️ VIN check digit (9th character) doesn't match. One character may be misread"
                 " (common with photos). Non-North-American VINs can ignore this.")
    st.subheader(f"{ss.vehicle_info}  ·  `{ss.active_vin}`")
    col1, col2 = st.columns(2)
    for i, (k, v) in enumerate(ss.vehicle_details.items()):
      (col1 if i % 2 == 0 else col2).write(f"**{k}:** {v}")
    st.caption(f"Bluetooth enhanced-PID profile: **{make_profile()}**")

# ========================================================
# --- TAB 2: LIVE TELEMETRY, ENHANCED PIDS, MONITORS & MODE 06 ---
# ========================================================
# ========================================================
# --- BLUETOOTH DASHBOARD PAGE (runs in the browser) ---
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
  .tile.na { opacity:.4; }
  .enh .tile { border-color:var(--p); }
  .box { background:var(--card); border:1px solid var(--line); border-radius:6px; padding:10px; margin-bottom:16px; font-size:.85rem; color:var(--muted); }
  .chips { display:flex; flex-wrap:wrap; gap:6px; }
  .chip { padding:4px 10px; border-radius:12px; font-weight:700; font-family:monospace; font-size:.9rem; border:1px solid; }
  .mon { background:var(--bg); border:1px solid; padding:6px; border-radius:5px; text-align:center; }
  .mon .l { font-size:.74rem; color:var(--muted); } .mon .v { font-size:.88rem; font-weight:700; }
  #aiBox { border-color:var(--o); color:#fff; font-size:.9rem; line-height:1.45; min-height:80px; }
  #aiBox h4 { color:var(--g); margin:8px 0 4px; }
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

  <h3 style="color:var(--g)">📈 LIVE DATA (MODE 01) <span id="rate" class="note"></span></h3>
  <div id="liveGrid" class="grid"></div>

  <h3 style="color:var(--p)">🏭 OEM ENHANCED PIDS <span class="note">beta: verify readings against a factory-level scan tool before relying on them</span></h3>
  <div id="enhGrid" class="grid enh"></div>

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

let ARGS = { vehicle: "", make: "GENERIC", ai: null };
let lastAiShown = null;
window.addEventListener("message", (e) => {
  if (!e.data || e.data.type !== "streamlit:render") return;
  const a = e.data.args || {};
  const makeChanged = a.make !== ARGS.make;
  ARGS = a;
  if (makeChanged && connected) buildEnhanced();
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
  ["volt", "Battery Volt", "w"],
];
const ENH_TILES = [
  ["tft", "Trans Fluid Temp"], ["eop", "Oil Pressure"], ["cht", "Cyl Head Temp / VCM / TC Temp"], ["tcc", "TCC Slip"],
  ["gear", "Commanded Gear"], ["kr", "Knock Retard"], ["eth", "Ethanol %"], ["soc", "Hybrid SOC"],
];
const LABEL = {};
function makeTiles(gridId, tiles, color) {
  $(gridId).innerHTML = tiles.map(([id, label, c]) => {
    LABEL[id] = label;
    return `<div class="tile" id="t_${id}"><div class="l">${label}</div><div class="v" id="v_${id}" style="color:var(--${c || color})">--</div></div>`;
  }).join("");
}
makeTiles("liveGrid", LIVE_TILES);
makeTiles("enhGrid", ENH_TILES, "p");

const shown = {};   // tile id -> display text
const num = {};     // tile id -> numeric value (for alerts)
function setTile(id, text, n) {
  shown[id] = text;
  if (n !== undefined) num[id] = n;
  const v = $("v_" + id); if (!v) return;
  v.textContent = text;
  $("t_" + id).classList.toggle("na", text === "N/A");
}

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
async function setHeader(h) {
  if (!isCan || h === curHeader) return;
  await sendCmd("ATSH" + h, 500);
  curHeader = h;
}

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
};
const TIER_EVERY = { 1: 1, 2: 2, 3: 6 };
let active = [];   // PIDs actually polled, chosen from what the ECM says it supports

function choosePids(sup) {
  const has = (p) => !sup || sup.has(p);
  const alt1D = sup && sup.has("1D") && !sup.has("13");   // 4-bank O2 layout
  const pick = {
    rpm: ["0C"], load: ["04"], tps: ["11"], spd: ["0D"], stft1: ["06"], ltft1: ["07"], stft2: ["08"], ltft2: ["09"],
    timing: ["0E"], maf: ["10"], map: ["0B"], app: ["49"], ect: ["05"], iat: ["0F"], aat: ["46"], eot: ["5C"],
    frp: ["23", "0A"], fli: ["2F"], evap: ["2E"], baro: ["33"],
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
  setTile(d.tile, d.fn(b), d.n ? d.n(b) : undefined);
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
    let raw = await sendCmd("01" + p + (isCan && fastOK ? "1" : ""), 800);
    if (isCan && fastOK && /\?/.test(raw)) { fastOK = false; raw = await sendCmd("01" + p, 800); }
    const got = parse01(raw, [p]);
    if (got[p]) applyPid(p, got[p]);
  }
}

// ===================== OEM enhanced DIDs (Service $22/$21) =====================
// [header, request, decoder]; candidates are tried in order and the first that answers is locked in.
const one = (f) => (b) => b.length ? f(b) : null;
const two = (f) => (b) => b.length >= 2 ? f(b) : null;
const C40 = one((b) => degF(b[0] - 40) + " °F");
const GEAR = one((b) => "Gear " + b[0]);
const ENH = {
  HONDA: [
    ["tft", [["7E1", "222201", (b) => b.length >= 27 ? degF(b[26] - 40) + " °F" : null], ["7E0", "222201", (b) => b.length >= 27 ? degF(b[26] - 40) + " °F" : null], ["7E1", "21D9", C40], ["7E0", "221627", C40]]],
    ["cht", [["7E0", "222615", (b) => b.length >= 51 ? b[50] + " Cyls (VCM)" : null]]],
    ["tcc", [["7E1", "221E14", two((b) => Math.round(u16(b) / 4) + " RPM")]]],
    ["gear", [["7E1", "221E12", GEAR]]],
  ],
  TOYOTA: [
    ["tft", [["7E0", "221627", C40], ["7E1", "221627", C40]]],
    ["cht", [["7E0", "221628", one((b) => degF(b[0] - 40) + " °F (TC)")]]],
    ["gear", [["7E0", "221621", GEAR]]],
    ["tcc", [["7E0", "221620", one((b) => (b[0] & 1) ? "Locked" : "Unlocked")]]],
    ["soc", [["7E0", "22015B", one((b) => (b[0] * 0.5).toFixed(1) + "%")]]],
  ],
  NISSAN: [
    ["tft", [["7E1", "221017", C40], ["7E0", "221017", C40]]],
    ["eot", [["7E0", "22114A", C40]], "ifEmpty"],
    ["gear", [["7E1", "221621", GEAR]]],
  ],
  HYUNDAI: [
    ["tft", [["7E1", "221627", C40]]],
    ["eot", [["7E0", "221104", C40]], "ifEmpty"],
    ["kr", [["7E0", "2211A6", one((b) => (b[0] * 0.1).toFixed(1) + "°")]]],
  ],
  SUBARU: [
    ["tft", [["7E1", "221017", C40], ["7E0", "221017", C40]]],
    ["eot", [["7E0", "22114A", C40]], "ifEmpty"],
  ],
  MAZDA: [
    ["tft", [["7E1", "221E1C", two((b) => degF(u16(b) / 80) + " °F")]]],
    ["gear", [["7E1", "221E12", GEAR]]],
    ["tcc", [["7E1", "221E14", two((b) => Math.round(u16(b) / 4) + " RPM")]]],
  ],
  FORD: [
    ["tft", [["7E0", "221E1C", two((b) => degF(u16(b) / 16 - 40) + " °F")], ["7E0", "221674", two((b) => degF(u16(b) * 5 / 72 - 18) + " °F")]]],
    ["cht", [["7E0", "221624", two((b) => degF(u16(b) / 10 - 40) + " °F")]]],
    ["tcc", [["7E0", "221E14", two((b) => Math.round(u16(b) / 4) + " RPM")]]],
    ["gear", [["7E0", "221E12", GEAR]]],
  ],
  GM: [
    ["tft", [["7E0", "221940", C40], ["7E2", "221940", C40]]],
    ["eop", [["7E0", "22115C", one((b) => Math.round(b[0] * 0.579) + " PSI")]]],
    ["kr", [["7E0", "2211A6", one((b) => (b[0] * 0.1).toFixed(1) + "°")]]],
    ["tcc", [["7E0", "221943", two((b) => Math.round(u16(b) / 8) + " RPM")]]],
    ["gear", [["7E0", "221944", GEAR]]],
    ["eth", [["7E0", "220052", one((b) => Math.round(b[0] * 0.392) + "%")]]],
  ],
  CHRYSLER: [
    ["eop", [["7E0", "221003", one((b) => Math.round(b[0] * 0.58) + " PSI")]]],
    ["tft", [["7E0", "22B005", C40], ["7E2", "22B005", C40]]],
    ["eot", [["7E0", "221002", C40]], "ifEmpty"],
  ],
};
let enh = [];
function profile() { const s = $("oemSel").value; return s === "AUTO" ? (ARGS.make || "GENERIC") : s; }
function buildEnhanced() {
  ENH_TILES.forEach(([id]) => setTile(id, "--"));
  const list = isCan ? (ENH[profile()] || []) : [];
  enh = list
    .filter(([tile, , mode]) => !(mode === "ifEmpty" && active.some((p) => PIDS[p].tile === tile)))
    .map(([tile, cands]) => ({ tile, cands, idx: 0, ok: false, miss: 0 }));
  const used = new Set(enh.map((e) => e.tile));
  ENH_TILES.forEach(([id]) => { if (!used.has(id)) setTile(id, "N/A"); });
}
async function readDid(hdr, req) {
  await setHeader(hdr);
  const raw = await sendCmd(req, 600);
  if (isErr(raw)) return null;
  const pre = respCode(req.slice(0, 2)) + req.slice(2);
  for (const m of messages(raw)) if (m.startsWith(pre)) return bytesOf(m.slice(pre.length));
  return null;
}
async function pollEnhanced() {
  const jobs = enh.filter((e) => e.idx < e.cands.length)
    .sort((a, b) => a.cands[a.idx][0].localeCompare(b.cands[b.idx][0]));   // group by module = fewer header switches
  for (const e of jobs) {
    const [hdr, req, fn] = e.cands[e.idx];
    const b = await readDid(hdr, req);
    let v = null; try { v = b ? fn(b) : null; } catch (_) {}
    if (v != null) { setTile(e.tile, v); e.ok = true; e.miss = 0; continue; }
    e.miss++;
    if (!e.ok || e.miss >= 3) {
      e.idx++; e.ok = false; e.miss = 0;
      if (e.idx >= e.cands.length) setTile(e.tile, "N/A");
    }
  }
  await setHeader(baseHeader);
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
    if (enh.length && cycle % 12 === 0) await txn(pollEnhanced);
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
  batchOK = false; fastOK = true; baseHeader = "7DF";

  if (isCan) {   // talk to the engine computer directly: no duplicate replies from other modules, faster
    await setHeader("7E0");
    if (messages(await sendCmd("0100", 1500)).some((m) => m.startsWith("4100"))) baseHeader = "7E0";
    else await setHeader("7DF");
  }

  log("Reading supported PIDs…");
  const sup = await supported("01", ["00", "20", "40"]);
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
    if (vinRead || dtcs.stored.length || dtcs.pending.length) sendSync(true);   // push VIN + codes into the app automatically (no page reload)
  } catch (err) {
    log("Error: " + err.message);
  } finally {
    $("bleBtn").disabled = connected;
  }
});

function sendSync(auto) {
  sendValue({ type: "sync", id: "sync-" + Date.now(), vin: vinRead, dtcs, auto: !!auto });
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
    codes = list(dict.fromkeys((d.get("stored") or []) + (d.get("pending") or [])))
    vin = (ev.get("vin") or "").upper()
    upd = {}
    if VIN_RE.fullmatch(vin):
      if vin == ss.active_vin or load_vehicle(vin):
        upd["vin_input"] = vin
    if codes:
      upd["active_dtc"] = ", ".join(codes)
    append_to_log(vin=vin or ss.active_vin, vehicle=ss.vehicle_info, dtc=", ".join(codes) or "No codes",
                  customer=ss.customer_name, phone=ss.customer_phone)
    queue_update(toast=f"Scanner synced: {vin or 'no VIN'} · {len(codes)} code(s)", **upd)

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
  event = _ble_dashboard(vehicle=ss.vehicle_info, make=make_profile(), ai=ss.ble_ai, key="ble", default=None)
  if isinstance(event, dict) and event.get("id") and event["id"] != ss.ble_last_event:
    ss.ble_last_event = event["id"]
    handle_ble_event(event)

# ========================================================
# --- TAB 3: IN-DEPTH DTC DIAGNOSTIC STRATEGY ---
# ========================================================
with tab3:
  st.subheader("Field Diagnostic Strategy & Testing Workflow")
  if ss.customer_name:
    st.markdown(f"👤 Customer: **{ss.customer_name}** | 📞 `{ss.customer_phone or 'No phone'}`")
  if ss.vehicle_info:
    st.success(f"Active Vehicle: **{ss.vehicle_info}** (VIN: `{ss.active_vin or 'Manual'}`)")
  else:
    st.caption("Tip: decode a vehicle in Tab 1 (or connect the scanner in Tab 2) to carry vehicle specs over.")
  if ss.ble_dtcs:
    st.caption(f"From scanner → {_fmt_dtcs(ss.ble_dtcs)}")

  col_input, col_engine, col_btn = st.columns([2.5, 2.5, 1.5])
  with col_input:
    st.text_input("OBD-II DTC(s) (e.g., P0316 or P0171, P0174):", key="active_dtc")
  with col_engine:
    ai_engine = st.selectbox(
        "Diagnostic AI Engine",
        options=["gemini", "perplexity"],
        format_func={"gemini": "✨ Google Gemini 2.5 Flash (Deep Logic)",
                     "perplexity": "🌐 Perplexity Sonar Pro (Live Web & TSBs)"}.get,
        help="Gemini provides deep circuit & mechanical logic; Perplexity checks live technical databases and TSBs.",
    )
  with col_btn:
    st.write("")
    lookup_clicked = st.button("Run Diagnostic Tree", use_container_width=True)

  code_input = ss.active_dtc.strip().upper()
  if lookup_clicked and not code_input:
    st.warning("Enter a fault code first.")
  elif lookup_clicked:
    vehicle = ss.vehicle_info or "General OBD-II Vehicle"
    append_to_log(vin=ss.active_vin, vehicle=vehicle, dtc=code_input, customer=ss.customer_name, phone=ss.customer_phone)
    dtc_prompt = f"""
You are an expert ASE master diagnostic technician. Provide a laser-focused, code-specific diagnostic testing workflow for fault code(s) {code_input} on a {vehicle}.

STRICT SCOPE RULES:
- ONLY provide tests and checks for the exact subsystem, sensor, actuator, or circuit named in {code_input}.
- DO NOT provide generic boilerplate checks (fuel pressure, fuel trims, spark, compression) UNLESS {code_input} directly involves those systems.
- If several codes are given, say whether they likely share one root cause and which to diagnose first.
- Focus on practical shop isolation: circuit vs computer vs mechanical component.

Format strictly using these Markdown sections:

### 1. Code Definition & Setting Criteria
- Exact technical definition and the conditions the ECM uses to set it.

### 2. Live Scan Data & Bi-Directional Active Tests
- Only the PIDs tied to this circuit/actuator (with expected values) and the functional test to command it.

### 3. Pinpoint Electrical & Circuit Checks (DMM / Scope)
- Connector pinout checks (reference, ground drop limit, feed, PWM duty) and component resistance specs.

### 4. Physical & Mechanical Inspection
- Visual/mechanical checks strictly for this mechanism.

### 5. Known Platform Pattern Failures & TSBs
- Real-world failure patterns for {vehicle} on this system.
"""
    with st.spinner(f"Generating {code_input} strategy via {ai_engine.upper()}..."):
      text = ask_gemini(dtc_prompt) if ai_engine == "gemini" else ask_perplexity(dtc_prompt)
    ss.dtc_result = {"title": f"{code_input} · {vehicle} · {ai_engine.title()}", "text": text}

  if ss.dtc_result:  # stays on screen while you use other tabs
    st.markdown(f"##### {ss.dtc_result['title']}")
    st.markdown(ss.dtc_result["text"])

# ========================================================
# --- TAB 4: DIAGNOSTIC COPILOT & SCOPE LAB ---
# ========================================================
with tab4:
  st.subheader("⚡ Diagnostic Copilot & Scope Lab")
  context_bar()

  col_scope, col_scratch = st.columns(2)
  with col_scope:
    st.markdown("#### 📸 Scope & Meter Display Capture")
    scope_capture = st.camera_input("Capture oscilloscope or meter") if st.toggle("📷 Open Camera for Scope / Meter") else None
    scope_file = st.file_uploader("Or upload scope waveform image", type=["png", "jpg", "jpeg"], key="scope_upload")
    active_img = scope_capture or scope_file
    pil_scope_image = None
    if active_img:
      st.image(active_img.getvalue(), caption="Captured Scope / Meter Display")
      pil_scope_image = ImageOps.exif_transpose(Image.open(active_img))

  with col_scratch:
    st.markdown("#### 📝 Test Results Scratchpad")
    with st.expander("Enter Physical Test Readings", expanded=True):
      comp_data = st.text_input("Compression / Leakdown (psi / % drop):",
                                placeholder="e.g., Cyl 1: 160, Cyl 2: 155, Cyl 3: 90, Cyl 4: 160")
      fuel_data = st.text_input("Fuel Pressure (Running / 5-min Bleed-down):",
                                placeholder="e.g., 55 psi running, drops to 12 psi in 3 mins")
      volt_data = st.text_input("Electrical / Voltage Drop:",
                                placeholder="e.g., Cranking battery drop 9.1V, engine ground drop 0.4V")
      scope_notes = st.text_area("Scope Waveform Observations:", height=70,
                                 placeholder="e.g., Coil burn time 0.7ms; injector kick only 35V; CKP missing tooth uneven")

  if st.button("🔍 Analyze Entered Test Results & Scope Pattern with Gemini"):
    test_summary = f"""
Vehicle: {ss.vehicle_info or 'General'}
Active DTC: {ss.active_dtc or 'None'}
Compression/Leakdown: {comp_data or 'Not tested'}
Fuel Pressure & Bleed-down: {fuel_data or 'Not tested'}
Voltage Drop / Electrical: {volt_data or 'Not tested'}
Scope Observations: {scope_notes or 'None reported'}
"""
    prompt = f"""
You are an expert ASE Master / L1 diagnostic technician and automotive oscilloscope waveform specialist.
Analyze this oscilloscope or multimeter capture (if attached) alongside the physical shop test readings.

TEST CONTEXT:
{test_summary}

TASK:
- Identify the signal type (secondary/primary ignition, injector voltage/current, CKP/CMP correlation, relative compression, PWM, sensor drop).
- Evaluate key signatures: firing/inductive kV, dwell, burn line slope & turbulence, coil oscillations, ground bounce, attenuation, missing-tooth spacing.
- Correlate waveform abnormalities with the physical readings.

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
    st.markdown("### Diagnostic Evaluation")
    st.markdown(ss.scope_result)

  st.write("---")
  st.markdown("#### 💬 Interactive Diagnostic Copilot (Gemini)")
  hcol1, hcol2 = st.columns([4, 1])
  hcol1.caption("Ask follow-up questions, request pinout checks, or ask how to isolate an intermittent fault.")
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
    chat_prompt = f"""
You are an expert automotive diagnostic technician assisting a mechanic in the field.
Vehicle: {ss.vehicle_info or 'General'}
Active DTC: {ss.active_dtc or 'None'}
Scanner codes: {_fmt_dtcs(ss.ble_dtcs) if ss.ble_dtcs else 'Not scanned'}

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
    st.info("No vehicles or DTCs logged yet. Connect the scanner (Tab 2) or run a code lookup (Tab 3) to start logging.")
