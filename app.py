import base64
import copy
import csv
from datetime import datetime, timezone
import hashlib
import html as html_lib
import io
import json
import os
from pathlib import Path
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageEnhance, ImageOps
import numpy as np
import requests
import streamlit as st
import streamlit.components.v1 as components
import zxingcpp

st.set_page_config(page_title="Test Don't Guess", page_icon="⚡", layout="wide")

APP_VERSION = "2026-10-25"
WHATS_NEW = [
    "Email or text the report to the customer (needs the email/text setup in Secrets)",
    "Job photos: attach pictures to the job; they go on the customer report",
    "Estimate builder with parts & labor totals on the report",
    "Follow-up reminders: flag a job for a callback and see the list in the Log tab",
    "Freeze frame vs. live comparison on the Diagnose tab",
    "Battery & charging slip you can print for the customer",
    "Waveform library: save known-good scope captures and compare against them",
    "Drive cycle coach: a plan for incomplete monitors, and spoken alerts when one completes on a drive",
    "Odometer field — saved with the job, the history and the report",
    "Shop summary: cars, top codes, top fixes and comebacks by month",
    "One-tap backup of everything in storage",
    "Multiple logins with names (APP_USERS in Secrets) — the log shows who worked each car",
    "NEW: 'Doesn't add up' alerts — tiles flag skewed sensors (temp disagreement, MAP vs BARO, low MAF, trims, PCM voltage drop)",
    "NEW: Glitch catcher — stumbles, trim spikes and fuel-pressure drops are caught on a drive with a 20-second hi-res recording for the AI review",
    "NEW: Factory codes now say what the sub-code means (C0031-11 → circuit short to ground)",
    "NEW: Seal EVAP button (Mode $08) for smoke testing, and a cranking smoothness check that screens for a weak cylinder",
    "REDESIGN: cleaner look throughout — one green accent, steadier gauge digits, pill tabs, status bar with a Next-step guide on every tab",
    "FLOW: vehicle first on the intake tab (customer below), photo scanner collapses once the vehicle is set, Diagnose sections 4-6 fold away until needed",
    "FLOW: Setup checklist at the top shows what's connected and exactly which Secret turns each feature on",
    "FIX: live data no longer freezes after connecting when the engine size isn't known yet",
    "FIX: Claude and DeepSeek no longer come back with empty answers on big jobs",
    "NEW: Scope data files — load the CSV your scope saves and the app MEASURES it: burn time, firing kV, injector "
    "pulse width & kick, pintle bump, crank pattern & bad teeth, relative compression by cylinder, cylinder pressure",
    "NEW: Scope setup form (engine condition, what's on each channel, probe scale) and a known-good library "
    "compared number by number",
]

st.markdown(
    f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600;700&display=swap');
.stApp {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }}
.block-container {{ padding-top: 4.5rem !important; padding-bottom: 3rem !important; max-width: 1440px !important; }}
#MainMenu, footer {{ visibility: hidden; }}
/* segmented pill tabs */
div[data-baseweb="tab-list"] {{ background: rgba(17,24,39,.55); border: 1px solid rgba(255,255,255,.08); border-radius: 12px;
  padding: 5px; gap: 6px; margin-bottom: .6rem; overflow-x: auto; }}
button[data-baseweb="tab"] {{ border-radius: 8px !important; padding: 9px 16px !important; font-weight: 600 !important;
  font-size: .92rem !important; border: none !important; background: transparent !important; transition: all .18s ease !important; }}
button[data-baseweb="tab"]:hover {{ background: rgba(255,255,255,.05) !important; }}
button[data-baseweb="tab"][aria-selected="true"] {{ background: linear-gradient(180deg, rgba(16,185,129,.18) 0%, rgba(16,185,129,.06) 100%) !important;
  color: #10B981 !important; box-shadow: inset 0 0 0 1px rgba(16,185,129,.35), 0 2px 8px rgba(0,0,0,.25) !important; }}
div[data-baseweb="tab-highlight"], div[data-baseweb="tab-border"] {{ display: none !important; }}
[data-testid="stTabs"] [role="tablist"] {{ background: rgba(17,24,39,.55); border: 1px solid rgba(255,255,255,.08) !important; border-radius: 12px;
  padding: 5px; gap: 6px; margin-bottom: .6rem; overflow-x: auto; }}
[data-testid="stTabs"] [role="tablist"]::after {{ display: none !important; content: none !important; }}
[data-testid="stTabs"] [role="tab"] {{ border-radius: 8px !important; padding: 8px 16px !important; border: none !important;
  background: transparent !important; transition: all .18s ease; height: auto !important; }}
[data-testid="stTabs"] [role="tab"] p {{ font-size: .92rem !important; font-weight: 600 !important; }}
[data-testid="stTabs"] [role="tab"]:hover {{ background: rgba(255,255,255,.05) !important; }}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {{ background: linear-gradient(180deg, rgba(16,185,129,.18) 0%, rgba(16,185,129,.06) 100%) !important;
  box-shadow: inset 0 0 0 1px rgba(16,185,129,.35), 0 2px 8px rgba(0,0,0,.25) !important; }}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] p {{ color: #10B981 !important; }}
[data-testid="stTabs"] .react-aria-SelectionIndicator {{ display: none !important; }}
/* dark-glass expanders & inputs */
div[data-testid="stExpander"] {{ border: 1px solid rgba(255,255,255,.08) !important; border-radius: 10px !important; overflow: hidden; }}
div[data-baseweb="input"] > div, div[data-baseweb="select"] > div, div[data-baseweb="textarea"] > div {{ border-radius: 8px !important; }}
/* HUD context bar */
.tdg-bar {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; background:rgba(15,22,35,.85); border:1px solid rgba(255,255,255,.08);
  padding:9px 14px; border-radius:10px; margin-bottom:12px; font-size:.85rem; }}
.tdg-bar .pill {{ background:rgba(255,255,255,.05); color:#E2E8F0; padding:3px 10px; border-radius:6px; font-weight:600; }}
.tdg-bar .dtc {{ font-family:'JetBrains Mono',monospace; font-weight:600; padding:3px 10px; border-radius:6px; }}
.tdg-next {{ flex-basis:100%; color:#8B9BB4; font-size:.8rem; }}
.tdg-next b {{ color:#10B981; }}
</style>

<div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px; padding:12px 18px;
  background:linear-gradient(90deg, rgba(16,185,129,.10) 0%, rgba(17,24,39,.55) 55%); border:1px solid rgba(255,255,255,.08);
  border-radius:14px; margin-bottom:1rem; box-shadow:0 10px 30px -10px rgba(0,0,0,.5);">
  <div style="display:flex; align-items:center; gap:14px;">
    <div style="background:rgba(16,185,129,.12); border:1px solid rgba(16,185,129,.3); padding:7px 9px; border-radius:10px; display:flex; align-items:center;">
      <svg width="46" height="28" viewBox="0 0 120 70" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M 5 45 L 22 45 L 24 60 L 42 60 L 43 5 L 46 36 Q 48 34 54 36 T 64 36 T 74 35 T 80 36 Q 84 18 88 50 Q 92 24 96 44 Q 100 32 104 42 L 118 42"
              stroke="#10B981" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"
              style="filter: drop-shadow(0px 0px 6px rgba(16,185,129,.6));"/>
      </svg>
    </div>
    <div>
      <h1 style="margin:0; padding:0; font-size:1.55rem; font-weight:700; letter-spacing:-.02em;">Test Don't Guess</h1>
      <div style="font-size:.74rem; color:#8B9BB4; font-weight:500; letter-spacing:.05em; text-transform:uppercase;">Telemetry &amp; AI diagnostics</div>
    </div>
  </div>
  <div style="font-family:'JetBrains Mono',monospace; font-size:.72rem; color:#10B981; background:rgba(16,185,129,.1);
    border:1px solid rgba(16,185,129,.25); padding:4px 10px; border-radius:999px;">v{APP_VERSION}</div>
</div>
""",
    unsafe_allow_html=True,
)

# ========================================================
# --- CONSTANTS ---
# ========================================================
LOG_FILE = "scan_history.csv"

PROBLEM_LOG = "problem_log.jsonl"
LOG_COLUMNS = ["Timestamp", "Customer", "Phone", "VIN", "Vehicle", "Fault Code (DTC)", "Tech"]
VIN_RE = re.compile(r"[A-HJ-NPR-Z0-9]{17}")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# Model can be changed without editing code: add GEMINI_MODEL = "..." to Streamlit Secrets.
GEMINI_DEFAULT_MODEL = "gemini-3.8-flash"
GEMINI_FALLBACK_MODEL = "gemini-2.5-flash"   # used automatically if the newer model isn't available on your key

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
    "ble_ai": None, "ble_last_event": None, "ble_dtcs": {}, "test_results": {},
    "tech_notes": "", "customer_summary": "", "fix_part": "", "fix_test": "", "fix_notes": "",
    "customer_email": "", "odometer": "", "estimate_rows": [], "follow_up_days": 0, "follow_up_note": "",
    "follow_up_done": False, "drive_plan": "", "wave_result": None,
}
for _k, _v in DEFAULTS.items():
    ss.setdefault(_k, copy.deepcopy(_v))

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
# --- PROBLEM LOG: crashes, AI/API failures and scanner errors, so they can be sent to Claude to fix ---
def log_problem(kind: str, where: str, message: str, details: str = "", extra: dict | None = None):
  entry = {"time": datetime.now().strftime("%Y-%m-%d %I:%M:%S %p"), "version": APP_VERSION, "kind": kind, "where": where,
           "message": str(message)[:500], "details": str(details)[-4000:], "vehicle": st.session_state.get("vehicle_info", ""),
           **(extra or {})}
  try:
    with open(PROBLEM_LOG, "a", encoding="utf-8") as f:
      f.write(json.dumps(entry) + "\n")
  except OSError:
    pass
  try:
    if store_on():
      store_put("problem", datetime.now().strftime("%Y%m%d%H%M%S%f"), entry, local_copy=False)
  except Exception:
    pass
  return entry


def load_problems(limit: int = 200) -> list[dict]:
  if store_on():
    rows = [r.get("data") or {} for r in store_list("problem", limit)]
    if rows:
      return rows
  try:
    with open(PROBLEM_LOG, encoding="utf-8") as f:
      rows = [json.loads(line) for line in f if line.strip()]
  except (OSError, ValueError):
    return []
  return rows[-limit:][::-1]


class guard:
  """Wrap a section: if it crashes, log it and show a friendly message instead of killing the whole app."""
  def __init__(self, where: str):
    self.where = where

  def __enter__(self):
    return self

  def __exit__(self, etype, exc, tb):
    if exc is None:
      return False
    name = etype.__name__
    if "Rerun" in name or "Stop" in name or isinstance(exc, (KeyboardInterrupt, SystemExit)):
      return False   # Streamlit control flow, not a crash
    import traceback
    log_problem("crash", self.where, f"{name}: {exc}", "".join(traceback.format_exception(etype, exc, tb)))
    st.error(f"⚠️ Something broke in **{self.where}** ({name}). It was saved to the problem log — "
             "go to the 📋 Log tab → 🐞 Problem log and copy the report to Claude.")
    return True


class AIError(Exception):
  def __init__(self, msg: str):
    super().__init__(msg)
    log_problem("ai", "AI request", msg)


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


# ========================================================
# --- PERMANENT STORAGE (Supabase; falls back to the app's temporary disk) ---
# ========================================================
# Jobs, scan log, test drives, confirmed fixes and the problem log are saved here so they survive restarts
# and updates. Needs SUPABASE_URL and SUPABASE_KEY in Streamlit Secrets (see the setup notes).
SUPA_TABLE = "tdg_records"
DATA_DIR = "data"


def store_on() -> bool:
  return bool(secret("SUPABASE_URL") and secret("SUPABASE_KEY"))


def _supa_url() -> str:
  return secret("SUPABASE_URL").strip().rstrip("/") + f"/rest/v1/{SUPA_TABLE}"


def _supa_headers(extra: dict | None = None) -> dict:
  key = secret("SUPABASE_KEY").strip()
  h = {"apikey": key, "Content-Type": "application/json"}
  if key.startswith("eyJ"):   # older-style Supabase keys also go in the Authorization header
    h["Authorization"] = f"Bearer {key}"
  h.update(extra or {})
  return h


@st.cache_resource
def _store_versions() -> dict:
  return {}


def _bump(kind: str):
  v = _store_versions()
  v[kind] = v.get(kind, 0) + 1


def _store_error(msg: str):
  """Note a storage problem without calling log_problem (which itself saves to storage)."""
  st.session_state["_store_err"] = msg
  try:
    with open(PROBLEM_LOG, "a", encoding="utf-8") as f:
      f.write(json.dumps({"time": datetime.now().strftime("%Y-%m-%d %I:%M:%S %p"), "version": APP_VERSION,
                          "kind": "storage", "where": "Permanent storage", "message": msg[:500]}) + "\n")
  except OSError:
    pass


def _local_dir(kind: str) -> str:
  d = os.path.join(DATA_DIR, re.sub(r"[^\w\-]", "", kind))
  os.makedirs(d, exist_ok=True)
  return d


def _clean(data):
  return json.loads(json.dumps(data, default=str))


def store_put(kind: str, rid: str, data: dict, local_copy: bool = True) -> bool:
  """Save one record. Returns True if it reached permanent storage."""
  data = _clean(data)
  _bump(kind)
  ok = False
  if store_on():
    try:
      r = http().post(_supa_url(), timeout=10, json=[{"kind": kind, "id": rid, "data": data,
                                                      "updated_at": datetime.now(timezone.utc).isoformat()}],
                      headers=_supa_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}))
      ok = r.status_code < 300
      if not ok:
        _store_error(f"Saving {kind} failed: HTTP {r.status_code} {r.text[:200]}")
    except requests.RequestException as e:
      _store_error(f"Saving {kind} failed: {e}")
  if not ok and local_copy:   # keep it on the temporary disk so nothing is lost this session
    try:
      with open(os.path.join(_local_dir(kind), re.sub(r"[^\w\-]", "", rid) + ".json"), "w", encoding="utf-8") as f:
        json.dump({"id": rid, "data": data, "updated_at": datetime.now(timezone.utc).isoformat()}, f)
    except OSError:
      pass
  return ok


def store_get(kind: str, rid: str) -> dict | None:
  if store_on():
    try:
      r = http().get(_supa_url(), headers=_supa_headers(), timeout=10,
                     params={"kind": f"eq.{kind}", "id": f"eq.{rid}", "select": "data"})
      if r.status_code == 200 and r.json():
        return r.json()[0].get("data")
    except (requests.RequestException, ValueError) as e:
      _store_error(f"Loading {kind} failed: {e}")
  try:
    with open(os.path.join(_local_dir(kind), re.sub(r"[^\w\-]", "", rid) + ".json"), encoding="utf-8") as f:
      return json.load(f).get("data")
  except (OSError, ValueError):
    return None


def store_list(kind: str, limit: int = 200, where: dict | None = None) -> list[dict]:
  """Newest first: [{"id", "data", "updated_at"}, ...]. `where` matches fields inside data exactly."""
  return _store_list(kind, limit, json.dumps(where or {}, sort_keys=True), _store_versions().get(kind, 0), store_on())


@st.cache_data(ttl=120, show_spinner=False, max_entries=300)
def _store_list(kind: str, limit: int, where_json: str, ver: int, online: bool) -> list[dict]:
  where = json.loads(where_json)
  rows = []
  if online:
    params = {"kind": f"eq.{kind}", "select": "id,data,updated_at", "order": "updated_at.desc", "limit": str(limit)}
    for k, v in where.items():
      params[f"data->>{k}"] = f"eq.{v}"
    try:
      r = http().get(_supa_url(), headers=_supa_headers(), params=params, timeout=10)
      if r.status_code == 200:
        rows = r.json()
      else:
        _store_error(f"Listing {kind} failed: HTTP {r.status_code} {r.text[:200]}")
    except (requests.RequestException, ValueError) as e:
      _store_error(f"Listing {kind} failed: {e}")
  seen = {r.get("id") for r in rows}
  try:   # plus anything on the temporary disk (everything, when Supabase isn't set up)
    d = _local_dir(kind)
    for fn in os.listdir(d):
      if fn.endswith(".json"):
        try:
          with open(os.path.join(d, fn), encoding="utf-8") as f:
            rec = json.load(f)
        except (OSError, ValueError):
          continue
        if rec.get("id") not in seen and all(str((rec.get("data") or {}).get(k, "")) == str(v) for k, v in where.items()):
          rows.append(rec)
  except OSError:
    pass
  rows.sort(key=lambda r: str(r.get("updated_at", "")), reverse=True)
  return rows[:limit]


def store_delete(kind: str, rid: str | None = None):
  """Delete one record, or every record of this kind when rid is None."""
  _bump(kind)
  if store_on():
    params = {"kind": f"eq.{kind}"}
    if rid:
      params["id"] = f"eq.{rid}"
    try:
      http().delete(_supa_url(), headers=_supa_headers(), params=params, timeout=10)
    except requests.RequestException as e:
      _store_error(f"Deleting {kind} failed: {e}")
  try:
    d = _local_dir(kind)
    for fn in os.listdir(d):
      if rid is None or fn == re.sub(r"[^\w\-]", "", rid) + ".json":
        os.remove(os.path.join(d, fn))
  except OSError:
    pass


def img_part(img: Image.Image) -> dict:
  im = img.convert("RGB")
  im.thumbnail((1600, 1600))  # smaller upload = faster + cheaper, still sharp enough
  b = io.BytesIO()
  im.save(b, format="JPEG", quality=85)
  return {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(b.getvalue()).decode()}}


def gemini_model() -> str:
  return ss.get("_gemini_model_ok") or secret("GEMINI_MODEL") or GEMINI_DEFAULT_MODEL


def gemini_label() -> str:
  m = gemini_model().replace("gemini-", "Gemini ").replace("-flash", " Flash").replace("-pro", " Pro").replace("-lite", " Lite")
  return m


def gemini(parts: list, *, json_mode: bool = False, timeout: int = 60) -> str:
  key = secret("GEMINI_API_KEY")
  if not key:
    raise AIError("GEMINI_API_KEY is missing from Streamlit Secrets.")
  payload = {"contents": [{"parts": parts}]}
  if json_mode:
    payload["generationConfig"] = {"response_mime_type": "application/json"}
  model = gemini_model()
  for attempt in range(2):
    try:
      res = http().post(GEMINI_URL.format(model=model), headers={"x-goog-api-key": key}, json=payload, timeout=timeout)
    except requests.RequestException as e:
      raise AIError(f"Gemini connection error: {e}") from e
    # Model not available on this key/region -> fall back once to the older model
    if res.status_code in (400, 404) and model != GEMINI_FALLBACK_MODEL and "model" in res.text.lower() and attempt == 0:
      model = GEMINI_FALLBACK_MODEL
      ss["_gemini_model_ok"] = model
      continue
    break
  if res.status_code != 200:
    raise AIError(f"Gemini API error ({res.status_code}, {model}): {res.text[:300]}")
  try:
    parts_out = res.json()["candidates"][0]["content"]["parts"]
    text = "".join(p.get("text", "") for p in parts_out if not p.get("thought"))
  except (KeyError, IndexError, ValueError) as e:
    raise AIError("Gemini returned no text (the request may have been blocked).") from e
  if not text.strip():
    raise AIError("Gemini returned an empty answer. Try again.")
  return text


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


# --- AI TEAM: Perplexity researches the web, Gemini reasons over everything ---
def web_research(vehicle: str, codes: str, symptoms: str, question: str = "") -> str:
  """Perplexity looks up live sources. Returns '' if not configured or it fails."""
  if not secret("PERPLEXITY_API_KEY"):
    return ""
  focus = question or f"fault code(s) {codes or 'none'}; symptoms: {symptoms or 'none given'}"
  prompt = f"""Research for a professional auto technician. Vehicle: {vehicle}. Problem: {focus}.
Find from current, reputable sources (manufacturer TSBs and recalls, NHTSA, technician forums like iATN, repair databases):
1. TSBs / recalls / service campaigns that match (give bulletin numbers and what they fix).
2. Known pattern failures for this exact platform and how often they're the cause.
3. Published factory specs relevant to testing (resistance, voltage, pressure, duty cycle, pinouts) if available.
4. Common misdiagnoses or parts that get replaced for nothing.
Be specific to this vehicle, list sources, and say clearly when something could not be confirmed."""
  out = ask_perplexity(prompt)
  if out.startswith("⚠️") or out == "No response text received.":
    log_problem("ai", "Perplexity web research", out)
    return ""
  return out


TEAM_RULES = """
WEB RESEARCH FROM PERPLEXITY (live sources; may contain errors):
{research}

TEAM RULES:
- Use the web research to sharpen your answer: name the TSBs, recalls and pattern failures it found.
- Cross-check it against sound diagnostic logic. If the research conflicts with good practice or the scan data, say so.
- Never invent TSB numbers or specs that aren't in the research or that you aren't sure of.
- Finish with a short "### Team Notes" section: where the web research and your analysis agree or disagree.
"""


# --- Claude (Anthropic) ---
CLAUDE_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_DEFAULT_MODEL = "claude-sonnet-5-5"   # change with CLAUDE_MODEL in Secrets (e.g. claude-opus-5-5)


def has_claude() -> bool:
  return bool(secret("ANTHROPIC_API_KEY"))


def claude_label() -> str:
  m = secret("CLAUDE_MODEL") or CLAUDE_DEFAULT_MODEL
  return m.replace("claude-", "Claude ").replace("-", " ").title().replace(" 5 5", " 5.5").replace("Claude Claude", "Claude")


def _img_list(image_b64) -> list:
  """One photo (a string) or several (a list) -> list of photos."""
  if isinstance(image_b64, str):
    return [image_b64] if image_b64 else []
  return [x for x in (image_b64 or []) if x]


def claude(prompt: str, *, max_tokens: int = 4000, timeout: int = 120, image_b64="") -> str:
  """Ask Claude. Newer Claude models can spend part of max_tokens "thinking" before they write; if the
  budget runs out mid-thought the answer comes back EMPTY (stop_reason = max_tokens). When that happens,
  ask once more with a much bigger budget instead of giving up."""
  key = secret("ANTHROPIC_API_KEY")
  if not key:
    raise AIError("ANTHROPIC_API_KEY is missing from Streamlit Secrets.")
  content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b}}
             for b in _img_list(image_b64)] + [{"type": "text", "text": prompt}]
  budgets = [max_tokens, min(max(max_tokens * 3, 12000), 32000)]
  why = ""
  for attempt, budget in enumerate(budgets):
    try:
      res = http().post(CLAUDE_URL, timeout=timeout if attempt == 0 else max(timeout, 240), json={
          "model": secret("CLAUDE_MODEL") or CLAUDE_DEFAULT_MODEL, "max_tokens": budget,
          "messages": [{"role": "user", "content": content}]},
          headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    except requests.RequestException as e:
      raise AIError(f"Claude connection error: {e}") from e
    if res.status_code != 200:
      raise AIError(f"Claude API error ({res.status_code}): {res.text[:300]}")
    try:
      data = res.json()
      blocks = data.get("content") or []
      text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    except (ValueError, AttributeError) as e:
      raise AIError("Claude returned an unreadable answer.") from e
    stop = data.get("stop_reason")
    if text.strip():
      if stop == "max_tokens":
        text += "\n\n_(Claude's answer hit the length limit and may be cut off.)_"
      return text
    kinds = sorted({b.get("type", "?") for b in blocks}) or ["none"]
    why = f"stop_reason={stop}, blocks={','.join(kinds)}, max_tokens={budget}"
    if stop == "refusal":
      raise AIError(f"Claude declined to answer this request ({why}).")
    if stop != "max_tokens" or attempt == len(budgets) - 1:
      break
    log_problem("ai", "Claude", f"Empty answer — budget used up before writing ({why}). Retrying with {budgets[attempt + 1]}.")
  raise AIError(f"Claude returned an empty answer ({why}).")


# --- DeepSeek (second independent draft) ---
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_DEFAULT_MODEL = "deepseek-flash"   # change with DEEPSEEK_MODEL in Secrets (e.g. deepseek-v4-pro)


def has_deepseek() -> bool:
  return bool(secret("DEEPSEEK_API_KEY"))


def deepseek_label() -> str:
  m = secret("DEEPSEEK_MODEL") or DEEPSEEK_DEFAULT_MODEL
  return m.replace("deepseek-", "DeepSeek ").replace("-", " ").replace("v4", "V4").title().replace("Deepseek", "DeepSeek").replace("V4 ", "V4 ")


def _deepseek_raw(key: str, model: str, session: requests.Session, prompt: str, max_tokens: int, timeout: int) -> str:
  """No Streamlit calls in here, so it is safe to run in a background thread.
  DeepSeek "thinks" by default, and the thinking counts against max_tokens — on a big job it could use the
  whole budget and return an EMPTY answer. Its job here is a fast second-opinion draft (Claude does the deep
  review), so thinking is switched off. If an empty answer still comes back, one retry with a bigger budget."""
  def call(think_off: bool, budget: int):
    body = {"model": model, "max_tokens": budget, "messages": [{"role": "user", "content": prompt}]}
    if think_off:
      body["thinking"] = {"type": "disabled"}
    try:
      res = session.post(DEEPSEEK_URL, timeout=timeout, json=body,
                         headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    except requests.RequestException as e:
      raise RuntimeError(f"DeepSeek connection error: {e}") from e
    return res
  res = call(True, max_tokens)
  if res.status_code == 400 and "think" in res.text.lower():   # this model doesn't take the switch: ask normally
    res = call(False, max(max_tokens, 12000))
  if res.status_code != 200:
    raise RuntimeError(f"DeepSeek API error ({res.status_code}, {model}): {res.text[:300]}")
  try:
    choice = res.json()["choices"][0]
    msg = choice["message"]
  except (KeyError, IndexError, ValueError) as e:
    raise RuntimeError("DeepSeek returned an unreadable answer.") from e
  text = msg.get("content") or ""
  if not text.strip() and choice.get("finish_reason") == "length":
    res = call(False, max(max_tokens * 3, 12000))
    try:
      choice = res.json()["choices"][0]
      msg = choice["message"]
      text = msg.get("content") or ""
    except (KeyError, IndexError, ValueError):
      text = ""
  if not text.strip():
    raise RuntimeError(f"DeepSeek returned an empty answer (finish_reason={choice.get('finish_reason')}, "
                       f"thinking={'yes' if msg.get('reasoning_content') else 'no'}).")
  return text


def deepseek(prompt: str, *, max_tokens: int = 4000, timeout: int = 120) -> str:
  key = secret("DEEPSEEK_API_KEY")
  if not key:
    raise AIError("DEEPSEEK_API_KEY is missing from Streamlit Secrets.")
  try:
    return _deepseek_raw(key, secret("DEEPSEEK_MODEL") or DEEPSEEK_DEFAULT_MODEL, http(), prompt, max_tokens, timeout)
  except RuntimeError as e:
    raise AIError(str(e)) from e


REVIEW_PROMPT = """You are the senior master technician on a diagnostic team. Perplexity searched the web, and Gemini and DeepSeek each wrote a first-draft plan on their own.
Your job: produce the FINAL plan the technician will follow.

ORIGINAL TASK (vehicle, codes, symptoms, scan data and test results, plus required format):
{task}

WEB RESEARCH (Perplexity; may contain errors):
{research}

GEMINI'S DRAFT:
{draft}

DEEPSEEK'S DRAFT (written separately — a second opinion):
{ds_draft}

INSTRUCTIONS:
- Keep the exact section format the original task requires.
- Compare both drafts against the scan data, test results and research. Keep the best of each, fix anything wrong, remove generic or irrelevant steps, add important tests or pattern failures it missed.
- If photos are attached (scope / meter capture, wiring diagram, connector, part), look at them yourself and check that what the drafts say they show is right. For wiring diagrams, read wire colors, pin numbers and splice/ground locations carefully.
- Your main job is making sure NOTHING IS MISSED: any reading, code, alert or test result in the task that neither draft explained, you explain.
- Order the tests from fastest/cheapest and most likely to least, so the tech doesn't throw parts at it.
- Never invent TSB numbers or specs; only use ones from the research or that you are sure of.
- End with "### Team Notes": 2-5 bullets on what you changed, and where Gemini, DeepSeek and the research disagreed and who was right."""


def team_answer(prompt: str, vehicle: str, codes: str, symptoms: str, use_web: bool, status=None, *,
                question: str = "", image_b64="", fast: bool = False, research: str = "") -> tuple[str, str, str, str]:
  """The whole team on one job: Perplexity researches -> Gemini and DeepSeek draft at the same time
  -> Claude checks both (and the photo, if any) and writes the final answer.
  Steps are skipped if their key isn't set. fast=True = short answers (live test drive checks).
  Returns (final answer, research, gemini draft, deepseek draft)."""
  draft, ds_draft, gem_err = "", "", ""
  tokens = 900 if fast else 4000
  if use_web and not research:
    if status:
      status.update(label="🌐 Perplexity is researching TSBs, recalls and known fixes...")
    research = web_research(vehicle, codes, symptoms, question=question)
  full = prompt + (TEAM_RULES.format(research=research[:6000]) if research else "")
  writers = f"✨ {gemini_label()}" + (f" and 🐋 {deepseek_label()} are" if has_deepseek() else " is")
  if status:
    status.update(label=f"{writers} working on it" + (" with the web research..." if research else "..."))
  pool, ds_job = None, None
  if has_deepseek():   # DeepSeek runs in the background while Gemini works, so it adds no wait time
    ds_prompt = full + ("\n\nNOTE: the technician attached photo(s) (scope, meter, wiring diagram or part) that you cannot see. "
                        "Work from the text; another technician is reading the photos." if _img_list(image_b64) else "")
    pool = ThreadPoolExecutor(max_workers=1)
    # its own connection: the shared one isn't guaranteed safe while Gemini uses it at the same time
    ds_job = pool.submit(_deepseek_raw, secret("DEEPSEEK_API_KEY"), secret("DEEPSEEK_MODEL") or DEEPSEEK_DEFAULT_MODEL, requests.Session(),
                         ds_prompt, tokens, 60 if fast else 120)
  try:
    parts = [{"text": full}] + [{"inline_data": {"mime_type": "image/jpeg", "data": b}} for b in _img_list(image_b64)]
    draft = gemini(parts, timeout=45 if fast else 60)
  except AIError as e:
    gem_err = str(e)
  if ds_job:
    try:
      ds_draft = ds_job.result(timeout=90 if fast else 200)
    except Exception as e:
      log_problem("ai", "DeepSeek draft", str(e))
      ds_draft = ""
    pool.shutdown(wait=False)
  if has_claude():
    if status:
      status.update(label=f"🧠 {claude_label()} is checking everyone's work so nothing is missed...")
    try:
      final = claude(REVIEW_PROMPT.format(task=prompt, research=research[:6000] or "none",
                                          draft=draft or "(Gemini draft unavailable)",
                                          ds_draft=ds_draft or "(DeepSeek draft unavailable)")
                     + ("\n\nKeep the final answer SHORT (the tech is driving): under 120 words, then 1-2 Team Notes bullets." if fast else ""),
                     max_tokens=1500 if fast else 8000, timeout=60 if fast else 150, image_b64=image_b64)
      return final, research, draft, ds_draft
    except AIError as e:
      best = draft or ds_draft
      if best:
        return best + f"\n\n_⚠️ Claude review unavailable: {e}_", research, "", (ds_draft if draft else "")
  if draft:
    return draft, research, "", ds_draft
  if ds_draft:
    return ds_draft + (f"\n\n_⚠️ Gemini failed: {gem_err}_" if gem_err else ""), research, "", ""
  return (f"⚠️ Gemini failed ({gem_err}). Showing Perplexity's research instead:\n\n{research}" if research else f"⚠️ {gem_err}"), research, "", ""


def team_names(draft: str, ds_draft: str, research: str) -> str:
  return " + ".join(x for x in ["🌐 Perplexity" if research else "", "✨ " + gemini_label() if draft or not has_claude() else "",
                                "🐋 " + deepseek_label() if ds_draft else "", "🧠 " + claude_label() if (draft or ds_draft) and has_claude() else ""] if x)


def quick_ai(prompt: str, image_b64="", max_tokens: int = 1500) -> tuple[str, str]:
  """One AI, one answer: Claude if its key is set, otherwise Gemini. Returns (answer, who answered)."""
  if has_claude():
    try:
      return claude(prompt, max_tokens=max_tokens, timeout=90, image_b64=image_b64), "🧠 " + claude_label()
    except AIError:
      pass   # fall through to Gemini
  try:
    parts = [{"text": prompt}] + [{"inline_data": {"mime_type": "image/jpeg", "data": b}} for b in _img_list(image_b64)]
    return gemini(parts, timeout=60), "✨ " + gemini_label()
  except AIError as e:
    return f"⚠️ {e}", ""


# --- VIN ---
_VIN_VALUES = dict(zip("ABCDEFGHJKLMNPRSTUVWXYZ", [1, 2, 3, 4, 5, 6, 7, 8, 1, 2, 3, 4, 5, 7, 9, 2, 3, 4, 5, 6, 7, 8, 9]))
_VIN_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]


def vin_check_digit_ok(vin: str) -> bool:
  total = sum((int(c) if c.isdigit() else _VIN_VALUES.get(c, 0)) * w for c, w in zip(vin, _VIN_WEIGHTS))
  r = total % 11
  return vin[8] == ("X" if r == 10 else str(r))


def scan_vin_barcode(img: Image.Image) -> str:
  """Door-jamb / registration barcodes (Code 39, DataMatrix, QR, PDF417). Tries several clean-ups of the photo."""
  gray = ImageOps.grayscale(img)
  big = gray.resize((gray.width * 2, gray.height * 2)) if max(gray.size) < 1600 else gray
  versions = [img, ImageEnhance.Contrast(gray).enhance(2.2), ImageEnhance.Sharpness(ImageEnhance.Contrast(big).enhance(2.5)).enhance(2.0),
              big.point(lambda p: 255 if p > 128 else 0)]
  for candidate in versions:
    try:
      found = zxingcpp.read_barcodes(candidate, try_rotate=True, try_downscale=True, try_invert=True)
    except Exception:
      continue
    for b in found:
      for m in re.finditer(r"[A-Z0-9]{17}", re.sub(r"[^A-Z0-9]", "", b.text.upper().replace("I", "1").replace("O", "0").replace("Q", "0"))):
        if VIN_RE.fullmatch(m.group(0)):
          return m.group(0)
  return ""


# Characters people (and OCR) mix up on VIN plates. VINs never use I, O or Q.
_CONFUSE = {"0": "DQOU", "1": "IL7T", "2": "Z", "5": "S", "6": "G", "8": "B3", "3": "8", "7": "1T", "9": "G",
            "D": "0", "Z": "2", "S": "5", "G": "6", "B": "8", "U": "V0", "V": "U", "T": "17"}


def clean_vin_text(s: str) -> list[str]:
  """Pull every 17-character VIN-looking string out of text, fixing letters that can't appear in a VIN."""
  t = s.upper().replace("O", "0").replace("Q", "0").replace("I", "1")
  t = re.sub(r"[\s\-\.\*]", "", t)
  return list(dict.fromkeys(m.group(0) for m in re.finditer(r"[A-HJ-NPR-Z0-9]{17}", t)))


def vin_fixes(v: str) -> list[str]:
  """If the check digit fails, try single-character swaps of look-alike characters that make it pass."""
  if vin_check_digit_ok(v):
    return [v]
  out = []
  for i, ch in enumerate(v):
    for alt in _CONFUSE.get(ch, ""):
      if alt in "IOQ":
        continue
      c = v[:i] + alt + v[i + 1:]
      if vin_check_digit_ok(c):
        out.append(c)
  return out


@st.cache_data(ttl=7 * 86400, show_spinner=False, max_entries=500)
def nhtsa_ok(vin: str) -> bool:
  """True when NHTSA decodes the VIN with no errors (error code 0)."""
  try:
    r = http().get(f"https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/{vin}?format=json", timeout=10)
    res = {i["Variable"]: i.get("Value") for i in r.json().get("Results", [])}
    return str(res.get("Error Code", "")).strip() == "0" and bool(res.get("Make"))
  except Exception:
    return False


VIN_READ_PROMPT = """You are reading a vehicle identification number (VIN) from a photo. It may be a door-jamb sticker, the dashboard plate seen through the windshield, an engine/frame stamping, a title, registration or insurance card, or a scan-tool screen.
Read the printed 17-character VIN exactly as printed, character by character. VINs never contain the letters I, O or Q.
Return JSON only: {"vins": ["<each 17-character VIN you can see, best reading first>"], "unsure_positions": [<1-based positions you are not sure about>], "where": "<where in the photo>"}.
If no VIN is visible return {"vins": [], "where": ""}."""


def _jpeg_b64(img: Image.Image, max_side: int) -> str:
  im = img.convert("RGB")
  im.thumbnail((max_side, max_side))
  b = io.BytesIO()
  im.save(b, format="JPEG", quality=90)
  return base64.b64encode(b.getvalue()).decode()


def _ai_vin_reads(img: Image.Image) -> dict:
  """Ask Gemini (and Claude, if its key is set) to read the printed VIN. Returns {model: [vins]}."""
  reads = {}
  try:
    raw = gemini([{"text": VIN_READ_PROMPT}, {"inline_data": {"mime_type": "image/jpeg", "data": _jpeg_b64(img, 2048)}}],
                 json_mode=True, timeout=40)
    reads["Gemini"] = [c for v in (json.loads(raw).get("vins") or []) for c in clean_vin_text(str(v))]
  except (AIError, ValueError, AttributeError):
    pass
  if has_claude():
    try:
      key = secret("ANTHROPIC_API_KEY")
      res = http().post(CLAUDE_URL, timeout=60, headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                        json={"model": secret("CLAUDE_MODEL") or CLAUDE_DEFAULT_MODEL, "max_tokens": 400, "messages": [{"role": "user", "content": [
                            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _jpeg_b64(img, 1568)}},
                            {"type": "text", "text": VIN_READ_PROMPT}]}]})
      if res.status_code == 200:
        txt = "".join(b.get("text", "") for b in res.json().get("content", []) if b.get("type") == "text")
        m = re.search(r"\{.*\}", txt, re.S)
        vins = json.loads(m.group(0)).get("vins", []) if m else []
        reads["Claude"] = [c for v in vins for c in clean_vin_text(str(v))]
      else:
        log_problem("ai", "VIN photo read (Claude)", f"HTTP {res.status_code}: {res.text[:200]}")
    except (requests.RequestException, ValueError, AttributeError) as e:
      log_problem("ai", "VIN photo read (Claude)", str(e))
  return reads


@st.cache_data(show_spinner=False, max_entries=50)
def find_vin(img_bytes: bytes) -> dict:
  """Read a VIN from a photo: barcode first, then the printed characters with AI, then verify.
  Returns {"vin", "method", "confidence": high|medium|low, "alts": [...], "note"}."""
  img = ImageOps.exif_transpose(Image.open(io.BytesIO(img_bytes)))
  bc = scan_vin_barcode(img)
  if bc and vin_check_digit_ok(bc):
    return {"vin": bc, "method": "barcode", "confidence": "high", "alts": [], "note": "Read from the barcode; check digit OK."}
  reads = _ai_vin_reads(img)
  if bc:
    reads["Barcode"] = [bc]
  # score every candidate (plus look-alike fixes that make the check digit pass)
  score, why = {}, {}
  for src, vins in reads.items():
    for rank, v in enumerate(vins[:3]):
      for c in [v] + [f for f in vin_fixes(v) if f != v]:
        pts = (3 if c == v else 1) - rank
        score[c] = score.get(c, 0) + pts
        why.setdefault(c, set()).add(src if c == v else f"{src} (corrected)")
  if not score:
    return {"vin": "", "method": "", "confidence": "low", "alts": [], "note": "No VIN found in the photo."}
  ranked = sorted(score, key=lambda c: -score[c])[:5]
  verified = []
  for c in ranked:
    ok_cd, ok_db = vin_check_digit_ok(c), nhtsa_ok(c)
    score[c] += (4 if ok_cd else 0) + (4 if ok_db else 0)
    if ok_cd and ok_db:
      verified.append(c)
  ranked.sort(key=lambda c: -score[c])
  best = ranked[0]
  agree = len([s_ for s_ in why[best] if "corrected" not in s_]) >= 2
  conf = "high" if best in verified and (agree or "Barcode" in why[best]) else "medium" if best in verified else "low"
  note = {"high": "Read by " + " + ".join(sorted(why[best])) + "; check digit and NHTSA decode OK.",
          "medium": "Check digit and NHTSA decode OK (read by " + ", ".join(sorted(why[best])) + "). Glance at it to be sure.",
          "low": "Couldn't fully verify this reading — compare it to the vehicle before using it."}[conf]
  alts = [c for c in ranked[1:4] if vin_check_digit_ok(c)]
  return {"vin": best, "method": " + ".join(sorted(why[best])), "confidence": conf, "alts": alts, "note": note}


@st.cache_data(show_spinner=False, max_entries=20)
def extract_customer(img_bytes: bytes) -> dict:
  img = ImageOps.exif_transpose(Image.open(io.BytesIO(img_bytes)))
  ask = ("Read this work order / invoice. Extract ONLY the customer name, address, phone number, email and odometer/mileage."
         " Return a JSON object with keys 'customer_name', 'address', 'phone', 'email', 'odometer' (empty string if missing).")
  try:
    return json.loads(gemini([{"text": ask}, img_part(img)], json_mode=True, timeout=25))
  except (AIError, ValueError):
    if not has_claude():
      raise
  # Gemini failed (quota, outage, bad answer): let Claude read it instead
  txt = claude(ask + " Reply with the JSON only.", max_tokens=400, timeout=60, image_b64=img_part(img)["inline_data"]["data"])
  m = re.search(r"\{.*\}", txt, re.S)
  if not m:
    raise ValueError("No customer details found in the AI's answer.")
  return json.loads(m.group(0))


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


# --- Vehicle-specific factory data from the open OBD database (github.com/OBDb) ---
OBDB_RAW = "https://raw.githubusercontent.com/OBDb/{repo}/{branch}/signalsets/v3/default.json"
OBDB_MAKE_NAMES = {"GMC": "GMC", "BMW": "BMW", "MINI": "MINI", "MERCEDES-BENZ": "Mercedes-Benz", "LAND ROVER": "Land-Rover"}
OBDB_SKIP_PATHS = {"Trips", "Seatbelts", "Lights", "Doors", "Clocks", "Details", "Stats", "DTCs", "ECU", "Cruise control"}
OBDB_UNITS = {
    "celsius": "C", "fahrenheit": "F", "kilopascal": "kPa", "psi": "psi", "bars": "bar", "volts": "V", "millivolts": "mV",
    "rpm": "rpm", "percent": "%", "degrees": "deg", "scalar": "", "unknown": "", "kilometersPerHour": "kph",
    "kilometers": "km", "miles": "mi", "offon": "onoff", "onoff": "onoff", "noyes": "yesno", "yesno": "yesno",
    "milliseconds": "ms", "seconds": "s", "minutes": "min", "hours": "h", "milliamps": "mA", "amps": "A",
    "gramsPerSecond": "gps", "newtonMeters": "Nm", "liters": "L", "hex": "hex", "metersPerSecondSquared": "m/s²",
    "gravity": "g", "ampereHours": "Ah", "kilowatts": "kW", "millimeters": "mm", "megaohms": "MΩ",
}


def _obdb_repo_candidates(make: str, model: str) -> list[str]:
  mk = OBDB_MAKE_NAMES.get(make.upper(), make.title().replace(" ", "-"))
  mdl = model.strip()
  cands = [mdl.replace(" ", "-"), mdl.split(" ")[0]]
  if mdl.split(" ")[0] in ("Silverado", "Sierra"):
    cands.append(mdl.split(" ")[0] + "-1500")
  return list(dict.fromkeys(f"{mk}-{c}" for c in cands if c))


def _year_ok(f: dict | None, year: int) -> bool:
  if not f or not year:
    return True
  if year in (f.get("years") or []):
    return True
  if "from" not in f and "to" not in f:
    return not f.get("years")
  return f.get("from", 0) <= year <= f.get("to", 9999)


@st.cache_data(ttl=86400, show_spinner=False, max_entries=200)
def obdb_signals(make: str, model: str, year: str) -> tuple[str, list[dict]]:
  """Download this exact model's factory data definitions (one small JSON file) and trim it for the scanner."""
  if not make or not model:
    return "", []
  y = int(year) if str(year).isdigit() else 0
  for repo in _obdb_repo_candidates(make, model):
    r = None
    for branch in ("main", "master"):
      try:
        r = http().get(OBDB_RAW.format(repo=repo, branch=branch), timeout=10)
      except requests.RequestException:
        r = None
      if r is not None and r.status_code == 200:
        break
    if r is None or r.status_code != 200:
      continue
    try:
      cmds = r.json().get("commands", [])
    except ValueError:
      continue
    out = []
    for c in cmds:
      hdr = str(c.get("hdr", "")).upper()
      if c.get("eax") or c.get("tst") or c.get("fcm1") or c.get("pri") or not re.fullmatch(r"[0-9A-F]{3}|DA[0-9A-F]{2}", hdr):
        continue
      if not _year_ok(c.get("filter"), y):
        continue
      svc, pid = next(iter(c.get("cmd", {}).items()), ("", ""))
      if svc in ("01", "02", "09") or not svc:
        continue
      for sig in c.get("signals", []):
        f = sig.get("fmt", {})
        if sig.get("path") in OBDB_SKIP_PATHS or not f.get("len") or f.get("len") > 32:
          continue
        out.append({
            "hdr": hdr, "rax": str(c.get("rax", "")).upper(), "req": f"{svc}{pid}".upper(),
            "bix": f.get("bix", 0), "len": f["len"], "mul": f.get("mul", 1), "div": f.get("div", 1), "add": f.get("add", 0),
            "sign": bool(f.get("sign")), "lsb": bool(f.get("blsb")), "unit": OBDB_UNITS.get(f.get("unit", ""), f.get("unit", "")),
            "min": f.get("min"), "max": f.get("max"), "nmin": f.get("nullmin"), "nmax": f.get("nullmax"),
            "map": {k: (v.get("description") or v.get("value")) if isinstance(v, dict) else v for k, v in f["map"].items()} if f.get("map") else None,
            "name": sig.get("name", sig.get("id", "")), "path": sig.get("path", ""),
        })
    if out:
      return repo, out
  return "", []


def make_profile() -> str:
  return MAKE_PROFILES.get(ss.vehicle_make, "GENERIC")


# --- EMAIL & TEXT (optional; needs the setup in Secrets) ---
def email_ready() -> bool:
  return bool(secret("SMTP_USER") and secret("SMTP_PASSWORD"))


def send_report_email(to: str, subject: str, body: str, html: str, filename: str) -> str:
  """Send the report as an email attachment. Returns '' on success, or the error text."""
  import smtplib
  from email.message import EmailMessage
  msg = EmailMessage()
  shop = secret("SHOP_NAME") or "Your repair shop"
  msg["Subject"], msg["From"], msg["To"] = subject, f"{shop} <{secret('SMTP_USER')}>", to
  msg.set_content(body or "Your diagnostic report is attached. Open it on a phone or computer.")
  msg.add_attachment(html.encode("utf-8"), maintype="text", subtype="html", filename=filename)
  try:
    with smtplib.SMTP_SSL(secret("SMTP_HOST") or "smtp.gmail.com", int(secret("SMTP_PORT") or "465"), timeout=20) as srv:
      srv.login(secret("SMTP_USER"), secret("SMTP_PASSWORD"))
      srv.send_message(msg)
    return ""
  except Exception as e:
    log_problem("email", "Send report email", str(e))
    return str(e)


def sms_ready() -> bool:
  return bool(secret("TWILIO_SID") and secret("TWILIO_TOKEN") and secret("TWILIO_FROM"))


def send_sms(to: str, body: str) -> str:
  """Text the customer via Twilio. Returns '' on success, or the error text."""
  digits = re.sub(r"\D", "", to or "")
  if len(digits) == 10:
    digits = "1" + digits
  if len(digits) < 11:
    return "That phone number doesn't look complete."
  sid = secret("TWILIO_SID")
  try:
    r = http().post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                    auth=(sid, secret("TWILIO_TOKEN")),
                    data={"From": secret("TWILIO_FROM"), "To": "+" + digits, "Body": body[:1500]}, timeout=15)
  except requests.RequestException as e:
    log_problem("sms", "Send text", str(e))
    return str(e)
  if r.status_code >= 300:
    log_problem("sms", "Send text", f"HTTP {r.status_code}: {r.text[:200]}")
    return f"HTTP {r.status_code}: {r.text[:200]}"
  return ""


def record_sent(how: str, to: str, what: str):
  store_put("sent", datetime.now().strftime("%Y%m%d%H%M%S%f"),
            {"how": how, "to": to, "what": what, "job": ss.get("job_id"), "vehicle": ss.vehicle_info,
             "tech": ss.get("tech_user") or "", "at": datetime.now().strftime("%Y-%m-%d %I:%M %p")}, local_copy=False)


# --- JOB PHOTOS & WAVEFORM LIBRARY ---
def shrink_to_b64(data: bytes, max_side: int = 1200, quality: int = 80) -> str:
  img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
  img.thumbnail((max_side, max_side))
  b = io.BytesIO()
  img.save(b, format="JPEG", quality=quality)
  return base64.b64encode(b.getvalue()).decode()


def job_photos() -> list[dict]:
  if not ss.get("job_id"):
    return []
  return [dict(r.get("data") or {}, _id=r["id"]) for r in store_list("jobphoto", 12, {"job": ss.job_id})]


# ========================================================
# --- SCOPE DATA FILES: read a scope's CSV export and MEASURE it (no guessing from a photo) ---
# ========================================================

WAVE_TYPES = {
    "volts": "Voltage signal (general)",
    "sec_ign": "Secondary ignition (kV)",
    "pri_ign": "Primary ignition (coil −, volts)",
    "coil_amp": "Ignition coil current (amps)",
    "inj_v": "Injector voltage (low side)",
    "inj_amp": "Injector current (amps)",
    "crank_sig": "Crank / cam sensor signal",
    "rel_comp": "Relative compression (starter current, cranking)",
    "px_cyl": "Pressure transducer — in cylinder",
    "px_intake": "Pressure transducer — intake / vacuum",
    "px_exhaust": "Pressure transducer — exhaust / tailpipe",
}
WAVE_UNITS = {"sec_ign": "kV", "pri_ign": "V", "coil_amp": "A", "inj_v": "V", "inj_amp": "A", "crank_sig": "V",
              "rel_comp": "A", "px_cyl": "psi", "px_intake": "inHg/psi", "px_exhaust": "psi", "volts": "V"}
_TIME_SCALE = {"s": 1.0, "sec": 1.0, "ms": 1e-3, "us": 1e-6, "µs": 1e-6, "μs": 1e-6, "ns": 1e-9}


def _num(tok: str) -> float:
  t = tok.strip().strip('"').replace("∞", "inf").replace("−", "-")
  if t in ("", "-", "NaN", "nan"):
    return np.nan
  if t in ("inf", "+inf", "-inf"):
    return np.nan   # PicoScope writes ∞ when a channel goes off scale
  return float(t)


def _is_num_row(fields: list[str]) -> bool:
  ok = 0
  for f in fields:
    try:
      _num(f)
      ok += 1
    except ValueError:
      return False
  return ok >= 1


def parse_scope_csv(raw: bytes) -> dict:
  """Read the CSV a scope saves (PicoScope, Hantek, Owon, Autel/Snap-on exports...).
  Returns {"t": seconds array, "chans": [{"name", "unit", "y"}], "dt": sample spacing (s), "n": samples}."""
  if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
    text = raw.decode("utf-16", errors="replace")
  else:
    text = raw.decode("utf-8-sig", errors="replace")
  lines = [ln.strip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
  sample = [ln for ln in lines if ln][:80]
  def split(ln, delim):
    parts = [p.strip() for p in ln.split(delim)]
    if delim != ",":   # ; or tab files often write 1,23 for 1.23
      parts = [p.replace(",", ".") for p in parts]
    while parts and parts[-1] == "":
      parts.pop()
    return parts
  def find_start(rows):   # first line of real data = 3 numeric rows in a row, same width
    for i in range(len(rows) - 3):
      w = len(rows[i])
      if w >= 1 and all(len(rows[i + k]) == w and _is_num_row(rows[i + k]) for k in range(3)):
        return i
    return None
  # try the separators in a sensible order; use the first one that gives clean numeric rows with the most columns
  start, rows, best_w = None, None, 0
  for delim in [d for d in (";", "\t", ",") if any(d in ln for ln in sample)] or [","]:
    rr = [split(ln, delim) for ln in lines[:4000]]
    st0 = find_start(rr)
    if st0 is not None and len(rr[st0]) > best_w:
      best_w, start, chosen = len(rr[st0]), st0, delim
  if start is not None:
    rows = [split(ln, chosen) for ln in lines]
  if start is None:
    raise ValueError("Couldn't find the data rows in this file. Save the capture from your scope as CSV (text), not as its own format.")
  width = len(rows[start])
  # header: names + units from the lines just above the data
  names, units, meta = [""] * width, [""] * width, {}
  for ln in rows[:start]:
    if len(ln) == 2 and not _is_num_row(ln[:1]):
      meta[ln[0].lower()] = ln[1]
  for ln in rows[max(0, start - 4):start]:
    if len(ln) != width or _is_num_row(ln):
      continue
    if all(re.fullmatch(r"\(?\[?\s*[^\w]?\w{0,4}\s*\]?\)?", c or "") for c in ln) and any("(" in c or "[" in c for c in ln):
      units = [re.sub(r"[()\[\]\s]", "", c) for c in ln]   # PicoScope's second line: (ms),(V),(V)
    else:
      names = ln
  for k, nm in enumerate(names):   # "Time (ms)" / "CH1[V]" style
    m = re.search(r"[(\[]\s*([^)\]]+?)\s*[)\]]", nm or "")
    if m and not units[k]:
      units[k] = m.group(1)
    names[k] = re.sub(r"\s*[(\[][^)\]]*[)\]]", "", nm or "").strip()
  data = None
  try:
    import pandas as pd
    body = "\n".join(lines[start:])
    df = pd.read_csv(io.StringIO(body), sep=chosen, header=None, decimal="," if chosen != "," else ".",
                     na_values=["∞", "-∞", "+∞", "inf", "-inf", "NaN", ""], keep_default_na=True, engine="c")
    df = df.iloc[:, :width].apply(pd.to_numeric, errors="coerce")
    if df.shape[1] == width and len(df) >= 20:
      data = df.to_numpy(dtype=float)
  except Exception:
    data = None
  if data is None:
    data = np.array([[_num(v) for v in r] for r in rows[start:] if len(r) == width and _is_num_row(r)], dtype=float)
  if len(data) < 20:
    raise ValueError("The file has too few samples to measure.")
  first_is_time = bool(re.search(r"time|^t$|sec", (names[0] or "").lower())) or units[0].lower() in _TIME_SCALE
  if width >= 2 and (first_is_time or np.all(np.diff(data[: min(200, len(data)), 0]) > 0)):
    tu = units[0].lower().replace("μ", "µ") if units[0] else ""
    scale = _TIME_SCALE.get(tu)
    if scale is None:
      span = np.nanmax(data[:, 0]) - np.nanmin(data[:, 0])
      scale = 1.0 if span < 20 else 1e-3   # no unit given: seconds, unless that would be an absurdly long capture
    t = data[:, 0] * scale
    cols = list(range(1, width))
  else:   # value-only export: needs the sample interval from the header
    iv = next((v for k, v in meta.items() if "interval" in k or "sample period" in k), None)
    rate = next((v for k, v in meta.items() if "sample rate" in k or "samplerate" in k), None)
    try:
      dt = _num(re.sub(r"[^0-9eE.+-]", "", iv)) if iv else 1.0 / _num(re.sub(r"[^0-9eE.+-]", "", rate))
    except (ValueError, TypeError, ZeroDivisionError):
      raise ValueError("This file has values but no time column or sample rate, so it can't be measured. "
                       "Export with the time column included.")
    t = np.arange(len(data)) * dt
    cols = list(range(width))
  chans = []
  for c in cols:
    y = data[:, c].copy()
    u = (units[c] or "").strip()
    if u.lower() == "mv":
      y, u = y / 1000.0, "V"
    elif u.lower() == "ma":
      y, u = y / 1000.0, "A"
    nm = names[c] or f"Channel {chr(64 + c) if cols[0] == 1 else c + 1}"
    if np.isfinite(y).sum() >= 20:
      chans.append({"name": nm, "unit": u or "V", "y": y})
  if not chans:
    raise ValueError("No usable channels in this file.")
  dt = float(np.nanmedian(np.diff(t)))
  return {"t": t, "chans": chans, "dt": dt, "n": len(t)}


def envelope(t, y, n: int = 1200):
  """Shrink to ~n points but keep every spike (min and max of each slice) — a firing line must not vanish."""
  if len(t) <= n:
    return t, y
  k = int(np.ceil(len(t) / (n / 2)))
  m = len(t) // k * k
  tt, yy = t[:m].reshape(-1, k), y[:m].reshape(-1, k)
  with np.errstate(all="ignore"):
    i_min, i_max = np.nanargmin(np.where(np.isfinite(yy), yy, np.inf), axis=1), np.nanargmax(np.where(np.isfinite(yy), yy, -np.inf), axis=1)
  rows = np.arange(len(tt))
  first = np.minimum(i_min, i_max)
  second = np.maximum(i_min, i_max)
  t_out = np.column_stack([tt[rows, first], tt[rows, second]]).ravel()
  y_out = np.column_stack([yy[rows, first], yy[rows, second]]).ravel()
  return t_out, y_out


def guess_type(ch: dict) -> str:
  y, u = ch["y"], ch["unit"].lower()
  hi, lo = np.nanmax(y), np.nanmin(y)   # use the true extremes: a firing line or injector kick is only a few samples
  big = max(abs(hi), abs(lo))
  if u == "kv":
    return "sec_ign"
  if u == "a":
    return "rel_comp" if big > 40 else "coil_amp" if big > 3 else "inj_amp"
  if big > 1000:
    return "sec_ign"
  if big > 120:
    return "pri_ign"
  if 25 < hi < 120 and np.nanmedian(y) > 9:
    return "inj_v"
  return "volts"


# ---------- small helpers ----------
def _smooth(y, n):
  n = max(1, int(n))
  if n <= 1:
    return y
  k = np.ones(n) / n
  yy = np.where(np.isfinite(y), y, np.nanmedian(y))
  return np.convolve(yy, k, mode="same")


def _edges(y, hi, lo):
  """Indices where the signal goes up through `hi` (after having been below `lo`) — hysteresis, so noise can't double-count."""
  st_ = np.zeros(len(y), dtype=np.int8)
  with np.errstate(invalid="ignore"):
    st_[y > hi] = 1
    st_[y < lo] = -1
  idx = np.nonzero(st_)[0]
  if len(idx) < 2:
    return np.array([], dtype=int)
  v = st_[idx]
  return idx[np.nonzero((v[1:] == 1) & (v[:-1] == -1))[0] + 1]


def _peaks(y, height, min_gap):
  """Tallest point of each burst above `height`, at least `min_gap` samples apart."""
  above = np.where(np.isfinite(y) & (y > height))[0]
  if not len(above):
    return np.array([], dtype=int)
  groups, cur = [], [above[0]]
  for i in above[1:]:
    if i - cur[-1] <= max(2, min_gap // 4):
      cur.append(i)
    else:
      groups.append(cur)
      cur = [i]
  groups.append(cur)
  pk = [g[int(np.nanargmax(y[g]))] for g in groups]
  out = []
  for p in pk:
    if out and p - out[-1] < min_gap:
      if y[p] > y[out[-1]]:
        out[-1] = p
    else:
      out.append(p)
  return np.array(out, dtype=int)


def _stats(vals):
  v = np.array([x for x in vals if x is not None and np.isfinite(x)], dtype=float)
  if not len(v):
    return None
  return {"avg": float(np.mean(v)), "min": float(np.min(v)), "max": float(np.max(v)),
          "spread_pct": float((np.max(v) - np.min(v)) / abs(np.mean(v)) * 100) if np.mean(v) else 0.0}


def _r(x, d=2):
  return None if x is None or not np.isfinite(x) else round(float(x), d)


# ---------- per-type measurements ----------
def _general(t, y):
  ok = np.isfinite(y)
  yy = y[ok]
  hi, lo = float(np.percentile(yy, 99)), float(np.percentile(yy, 1))
  mid = (hi + lo) / 2
  e = _edges(y, mid + (hi - lo) * 0.1, mid - (hi - lo) * 0.1)
  per = float(np.median(np.diff(t[e]))) if len(e) >= 3 else None
  return {"min": _r(float(np.min(yy))), "max": _r(float(np.max(yy))), "average": _r(float(np.mean(yy))),
          "peak_to_peak": _r(hi - lo), "frequency_hz": _r(1 / per, 1) if per else None,
          "duty_cycle_pct": _r(float(np.mean(yy > mid) * 100), 1) if (hi - lo) > 0.2 else None}


def _sec_ign(t, y, dt):
  if abs(np.nanmin(y)) > abs(np.nanmax(y)):
    y = -y   # inverted probe or negative-fire coil
  peak = float(np.nanpercentile(y, 99.95))
  pk = _peaks(y, max(0.45 * peak, 2.5), int(0.004 / dt))   # firings at least 4 ms apart
  ev, notes = [], []
  for p in pk:
    w = int(0.0045 / dt)
    seg = y[p: p + w]
    if len(seg) < 10:
      continue
    s = next((i for i in range(1, len(seg)) if seg[i] < 0.35 * y[p]), None)
    if s is None:
      continue
    first = seg[s: s + max(3, int(0.0004 / dt))]
    level = float(np.median(first))
    if level <= 0.2:
      continue
    e = next((i for i in range(s + max(2, int(0.0002 / dt)), len(seg)) if seg[i] < 0.35 * level), None)
    if e is None:
      continue
    line = seg[s:e]
    slope = float(np.polyfit(np.arange(len(line)) * dt * 1000, line, 1)[0]) if len(line) > 5 else None
    after = seg[e: e + int(0.002 / dt)] - np.median(seg[-max(5, int(0.0005 / dt)):])
    osc = int(np.sum(np.diff(np.sign(after[np.abs(after) > 0.08 * level])) != 0) // 2) if len(after) > 5 else 0
    ev.append({"time_ms": _r(t[p] * 1000, 2), "firing_kv": _r(y[p], 1), "spark_line_kv": _r(level, 2),
               "burn_ms": _r((e - s) * dt * 1000, 2), "spark_slope_kv_per_ms": _r(slope, 2), "coil_oscillations": osc})
  m = {"events": len(ev)}
  if ev:
    for k in ("firing_kv", "spark_line_kv", "burn_ms", "coil_oscillations"):
      st_ = _stats([x[k] for x in ev])
      if st_:
        m[k] = _r(st_["avg"], 2)
        m[k + "_range"] = f"{_r(st_['min'], 2)}–{_r(st_['max'], 2)}"
    if len(ev) >= 2:
      m["firing_kv_spread_pct"] = _r(_stats([x["firing_kv"] for x in ev])["spread_pct"], 0)
    b, f = m.get("burn_ms"), m.get("firing_kv")
    if b is not None and b < 0.8:
      notes.append(f"Short burn time ({b} ms; ~1.0–2.0 ms is typical): the spark ran out of energy early — wide gap, lean, "
                   "high secondary resistance, or a weak coil.")
    if b is not None and b > 2.5:
      notes.append(f"Long burn time ({b} ms): low resistance in the spark path — fouled/shorted plug, rich mixture, or low compression.")
    if f is not None and f > 20:
      notes.append(f"High firing voltage ({f} kV): big gap, open/high-resistance plug wire or boot, lean, or high cylinder pressure.")
    if f is not None and f < 4:
      notes.append(f"Low firing voltage ({f} kV): fouled plug, narrow gap, rich, low compression — or a secondary leak to ground.")
    sl = m.get("spark_line_kv")
    sl_slope = _stats([x["spark_slope_kv_per_ms"] for x in ev])
    if sl_slope and sl_slope["avg"] > 1.0:
      notes.append("Spark line slopes UP: resistance rising during the burn — lean cylinder or high-resistance secondary.")
    if m.get("firing_kv_spread_pct") and m["firing_kv_spread_pct"] > 35:
      notes.append(f"Firing voltage varies {m['firing_kv_spread_pct']}% between events — compare cylinders, or look for an intermittent fault.")
    if sl is not None and sl > 4:
      notes.append(f"High spark line ({sl} kV): high resistance in the secondary or a lean cylinder.")
  return m, ev, notes


def _pri_ign(t, y, dt):
  peak = float(np.nanpercentile(y, 99.95))
  pk = _peaks(y, max(0.5 * peak, 80), int(0.004 / dt))
  ev, notes = [], []
  for p in pk:
    back = y[max(0, p - int(0.012 / dt)): p][::-1]
    d = 0
    while d < len(back) and back[d] < 2.5:
      d += 1
    seg = y[p: p + int(0.004 / dt)]
    s = next((i for i in range(1, len(seg)) if seg[i] < 0.5 * y[p]), None)
    burn = None
    if s is not None:
      level = float(np.median(seg[s: s + max(3, int(0.0003 / dt))]))
      e = next((i for i in range(s + 2, len(seg)) if seg[i] < 0.6 * level), None)
      burn = (e - s) * dt * 1000 if e else None
    ev.append({"time_ms": _r(t[p] * 1000, 2), "peak_v": _r(y[p], 0), "dwell_ms": _r(d * dt * 1000, 2) if d > 2 else None,
               "burn_ms": _r(burn, 2)})
  m = {"events": len(ev)}
  for k in ("peak_v", "dwell_ms", "burn_ms"):
    st_ = _stats([x[k] for x in ev])
    if st_:
      m[k] = _r(st_["avg"], 2)
  if m.get("peak_v") and m["peak_v"] < 200:
    notes.append(f"Low primary inductive peak ({m['peak_v']} V; 250–400 V is common): weak coil, low current, or a primary circuit problem.")
  if m.get("dwell_ms") and m["dwell_ms"] < 1.0:
    notes.append(f"Very short dwell ({m['dwell_ms']} ms): the coil may not be reaching full current.")
  return m, ev, notes


def _ramp_events(t, y, dt, min_gap_s):
  peak = float(np.nanpercentile(y, 99.9))
  pk = _peaks(y, 0.5 * peak, int(min_gap_s / dt))
  out = []
  for p in pk:
    back = y[max(0, p - int(0.02 / dt)): p + 1][::-1]
    start = next((i for i in range(len(back)) if back[i] < 0.08 * y[p]), len(back) - 1)
    out.append((p, p - start))
  return out


def _coil_amp(t, y, dt):
  ev, notes = [], []
  for p, s in _ramp_events(t, y, dt, 0.004):
    seg = y[s: p + 1]
    top = seg[seg > 0.9 * y[p]]
    ev.append({"time_ms": _r(t[p] * 1000, 2), "peak_a": _r(y[p], 2), "ramp_ms": _r((p - s) * dt * 1000, 2),
               "current_limited": bool(len(top) * dt > 0.0003)})
  m = {"events": len(ev)}
  for k in ("peak_a", "ramp_ms"):
    st_ = _stats([x[k] for x in ev])
    if st_:
      m[k] = _r(st_["avg"], 2)
      m[k + "_spread_pct"] = _r(st_["spread_pct"], 0)
  if m.get("peak_a_spread_pct", 0) > 20:
    notes.append(f"Peak coil current varies {m['peak_a_spread_pct']}% — if this is several coils, the low or fast-ramping one is suspect.")
  return m, ev, notes


def _inj_v(t, y, dt):
  supply = float(np.nanpercentile(y, 60))
  lo_thr = min(3.0, supply * 0.3)
  ev, notes = [], []
  down = _edges(-y, -lo_thr, -(supply * 0.7))   # falling through the low threshold = driver turns on
  for d in down:
    k = d
    while k < len(y) and y[k] < supply * 0.7:
      k += 1
    if k >= len(y):
      break
    seg = y[k: k + int(0.003 / dt)]
    kick = float(np.nanmax(seg)) if len(seg) else None
    kick_i = int(np.nanargmax(seg)) if len(seg) else 0
    tail = seg[kick_i:]
    settle = next((i for i in range(len(tail)) if tail[i] < supply + 1.0), None)
    bump = False
    if settle is not None and settle + 5 < len(tail):
      rest = tail[settle: settle + int(0.0015 / dt)] - supply
      bump = bool(len(rest) > 5 and np.nanmax(_smooth(rest, max(1, int(0.00005 / dt)))) > 0.35)
    ev.append({"time_ms": _r(t[d] * 1000, 2), "pulse_width_ms": _r((k - d) * dt * 1000, 2), "kick_v": _r(kick, 1),
               "pintle_bump": bump})
  m = {"events": len(ev), "supply_v": _r(supply, 2)}
  for k in ("pulse_width_ms", "kick_v"):
    st_ = _stats([x[k] for x in ev])
    if st_:
      m[k] = _r(st_["avg"], 2)
      m[k + "_spread_pct"] = _r(st_["spread_pct"], 0)
  if ev:
    m["pintle_bump_seen"] = f"{sum(x['pintle_bump'] for x in ev)} of {len(ev)}"
  if m.get("kick_v") is not None and m["kick_v"] < 35:
    notes.append(f"Low inductive kick ({m['kick_v']} V; port injectors usually spike ~45–80 V): shorted injector winding or a "
                 "clamped/suppressed driver — compare with a known-good injector on this engine.")
  if ev and sum(x["pintle_bump"] for x in ev) == 0 and dt < 0.00005:
    notes.append("No pintle bump found after the kick: possible sticking injector — compare with the other injectors "
                 "(some designs and slow sample rates won't show it).")
  if m.get("supply_v") is not None and m["supply_v"] < 11.5:
    notes.append(f"Injector supply only {m['supply_v']} V while off: check the feed circuit and fuse for voltage drop.")
  return m, ev, notes


def _inj_amp(t, y, dt):
  ev, notes = [], []
  for p, s in _ramp_events(t, y, dt, 0.004):
    seg = _smooth(y[s: p + 1], max(1, int(0.00004 / dt)))
    hook = None
    if len(seg) > 20:
      dy = np.diff(seg)
      body = dy[int(len(dy) * 0.15): int(len(dy) * 0.95)]
      if len(body) and np.min(body) < 0.15 * np.max(dy):
        hook = (int(np.argmin(body)) + int(len(dy) * 0.15)) * dt * 1000
    ev.append({"time_ms": _r(t[p] * 1000, 2), "peak_a": _r(y[p], 2), "ramp_ms": _r((p - s) * dt * 1000, 2),
               "pintle_hook_ms": _r(hook, 2)})
  m = {"events": len(ev)}
  for k in ("peak_a", "ramp_ms", "pintle_hook_ms"):
    st_ = _stats([x[k] for x in ev])
    if st_:
      m[k] = _r(st_["avg"], 2)
      m[k + "_spread_pct"] = _r(st_["spread_pct"], 0)
  if ev and not any(x["pintle_hook_ms"] for x in ev):
    notes.append("No pintle 'hook' (dip in the current ramp) found — the injector may not be opening cleanly; "
                 "compare against a known-good injector.")
  return m, ev, notes


def _crank_sig(t, y, dt):
  hi, lo = float(np.nanpercentile(y, 98)), float(np.nanpercentile(y, 2))
  mid, h = (hi + lo) / 2, (hi - lo) * 0.15
  e = _edges(y, mid + h, mid - h)
  m, notes, ev = {"amplitude_pp": _r(hi - lo), "low_level_v": _r(lo), "high_level_v": _r(hi)}, [], []
  if len(e) < 6:
    m["teeth_seen"] = int(len(e))
    notes.append("Too few teeth in this capture to analyze the pattern — capture at least one full revolution.")
    return m, ev, notes
  iv = np.diff(t[e])
  # local reference = median of the neighbors, so normal speed changes while cranking don't count as defects
  ref = np.array([np.median(iv[max(0, i - 6): i + 7]) for i in range(len(iv))])
  ratio = iv / ref
  gaps = np.where(ratio > 1.6)[0]
  odd = np.where((np.abs(ratio - 1) > 0.18) & (ratio <= 1.6))[0]
  m["teeth_seen"] = int(len(e))
  m["frequency_hz"] = _r(1 / float(np.median(iv)), 1)
  if len(gaps):
    missing = int(round(float(np.median(ratio[gaps]))) - 1)
    m["missing_teeth_at_gap"] = missing
    if len(gaps) >= 2:
      between = np.diff(gaps)
      teeth = int(np.median(between))
      m["pattern"] = f"{teeth + missing}-{missing}"
      rev_s = float(np.median([t[e[gaps[i + 1]]] - t[e[gaps[i]]] for i in range(len(gaps) - 1)]))
      m["rpm_from_wheel"] = _r(60 / rev_s, 0) if rev_s > 0 else None
  m["irregular_intervals"] = int(len(odd))
  if len(odd):
    m["irregular_tooth_times_ms"] = ", ".join(str(_r(t[e[i]] * 1000, 1)) for i in odd[:8])
    repeats = False
    if len(gaps) >= 2 and len(odd) >= 2:
      # position of each odd tooth counted from the gap before it: same count every turn = the same physical tooth
      pos = [int(i - gaps[gaps < i].max()) for i in odd if np.any(gaps < i)]
      repeats = len(pos) >= 2 and len(set(pos)) <= max(1, len(pos) // 3)
    if repeats:
      m["odd_tooth_repeats_every_rev"] = True
      notes.append(f"An odd tooth interval repeats at the SAME tooth every revolution ({len(odd)} times) → a physical problem on "
                   "the reluctor/tone wheel (damaged, bent or chipped tooth, debris), not wiring. Inspect the wheel.")
    else:
      notes.append(f"{len(odd)} tooth interval(s) more than 18% off their neighbors at random spots → more like a dropout: "
                   "wiring/connector, air gap, or electrical noise. Wiggle-test the harness while watching.")
  if lo > 0.8 and hi < 15:
    notes.append(f"Signal never goes fully low (lowest {_r(lo)} V): bad sensor ground, pull-down problem, or a shorted sensor output.")
  if abs(np.nanpercentile(y, 2)) > 0.5 and np.nanpercentile(y, 2) < 0 < np.nanpercentile(y, 98):
    m["signal_kind"] = "AC (magnetic / variable reluctance)"
    if hi - lo < 0.5:
      notes.append(f"Weak AC signal ({_r(hi - lo)} V peak-to-peak): check air gap, the reluctor, and the sensor itself "
                   "(amplitude rises with speed — compare at the same RPM).")
  else:
    m["signal_kind"] = "Digital (square wave)"
  return m, ev, notes


def _rel_comp(t, y, dt, cyl):
  ys = _smooth(y, max(1, int(0.004 / dt)))
  steady = ys[int(len(ys) * 0.15):]   # skip the starter's inrush at the start of the crank
  off = int(len(ys) * 0.15)
  base, top = float(np.nanpercentile(steady, 20)), float(np.nanpercentile(steady, 98))
  pk = _peaks(ys, base + (top - base) * 0.45, int(0.03 / dt))
  pk = pk[pk >= off]
  m, notes, ev = {}, [], []
  if len(pk) < 4:
    notes.append("Couldn't find enough compression humps. Disable fuel/ignition, clamp the starter cable, and crank 4–5 s.")
    return {"humps": int(len(pk))}, ev, notes
  amps = ys[pk] - base
  avg = float(np.mean(amps))
  for i, p in enumerate(pk):
    ev.append({"hump": i + 1, "time_ms": _r(t[p] * 1000, 1), "peak_a": _r(ys[p], 1), "relative_pct": _r(amps[i] / avg * 100, 0)})
  m["humps"] = len(pk)
  m["average_cranking_a"] = _r(float(np.nanmean(steady)), 0)
  per = float(np.median(np.diff(t[pk])))
  if cyl:
    m["cranking_rpm"] = _r(120 / (per * cyl), 0)
    m["cylinders"] = cyl
    # group humps into the same cylinder position each engine cycle
    pos = {}
    for i, a in enumerate(amps):
      pos.setdefault(i % cyl, []).append(a / avg * 100)
    m["relative_by_position_pct"] = {f"hump {k + 1} of {cyl}": _r(float(np.mean(v)), 0) for k, v in sorted(pos.items())}
    weakest = min(pos.items(), key=lambda kv: np.mean(kv[1]))
    if np.mean(weakest[1]) < 85:
      notes.append(f"Hump {weakest[0] + 1} of every {cyl} is only {_r(float(np.mean(weakest[1])), 0)}% of average — a low-compression "
                   "cylinder. Put a sync on cylinder 1's ignition (fuel disabled, spark on) to name it by firing order, then confirm with "
                   "a compression or leak-down test.")
  low = [x for x in ev if x["relative_pct"] is not None and x["relative_pct"] < 85]
  if low and not cyl:
    notes.append(f"{len(low)} hump(s) under 85% of average — possible low compression. Enter the cylinder count to group them.")
  if not low:
    notes.append("Humps are even (all within 15% of average) → no big compression difference between cylinders.")
  return m, ev, notes


def _px_cyl(t, y, dt):
  top = float(np.nanpercentile(y, 99.9))
  pk = _peaks(y, top * 0.55, int(0.02 / dt))
  m, ev, notes = {}, [], []
  if len(pk) < 2:
    notes.append("Capture at least two full engine cycles (two compression peaks) so the app can map crank degrees.")
    m["compression_peaks"] = int(len(pk))
    if len(pk):
      m["peak_pressure"] = _r(float(y[pk[0]]), 1)
    return m, ev, notes
  cyc = float(np.median(np.diff(t[pk])))   # one compression peak per 720° (4-stroke)
  m["engine_rpm_from_cycle"] = _r(120 / cyc, 0)
  peaks = y[pk]
  m["peak_pressure"] = _r(float(np.mean(peaks)), 1)
  m["peak_pressure_spread_pct"] = _r(float((peaks.max() - peaks.min()) / peaks.mean() * 100), 0)
  deg = 720.0 / cyc
  samples = []
  for a, b in zip(pk[:-1], pk[1:]):
    seg_t = (t[a:b] - t[a]) * deg   # 0° = compression TDC (the peak)
    seg_y = y[a:b]
    def at(lo_d, hi_d, fn):
      sel = (seg_t >= lo_d) & (seg_t < hi_d)
      return float(fn(seg_y[sel])) if np.any(sel) else np.nan
    samples.append({"exh_stroke_avg": at(200, 340, np.mean), "intake_stroke_min": at(380, 520, np.min),
                    "overlap_tdc": at(350, 370, np.mean), "bdc_power": at(170, 190, np.mean)})
  for k in ("exh_stroke_avg", "intake_stroke_min", "overlap_tdc", "bdc_power"):
    v = np.nanmean([s[k] for s in samples])
    m[k] = _r(float(v), 2)
  for i, p in enumerate(pk):
    ev.append({"cycle": i + 1, "time_ms": _r(t[p] * 1000, 1), "peak": _r(float(y[p]), 1)})
  notes.append("Degrees are measured from the compression peak (= TDC) assuming a 4-stroke 720° cycle; for exact valve "
               "timing, add a cam/crank or ignition sync channel.")
  if m["peak_pressure_spread_pct"] and m["peak_pressure_spread_pct"] > 8:
    notes.append(f"Compression peaks vary {m['peak_pressure_spread_pct']}% cycle to cycle — leaking valve, sticking valve, or a ring problem.")
  return m, ev, notes


def _px_pulses(t, y, dt, cyl, kind):
  ys = _smooth(y, max(1, int(0.002 / dt)))
  base = float(np.nanmedian(ys))
  sig = -(ys - base) if kind == "px_intake" else (ys - base)
  top = float(np.nanpercentile(sig, 99))
  pk = _peaks(sig, top * 0.4, int(0.008 / dt))
  m, ev, notes = {"pulses": int(len(pk)), "average_level": _r(base, 2)}, [], []
  if len(pk) < 3:
    notes.append("Too few pulses to compare — capture at least two engine cycles.")
    return m, ev, notes
  amps = sig[pk]
  avg = float(np.mean(amps))
  for i, p in enumerate(pk):
    ev.append({"pulse": i + 1, "time_ms": _r(t[p] * 1000, 1), "relative_pct": _r(float(amps[i] / avg * 100), 0)})
  if cyl:
    pos = {}
    for i, a in enumerate(amps):
      pos.setdefault(i % cyl, []).append(a / avg * 100)
    m["relative_by_position_pct"] = {f"pulse {k + 1} of {cyl}": _r(float(np.mean(v)), 0) for k, v in sorted(pos.items())}
    weak = min(pos.items(), key=lambda kv: np.mean(kv[1]))
    if np.mean(weak[1]) < 80:
      what = "intake pulse (possible intake valve not opening fully / cam lobe)" if kind == "px_intake" else \
          "exhaust pulse (misfire, low compression, or an exhaust valve problem in that cylinder)"
      notes.append(f"Pulse {weak[0] + 1} of every {cyl} is weak ({_r(float(np.mean(weak[1])), 0)}% of average): {what}. "
                   "Add a cylinder 1 sync to name the cylinder by firing order.")
  m["pulse_spread_pct"] = _r(float((amps.max() - amps.min()) / avg * 100), 0)
  return m, ev, notes


def measure_channel(t, y, dt, wtype: str, cyl: int | None = None) -> dict:
  """Measure one channel as the given type. Returns {"type", "measurements", "events", "notes"}."""
  ok = np.isfinite(y)
  if ok.sum() < 20:
    return {"type": wtype, "measurements": {}, "events": [], "notes": ["Channel has no usable data (off scale?)."]}
  try:
    if wtype == "sec_ign":
      m, ev, notes = _sec_ign(t, y, dt)
    elif wtype == "pri_ign":
      m, ev, notes = _pri_ign(t, y, dt)
    elif wtype == "coil_amp":
      m, ev, notes = _coil_amp(t, y, dt)
    elif wtype == "inj_v":
      m, ev, notes = _inj_v(t, y, dt)
    elif wtype == "inj_amp":
      m, ev, notes = _inj_amp(t, y, dt)
    elif wtype == "crank_sig":
      m, ev, notes = _crank_sig(t, y, dt)
    elif wtype == "rel_comp":
      m, ev, notes = _rel_comp(t, y, dt, cyl)
    elif wtype == "px_cyl":
      m, ev, notes = _px_cyl(t, y, dt)
    elif wtype in ("px_intake", "px_exhaust"):
      m, ev, notes = _px_pulses(t, y, dt, cyl, wtype)
    else:
      m, ev, notes = {}, [], []
  except Exception as e:   # a measuring problem must never stop the rest of the analysis
    m, ev, notes = {}, [], [f"Couldn't measure this as {WAVE_TYPES.get(wtype, wtype)}: {e}"]
  gen = _general(t, y)
  for k, v in gen.items():
    m.setdefault(k, v)
  return {"type": wtype, "measurements": m, "events": ev, "notes": notes}


def capture_summary(cap: dict, setup: dict, results: list[dict]) -> str:
  """Compact text for the AI: the setup, every measurement and a small trace per channel."""
  lines = [f"SCOPE CAPTURE (raw data file, {cap['n']} samples, {(cap['t'][-1] - cap['t'][0]) * 1000:.1f} ms long, "
           f"sample interval {cap['dt'] * 1e6:.1f} µs)",
           f"Engine condition: {setup.get('condition') or 'not given'} · RPM: {setup.get('rpm') or 'not given'} · "
           f"Cylinders: {setup.get('cyl') or '?'} · Firing order: {setup.get('fo') or 'not given'}"]
  for ch, r, s in zip(cap["chans"], results, setup.get("chans", [])):
    lines.append(f"\n--- {ch['name']}: {WAVE_TYPES.get(r['type'], r['type'])}"
                 + (f", cylinder {s.get('cyl_no')}" if s.get("cyl_no") else "") + f" ({s.get('unit') or ch['unit']}) ---")
    lines.append("MEASURED: " + json.dumps(r["measurements"]))
    if r["events"]:
      lines.append(f"EVENTS (first 12 of {len(r['events'])}): " + json.dumps(r["events"][:12]))
    if r["notes"]:
      lines.append("APP FLAGS: " + " | ".join(r["notes"]))
    tt, yy = envelope(cap["t"], s.get("_y", ch["y"]), 160)
    lines.append("TRACE (ms:value, min/max per slice): " + " ".join(f"{a * 1000:.2f}:{b:.3g}" for a, b in zip(tt, yy) if np.isfinite(b)))
  return "\n".join(lines)


def name_cylinders(humps: list[dict], sync_ms: list[float], cyl: int, firing_order: str, sync_cyl: int) -> dict | None:
  """Relative compression + an ignition sync on one cylinder: the hump that lines up with that cylinder's spark is
  that cylinder (peak cranking current = compression TDC), and the humps after it follow the firing order."""
  fo = [int(x) for x in re.findall(r"\d+", firing_order or "")]
  if not humps or not sync_ms or not cyl or len(fo) != cyl or sync_cyl not in fo:
    return None
  ht = np.array([h["time_ms"] for h in humps], dtype=float)
  per = float(np.median(np.diff(ht))) if len(ht) > 2 else None
  if not per:
    return None
  anchor = None
  for s_ in sync_ms:
    j = int(np.argmin(np.abs(ht - s_)))
    if abs(ht[j] - s_) < 0.35 * per:
      anchor = j
      break
  if anchor is None:
    return None
  start = fo.index(sync_cyl)
  by = {}
  for j, h in enumerate(humps):
    c = fo[(start + (j - anchor)) % cyl]
    by.setdefault(c, []).append(h["relative_pct"])
  return {f"cyl {c}": _r(float(np.mean(v)), 0) for c, v in sorted(by.items())}


# --- RECALLS (NHTSA, free) ---
@st.cache_data(ttl=86400, show_spinner=False, max_entries=300)
def nhtsa_recalls(make: str, model: str, year: str) -> list[dict]:
  """Every recall for this year / make / model (not VIN-specific)."""
  if not (make and model and str(year).isdigit()):
    return []
  try:
    r = http().get("https://api.nhtsa.gov/recalls/recallsByVehicle",
                   params={"make": make, "model": model, "modelYear": str(year)}, timeout=10)
    r.raise_for_status()
    return r.json().get("results") or []
  except (requests.RequestException, ValueError):
    return []


def vehicle_recalls() -> list[dict]:
  vd = ss.vehicle_details or {}
  return nhtsa_recalls(str(vd.get("Make", "")), str(vd.get("Model", "")), str(vd.get("Model Year", "")))


# --- JOBS (each car in the shop is a job, saved automatically) ---
JOB_FIELDS = ["customer_name", "customer_phone", "customer_address", "vin_input", "active_vin", "vehicle_info", "vehicle_make",
              "vehicle_details", "sel_codes", "manual_dtc", "symptoms", "ble_dtcs", "scan_data", "test_results", "dtc_result",
              "scope_result", "chat_history", "tech_notes", "customer_summary", "fix_part", "fix_test", "fix_notes",
              "customer_email", "odometer", "estimate_rows", "follow_up_days", "follow_up_note", "follow_up_done",
              "wave_result"]


def job_snapshot() -> dict:
  d = {k: ss.get(k) for k in JOB_FIELDS}
  # photos stay out of storage (too big); the text of the chat is kept
  d["chat_history"] = [{"role": m.get("role"), "content": m.get("content"), "photos_n": len(m.get("photos") or []) or m.get("photos_n", 0)}
                       for m in (ss.get("chat_history") or [])][-40:]
  return d


def job_has_content(d: dict) -> bool:
  return any(d.get(k) for k in ("customer_name", "vehicle_info", "sel_codes", "manual_dtc", "symptoms"))


def job_codes(d: dict) -> str:
  codes = list(d.get("sel_codes") or [])
  codes += [c for c in re.split(r"[,\s;/]+", str(d.get("manual_dtc") or "").upper()) if DTC_RE.fullmatch(c) and c not in codes]
  return ", ".join(codes)


def autosave_job(force: bool = False):
  snap = job_snapshot()
  if not job_has_content(snap):
    return
  h = hashlib.md5(json.dumps(snap, sort_keys=True, default=str).encode()).hexdigest()
  if h == ss.get("_job_hash") and not force:
    return
  if not ss.get("job_id"):
    ss.job_id = "J" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + os.urandom(2).hex()
    ss.job_created = datetime.now().strftime("%Y-%m-%d %I:%M %p")
    ss.job_status = "open"
    st.query_params["job"] = ss.job_id
  snap.update(id=ss.job_id, status=ss.get("job_status") or "open", created=ss.get("job_created") or "",
              tech=ss.get("tech_user") or "",
              updated=datetime.now().strftime("%Y-%m-%d %I:%M %p"), codes=job_codes(snap))
  store_put("job", ss.job_id, snap)
  ss._job_hash = h


def load_job(jid: str) -> bool:
  rec = store_get("job", jid)
  if not rec:
    return False
  for k in JOB_FIELDS:
    ss[k] = rec.get(k) if rec.get(k) is not None else copy.deepcopy(DEFAULTS.get(k, ""))
  ss.job_id, ss.job_status, ss.job_created = jid, rec.get("status") or "open", rec.get("created") or ""
  ss.ble_ai, ss.vin_error = None, ""
  ss.job_n = ss.get("job_n", 0) + 1   # empties the photo boxes
  ss._job_hash = hashlib.md5(json.dumps(job_snapshot(), sort_keys=True, default=str).encode()).hexdigest()
  st.query_params["job"] = jid
  return True


def new_job():
  for k in JOB_FIELDS:
    ss[k] = copy.deepcopy(DEFAULTS.get(k, ""))
  ss.job_id, ss.job_status, ss.job_created, ss._job_hash = None, "open", "", None
  ss.ble_ai, ss.vin_error = None, ""
  ss.job_n = ss.get("job_n", 0) + 1
  if "job" in st.query_params:
    del st.query_params["job"]


# --- SHOP HISTORY: earlier visits + this shop's confirmed fixes, fed to the AI ---
def vin_history(vin: str) -> list[dict]:
  if not vin:
    return []
  fixes = {r["id"]: r.get("data") or {} for r in store_list("fix", 50, {"vin": vin})}
  out = []
  for r in store_list("job", 50, {"active_vin": vin}):
    if r["id"] == ss.get("job_id"):
      continue
    d = r.get("data") or {}
    f = fixes.get(r["id"]) or {}
    out.append({"date": d.get("created") or d.get("updated", ""), "miles": d.get("odometer", ""),
                "complaint": d.get("symptoms", ""), "codes": d.get("codes", ""),
                "fix": f.get("fix", ""), "proved by": f.get("confirmed_by", ""), "notes": d.get("tech_notes", "")})
  return out


def similar_fixes(limit: int = 8) -> list[dict]:
  vd = ss.vehicle_details or {}
  make, model = str(vd.get("Make", "")).upper(), str(vd.get("Model", "")).upper()
  if not (make and model):
    return []
  codes = set(current_codes())
  rows = [r.get("data") or {} for r in store_list("fix", 100, {"make": make, "model": model}) if r["id"] != ss.get("job_id")]
  rows.sort(key=lambda f: -len(codes & set(f.get("codes") or [])))   # same codes first
  return rows[:limit]


def shop_context() -> str:
  """This shop's own history for the AI prompts ('' if there is none)."""
  out = []
  try:
    visits = vin_history(ss.active_vin)
    if visits:
      out.append("EARLIER VISITS OF THIS SAME VEHICLE (VIN) TO THIS SHOP:")
      out += [f"- {v['date']}: codes {v['codes'] or 'none'}; complaint: {v['complaint'] or '-'}; "
              f"confirmed fix: {v['fix'] or 'not recorded'}" for v in visits[:5]]
    fixes = similar_fixes()
    if fixes:
      out.append("THIS SHOP'S CONFIRMED FIXES ON THE SAME MAKE/MODEL (real repairs that were proven; weigh them heavily but still test):")
      out += [f"- {f.get('vehicle', '')}: codes {', '.join(f.get('codes') or []) or 'none'}; "
              f"complaint: {(f.get('complaint') or '-')[:120]} -> FIXED BY {f.get('fix')} (proved by: {f.get('confirmed_by') or '-'})"
              for f in fixes]
    recalls = vehicle_recalls()
    if recalls:
      out.append(f"NHTSA RECALLS FOR THIS YEAR/MAKE/MODEL ({len(recalls)}; may or may not be done on this VIN):")
      out += [f"- {r.get('NHTSACampaignNumber', '')} {r.get('Component', '')}: {str(r.get('Summary', ''))[:220]}" for r in recalls[:6]]
  except Exception as e:   # history is a bonus; never block a diagnosis over it
    log_problem("storage", "Shop history for AI", str(e))
  return ("\n\n" + "\n".join(out)) if out else ""


def save_fix():
  vd = ss.vehicle_details or {}
  autosave_job(force=True)
  if not ss.get("job_id"):
    return False
  rec = {"date": datetime.now().strftime("%Y-%m-%d"), "job": ss.job_id, "vin": ss.active_vin, "vehicle": ss.vehicle_info,
         "make": str(vd.get("Make", "")).upper(), "model": str(vd.get("Model", "")).upper(), "year": str(vd.get("Model Year", "")),
         "engine": str(vd.get("Displacement (L)") or vd.get("Engine") or ""), "codes": current_codes(),
         "odometer": ss.odometer.strip(), "tech": ss.get("tech_user") or "",
         "complaint": ss.symptoms.strip(), "fix": ss.fix_part.strip(), "confirmed_by": ss.fix_test.strip(), "notes": ss.fix_notes.strip()}
  store_put("fix", ss.job_id, rec)
  return True


# --- LOG ---
def append_to_log(vin: str, vehicle: str, dtc: str, customer: str = "", phone: str = ""):
  row = dict(zip(LOG_COLUMNS, [datetime.now().strftime("%Y-%m-%d %I:%M %p"), customer or "N/A", phone or "N/A",
                               vin or "N/A", vehicle or "Unknown Vehicle", dtc or "N/A", ss.get("tech_user") or ""]))
  store_put("log", datetime.now().strftime("%Y%m%d%H%M%S%f"), row)


def load_log() -> list[dict]:
  return [{c: (r.get("data") or {}).get(c, "") for c in LOG_COLUMNS} for r in store_list("log", 500)]


def log_csv(rows: list[dict]) -> str:
  b = io.StringIO()
  w = csv.DictWriter(b, fieldnames=LOG_COLUMNS)
  w.writeheader()
  w.writerows(rows)
  return b.getvalue()


def next_step() -> str:
  """One line telling the tech where the job goes next — the same guided feel as a factory tool."""
  if not ss.vehicle_info:
    return "Tap <b>Connect &amp; Auto-Scan</b> on 📊 Scanner (fills everything in), or photo the VIN on 📷."
  if not current_codes() and not (ss.symptoms or "").strip() and not ss.scan_data:
    return "Connect the scanner on 📊 to read codes — or type codes/symptoms on 🔧 Diagnose."
  if not ss.dtc_result:
    return "Run the <b>Diagnostic Tree</b> on 🔧 Diagnose to get the test plan."
  if not (ss.fix_part or "").strip():
    return "Work the plan (scope + guided tests), then record the <b>confirmed fix</b> on 🔧 section 6."
  return "Send the report (🔧 section 5), then close the job under 🚗 Cars in the shop."


def context_bar():
  e = html_lib.escape
  has_dtc = bool(ss.active_dtc)
  dtc_style = ("background:rgba(239,68,68,.12);color:#F87171;border:1px solid rgba(239,68,68,.3)" if has_dtc
               else "background:rgba(16,185,129,.1);color:#34D399;border:1px solid rgba(16,185,129,.25)")
  job = "open job" if ss.get("job_id") else "not saved yet"
  st.markdown(
      f'<div class="tdg-bar">'
      f'<span class="pill">🚗 {e(ss.vehicle_info or "No vehicle")}</span>'
      f'<span class="pill" style="font-weight:500;color:#CBD5E1">👤 {e(ss.customer_name or "no customer")}'
      f'{(" · " + e(ss.odometer) + " mi") if (ss.odometer or "").strip() else ""}</span>'
      f'<span class="dtc" style="{dtc_style}">{e(ss.active_dtc or "no codes")}</span>'
      f'<span style="color:#64748B;font-size:.75rem">{job}</span>'
      f'<span class="tdg-next">▶ Next: {next_step()}</span>'
      f'</div>', unsafe_allow_html=True)


# ========================================================
# --- SHOP LOGIN (only when APP_PASSWORD is set in Streamlit Secrets) ---
# ========================================================
def shop_users() -> dict:
  """password -> name. APP_USERS = "Ricky:pass1, Joe:pass2" in Secrets; or the single APP_PASSWORD."""
  users = {}
  for part in (secret("APP_USERS") or "").split(","):
    if ":" in part:
      name, _, pw = part.strip().partition(":")
      if name.strip() and pw.strip():
        users[pw.strip()] = name.strip()
  if secret("APP_PASSWORD"):
    users.setdefault(secret("APP_PASSWORD"), "Shop")
  return users


def require_password():
  users = shop_users()
  if not users:
    return
  tokens = {hashlib.sha256(("tdg-login:" + pw).encode()).hexdigest()[:24]: name for pw, name in users.items()}
  seen = ss.get("_authed") or st.query_params.get("k")
  if seen in tokens:
    ss._authed = seen
    ss.tech_user = tokens[seen]
    if st.query_params.get("k") != seen:
      st.query_params["k"] = seen   # keeps this phone/computer logged in after a refresh (bookmark the page)
    return
  st.markdown("### 🔒 Shop login")
  with st.form("login"):
    entered = st.text_input("Password", type="password")
    if st.form_submit_button("Log in", type="primary"):
      match = next((pw for pw in users if hashlib.sha256(entered.encode()).digest() == hashlib.sha256(pw.encode()).digest()), None)
      if match:
        tok = hashlib.sha256(("tdg-login:" + match).encode()).hexdigest()[:24]
        ss._authed, ss.tech_user = tok, users[match]
        st.query_params["k"] = tok
        st.rerun()
      st.error("Wrong password.")
  st.stop()


require_password()

if ss.get("_seen_version") != APP_VERSION:
  ss._seen_version = APP_VERSION
  st.toast(f"✅ Running version {APP_VERSION} — see 🆕 What's new at the top")



# Legacy links from the old "Sync" button (?ble_vin=...&ble_dtc=...): use once, then clear
if "ble_vin" in st.query_params or "ble_dtc" in st.query_params:
  _qv = st.query_params.get("ble_vin", "").upper().strip()
  _qd = st.query_params.get("ble_dtc", "").upper().strip()
  for _qk in ("ble_vin", "ble_dtc"):
    if _qk in st.query_params:
      del st.query_params[_qk]
  _upd = {}
  if VIN_RE.fullmatch(_qv) and load_vehicle(_qv):
    _upd["vin_input"] = _qv
  if _qd:
    _upd["manual_dtc"] = _qd
  queue_update(**_upd)


# ========================================================
# --- CARS IN THE SHOP (open jobs) ---
# ========================================================
if (_jr := ss.pop("_job_request", None)) is not None:
  if _jr == "new":
    new_job()
  elif not load_job(_jr):
    ss._toast = "Couldn't open that job."
elif "job_id" not in ss:
  ss.job_id = None
  if _qj := st.query_params.get("job"):
    if not load_job(_qj):   # e.g. the link is from before permanent storage was set up
      del st.query_params["job"]
ss.active_dtc = ", ".join(current_codes())


def jobs_panel():
  jobs = store_list("job", 60, {"status": "open"})
  cur = ss.get("job_id")
  now_on = f" · now: {ss.vehicle_info or ss.customer_name or 'new car'}" if job_has_content(job_snapshot()) else ""
  with st.expander(f"🚗 Cars in the shop ({len(jobs)} open){now_on}", expanded=False):
    if not store_on():
      st.warning("⚠️ Permanent storage isn't set up yet, so jobs, the log and test drives are still erased when the app "
                 "restarts or you update it. Add SUPABASE_URL and SUPABASE_KEY to Streamlit Secrets to fix this.")
    elif ss.get("_store_err"):
      st.warning(f"⚠️ Last save had a problem: {ss._store_err} (details in 📋 Log → 🐞 Problem log)")
    st.caption("Every car is saved automatically as you work. Switch between cars here; refreshing the page keeps your place.")
    c1, c2 = st.columns(2)
    if c1.button("➕ Start a new car", use_container_width=True):
      ss._job_request = "new"
      st.rerun()
    if cur and c2.button("✅ Close this job (car is done)", use_container_width=True):
      ss.job_status = "closed"
      autosave_job(force=True)
      ss._job_request = "new"
      ss._toast = "Job closed"
      st.rerun()
    for r in jobs:
      d = r.get("data") or {}
      a, b = st.columns([5, 1])
      a.markdown(f"{'👉 ' if r['id'] == cur else ''}**{d.get('vehicle_info') or 'Vehicle not set'}** · {d.get('customer_name') or 'no name'}"
                 f" · {d.get('codes') or 'no codes'}  \n<small>Started {d.get('created', '')} · updated {d.get('updated', '')}</small>",
                 unsafe_allow_html=True)
      if r["id"] != cur and b.button("Open", key=f"open_{r['id']}", use_container_width=True):
        ss._job_request = r["id"]
        st.rerun()
    closed = store_list("job", 25, {"status": "closed"})
    if closed:
      pick = st.selectbox("Reopen a closed job", [r["id"] for r in closed], index=None, placeholder="Recently closed jobs…",
                          format_func=lambda i: next(f"{(r.get('data') or {}).get('updated', '')} · "
                                                     f"{(r.get('data') or {}).get('vehicle_info') or 'vehicle'} · "
                                                     f"{(r.get('data') or {}).get('customer_name') or 'no name'}"
                                                     for r in closed if r["id"] == i), key=f"reopen_{ss.get('job_n', 0)}")
      if pick and st.button("↩️ Reopen it"):
        rec = store_get("job", pick) or {}
        rec["status"] = "open"
        store_put("job", pick, rec)
        ss._job_request = pick
        st.rerun()


def setup_panel():
  checks = [
      ("🔑 Shop login", bool(shop_users())), ("💾 Permanent storage", store_on()),
      ("✨ Gemini (main AI)", bool(secret("GEMINI_API_KEY"))), ("🧠 Claude review", has_claude()),
      ("🐋 DeepSeek 2nd opinion", has_deepseek()), ("🌐 Perplexity research", bool(secret("PERPLEXITY_API_KEY"))),
      ("📧 Email reports", email_ready()), ("💬 Text customers", sms_ready()),
  ]
  on = sum(1 for _, ok in checks if ok)
  with st.expander(("⚙️" if on == len(checks) else "🟡") + f" Setup — {on}/{len(checks)} connected"):
    st.markdown("  \n".join(("✅ " if ok else "⬜ ") + n for n, ok in checks))
    if on < len(checks):
      st.caption("Turn one on by adding its key in **Manage app → Settings → Secrets**:  \n"
                 "login → APP_PASSWORD (or APP_USERS = \"Name:pass, Name2:pass2\")  \n"
                 "storage → SUPABASE_URL + SUPABASE_KEY  \n"
                 "AIs → GEMINI_API_KEY · ANTHROPIC_API_KEY · DEEPSEEK_API_KEY · PERPLEXITY_API_KEY  \n"
                 "email → SMTP_USER + SMTP_PASSWORD (Gmail app password)  \n"
                 "texting → TWILIO_SID + TWILIO_TOKEN + TWILIO_FROM")


with guard("Cars in the shop"):
  _topL, _topM, _topR = st.columns([2.4, 1.2, 1.2])
  with _topL:
    jobs_panel()
  with _topM:
    setup_panel()
  with _topR:
    with st.expander("🆕 What's new"):
      st.markdown("\n".join(f"- {w}" for w in WHATS_NEW))


tab1, tab2, tab3, tab5 = st.tabs([
    "📷 Vehicle & Customer",
    "📊 Scanner & Live Data",
    "🔧 Diagnose",
    "📋 Log & History",
])

# ========================================================
# --- TAB 1: VIN & CUSTOMER INFO ---
# ========================================================
with tab1, guard("VIN & Customer tab"):
  context_bar()
  st.markdown("#### 🚗 Vehicle")
  with st.expander("📸 Read the VIN from a photo", expanded=not ss.vehicle_details):
    st.caption("Tip: use **Take or upload photo** — on a phone it opens the full-resolution camera, which reads far better than "
             "the small in-app camera. Get close, fill the frame with the VIN, avoid glare. Works with the door sticker, "
             "windshield plate, registration/insurance card or a scan-tool screen. (Connecting the scanner reads the VIN "
             "straight from the car and needs no photo.)")
    col_up, col_cam = st.columns(2)
    with col_up:
      uploaded = st.file_uploader("📷 Take or upload photo of the VIN", type=["png", "jpg", "jpeg", "webp"],
                                  key=f"vin_upload_{ss.get('job_n', 0)}")
    with col_cam:
      photo = st.camera_input("In-app camera (lower resolution)") if st.toggle("Use in-app camera instead") else None

    active_image = uploaded or photo
    if active_image:
      img_bytes = active_image.getvalue()
      photo_id = hashlib.md5(img_bytes).hexdigest()
      try:
        st.image(img_bytes, caption="Photo", width=420)
      except Exception:
        pass

      read = {"vin": ""}
      try:
        with st.spinner("Reading the VIN (barcode + printed characters) and verifying it..."):
          read = find_vin(img_bytes)
      except Exception as e:   # unreadable image format etc.
        log_problem("vin", "VIN photo read", f"{type(e).__name__}: {e}")
        st.warning("Couldn't read that photo. Try a JPG/PNG, or type the VIN below.")

      found_vin = read.get("vin", "")
      if found_vin:
        icon = {"high": "✅", "medium": "🟡", "low": "⚠️"}[read["confidence"]]
        st.markdown(f"{icon} **{found_vin}**  \n<small>{read['note']}</small>", unsafe_allow_html=True)
        if ss.get("_applied_photo") != photo_id:  # apply each photo once so manual edits stick
          ss._applied_photo = photo_id
          load_vehicle(found_vin)
          queue_update(vin_input=found_vin)
        if read.get("alts"):
          st.caption("Not right? Other possible readings:")
          alt_cols = st.columns(len(read["alts"]))
          for col, alt in zip(alt_cols, read["alts"]):
            if col.button(alt, key=f"alt_{alt}"):
              load_vehicle(alt)
              queue_update(vin_input=alt, toast=f"Using {alt}")
      else:
        st.warning(read.get("note") or "Could not find a VIN. Try a closer, sharper photo, or type it below.")
      if (not found_vin or read.get("confidence") == "low") and st.button("🔁 Read this photo again"):
        getattr(find_vin, "clear", lambda: None)()
        ss._applied_photo = None
        st.rerun()

      if st.button("📄 Extract Customer Details from this Image"):
        try:
          with st.spinner("Extracting customer name, address, and phone..."):
            info = extract_customer(img_bytes)
        except (AIError, ValueError) as e:
          st.error(f"Couldn't read customer details: {e}")
        else:
          upd = {k: str(info.get(j, "")).strip() for k, j in
                 (("customer_name", "customer_name"), ("customer_address", "address"), ("customer_phone", "phone"),
                  ("customer_email", "email"), ("odometer", "odometer"))
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
    _mk = f"_{ss.get('job_n', 0)}"   # fresh boxes for each new car; model box resets when year/make change
    m1, m2, m3 = st.columns(3)
    man_year = m1.selectbox("Year", [str(y) for y in range(this_year + 1, 1980, -1)], index=None, placeholder="Year",
                            key=f"man_year{_mk}")
    man_make = m2.selectbox("Make", MANUAL_MAKES, index=None, placeholder="Make", key=f"man_make_sel{_mk}")
    if man_make == "Other...":
      man_make = m2.text_input("Type the make", key=f"man_make_other{_mk}").strip().title()
    model_list = models_for(man_make, int(man_year)) if man_year and man_make else []
    if model_list:
      man_model = m3.selectbox("Model", model_list, index=None, placeholder="Model",
                               key=f"man_model_sel{_mk}_{man_year}_{man_make}")
    else:
      man_model = m3.text_input("Model", key=f"man_model{_mk}_{man_year}_{man_make}", placeholder="e.g. Accord")
    m4, m5 = st.columns(2)
    man_trim = m4.text_input("Submodel / trim (optional)", key=f"man_trim{_mk}", placeholder="e.g. EX-L, LT, SR5")
    man_engine = m5.text_input("Engine size (optional)", key=f"man_engine{_mk}", placeholder="e.g. 2.4L, 5.3L V8")
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

    # 🕘 Has this exact car been here before?
    visits = vin_history(ss.active_vin)
    if visits:
      with st.expander(f"🕘 This car has been here before — {len(visits)} earlier visit(s)", expanded=True):
        st.dataframe(visits, use_container_width=True, hide_index=True)
        st.caption("The AI sees these visits and their confirmed fixes when it builds a test plan.")
    elif ss.active_vin:
      st.caption("🕘 First visit for this VIN.")

    # ⚠️ Recalls for this year / make / model
    recalls = vehicle_recalls()
    if recalls:
      with st.expander(f"⚠️ {len(recalls)} NHTSA recall(s) for the {ss.vehicle_details.get('Model Year', '')} "
                       f"{ss.vehicle_details.get('Make', '')} {ss.vehicle_details.get('Model', '')}"):
        st.caption("These cover every vehicle of this year/make/model. To see if THIS car's recalls are done, enter the VIN at "
                   "nhtsa.gov/recalls or the maker's site.")
        for r in recalls:
          st.markdown(f"**{r.get('Component', '')}** · campaign {r.get('NHTSACampaignNumber', '')} · {r.get('ReportReceivedDate', '')}  \n"
                      f"{r.get('Summary', '')}  \n_Fix: {r.get('Remedy', '')}_")
    elif ss.vehicle_details.get("Model"):
      st.caption("No NHTSA recalls found for this year/make/model.")

  st.write("---")
  st.markdown("#### 👤 Customer")
  col_c1, col_c2 = st.columns(2)
  with col_c1:
    st.text_input("Customer Name:", key="customer_name", placeholder="e.g. ROTAE LLC")
    st.text_input("Phone Number:", key="customer_phone", placeholder="e.g. 678-365-2146")
    st.text_input("Email (for sending the report):", key="customer_email", placeholder="e.g. name@gmail.com")
  with col_c2:
    st.text_area("Address:", key="customer_address", height=108,
                 placeholder="e.g. 6428 DAWSON BLVD, STE 1730, NORCROSS, GA, 30093")
    st.text_input("Odometer (miles):", key="odometer", placeholder="e.g. 163,420")
  st.caption("📄 Got a work order? Open 📸 Read the VIN from a photo above and tap "
             "\"Extract Customer Details from this Image\" — it fills all of this in.")

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
  #readBtn { background:var(--b); } #clearBtn { background:var(--r); color:#fff; } #aiBtn { background:var(--o); } #syncBtn { background:var(--v); color:#fff; } #modBtn { background:var(--b); }
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
  #testTabs button { padding:6px 10px; font-size:.8rem; background:var(--card); color:var(--w); border:1px solid var(--line); }
  #testTabs button.on { border-color:var(--y); color:var(--y); }
  .tbtn { padding:7px 12px; font-size:.82rem; background:var(--y); color:#0E1117; border:none; margin:4px 6px 4px 0; }
  .tbtn.sec { background:var(--card); color:var(--w); border:1px solid var(--line); }
  .ttab { width:100%; border-collapse:collapse; font-size:.85rem; margin:6px 0; }
  .ttab td, .ttab th { border-bottom:1px solid var(--line); padding:5px 6px; text-align:center; }
  .ttab th { color:var(--muted); font-weight:600; font-size:.75rem; text-transform:uppercase; }
  .grade-g { color:var(--g); font-weight:700; } .grade-y { color:var(--y); font-weight:700; } .grade-r { color:var(--r); font-weight:700; } .grade-n { color:var(--s); }
  .verdict { background:var(--bg); border-left:4px solid var(--y); padding:8px 10px; border-radius:4px; margin:8px 0; line-height:1.45; }
  .tsteps { color:var(--muted); font-size:.85rem; line-height:1.5; margin:4px 0 8px; }
  .tnum { font-size:1.6rem; font-weight:700; }
  canvas.tplot { width:100%; height:180px; display:block; background:var(--card); border:1px solid var(--line); border-radius:6px; }
  .tile.warn { border-color: var(--r) !important; animation: plpulse 1.2s ease-in-out infinite; }
  @keyframes plpulse { 0%,100% { box-shadow: 0 0 0 0 rgba(255,70,70,.0); } 50% { box-shadow: 0 0 8px 1px rgba(255,70,70,.55); } }
  #plausBox { display:none; margin:6px 0 10px; padding:8px 10px; border:1px solid var(--r); border-radius:6px; background:rgba(255,60,60,.07); font-size:.84rem; line-height:1.45; }
  #plausBox b { color: var(--r); }
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
<style>
/* ===== 2026 design pass: dark-glass override (keeps every rule above, restyles on top) ===== */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600;700&display=swap');
:root { --bg:#0E1420; --card:#141C2E; --line:rgba(255,255,255,.08); --muted:#8B9BB4; --g:#10B981; --t:#14B8A6; --w:#F1F5F9; }
body { color: var(--w); font-family: 'Inter', system-ui, -apple-system, sans-serif; -webkit-font-smoothing: antialiased; }
.wrap { background: linear-gradient(180deg,#121A2A 0%,#0C121D 100%); border: 1px solid rgba(255,255,255,.1); border-radius: 14px; padding: 16px;
  box-shadow: 0 20px 40px -15px rgba(0,0,0,.6), inset 0 1px 0 rgba(255,255,255,.05); }
button { font-family: 'Inter', system-ui, sans-serif; font-weight: 600; font-size: .82rem; border: 1px solid rgba(255,255,255,.1) !important;
  border-radius: 8px; background: #1A2333 !important; color: var(--w) !important; transition: all .15s ease;
  box-shadow: 0 2px 4px rgba(0,0,0,.25), inset 0 1px 0 rgba(255,255,255,.05); }
button:hover:not(:disabled) { background: #232F46 !important; border-color: rgba(255,255,255,.22) !important; transform: translateY(-1px); }
button:active:not(:disabled) { transform: translateY(0); }
button:disabled { background: rgba(255,255,255,.03) !important; color: #475569 !important; border-color: rgba(255,255,255,.04) !important;
  box-shadow: none; cursor: not-allowed; }
#bleBtn { background: linear-gradient(180deg,#10B981 0%,#059669 100%) !important; color: #052E16 !important; font-weight: 700;
  border: 1px solid #34D399 !important; box-shadow: 0 0 16px rgba(16,185,129,.25); }
#bleBtn:hover:not(:disabled) { filter: brightness(1.08); }
#aiBtn:not(:disabled) { background: rgba(245,158,11,.14) !important; color: #FBBF24 !important; border-color: rgba(245,158,11,.35) !important; }
#clearBtn:not(:disabled) { background: rgba(239,68,68,.12) !important; color: #FCA5A5 !important; border-color: rgba(239,68,68,.35) !important; }
select { background: #0F1623; color: var(--w); border: 1px solid rgba(255,255,255,.14); padding: 6px 9px; border-radius: 8px; font-weight: 600; }
#status { color: #94A3B8; font-family: 'JetBrains Mono', monospace; font-size: .78rem; background: #0A0F18;
  border: 1px solid var(--line); padding: 8px 12px; border-radius: 8px; }
h3 { font-size: .78rem; font-weight: 700; text-transform: uppercase; letter-spacing: .07em; }
.tile { background: linear-gradient(180deg, rgba(25,35,58,.75) 0%, rgba(15,22,36,.9) 100%); border: 1px solid var(--line);
  border-radius: 10px; text-align: left; padding: 9px 11px; box-shadow: inset 0 1px 0 rgba(255,255,255,.04);
  transition: transform .12s ease, border-color .12s ease; }
.tile:hover { border-color: rgba(255,255,255,.22); transform: translateY(-1px); }
.tile .l { font-size: .66rem; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .04em;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tile .v { font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; font-size: 1.12rem; font-weight: 700;
  letter-spacing: -.02em; }
.box, .chart { background: rgba(15,22,36,.85); border: 1px solid var(--line); border-radius: 10px; }
canvas.tplot { background: rgba(15,22,36,.85); border: 1px solid var(--line); border-radius: 10px; }
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
    <button id="evapBtn" disabled title="Commands the ECM to seal the EVAP system for a smoke test (Mode $08)">💨 Seal EVAP</button>
    <button id="aiBtn" disabled>🤖 AI Check</button>
    <button id="modBtn" disabled>🧭 Scan All Modules</button>
    <button id="syncBtn" disabled>📋 Send VIN &amp; Codes to App</button>
    <button id="dbgBtn" style="background:var(--card);color:var(--muted);border:1px solid var(--line)">🐞 Send debug info</button>
    <div class="oem">OEM Profile:
      <select id="oemSel">
        <option value="AUTO">Auto (this vehicle)</option><option value="HONDA">Honda / Acura</option>
        <option value="TOYOTA">Toyota / Lexus / Scion</option><option value="NISSAN">Nissan / Infiniti</option>
        <option value="HYUNDAI">Hyundai / Kia / Genesis</option><option value="SUBARU">Subaru</option>
        <option value="MAZDA">Mazda</option><option value="FORD">Ford / Lincoln / Mercury</option>
        <option value="GM">GM</option><option value="CHRYSLER">Chrysler / Dodge / Jeep / Ram</option>
        <option value="GENERIC">Generic (OBD-II only)</option>
      </select>
    </div>
  </div>
  <div id="status">Status: Ready. Key ON (or engine running), then tap Connect.</div>
  <div id="driveBanner">🚗 <strong>Test Drive ON:</strong> screen stays awake; guided tests run automatically (see 🎯 Guided Tests); spoken alerts for fuel trim, coolant temp and charging; AI check every 60 s.</div>

  <h3 style="color:var(--r)">🚨 FAULT CODES</h3>
  <div id="dtcBox" class="box">Codes are read automatically on connect.</div>
  <div id="clearWarn" class="box" style="display:none;border-color:var(--o);color:var(--o);font-weight:700"></div>
  <div id="ffBox" class="box" style="display:none"></div>
  <h3 style="color:var(--b)">🧭 ALL MODULES <span id="modNote" class="note">ABS, airbag, body, HVAC, cluster… scanned automatically after connect</span></h3>
  <div id="modBox" class="box">Not scanned yet.</div>

  <h3 style="color:var(--g)">📈 LIVE DATA (MODE 01) <span id="rate" class="note"></span></h3>
  <div id="plausBox"></div>
  <div id="graphs">
    <div class="gbar" id="gbar">📈 Tap any reading to graph it live (up to 4 at once).</div>
    <div id="charts"></div>
  </div>
  <div id="liveGrid" class="grid"></div>

  <h3 style="color:var(--y)">🎯 GUIDED TESTS <span class="note">fuel trim, VE, catalyst, charging, power &amp; braking</span></h3>
  <div id="tests" class="box" style="color:var(--w)">
    <div id="driveTests"></div>
    <div id="drivesBox"></div>
    <div class="bar" id="testTabs" style="margin-bottom:8px"></div>
    <div id="testBody"></div>
  </div>

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
  const changed = a.make !== ARGS.make || String(a.year) !== String(ARGS.year) || a.oem_src !== ARGS.oem_src;
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
const num = {};     // tile id -> numeric value (for alerts & tests)
const numT = {};    // tile id -> time of last update (s)
function setTile(id, text, n) {
  shown[id] = text;
  recordHist(id, text);
  if (n !== undefined) num[id] = n;
  else { const v = toNumber(text); if (v != null && isFinite(v)) num[id] = v; }
  numT[id] = performance.now() / 1000;
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
    if (pts.length > 1 && color.startsWith("rgb(")) {   // soft gradient under the trace, like a scope
      const grad = g.createLinearGradient(0, T, 0, T + ph);
      grad.addColorStop(0, color.replace("rgb(", "rgba(").replace(")", ", 0.18)"));
      grad.addColorStop(1, "rgba(0,0,0,0)");
      g.lineTo(X(pts[pts.length - 1][0]), T + ph); g.lineTo(X(pts[0][0]), T + ph); g.closePath();
      g.fillStyle = grad; g.fill();
    }
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
// ---- debug trace + problem logging (sent to the app's 🐞 Problem log) ----
const TRACE = [], LOGQ = [];
let lastLogFlush = 0;
function traceAdd(cmd, out) {
  const r = (out || "(timeout)").replace(/[\r\n]+/g, " ").replace(/\s+/g, " ").replace(">", "").trim();
  TRACE.push(`${new Date().toLocaleTimeString()} [${curHeader || "-"}] ${cmd} → ${r.slice(0, 80)}`);
  if (TRACE.length > 200) TRACE.shift();
}
function logEvent(kind, where, message, details) {
  LOGQ.push({ kind, where, message: String(message).slice(0, 400), details: (details ? String(details) : "") + "\n--- last adapter exchanges ---\n" + TRACE.slice(-25).join("\n") });
  flushLog();
}
function flushLog(force) {
  if (!LOGQ.length && !force) return;
  const now = Date.now();
  if (!force && now - lastLogFlush < 15000) { setTimeout(() => flushLog(), 15500 - (now - lastLogFlush)); return; }
  lastLogFlush = now;
  sendValue({ type: "log", id: "log-" + now, entries: LOGQ.splice(0) });
}
function debugSnapshot() {
  return { connected, isCan, protocol: baseProto, baseHeader, batchOK, fastOK, adapter: device && device.name,
    pidsPolled: active.length, oemSource: typeof oemSourceName === "function" ? oemSourceName() : "", oemChecked: oemCmds.filter((c) => c.state !== "new").length,
    oemTotal: oemCmds.length, oemFound, modulesAnswered: modResults.length, vin: vinRead, codes: dtcs.stored, profile: profile(),
    userAgent: navigator.userAgent, trace: TRACE.slice(-80) };
}
window.addEventListener("error", (e) => logEvent("scanner-crash", "Scanner page", e.message, (e.error && e.error.stack) || `${e.filename}:${e.lineno}`));
window.addEventListener("unhandledrejection", (e) => logEvent("scanner-crash", "Scanner page", (e.reason && e.reason.message) || String(e.reason), e.reason && e.reason.stack));

function rawSend(cmd, timeoutMs) {
  return new Promise((resolve) => {
    buf = "";
    let t;
    const done = (out) => { clearTimeout(t); pending = null; traceAdd(cmd, out); resolve(out); };
    t = setTimeout(() => { staleReply = true; done(buf); }, timeoutMs);
    pending = done;
    const data = new TextEncoder().encode(cmd + "\r");
    const w = rxChar.properties.writeWithoutResponse && rxChar.writeValueWithoutResponse
      ? rxChar.writeValueWithoutResponse(data)
      : (rxChar.writeValueWithResponse ? rxChar.writeValueWithResponse(data) : rxChar.writeValue(data));
    w.catch(() => done(""));
  });
}
// One command at a time on the wire
// After a timeout the adapter may still be answering the old command. Wait for its ">" prompt (or a short
// pause) and throw that late reply away, so it can't mix into the next command's answer.
// (Don't send a bare "\r" to flush: on an ELM327 that REPEATS the last command.)
let staleReply = false;
async function drainStale(maxMs = 600) {
  const t0 = Date.now();
  while (Date.now() - t0 < maxMs && !buf.includes(">")) await sleep(25);
  buf = ""; staleReply = false;
}
function sendCmd(cmd, timeoutMs = 1000) {
  if (!rxChar) return Promise.resolve("");
  const p = cmdChain.then(async () => { if (staleReply) await drainStale(); return rawSend(cmd, timeoutMs); });
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
7E2||221991|0|16|1|8|0|1|0|rpm|Torque converter slip|*
7E0||221991|0|16|1|8|0|1|0|rpm|Torque converter slip v2|*
7E2||221942|0|8|1|4|0|0|0|rpm|trans output shaft speed|*
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
  if (sig.map) { const t = sig.map[String(v)]; return t == null ? null : String(t); }
  const x = v * sig.mul / sig.div + sig.add;
  if ((sig.nmin != null && x <= sig.nmin) || (sig.nmax != null && x >= sig.nmax)) return null;      // "no value" markers
  if ((sig.min != null && x < sig.min - 1e-6) || (sig.max != null && x > sig.max + 1e-6)) return null;  // impossible = wrong layout
  const r1 = (n) => (Math.abs(n) >= 100 ? Math.round(n) : Math.round(n * 10) / 10);
  switch (sig.unit) {
    case "C": return x <= -39.5 || x > 300 ? null : degF(x) + " °F";
    case "F": return x <= -39.5 || x > 570 ? null : Math.round(x) + " °F";
    case "kPa": return r1(x * 0.145038) + " psi";
    case "bar": return r1(x * 14.5038) + " psi";
    case "psi": return r1(x) + " psi";
    case "kph": return Math.round(x * 0.621371) + " mph";
    case "km": return Math.round(x * 0.621371).toLocaleString() + " mi";
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
const PATH_GROUP = {
  "Engine": "Engine", "Engine.Catalyst": "Engine", "Engine.DPF": "Engine", "Fluids": "Engine", "Engine.Misfires": "Misfire counters",
  "Transmission": "Transmission", "Drivetrain": "Transmission", "Fuel": "Fuel & air", "Emissions": "Fuel & air",
  "Battery": "Electrical", "Electrical": "Electrical", "Tires": "Tire pressure (TPMS)",
  "Control": "Chassis, ABS & steering", "Control.Traction": "Chassis, ABS & steering", "Brakes": "Chassis, ABS & steering",
  "Movement": "Wheel speeds & motion", "Orientation": "Wheel speeds & motion", "Climate": "Climate & A/C",
};
const GROUP_ORDER = ["Engine", "Transmission", "Misfire counters", "Fuel & air", "Electrical", "Tire pressure (TPMS)",
  "Chassis, ABS & steering", "Wheel speeds & motion", "Climate & A/C", "Other"];
const GROUP_CLOSED = new Set(["Chassis, ABS & steering", "Wheel speeds & motion", "Climate & A/C", "Other"]);
function oemGroup(sig) {
  if (sig.path) return PATH_GROUP[sig.path] || "Other";
  const n = sig.name;
  if (/misfire/i.test(n)) return "Misfire counters";
  if (/tire/i.test(n)) return "Tire pressure (TPMS)";
  if (/trans|gear|cvt|torque converter|lock.?up|clutch|shaft|gearbox|transaxle|pulley|awd/i.test(n)) return "Transmission";
  if (/fuel|inject|rail|boost|turbo|wastegate|throttle|air|lambda|map |egr|purge|evap/i.test(n)) return "Fuel & air";
  if (/volt|battery|generator/i.test(n)) return "Electrical";
  return "Engine";
}

let oemCmds = [], oemRR = 0, oemFound = 0, oemModules = {};
function profile() { const s = $("oemSel").value; return s === "AUTO" ? (ARGS.make || "GENERIC") : s; }
function usingModelData() { return $("oemSel").value === "AUTO" && Array.isArray(ARGS.oem) && ARGS.oem.length > 0; }
function oemSourceName() { return usingModelData() ? (ARGS.oem_src || "").replace(/-/g, " ") : profile(); }
function buildEnhanced() {
  const year = parseInt(ARGS.year, 10) || 0;
  const model = usingModelData();
  const sigs = !isCan ? [] : model ? ARGS.oem.map((g) => Object.assign({}, g))
    : (OEM_DB[profile()] || []).filter((g) => yearOk(g.yrs, year)).map((g) => Object.assign({}, g));
  const byCmd = new Map();
  sigs.forEach((g) => {
    g.label = cleanName(g.name);
    g.group = oemGroup(g);
    g.watch = /torque conv|converter clutch|\btcc\b|tc slip/i.test(g.name) && !/command|desired|duty|pressure|solenoid|temp/i.test(g.name) ? "tcc" : "";
    const k = g.hdr + "|" + g.rax + "|" + g.req;
    if (!byCmd.has(k)) byCmd.set(k, { hdr: g.hdr, rax: g.rax, req: g.req, sigs: [], state: "new", miss: 0 });
    byCmd.get(k).sigs.push(g);
  });
  oemCmds = [...byCmd.values()];
  if (!model) {
    // Make-level list mixes layouts from several models: keep one layout per quantity so values never conflict.
    oemCmds.forEach((c) => {
      const seen = new Set();
      c.sigs = c.sigs.filter((g) => (seen.has(g.label) ? false : (seen.add(g.label), true)));
    });
  }
  // Probe the most useful systems first
  const rank = (c) => Math.min(...c.sigs.map((g) => GROUP_ORDER.indexOf(g.group)));
  oemCmds.sort((a, b) => rank(a) - rank(b));
  oemRR = 0; oemFound = 0; oemModules = {}; oemTile.n = 0;
  $("enhBox").innerHTML = '<div class="box">' + (oemCmds.length
    ? `Checking ${oemCmds.length} factory data requests (${esc(oemSourceName())})…`
    : (isCan ? "No factory definitions for this vehicle yet. Pick a make in OEM Profile above to try the make-level list."
             : "OEM data needs a CAN vehicle (most 2008+).")) + "</div>";
  updateEnhNote();
}
function updateEnhNote() {
  const checked = oemCmds.filter((c) => c.state !== "new").length;
  $("enhNote").textContent = oemCmds.length
    ? `${oemSourceName()} · checked ${checked}/${oemCmds.length} requests · ${oemFound} readings found`
    : "";
}
function oemTile(sig) {
  if (sig.tile) return sig.tile;
  const box = $("enhBox");
  if (box.firstElementChild && box.firstElementChild.classList.contains("box")) box.innerHTML = "";
  const grp = sig.group;
  let sec = [...box.children].find((c) => c.dataset.grp === grp);
  if (!sec) {
    sec = document.createElement("details");
    sec.dataset.grp = grp;
    sec.open = !GROUP_CLOSED.has(grp);
    sec.innerHTML = `<summary class="grp" style="cursor:pointer">${esc(grp)} <span class="cnt"></span></summary><div class="grid" style="margin:4px 0 10px"></div>`;
    const after = [...box.children].find((c) => GROUP_ORDER.indexOf(c.dataset.grp) > GROUP_ORDER.indexOf(grp));
    box.insertBefore(sec, after || null);
  }
  const id = "oem" + (oemTile.n = (oemTile.n || 0) + 1);
  LABEL[id] = `${sig.label} [OEM ${sig.hdr} ${sig.req}]`;
  sec.lastElementChild.insertAdjacentHTML("beforeend",
    `<div class="tile" id="t_${id}" title="${esc(sig.hdr + " " + sig.req)}"><div class="l">${esc(sig.label)}</div><div class="v" id="v_${id}" style="color:var(--p)">--</div></div>`);
  sec.querySelector(".cnt").textContent = `(${sec.lastElementChild.children.length})`;
  sig.tile = id; oemFound++;
  return id;
}
// Factory (enhanced) request to one module.
//  - A real answer wins even if a "busy" (7F xx 78) came with it.
//  - 7F xx 78 = "busy, answer coming": wait longer instead of giving up.
//  - 7F 22 7E / 7F = "not allowed in this session": open the extended diagnostic session (10 03) on that
//    module once and try again. 7F xx 31 (not supported) and 7F xx 33 (security locked) are left alone.
const extSession = {};   // header -> true (opened OK) / false (module refused it, don't try again)
async function readOem(cmd, retry = true) {
  await setAddr(cmd.hdr, cmd.rax);
  const pre = respCode(cmd.req.slice(0, 2)) + cmd.req.slice(2);
  const nrc = (ms) => { const m = ms.find((x) => x.startsWith("7F")); return m ? m.slice(4, 6) : ""; };
  let msgs = messages(await sendCmd(cmd.req, 500));
  if (!msgs.some((m) => m.startsWith(pre)) && nrc(msgs) === "78") msgs = messages(await sendCmd(cmd.req, 2500));
  for (const m of msgs) if (m.startsWith(pre)) return { bytes: bytesOf(m.slice(pre.length)), replied: true };
  const code = nrc(msgs);
  if (retry && cmd.req.startsWith("22") && (code === "7E" || code === "7F") && extSession[cmd.hdr] !== false) {
    const r = messages(await sendCmd("1003", 1500));
    const ok = r.some((m) => m.startsWith("5003"));
    if (!ok && extSession[cmd.hdr] !== true) extSession[cmd.hdr] = false;
    if (ok) {   // (sessions time out after a few seconds, so this can repeat on later passes; only log the first)
      if (extSession[cmd.hdr] !== true) logEvent("scanner", "Extended session", `Opened 10 03 on module ${cmd.hdr} for ${cmd.req}`);
      extSession[cmd.hdr] = true;
      return readOem(cmd, false);
    }
  }
  return { bytes: null, replied: msgs.length > 0 };   // any reply (even a refusal) means the module is there
}
async function pollEnhanced() {
  const fresh = oemCmds.filter((c) => c.state === "new").slice(0, 6);      // discovery: probe a few new requests
  const live = oemCmds.filter((c) => c.state === "live");
  const driving = typeof T !== "undefined" && (T.drive.on || T.trans.on);
  const graphed = live.filter((c) => c.sigs.some((g) => (g.tile && graphSel.includes(g.tile)) || (driving && g.watch)));   // graphed + TCC slip on a drive = every pass
  const rest = live.filter((c) => !graphed.includes(c));
  const due = [...graphed];
  for (let i = 0; i < Math.min(4, rest.length); i++) due.push(rest[(oemRR + i) % rest.length]);
  oemRR += 4;
  const jobs = [...fresh, ...due].sort((a, b) => (a.hdr + a.rax).localeCompare(b.hdr + b.rax));   // fewer module switches
  for (const c of jobs) {
    if (c.state === "dead") continue;
    const mod = oemModules[c.hdr] || (oemModules[c.hdr] = { alive: false, silent: 0 });
    const { bytes, replied } = await readOem(c);
    if (replied || bytes) mod.alive = true; else mod.silent++;
    let any = false;
    if (bytes) for (const g of c.sigs) {
      const v = extractBits(bytes, g.bix, g.len, g.lsb, g.sign);
      const text = v == null ? null : fmtOem(g, v);
      if (text == null) continue;
      any = true;
      setTile(oemTile(g), text);
    }
    if (c.state === "new") c.state = any ? "live" : "dead";
    else if (any) c.miss = 0;
    else if (++c.miss >= 3) c.state = "dead";
    // A module that never answers (not fitted on this car): skip the rest of its requests
    if (!mod.alive && mod.silent >= 2) oemCmds.forEach((o) => { if (o.hdr === c.hdr && o.state === "new") o.state = "dead"; });
  }
  await setAddr(baseHeader, "");
  updateEnhNote();
  if (oemCmds.length && !oemFound && oemCmds.every((c) => c.state !== "new"))
    $("enhBox").innerHTML = '<div class="box">This vehicle did not answer any of the factory requests on file for it.</div>';
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
// ===================== All-module code scan =====================
// Asks every likely module for its codes: UDS $19 02 first, then older KWP ($18 / $13) and OBD $03 as fallbacks.
const SWEEP = {
  ALL: ["7E0", "7E1", "7E2", "7E3", "7E4", "7E5", "7E6", "7E7"],
  TOYOTA: ["7B0", "7B1", "7B2", "7B3", "7C0", "7C4", "7C6", "7D0", "7D2", "7A1", "7A2", "781"],
  HONDA: ["DA0E", "DA10", "DA11", "DA1D", "DA1E", "DA26", "DA28", "DA2B", "DA30", "DA3A", "DA40", "DA53", "DA60", "DAB0"],
  NISSAN: ["740", "743", "744", "745", "746", "747", "752", "765", "79D"],
  HYUNDAI: ["7A0", "7A5", "7B3", "7C6", "7D0", "7D1", "7D4", "770", "7C4"],
  SUBARU: ["7A2", "7A3", "7B0", "7C0", "7C4", "7D0", "7D2", "7E2"],
  MAZDA: ["720", "726", "730", "733", "737", "760", "764", "7A6"],
  FORD: ["720", "724", "726", "727", "730", "732", "733", "737", "760", "764", "7A6", "7A7"],
  GM: ["241|641", "243|643", "244|644", "247|647", "24A|64A", "24C|64C", "251|651", "252|652"],
  CHRYSLER: ["740", "742", "744", "745", "747", "74A", "74F", "753", "75A", "783"],
};
const ADDR_NAMES = {
  "7E0": "Engine (ECM/PCM)", "7E1": "Transmission (TCM)", "7E2": "Hybrid / 2nd powertrain", "7E3": "Powertrain module 4",
  "7E4": "Battery / EV module", "7B0": "ABS / VSC", "7C0": "Instrument cluster", "7C4": "Air conditioning", "7A1": "Power steering",
  "760": "ABS / brakes", "726": "Body (BCM)", "720": "Instrument cluster", "737": "Airbag (SRS)", "733": "HVAC", "727": "Audio / ACM",
  "243": "ABS (EBCM)", "241": "Body (BCM)", "244": "Cluster", "247": "Airbag (SDM)", "251": "HVAC", "7D4": "Power steering (MDPS)",
  "770": "Body (BCM)", "7D1": "ABS / ESC", "7D0": "Airbag (SRS)", "743": "Instrument cluster", "745": "Body (BCM)", "740": "Body",
  "747": "ABS", "DA10": "Engine (PGM-FI)", "DA11": "Engine (PGM-FI)", "DA1E": "Transmission", "DA1D": "Transmission",
  "DA28": "VSA / ABS", "DA53": "Airbag (SRS)", "DA40": "Body (MICU)", "DA60": "Instrument cluster", "DA26": "TPMS",
};
const PATH_MODULE = { Engine: "Engine", Transmission: "Transmission", Movement: "ABS / chassis", Control: "ABS / chassis",
  "Control.Traction": "ABS / chassis", Brakes: "ABS / brakes", Climate: "HVAC / A/C", Tires: "TPMS", Battery: "Body / power",
  Electrical: "Body / power", Lights: "Body (lighting)", Doors: "Body (doors)", Seatbelts: "Airbag / restraints" };
let modResults = [], modScanning = false;

function moduleList() {
  const map = new Map();
  const add = (hdr, rax, name) => {
    if (!hdr || hdr === "7DF" || !/^([0-9A-F]{3}|DA[0-9A-F]{2})$/.test(hdr)) return;
    const m = map.get(hdr) || { hdr, rax: rax || "", names: {} };
    if (rax && !m.rax) m.rax = rax;
    if (name) m.names[name] = (m.names[name] || 0) + 1;
    map.set(hdr, m);
  };
  SWEEP.ALL.forEach((a) => add(a));
  (SWEEP[profile()] || []).forEach((a) => { const [h, r] = a.split("|"); add(h, r); });
  (Array.isArray(ARGS.oem) ? ARGS.oem : []).forEach((g) => add(g.hdr, g.rax, PATH_MODULE[g.path]));
  (OEM_DB[profile()] || []).forEach((g) => add(g.hdr, g.rax));
  return [...map.values()].map((m) => {
    const best = Object.entries(m.names).sort((a, b) => b[1] - a[1])[0];
    m.name = ADDR_NAMES[m.hdr] || (best ? best[0] : "Module");
    return m;
  });
}
const FTB_TEXT = {
  "01": "general electrical failure", "02": "general signal failure", "04": "internal system failure", "07": "mechanical failure",
  "11": "circuit short to ground", "12": "circuit short to battery", "13": "circuit open",
  "14": "short to ground or open", "15": "short to battery or open", "16": "voltage below threshold", "17": "voltage above threshold",
  "1C": "voltage out of range", "1F": "circuit intermittent",
  "23": "signal stuck low", "24": "signal stuck high", "29": "signal invalid", "2F": "signal erratic", "31": "no signal",
  "41": "checksum failure", "42": "memory failure", "49": "internal electronic failure", "4B": "over temperature",
  "64": "signal plausibility failure (reading doesn't match the others)",
  "71": "actuator stuck", "72": "actuator stuck open", "73": "actuator stuck closed", "77": "commanded position not reachable",
  "78": "alignment or adjustment incorrect", "7A": "fluid leak or seal failure", "7B": "fluid level low",
  "81": "invalid serial data received", "87": "missing message (lost communication)", "88": "bus off (module quit talking)",
  "92": "performance / incorrect operation", "93": "no operation", "94": "unexpected operation",
  "96": "component internal failure", "97": "operation obstructed or blocked", "98": "component over temperature",
};
function ftbText(code) { const m = /-([0-9A-F]{2})$/.exec(code || ""); return m ? FTB_TEXT[m[1]] || "" : ""; }
function decodeDtc3(h) {   // 2-byte DTC + optional failure-type byte
  const base = decodeDtc(h.slice(0, 4)), ftb = h.slice(4, 6);
  return ftb && ftb !== "00" ? base + "-" + ftb : base;
}
function udsStatus(st) {
  if (st & 0x08) return "stored";
  if (st & 0x04) return "pending";
  if (st & 0x01) return "active";
  return "history";
}
async function askModule(mod, req, timeout) {
  await setAddr(mod.hdr, mod.rax);
  let msgs = messages(await sendCmd(req, timeout));
  // "busy, wait" (7F xx 78) with no real answer yet -> ask again with a longer wait
  if (msgs.some((m) => /^7F..78/.test(m)) && !msgs.some((m) => !m.startsWith("7F"))) msgs = messages(await sendCmd(req, 2000));
  return msgs;
}
async function readModuleCodes(mod) {
  // 1) UDS ReadDTCInformation, all codes
  let msgs = await askModule(mod, "1902FF", 600);
  let r = msgs.find((m) => m.startsWith("5902"));
  if (r) {
    const codes = [];
    for (let i = 6; i + 8 <= r.length; i += 8) {
      const rec = r.substr(i, 8), st = parseInt(rec.slice(6, 8), 16);
      if (rec.slice(0, 6) === "000000") continue;
      codes.push({ code: decodeDtc3(rec.slice(0, 6)), status: udsStatus(st) });
    }
    return { alive: true, proto: "uds", codes };
  }
  const answered = msgs.length > 0;
  // 2) KWP2000 ReadDTCByStatus
  msgs = await askModule(mod, "1800FF00", 600);
  r = msgs.find((m) => m.startsWith("58"));
  if (r) {
    const n = parseInt(r.slice(2, 4), 16) || 0, codes = [];
    for (let k = 0, i = 4; k < n && i + 6 <= r.length; k++, i += 6) {
      const st = parseInt(r.substr(i + 4, 2), 16);
      codes.push({ code: decodeDtc(r.substr(i, 4)), status: (st & 0x40) ? "stored" : (st & 0x20) ? "pending" : "stored" });
    }
    return { alive: true, proto: "kwp", codes };
  }
  if (!answered && !msgs.length) return { alive: false };
  // 3) Toyota-style $13 and 4) OBD $03 sent straight to this module
  for (const [req, pre, proto] of [["13", "53", "t13"], ["03", "43", "obd"]]) {
    msgs = await askModule(mod, req, 600);
    r = msgs.find((m) => m.startsWith(pre));
    if (r) {
      const n = parseInt(r.slice(2, 4), 16) || 0, codes = [];
      for (let k = 0, i = 4; k < n && i + 4 <= r.length; k++, i += 4) if (r.substr(i, 4) !== "0000") codes.push({ code: decodeDtc(r.substr(i, 4)), status: "stored" });
      return { alive: true, proto, codes };
    }
  }
  return { alive: true, proto: "", codes: [], unsupported: true };
}
async function scanModules() {
  if (modScanning || !isCan) { if (!isCan) $("modBox").textContent = "All-module scan needs a CAN vehicle (most 2008+)."; return; }
  modScanning = true; $("modBtn").disabled = true;
  const list = moduleList();
  modResults = [];
  try {
    for (let i = 0; i < list.length && connected; i++) {
      const mod = list[i];
      log(`Scanning modules ${i + 1}/${list.length} (${mod.name}, ${mod.hdr})…`);
      const res = await txn(async () => { const r = await readModuleCodes(mod); await setAddr(baseHeader, ""); return r; });
      if (res.alive) modResults.push(Object.assign(mod, res));
      renderModules(i + 1, list.length);
    }
  } finally {
    modScanning = false; $("modBtn").disabled = !connected;
    renderModules();
    log(streaming ? "Streaming live data…" : "Module scan done.");
  }
}
function renderModules(done, total) {
  const color = { stored: "r", active: "r", pending: "o", history: "s" };
  const found = modResults.reduce((n, m) => n + m.codes.length, 0);
  $("modNote").textContent = total && done < total
    ? `scanning ${done}/${total}…`
    : `${modResults.length} modules answered · ${found} code(s)`;
  if (!modResults.length) { $("modBox").textContent = total ? "Scanning…" : "No modules answered."; return; }
  $("modBox").innerHTML = modResults.map((m, i) => {
    const chips = m.codes.length
      ? m.codes.map((c) => `<span class="chip" title="${c.status}${ftbText(c.code) ? " · " + ftbText(c.code) : ""}" style="color:var(--${color[c.status]});border-color:var(--${color[c.status]})">${esc(c.code)}<span style="font-weight:400;font-size:.7rem"> ${c.status}${ftbText(c.code) ? " · " + ftbText(c.code) : ""}</span></span>`).join("")
      : `<span style="color:var(--g)">${m.unsupported ? "answered, but codes not readable with generic commands" : "no codes"}</span>`;
    const clr = m.codes.length && m.proto ? `<button data-clrmod="${i}" style="padding:3px 8px;font-size:.72rem;background:var(--card);color:var(--r);border:1px solid var(--r)">Clear</button>` : "";
    return `<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:5px 0;border-bottom:1px solid var(--line)">
      <span style="min-width:170px;color:var(--w);font-weight:700">${esc(m.name)} <span class="note">${m.hdr}</span></span>
      <span class="chips" style="flex:1">${chips}</span>${clr}</div>`;
  }).join("");
}
async function clearModule(i) {
  const m = modResults[i]; if (!m) return;
  if (!confirm(`Clear all codes in ${m.name} (${m.hdr})?\n\nKey ON, engine OFF is best.`)) return;
  const req = { uds: "14FFFFFF", kwp: "14FF00", t13: "14FF00", obd: "04" }[m.proto];
  const pre = m.proto === "obd" ? "44" : "54";
  const ok = await txn(async () => { const msgs = await askModule(m, req, 3000); await setAddr(baseHeader, ""); return msgs.some((x) => x.startsWith(pre)); });
  log(ok ? `${m.name}: codes cleared. Re-reading…` : `${m.name} did not confirm the clear.`);
  const res = await txn(async () => { const r = await readModuleCodes(m); await setAddr(baseHeader, ""); return r; });
  Object.assign(m, res); renderModules();
  if (!ok) alert(`${m.name} did not confirm the clear. Some modules need the key ON / engine OFF, or a factory tool.`);
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-clrmod]");
  if (b) clearModule(+b.dataset.clrmod);
});

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
  misMids = [...(sup || new Set(DEFAULT_MIDS))].filter((m) => m >= "A2" && m <= "AD").sort();
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
    if (oemCmds.length && cycle % (discovering ? 2 : 3) === 0) await txn(pollEnhanced);
    await extraPolls(cycle);
    if (cycle % 10 === 0) {
      const secs = (performance.now() - t0) / 1000;
      $("rate").textContent = `· ${(cycle / secs).toFixed(1)} refresh/s${batchOK ? " · multi-PID" : ""}`;
    }
    safely("Drive checks", driveChecks);
    safely("Guided tests", testsTick);
  }
}
function startStream() { streaming = true; loopToken++; liveLoop(loopToken); $("pauseBtn").textContent = "⏸️ Pause"; log("Streaming live data…"); }
function stopStream() { streaming = false; loopToken++; $("pauseBtn").textContent = "▶️ Resume"; }

function speak(text) {
  const now = Date.now(); if (now - lastSpeak < 18000) return; lastSpeak = now;
  if (typeof driveRecAlert === "function") driveRecAlert(text);
  if ("speechSynthesis" in window) { speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(text); u.rate = 1.05; speechSynthesis.speak(u); }
}
// ---- deceleration fuel cut / open loop detection (fuel trims are meaningless then) ----
let lastDecelT = 0, minTps = null, trimBadSince = 0;
function closedLoop() { const f = shown.fss; return !f || f === "--" || f === "N/A" || /^CL/.test(f); }
function inDecel() {
  if (num.tps != null && (num.spd ?? 0) < 2 && (num.rpm ?? 2000) < 1100) minTps = minTps == null ? num.tps : Math.min(minTps, num.tps);
  const throttleShut = num.tps != null && num.tps <= (minTps ?? num.tps) + 1.5;
  const decel = /decel/i.test(shown.fss || "") || ((num.rpm ?? 0) > 1100 && (num.spd ?? 0) > 5 && (throttleShut || (num.load ?? 100) <= 18));
  if (decel) lastDecelT = nowS();
  return decel || nowS() - lastDecelT < 4;   // trims settle for a few seconds after fuel cut ends
}
function trimsTrustworthy() { return closedLoop() && !inDecel(); }

// ===================== Plausibility engine: flags readings that can't be right =====================
// Each rule must hold for 5 s straight to appear and stays listed 30 s, so nothing flickers.
const PL = {};   // rule id -> { since, until, text, tiles }
function plRule(id, active, text, tiles) {
  const t = nowS();
  if (active) {
    PL[id] = PL[id] || { since: t };
    PL[id].text = text; PL[id].tiles = tiles || [];
    if (t - PL[id].since >= 5) PL[id].until = t + 30;
  } else if (PL[id] && !PL[id].until) delete PL[id];
  else if (PL[id] && t > PL[id].until) delete PL[id];
}
const frsh = (k, maxAge = 8) => num[k] != null && numT[k] != null && nowS() - numT[k] < maxAge;
function plausibility() {
  const rpm = frsh("rpm") ? num.rpm : null, spd = num.spd ?? 0;
  const L = engineLiters();
  // --- Key on, engine off ---
  const koeo = rpm === 0;
  const coldish = (num.ect ?? 999) < 125 && (num.iat ?? 999) < 125;   // sensors should agree only on a cool engine
  plRule("tempskew", koeo && coldish && frsh("ect", 20) && frsh("iat", 20) && Math.abs(num.ect - num.iat) > 15,
         `<b>Temperature sensors disagree</b>: coolant ${Math.round(num.ect ?? 0)}°F vs intake air ${Math.round(num.iat ?? 0)}°F with the engine off and cool — ` +
         `one is skewed (ignore if the engine ran in the last few hours).`, ["ect", "iat"]);
  plRule("aatskew", koeo && coldish && frsh("aat", 20) && frsh("iat", 20) && Math.abs(num.aat - num.iat) > 20,
         `<b>Ambient vs intake air temp</b> differ by ${Math.round(Math.abs(num.aat - num.iat))}°F on a cool engine — one sensor is likely skewed.`, ["aat", "iat"]);
  plRule("mapskew", koeo && frsh("map", 20) && frsh("baro", 20) && Math.abs(num.map - num.baro * 0.4912) > 0.8,
         `<b>MAP vs barometric pressure</b>: engine off, MAP should equal BARO. MAP ${(num.map ?? 0).toFixed(1)} PSI vs BARO ` +
         `${((num.baro ?? 0) * 0.4912).toFixed(1)} PSI — the MAP sensor (or BARO) is skewed.`, ["map", "baro"]);
  // --- Hot idle ---
  const hotIdle = rpm != null && rpm >= 550 && rpm <= 950 && (num.ect ?? 0) >= 175 && spd < 1;
  plRule("mafidle", hotIdle && L && frsh("maf") && num.maf > 0 && num.maf < 0.6 * L,
         `<b>MAF reads low</b>: ${(num.maf ?? 0).toFixed(1)} g/s at hot idle on a ${L ? L.toFixed(1) : "?"}L engine (expect roughly ${(0.9 * L).toFixed(1)}–${(1.4 * L).toFixed(1)}). ` +
         `Dirty/under-reporting MAF or unmetered air after the sensor — check it against the fuel trims.`, ["maf"]);
  plRule("trimidle", hotIdle && trimsTrustworthy() && frsh("stft1") && Math.abs((num.stft1 ?? 0) + (num.ltft1 ?? 0)) > 10,
         `<b>Fuel trim off at idle</b>: Bank 1 total ${(((num.stft1 ?? 0) + (num.ltft1 ?? 0))).toFixed(0)}% ` +
         `(${(num.stft1 ?? 0) + (num.ltft1 ?? 0) > 0 ? "lean — vacuum leak, low fuel delivery, under-reporting MAF" : "rich — leaking injector, fuel pressure high, MAF over-reporting"}).`,
         ["stft1", "ltft1"]);
  plRule("trimidle2", hotIdle && trimsTrustworthy() && frsh("stft2") && Math.abs((num.stft2 ?? 0) + (num.ltft2 ?? 0)) > 10,
         `<b>Fuel trim off at idle</b>: Bank 2 total ${(((num.stft2 ?? 0) + (num.ltft2 ?? 0))).toFixed(0)}%.`, ["stft2", "ltft2"]);
  // --- Any time the engine is running ---
  plRule("pcmdrop", rpm != null && rpm > 500 && frsh("volt") && frsh("cmv") && Math.abs(num.volt - num.cmv) > 0.5,
         `<b>Voltage drop to the PCM</b>: adapter sees ${(num.volt ?? 0).toFixed(1)} V but the PCM reports ${(num.cmv ?? 0).toFixed(1)} V — ` +
         `check PCM power and ground circuits (voltage-drop test them).`, ["volt", "cmv"]);
  // render
  const act = Object.values(PL).filter((r) => r.until);
  const box = $("plausBox");
  const flagged = new Set(act.flatMap((r) => r.tiles || []));
  for (const el of document.querySelectorAll(".tile.warn")) if (!flagged.has(el.id.slice(2))) el.classList.remove("warn");
  for (const id of flagged) { const el = $("t_" + id); if (el) el.classList.add("warn"); }
  if (!act.length) { box.style.display = "none"; return; }
  box.style.display = "block";
  box.innerHTML = "⚠️ <b>Doesn't add up:</b><br>" + act.map((r) => "• " + r.text).join("<br>");
}
function plausNow() { return Object.values(PL).filter((r) => r.until).map((r) => r.text.replace(/<[^>]+>/g, "")); }

// ===================== Glitch catcher: hi-res window around a stumble =====================
const GB = [];   // ring buffer, ~1 entry per live-data pass, last 25 s
const GB_KEYS = ["rpm", "spd", "tps", "load", "stft1", "ltft1", "map", "maf", "frp", "volt"];
let glitchCool = {};
function glitchTick() {
  const t = nowS();
  GB.push([t, ...GB_KEYS.map((k) => (frsh(k, 6) ? r2(num[k]) : null))]);
  while (GB.length && t - GB[0][0] > 25) GB.shift();
  if (!driveOn) return;
  const back = (secs, key) => {
    const i = GB_KEYS.indexOf(key) + 1;
    for (let j = GB.length - 1; j >= 0; j--) if (t - GB[j][0] >= secs) return GB[j][i];
    return null;
  };
  const fire = (kind, text) => {
    if (glitchCool[kind] && t - glitchCool[kind] < 30) return;
    glitchCool[kind] = t;
    lastSpeak = 0; speak(text);
    logEvent("glitch", "Glitch catcher", text);
    setTimeout(() => {   // give it 5 more seconds, then attach the hi-res window to the saved alert
      if (REC && REC.status === "recording") {
        const a = [...REC.alerts].reverse().find((x) => x.text === text && !x.win);
        if (a) a.win = glitchWindow();
      }
    }, 5200);
  };
  const rpm = num.rpm, rpm1 = back(1.2, "rpm");
  if (rpm != null && rpm1 != null && rpm1 - rpm > 250 && (num.tps ?? 0) > 3 && (num.spd ?? 0) > 2 && !inDecel())
    fire("stumble", `Stumble caught. RPM dropped ${Math.round(rpm1 - rpm)} with your foot on the throttle.`);
  const st = num.stft1, st2 = back(2, "stft1");
  if (st != null && st2 != null && trimsTrustworthy() && Math.abs(st - st2) > 15 && Math.abs(st) > 20)
    fire("trimspike", `Fuel trim spike, bank 1 short term ${Math.round(st)} percent.`);
  const frp = num.frp, frp5 = back(5, "frp");
  if (frp != null && frp5 != null && frp5 > 20 && frp < frp5 * 0.72 && (num.rpm ?? 0) > 500)
    fire("frpdrop", `Fuel pressure dropped from ${Math.round(frp5)} to ${Math.round(frp)} PSI.`);
}
function glitchWindow() {   // the last 15 s, full resolution, as a small CSV table
  const t = nowS();
  const rows = GB.filter((g) => t - g[0] <= 15);
  return ["sec_ago," + GB_KEYS.join(",")].concat(rows.map((g) => (t - g[0]).toFixed(1) + "," + g.slice(1).map((v) => v == null ? "" : v).join(","))).join("\n");
}

const SAFE_SEEN = {};
function safely(name, fn) {   // a bug in one check must never freeze the live data
  try { fn(); } catch (e) {
    if (!SAFE_SEEN[name + e.message]) { SAFE_SEEN[name + e.message] = 1; logEvent("scanner-crash", name, e.message, e.stack); }
  }
}
function driveChecks() {
  safely("Plausibility check", plausibility);
  safely("Glitch catcher", glitchTick);
  if (!driveOn) return;
  const t1 = (num.stft1 ?? 0) + (num.ltft1 ?? 0);
  const hasB2 = num.stft2 !== undefined;
  const t2 = (num.stft2 ?? 0) + (num.ltft2 ?? 0);
  // Trim alerts only in closed loop, not during decel fuel cut, and only if they stay out for 3+ seconds
  const bad = trimsTrustworthy() && (Math.abs(t1) > 16 || (hasB2 && Math.abs(t2) > 16));
  trimBadSince = bad ? (trimBadSince || nowS()) : 0;
  const trimAlert = bad && nowS() - trimBadSince >= 3;
  if (trimAlert && t1 > 16) speak(`Bank 1 total fuel trim plus ${Math.round(t1)} percent. Lean.`);
  else if (trimAlert && t1 < -16) speak(`Bank 1 total fuel trim minus ${Math.abs(Math.round(t1))} percent. Rich.`);
  else if (trimAlert && hasB2 && t2 > 16) speak(`Bank 2 total fuel trim plus ${Math.round(t2)} percent. Lean.`);
  else if (trimAlert && hasB2 && t2 < -16) speak(`Bank 2 total fuel trim minus ${Math.abs(Math.round(t2))} percent. Rich.`);
  else if ((num.ect ?? 0) >= 225) speak(`High coolant temperature, ${num.ect} degrees.`);
  else if ((num.rpm ?? 0) > 500 && num.volt && num.volt < 13.0) speak(`Low charging voltage, ${num.volt.toFixed(1)} volts.`);
  if (Date.now() - lastDriveAi > 90000) { lastDriveAi = Date.now(); requestAi("drive"); }
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
  if (mode === "full") $("aiBox").innerHTML = `<span style="color:var(--o)">🤖 The AI team is analyzing live data, codes, monitors, Mode $06 and test results… (about 30–60 s)</span>`;
  sendValue({ type: "ai", id: aiPendingId, mode, at: new Date().toLocaleTimeString(), pids: snapshot(), dtcs, readiness: readinessSummary, mode6: mode6Summary, tests: T.results || {}, flags: plausNow() });
  const id = aiPendingId;
  setTimeout(() => { if (aiPendingId === id) { aiPendingId = null; if (mode === "full") $("aiBox").textContent = "AI request timed out. Try again."; logEvent("ai", "AI check (" + mode + ")", "No answer from the app within 3 min"); } }, 180000);
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
const BTN_IDS = ["pauseBtn", "driveBtn", "readBtn", "clearBtn", "aiBtn", "syncBtn", "modBtn", "evapBtn"];
const enableBtns = (on) => BTN_IDS.forEach((id) => { $(id).disabled = !on; });

// If the adapter drops (bumps, ignition flicker, phone hiccup), reconnect on our own and keep the test drive going.
let reconnecting = false;
async function onDisconnect() {
  const wasLive = streaming || driveOn, wasDriving = driveOn;
  connected = false; stopStream(); enableBtns(false);
  if (reconnecting) return;   // a retry below dropped again; the loop keeps trying
  reconnecting = true;
  $("bleBtn").disabled = true; $("bleBtn").textContent = "🔄 Reconnecting…";
  logEvent("scanner", "Bluetooth", "Adapter disconnected" + (wasDriving ? " during a test drive" : ""));
  if (wasDriving) { lastSpeak = 0; speak("Scanner connection lost. Reconnecting."); }
  for (let i = 1; i <= 6; i++) {
    log(`Adapter dropped — reconnecting (try ${i} of 6)…`);
    await sleep(1000 + 1500 * i);
    try {
      await connectGatt();
      if (await initVehicle()) {
        connected = true; enableBtns(true);
        $("bleBtn").textContent = "✅ Connected"; $("bleBtn").disabled = true;
        log("Reconnected ✓"); logEvent("scanner", "Bluetooth", `Reconnected automatically on try ${i}`);
        if (driveOn) { lastSpeak = 0; speak("Scanner reconnected."); }
        if (wasLive) startStream();
        reconnecting = false; return;
      }
    } catch (_) { /* adapter not back yet */ }
  }
  reconnecting = false;
  if (driveOn) {   // give up: end the drive cleanly so everything recorded so far is saved
    driveOn = false; $("driveBanner").style.display = "none"; $("driveBtn").textContent = "🚗 Test Drive Audio";
    wake(false); stopDriveTests(); speak("Could not reconnect to the scanner. The test drive was saved.");
  }
  $("bleBtn").textContent = "🔄 Reconnect"; $("bleBtn").disabled = false;
  log("Couldn't reconnect on its own. Check the adapter is plugged in and the key is ON, then tap Reconnect.");
  logEvent("scanner", "Bluetooth", "Automatic reconnect failed after 6 tries");
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
  sup01 = sup;
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
      logEvent("scanner", "Connect", "ECM did not answer 0100 on CAN or auto protocol");
      $("bleBtn").disabled = false; return;
    }
    connected = true; enableBtns(true);
    $("bleBtn").textContent = "✅ Connected";

    log("Reading VIN & codes…");
    await readVin(); await readDtcs(); await readFreezeFrame();
    log("Reading I/M readiness…"); await loadReadiness();
    log("Reading Mode $06…"); await loadMode6();
    startStream();
    await sleep(1500);
    await scanModules();             // live data keeps updating between modules
    if (connected) sendSync(true);   // push VIN + all codes + snapshot into the app (no page reload)
  } catch (err) {
    log("Error: " + err.message);
    if (!/cancel|chooser|User cancelled/i.test(err.message)) logEvent("scanner", "Connect", err.message, err.stack);
  } finally {
    $("bleBtn").disabled = connected;
  }
});

function sendSync(auto) {
  const modules = modResults.filter((m) => m.codes.length).map((m) => ({ name: m.name, addr: m.hdr, codes: m.codes }));
  sendValue({ type: "sync", id: "sync-" + Date.now(), vin: vinRead, dtcs: Object.assign({}, dtcs, { modules, freeze: freezeFrame }), auto: !!auto,
    pids: snapshot(), readiness: readinessSummary, mode6: mode6Summary, flags: plausNow(), at: new Date().toLocaleTimeString() });
  log(`Sent to app → VIN ${vinRead || "not reported"} · ${dtcs.stored.length} stored / ${dtcs.pending.length} pending code(s)`);
}

$("pauseBtn").addEventListener("click", () => { streaming ? (stopStream(), log("Paused.")) : startStream(); });
$("driveBtn").addEventListener("click", () => {
  driveOn = !driveOn;
  $("driveBanner").style.display = driveOn ? "block" : "none";
  $("driveBtn").textContent = driveOn ? "⏹️ Stop Test Drive" : "🚗 Test Drive Audio";
  wake(driveOn);
  lastDriveAi = Date.now();
  if (driveOn && !streaming) startStream();
  if (driveOn) {
    startDriveTests();
    lastSpeak = 0; speak("Test drive started. Tests are running. When it's safe, include steady cruising, one full throttle pull, and one firm stop from 30 miles per hour.");
  } else stopDriveTests();
});
$("dbgBtn").addEventListener("click", () => {
  sendValue({ type: "log", id: "dbg-" + Date.now(), entries: LOGQ.splice(0), debug: debugSnapshot() });
  log("Debug info sent — see the 📋 Log tab → 🐞 Problem log.");
});
$("modBtn").addEventListener("click", async () => { await scanModules(); sendSync(false); });
$("evapBtn").addEventListener("click", async () => {
  if (!confirm("Command the ECM to SEAL the EVAP system (close the vent valve) for a smoke test?\n\n" +
               "Key ON, engine OFF. This is the standardized OBD Mode $08 request — many vehicles support it, some don't. " +
               "Cycling the key releases it.")) return;
  log("Sending EVAP seal request (Mode $08)…");
  const ok = await txn(async () => {
    await setHeader("7DF");
    const raw = await sendCmd("0801", 4000);
    await setHeader(baseHeader);
    return messages(raw).some((m) => m.startsWith("4801"));
  });
  if (ok) { log("✅ EVAP system commanded sealed — smoke test it now. Cycle the key when done to release it."); }
  else { log("This vehicle did not accept the EVAP seal command (not all do)."); logEvent("scanner", "EVAP seal", "No 48 01 reply to Mode 08"); }
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
    logEvent("scanner", "Clear codes", "No 44 reply to Mode 04");
    alert("The ECM did not confirm the clear (no 44 response). Try again with key ON, engine OFF.");
  }
});
$("aiBtn").addEventListener("click", () => requestAi("full"));
$("syncBtn").addEventListener("click", async () => { if (!vinRead) await txn(readVin); sendSync(false); });
$("oemSel").addEventListener("change", () => { if (connected) buildEnhanced(); });

// ===================== Guided tests (eSCAN-style) =====================
const TESTS = [["ft", "⛽ Fuel Trim"], ["ve", "🌬️ VE / MAF"], ["cat", "♨️ Catalyst"], ["chg", "🔋 Charging"], ["perf", "🏁 Power & Braking"],
  ["mis", "🔥 Misfires"], ["rdy", "📋 Readiness Coach"], ["vac", "🧭 Vacuum"], ["warm", "🌡️ Warm-up"], ["crank", "🔑 Cranking"],
  ["trans", "⚙️ Trans"], ["nvh", "〰️ Vibration"], ["tail", "👂 Tailpipe"], ["rec", "💾 Record & Compare"]];
let testTab = "ft";
// Test drive: runs the tests automatically while you drive (started/stopped by the Test Drive button)
const T = {
  ft: { on: false, bins: null, lastT: 0 },
  ve: { phase: "idle", pts: [], peak: null, result: null },
  cat: { phase: "idle", t0: 0, up: [], dn: [], result: null },
  chg: { koeo: null, idle: null, loaded: null },
  perf: { mode: null, phase: "idle", pts: [], result: null, cal: null, motion: null },
};
const nowS = () => performance.now() / 1000;
T.drive = { on: false, done: {}, perfBest: {} };
function startDriveTests() {
  T.drive = { on: true, t0: nowS(), done: {}, perfBest: {}, veBest: null, idleSince: null, idleV: [], dV: [], report: null };
  T.ft = { on: true, bins: newFtBins(), lastT: 0 };
  T.ve = { phase: "armed", pts: [], peak: null, result: null };
  T.cat = { phase: "idle", up: [], dn: [], up2: [], dn2: [], result: null };
  T.chg = { koeo: T.chg.koeo, idle: null, loaded: null, drive: null };
  Object.assign(T.perf, { mode: null, phase: "idle", pts: [], acc: [], result: null, auto: true });
  extraDriveStart();
  driveRecStart();
  renderTests();
}
function driveTestsTick() {
  const D = T.drive; if (!D.on) return;
  const t = nowS(), rpm = num.rpm ?? 0, v = num.spd ?? 0, load = num.load ?? num.absload ?? 0, volt = num.volt ?? num.cmv;
  // Catalyst: start automatically during steady warm cruise, abort if it stops being steady
  const steady = (num.ect ?? 0) >= 175 && rpm >= 1500 && rpm <= 3200 && v >= 25 && load >= 10 && load <= 60;
  if (!T.cat.result && T.cat.phase !== "run" && steady) T.cat = { phase: "run", t0: t, up: [], dn: [], up2: [], dn2: [], result: null, auto: true };
  if (T.cat.phase === "run" && T.cat.auto && !steady) T.cat.phase = "idle";
  // Charging: idle voltage after 5 s of idling; lowest/average voltage while driving
  if (volt != null) {
    if (v < 1 && rpm > 450 && rpm < 1100) {
      D.idleSince = D.idleSince || t; D.idleV.push(volt);
      if (t - D.idleSince >= 5) { T.chg.idle = { v: avg(D.idleV.slice(-30)), rpm }; }
    } else { D.idleSince = null; D.idleV = []; }
    if (rpm > 1500 && v > 10) { D.dV.push(volt); if (D.dV.length > 2000) D.dV.shift(); T.chg.drive = { min: Math.min(...D.dV), avg: avg(D.dV) }; }
  }
  // Power & braking: arm automatically from a stop, or when above 32 mph
  const P = T.perf;
  if (fresh("spd", 2) && (P.phase === "idle" || P.phase === "done")) {
    if (v <= 0.5) Object.assign(P, { mode: "060", phase: "ready", pts: [], acc: [], auto: true });
    else if (v >= 32) Object.assign(P, { mode: "brake", phase: "ready", pts: [], acc: [], auto: true });
  }
}
function stopDriveTests() {
  const D = T.drive; if (!D.on) return;
  D.on = false;
  if (T.ft.on) { T.ft.on = false; const r = ftAnalyze(); if (r.enough) reportTest("Fuel trim", r.summary, true); }
  if (T.ve.phase !== "done") T.ve.phase = T.ve.result ? "done" : "idle";
  if (T.cat.phase === "run") T.cat.phase = "idle";
  if (T.chg.idle) reportTest("Charging", { idle: T.chg.idle.v, driving_min: T.chg.drive && T.chg.drive.min, verdict: chgVerdict().replace(/<[^>]+>/g, "") }, true);
  Object.assign(T.perf, { phase: "idle", mode: null, auto: false });
  extraDriveStop();
  D.report = driveReportHtml();
  D.minutes = (nowS() - D.t0) / 60;
  driveRecStop();
  renderTests();
  const n = Object.keys(D.done).length;
  lastSpeak = 0; speak(`Test drive done. ${n} test${n === 1 ? "" : "s"} completed. Results are on screen.`);
  aiPendingId = null;  // don't let a pending mid-drive check block the final review
  requestAi("full");   // full AI review including the test results
}
function driveReportHtml() {
  const D = T.drive, rows = [];
  const add = (name, val, grade, note) => rows.push(`<tr><td style="text-align:left">${name}</td><td class="${gradeCls(grade)}">${val}</td><td class="${gradeCls(grade)}">${grade ? gradeTxt(grade) : ""}</td><td style="text-align:left" class="note">${note || ""}</td></tr>`);
  const ft = ftAnalyze();
  if (ft.enough) { const w = ["idle", "cruise", "load"].map((k) => ft.a[k].b1).filter((x) => x != null); add("⛽ Fuel trim", w.map((x) => fmtF(x) + "%").join(" / "), ft.grade, "idle / cruise / load, bank 1"); }
  else add("⛽ Fuel trim", "not enough data", null, "drive longer at idle, cruise and under load");
  if (T.ve.result) add("🌬️ VE / MAF", T.ve.result.ve.toFixed(0) + "%", T.ve.result.grade, `best WOT pull, ${Math.round(T.ve.result.rpm)} RPM`);
  else add("🌬️ VE / MAF", "no WOT pull", null, "floor it once from ~2,000 RPM when safe");
  const c = T.cat.result && T.cat.result.b1;
  if (c) add("♨️ Catalyst", c.ratio == null ? "n/a" : "ratio " + c.ratio.toFixed(2), c.g, "45 s of steady cruise");
  else add("♨️ Catalyst", "not run", null, "needs 45 s of steady cruise, 25+ mph, warm engine");
  if (T.chg.idle || T.chg.drive) {
    const i = T.chg.idle && T.chg.idle.v, m = T.chg.drive && T.chg.drive.min;
    add("🔋 Charging", `${i != null ? i.toFixed(1) + " V idle" : ""}${i != null && m != null ? " · " : ""}${m != null ? m.toFixed(1) + " V min driving" : ""}`, worstGrade([chgGrade("idle", i), chgGrade("loaded", m)]));
  }
  for (const [k, l] of [["030", "🏁 0–30 mph"], ["060", "🏁 0–60 mph"], ["brake", "🛑 30–0 braking"]]) {
    const r = D.perfBest[k];
    if (r) add(l, `${r.time.toFixed(1)} s · ${Math.round(r.distFt)} ft${r.avgG != null ? " · " + r.avgG.toFixed(2) + " g" : ""}`, k === "brake" ? r.grade : null, r.pullSide ? (r.pullSide === "straight" ? "tracks straight" : "pulls " + r.pullSide) : "");
  }
  extraReportRows(add);
  return `<div class="verdict" style="border-color:var(--b)"><b>🚗 Test drive report</b> <span class="note">${new Date().toLocaleTimeString()}</span>
    <table class="ttab">${rows.join("")}</table><span class="note">Tap a test tab for details. The AI review is running below.</span></div>`;
}
function worstGrade(gs) { return gs.includes("r") ? "r" : gs.includes("y") ? "y" : gs.includes("g") ? "g" : null; }
function driveStatusHtml() {
  const D = T.drive; if (!D.on) return D.report || "";
  const B = T.ft.bins || newFtBins(), mins = ((nowS() - D.t0) / 60).toFixed(1);
  const chip = (ok, txt) => `<span style="margin-right:10px" class="${ok ? "grade-g" : "grade-y"}">${ok ? "✓" : "…"} ${txt}</span>`;
  return `<div class="verdict" style="border-color:var(--b)"><b>🚗 Test drive running</b> · ${mins} min — drive normally. When safe, include: idle, steady cruise, one full-throttle pull and one firm stop from 30+ mph.<br>
    ${chip(B.idle.b1.length >= 15, `Idle trims (${B.idle.b1.length})`)}${chip(B.cruise.b1.length >= 15, `Cruise trims (${B.cruise.b1.length})`)}${chip(B.load.b1.length >= 15, `Load trims (${B.load.b1.length})`)}
    ${chip(!!T.ve.result, "WOT pull / VE")}${chip(!!T.cat.result, T.cat.phase === "run" ? `Catalyst (${Math.max(0, CAT_SECS - (nowS() - T.cat.t0)).toFixed(0)} s)` : "Catalyst (steady cruise)")}
    ${chip(!!T.chg.idle, "Charging idle")}${chip(!!D.perfBest["030"], "Launch")}${chip(!!D.perfBest.brake, "Firm stop")}
    ${extraDriveChips(chip)}</div>`;
}
const fresh = (id, maxAge = 3) => numT[id] && nowS() - numT[id] < maxAge;
const gradeCls = (g) => ({ g: "grade-g", y: "grade-y", r: "grade-r" }[g] || "grade-n");
const gradeTxt = (g) => ({ g: "GOOD", y: "MARGINAL", r: "BAD" }[g] || "—");
function fmtF(v, d = 1) { return v == null || !isFinite(v) ? "—" : (v > 0 ? "+" : "") + v.toFixed(d); }
function reportTest(name, summary, quiet) {
  T.results = T.results || {};
  T.results[name] = summary;
  sendValue({ type: "tests", id: "tests-" + Date.now(), results: T.results });
  if (!quiet) speak(`${name} test: ${summary.verdict || summary.grade || "done"}`.slice(0, 160));
  if (T.drive && T.drive.on) T.drive.done[name] = summary;
}

function renderTests() {
  $("driveTests").innerHTML = driveStatusHtml();
  $("drivesBox").innerHTML = savedDrivesHtml();
  $("testTabs").innerHTML = TESTS.map(([k, l]) => `<button data-ttab="${k}" class="${k === testTab ? "on" : ""}">${l}</button>`).join("");
  const body = $("testBody");
  if (testTab === "ft") body.innerHTML = ftHtml();
  if (testTab === "ve") body.innerHTML = veHtml();
  if (testTab === "cat") body.innerHTML = catHtml();
  if (testTab === "chg") body.innerHTML = chgHtml();
  if (testTab === "perf") body.innerHTML = perfHtml();
  if (EXTRA_HTML[testTab]) body.innerHTML = EXTRA_HTML[testTab]();
  drawTestPlots(); drawExtraPlots();
  // redraw the plots once the page has its real width (they were coming up blank when drawn before layout)
  if (!window._plotRO && window.ResizeObserver) {
    let w = 0;
    window._plotRO = new ResizeObserver(() => { if (body.clientWidth !== w) { w = body.clientWidth; try { drawTestPlots(); drawExtraPlots(); } catch (_) {} } });
    window._plotRO.observe(body);
  }
}
document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-ttab]");
  if (t) { testTab = t.dataset.ttab; renderTests(); return; }
  const a = e.target.closest("[data-tact]");
  if (a) testAction(a.dataset.tact);
});
function testAction(act) {
  if (!connected && !/^(perf-(motion|level)|nvh-|tail-|rec-)/.test(act)) { alert("Connect to the vehicle first."); return; }
  if (EXTRA_ACTIONS[act]) { EXTRA_ACTIONS[act](); renderTests(); return; }
  ({
    "ft-start": () => { T.ft.on = true; T.ft.bins = newFtBins(); },
    "ft-stop": () => { T.ft.on = false; const r = ftAnalyze(); if (r.enough) reportTest("Fuel trim", r.summary); },
    "ft-reset": () => { T.ft.bins = newFtBins(); },
    "ve-start": () => { T.ve = { phase: "armed", pts: [], peak: null, result: null }; },
    "ve-cancel": () => { T.ve.phase = "idle"; },
    "cat-start": () => { T.cat = { phase: "run", t0: nowS(), up: [], dn: [], up2: [], dn2: [], result: null }; },
    "cat-cancel": () => { T.cat.phase = "idle"; },
    "chg-koeo": () => chgRecord("koeo"), "chg-idle": () => chgRecord("idle"), "chg-loaded": () => chgRecord("loaded"),
    "chg-reset": () => { T.chg = { koeo: null, idle: null, loaded: null }; },
    "perf-motion": () => perfMotion(), "perf-level": () => perfLevel(),
    "perf-060": () => perfArm("060"), "perf-030": () => perfArm("030"), "perf-brake": () => perfArm("brake"),
    "perf-cancel": () => { T.perf.phase = "idle"; T.perf.mode = null; },
  }[act] || (() => {}))();
  renderTests();
}
let lastTestRender = 0;
function testsTick() {
  driveTestsTick(); ftTick(); veTick(); catTick(); perfTick(); extraTicks();
  const ae = document.activeElement;
  const typing = ae && /INPUT|TEXTAREA|SELECT/.test(ae.tagName) && ae.closest("#tests");
  if (!typing && nowS() - lastTestRender > 0.7) { lastTestRender = nowS(); renderTests(); }
}

// ---------- 1. Fuel trim analyzer ----------
const FT_BINS = [["idle", "Idle"], ["cruise", "Light cruise"], ["load", "Heavy load"]];
function newFtBins() { const b = {}; FT_BINS.forEach(([k]) => (b[k] = { b1: [], b2: [] })); b.pts = []; return b; }
function ftCondition() {
  const rpm = num.rpm, spd = num.spd ?? 0, load = num.load ?? num.absload, tps = num.tps;
  if (rpm == null || load == null) return null;
  if (rpm < 1100 && spd < 3 && (tps == null || tps < 15)) return "idle";
  if (load >= 60 || (tps != null && tps >= 45)) return "load";
  if (rpm >= 1200 && rpm <= 3200 && load < 50) return "cruise";
  return null;
}
function ftTick() {
  if (!T.ft.on || !numT.stft1 || numT.stft1 <= T.ft.lastT) return;
  T.ft.lastT = numT.stft1;
  if ((num.ect ?? 200) < 160) return;   // wait for warm engine / closed loop
  if (!trimsTrustworthy()) return;       // skip decel fuel cut & open loop
  const c = ftCondition(); if (!c) return;
  const t1 = (num.stft1 ?? 0) + (num.ltft1 ?? 0);
  const has2 = fresh("stft2", 10) && num.stft2 != null;
  const t2 = has2 ? (num.stft2 ?? 0) + (num.ltft2 ?? 0) : null;
  T.ft.bins[c].b1.push(t1); if (t2 != null) T.ft.bins[c].b2.push(t2);
  T.ft.bins.pts.push([num.load ?? num.absload, t1, t2, c]);
  if (T.ft.bins.pts.length > 3000) T.ft.bins.pts.shift();
}
const avg = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : null);
const ftGrade = (v) => (v == null ? "n" : Math.abs(v) <= 10 ? "g" : Math.abs(v) <= 20 ? "y" : "r");
function ftAnalyze() {
  const B = T.ft.bins || newFtBins(), MIN = 15;
  const a = {}; FT_BINS.forEach(([k]) => (a[k] = { b1: B[k].b1.length >= MIN ? avg(B[k].b1) : null, b2: B[k].b2.length >= MIN ? avg(B[k].b2) : null, n: B[k].b1.length }));
  const notes = [];
  for (const bank of ["b1", "b2"]) {
    const I = a.idle[bank], C = a.cruise[bank], L = a.load[bank], name = bank === "b1" ? "Bank 1" : "Bank 2";
    const vals = [I, C, L].filter((v) => v != null);
    if (!vals.length) continue;
    const lo = Math.min(...vals), hi = Math.max(...vals);
    if (I != null && I > 10 && ((C != null && I - C >= 7) || (L != null && I - L >= 7)))
      notes.push(`${name}: lean at idle that improves as airflow rises → <b>unmetered air / vacuum leak</b> (intake gasket, PCV, brake booster, hoses). Smoke test it.`);
    else if (L != null && L > 10 && (I == null || L - I >= 7))
      notes.push(`${name}: lean that gets worse with load → <b>fuel delivery</b> (pump, filter, regulator, restricted injectors) <b>or MAF under-reading at high flow</b>. Run the VE test and check fuel pressure/volume under load.`);
    else if (vals.length >= 2 && lo > 10)
      notes.push(`${name}: lean everywhere → <b>MAF under-reading</b>, low fuel pressure, or an exhaust leak ahead of the upstream O2.`);
    else if (vals.length >= 2 && hi < -10)
      notes.push(`${name}: rich everywhere → leaking injector(s), high fuel pressure, purge stuck open, MAF over-reading, or fuel-diluted oil.`);
    else if (vals.length === 1 && Math.abs(vals[0]) > 10)
      notes.push(`${name}: ${vals[0] > 0 ? "lean" : "rich"} (${fmtF(vals[0])}%) in the only condition recorded. <b>Drive at cruise and under load</b> so the pattern can point to the cause.`);
    else if (I != null && I < -10 && (C == null || C - I >= 7))
      notes.push(`${name}: rich at idle only → <b>EVAP purge valve stuck open</b>, leaking injector, or fuel in the oil (pull the PCV / oil cap and retest).`);
  }
  for (const [k, l] of FT_BINS) {
    const x = a[k].b1, y = a[k].b2;
    if (x != null && y != null && Math.abs(x - y) >= 10)
      notes.push(`${l}: banks differ by ${Math.abs(x - y).toFixed(0)}% → problem on <b>${x > y ? "Bank 1" : "Bank 2"}</b> only (that bank's intake leak, injectors, or exhaust leak before its O2). A shared part like the MAF or fuel pump would affect both banks.`);
  }
  const enough = FT_BINS.some(([k]) => a[k].b1 != null);
  const worst = Math.max(...FT_BINS.flatMap(([k]) => [a[k].b1, a[k].b2]).filter((v) => v != null).map(Math.abs), 0);
  const grade = !enough ? "n" : ftGrade(worst);
  if (enough && !notes.length) notes.push("Total fuel trims are within ±10% in every condition recorded — fuel control looks healthy.");
  const summary = {
    grade: gradeTxt(grade),
    idle: { b1: a.idle.b1, b2: a.idle.b2 }, cruise: { b1: a.cruise.b1, b2: a.cruise.b2 }, load: { b1: a.load.b1, b2: a.load.b2 },
    verdict: notes.map((n) => n.replace(/<[^>]+>/g, "")).join(" "),
  };
  return { a, notes, grade, enough, summary };
}
function ftHtml() {
  const r = ftAnalyze(), B = T.ft.bins;
  const cell = (v) => `<td class="${gradeCls(ftGrade(v))}">${v == null ? "—" : fmtF(v) + "%"}</td>`;
  const rows = FT_BINS.map(([k, l]) => `<tr><td style="text-align:left">${l}</td>${cell(r.a[k].b1)}${cell(r.a[k].b2)}<td class="grade-n">${B ? B[k].b1.length : 0}</td></tr>`).join("");
  return `<div class="tsteps">Total fuel trim (short + long term) sorted by driving condition. Start recording with the engine warm, idle a minute, then drive: steady cruise and a few hard pulls. Needs ~15 samples per condition.</div>
    <button class="tbtn" data-tact="${T.ft.on ? "ft-stop" : "ft-start"}">${T.ft.on ? "■ Stop & analyze" : "● Start recording"}</button>
    <button class="tbtn sec" data-tact="ft-reset">Reset</button>
    ${T.ft.on ? `<span class="grade-y">recording…</span>` : ""}
    <table class="ttab"><tr><th style="text-align:left">Condition</th><th>Bank 1</th><th>Bank 2</th><th>Samples</th></tr>${rows}</table>
    <canvas class="tplot" id="ftPlot"></canvas>
    <div class="note">Plot: total trim (y) vs engine load (x). Green ±10% · yellow ±20% · red beyond.</div>
    ${r.enough ? `<div class="verdict"><b class="${gradeCls(r.grade)}">${gradeTxt(r.grade)}</b><br>${r.notes.join("<br>")}</div>` : ""}`;
}

// ---------- 2. Volumetric efficiency ----------
function engineLiters() { const v = parseFloat(T.veDisp || ARGS.disp); return v > 0.5 && v < 10 ? v : null; }
document.addEventListener("input", (e) => { if (e.target.id === "veDisp") T.veDisp = e.target.value; });
function veSample() {
  // VE = actual airflow (MAF) / theoretical airflow of a 4-stroke engine at outside-air density
  const L = engineLiters(), maf = num.maf, rpm = num.rpm;
  if (!L || maf == null || !rpm || rpm < 1000) return null;
  const iatF = num.iat ?? 77, T_K = (iatF - 32) / 1.8 + 273.15;
  const baroKpa = num.baro != null ? num.baro / 0.2953 : (num.map != null ? num.map / 0.145038 : 101.3);
  const rho = baroKpa / (0.28705 * T_K);                 // g per liter
  const theo = (rpm / 2 / 60) * L * rho;                  // g/s at 100% VE
  return { ve: (maf / theo) * 100, maf, theo, rpm };
}
function veTick() {
  const V = T.ve; if (V.phase === "idle" || V.phase === "done") return;
  const wot = (num.tps ?? 0) >= 75 || (num.app ?? 0) >= 75;
  const s = veSample();
  if (V.phase === "armed" && wot && s) V.phase = "run";
  if (V.phase === "run") {
    if (s && wot) { V.pts.push([nowS(), s.maf, s.theo * 0.85, s.ve, s.rpm]); }
    if (!wot && V.pts.length) {
      V.phase = "done";
      const good = V.pts.filter((p) => p[4] >= 3000);
      const use = good.length >= 3 ? good : V.pts;
      const peak = use.reduce((m, p) => (p[3] > m[3] ? p : m), use[0]);
      const g = peak[3] >= 75 ? "g" : peak[3] >= 65 ? "y" : "r";
      const hiTrim = T.ft.bins ? avg(T.ft.bins.load.b1) : null;
      const curTrim = (num.stft1 ?? 0) + (num.ltft1 ?? 0);
      const lean = (hiTrim ?? curTrim) > 10;
      let verdict;
      if (g === "g") verdict = lean ? "Engine breathes normally, but fuel trims go lean under load → suspect <b>fuel delivery</b> (pump, filter, regulator, injectors) rather than the MAF."
        : "Engine breathing and MAF reading look normal.";
      else verdict = lean ? "Low VE <b>and</b> lean fuel trims → the <b>MAF is under-reading</b> airflow (dirty or failing MAF, or air leak after the MAF). Clean/test the MAF."
        : "Low VE with normal fuel trims → the engine really isn't moving air: check for <b>restricted exhaust/catalyst</b>, intake restriction, or cam timing. (Turbo engines read above 100% — this grading is for non-turbo engines.)";
      const res = { ve: peak[3], rpm: peak[4], grade: g, verdict };
      const best = T.drive.on && T.drive.veBest;
      if (best && best.ve >= res.ve) V.result = best;     // keep the strongest WOT pull of the drive
      else {
        V.result = res;
        if (T.drive.on) T.drive.veBest = res;
        reportTest("Volumetric efficiency", { peakVE: Math.round(peak[3]), rpm: Math.round(peak[4]), grade: gradeTxt(g), verdict: verdict.replace(/<[^>]+>/g, "") }, T.drive.on);
      }
      if (T.drive.on) { V.phase = "armed"; V.pts = []; }
    }
  }
}
function veHtml() {
  const V = T.ve, L = engineLiters();
  const live = veSample();
  return `<div class="tsteps">Checks whether the MAF reading matches how much air the engine should pull. Engine warm. In a safe place, in 2nd or 3rd gear (or Low), go <b>wide-open throttle from ~2,000 to ~5,000 RPM</b>, then lift. Non-turbo engines should read about 75–90%.</div>
    <div style="margin-bottom:6px">Engine size: <input id="veDisp" value="${L || ""}" placeholder="liters" style="width:70px;background:var(--card);color:var(--w);border:1px solid var(--line);padding:4px;border-radius:4px"> L
      ${!L ? '<span class="grade-y"> enter engine size (or decode the VIN)</span>' : ""}${num.maf == null ? '<span class="grade-r"> · this vehicle has no MAF reading — VE test needs a MAF</span>' : ""}</div>
    ${V.phase === "idle" || V.phase === "done" ? `<button class="tbtn" data-tact="ve-start">Arm VE test</button>` : `<button class="tbtn sec" data-tact="ve-cancel">Cancel</button>`}
    <span class="${V.phase === "armed" ? "grade-y" : V.phase === "run" ? "grade-g" : "grade-n"}">${{ idle: "", armed: "Armed — floor it when ready…", run: "Recording WOT pull…", done: "" }[V.phase]}</span>
    <span class="note"> Live VE: ${live ? live.ve.toFixed(0) + "%" : "—"}</span>
    <canvas class="tplot" id="vePlot"></canvas>
    <div class="note">Yellow = MAF actual (g/s) · Red = expected airflow at 85% VE. MAF well below red at WOT = under-reading MAF or restriction.</div>
    ${V.result ? `<div class="verdict"><span class="tnum ${gradeCls(V.result.grade)}">${V.result.ve.toFixed(0)}% VE</span> at ${Math.round(V.result.rpm)} RPM · <b class="${gradeCls(V.result.grade)}">${gradeTxt(V.result.grade)}</b><br>${V.result.verdict}</div>` : ""}`;
}

// ---------- 3. Catalyst efficiency ----------
const CAT_SECS = 45;
function crossings(arr, mid) { let n = 0; for (let i = 1; i < arr.length; i++) if ((arr[i - 1] - mid) * (arr[i] - mid) < 0) n++; return n; }
function catTick() {
  const C = T.cat; if (C.phase !== "run") return;
  const t = nowS();
  const upWide = /λ/.test(shown.o2b1s1 || "");
  if (fresh("o2b1s1", 1.5)) C.up.push(upWide ? num.stft1 : num.o2b1s1);   // wideband: use short-term trim oscillation
  if (fresh("o2b1s2", 1.5)) C.dn.push(num.o2b1s2);
  if (fresh("o2b2s2", 1.5) && num.o2b2s2 != null) { C.dn2.push(num.o2b2s2); if (fresh("stft2", 2)) C.up2.push(/λ/.test(shown.o2b2s1 || "") ? num.stft2 : num.o2b2s1); }
  if (t - C.t0 >= CAT_SECS) {
    C.phase = "done";
    const upWideB = /λ/.test(shown.o2b1s1 || "");
    const one = (up, dn, wide) => {
      if (up.length < 20 || dn.length < 20) return null;
      const upX = crossings(up, wide ? avg(up) : 0.45), dnX = crossings(dn, 0.45);
      const ratio = upX ? dnX / upX : null;
      const dAvg = avg(dn), dSpan = Math.max(...dn) - Math.min(...dn);
      const g = ratio == null ? "n" : ratio <= 0.2 && dAvg >= 0.5 ? "g" : ratio <= 0.5 ? "y" : "r";
      return { upX, dnX, ratio, dAvg, dSpan, g };
    };
    C.result = { b1: one(C.up, C.dn, upWideB), b2: one(C.up2, C.dn2, /λ/.test(shown.o2b2s1 || "")) };
    const m6 = (mode6Summary || "").split("\n").filter((l) => /Catalyst/.test(l)).join("; ");
    C.result.m6 = m6;
    const parts = ["b1", "b2"].filter((b) => C.result[b]).map((b) => `${b === "b1" ? "Bank 1" : "Bank 2"} ratio ${C.result[b].ratio == null ? "n/a" : C.result[b].ratio.toFixed(2)} (${gradeTxt(C.result[b].g)})`);
    reportTest("Catalyst", { result: parts.join("; ") || "not enough O2 data", mode6: m6, verdict: parts.join("; ") });
  }
}
function catHtml() {
  const C = T.cat, left = C.phase === "run" ? Math.max(0, CAT_SECS - (nowS() - C.t0)) : 0;
  const warm = (num.ect ?? 0) >= 175;
  const row = (b, r) => !r ? "" : `<tr><td style="text-align:left">${b}</td><td>${r.upX}</td><td>${r.dnX}</td><td class="${gradeCls(r.g)}">${r.ratio == null ? "—" : r.ratio.toFixed(2)}</td><td>${r.dAvg.toFixed(2)} V</td><td class="${gradeCls(r.g)}">${gradeTxt(r.g)}</td></tr>`;
  return `<div class="tsteps">Compares how often the downstream O2 switches versus the upstream sensor. A good cat stores oxygen, so the rear sensor stays steady (~0.6–0.8 V). Engine fully warm (drive 10+ min), in Park, <b>hold ~2,500 RPM</b> for ${CAT_SECS} seconds.</div>
    ${!warm ? `<div class="grade-y">Coolant is ${num.ect != null ? Math.round(num.ect) + "°F" : "unknown"} — warm the engine to at least 175°F first.</div>` : ""}
    ${C.phase === "run" ? `<button class="tbtn sec" data-tact="cat-cancel">Cancel</button> <span class="grade-g">Hold 2,500 RPM… ${left.toFixed(0)} s left (now ${Math.round(num.rpm ?? 0)} RPM)</span>`
      : `<button class="tbtn" data-tact="cat-start">Start catalyst test</button>`}
    ${C.result ? `<table class="ttab"><tr><th style="text-align:left">Bank</th><th>Upstream switches</th><th>Downstream switches</th><th>Ratio</th><th>Rear O2 avg</th><th>Result</th></tr>${row("Bank 1", C.result.b1)}${row("Bank 2", C.result.b2)}</table>
      ${["b1", "b2"].some((b) => C.result[b] && C.result[b].upX < 3) ? `<div class="verdict grade-y">Upstream sensor barely switched — fuel control isn't cycling (or the sensor is lazy). Fix that first; the cat can't be judged until it does.</div>` : ""}
      <div class="verdict">Ratio near 0 = good cat; above ~0.5 = rear sensor copying the front = <b>catalyst not storing oxygen</b>. Before condemning: no exhaust leaks, no misfires, fuel trims normal.${C.result.m6 ? "<br>Mode $06: " + esc(C.result.m6) : ""}</div>` : ""}`;
}

// ---------- 4. Charging system ----------
function chgVolts() { return num.volt ?? num.cmv ?? null; }
function chgRecord(step) {
  const v = chgVolts(); if (v == null) { alert("No voltage reading yet — wait a few seconds."); return; }
  T.chg[step] = { v, rpm: num.rpm ?? 0 };
  if (T.chg.idle && T.chg.loaded) reportTest("Charging", { koeo: T.chg.koeo && T.chg.koeo.v, idle: T.chg.idle.v, loaded: T.chg.loaded.v, verdict: chgVerdict().replace(/<[^>]+>/g, "") });
}
function chgGrade(step, v) {
  if (v == null) return "n";
  if (step === "koeo") return v >= 12.4 ? "g" : v >= 12.2 ? "y" : "r";
  if (step === "idle") return v >= 13.5 && v <= 14.9 ? "g" : v >= 13.2 && v <= 15.2 ? "y" : "r";
  return v >= 13.2 && v <= 14.9 ? "g" : v >= 12.8 ? "y" : "r";
}
function chgVerdict() {
  const k = T.chg.koeo && T.chg.koeo.v, i = T.chg.idle && T.chg.idle.v, out = [];
  const l = T.chg.loaded ? T.chg.loaded.v : (T.chg.drive ? T.chg.drive.min : null);
  if (k != null && k < 12.4) out.push(`Battery resting at ${k.toFixed(2)} V is below a full charge (12.6 V) — charge and load-test the battery.`);
  if (i != null && i > 15.0) out.push("Over-charging at idle — check the regulator / alternator and the voltage-sense circuit.");
  if (i != null && i < 13.2) out.push("Not charging properly at idle — check belt, alternator output, and the B+ and ground cables (voltage drop test).");
  if (l != null && i != null && i - l > 0.7) out.push(`Voltage drops ${(i - l).toFixed(1)} V with loads on — alternator can't keep up: check output amperage, belt slip, and connections.`);
  if (!out.length && i != null && l != null) out.push("Charging system looks healthy. (Many newer vehicles use 'smart charging' and may idle at 12.8–13.2 V on purpose — check the factory spec if borderline.)");
  return out.join(" ");
}
function chgHtml() {
  const step = (k, title, how) => {
    const r = T.chg[k], g = chgGrade(k, r && r.v);
    return `<tr><td style="text-align:left"><b>${title}</b><div class="note">${how}</div></td><td class="${gradeCls(g)}" style="font-size:1.1rem">${r ? r.v.toFixed(2) + " V" : "—"}</td><td class="${gradeCls(g)}">${r ? gradeTxt(g) : ""}</td><td><button class="tbtn" data-tact="chg-${k}">Record</button></td></tr>`;
  };
  return `<div class="tsteps">Live voltage: <b>${chgVolts() != null ? chgVolts().toFixed(2) + " V" : "—"}</b> · ${Math.round(num.rpm ?? 0)} RPM. Do each step in order and tap Record.</div>
    <table class="ttab">${step("koeo", "1 · Key on, engine off", "Resting battery (after sitting a while is best). Good ≥ 12.4 V.")}
    ${step("idle", "2 · Engine idling, everything off", "Good 13.5–14.9 V.")}
    ${step("loaded", "3 · 2,000 RPM, loads on", "Headlights high, blower high, rear defrost on. Should stay ≥ 13.2 V.")}
    ${T.chg.drive ? `<tr><td style="text-align:left"><b>Test drive (automatic)</b><div class="note">Lowest / average while driving</div></td><td class="${gradeCls(chgGrade("loaded", T.chg.drive.min))}" style="font-size:1.1rem">${T.chg.drive.min.toFixed(2)} V</td><td>${T.chg.drive.avg.toFixed(2)} V avg</td><td></td></tr>` : ""}</table>
    <button class="tbtn sec" data-tact="chg-reset">Reset</button>
    ${(T.chg.idle || T.chg.koeo) ? `<div class="verdict">${chgVerdict() || "Finish the remaining steps."}</div>` : ""}`;
}

// ---------- 5. Power & braking (vehicle speed + phone motion sensor) ----------
function perfMotion() {
  const start = () => {
    window.addEventListener("devicemotion", (e) => {
      const a = e.accelerationIncludingGravity; if (!a || a.x == null) return;
      T.perf.motion = { x: a.x, y: a.y, z: a.z, t: nowS() };
      if (T.perf.phase === "run") T.perf.acc.push([nowS(), a.x, a.y, a.z]);
      learnForward(a);
    });
    T.perf.motionOn = true; renderTests();
  };
  if (typeof DeviceMotionEvent !== "undefined" && typeof DeviceMotionEvent.requestPermission === "function")
    DeviceMotionEvent.requestPermission().then((r) => (r === "granted" ? start() : alert("Motion sensor permission was denied."))).catch(() => alert("Motion sensor not available."));
  else if (typeof DeviceMotionEvent !== "undefined") start();
  else alert("This device/browser has no motion sensor access.");
}
function perfLevel() {
  const m = T.perf.motion;
  if (!m || nowS() - m.t > 1) { alert("No motion data yet. Tap 'Enable phone sensor' first (phones/tablets only)."); return; }
  const g = Math.hypot(m.x, m.y, m.z);
  T.perf.cal = { up: [m.x / g, m.y / g, m.z / g] };   // gravity direction with the car parked
  T.perf.fwd = null; fwdSum = [0, 0, 0]; fwdN = 0;
}
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
function horizOf(x, y, z) { const up = T.perf.cal.up, k = x * up[0] + y * up[1] + z * up[2]; return [x - k * up[0], y - k * up[1], z - k * up[2]].map((c) => c / 9.81); }
// Learn which way is "forward" for the phone from straight-line acceleration (speed rising, low speed)
let fwdSum = [0, 0, 0], fwdN = 0, spdHist = [];
function learnForward(a) {
  if (!T.perf.cal) return;
  const t = nowS();
  if (fresh("spd", 1)) { spdHist.push([t, num.spd]); spdHist = spdHist.filter((p) => t - p[0] < 1.2); }
  if (spdHist.length < 2) return;
  const dv = spdHist[spdHist.length - 1][1] - spdHist[0][1], v = num.spd;
  if (dv < 1.5 || v < 2 || v > 45) return;          // only while clearly speeding up
  const h = horizOf(a.x, a.y, a.z);
  if (Math.hypot(...h) < 0.05) return;
  fwdSum = fwdSum.map((c, i) => c + h[i]); fwdN++;
  if (fwdN >= 15) { const n = Math.hypot(...fwdSum); T.perf.fwd = fwdSum.map((c) => c / n); }
}
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
function perfArm(mode) { T.perf = Object.assign(T.perf, { mode, phase: "armed", pts: [], acc: [], result: null }); }
function perfTick() {
  const P = T.perf; if (!P.mode || P.phase === "idle" || P.phase === "done" || !fresh("spd", 2)) return;
  const v = num.spd, t = numT.spd;
  if (P.pts.length && P.pts[P.pts.length - 1][0] === t) return;
  if (P.mode === "brake") {
    if (P.phase === "armed" && v >= 32) P.phase = "ready";
    if (P.phase === "ready" && v <= 30) { P.phase = "run"; P.pts = [[t, v]]; P.acc = []; }
    else if (P.phase === "run") {
      if (P.auto && v > P.pts[0][1] + 2) { P.phase = "idle"; return; }   // sped back up: not a stop
      P.pts.push([t, v]); if (v <= 0.5) perfFinish();
    }
  } else {
    const target = P.mode === "060" ? 60 : 30;
    if (P.phase === "armed" && v <= 0.5) P.phase = "ready";
    if (P.phase === "ready" && v > 0.5) { P.phase = "run"; P.pts = [[t, 0]]; P.acc = []; P.vmax = 0; P.split = 0; }
    else if (P.phase === "run") {
      P.pts.push([t, v]); P.vmax = Math.max(P.vmax, v);
      if (!P.split && v >= 30) P.split = P.pts.length;
      if (v >= target) perfFinish();
      else if (P.auto && (v < P.vmax - 3 || t - P.pts[0][0] > 30)) perfFinish(true);   // lifted before 60
    }
  }
}
function perfFinish(partial) {
  const P = T.perf;
  if (P.auto) return perfAutoFinish(partial);
  P.phase = "done";
  const res = perfCompute(P.mode, P.pts);
  P.result = res;
  const label = { "060": "0-60 mph", "030": "0-30 mph", brake: "30-0 mph braking" }[P.mode];
  reportTest(label, perfSummary(res, label));
}
function perfSummary(res, label) {
  return { time_s: +res.time.toFixed(2), distance_ft: Math.round(res.distFt), avg_g: res.avgG && +res.avgG.toFixed(2), peak_g: res.peakG && +res.peakG.toFixed(2),
    pull: res.pullSide ? `${res.pullSide} (${Math.abs(res.pullG).toFixed(2)} g)` : undefined, verdict: `${label} in ${res.time.toFixed(1)} seconds` };
}
// Test-drive mode: keep the best launch (0-30, 0-60) and the hardest stop; ignore gentle driving
function perfAutoFinish(partial) {
  const P = T.perf, results = [];
  if (P.mode === "brake") {
    const r = perfCompute("brake", P.pts);
    if ((r.avgG ?? 0) >= 0.3) results.push(["brake", r]);
  } else {
    if (P.split) results.push(["030", perfCompute("030", P.pts.slice(0, P.split))]);
    if (!partial) results.push(["060", perfCompute("060", P.pts)]);
  }
  for (const [mode, r] of results) {
    const best = T.drive.perfBest[mode];
    const better = !best || (mode === "brake" ? r.avgG > best.avgG : r.time < best.time);
    if (better) {
      T.drive.perfBest[mode] = r; P.result = r;
      const label = { "060": "0-60 mph", "030": "0-30 mph", brake: "30-0 mph braking" }[mode];
      reportTest(label, perfSummary(r, label), true);
    }
  }
  P.phase = "idle";
}
function perfCompute(mode, pts) {
  const P = T.perf;
  const t = pts[pts.length - 1][0] - pts[0][0];
  let distFt = 0; for (let i = 1; i < pts.length; i++) distFt += ((pts[i][1] + pts[i - 1][1]) / 2) * 1.46667 * (pts[i][0] - pts[i - 1][0]);
  const dv = Math.abs(pts[pts.length - 1][1] - pts[0][1]) * 0.44704;   // m/s
  const avgG = t > 0 ? dv / t / 9.81 : null;
  let peakG = null, pullG = null;
  if (P.cal && P.acc.length > 5) {
    const up = P.cal.up;
    const horiz = P.acc.map(([, x, y, z]) => horizOf(x, y, z));
    // forward axis = dominant horizontal direction of the event
    const sum = horiz.reduce((s, h) => [s[0] + h[0], s[1] + h[1], s[2] + h[2]], [0, 0, 0]);
    const n = Math.hypot(...sum) || 1, ev = sum.map((c) => c / n);
    const fwd = P.fwd || (mode === "brake" ? null : ev);   // learned forward axis (from a straight launch)
    peakG = Math.max(...horiz.map((h) => Math.abs(dot(h, fwd || ev))));
    if (mode === "brake" && fwd) pullG = avg(horiz.map((h) => dot(h, cross(fwd, up))));   // + = toward the car's right
  }
  const res = { mode, time: t, distFt, avgG, peakG, pullG };
  if (mode === "brake") {
    res.grade = avgG == null ? "n" : avgG >= 0.7 ? "g" : avgG >= 0.5 ? "y" : "r";
    if (pullG != null) res.pullSide = Math.abs(pullG) < 0.04 ? "straight" : (pullG > 0 ? "right" : "left");
  } else {
    res.grade = "n";
  }
  return res;
}
function perfHtml() {
  const P = T.perf, r = P.result;
  const status = { armed: P.mode === "brake" ? "Armed — get above 32 mph, then brake firmly to a stop" : "Armed — come to a full stop, then accelerate hard",
    ready: P.mode === "brake" ? "Ready — brake when you want; timing starts at 30 mph" : "Ready — go!", run: "Recording…" }[P.phase] || "";
  return `<div class="tsteps">Time and distance come from the vehicle's speed. Add your phone's motion sensor for g-force and <b>brake pull</b>: mount the phone solidly, tap Enable, then <b>Level</b> while parked. Only test in a safe, legal place.</div>
    <button class="tbtn sec" data-tact="perf-motion">${P.motionOn ? "✓ Phone sensor on" : "📱 Enable phone sensor"}</button>
    <button class="tbtn sec" data-tact="perf-level">${P.cal ? "✓ Leveled (re-level)" : "Level (car parked)"}</button>
    ${P.cal ? `<span class="${P.fwd ? "grade-g" : "grade-y"}">${P.fwd ? "✓ Forward direction learned" : "Then accelerate from a stop in a straight line once to learn 'forward'"}</span>` : ""}<br>
    <button class="tbtn" data-tact="perf-060">0–60 mph</button><button class="tbtn" data-tact="perf-030">0–30 mph</button><button class="tbtn" data-tact="perf-brake">30–0 braking</button>
    ${P.phase !== "idle" && P.phase !== "done" ? `<button class="tbtn sec" data-tact="perf-cancel">Cancel</button>` : ""}
    <div class="grade-y">${status} ${P.phase !== "idle" && P.phase !== "done" ? `· ${Math.round(num.spd ?? 0)} mph` : ""}</div>
    ${r ? `<div class="verdict"><span class="tnum">${r.time.toFixed(1)} s</span> · ${Math.round(r.distFt)} ft
      ${r.avgG != null ? ` · avg ${r.avgG.toFixed(2)} g` : ""}${r.peakG != null ? ` · peak ${r.peakG.toFixed(2)} g` : ""}
      ${r.mode === "brake" ? `<br>Braking: <b class="${gradeCls(r.grade)}">${gradeTxt(r.grade)}</b> (good ≥ 0.7 g average on dry pavement)` : ""}
      ${r.pullSide ? `<br>Pull: <b>${r.pullSide === "straight" ? "tracks straight" : "pulls " + r.pullSide.toUpperCase()}</b> (${Math.abs(r.pullG).toFixed(2)} g sideways)`
        : r.mode === "brake" ? `<br><span class='note'>${P.cal ? "Brake pull needs one straight-line launch first (accelerate from a stop in a straight line) so the app learns which way is forward — then rerun." : "Enable + level the phone sensor to measure brake pull."}</span>` : ""}
      </div>` : ""}`;
}

// ---------- plots ----------
function plotSetup(id) {
  const cv = $(id); if (!cv) return null;
  const dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
  cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
  const g = cv.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0);
  const css = getComputedStyle(document.documentElement);
  return { g, W, H, c: (n) => css.getPropertyValue(n).trim() };
}
function axes(P, x0, x1, y0, y1, L = 40, B = 18) {
  const { g, W, H, c } = P, pw = W - L - 8, ph = H - B - 8;
  const X = (x) => L + (x - x0) / (x1 - x0) * pw, Y = (y) => 8 + (1 - (y - y0) / (y1 - y0)) * ph;
  g.strokeStyle = c("--line"); g.fillStyle = c("--muted"); g.font = "10px sans-serif"; g.lineWidth = 1;
  return { X, Y, pw, ph, L, B };
}
function drawTestPlots() {
  if (testTab === "ft") {
    const P = plotSetup("ftPlot"); if (!P) return;
    const A = axes(P, 0, 100, -30, 30), { g, c } = P;
    for (const y of [-20, -10, 0, 10, 20]) { g.beginPath(); g.moveTo(A.L, A.Y(y)); g.lineTo(A.L + A.pw, A.Y(y)); g.stroke(); g.textAlign = "right"; g.fillText((y > 0 ? "+" : "") + y + "%", A.L - 4, A.Y(y) + 3); }
    g.textAlign = "center"; [0, 25, 50, 75, 100].forEach((x) => g.fillText(x + "%", A.X(x), P.H - 4));
    const pts = T.ft.bins ? T.ft.bins.pts : [];
    const dotAt = (x, y, col) => { g.fillStyle = col; g.beginPath(); g.arc(A.X(Math.min(100, x)), A.Y(Math.max(-30, Math.min(30, y))), 3, 0, 7); g.fill(); };
    pts.forEach((p) => { dotAt(p[0], p[1], c("--y")); if (p[2] != null) dotAt(p[0], p[2], c("--b")); });
    if (!pts.length) { g.fillStyle = c("--muted"); g.font = "12px sans-serif"; g.textAlign = "center";
      g.fillText("Tap Start recording — each dot is a trim reading (across = engine load %).", A.L + A.pw / 2, A.Y(0) - 10); g.font = "10px sans-serif"; }
    g.textAlign = "left";
    [["Bank 1", c("--y"), 0], ["Bank 2", c("--b"), 62]].forEach(([l, col, dx]) => { g.fillStyle = col; g.beginPath(); g.arc(A.L + 10 + dx, 15, 4, 0, 7); g.fill(); g.fillStyle = c("--muted"); g.fillText(l, A.L + 17 + dx, 18); });
  }
  if (testTab === "ve") {
    const P = plotSetup("vePlot"); if (!P) return;
    const pts = T.ve.pts; const { g, c } = P;
    if (!pts.length) { g.fillStyle = c("--muted"); g.font = "12px sans-serif"; g.fillText("Waiting for a wide-open-throttle pull…", 44, 90); return; }
    const t0 = pts[0][0], t1 = Math.max(pts[pts.length - 1][0], t0 + 1), hi = Math.max(...pts.map((p) => Math.max(p[1], p[2]))) * 1.1;
    const A = axes(P, t0, t1, 0, hi);
    for (let k = 0; k <= 2; k++) { const v = hi * k / 2; g.beginPath(); g.moveTo(A.L, A.Y(v)); g.lineTo(A.L + A.pw, A.Y(v)); g.stroke(); g.textAlign = "right"; g.fillText(v.toFixed(0), A.L - 4, A.Y(v) + 3); }
    const line = (i, col) => { g.strokeStyle = col; g.lineWidth = 2; g.beginPath(); pts.forEach((p, j) => (j ? g.lineTo(A.X(p[0]), A.Y(p[i])) : g.moveTo(A.X(p[0]), A.Y(p[i])))); g.stroke(); };
    line(2, c("--r")); line(1, c("--y"));
    g.fillStyle = c("--muted"); g.textAlign = "left"; g.fillText("g/s", 4, 12);
  }
}

// ===================== More tests: freeze frame, misfire monitor, readiness coach, vacuum, warm-up,
// cranking, transmission, vibration (NVH), tailpipe listener, record / compare / export =====================
let sup01 = null, freezeFrame = null, misMids = [];
T.inp = T.inp || {};
document.addEventListener("input", (e) => { const k = e.target.dataset && e.target.dataset.tin; if (k) T.inp[k] = e.target.value; });
const inp = (k, ph, w = 90) => `<input data-tin="${k}" value="${esc(T.inp[k] || "")}" placeholder="${ph}" style="width:${w}px;background:var(--card);color:var(--w);border:1px solid var(--line);padding:4px 6px;border-radius:4px">`;
const btn = (act, label, sec) => `<button class="tbtn${sec ? " sec" : ""}" data-tact="${act}">${label}</button>`;
const sd = (a) => { if (a.length < 2) return 0; const m = avg(a); return Math.sqrt(avg(a.map((x) => (x - m) ** 2))); };
function cylCount() { const v = parseInt(T.inp.cyl || ARGS.cyl, 10); return v >= 2 && v <= 12 ? v : null; }

// ---------- Freeze frame (Mode $02) ----------
async function readFreezeFrame() {
  try {
    const r = messages(await sendCmd("020200", 1500)).find((m) => m.startsWith("420200"));
    const code = r && r.length >= 10 && r.substr(6, 4) !== "0000" ? decodeDtc(r.substr(6, 4)) : null;
    if (!code) { freezeFrame = null; renderFreeze(); return; }
    const want = ["03", "04", "05", "06", "07", "08", "09", "0A", "0B", "0C", "0D", "0E", "0F", "10", "11", "23", "2F", "33", "42", "43", "44", "1F", "31", "21", "46"];
    const vals = {};
    for (const p of want) {
      if (sup01 && !sup01.has(p)) continue;
      const m = messages(await sendCmd("02" + p + "00", 700)).find((x) => x.startsWith("42" + p + "00"));
      const d = PIDS[p];
      if (!m || !d) continue;
      const b = bytesOf(m.slice(6));
      if (b.length < d.len) continue;
      const t = d.fn(b); if (t != null) vals[LABEL[d.tile] || d.tile] = t;
    }
    freezeFrame = { dtc: code, vals };
  } catch (_) { freezeFrame = null; }
  renderFreeze();
}
function renderFreeze() {
  const box = $("ffBox");
  if (!freezeFrame) { box.style.display = "none"; return; }
  box.style.display = "block";
  box.innerHTML = `<div style="color:var(--w);font-weight:700;margin-bottom:6px">❄️ Freeze frame — conditions when <span style="color:var(--r)">${esc(freezeFrame.dtc)}</span> set</div>
    <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(120px,1fr));margin:0">${Object.entries(freezeFrame.vals).map(([k, v]) =>
      `<div class="tile" style="cursor:default"><div class="l">${esc(k)}</div><div class="v" style="color:var(--b);font-size:1rem">${esc(v)}</div></div>`).join("")}</div>`;
}

// ---------- background polls (misfire counters, this-drive monitors) ----------
let misRR = 0, misLive = {}, misEvents = [], r41 = null;
async function extraPolls(cycle) {
  if (!isCan) return;
  const focus = T.drive.on || ["mis", "rdy"].includes(testTab);
  if (misMids.length && cycle % (focus ? 3 : 15) === 0) await txn(pollMisfires);
  if (cycle % (focus ? 10 : 40) === 0) await txn(pollMonitors41);
}
async function pollMisfires() {
  const ids = [...new Set([misMids[misRR % misMids.length], misMids[(misRR + 1) % misMids.length]])];
  misRR += 2;
  for (const mid of ids) {
    const cur = parse06(await sendCmd("06" + mid, 800), mid).find((r) => r.tid === 0x0C);
    if (!cur) continue;
    const cyl = parseInt(mid, 16) - 0xA1;
    const L = misLive[cyl] || (misLive[cyl] = { cur: cur.v, tot: 0 });
    if (cur.v > L.cur) {
      const n = cur.v - L.cur; L.tot += n;
      misEvents.push({ cyl, n, rpm: num.rpm, load: num.load, ect: num.ect, spd: num.spd, at: new Date().toLocaleTimeString() });
      if (misEvents.length > 300) misEvents.shift();
      speak(`Misfire, cylinder ${cyl}`);
    }
    L.cur = cur.v;
  }
}
async function pollMonitors41() {
  const m = messages(await sendCmd("0141", 800)).find((x) => x.startsWith("4141") && x.length >= 12);
  if (!m) return;
  const [, B, C, D] = bytesOf(m.slice(4, 12));
  const prev = r41;
  r41 = { B, C, D, at: new Date().toLocaleTimeString() };
  // Drive cycle coach: announce each monitor the moment it completes on this drive
  if (driveOn && prev) {
    const was = new Set(readinessRows(prev.B, prev.C, prev.D, true).filter((r) => !r.done).map((r) => r.n));
    for (const r of readinessRows(B, C, D, true)) if (r.done && was.has(r.n)) speak(`${r.n} monitor completed.`);
  }
}

// ---------- 🔥 Misfire monitor ----------
function misAnalyze() {
  const tot = Object.entries(misLive).map(([c, L]) => [+c, L.tot]).filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1]);
  const all = tot.reduce((s, [, n]) => s + n, 0);
  if (!all) return { all, text: "No new misfires counted since monitoring started." };
  const lines = [];
  if (tot.length === 1 || tot[0][1] >= all * 0.75)
    lines.push(`<b>Cylinder ${tot[0][0]}</b> has ${Math.round(tot[0][1] / all * 100)}% of the misfires → swap that coil (and plug) with a neighbor and retest. Misfire follows the part = coil/plug; stays on cylinder ${tot[0][0]} = injector, compression or valve (run a compression/leak-down or relative compression on the scope).`);
  else if (tot.length >= 3)
    lines.push("Misfires spread across several cylinders → look for a shared cause: vacuum leak, low fuel pressure/volume, EGR stuck open, contaminated fuel, cam/crank timing, or a weak ignition supply.");
  else lines.push(`Misfires on cylinders ${tot.map(([c]) => c).join(" & ")} → if they share a coil pack, injector circuit or bank, check that first.`);
  const ev = misEvents.slice(-80);
  if (ev.length >= 3) {
    const idle = ev.filter((e) => (e.spd ?? 0) < 3).length, load = ev.filter((e) => (e.load ?? 0) >= 60).length, cold = ev.filter((e) => (e.ect ?? 200) < 150).length;
    if (load >= ev.length * 0.6) lines.push("Mostly <b>under load</b> → ignition breakdown (coil, plug gap, boots) or lean under load (fuel delivery).");
    if (idle >= ev.length * 0.6) lines.push("Mostly <b>at idle</b> → vacuum leak, injector, valve sealing or carbon; compare fuel trims at idle.");
    if (cold >= ev.length * 0.6) lines.push("Mostly <b>cold</b> → injector leakdown, carbon on intake valves (direct injection), or sticking valve.");
  }
  return { all, text: lines.join("<br>"), worst: tot[0] };
}
function misHtml() {
  if (!misMids.length) return `<div class="tsteps">This vehicle doesn't report per-cylinder misfire counters (Mode $06 MIDs A2+). The OEM section may still show misfire counts if the factory list has them.</div>`;
  const cyls = misMids.map((m) => parseInt(m, 16) - 0xA1);
  const max = Math.max(1, ...cyls.map((c) => (misLive[c] ? misLive[c].tot : 0)));
  const bars = cyls.map((c) => {
    const L = misLive[c] || { cur: "—", tot: 0 };
    return `<div style="display:flex;align-items:center;gap:8px;margin:3px 0"><span style="width:60px">Cyl ${c}</span>
      <div style="flex:1;background:var(--bg);border-radius:3px;height:14px"><div style="width:${L.tot / max * 100}%;min-width:${L.tot ? 4 : 0}px;height:14px;border-radius:3px;background:var(--r)"></div></div>
      <span style="width:150px" class="note"><b style="color:var(--w)">${L.tot}</b> new · ${L.cur} this cycle</span></div>`;
  }).join("");
  const a = misAnalyze();
  const ev = misEvents.slice(-8).reverse().map((e) => `<tr><td>${e.at}</td><td>Cyl ${e.cyl}</td><td>${e.n}</td><td>${Math.round(e.rpm ?? 0)}</td><td>${Math.round(e.load ?? 0)}%</td><td>${Math.round(e.spd ?? 0)} mph</td><td>${Math.round(e.ect ?? 0)}°F</td></tr>`).join("");
  return `<div class="tsteps">Live per-cylinder misfire counters from the ECM (updates every few seconds; spoken alert on each new misfire). Drive or idle the way the customer describes.</div>
    ${btn("mis-reset", "Reset counts", 1)}
    <div style="margin:8px 0">${bars}</div>
    ${ev ? `<table class="ttab"><tr><th>Time</th><th>Cyl</th><th>Count</th><th>RPM</th><th>Load</th><th>Speed</th><th>Coolant</th></tr>${ev}</table>` : ""}
    <div class="verdict">${a.text}</div>`;
}

// ---------- 📋 Readiness coach (PID $41: monitors this drive cycle) ----------
const MON_TIPS = {
  "Catalyst": "Warm engine, then steady 45–60 mph with light throttle for 3–5 minutes.",
  "Heated Catalyst": "Same as catalyst: warm, steady cruise for several minutes.",
  "EVAP": "Fuel 15–85%. Usually needs an overnight cold soak (6–8 h), cold start, a 10+ min drive with steady cruise, then idle/key-off. Some makes run it after key-off.",
  "Secondary Air": "Cold start (coolant below ~100°F) and idle 1–2 minutes.",
  "A/C Refrigerant": "Rarely used.",
  "O2 Sensor": "Warm engine, steady 40–55 mph for 3 minutes, then a few long coast-downs without braking (fuel cut).",
  "O2 Heater": "Cold start and idle 2 minutes; some cars finish it after key-off.",
  "EGR / VVT": "Several coast-downs from 50+ mph off the throttle, plus steady 35–55 mph cruising.",
  "Misfire": "Runs continuously during normal driving.", "Fuel System": "Runs continuously once in closed loop.",
  "Comprehensive": "Runs continuously.",
};
function readinessRows(B, C, D, thisDrive) {
  const names = ["Catalyst", "Heated Catalyst", "EVAP", "Secondary Air", "A/C Refrigerant", "O2 Sensor", "O2 Heater", "EGR / VVT"];
  const rows = [["Misfire", 0, 4], ["Fuel System", 1, 5], ["Comprehensive", 2, 6]].map(([n, sb, rb]) => ({ n, sup: (B >> sb) & 1, done: !((B >> rb) & 1) }));
  names.forEach((n, bit) => rows.push({ n, sup: (C >> bit) & 1, done: !((D >> bit) & 1) }));
  return rows.filter((r) => r.sup || !thisDrive);
}
let r01raw = null;
function rdyHtml() {
  let since = null;
  const m = (readinessSummary || "");
  const rows = r41 ? readinessRows(r41.B, r41.C, r41.D, true) : [];
  const left = rows.filter((r) => !r.done);
  return `<div class="tsteps">Shows which emissions monitors have finished <b>on this drive</b> (updates every ~20 s) and what driving each remaining one needs. Overall status since codes were cleared: ${esc(m || "not read")}</div>
    ${btn("rdy-refresh", "Refresh now", 1)} <span class="note">${r41 ? "updated " + r41.at : "waiting for first reading…"}</span>
    ${rows.length ? `<table class="ttab"><tr><th style="text-align:left">Monitor</th><th>This drive</th><th style="text-align:left">How to finish it</th></tr>${rows.map((r) =>
      `<tr><td style="text-align:left">${r.n}</td><td class="${r.done ? "grade-g" : "grade-y"}">${r.done ? "✓ complete" : "… running"}</td><td style="text-align:left" class="note">${r.done ? "" : MON_TIPS[r.n] || ""}</td></tr>`).join("")}</table>` : ""}
    ${r41 ? `<div class="verdict">${left.length ? `${left.length} monitor(s) still running: <b>${left.map((r) => r.n).join(", ")}</b>. Exact drive cycles vary by make — check service info for the factory procedure.` : "All supported monitors have completed on this drive. ✓"}</div>` : ""}`;
}

// ---------- 🧭 Electronic vacuum gauge (from MAP) ----------
T.vac = { trace: [], idle: null, snap: null, hold: null, step: null, buf: [], t0: 0 };
function vacNow() {
  if (num.map == null || !fresh("map", 3)) return null;
  const baro = num.baro ?? 29.92;            // inHg
  return baro - num.map * 2.03602;           // psi -> inHg
}
function vacTick() {
  const v = vacNow(); if (v == null) return;
  const t = nowS(), V = T.vac;
  if (!V.trace.length || t - V.trace[V.trace.length - 1][0] >= 0.15) { V.trace.push([t, v]); V.trace = V.trace.filter((p) => t - p[0] < 40); }
  if (!V.step) return;
  V.buf.push([t, v, num.rpm ?? 0, num.tps ?? 0]);
  const el = t - V.t0;
  if (V.step === "idle" && el >= 10) { const a = V.buf.map((p) => p[1]); V.idle = { avg: avg(a), sd: sd(a), min: Math.min(...a), max: Math.max(...a) }; V.step = null; vacReport(); }
  if (V.step === "hold" && el >= 30) {
    const ok = V.buf.filter((p) => p[2] >= 2000 && p[2] <= 3000);
    if (ok.length < 20) { V.hold = { error: "RPM wasn't held near 2,500 — try again." }; }
    else { const first = avg(ok.slice(0, 15).map((p) => p[1])), last = avg(ok.slice(-15).map((p) => p[1])); V.hold = { first, last, drop: first - last }; }
    V.step = null; vacReport();
  }
  if (V.step === "snap") {
    const snapped = V.buf.some((p) => p[3] >= 60);
    if (snapped && el > 1 && V.buf[V.buf.length - 1][3] < 20 && !V.relT) V.relT = t;
    if ((V.relT && t - V.relT > 2.5) || el > 12) {
      const a = V.buf.map((p) => p[1]), i = V.idle ? V.idle.avg : null;
      const after = V.relT ? V.buf.filter((p) => p[0] >= V.relT).map((p) => p[1]) : [];
      V.snap = snapped ? { min: Math.min(...a), peak: after.length ? Math.max(...after) : null, idle: i } : { error: "No throttle snap detected — snap it quickly to wide open and release." };
      V.step = null; V.relT = null; vacReport();
    }
  }
}
function vacVerdict() {
  const V = T.vac, out = []; let g = "g";
  if (V.idle) {
    const a = V.idle.avg;
    if (V.idle.sd > 1.5) { out.push(`Idle needle <b>flutters</b> (±${V.idle.sd.toFixed(1)} inHg) → burnt/sticking valve, misfire, or leaking intake runner. Check misfire counters.`); g = "r"; }
    else if (a < 15) { out.push(`Idle vacuum low (${a.toFixed(1)} inHg) → <b>vacuum leak</b>, late cam/ignition timing, or low compression. Smoke test and check timing.`); g = "r"; }
    else if (a < 17) { out.push(`Idle vacuum a bit low (${a.toFixed(1)} inHg) → small leak, retarded timing, or worn engine. (Lower is normal at high altitude; aggressive cams also idle lower.)`); g = "y"; }
    else out.push(`Idle vacuum ${a.toFixed(1)} inHg and steady → normal.`);
  }
  if (V.snap && !V.snap.error) {
    const i = V.snap.idle ?? (V.idle && V.idle.avg);
    if (V.snap.peak != null && i != null && V.snap.peak < i + 1.5) { out.push("On snap release the vacuum didn't overshoot idle → worn rings, poor valve sealing, or <b>exhaust restriction</b>."); g = g === "r" ? "r" : "y"; }
    else out.push("Snap test: vacuum dropped and rebounded above idle → rings and valves sealing OK.");
  }
  if (V.hold && !V.hold.error) {
    if (V.hold.drop >= 3) { out.push(`At 2,500 RPM vacuum fell ${V.hold.drop.toFixed(1)} inHg over 30 s → <b>exhaust restriction</b> (clogged cat/muffler). Confirm with back-pressure test or the VE test.`); g = "r"; }
    else out.push(`2,500 RPM hold steady (${V.hold.last.toFixed(1)} inHg) → no exhaust restriction.`);
  }
  return { g, text: out.join("<br>") };
}
function vacReport() { const r = vacVerdict(); if (r.text) reportTest("Vacuum (MAP)", { idle: T.vac.idle && +T.vac.idle.avg.toFixed(1), hold_drop: T.vac.hold && T.vac.hold.drop != null ? +T.vac.hold.drop.toFixed(1) : undefined, grade: gradeTxt(r.g), verdict: r.text.replace(/<[^>]+>/g, "") }, true); }
function vacHtml() {
  const V = T.vac, v = vacNow(), r = vacVerdict();
  if (!active.includes("0B")) return `<div class="tsteps">This vehicle doesn't report a MAP sensor, so the electronic vacuum gauge can't run. Use a mechanical gauge or a pressure transducer on the scope.</div>`;
  const left = V.step ? Math.max(0, (V.step === "hold" ? 30 : V.step === "idle" ? 10 : 12) - (nowS() - V.t0)).toFixed(0) : "";
  return `<div class="tsteps">Uses the MAP sensor as a vacuum gauge (corrected for altitude with the baro reading). Engine warm, in Park/Neutral. Run the three steps in order.</div>
    <div><span class="tnum" style="color:var(--b)">${v != null ? v.toFixed(1) : "—"}</span> inHg vacuum · ${Math.round(num.rpm ?? 0)} RPM ${V.step ? `<span class="grade-y"> · recording ${V.step} (${left}s)</span>` : ""}</div>
    ${btn("vac-idle", "1 · Idle (10 s)")}${btn("vac-snap", "2 · Snap throttle")}${btn("vac-hold", "3 · Hold 2,500 RPM (30 s)")}${btn("vac-reset", "Reset", 1)}
    <canvas class="tplot" id="vacPlot"></canvas>
    <table class="ttab"><tr><th>Idle</th><th>Snap low / rebound</th><th>2,500 hold start → end</th></tr>
    <tr><td>${V.idle ? `${V.idle.avg.toFixed(1)} (±${V.idle.sd.toFixed(1)})` : "—"}</td><td>${V.snap ? (V.snap.error || `${V.snap.min.toFixed(1)} / ${V.snap.peak != null ? V.snap.peak.toFixed(1) : "—"}`) : "—"}</td>
    <td>${V.hold ? (V.hold.error || `${V.hold.first.toFixed(1)} → ${V.hold.last.toFixed(1)}`) : "—"}</td></tr></table>
    ${r.text ? `<div class="verdict"><b class="${gradeCls(r.g)}">${gradeTxt(r.g)}</b><br>${r.text}</div>` : ""}`;
}

// ---------- 🌡️ Warm-up / thermostat ----------
T.warm = { on: false, pts: [], t0: 0, result: null };
function warmTick() {
  const W = T.warm; if (!W.on || !fresh("ect", 8)) return;
  const t = nowS();
  if (!W.pts.length || t - W.pts[W.pts.length - 1][0] >= 2) W.pts.push([t, num.ect, num.spd ?? 0, num.iat ?? null]);
  const mins = (t - W.t0) / 60, maxT = Math.max(...W.pts.map((p) => p[1]));
  const driveMin = W.pts.filter((p) => p[2] > 20).length * 2 / 60;
  if (maxT >= 235) W.result = { g: "r", text: `Coolant reached ${Math.round(maxT)}°F → <b>overheating</b>: check coolant level, fan operation, thermostat stuck closed, water pump, radiator flow, head gasket (combustion gas in coolant).` };
  else if (W.pts.some((p) => p[1] >= 185)) {
    const t180 = W.pts.find((p) => p[1] >= 180); const m = (t180[0] - W.t0) / 60;
    W.result = { g: m <= 15 ? "g" : "y", text: `Reached 180°F in ${m.toFixed(1)} min${W.pts[0][1] > 120 ? " (engine wasn't fully cold at start)" : ""} → thermostat opening ${m <= 15 ? "normally" : "late/slow — check thermostat & fan clutch"}.` };
  } else if (driveMin >= 8 && maxT < 172) W.result = { g: "r", text: `After ${driveMin.toFixed(0)} min of driving coolant is only ${Math.round(maxT)}°F → <b>thermostat stuck open</b> (classic P0128). Verify the ECT sensor reading with an IR gun first.` };
  else W.result = null;
  if (W.result && !W.reported && (W.result.g !== "g" || mins > 1)) { W.reported = true; reportTest("Warm-up / thermostat", { minutes: +mins.toFixed(1), max_F: Math.round(maxT), grade: gradeTxt(W.result.g), verdict: W.result.text.replace(/<[^>]+>/g, "") }, T.drive.on); }
}
function warmHtml() {
  const W = T.warm;
  return `<div class="tsteps">Start with a <b>cold engine</b> (sat 4+ hours). Tap Start, then idle or drive normally. Watches how fast coolant warms up: thermostat stuck open, slow warm-up, or overheating. Runs automatically on a test drive when the engine starts cold.</div>
    ${W.on ? btn("warm-stop", "■ Stop") : btn("warm-start", "● Start (cold engine)")} <span class="note">Coolant now: ${num.ect != null ? Math.round(num.ect) + "°F" : "—"}${W.on ? ` · ${((nowS() - W.t0) / 60).toFixed(1)} min` : ""}</span>
    <canvas class="tplot" id="warmPlot"></canvas>
    ${W.result ? `<div class="verdict"><b class="${gradeCls(W.result.g)}">${gradeTxt(W.result.g)}</b><br>${W.result.text}</div>` : ""}`;
}

// ---------- 🔑 Cranking / starting ----------
T.crank = { phase: "idle", result: null, pts: [] };
async function crankTest() {
  if (fresh("rpm", 3) && (num.rpm ?? 0) > 400) { T.crank = { phase: "done", pts: [], result: { error: "Engine is running. Shut it off, turn the key to ON (engine off), then arm the test and crank." } }; renderTests(); return; }
  const wasStreaming = streaming; stopStream();
  T.crank = { phase: "wait", result: null, pts: [] }; renderTests();
  lastSpeak = 0; speak("Cranking test armed. Crank the engine now.");
  await txn(async () => {
    const t0 = nowS(); let base = null, crankT = null, startT = null, rpmOk = 0;
    while (nowS() - t0 < 25) {
      const vr = (await sendCmd("ATRV", 400)).match(/(\d+\.\d+)/);
      const v = vr ? parseFloat(vr[1]) : null;
      const got = parse01(await sendCmd("010C" + (isCan && fastOK ? "1" : ""), 400), ["0C"]);
      const rpm = got["0C"] ? (got["0C"][0] * 256 + got["0C"][1]) / 4 : null;
      const t = nowS() - t0;
      T.crank.pts.push([t, v, rpm]);
      if (v != null && base == null && T.crank.pts.length >= 3) base = avg(T.crank.pts.slice(0, 3).map((p) => p[1]).filter((x) => x != null));
      if (base != null && v != null && !crankT && v < base - 1.0) { crankT = t; T.crank.phase = "crank"; }
      if (crankT && rpm != null && rpm > 450) { if (++rpmOk >= 2) { startT = t; break; } } else rpmOk = 0;
      if (crankT && !startT && v != null && v > base - 0.3 && t - crankT > 1) break;   // stopped cranking without starting
      if (!crankT && t > 20) break;
    }
    // capture ~3 s after start for charging
    if (startT) { const t1 = nowS(); while (nowS() - t1 < 3) { const vr = (await sendCmd("ATRV", 400)).match(/(\d+\.\d+)/); T.crank.pts.push([nowS() - t0, vr ? parseFloat(vr[1]) : null, null]); } }
    const during = T.crank.pts.filter((p) => crankT && p[0] >= crankT && (!startT || p[0] <= startT));
    const minV = Math.min(...during.map((p) => p[1]).filter((x) => x != null));
    const crRpm = during.map((p) => p[2]).filter((x) => x != null && x > 30 && x < 450);
    const after = startT ? T.crank.pts.filter((p) => p[0] > startT + 1).map((p) => p[1]).filter((x) => x != null) : [];
    const steadyR = crRpm.slice(1);   // skip the first hit while the starter spins up
    const steadyV = during.slice(1).map((p) => p[1]).filter((x) => x != null);
    T.crank.result = !crankT ? { error: "No cranking detected (voltage never dipped). Arm the test, then crank within 20 s." } : {
      base, minV: isFinite(minV) ? minV : null, crankTime: startT ? startT - crankT : null, started: !!startT,
      crankRpm: crRpm.length ? avg(crRpm) : null, afterV: after.length ? avg(after) : null,
      rpmSpread: steadyR.length >= 4 ? Math.max(...steadyR) - Math.min(...steadyR) : null,
      vSpread: steadyV.length >= 4 ? Math.max(...steadyV) - Math.min(...steadyV) : null,
    };
    T.crank.phase = "done";
  });
  const R = T.crank.result;
  if (R && !R.error) reportTest("Cranking / starting", { resting_V: R.base && +R.base.toFixed(2), min_crank_V: R.minV && +R.minV.toFixed(2), crank_s: R.crankTime && +R.crankTime.toFixed(1),
    crank_rpm: R.crankRpm && Math.round(R.crankRpm), rpm_spread: R.rpmSpread && Math.round(R.rpmSpread), started: R.started,
    verdict: crankVerdict(R).text.replace(/<[^>]+>/g, "") });
  if (wasStreaming && connected) startStream();
  renderTests();
}
function crankVerdict(R) {
  const out = []; let g = "g";
  if (R.minV != null) {
    if (R.minV < 9.6) { out.push(`Cranking voltage dropped to ${R.minV.toFixed(1)} V (below 9.6 V) → <b>weak battery</b>, high-resistance cables/grounds, or a dragging starter. Load-test the battery and voltage-drop the cables.`); g = "r"; }
    else if (R.minV < 10) { out.push(`Cranking voltage ${R.minV.toFixed(1)} V is marginal.`); g = "y"; }
    else out.push(`Cranking voltage ${R.minV.toFixed(1)} V → battery and cables OK.`);
  }
  if (R.crankRpm != null) {
    if (R.crankRpm < 120) { out.push(`Slow cranking (~${Math.round(R.crankRpm)} RPM) → starter, battery, cables, or engine drag.`); g = "r"; }
    else out.push(`Cranking speed ~${Math.round(R.crankRpm)} RPM.`);
  }
  if (!R.started) { out.push("Engine did <b>not start</b>: if cranking is healthy, check fuel pressure/prime, spark, crank/cam sensor signal (RPM reading while cranking), and immobilizer."); g = "r"; }
  else if (R.crankTime != null) {
    if (R.crankTime > 4) { out.push(`Long crank (${R.crankTime.toFixed(1)} s) → <b>hard start</b>: fuel pressure bleed-down (check valve, leaking injector), weak prime, or cam/crank sync.`); g = "r"; }
    else if (R.crankTime > 2) { out.push(`Crank time ${R.crankTime.toFixed(1)} s is a little long.`); if (g === "g") g = "y"; }
    else out.push(`Started in ${R.crankTime.toFixed(1)} s.`);
  }
  if (R.afterV != null && R.afterV < 13.2) out.push(`Charging voltage right after start only ${R.afterV.toFixed(1)} V.`);
  // Compression screen: an engine with one weak cylinder cranks unevenly (RPM surges and voltage ripples)
  if ((R.rpmSpread != null && R.rpmSpread >= 50) || (R.vSpread != null && R.vSpread >= 0.6)) {
    out.push(`<b>Uneven cranking</b> (RPM varied ${R.rpmSpread != null ? Math.round(R.rpmSpread) : "?"} / voltage rippled ` +
             `${R.vSpread != null ? R.vSpread.toFixed(1) : "?"} V) → possible low compression in a cylinder or a dragging spot. ` +
             `This Bluetooth sampling is too slow to name the cylinder — confirm with a relative-compression scope test.`);
    if (g === "g") g = "y";
  } else if (R.rpmSpread != null) out.push(`Cranking was smooth (RPM spread ${Math.round(R.rpmSpread)}) → no gross compression difference.`);
  return { g, text: out.join("<br>") };
}
function crankHtml() {
  const C = T.crank, R = C.result;
  return `<div class="tsteps">Key on, engine off, adapter connected. Tap <b>Arm</b>, then crank and let it start. Records resting voltage, lowest cranking voltage, cranking RPM and time to start. (Live data pauses during the test.)</div>
    ${C.phase === "wait" || C.phase === "crank" ? `<span class="grade-y">${C.phase === "wait" ? "Armed — crank the engine now…" : "Cranking…"}</span>` : btn("crank-arm", "Arm cranking test")}
    <canvas class="tplot" id="crankPlot"></canvas>
    ${R ? (R.error ? `<div class="verdict grade-y">${R.error}</div>` : (() => { const v = crankVerdict(R); return `<table class="ttab"><tr><th>Resting</th><th>Lowest while cranking</th><th>Crank RPM</th><th>Time to start</th></tr>
      <tr><td>${R.base ? R.base.toFixed(2) + " V" : "—"}</td><td>${R.minV ? R.minV.toFixed(2) + " V" : "—"}</td><td>${R.crankRpm ? Math.round(R.crankRpm) : "—"}</td><td>${R.started ? R.crankTime.toFixed(1) + " s" : "no start"}</td></tr></table>
      <div class="verdict"><b class="${gradeCls(v.g)}">${gradeTxt(v.g)}</b><br>${v.text}</div>`; })()) : ""}`;
}

// ---------- ⚙️ Transmission (gear ratio from RPM vs speed) ----------
T.trans = { on: false, pts: [] };
function transTick() {
  const X = T.trans; if (!(X.on || T.drive.on) || !fresh("spd", 2) || !fresh("rpm", 2)) return;
  const v = num.spd, r = num.rpm; if (v < 8 || r < 600) return;
  const t = nowS();
  if (X.pts.length && t - X.pts[X.pts.length - 1][0] < 0.2) return;
  X.pts.push([t, r / v, num.tps ?? 0, v, r]);
  if (X.pts.length > 6000) X.pts.shift();
}
function transAnalyze() {
  const P = T.trans.pts; if (P.length < 40) return null;
  // stable samples: ratio within 2% of the one before and after
  const st = P.filter((p, i) => i > 0 && i < P.length - 1 && Math.abs(P[i - 1][1] - p[1]) / p[1] < 0.02 && Math.abs(P[i + 1][1] - p[1]) / p[1] < 0.02);
  const bins = {}; st.forEach((p) => { const b = Math.round(Math.log(p[1]) / Math.log(1.03)); bins[b] = (bins[b] || 0) + 1; });
  const peaks = Object.entries(bins).map(([b, n]) => [+b, n]).filter(([b, n]) => n >= 8 && n >= (bins[b - 1] || 0) && n >= (bins[b + 1] || 0))
    .sort((a, b) => b[0] - a[0]);
  const gears = []; peaks.forEach(([b, n]) => { const ratio = 1.03 ** b; if (!gears.some((g) => Math.abs(g.ratio - ratio) / ratio < 0.07)) gears.push({ ratio, n }); });
  gears.sort((a, b) => b.ratio - a.ratio);
  const near = (x) => gears.reduce((m, g) => (Math.abs(g.ratio - x) < Math.abs(m.ratio - x) ? g : m), gears[0]);
  const flags = [];
  if (gears.length >= 2) {
    // in-gear slip: under throttle, ratio sits 5-15% above its gear for 1 s+
    let run = 0, slips = 0;
    for (const p of P) { const g = near(p[1]); const over = (p[1] - g.ratio) / g.ratio; if (p[2] >= 25 && over > 0.05 && over < 0.15) { if (++run === 5) slips++; } else run = 0; }
    if (slips >= 2) flags.push(`${slips} spots where RPM rose 5–15% above the gear's normal ratio under throttle → <b>clutch/band slip</b> or a flare. Check fluid level/condition first.`);
    // TCC: top gear at steady cruise should hold ratio within ~2%
    const top = gears[gears.length - 1], cruise = P.filter((p) => p[3] > 40 && p[2] < 30 && Math.abs(p[1] - top.ratio) / top.ratio < 0.1);
    if (cruise.length > 30) { const dev = sd(cruise.map((p) => p[1])) / top.ratio; if (dev > 0.025) flags.push(`Top-gear ratio wanders ±${(dev * 100).toFixed(1)}% at steady cruise → <b>torque converter clutch slip/shudder</b> or not locking. Compare with the OEM TCC slip reading if available.`); }
  }
  return { gears, flags, n: P.length };
}
function transHtml() {
  const X = T.trans, a = transAnalyze();
  return `<div class="tsteps">Calculates the overall gear ratio (RPM ÷ speed) while you drive, finds each gear, and looks for slipping and flares. Also watches the torque converter: uses the factory TCC slip reading when the car has one (most GM, many Ford/Chrysler), and speaks up for shudder or slipping at cruise. For converter problems, drive at a <b>steady 25–55 mph with light throttle</b> for a minute or two. Accelerate through all gears a few times and cruise at highway speed. Records automatically on a test drive. <b>Beta.</b></div>
    ${X.on ? btn("trans-stop", "■ Stop") : btn("trans-start", "● Start recording")}${btn("trans-reset", "Reset", 1)} <span class="note">${X.pts.length} samples</span>
    <canvas class="tplot" id="transPlot"></canvas>
    <div class="note">RPM per mph over time. Flat steps = gears.</div>
    ${a ? `<div class="verdict">Gears found: ${a.gears.length ? a.gears.map((g, i) => `<b>${i + 1}</b>: ${g.ratio.toFixed(1)} rpm/mph`).join(" · ") : "not enough steady driving yet"}<br>
      ${a.flags.length ? a.flags.join("<br>") : a.gears.length >= 3 ? "<span class='grade-g'>No gear slip detected.</span>" : ""}</div>` : ""}
    ${(() => { const c = tccAnalyze(); return c ? `<div class="verdict"><b>🌀 Torque converter:</b> ${c.g ? `<b class="${gradeCls(c.g)}">${c.g === "g" ? "OK" : c.g === "r" ? "PROBLEM" : "CHECK"}</b> — ` : ""}${esc(c.text)}${num.tccslip != null && fresh("tccslip", 3) ? `<br>Live TCC slip: <b>${Math.round(num.tccslip)} rpm</b>` : ""}${c.events.length ? "<br><span class='note'>" + c.events.slice(-5).map((e) => esc(e.at + " — " + e.text)).join("<br>") + "</span>" : ""}</div>` : ""; })()}`;
}


// ---------- 🌀 Torque converter clutch (TCC) slip / shudder monitor ----------
// Uses the factory TCC slip reading when the car has one; otherwise watches RPM vs speed at steady cruise.
let TCC = null;
function tccReset() { TCC = { w: [], ev: [], kinds: {}, lastChk: 0, run: 0, steadyS: 0, slipSteady: [], src: null, spokeT: {} }; }
tccReset();
const range = (a) => (a.length ? Math.max(...a) - Math.min(...a) : 0);
const median = (a) => { if (!a.length) return null; const b = [...a].sort((x, y) => x - y); return b[Math.floor(b.length / 2)]; };
function tccSlipTile() {
  for (const c of oemCmds) { if (c.state !== "live") continue;
    for (const g of c.sigs) if (g.watch === "tcc" && g.tile && fresh(g.tile, 3)) return { tile: g.tile, label: g.label }; }
  return null;
}
const TCC_SAY = {
  shudder: (e) => `Possible torque converter shudder at ${Math.round(e.spd)} miles per hour.`,
  nolock: (e) => `Torque converter slipping at cruise, about ${Math.round(e.slip)} RPM.`,
  flareslip: (e) => `Torque converter slip jumped to ${Math.round(e.slip)} RPM without more throttle.`,
  surge: () => `RPM surging at steady speed. Possible torque converter shudder.`,
  flare: () => `RPM flare without a speed change. Possible converter or clutch slip.`,
};
const TCC_NEED = { shudder: 2, nolock: 1, flareslip: 2, surge: 3, flare: 2 };
function tccEvent(kind, text, extra) {
  const t = nowS(), last = TCC.ev.filter((e) => e.kind === kind).pop();
  if (last && t - last.t < 6) return;                      // one event per 6 s window
  const e = Object.assign({ t, kind, text, spd: num.spd, rpm: num.rpm, at: new Date().toLocaleTimeString() }, extra || {});
  TCC.ev.push(e); TCC.kinds[kind] = (TCC.kinds[kind] || 0) + 1;
  if (TCC.ev.length > 200) TCC.ev.shift();
  if (T.drive.on && TCC.kinds[kind] >= TCC_NEED[kind] && t - (TCC.spokeT[kind] || -999) > 90) { TCC.spokeT[kind] = t; lastSpeak = 0; speak(TCC_SAY[kind](e)); }
}
function tccTick() {
  if (!(T.drive.on || T.trans.on) || !fresh("rpm", 2) || !fresh("spd", 2)) return;
  const t = nowS(), src = tccSlipTile();
  if (src) { num.tccslip = num[src.tile]; numT.tccslip = numT[src.tile]; LABEL.tccslip = "TCC slip (rpm)"; TCC.src = src.label; }
  const slip = src ? num[src.tile] : null;
  const W = TCC.w;
  if (!W.length || t - W[W.length - 1][0] >= 0.15) W.push([t, num.rpm, num.spd, num.tps ?? null, slip, inDecel() ? 1 : 0]);
  while (W.length && t - W[0][0] > 12) W.shift();
  if (t - TCC.lastChk < 1) return; TCC.lastChk = t;
  const w = W.filter((s) => t - s[0] <= 4); if (w.length < 6) return;
  const spd = w.map((s) => s[2]), rpm = w.map((s) => s[1]), tps = w.map((s) => s[3]).filter((x) => x != null);
  const ms = avg(spd), mr = avg(rpm);
  const steady = Math.min(...spd) >= 22 && range(spd) <= 2.5 && (!tps.length || range(tps) <= 4) && !w.some((s) => s[5]) && mr >= 900 && mr <= 3800;
  if (!steady) { TCC.run = 0; return; }
  TCC.steadyS++;
  const sl = w.map((s) => s[4]).filter((x) => x != null);
  if (sl.length >= 4) {
    const m = median(sl), p2p = range(sl), dev = sd(sl);
    TCC.slipSteady.push([Math.round(ms), Math.round(m), Math.round(p2p)]); if (TCC.slipSteady.length > 600) TCC.slipSteady.shift();
    // Locked or near-locked converter whose slip keeps swinging = shudder
    if (m > -50 && m < 250 && (p2p >= 100 || dev >= 35))
      tccEvent("shudder", `TCC slip swinging ${Math.round(Math.min(...sl))} to ${Math.round(Math.max(...sl))} rpm at a steady ${Math.round(ms)} mph`, { slip: m, p2p });
    // Highway cruise, light steady throttle, converter still slipping 120+ rpm for 8 s = not locking / lock-up clutch slipping
    if (ms >= 45 && m >= 120 && m <= 900) { if (++TCC.run >= 8) { tccEvent("nolock", `TCC slip held about ${Math.round(m)} rpm for 8+ s at a steady ${Math.round(ms)} mph cruise — converter not locking, or lock-up clutch slipping`, { slip: m }); TCC.run = 0; } }
    else TCC.run = 0;
    // Slip jumps from locked to 150+ rpm with no extra throttle
    const first = w.slice(0, 3).map((s) => s[4]).filter((x) => x != null), lastS = w.slice(-3).map((s) => s[4]).filter((x) => x != null);
    if (first.length && lastS.length && Math.max(...first) < 60 && Math.min(...lastS) > 150)
      tccEvent("flareslip", `TCC slip jumped from ${Math.round(avg(first))} to ${Math.round(avg(lastS))} rpm at ${Math.round(ms)} mph with steady throttle`, { slip: avg(lastS) });
  } else {
    // No factory slip reading: look at RPM itself while speed and throttle hold steady
    const dr = sd(rpm);
    if (sd(spd) < 0.6 && dr >= 30 && dr / mr >= 0.012)
      tccEvent("surge", `RPM swinging ±${Math.round(dr)} (${Math.round(Math.min(...rpm))}–${Math.round(Math.max(...rpm))}) at a steady ${Math.round(ms)} mph`);
    const r0 = avg(w.slice(0, 3).map((s) => s[1])), r1 = avg(w.slice(-3).map((s) => s[1])), v0 = avg(w.slice(0, 3).map((s) => s[2])), v1 = avg(w.slice(-3).map((s) => s[2]));
    if (r1 > r0 * 1.07 && Math.abs(v1 - v0) < 0.7) tccEvent("flare", `RPM rose ${Math.round(r0)}→${Math.round(r1)} with speed steady at ${Math.round(ms)} mph`);
  }
}
function tccAnalyze() {
  if (!TCC) return null;
  const k = TCC.kinds, n = (x) => k[x] || 0, hasSlip = !!TCC.src;
  const bad = n("nolock") >= 1 || n("shudder") >= 3 || n("flareslip") >= 3;
  const warn = bad || n("shudder") + n("flareslip") + n("surge") + n("flare") >= 2;
  const g = bad ? "r" : warn ? "y" : TCC.steadyS >= 30 ? "g" : null;
  const cr = TCC.slipSteady.filter((s) => s[0] >= 45), typ = cr.length ? median(cr.map((s) => s[1])) : null;
  const parts = [];
  if (n("shudder")) parts.push(`${n("shudder")}× slip swinging at steady speed (shudder)`);
  if (n("nolock")) parts.push(`${n("nolock")}× converter slipping 120+ rpm at highway cruise`);
  if (n("flareslip")) parts.push(`${n("flareslip")}× slip jumped with no extra throttle`);
  if (n("surge")) parts.push(`${n("surge")}× RPM surging at steady speed`);
  if (n("flare")) parts.push(`${n("flare")}× RPM flare with no speed change`);
  let text = !g ? "Not enough steady cruising yet (need ~30 s total at a steady 25+ mph)." :
    g === "g" ? `No converter slip or shudder seen in ${TCC.steadyS} s of steady driving.` :
    parts.join("; ") + ". " + (bad ? "Likely torque converter clutch problem." : "Possible torque converter clutch problem.") +
    " Next: check fluid level/condition and for TSBs (fluid exchange / TCM reflash for shudder), then command TCC on with a scan tool and watch slip.";
  text += hasSlip ? ` Using factory reading: ${TCC.src}${typ != null ? ` (typical slip at 45+ mph cruise: ${typ} rpm; locked is about 0–40)` : ""}.`
    : " No factory TCC slip reading on this car — judged from RPM vs speed, which only catches bigger slip/shudder.";
  return { g, text, kinds: k, hasSlip, steadyS: TCC.steadyS, events: TCC.ev.slice(-20) };
}

// ---------- signal tools: FFT + microphone ----------
function fftMag(sig) {
  let n = 1; while (n < sig.length) n <<= 1;
  const re = new Float64Array(n), im = new Float64Array(n), m = avg(sig);
  for (let i = 0; i < sig.length; i++) re[i] = (sig[i] - m) * (0.5 - 0.5 * Math.cos(2 * Math.PI * i / (sig.length - 1)));   // Hann window
  for (let i = 1, j = 0; i < n; i++) { let bit = n >> 1; for (; j & bit; bit >>= 1) j ^= bit; j ^= bit; if (i < j) { [re[i], re[j]] = [re[j], re[i]]; [im[i], im[j]] = [im[j], im[i]]; } }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = -2 * Math.PI / len, wr = Math.cos(ang), wi = Math.sin(ang);
    for (let i = 0; i < n; i += len) { let cr = 1, ci = 0;
      for (let k = 0; k < len / 2; k++) { const ar = re[i + k + len / 2] * cr - im[i + k + len / 2] * ci, ai = re[i + k + len / 2] * ci + im[i + k + len / 2] * cr;
        re[i + k + len / 2] = re[i + k] - ar; im[i + k + len / 2] = im[i + k] - ai; re[i + k] += ar; im[i + k] += ai; const t = cr * wr - ci * wi; ci = cr * wi + ci * wr; cr = t; } }
  }
  const mag = new Float64Array(n / 2); for (let i = 0; i < n / 2; i++) mag[i] = Math.hypot(re[i], im[i]);
  return { mag, n };
}
function topPeaks(mag, fs, n, fmin, fmax, k = 4) {
  const df = fs / n, out = [];
  for (let i = Math.max(2, Math.ceil(fmin / df)); i < Math.min(mag.length - 1, fmax / df); i++)
    if (mag[i] > mag[i - 1] && mag[i] >= mag[i + 1]) out.push([i * df, mag[i]]);
  out.sort((a, b) => b[1] - a[1]);
  const res = []; for (const p of out) { if (res.some((q) => Math.abs(q[0] - p[0]) < 3 * df)) continue; res.push(p); if (res.length >= k) break; }
  return res;
}
async function recordMic(secs) {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  if (ctx.state === "suspended") await ctx.resume();
  const src = ctx.createMediaStreamSource(stream), proc = ctx.createScriptProcessor(4096, 1, 1), chunks = [];
  proc.onaudioprocess = (e) => chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
  src.connect(proc); proc.connect(ctx.destination);
  await sleep(secs * 1000);
  proc.disconnect(); src.disconnect(); stream.getTracks().forEach((t) => t.stop());
  const fs = ctx.sampleRate; await ctx.close();
  const raw = new Float32Array(chunks.reduce((s, c) => s + c.length, 0)); let o = 0; chunks.forEach((c) => { raw.set(c, o); o += c.length; });
  return { raw, fs };
}
function downsample(raw, fs, target) {
  const f = Math.max(1, Math.floor(fs / target)), out = new Float64Array(Math.floor(raw.length / f));
  for (let i = 0; i < out.length; i++) { let s = 0; for (let j = 0; j < f; j++) s += raw[i * f + j]; out[i] = s / f; }
  return { sig: out, fs: fs / f };
}

// ---------- 〰️ Vibration / noise finder (NVH) ----------
T.nvh = { phase: "idle", res: null, acc: [] };
function tireCirc() {   // e.g. 225/45R17 -> meters
  const m = (T.inp.tire || "").toUpperCase().match(/(\d{3})\s*\/\s*(\d{2})\s*Z?R?\s*(\d{2})/);
  if (!m) return null;
  const dIn = +m[3] + 2 * (+m[1] * +m[2] / 100) / 25.4;
  return Math.PI * dIn * 0.0254;
}
function nvhOrders(spdMph, rpm) {
  const o = [], circ = tireCirc(), cyl = cylCount() || 4;
  if (circ && spdMph > 3) { const fw = spdMph * 0.44704 / circ; o.push(["1× wheel/tire", fw, "tire/wheel imbalance, bent rim, tire belt shift, hub/rotor runout"], ["2× wheel/tire", 2 * fw, "out-of-round tire, tire uniformity (road-force balance)"]);
    o.push(["driveshaft range (≈3–4.5× wheel)", 3.7 * fw, "driveshaft balance, U-joints, CV joints, carrier bearing", 0.25]); }
  if (rpm > 300) { const fe = rpm / 60; o.push(["½× engine", fe / 2, "camshaft-speed part, misfire on one cylinder", 0.08], ["1× engine", fe, "crank pulley/balancer, flexplate/flywheel, torque converter, accessory imbalance"],
    [`firing (${cyl / 2}× engine)`, fe * cyl / 2, "engine/trans mounts, exhaust grounding, misfire, firing pulses"], ["2× firing", fe * cyl, "mounts/exhaust, intake/valvetrain noise"]); }
  return o;
}
function matchOrder(f, orders) {
  let best = null;
  for (const [name, fo, why, tol = 0.1] of orders) { const e = Math.abs(f - fo) / fo; if (e <= tol && (!best || e < best.e)) best = { name, why, e, fo }; }
  return best;
}
async function nvhRecord(kind) {
  const N = T.nvh; N.phase = "rec"; N.kind = kind; N.res = null; renderTests();
  const spd0 = [], rpm0 = [], t0 = nowS();
  const stamp = setInterval(() => { if (num.spd != null) spd0.push(num.spd); if (num.rpm != null) rpm0.push(num.rpm); }, 200);
  try {
    let peaks, fs, spec;
    if (kind === "acc") {
      if (!T.perf.motionOn) { perfMotion(); await sleep(500); }
      N.acc = [];
      const h = (e) => { const a = e.accelerationIncludingGravity; if (a && a.x != null) N.acc.push([nowS(), a.x, a.y, a.z]); };
      window.addEventListener("devicemotion", h); await sleep(8000); window.removeEventListener("devicemotion", h);
      if (N.acc.length < 100) throw new Error("Not enough motion samples — use a phone/tablet and allow motion access.");
      fs = (N.acc.length - 1) / (N.acc[N.acc.length - 1][0] - N.acc[0][0]);
      const mags = [0, 1, 2].map((ax) => fftMag(N.acc.map((p) => p[1 + ax])));
      const n = mags[0].n, sum = new Float64Array(n / 2); mags.forEach((m) => m.mag.forEach((v, i) => (sum[i] += v * v)));
      spec = Array.from(sum, Math.sqrt);
      peaks = topPeaks(spec, fs, n, 2.5, fs / 2 - 1); N.spec = { spec, fs, n, fmax: fs / 2 };
    } else {
      const { raw, fs: f0 } = await recordMic(8);
      const d = downsample(raw, f0, 2000); fs = d.fs;
      const { mag, n } = fftMag(Array.from(d.sig));
      spec = Array.from(mag); peaks = topPeaks(spec, fs, n, 15, 800); N.spec = { spec, fs, n, fmax: 800 };
    }
    const spd = avg(spd0) ?? 0, rpm = avg(rpm0) ?? 0, orders = nvhOrders(spd, rpm);
    N.res = { kind, spd, rpm, peaks: peaks.map(([f, m]) => ({ f, m, match: matchOrder(f, orders) })), orders, secs: nowS() - t0 };
    const top = N.res.peaks[0];
    reportTest(kind === "acc" ? "Vibration (NVH)" : "Noise (NVH)", { speed_mph: Math.round(spd), rpm: Math.round(rpm), top_hz: top && +top.f.toFixed(1),
      match: top && top.match ? top.match.name : "no order match", verdict: top && top.match ? `${top.f.toFixed(1)} Hz matches ${top.match.name}: ${top.match.why}` : "Strongest frequency doesn't match a rotating order" });
  } catch (e) { N.res = { error: e.message || String(e) }; logEvent("test", "Vibration/noise test", N.res.error, e.stack); }
  clearInterval(stamp); N.phase = "idle"; renderTests();
}
function nvhHtml() {
  const N = T.nvh, R = N.res, circ = tireCirc();
  return `<div class="tsteps">Finds what's spinning at the same speed as the vibration or noise. <b>Vibration:</b> phone solidly on the seat rail/floor or dash mount. <b>Noise:</b> phone in the cabin near the noise (or under the hood at idle). Drive at the speed where it's worst, hold steady, and record 8 s. Tip: repeat while coasting in Neutral — if it's still there it's wheels/tires/driveline, if it's gone it's engine/trans.</div>
    Tire size: ${inp("tire", "225/45R17", 110)} ${circ ? `<span class="note">${(circ / 0.0254 / Math.PI).toFixed(1)}" tall</span>` : '<span class="grade-y">needed for wheel/driveshaft orders</span>'}
    &nbsp; Cylinders: ${inp("cyl", ARGS.cyl || "4", 40)}<br>
    ${N.phase === "rec" ? `<span class="grade-y">Recording 8 s… hold steady (${Math.round(num.spd ?? 0)} mph, ${Math.round(num.rpm ?? 0)} RPM)</span>`
      : btn("nvh-acc", "〰️ Record vibration (motion sensor)") + btn("nvh-mic", "🎤 Record noise (microphone)")}
    <canvas class="tplot" id="nvhPlot"></canvas>
    ${R ? (R.error ? `<div class="verdict grade-y">${esc(R.error)}</div>` : `<table class="ttab"><tr><th>Frequency</th><th>Strength</th><th style="text-align:left">Matches</th><th style="text-align:left">Likely causes</th></tr>
      ${R.peaks.map((p, i) => `<tr><td>${p.f.toFixed(1)} Hz</td><td>${i === 0 ? "strongest" : (p.m / R.peaks[0].m * 100).toFixed(0) + "%"}</td><td style="text-align:left">${p.match ? "<b>" + p.match.name + "</b>" : "—"}</td><td style="text-align:left" class="note">${p.match ? p.match.why : "not tied to wheel or engine speed (could be a resonance, accessory, or road surface)"}</td></tr>`).join("")}</table>
      <div class="note">At ${Math.round(R.spd)} mph / ${Math.round(R.rpm)} RPM: ${R.orders.map((o) => `${o[0]} ${o[1].toFixed(1)} Hz`).join(" · ")}</div>`) : ""}`;
}

// ---------- 👂 Tailpipe listener (exhaust pulse evenness) ----------
T.tail = { phase: "idle", res: null };
async function tailRecord() {
  const L = T.tail; L.phase = "rec"; L.res = null; renderTests();
  const rpms = [], stamp = setInterval(() => { if (num.rpm) rpms.push(num.rpm); }, 200);
  try {
    const cyl = cylCount(); if (!cyl) throw new Error("Enter the number of cylinders.");
    const { raw, fs: f0 } = await recordMic(8);
    const rpm = rpms.length ? avg(rpms) : parseFloat(T.inp.trpm);
    if (!rpm) throw new Error("No RPM — connect the scanner or type the idle RPM.");
    if (rpms.length && sd(rpms) > 60) throw new Error("RPM wasn't steady — let it idle smoothly and try again.");
    const d = downsample(raw, f0, 1000), { mag, n } = fftMag(Array.from(d.sig)), df = d.fs / n, fc = rpm / 120;
    const amp = (f) => { const i = Math.round(f / df), w = Math.max(1, Math.round(f * 0.03 / df)); let m = 0; for (let k = i - w; k <= i + w; k++) if (mag[k] > m) m = mag[k]; return m; };
    const orders = []; for (let k = 1; k <= 2 * cyl; k++) orders.push({ k, f: k * fc, a: amp(k * fc), firing: k % cyl === 0 });
    const firing = orders.filter((o) => o.firing).reduce((s, o) => s + o.a, 0) || 1e-9, sub = orders.filter((o) => !o.firing && o.k <= cyl).reduce((s, o) => s + o.a, 0);
    const score = sub / firing / (cyl - 1);
    const g = score < 0.25 ? "g" : score < 0.45 ? "y" : "r";
    L.res = { rpm, cyl, orders, score, g };
    reportTest("Tailpipe pulse listener", { rpm: Math.round(rpm), unevenness: +score.toFixed(2), grade: gradeTxt(g), verdict: g === "g" ? "Exhaust pulses even" : "Exhaust pulses uneven — possible misfire/weak cylinder" });
  } catch (e) { L.res = { error: e.message || String(e) }; logEvent("test", "Tailpipe test", L.res.error, e.stack); }
  clearInterval(stamp); L.phase = "idle"; renderTests();
}
function tailHtml() {
  const L = T.tail, R = L.res;
  return `<div class="tsteps">Screening test inspired by tailpipe pulse sensors. Engine warm at a <b>steady idle</b>. Hold the phone's microphone about 6–12 inches from the tailpipe (out of the direct blast, wind off), tap Record and hold still for 8 s. An even engine puts its sound at the firing frequency; a weak or misfiring cylinder adds a once-per-cycle "thump".</div>
    Cylinders: ${inp("cyl", ARGS.cyl || "4", 40)} &nbsp; Idle RPM (if not connected): ${inp("trpm", "750", 60)}<br>
    ${L.phase === "rec" ? '<span class="grade-y">Listening 8 s… hold still</span>' : btn("tail-rec", "👂 Record at tailpipe")}
    <canvas class="tplot" id="tailPlot"></canvas>
    <div class="note">Bars = sound at each multiple of engine-cycle speed. Green = firing pulses (should dominate); red = uneven-cylinder orders.</div>
    ${R ? (R.error ? `<div class="verdict grade-y">${esc(R.error)}</div>` : `<div class="verdict"><b class="${gradeCls(R.g)}">${R.g === "g" ? "EVEN" : R.g === "y" ? "SLIGHTLY UNEVEN" : "UNEVEN"}</b> (unevenness ${R.score.toFixed(2)} at ${Math.round(R.rpm)} RPM)<br>
      ${R.g === "g" ? "Exhaust pulses are even — all cylinders contributing about equally." : "One or more cylinders aren't contributing evenly → check the misfire counters, then compression/leak-down or a relative compression on the scope. Exhaust leaks and background noise can also affect this screening test."}</div>`) : ""}`;
}

// ---------- 💾 Record, compare (before/after) and export ----------
const KEY_STATS = ["rpm", "load", "stft1", "ltft1", "stft2", "ltft2", "maf", "map", "ect", "iat", "volt", "o2b1s1", "o2b1s2", "timing", "frp"];
function statsNow(secs = 60) {
  const t = nowS(), out = {};
  for (const id of KEY_STATS) { const h = (HIST[id] || []).filter((p) => t - p[0] <= secs).map((p) => p[1]); if (h.length) out[id] = { avg: avg(h), min: Math.min(...h), max: Math.max(...h) }; }
  return out;
}
function storeKey() { return "tdg_before_" + (ARGS.vehicle || "vehicle").replace(/\W+/g, "_"); }
function saveBefore() {
  const snap = { when: new Date().toLocaleString(), vehicle: ARGS.vehicle, stats: statsNow(), tests: JSON.parse(JSON.stringify(T.results || {})), codes: dtcs };
  T.before = snap; try { localStorage.setItem(storeKey(), JSON.stringify(snap)); } catch (_) {}
}
function loadBefore() { if (T.before) return T.before; try { const s = localStorage.getItem(storeKey()); if (s) T.before = JSON.parse(s); } catch (_) {} return T.before; }
function exportCsv() {
  const ids = Object.keys(HIST).filter((id) => HIST[id].length);
  if (!ids.length) { alert("No data recorded yet."); return; }
  const times = [...new Set(ids.flatMap((id) => HIST[id].map((p) => Math.round(p[0] * 4) / 4)))].sort((a, b) => a - b);
  const idx = Object.fromEntries(ids.map((id) => [id, 0])), last = {}, t0 = times[0], wall = Date.now() / 1000 - nowS();
  const rows = ["time,elapsed_s," + ids.map((id) => `"${(LABEL[id] || id).replace(/"/g, "'")}"`).join(",")];
  for (const t of times) {
    for (const id of ids) { const h = HIST[id]; while (idx[id] < h.length && h[idx[id]][0] <= t + 0.125) last[id] = h[idx[id]++][1]; }
    rows.push(new Date((wall + t) * 1000).toLocaleTimeString() + "," + (t - t0).toFixed(2) + "," + ids.map((id) => (last[id] ?? "")).join(","));
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([rows.join("\n")], { type: "text/csv" }));
  a.download = `scan_${(ARGS.vehicle || "vehicle").replace(/\W+/g, "_")}_${new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-")}.csv`;
  document.body.appendChild(a); a.click(); a.remove();
}
function recHtml() {
  const B = loadBefore(), now = statsNow();
  const recMins = Math.max(0, ...Object.values(HIST).map((h) => (h.length ? (h[h.length - 1][0] - h[0][0]) / 60 : 0)));
  const rows = B ? KEY_STATS.filter((id) => B.stats[id] || now[id]).map((id) => {
    const b = B.stats[id], a = now[id], d = b && a ? a.avg - b.avg : null;
    return `<tr><td style="text-align:left">${esc(LABEL[id] || id)}</td><td>${b ? fmtNum(b.avg) : "—"}</td><td>${a ? fmtNum(a.avg) : "—"}</td><td>${d == null ? "" : (d > 0 ? "+" : "") + fmtNum(d)}</td></tr>`;
  }).join("") : "";
  const tests = B ? [...new Set([...Object.keys(B.tests || {}), ...Object.keys(T.results || {})])].map((k) =>
    `<tr><td style="text-align:left">${esc(k)}</td><td>${esc(((B.tests || {})[k] || {}).grade || "—")}</td><td>${esc(((T.results || {})[k] || {}).grade || "—")}</td><td></td></tr>`).join("") : "";
  return `<div class="tsteps">Everything you stream is recorded (last ~10 min per reading). <b>Export</b> it as a spreadsheet (CSV). Before a repair, tap <b>Save BEFORE</b> with the engine in the condition you care about (e.g. warm idle); after the repair, run the same way and the table compares the last minute against BEFORE. The BEFORE snapshot is saved on this device for this vehicle.</div>
    ${btn("rec-csv", "⬇️ Export data (CSV)")}${btn("rec-before", "📌 Save BEFORE snapshot", 1)}${B ? btn("rec-clear", "Clear BEFORE", 1) : ""}
    <span class="note">${recMins.toFixed(1)} min recorded</span>
    ${B ? `<div class="note" style="margin-top:6px">BEFORE saved ${esc(B.when)}. AFTER = last 60 s of live data.</div>
      <table class="ttab"><tr><th style="text-align:left">Reading (avg)</th><th>Before</th><th>After</th><th>Change</th></tr>${rows}
      ${tests ? `<tr><th style="text-align:left">Test</th><th>Before</th><th>After</th><th></th></tr>${tests}` : ""}</table>` : ""}`;
}

// ---------- plots for the new tabs ----------
function linePlot(id, pts, color, yLabel, opts = {}) {
  const P = plotSetup(id); if (!P) return; const { g, c } = P;
  if (!pts.length) { g.fillStyle = c("--muted"); g.font = "12px sans-serif"; g.fillText(opts.empty || "Waiting for data…", 44, 90); return; }
  const t0 = pts[0][0], t1 = Math.max(pts[pts.length - 1][0], t0 + 1);
  let lo = opts.lo ?? Math.min(...pts.map((p) => p[1])), hi = opts.hi ?? Math.max(...pts.map((p) => p[1]));
  if (hi - lo < 1) { lo -= 1; hi += 1; }
  const A = axes(P, t0, t1, lo, hi);
  for (let k = 0; k <= 2; k++) { const v = lo + (hi - lo) * k / 2; g.beginPath(); g.moveTo(A.L, A.Y(v)); g.lineTo(A.L + A.pw, A.Y(v)); g.stroke(); g.textAlign = "right"; g.fillText(fmtNum(v), A.L - 4, A.Y(v) + 3); }
  (opts.refs || []).forEach(([v, col]) => { g.strokeStyle = col; g.setLineDash([4, 4]); g.beginPath(); g.moveTo(A.L, A.Y(v)); g.lineTo(A.L + A.pw, A.Y(v)); g.stroke(); g.setLineDash([]); });
  g.strokeStyle = c(color); g.lineWidth = 2; g.beginPath(); pts.forEach((p, j) => (j ? g.lineTo(A.X(p[0]), A.Y(p[1])) : g.moveTo(A.X(p[0]), A.Y(p[1])))); g.stroke();
  g.fillStyle = c("--muted"); g.textAlign = "left"; g.fillText(yLabel, 4, 12);
  g.textAlign = "right"; g.fillText(opts.xLabel || `${((t1 - t0) / 60).toFixed(1)} min`, A.L + A.pw, P.H - 4);
}
function specPlot(id, spec, fs, n, fmax, marks) {
  const P = plotSetup(id); if (!P) return; const { g, c } = P;
  if (!spec) { g.fillStyle = c("--muted"); g.font = "12px sans-serif"; g.fillText("No recording yet.", 44, 90); return; }
  const df = fs / n, imax = Math.min(spec.length, Math.floor(fmax / df)), hi = Math.max(...spec.slice(2, imax)) * 1.1 || 1;
  const A = axes(P, 0, fmax, 0, hi);
  g.textAlign = "center"; for (let k = 0; k <= 4; k++) { const f = fmax * k / 4; g.fillText(f.toFixed(0) + " Hz", A.X(f), P.H - 4); }
  (marks || []).forEach(([f, label]) => { if (f > fmax) return; g.strokeStyle = c("--s"); g.setLineDash([3, 3]); g.beginPath(); g.moveTo(A.X(f), A.Y(0)); g.lineTo(A.X(f), A.Y(hi)); g.stroke(); g.setLineDash([]); g.fillStyle = c("--muted"); g.textAlign = "left"; g.fillText(label, A.X(f) + 2, 20); });
  g.strokeStyle = c("--b"); g.lineWidth = 2; g.beginPath(); for (let i = 1; i < imax; i++) { const x = A.X(i * df), y = A.Y(spec[i]); i === 1 ? g.moveTo(x, y) : g.lineTo(x, y); } g.stroke();
}
function drawExtraPlots() {
  if (testTab === "vac") linePlot("vacPlot", T.vac.trace, "--b", "inHg", { lo: 0, hi: 25, refs: [[17, "rgba(0,255,102,.5)"], [21, "rgba(0,255,102,.5)"]], xLabel: "last 40 s" });
  if (testTab === "warm") linePlot("warmPlot", T.warm.pts.map((p) => [p[0], p[1]]), "--o", "°F", { refs: [[195, "rgba(0,255,102,.5)"], [230, "rgba(239,68,68,.6)"]], empty: "Tap Start with a cold engine." });
  if (testTab === "crank") linePlot("crankPlot", T.crank.pts.filter((p) => p[1] != null).map((p) => [p[0], p[1]]), "--y", "Volts", { refs: [[9.6, "rgba(239,68,68,.6)"]], xLabel: "seconds", empty: "Arm the test and crank." });
  if (testTab === "trans") linePlot("transPlot", T.trans.pts.map((p) => [p[0], p[1]]), "--p", "rpm/mph", { empty: "Drive to record." });
  if (testTab === "nvh") { const S = T.nvh.spec, R = T.nvh.res; specPlot("nvhPlot", S && S.spec, S && S.fs, S && S.n, S ? S.fmax : 30, R && R.orders ? R.orders.map((o) => [o[1], o[0].split(" ")[0]]) : []); }
  if (testTab === "tail") {
    const P = plotSetup("tailPlot"), R = T.tail.res; if (!P) return; const { g, c } = P;
    if (!R || R.error) { g.fillStyle = c("--muted"); g.font = "12px sans-serif"; g.fillText("No recording yet.", 44, 90); return; }
    const hi = Math.max(...R.orders.map((o) => o.a)) || 1, A = axes(P, 0, R.orders.length + 1, 0, hi), w = A.pw / (R.orders.length + 1) * 0.6;
    R.orders.forEach((o) => { g.fillStyle = o.firing ? c("--g") : c("--r"); const x = A.X(o.k) - w / 2, y = A.Y(o.a); g.fillRect(x, y, w, A.Y(0) - y); g.fillStyle = c("--muted"); g.textAlign = "center"; g.fillText(o.k + "×", A.X(o.k), P.H - 4); });
  }
}

// ---------- wiring ----------
const EXTRA_HTML = { mis: misHtml, rdy: rdyHtml, vac: vacHtml, warm: warmHtml, crank: crankHtml, trans: transHtml, nvh: nvhHtml, tail: tailHtml, rec: recHtml };
const EXTRA_ACTIONS = {
  "mis-reset": () => { Object.values(misLive).forEach((L) => (L.tot = 0)); misEvents = []; },
  "rdy-refresh": () => txn(pollMonitors41).then(renderTests),
  "vac-idle": () => Object.assign(T.vac, { step: "idle", buf: [], t0: nowS() }),
  "vac-snap": () => Object.assign(T.vac, { step: "snap", buf: [], t0: nowS(), relT: null }),
  "vac-hold": () => Object.assign(T.vac, { step: "hold", buf: [], t0: nowS() }),
  "vac-reset": () => Object.assign(T.vac, { idle: null, snap: null, hold: null, step: null }),
  "warm-start": () => { T.warm = { on: true, pts: [], t0: nowS(), result: null }; },
  "warm-stop": () => { T.warm.on = false; },
  "crank-arm": () => { crankTest(); },
  "trans-start": () => { T.trans.on = true; }, "trans-stop": () => { T.trans.on = false; }, "trans-reset": () => { T.trans.pts = []; },
  "nvh-acc": () => { nvhRecord("acc"); }, "nvh-mic": () => { nvhRecord("mic"); },
  "tail-rec": () => { tailRecord(); },
  "rec-csv": () => exportCsv(), "rec-before": () => saveBefore(),
  "rec-clear": () => { T.before = null; try { localStorage.removeItem(storeKey()); } catch (_) {} },
};
function extraTicks() { vacTick(); warmTick(); transTick(); tccTick(); }
function extraDriveStart() {
  Object.values(misLive).forEach((L) => (L.tot = 0)); misEvents = [];
  T.trans.pts = []; tccReset();
  if ((num.ect ?? 999) < 150) T.warm = { on: true, pts: [], t0: nowS(), result: null };
}
function extraDriveStop() { if (T.warm.on) T.warm.on = false; }
function extraDriveChips(chip) {
  const m = misAnalyze(), a = transAnalyze();
  return chip(true, m.all ? `${m.all} misfire(s)` : "No misfires") + chip(a && a.gears.length >= 3, `Gears found (${a ? a.gears.length : 0})`) +
    chip(TCC && TCC.steadyS >= 30, TCC && TCC.ev.length ? "⚠️ Converter" : "Converter check") +
    (T.warm.on ? chip(!!T.warm.result, "Warm-up") : "") + (r41 ? chip(readinessRows(r41.B, r41.C, r41.D, true).every((r) => r.done), "Monitors this drive") : "");
}
function extraReportRows(add) {
  const m = misAnalyze();
  add("🔥 Misfires", m.all ? `${m.all} new${m.worst ? " · mostly cyl " + m.worst[0] : ""}` : "none", m.all ? (m.all > 20 ? "r" : "y") : "g", m.all ? m.text.replace(/<[^>]+>/g, "").slice(0, 140) + "…" : "");
  const a = transAnalyze();
  if (a) add("⚙️ Transmission", `${a.gears.length} gears found`, a.flags.length ? "y" : a.gears.length >= 3 ? "g" : null, a.flags.length ? a.flags.map((f) => f.replace(/<[^>]+>/g, "")).join(" ").slice(0, 160) : "");
  const tc = tccAnalyze();
  if (tc && tc.g) { add("🌀 Torque converter", tc.g === "g" ? "no slip/shudder" : tc.g === "r" ? "problem" : "check", tc.g, tc.text.slice(0, 220));
    reportTest("Torque converter clutch", { grade: tc.g === "g" ? "GOOD" : tc.g === "r" ? "BAD" : "MARGINAL", verdict: tc.text, factory_slip_pid: tc.hasSlip, events: tc.events.map((e) => e.at + " " + e.text) }, true); }
  if (T.warm.result) add("🌡️ Warm-up", T.warm.result.g === "g" ? "normal" : "check", T.warm.result.g, T.warm.result.text.replace(/<[^>]+>/g, "").slice(0, 160));
  if (r41) { const rows = readinessRows(r41.B, r41.C, r41.D, true), left = rows.filter((r) => !r.done); add("📋 Monitors (this drive)", `${rows.length - left.length}/${rows.length} complete`, left.length ? "y" : "g", left.length ? "still running: " + left.map((r) => r.n).join(", ") : ""); }
  if (misAnalyze().all) reportTest("Misfire monitor", { total_new: m.all, worst_cylinder: m.worst && m.worst[0], verdict: m.text.replace(/<[^>]+>/g, "") }, true);
  if (a && a.gears.length) reportTest("Transmission ratio analysis", { gears: a.gears.map((g) => +g.ratio.toFixed(1)), flags: a.flags.map((f) => f.replace(/<[^>]+>/g, "")), grade: a.flags.length ? "MARGINAL" : "GOOD" }, true);
}


// ===================== Test drive recorder (auto-saved on this device + sent to the app) =====================
const DRIVE_KEYS = ["rpm", "spd", "load", "tps", "stft1", "ltft1", "stft2", "ltft2", "maf", "map", "ect", "iat", "o2b1s1", "o2b1s2", "timing", "volt", "frp", "tccslip"];
const FSS_CODE = (t) => (!t || t === "--" ? null : /^CL O2/.test(t) ? 5 : /^CL/.test(t) ? 1 : /decel/.test(t) ? 3 : /cold/.test(t) ? 2 : /fault/.test(t) ? 4 : 9);
const FSS_NAME = { 1: "CL", 2: "OL cold", 3: "OL decel", 4: "OL fault", 5: "CL O2 fault", 9: "other" };
const LS_DRIVES = "tdg_drives", LS_CURRENT = "tdg_drive_current";
let REC = null, recTimer = null, recSaveT = 0;
function lsGet(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (_) { return d; } }
function lsSet(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch (_) { return false; } }
const r2 = (x) => (x == null || !isFinite(x) ? null : Math.round(x * 100) / 100);
function snapNow() { const o = {}; DRIVE_KEYS.forEach((k) => { if (num[k] != null) o[k] = r2(num[k]); }); o.fss = shown.fss || ""; o.decel = inDecel(); return o; }
function driveRecStart() {
  REC = { id: "drv-" + Date.now(), started: new Date().toLocaleString(), startMs: Date.now(), vehicle: ARGS.vehicle || "", vin: vinRead || "",
    keys: DRIVE_KEYS, samples: [], alerts: [], status: "recording" };
  clearInterval(recTimer);
  recTimer = setInterval(() => {
    if (!REC || !connected) return;
    REC.samples.push([Math.round((Date.now() - REC.startMs) / 1000), ...DRIVE_KEYS.map((k) => (fresh(k, 5) ? r2(num[k]) : null)), FSS_CODE(shown.fss), inDecel() ? 1 : 0]);
    if (REC.samples.length > 7200) REC.samples.shift();               // up to 2 hours at 1 sample/s
    if (Date.now() - recSaveT > 15000) { recSaveT = Date.now(); lsSet(LS_CURRENT, REC); }   // survives reloads / crashes
  }, 1000);
}
function driveRecAlert(text) { if (REC && REC.status === "recording") REC.alerts.push({ t: Math.round((Date.now() - REC.startMs) / 1000), at: new Date().toLocaleTimeString(), text, snap: snapNow() }); }
function driveRecFinish(rec, status) {
  rec.status = status; rec.minutes = Math.round(((rec.samples.length ? rec.samples[rec.samples.length - 1][0] : 0) / 60) * 10) / 10;
  let list = lsGet(LS_DRIVES, []).filter((d) => d.id !== rec.id);
  list.unshift(rec); list = list.slice(0, 10);
  while (!lsSet(LS_DRIVES, list) && list.length > 1) list.pop();   // drop oldest if storage is full
  try { localStorage.removeItem(LS_CURRENT); } catch (_) {}
}
function driveRecStop() {
  clearInterval(recTimer); if (!REC) return;
  const D = T.drive;
  Object.assign(REC, { results: JSON.parse(JSON.stringify(T.results || {})), codes: dtcs, misfires: misEvents.slice(-100),
    report: (D.report || "").replace(/<br\s*\/?>/g, "\n").replace(/<\/tr>/g, "\n").replace(/<\/td>/g, " | ").replace(/<[^>]+>/g, "").replace(/\n\s*\n/g, "\n").trim() });
  driveRecFinish(REC, "complete");
  sendDrive(REC);
  REC = null;
}
function sendDrive(rec) { sendValue({ type: "drive", id: "drive-" + Date.now(), record: rec }); }
// On page load: rescue a drive that was cut off by a reload or crash
(function rescueDrive() {
  const cur = lsGet(LS_CURRENT, null);
  if (cur && cur.samples && cur.samples.length) driveRecFinish(cur, "interrupted (page closed mid-drive)");
})();
function exportDriveCsv(rec) {
  const head = ["seconds", ...rec.keys.map((k) => LABEL[k] || k), "fuel system", "decel/fuel cut"];
  const rows = [head.map((h) => `"${h}"`).join(",")].concat(rec.samples.map((s) => s.slice(0, -2).concat([FSS_NAME[s[s.length - 2]] || "", s[s.length - 1] ? "yes" : ""]).map((v) => v ?? "").join(",")));
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([rows.join("\n")], { type: "text/csv" }));
  a.download = `testdrive_${(rec.vehicle || "vehicle").replace(/\W+/g, "_")}_${rec.id.slice(4)}.csv`;
  document.body.appendChild(a); a.click(); a.remove();
}
function savedDrivesHtml() {
  const list = lsGet(LS_DRIVES, []);
  if (!list.length) return "";
  return `<details data-drvlist ${T.drivesOpen ? "open" : ""} style="margin:8px 0"><summary class="grp" style="cursor:pointer;color:var(--b)">📁 Saved test drives on this device (${list.length})</summary>
    <table class="ttab"><tr><th style="text-align:left">When</th><th style="text-align:left">Vehicle</th><th>Minutes</th><th>Alerts</th><th></th></tr>
    ${list.map((d, i) => `<tr><td style="text-align:left">${esc(d.started)}${/interrupted/.test(d.status) ? ' <span class="grade-y">(interrupted)</span>' : ""}</td>
      <td style="text-align:left">${esc(d.vehicle || "—")}</td><td>${d.minutes ?? "—"}</td><td>${(d.alerts || []).length}</td>
      <td><button class="tbtn" data-drv="send" data-i="${i}">Send to app / Claude</button><button class="tbtn sec" data-drv="csv" data-i="${i}">CSV</button><button class="tbtn sec" data-drv="del" data-i="${i}">✕</button></td></tr>`).join("")}</table>
    <div class="note">"Send to app" puts the drive in the 📋 Log tab → 🚗 Test drive review, where you can copy it to Claude or have the AI team review it.</div></details>`;
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-drv]"); if (!b) return;
  const list = lsGet(LS_DRIVES, []), d = list[+b.dataset.i]; if (!d) return;
  if (b.dataset.drv === "send") { sendDrive(d); log("Drive sent to the app — see 📋 Log → 🚗 Test drive review."); }
  if (b.dataset.drv === "csv") exportDriveCsv(d);
  if (b.dataset.drv === "del" && confirm("Delete this saved drive?")) { list.splice(+b.dataset.i, 1); lsSet(LS_DRIVES, list); renderTests(); }
});
document.addEventListener("toggle", (e) => { if (e.target.matches && e.target.matches("[data-drvlist]")) T.drivesOpen = e.target.open; }, true);

renderTests();
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


FTB_MEANINGS = {
    "01": "general electrical failure", "02": "general signal failure", "04": "internal system failure", "07": "mechanical failure",
    "11": "circuit short to ground", "12": "circuit short to battery", "13": "circuit open",
    "14": "short to ground or open", "15": "short to battery or open", "16": "voltage below threshold", "17": "voltage above threshold",
    "1C": "voltage out of range", "1F": "circuit intermittent",
    "23": "signal stuck low", "24": "signal stuck high", "29": "signal invalid", "2F": "signal erratic", "31": "no signal",
    "41": "checksum failure", "42": "memory failure", "49": "internal electronic failure", "4B": "over temperature",
    "64": "signal plausibility failure", "71": "actuator stuck", "72": "actuator stuck open", "73": "actuator stuck closed",
    "77": "commanded position not reachable", "78": "alignment or adjustment incorrect", "7A": "fluid leak or seal failure",
    "7B": "fluid level low", "81": "invalid serial data received", "87": "missing message (lost communication)",
    "88": "bus off (module quit talking)", "92": "performance / incorrect operation", "93": "no operation",
    "94": "unexpected operation", "96": "component internal failure", "97": "operation obstructed or blocked",
    "98": "component over temperature",
}


def with_ftb(code: str) -> str:
  """P0171 -> P0171; C0031-11 -> 'C0031-11 (circuit short to ground)'."""
  m = re.search(r"-([0-9A-F]{2})$", str(code or ""))
  t = FTB_MEANINGS.get(m.group(1)) if m else None
  return f"{code} ({t})" if t else str(code)


def _fmt_dtcs(d: dict) -> str:
  out = (f"Engine/emissions (OBD-II) stored: {', '.join(d.get('stored') or []) or 'none'} | pending: "
         f"{', '.join(d.get('pending') or []) or 'none'} | permanent: {', '.join(d.get('permanent') or []) or 'none'}")
  mods = [f"{m.get('name')} [{m.get('addr')}]: " + ", ".join(f"{with_ftb(c.get('code'))} ({c.get('status')})" for c in m.get("codes", []))
          for m in d.get("modules") or [] if m.get("codes")]
  ff = d.get("freeze") or {}
  ffs = (f" | Freeze frame for {ff.get('dtc')}: " + ", ".join(f"{k} {v}" for k, v in (ff.get("vals") or {}).items())) if ff.get("dtc") else ""
  return out + (" | Other modules -> " + "; ".join(mods) if mods else "") + ffs


def module_codes(d: dict) -> dict:
  """code -> 'Module name · status' for every module code the scanner found."""
  return {c["code"]: f"{m.get('name', 'Module')} · {c.get('status', '')}"
          for m in d.get("modules") or [] for c in m.get("codes", []) if c.get("code")}


def handle_ble_event(ev: dict):
  if ev.get("type") == "sync":
    d = ev.get("dtcs") or {}
    ss.ble_dtcs = d
    ss.scan_data = {k: ev.get(k) for k in ("pids", "readiness", "mode6", "at", "flags")}
    codes = list(dict.fromkeys((d.get("stored") or []) + (d.get("pending") or [])))
    for m in d.get("modules") or []:   # ABS, airbag, body, HVAC... (skip old "history" codes)
      codes += [c["code"] for c in m.get("codes", []) if c.get("status") != "history" and c["code"] not in codes]
    vin = (ev.get("vin") or "").upper()
    upd = {}
    if VIN_RE.fullmatch(vin):
      if vin == ss.active_vin or load_vehicle(vin):
        upd["vin_input"] = vin
    upd["sel_codes"] = codes  # scanned codes go straight into the Diagnose tab
    append_to_log(vin=vin or ss.active_vin, vehicle=ss.vehicle_info, dtc=", ".join(codes) or "No codes",
                  customer=ss.customer_name, phone=ss.customer_phone)
    queue_update(toast=f"Scanner synced: {vin or 'no VIN'} · {len(codes)} code(s) sent to the Diagnose tab", **upd)

  elif ev.get("type") == "log":
    for e in ev.get("entries") or []:
      log_problem(e.get("kind", "scanner"), e.get("where", "Bluetooth scanner"), e.get("message", ""), e.get("details", ""))
    if ev.get("debug"):
      ss.scanner_debug = ev["debug"]
      ss._toast = "Scanner debug info saved to the problem log"

  elif ev.get("type") == "drive":
    rec = ev.get("record") or {}
    if rec.get("id"):
      rec.setdefault("job", ss.get("job_id"))
      ss.setdefault("drives", {})[rec["id"]] = rec
      store_put("drive", rec["id"], rec)
      ss.drive_pick = rec["id"]
      ss.drive_review_pending = rec["id"]   # the AI team reviews every drive automatically
      ss._toast = "Test drive saved — the AI team is reviewing it (📋 Log → 🚗 Test drive review)"

  elif ev.get("type") == "tests":
    ss.test_results = ev.get("results") or {}

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

PLAUSIBILITY ALERTS the dashboard flagged (readings that don't add up; weigh these heavily):
{chr(10).join('- ' + f for f in (ev.get('flags') or [])) or 'none'}

MODE $06 RESULTS (value [min..max]):
{ev.get('mode6') or 'Not read'}

GUIDED TEST RESULTS (fuel trim / VE / catalyst / charging / power & braking, if run):
{json.dumps(ev.get('tests') or ss.test_results or {}) or 'none'}
{shop_context()}

DIAGNOSTIC TASK:
1. Fuel control: total trim (STFT + LTFT) Bank 1 vs Bank 2; single- vs dual-bank pattern.
2. Powertrain/drivetrain health from whatever enhanced data is present.
3. Air metering & O2/AFR sensors: sensor activity vs catalyst storage on each bank.
4. Mode $06: cylinder misfire counts and any failing or marginal monitor tests.
5. Readiness: which monitors are incomplete and the drive-cycle conditions to set them.
6. The single most definitive next physical/electrical test to confirm the root cause.

Use clean bold section headers and direct shop-floor language. Skip sections with no data."""
      label = f"[Full AI Check - {ev.get('at')}]"
    drive_mode = ev.get("mode") == "drive"
    with st.status("🤖 AI team is checking the live data...", expanded=False) as status:
      text, research, draft, ds_draft = team_answer(
          prompt, vehicle, dtcs, ss.symptoms.strip(), use_web=bool(not drive_mode and ss.get("use_web") and secret("PERPLEXITY_API_KEY")),
          status=status, fast=drive_mode)
      status.update(label="Done", state="complete")
    ss.ble_ai = {"id": ev.get("id"), "text": text, "label": label + " · " + team_names(draft, ds_draft, research)}
    st.rerun()


with tab2, guard("Live Telemetry tab"):
  st.subheader("📊 Scanner & Live Data")
  context_bar()
  st.caption("Works in Chrome (Android, Windows, macOS, ChromeOS). Connecting reads the VIN and codes and fills them"
             " into the other tabs automatically. The Bluetooth link stays up while you use the rest of the app.")
  _vd = ss.vehicle_details or {}
  oem_repo, oem_sigs = obdb_signals(_vd.get("Make", ""), _vd.get("Model", ""), str(_vd.get("Model Year", "")))
  _disp = re.search(r"\d+(\.\d+)?", str(_vd.get("Displacement (L)") or _vd.get("Engine") or ""))
  event = _ble_dashboard(vehicle=ss.vehicle_info, make=make_profile(), year=_vd.get("Model Year", ""),
                         disp=_disp.group(0) if _disp else "",
                         cyl=str(_vd.get("Engine Number of Cylinders") or
                                 (re.search(r"[VIL](\d{1,2})\b|(\d{1,2})\s*cyl", str(_vd.get("Engine", "")), re.I) or [None, ""])[1] or ""),
                         oem=oem_sigs, oem_src=oem_repo, ai=ss.ble_ai, key="ble", default=None)
  if isinstance(event, dict) and event.get("id") and event["id"] != ss.ble_last_event:
    ss.ble_last_event = event["id"]
    handle_ble_event(event)

  # ---- Drive cycle coach: a concrete plan to finish the incomplete monitors ----
  _rdy = (ss.scan_data or {}).get("readiness") or ""
  if "NOT READY" in _rdy:
    _left = [p.split(":")[0].strip() for p in _rdy.split(";") if "NOT READY" in p]
    st.markdown(f"**🧭 Drive cycle coach** — monitors not finished yet: **{', '.join(_left)}**")
    st.caption("During a test drive the app watches these and says it out loud when one completes. "
               "Tap below for a drive plan to set the rest.")
    if st.button("📋 Build a drive cycle plan for this vehicle"):
      with st.spinner("Writing the drive plan..."):
        _plan, _who = quick_ai(f"""You are an ASE master technician. Vehicle: {ss.vehicle_info or 'OBD-II vehicle'}.
These I/M readiness monitors are incomplete: {', '.join(_left)}.
Full readiness status: {_rdy}

Write a single practical drive cycle plan to complete them, in order, as a numbered checklist a technician follows
while driving. For each step give: starting conditions (cold engine / coolant temp / fuel level if it matters),
exact speeds, times and throttle behavior, and WHICH monitor that step completes. Mention this make's known quirks
for setting these monitors if you are sure of them. Keep it under 300 words.""", max_tokens=900)
      ss.drive_plan = ("" if _plan.startswith("⚠️") else f"_{_who}_\n\n") + _plan
    if ss.drive_plan:
      with st.expander("📋 Drive cycle plan", expanded=True):
        st.markdown(ss.drive_plan)

# ========================================================
# --- TAB 3: DIAGNOSE (STRATEGY + SCOPE LAB + COPILOT) ---
# ========================================================
def scan_context() -> str:
  """Everything the scanner captured, for the AI prompts."""
  tests = ("\nGuided test results: " + json.dumps(ss.test_results)) if ss.test_results else ""
  if not ss.ble_dtcs and not ss.scan_data:
    return "No scanner data (codes entered by hand)." + tests + shop_context()
  sd = ss.scan_data or {}
  pids = json.dumps(sd.get("pids") or {}, indent=0) if sd.get("pids") else "not captured"
  return (f"Scanner codes: {_fmt_dtcs(ss.ble_dtcs)}\n"
          f"I/M readiness: {sd.get('readiness') or 'not read'}\n"
          + ("".join("PLAUSIBILITY ALERT (reading that doesn't add up): " + f + "\n" for f in (sd.get("flags") or [])))
          + f"Mode $06 results: {sd.get('mode6') or 'not read'}\n"
          + f"Live data snapshot at sync ({sd.get('at') or '?'}): {pids}" + tests + shop_context())


# ========================================================
# --- SCOPE DATA FILE SCREEN (Diagnose tab, section 2) ---
# ========================================================
WAVE_CONDITIONS = ["Hot idle", "Cold idle", "Cranking (no start)", "2500 RPM steady", "Snap throttle",
                   "Road test / under load", "Key on, engine off"]
WAVE_PROMPT = """You are a master automotive scope diagnostician (ignition, injectors, sensors, current ramps, pressure transducers).
The app measured this capture from the scope's RAW DATA FILE — the numbers below are exact measurements, not guesses
from a photo. Base your analysis on them. Never invent a measurement that isn't here.
The typical ranges in APP FLAGS are general guides; this engine's own specs can differ — say so when it matters.

Vehicle: {vehicle}
Fault codes: {codes}
Symptoms / complaint: {symptoms}
{scan}

{capture}
{compare}

FORMAT STRICTLY AS:
### 1. What the measurements show
(Per channel: the key numbers and what each one means, in shop terms.)
### 2. Normal vs. abnormal
(Which numbers are out of line and why; cross-check the channels against each other and against the codes/scan data.)
### 3. Most likely cause(s), ranked
### 4. Next test to confirm
(Exactly what to hook up where, what to look for, and what result proves it.)"""


@st.cache_data(show_spinner=False, max_entries=6)
def load_capture(raw: bytes) -> dict:
  return parse_scope_csv(raw)


@st.cache_data(show_spinner=False, max_entries=48)
def measure_cached(raw: bytes, idx: int, wtype: str, factor: float, cyl: int) -> dict:
  cap = load_capture(raw)
  return measure_channel(cap["t"], cap["chans"][idx]["y"] * factor, cap["dt"], wtype, cyl or None)


def _pretty_key(k: str) -> str:
  out = k
  for suf, lab in (("_kv_per_ms", " (kV/ms)"), ("_kv", " (kV)"), ("_ms", " (ms)"), ("_pct", " (%)"), ("_hz", " (Hz)"),
                   ("_pp", " (peak-to-peak)"), ("_a", " (A)"), ("_v", " (V)")):
    if out.endswith(suf):
      out = out[: -len(suf)] + lab
      break
  return out.replace("_", " ").capitalize()


def _pretty_val(v):
  if isinstance(v, dict):
    return " · ".join(f"{k}: {x}%" if k.startswith(("hump", "pulse", "cyl")) else f"{k}: {x}" for k, x in v.items())
  if isinstance(v, bool):
    return "yes" if v else "no"
  return "—" if v is None else str(v)


def scope_data_section():
  st.markdown("**📈 Scope data file — the app measures it exactly (best)**")
  st.caption("On the scope, save the capture as **CSV**: PicoScope → File → Save As → CSV · Hantek / Owon → Save → CSV · "
             "most others: Export → CSV or text. A photo of the screen (further down) still works, but a data file "
             "gives real numbers instead of the AI's best read of a picture.")
  wf = st.file_uploader("Scope CSV file", type=["csv", "txt"], key=f"wave_csv_{ss.get('job_n', 0)}")
  if not wf:
    if ss.get("wave_result"):
      with st.expander(f"🔬 Last scope data analysis · {ss.wave_result.get('team', '')}", expanded=False):
        st.markdown(ss.wave_result["text"])
    return
  raw = wf.getvalue()
  try:
    with st.spinner("Reading the capture..."):
      cap = load_capture(raw)
  except ValueError as e:
    st.error(str(e))
    return
  except Exception as e:
    log_problem("scope", "Scope CSV", f"{type(e).__name__}: {e}")
    st.error("Couldn't read that file. Make sure it's the CSV/text export from the scope.")
    return
  fid = hashlib.md5(raw).hexdigest()[:10]
  st.caption(f"✅ {len(cap['chans'])} channel(s) · {cap['n']:,} samples · {(cap['t'][-1] - cap['t'][0]) * 1000:.1f} ms long · "
             f"one sample every {cap['dt'] * 1e6:.1f} µs")

  # ---- setup: what was going on, and what's on each channel ----
  vd = ss.vehicle_details or {}
  try:
    def_cyl = int(str(vd.get("Engine Number of Cylinders") or "0").split(".")[0])
  except ValueError:
    def_cyl = 0
  c1, c2, c3, c4 = st.columns(4)
  cond = c1.selectbox("Engine condition", WAVE_CONDITIONS, key=f"wv_cond_{fid}")
  rpm = c2.text_input("RPM (optional)", key=f"wv_rpm_{fid}")
  cyl = int(c3.number_input("Cylinders", 0, 16, value=min(max(def_cyl, 0), 16), key=f"wv_cyl_{fid}", help="0 = unknown"))
  fo = c4.text_input("Firing order (optional)", key=f"wv_fo_{fid}", placeholder="e.g. 1-3-4-2")
  setup = {"condition": cond, "rpm": rpm, "cyl": cyl or None, "fo": fo, "chans": []}
  keys = list(WAVE_TYPES)
  results = []
  for i, ch in enumerate(cap["chans"]):
    a, b, c = st.columns([2.4, 0.8, 1.2])
    g = guess_type(ch)
    wtype = a.selectbox(f"{ch['name']} ({ch['unit']}) is:", keys, index=keys.index(g), format_func=lambda k: WAVE_TYPES[k],
                        key=f"wv_t_{fid}_{i}")
    cyl_no = int(b.number_input("Cyl #", 0, 16, value=0, key=f"wv_c_{fid}_{i}", help="Cylinder this probe is on (0 = not one cylinder)"))
    want = WAVE_UNITS.get(wtype, ch["unit"])
    auto = 0.001 if (wtype == "sec_ign" and ch["unit"].lower() == "v" and np.nanmax(np.abs(ch["y"])) > 400) else 1.0
    factor = float(c.number_input(f"Scale: 1 {ch['unit']} =", value=auto, format="%g", key=f"wv_f_{fid}_{i}_{wtype}",
                                  help="Probe/sensor conversion. Current clamp at 10 mV/A → 100. Pressure transducer: "
                                       "its psi per volt (check its range setting). Leave 1 if the scope already shows real units."))
    unit = want if factor != 1.0 else ch["unit"]
    if factor == 1.0 and ch["unit"].lower() == "v" and want not in ("V", "kV") and wtype != "volts":
      st.caption(f"↳ Showing volts. Enter your probe's scale above to read it in {want}.")
    if wtype in ("sec_ign",) and unit.lower() == "v":
      st.caption("↳ Secondary is measured in kV — if the scope recorded volts, set the scale to 0.001.")
    results.append(measure_cached(raw, i, wtype, factor, cyl))
    setup["chans"].append({"type": wtype, "cyl_no": cyl_no, "unit": unit, "_y": ch["y"] * factor, "name": ch["name"]})

  # ---- relative compression: name the cylinders from an ignition sync ----
  sync = next(((r, s_) for r, s_ in zip(results, setup["chans"]) if s_["type"] in ("sec_ign", "pri_ign", "coil_amp")
               and s_["cyl_no"] and r["events"]), None)
  for r in results:
    if r["type"] == "rel_comp" and sync and cyl and fo:
      named = name_cylinders(r["events"], [e["time_ms"] for e in sync[0]["events"]], cyl, fo, sync[1]["cyl_no"])
      if named:
        r = dict(r)
        r["measurements"]["relative_by_cylinder_pct"] = named
        weak = min(named.items(), key=lambda kv: kv[1] or 999)
        if weak[1] is not None and weak[1] < 85:
          r["notes"].insert(0, f"Weakest: {weak[0]} at {weak[1]}% of average (named from the cylinder {sync[1]['cyl_no']} "
                               f"spark and firing order {fo}). Confirm with a compression or leak-down test on that cylinder.")

  # ---- show each channel ----
  for ch, r, s_ in zip(cap["chans"], results, setup["chans"]):
    with st.container(border=True):
      st.markdown(f"**{ch['name']} — {WAVE_TYPES.get(r['type'], r['type'])}**" + (f" · cylinder {s_['cyl_no']}" if s_["cyl_no"] else ""))
      tt, yy = envelope(cap["t"], s_["_y"], 1500)
      st.line_chart({"ms": tt * 1000, f"{ch['name']} ({s_['unit']})": yy}, x="ms", height=200)
      st.dataframe([{"Measurement": _pretty_key(k), "Value": _pretty_val(v)} for k, v in r["measurements"].items()],
                   use_container_width=True, hide_index=True)
      for n in r["notes"]:
        st.warning(n)
      if r["events"]:
        with st.expander(f"Every event ({len(r['events'])})"):
          st.dataframe(r["events"], use_container_width=True, hide_index=True)

  # ---- known-good library: save + compare by the numbers ----
  saved = store_list("csvwave", 80)
  my_types = {s_["type"] for s_ in setup["chans"]}
  matches = {r_["id"]: (r_.get("data") or {}) for r_ in saved
             if my_types & {x.get("type") for x in ((r_.get("data") or {}).get("setup") or {}).get("chans", [])}}
  compare_txt = ""
  cs1, cs2 = st.columns([1.4, 1])
  with cs1:
    ref_id = st.selectbox("Compare with a saved known-good capture:", [None] + list(matches), index=0,
                          format_func=lambda k: "No comparison" if k is None else
                          f"{matches[k].get('label', '?')} · {matches[k].get('vehicle') or ''} · {matches[k].get('date', '')}",
                          key=f"wv_ref_{fid}")
  with cs2:
    with st.form(f"wv_save_{fid}", clear_on_submit=True):
      lab = st.text_input("Save this capture as:", placeholder="e.g. Known-good secondary, 2014 Traverse 3.6 hot idle")
      if st.form_submit_button("💾 Save to library") and lab.strip():
        store_put("csvwave", datetime.now().strftime("%Y%m%d%H%M%S"), {
            "label": lab.strip(), "vehicle": ss.vehicle_info, "date": datetime.now().strftime("%Y-%m-%d"), "tech": ss.get("tech_user") or "",
            "setup": {k: v for k, v in setup.items() if k != "chans"} | {"chans": [{k: v for k, v in c.items() if k != "_y"} for c in setup["chans"]]},
            "results": [{"type": r["type"], "measurements": r["measurements"], "notes": r["notes"]} for r in results],
            "trace": [dict(zip(("t", "y"), (list(np.round(a_ * 1000, 3)), [None if not np.isfinite(v) else round(float(v), 4) for v in b_])))
                      for a_, b_ in (envelope(cap["t"], c["_y"], 500) for c in setup["chans"])]})
        st.toast("Saved to the scope library")
  if ref_id:
    ref = matches[ref_id]
    rows, lines = [], []
    for r, s_ in zip(results, setup["chans"]):
      k = next((j for j, c in enumerate(ref["setup"]["chans"]) if c.get("type") == s_["type"]), None)
      if k is None:
        continue
      rm = ref["results"][k]["measurements"]
      for key, val in r["measurements"].items():
        rv = rm.get(key)
        if isinstance(val, (int, float)) and isinstance(rv, (int, float)) and not isinstance(val, bool):
          diff = round((val - rv) / abs(rv) * 100) if rv else None
          rows.append({"Channel": s_["name"], "Measurement": _pretty_key(key), "This car": val, "Known-good": rv,
                       "Difference": f"{diff:+d}%" if diff is not None else "—"})
          lines.append(f"{s_['name']} {key}: this {val} vs known-good {rv}" + (f" ({diff:+d}%)" if diff is not None else ""))
      tr = (ref.get("trace") or [])[k] if k < len(ref.get("trace") or []) else None
      if tr:
        st.line_chart({"ms": tr["t"], f"Known-good: {ref.get('label', '')}": tr["y"]}, x="ms", height=160)
    if rows:
      st.dataframe(rows, use_container_width=True, hide_index=True)
      compare_txt = (f"KNOWN-GOOD REFERENCE from this shop's library ({ref.get('label')}, {ref.get('vehicle') or ''}):\n"
                     + "\n".join(lines))
  with st.expander(f"📚 Scope library ({len(saved)} saved data captures)"):
    for r_ in saved:
      d_ = r_.get("data") or {}
      l1, l2 = st.columns([6, 1])
      l1.markdown(f"**{d_.get('label', '?')}** · {d_.get('vehicle') or ''} · {d_.get('date', '')} · "
                  + ", ".join(WAVE_TYPES.get(c.get("type"), "?") for c in (d_.get("setup") or {}).get("chans", [])))
      if l2.button("🗑️", key=f"delcw_{r_['id']}", help="Delete this saved capture"):
        store_delete("csvwave", r_["id"])
        st.rerun()

  # ---- the AI team reads the numbers ----
  if st.button("🔍 Have the AI team interpret these measurements", type="primary", key=f"wv_ai_{fid}"):
    prompt = WAVE_PROMPT.format(vehicle=ss.vehicle_info or "not given", codes=", ".join(current_codes()) or "none",
                                symptoms=(ss.symptoms or "").strip() or "not given", scan=scan_context(),
                                capture=capture_summary(cap, setup, results), compare=compare_txt)
    with st.status("The AI team is reading the measurements...", expanded=False) as status:
      text, _r, draft, ds_draft = team_answer(prompt, ss.vehicle_info or "vehicle", ", ".join(current_codes()),
                                              (ss.symptoms or "").strip(), False, status)
      status.update(label="Done", state="complete")
    ss.wave_result = {"text": text, "team": team_names(draft, ds_draft, ""), "file": wf.name,
                      "at": datetime.now().strftime("%Y-%m-%d %I:%M %p")}
  if ss.get("wave_result"):
    with st.expander(f"🔬 Scope data analysis · {ss.wave_result.get('team', '')}", expanded=True):
      st.markdown(ss.wave_result["text"])


with tab3, guard("Diagnose tab"):
  st.subheader("🔧 Diagnose")
  context_bar()

  # ---------- 1. Codes ----------
  st.markdown("#### 1 · Fault codes")
  d = ss.ble_dtcs or {}
  kinds = {}
  kinds.update(module_codes(d))
  for kind in ("permanent", "pending", "stored"):  # stored wins if a code is in more than one list
    for c in d.get(kind) or []:
      kinds[c] = f"Engine (OBD) · {kind}"
  options = list(dict.fromkeys(list(kinds) + list(ss.sel_codes or [])))
  if options:
    st.multiselect(
        "Codes from the scanner (tap ✕ to leave one out):", options=options, key="sel_codes",
        format_func=lambda c: f"{c} · {kinds.get(c, 'added')}",
    )
  else:
    st.caption("Connect the scanner on the 📊 Scanner tab — the codes it reads show up here automatically.")
  st.text_input("Add codes by hand (optional):", key="manual_dtc", placeholder="e.g. P0171, P0174")
  st.text_area("Symptoms / customer complaint (optional — works with or without codes):", key="symptoms", height=80,
               placeholder="e.g. Rough idle when cold, stumbles on hard acceleration, no check engine light")

  # ❄️ Freeze frame vs the live readings captured at sync: what changed since the code set?
  _ff = (ss.ble_dtcs or {}).get("freeze") or {}
  if _ff.get("dtc") and _ff.get("vals"):
    _live = (ss.scan_data or {}).get("pids") or {}
    _lv = {str(k).strip().upper(): v for k, v in _live.items()}
    with st.expander(f"❄️ Freeze frame vs. now — conditions when {_ff['dtc']} set"):
      st.caption("Left: the moment the code set. Right: the live snapshot from the last scanner sync. "
                 "A big difference (coolant temp, load, trims) tells you the conditions to recreate.")
      st.dataframe([{"Reading": k, f"When {_ff['dtc']} set": v, "At last sync": _lv.get(str(k).strip().upper(), "—")}
                    for k, v in _ff["vals"].items()], use_container_width=True, hide_index=True)

  codes = current_codes()
  code_str = ", ".join(codes)
  has_pplx = bool(secret("PERPLEXITY_API_KEY"))
  col_engine, col_btn = st.columns([3, 1.4])
  with col_engine:
    use_web = st.toggle("🌐 Include Perplexity web research", value=has_pplx, disabled=not has_pplx, key="use_web",
                        help="Perplexity finds TSBs, recalls and known fixes online. Turn off for a faster answer.")
    st.caption("Team: " + " → ".join(x for x in [
        "🌐 Perplexity researches" if has_pplx else "",
        f"✨ {gemini_label()}" + (f" + 🐋 {deepseek_label()}" if has_deepseek() else "") + " draft",
        f"🧠 {claude_label()} reviews & finalizes" if has_claude() else ""] if x) +
        ("" if has_pplx else " · add PERPLEXITY_API_KEY for web research") +
        ("" if has_claude() else " · add ANTHROPIC_API_KEY for Claude's review") +
        ("" if has_deepseek() else " · add DEEPSEEK_API_KEY for a DeepSeek second opinion"))
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
- Put any matching confirmed fix from THIS SHOP'S OWN HISTORY and any matching NHTSA recall first.
"""
    with st.status("Working on it...", expanded=False) as status:
      text, research, draft, ds_draft = team_answer(sym_prompt, vehicle, "", symptoms, use_web, status)
      status.update(label="Done", state="complete")
    ss.dtc_result = {"title": f"Symptoms · {vehicle}", "text": text, "research": research, "draft": draft, "ds_draft": ds_draft,
                    "team": team_names(draft, ds_draft, research)}

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
- Put any matching confirmed fix from THIS SHOP'S OWN HISTORY and any matching NHTSA recall first.
"""
    with st.status("Working on it...", expanded=False) as status:
      text, research, draft, ds_draft = team_answer(dtc_prompt, vehicle, code_str, symptoms, use_web, status)
      status.update(label="Done", state="complete")
    ss.dtc_result = {"title": f"{code_str} · {vehicle}", "text": text, "research": research, "draft": draft, "ds_draft": ds_draft,
                    "team": team_names(draft, ds_draft, research)}

  if ss.dtc_result:  # stays on screen while you use other tabs
    team = ss.dtc_result.get("team") or team_names(ss.dtc_result.get("draft", ""), ss.dtc_result.get("ds_draft", ""),
                                                    ss.dtc_result.get("research", ""))
    with st.expander(f"📋 Test plan: {ss.dtc_result['title']} · {team}", expanded=True):
      st.markdown(ss.dtc_result["text"])
    if ss.dtc_result.get("draft"):
      with st.expander(f"✨ {gemini_label()}'s first draft (before {claude_label()}'s review)"):
        st.markdown(ss.dtc_result["draft"])
    if ss.dtc_result.get("ds_draft"):
      with st.expander(f"🐋 {deepseek_label()}'s draft (second opinion)"):
        st.markdown(ss.dtc_result["ds_draft"])
    if ss.dtc_result.get("research"):
      with st.expander("🌐 Web research Perplexity found (TSBs, recalls, known fixes, sources)"):
        st.markdown(ss.dtc_result["research"])

  # ---------- 2. Scope lab ----------
  st.write("---")
  st.markdown("#### 2 · Scope & test readings")
  with guard("Scope data file"):
    scope_data_section()
  st.markdown("**📸 Or a photo of the scope / meter screen**")
  col_scope, col_scratch = st.columns(2)
  with col_scope:
    scope_capture = st.camera_input("Capture oscilloscope or meter") if st.toggle("📷 Open Camera for Scope / Meter") else None
    scope_file = st.file_uploader("Or upload a scope / meter photo", type=["png", "jpg", "jpeg"], key="scope_upload")
    active_img = scope_capture or scope_file
    pil_scope_image = None
    if active_img:
      st.image(active_img.getvalue(), caption="Captured Scope / Meter Display")
      pil_scope_image = ImageOps.exif_transpose(Image.open(active_img))
      with st.form("save_wave", clear_on_submit=True):
        _wl1, _wl2 = st.columns([3, 1])
        _wave_label = _wl1.text_input("Save this capture to your waveform library as:",
                                      placeholder="e.g. Known-good CKP — 2014 Accord 2.4 hot idle")
        _wl2.write("")
        if st.form_submit_button("💾 Save waveform") and _wave_label.strip():
          store_put("wave", datetime.now().strftime("%Y%m%d%H%M%S"),
                    {"label": _wave_label.strip(), "vehicle": ss.vehicle_info, "tech": ss.get("tech_user") or "",
                     "date": datetime.now().strftime("%Y-%m-%d"), "b64": shrink_to_b64(active_img.getvalue(), 1000, 75)})
          st.toast("Waveform saved to the library")

    _waves = store_list("wave", 80)
    _wave_pick = None
    if _waves:
      _wopts = {r["id"]: (r.get("data") or {}) for r in _waves}
      _wave_pick = st.selectbox("Compare against a saved waveform (optional):", [None] + list(_wopts), index=0,
                                format_func=lambda i: "No comparison" if i is None else
                                f"{_wopts[i].get('label', '?')} · {_wopts[i].get('vehicle') or ''} · {_wopts[i].get('date', '')}")
      if _wave_pick:
        try:
          st.image(base64.b64decode(_wopts[_wave_pick].get("b64", "")), caption=f"Reference: {_wopts[_wave_pick].get('label', '')}", width=320)
        except Exception:
          st.warning("Couldn't show that saved waveform.")
      with st.expander(f"📚 Waveform library ({len(_waves)} saved)"):
        _wq = st.text_input("Filter:", key="wave_filter", placeholder="e.g. CKP, Accord, injector")
        for _wid, _wd in _wopts.items():
          if _wq.strip() and _wq.strip().lower() not in (_wd.get("label", "") + " " + (_wd.get("vehicle") or "")).lower():
            continue
          _wc1, _wc2 = st.columns([5, 1])
          with _wc1:
            try:
              st.image(base64.b64decode(_wd.get("b64", "")), caption=f"{_wd.get('label', '')} · {_wd.get('vehicle') or ''} · {_wd.get('date', '')}", width=300)
            except Exception:
              st.caption(f"{_wd.get('label', '')} (image unreadable)")
          if _wc2.button("🗑️", key=f"delw_{_wid}", help="Delete this saved waveform"):
            store_delete("wave", _wid)
            st.rerun()

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

Web research already found for this job (TSBs / known fixes, if any):
{(ss.dtc_result or {}).get("research", "")[:2500] or 'none'}

TASK:
- Identify the signal type (secondary/primary ignition, injector voltage/current, CKP/CMP correlation, relative compression, PWM, sensor drop).
- Evaluate key signatures: firing/inductive kV, dwell, burn line slope & turbulence, coil oscillations, ground bounce, attenuation, missing-tooth spacing.
- Correlate waveform abnormalities with the physical readings, the fault codes and the scan data.
{"- A SECOND image is attached: a KNOWN-GOOD reference waveform from this shop's library (" + _wopts[_wave_pick].get("label", "") + "). Compare the capture against it and call out every meaningful difference." if _wave_pick and pil_scope_image else ""}

FORMAT STRICTLY AS:
### 1. Scope Waveform & Electrical Findings
### 2. Component Condemnation & Defect Root Cause
### 3. Immediate Pinpoint Verification Step
"""
    img_b64 = [img_part(pil_scope_image)["inline_data"]["data"]] if pil_scope_image else []
    if _wave_pick and pil_scope_image:
      img_b64.append(_wopts[_wave_pick].get("b64", ""))
    with st.status("Working on it...", expanded=False) as status:
      text, _r, draft, ds_draft = team_answer(prompt, ss.vehicle_info or "vehicle", code_str, ss.symptoms.strip(), False, status,
                                              image_b64=img_b64)
      status.update(label="Done", state="complete")
    ss.scope_result = {"text": text, "team": team_names(draft, ds_draft, ""), "draft": draft, "ds_draft": ds_draft}

  if ss.scope_result:
    sr = ss.scope_result if isinstance(ss.scope_result, dict) else {"text": str(ss.scope_result), "team": ""}
    with st.expander(f"🔬 Scope & readings evaluation · {sr.get('team', '')}", expanded=True):
      st.markdown(sr["text"])
    if sr.get("draft") or sr.get("ds_draft"):
      with st.expander("👀 See each AI's own read"):
        if sr.get("draft"):
          st.markdown(f"**✨ {gemini_label()}** (saw the photo)")
          st.markdown(sr["draft"])
        if sr.get("ds_draft"):
          st.markdown(f"**🐋 {deepseek_label()}** (readings only — can't see photos)")
          st.markdown(sr["ds_draft"])

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
      for thumb in msg.get("photos") or []:
        st.image(thumb, width=220)
      st.markdown(msg["content"])

  # 📷 Photos for the next question: wiring diagrams, connectors, parts, scope or meter screens
  nkey = ss.get("chat_photo_n", 0)
  with st.expander("📷 Add photos to your question (wiring diagram, connector, part, scope, meter)",
                   expanded=bool(ss.get(f"chat_cam_on_{nkey}"))):
    chat_files = st.file_uploader("Take or upload photos (up to 4)", type=["png", "jpg", "jpeg", "webp"],
                                  accept_multiple_files=True, key=f"chat_files_{nkey}_{ss.get('job_n', 0)}") or []
    chat_cam = st.camera_input("Take a photo", key=f"chat_cam_{nkey}") if st.toggle("Use in-app camera instead", key=f"chat_cam_on_{nkey}") else None
    chat_imgs = []
    for f in ([chat_cam] if chat_cam else []) + list(chat_files):
      try:
        chat_imgs.append(ImageOps.exif_transpose(Image.open(f)))
      except Exception:
        st.warning(f"Couldn't open {getattr(f, 'name', 'that photo')} — try a JPG or PNG.")
    chat_imgs = chat_imgs[:4]
    if chat_imgs:
      st.image([im.convert("RGB") for im in chat_imgs], width=140)
      st.caption(f"{len(chat_imgs)} photo(s) will go with your next question. Gemini and Claude read them; DeepSeek works from your text.")

  chat_quick = st.toggle("⚡ Quick answers — one AI, a few seconds (turn off to have the whole team check every answer)",
                         value=True, key="chat_quick")
  user_question = st.chat_input("Ask a question (add photos above first if you want)" if not chat_imgs else
                                f"Ask about the {len(chat_imgs)} photo(s) — e.g. 'Which wire is the 5V reference?'")
  if user_question:
    photos_b64 = [_jpeg_b64(im, 2000) for im in chat_imgs]       # big enough to read wire colors and pin numbers
    thumbs = []
    for im in chat_imgs:
      t = im.convert("RGB"); t.thumbnail((500, 500)); b = io.BytesIO(); t.save(b, format="JPEG", quality=80); thumbs.append(b.getvalue())
    ss.chat_history.append({"role": "user", "content": user_question, "photos": thumbs})
    if chat_imgs:
      ss.chat_photo_n = nkey + 1        # empties the photo box for the next question
    with st.chat_message("user"):
      for thumb in thumbs:
        st.image(thumb, width=220)
      st.markdown(user_question)
    history = "\n".join(f"{m['role'].upper()}: {m['content']}" + (f" [attached {len(m['photos'])} photo(s)]" if m.get("photos") else "")
                        for m in ss.chat_history[-6:])
    plan = (ss.dtc_result or {}).get("text", "")[:3000]
    chat_prompt = f"""
You are an expert automotive diagnostic technician assisting a mechanic in the field.
Vehicle: {ss.vehicle_info or 'General'}
Fault codes being worked: {code_str or 'None'}
Symptoms / complaint: {ss.symptoms.strip() or 'not given'}
{scan_context()}
Current test plan (if any): {plan or 'none yet'}
Latest scope/readings evaluation (if any): {((ss.scope_result or {}).get('text', '') if isinstance(ss.scope_result, dict) else (ss.scope_result or ''))[:1500] or 'none'}
Latest scope DATA FILE analysis (measured from raw data, if any): {((ss.wave_result or {}).get('text', ''))[:2000] or 'none'}

Recent conversation:
{history}

Earlier web research for this job (if any): {(ss.dtc_result or {}).get("research", "")[:2500] or 'none'}

Respond directly, practically, and concisely to the latest question. Focus on physical shop tests, circuit checks, and logical isolation.
""" + (f"""
The technician attached {len(photos_b64)} photo(s) with this question (wiring diagram, connector, part, scope or meter).
Read them carefully: wire colors, pin/cavity numbers, splices, grounds, connector IDs, component names, readings on screen.
Say what you can read in the photo, and say so plainly if part of it is too blurry or cut off to read.""" if photos_b64 else "")
    with st.chat_message("assistant"):
      if chat_quick:
        with st.spinner("Thinking..."):
          reply, who = quick_ai(chat_prompt, image_b64=photos_b64, max_tokens=1500)
        research = ""
        st.caption(who + " · quick answer")
      else:
        with st.status("Working on it...", expanded=False) as status:
          reply, research, draft, ds_draft = team_answer(
              chat_prompt, ss.vehicle_info or "General vehicle", code_str, ss.symptoms.strip(),
              bool(ss.get("use_web", False) and secret("PERPLEXITY_API_KEY")), status, question=user_question, image_b64=photos_b64)
          status.update(label="Done", state="complete")
        st.caption(team_names(draft, ds_draft, research))
      st.markdown(reply)
      if research:
        with st.expander("🌐 Sources Perplexity found"):
          st.markdown(research)
    ss.chat_history.append({"role": "assistant", "content": reply})

# ========================================================
# --- TEST DRIVE REVIEW (saved drives from the Bluetooth dashboard) ---
# ========================================================
FSS_NAMES = {1: "CL", 2: "OL cold", 3: "OL decel", 4: "OL fault", 5: "CL O2 fault", 9: "other"}


def load_drives() -> dict:
  drives = dict(ss.get("drives") or {})
  for r in store_list("drive", 40):
    if r.get("id") and r["id"] not in drives and isinstance(r.get("data"), dict):
      drives[r["id"]] = r["data"]
  return dict(sorted(drives.items(), key=lambda kv: kv[0], reverse=True))


def drive_rows(rec: dict) -> list[dict]:
  keys = rec.get("keys") or []
  out = []
  for smp in rec.get("samples") or []:
    row = {"sec": smp[0]}
    row.update({k: smp[1 + i] for i, k in enumerate(keys)})
    row["fuel_system"] = FSS_NAMES.get(smp[-2], "") if len(smp) >= len(keys) + 3 else ""
    row["decel"] = bool(smp[-1]) if len(smp) >= len(keys) + 3 else False
    out.append(row)
  return out


def drive_text(rec: dict) -> str:
  rows = drive_rows(rec)
  step = 5 if len(rows) <= 1800 else 10
  cols = ["sec", "rpm", "spd", "load", "tps", "stft1", "ltft1", "stft2", "ltft2", "o2b1s1", "o2b1s2", "ect", "fuel_system", "decel"]
  cols = [c for c in cols if any(r.get(c) not in (None, "", False) for r in rows)] or ["sec"]
  def fmt(v):
    return "" if v is None else ("Y" if v is True else "" if v is False else str(v))
  lines = [",".join(cols)] + [",".join(fmt(r.get(c)) for c in cols) for r in rows[::step]][:600]
  alerts = rec.get("alerts") or []
  return "\n".join([
      "TEST DON'T GUESS — TEST DRIVE",
      f"App version {APP_VERSION} · Drive {rec.get('started')} · {rec.get('minutes')} min · status: {rec.get('status')}",
      f"Vehicle: {rec.get('vehicle') or ss.vehicle_info or 'unknown'} · VIN {rec.get('vin') or ss.active_vin or 'unknown'}",
      f"Codes: {json.dumps(rec.get('codes') or {})}",
      "", "DRIVE REPORT:", rec.get("report") or "(none)",
      "", "TEST RESULTS:", json.dumps(rec.get("results") or {}, indent=0)[:4000],
      "", f"SPOKEN ALERTS ({len(alerts)}), with readings at that moment:",
      *[f"- {a.get('at')} (+{a.get('t')}s): {a.get('text')} | {json.dumps(a.get('snap'))}"
        + (f"\n  HI-RES WINDOW around this alert (one row per live-data pass, 15 s before to 5 s after — find the first reading that moved):\n  "
           + str(a.get('win')).replace(chr(10), chr(10) + "  ") if a.get("win") else "")
        for a in alerts],
      "", f"MISFIRE EVENTS: {json.dumps((rec.get('misfires') or [])[-30:])}",
      "", f"TIMELINE every {step} s (fuel_system CL=closed loop; decel=Y means fuel cut/closed throttle):",
      *lines,
  ])


# ========================================================
# --- CUSTOMER / SHOP REPORT (shown at the bottom of the Diagnose tab) ---
# ========================================================
FOLLOW_UP_LABELS = {0: "No follow-up", 7: "In about 1 week", 14: "In about 2 weeks", 30: "In about 1 month",
                    60: "In about 2 months", 90: "In about 3 months", 180: "In about 6 months"}

CUSTOMER_SUMMARY_PROMPT = """Write a short summary of this diagnosis for the CAR OWNER (not a mechanic).
Vehicle: {vehicle}
Customer's complaint: {complaint}
Trouble codes: {codes}
Test results: {tests}
Technician's notes / recommendation: {notes}
Repair done: {fix}
Technician's diagnostic plan (for background only): {plan}

RULES:
- 4 to 7 short sentences in plain, friendly English. No jargon; if you must name a part, say what it does in a few words.
- Cover: what we found, what it means for the car (safety, reliability, or cost of waiting), and what we recommend or already fixed.
- Use ONLY the facts above. Do not invent findings, test results, prices or time estimates.
- If the technician's notes give a recommendation, that is the recommendation. If nothing is confirmed yet, say more testing is needed.
- No headings, no bullet points, no sign-off."""


def battery_slip_html() -> str:
  e = html_lib.escape
  t = ss.test_results or {}
  picked = {k: v for k, v in t.items() if re.search(r"charg|crank|battery|power", k, re.I)}
  def rows(v):
    if not isinstance(v, dict):
      return f"<tr><td>Result</td><td>{e(str(v))}</td></tr>"
    return "".join(f"<tr><td>{e(str(k).replace('_', ' ').title())}</td><td>{e(str(x))}</td></tr>" for k, x in v.items() if x not in (None, ""))
  body = "".join(f"<h2>{e(k)}</h2><table>{rows(v)}</table>" for k, v in picked.items())
  shop = secret("SHOP_NAME") or "Test Don't Guess"
  return f"""<!doctype html><html><head><meta charset="utf-8"><title>Battery & charging test - {e(ss.vehicle_info or 'Vehicle')}</title>
<style>body{{font-family:Arial,sans-serif;color:#222;max-width:680px;margin:24px auto;padding:0 16px}}h1{{font-size:22px;margin:0}}
h2{{font-size:15px;border-bottom:2px solid #222;padding-bottom:3px;margin-top:20px}}table{{width:100%;border-collapse:collapse;font-size:13px}}
td{{border:1px solid #ccc;padding:5px 7px}}.muted{{color:#666;font-size:12px}}@media print{{button{{display:none}}}}</style></head><body>
<button onclick="window.print()" style="float:right;padding:8px 14px">Print / Save as PDF</button>
<h1>🔋 {e(shop)} — Battery & Charging Test</h1>
<div class="muted">{e(datetime.now().strftime("%B %d, %Y %I:%M %p"))}{(" · Technician: " + e(ss.get("tech_user") or "")) if ss.get("tech_user") else ""}</div>
<h2>Vehicle</h2><table><tr><td>Customer</td><td>{e(ss.customer_name or '')}</td></tr><tr><td>Vehicle</td><td>{e(ss.vehicle_info or '')}</td></tr>
<tr><td>VIN</td><td>{e(ss.active_vin or '')}</td></tr><tr><td>Odometer</td><td>{e(ss.odometer or '')}</td></tr></table>
{body}
<p class="muted">Guide: rest voltage ≥ 12.4 V, cranking ≥ 9.6 V, charging at idle 13.5–15.0 V. Results from on-vehicle testing.</p>
</body></html>"""


def build_report_html(notes: str) -> str:
  e = html_lib.escape
  d, vd = ss.ble_dtcs or {}, ss.vehicle_details or {}
  grade_color = {"GOOD": "#0a7d32", "MARGINAL": "#a66b00", "BAD": "#c62828"}
  code_rows = []
  for kind in ("stored", "pending", "permanent"):
    for c in d.get(kind) or []:
      code_rows.append(("Engine / emissions", c, kind))
  for m in d.get("modules") or []:
    for c in m.get("codes", []):
      code_rows.append((m.get("name", "Module"), c.get("code"), c.get("status")))
  for c in ss.sel_codes or []:
    if not any(c == r[1] for r in code_rows):
      code_rows.append(("Entered", c, ""))
  ff = d.get("freeze") or {}
  tests = ss.test_results or {}
  def grade_of(v):
    g = str(v.get("grade", "")).upper() if isinstance(v, dict) else ""
    return f'<b style="color:{grade_color.get(g, "#333")}">{e(g)}</b>' if g else ""
  plan = re.sub(r"^#+\s*", "", (ss.dtc_result or {}).get("text", ""), flags=re.M).replace("**", "")
  eng = str(vd.get("Displacement (L)") or vd.get("Engine") or "")
  if re.fullmatch(r"\d+(\.\d+)?", eng):
    eng += " L"
  def _money(v):
    try:
      return float(str(v).replace("$", "").replace(",", "") or 0)
    except ValueError:
      return 0.0
  est_rows = [r for r in (ss.estimate_rows or []) if isinstance(r, dict) and str(r.get("Item") or "").strip()]
  est_html = ""
  if est_rows:
    tp = sum(_money(r.get("Parts $")) for r in est_rows)
    tl = sum(_money(r.get("Labor $")) for r in est_rows)
    est_html = ("<h2>Estimate</h2><table><tr><th>Item</th><th>Parts</th><th>Labor</th></tr>" +
                "".join(f"<tr><td>{e(str(r.get('Item', '')))}</td><td>${_money(r.get('Parts $')):,.2f}</td>"
                        f"<td>${_money(r.get('Labor $')):,.2f}</td></tr>" for r in est_rows) +
                f"<tr><th>Total</th><th>${tp:,.2f}</th><th>${tl:,.2f}</th></tr></table>"
                f"<p><b>Estimate total: ${tp + tl:,.2f}</b> <span class=muted>(parts availability and final pricing may adjust this)</span></p>")
  photo_html = ""
  phs = job_photos()
  if phs:
    photo_html = ("<h2>Photos</h2><div>" +
                  "".join(f'<img src="data:image/jpeg;base64,{p_.get("b64", "")}" style="max-width:48%;margin:4px;border:1px solid #ccc">'
                          for p_ in phs[:8]) + "</div>")
  rows_codes = "".join(f"<tr><td>{e(str(a))}</td><td><b>{e(str(b))}</b></td><td>{e(str(c))}</td></tr>" for a, b, c in code_rows) or \
      "<tr><td colspan=3>No trouble codes found</td></tr>"
  rows_tests = "".join(
      f"<tr><td>{e(k)}</td><td>{grade_of(v)}</td><td>{e(str(v.get('verdict', '')) if isinstance(v, dict) else str(v))}</td></tr>"
      for k, v in tests.items()) or "<tr><td colspan=3>No guided tests run</td></tr>"
  ff_html = ("<h2>Freeze frame (" + e(ff.get("dtc", "")) + ")</h2><p>" +
             " · ".join(f"{e(k)}: <b>{e(str(v))}</b>" for k, v in (ff.get("vals") or {}).items()) + "</p>") if ff.get("dtc") else ""
  return f"""<!doctype html><html><head><meta charset="utf-8"><title>Diagnostic report - {e(ss.vehicle_info or 'Vehicle')}</title>
<style>body{{font-family:Arial,sans-serif;color:#222;max-width:820px;margin:24px auto;padding:0 16px}}h1{{margin:0;font-size:24px}}
h2{{font-size:16px;border-bottom:2px solid #222;padding-bottom:3px;margin-top:22px}}table{{width:100%;border-collapse:collapse;font-size:13px}}
td,th{{border:1px solid #ccc;padding:5px 7px;text-align:left;vertical-align:top}}th{{background:#f2f2f2}}.muted{{color:#666;font-size:12px}}
pre{{white-space:pre-wrap;font-family:inherit;font-size:13px;background:#fafafa;border:1px solid #ddd;padding:10px}}
@media print{{button{{display:none}}}}</style></head><body>
<button onclick="window.print()" style="float:right;padding:8px 14px">Print / Save as PDF</button>
<h1>⚡ Test Don't Guess — Diagnostic Report</h1><div class="muted">{e(datetime.now().strftime("%B %d, %Y %I:%M %p"))}</div>
<h2>Customer & vehicle</h2><table>
<tr><th>Customer</th><td>{e(ss.customer_name or '')}</td><th>Phone</th><td>{e(ss.customer_phone or '')}</td></tr>
<tr><th>Vehicle</th><td>{e(ss.vehicle_info or '')}</td><th>VIN</th><td>{e(ss.active_vin or 'not provided')}</td></tr>
<tr><th>Engine</th><td>{e(eng)}</td><th>Complaint</th><td>{e(ss.symptoms or '')}</td></tr>
<tr><th>Odometer</th><td>{e(ss.odometer or '')}</td><th>Technician</th><td>{e(ss.get('tech_user') or '')}</td></tr></table>
{"<h2>What we found</h2><p style='font-size:15px;line-height:1.5'>" + e(ss.customer_summary).replace(chr(10), "<br>") + "</p>" if (ss.customer_summary or "").strip() else ""}
{"<h2>Repair performed</h2><p><b>" + e(ss.fix_part) + "</b>" + ("<br>Verified by: " + e(ss.fix_test) if (ss.fix_test or "").strip() else "") + "</p>" if (ss.fix_part or "").strip() else ""}
<h2>Trouble codes</h2><table><tr><th>Module</th><th>Code</th><th>Status</th></tr>{rows_codes}</table>
{ff_html}
<h2>Test results</h2><table><tr><th>Test</th><th>Result</th><th>Details</th></tr>{rows_tests}</table>
{est_html}
{photo_html}
{"<h2>Technician notes & recommendation</h2><pre>" + e(notes) + "</pre>" if notes.strip() else ""}
{"<h2>Recommended follow-up</h2><p>" + e(FOLLOW_UP_LABELS.get(ss.follow_up_days, "")) + ((": " + e(ss.follow_up_note)) if (ss.follow_up_note or "").strip() else "") + "</p>" if ss.get("follow_up_days") else ""}
{"<h2>Diagnostic plan</h2><pre>" + e(plan) + "</pre>" if plan else ""}
<p class="muted">Results from on-board diagnostic data and road/bay tests. Further pinpoint testing may be required before parts replacement.</p>
</body></html>"""


with tab3, guard("Diagnose tab"):
  st.write("---")
  with st.expander("📸 4 · Job photos & estimate", expanded=bool(
      [r for r in (ss.estimate_rows or []) if isinstance(r, dict) and str(r.get("Item") or "").strip()])):
    st.caption("Photos save with the job and go on the customer report — the leaky gasket or chafed wire sells the repair "
               "better than words. The estimate prints on the report with a total.")
    _pc1, _pc2 = st.columns(2)
    with _pc1:
      _new_photos = st.file_uploader("📸 Add photos to this job", type=["png", "jpg", "jpeg", "webp"],
                                     accept_multiple_files=True, key=f"job_photos_{ss.get('photo_n', 0)}_{ss.get('job_n', 0)}")
      if _new_photos and st.button(f"💾 Attach {len(_new_photos)} photo(s) to the job"):
        autosave_job(force=True)
        if not ss.get("job_id"):
          st.warning("Add a customer, vehicle or code first so there's a job to attach them to.")
        else:
          _have = len(job_photos())
          for _i, _f in enumerate(_new_photos[: max(0, 12 - _have)]):
            try:
              store_put("jobphoto", f"{ss.job_id}-{datetime.now().strftime('%H%M%S%f')}{_i}",
                        {"job": ss.job_id, "b64": shrink_to_b64(_f.getvalue()), "name": getattr(_f, "name", ""),
                         "at": datetime.now().strftime("%Y-%m-%d %I:%M %p")})
            except Exception as _e:
              st.warning(f"Couldn't save {getattr(_f, 'name', 'a photo')}: {_e}")
          ss.photo_n = ss.get("photo_n", 0) + 1   # empty the picker
          queue_update(toast="Photo(s) attached to the job")
      _jp = job_photos()
      if _jp:
        st.caption(f"{len(_jp)} photo(s) on this job (12 max):")
        for _ph in _jp:
          _jc1, _jc2 = st.columns([5, 1])
          with _jc1:
            try:
              st.image(base64.b64decode(_ph.get("b64", "")), width=260, caption=_ph.get("at", ""))
            except Exception:
              st.caption("(photo unreadable)")
          if _jc2.button("🗑️", key=f"delp_{_ph['_id']}", help="Remove this photo"):
            store_delete("jobphoto", _ph["_id"])
            st.rerun()
    with _pc2:
      st.markdown("**🧾 Estimate** (tap a cell to edit; ➕ at the bottom adds a line)")
      _est_in = ss.estimate_rows if isinstance(ss.estimate_rows, list) and ss.estimate_rows else         [{"Item": "", "Parts $": 0.0, "Labor $": 0.0}]
      _est = st.data_editor(_est_in, num_rows="dynamic", use_container_width=True,
                            key=f"est_{ss.get('job_n', 0)}_{ss.get('job_id') or 'new'}")
      ss.estimate_rows = [r for r in (_est or []) if isinstance(r, dict)]
      def _money(v):
        try:
          return float(str(v).replace("$", "").replace(",", "") or 0)
        except ValueError:
          return 0.0
      _parts = sum(_money(r.get("Parts $")) for r in ss.estimate_rows)
      _labor = sum(_money(r.get("Labor $")) for r in ss.estimate_rows)
      if _parts or _labor:
        st.markdown(f"Parts **${_parts:,.2f}** · Labor **${_labor:,.2f}** · **Total ${_parts + _labor:,.2f}**")

  st.write("---")
  with st.expander("🧾 5 · Customer report — summary, email, text, print",
                   expanded=bool((ss.customer_summary or "").strip() or (ss.tech_notes or "").strip())):
    st.caption("One page with the vehicle, all codes, freeze frame, every test result (green / yellow / red) and the plan. "
               "Open it on your phone and use Print → Save as PDF, or text it to the customer.")
    notes = st.text_area("Technician notes / recommendation (goes on the report):", key="tech_notes", height=80,
                         placeholder="e.g. Recommend replacing cylinder 3 ignition coil and spark plugs. Fuel trims normal after repair.")
    _has_findings = bool(ss.dtc_result or ss.test_results or ss.tech_notes.strip() or ss.fix_part.strip() or current_codes())
    if st.button("✍️ Write a plain-English summary for the customer", disabled=not _has_findings):
      with st.spinner("Writing the customer summary..."):
        _sum, _who = quick_ai(CUSTOMER_SUMMARY_PROMPT.format(
            vehicle=ss.vehicle_info or "the vehicle", complaint=ss.symptoms.strip() or "not given", codes=", ".join(current_codes()) or "none",
            tests=json.dumps(ss.test_results or {})[:2500], notes=ss.tech_notes.strip() or "none",
            fix=(ss.fix_part.strip() + (f" (proved by: {ss.fix_test.strip()})" if ss.fix_test.strip() else "")) or "not done yet",
            plan=(ss.dtc_result or {}).get("text", "")[:2500] or "none"), max_tokens=700)
      if _sum.startswith("⚠️"):
        st.error(_sum)
      else:
        ss.customer_summary = _sum.strip()
    st.text_area("Customer summary (edit it as you like — it goes at the top of the report):", key="customer_summary", height=130,
                 placeholder="Tap the button above, or type your own summary for the customer.")
    _rep_name = re.sub(r"\W+", "_", ss.vehicle_info or "vehicle")
    _report_html = build_report_html(notes)
    _bat = battery_slip_html() if any(re.search(r"charg|crank|battery|power", k, re.I) for k in (ss.test_results or {})) else ""
    _sc1, _sc2, _sc3, _sc4 = st.columns(4)
    with _sc1:
      st.download_button("🧾 Download report", data=_report_html.encode("utf-8"), mime="text/html",
                         file_name=f"report_{_rep_name}_{datetime.now():%Y%m%d}.html", use_container_width=True)
    with _sc2:
      if st.button("📧 Email it to the customer", use_container_width=True,
                   disabled=not (email_ready() and (ss.customer_email or "").strip())):
        with st.spinner("Sending the email..."):
          _err = send_report_email(ss.customer_email.strip(), f"Diagnostic report — {ss.vehicle_info or 'your vehicle'}",
                                   (ss.customer_summary or "").strip() or "Your diagnostic report is attached.",
                                   _report_html, f"report_{_rep_name}_{datetime.now():%Y%m%d}.html")
        if _err:
          st.error(f"Couldn't send it: {_err}")
        else:
          record_sent("email", ss.customer_email.strip(), "report")
          st.success(f"Report emailed to {ss.customer_email.strip()} ✓")
    with _sc3:
      if st.button("💬 Text the summary", use_container_width=True,
                   disabled=not (sms_ready() and (ss.customer_phone or "").strip() and (ss.customer_summary or "").strip())):
        _shop = secret("SHOP_NAME") or "the shop"
        with st.spinner("Sending the text..."):
          _err = send_sms(ss.customer_phone, f"{_shop} — {ss.vehicle_info or 'your vehicle'}:\n{ss.customer_summary.strip()}")
        if _err:
          st.error(f"Couldn't send it: {_err}")
        else:
          record_sent("text", ss.customer_phone.strip(), "summary")
          st.success("Summary texted ✓")
    with _sc4:
      if _bat:
        st.download_button("🔋 Battery/charging slip", data=_bat.encode("utf-8"), mime="text/html",
                           file_name=f"battery_{_rep_name}_{datetime.now():%Y%m%d}.html", use_container_width=True)
      else:
        st.caption("🔋 Run the Charging or Cranking guided test to get a battery slip here.")
    if not email_ready():
      st.caption("📧 To email reports: add SMTP_USER and SMTP_PASSWORD to Streamlit Secrets (for Gmail, make an "
                 "\"App password\" under Google Account → Security → 2-Step Verification, and use that, not your normal password).")
    elif not (ss.customer_email or "").strip():
      st.caption("📧 Add the customer's email on the VIN tab to enable emailing.")
    if not sms_ready():
      st.caption("💬 To text customers: make a free trial account at twilio.com, buy a texting number (~$1/mo), and add "
                 "TWILIO_SID, TWILIO_TOKEN and TWILIO_FROM (the number, like +16785551234) to Secrets.")
    _sent = [r.get("data") or {} for r in store_list("sent", 3, {"job": ss.get("job_id")})] if ss.get("job_id") else []
    if _sent:
      st.caption("Sent: " + " · ".join(f"{x.get('what')} by {x.get('how')} to {x.get('to')} ({x.get('at')})" for x in _sent))

    # ---------- 5. Confirmed fix ----------
  st.write("---")
  with st.expander("✅ 6 · Confirmed fix & follow-up — teaches the app", expanded=bool((ss.fix_part or "").strip())):
    st.caption("When the car is fixed, write down what actually fixed it and the test that proved it. Next time a car like this "
               "comes in, the AI sees your shop's real fixes first.")
    f1, f2 = st.columns(2)
    f1.text_input("What fixed it:", key="fix_part", placeholder="e.g. Replaced upstream O2 sensor (Bank 1 Sensor 1)")
    f2.text_input("Test that proved it:", key="fix_test", placeholder="e.g. O2 now switching 0.1–0.9 V, total trims back within ±5%")
    st.text_input("Extra notes (optional):", key="fix_notes", placeholder="e.g. Connector pin 3 was corroded too")
    if st.button("💾 Save confirmed fix", type="primary", disabled=not (ss.fix_part.strip() and ss.vehicle_info)):
      if save_fix():
        st.success("Saved. It's now part of your shop's history for this car and for others like it.")
      else:
        st.error("Couldn't save the fix — add the vehicle or customer first.")
    if not ss.vehicle_info:
      st.caption("Set the vehicle on the VIN tab first.")

    st.markdown("**📅 Follow up with this customer?**")
    _fu1, _fu2 = st.columns(2)
    _fu_opts = list(FOLLOW_UP_LABELS)
    _cur_fu = ss.follow_up_days if ss.follow_up_days in FOLLOW_UP_LABELS else 0
    _fu_pick = _fu1.selectbox("Call them back", _fu_opts, index=_fu_opts.index(_cur_fu),
                              format_func=lambda d: FOLLOW_UP_LABELS[d], key=f"fu_{ss.get('job_n', 0)}")
    ss.follow_up_days = _fu_pick
    _fu2.text_input("About what:", key="follow_up_note", placeholder="e.g. Rear brakes at 4mm — due soon")
    if _fu_pick:
      st.caption("It'll show under 📅 Callbacks due on the Log tab when the time comes (counted from the job's last update).")
# ========================================================
# --- TAB 5: VEHICLE & DTC LOG ---
# ========================================================
DRIVE_REVIEW_TASK = """You are an expert ASE master diagnostic technician. Review this recorded test drive so NOTHING IS MISSED.
- Explain every spoken alert: a real problem, or normal behavior (decel fuel cut, open loop, warm-up, a shift)?
- Evaluate fuel trims by condition (idle / cruise / load), misfires, charging, catalyst, transmission and torque converter
  (TCC slip, RPM flare or surging at steady speed), and every guided test result.
- Look through the samples yourself for problems the app's alerts did NOT catch.
- List anything that needs follow-up testing, with the specific test to do.

"""


def review_drive(rec: dict, status_label: str = "Reviewing the drive...") -> str:
  with st.status(status_label) as status:
    ans, research, draft, ds_draft = team_answer(DRIVE_REVIEW_TASK + drive_text(rec), rec.get("vehicle") or ss.vehicle_info or "vehicle",
                                                 ss.active_dtc, ss.symptoms.strip(), False, status)
    status.update(label="Done", state="complete")
  ss.setdefault("drive_reviews", {})[rec["id"]] = ans + f"\n\n_{team_names(draft, ds_draft, research)}_"
  return ans


# A drive that just finished gets reviewed by the whole team automatically (retried on the next run if it gets interrupted)
if ss.get("drive_review_pending"):
  with guard("Automatic test drive review"):
    _rec = load_drives().get(ss.drive_review_pending)
    if _rec and _rec["id"] not in (ss.get("drive_reviews") or {}):
      review_drive(_rec, "🤖 AI team is reviewing the test drive you just finished...")
      ss.ble_ai = {"id": "review-" + _rec["id"], "text": ss.drive_reviews[_rec["id"]], "label": "[AI team test drive review]"}
      ss.drive_review_pending = None
      st.rerun()
    ss.drive_review_pending = None


with tab5, guard("Log tab"):
  st.subheader("📋 Scan history")
  st.caption("Logged automatically when the scanner syncs or you run a diagnostic tree. " +
             ("Saved permanently." if store_on() else "⚠️ Permanent storage isn't set up yet, so this resets when the app "
                                                       "restarts — export it regularly."))

  history = load_log()
  if history:
    q = st.text_input("🔎 Search the log (name, phone, VIN, vehicle or code):", key="log_search")
    shown_rows = [r for r in history if q.strip().lower() in " ".join(str(v) for v in r.values()).lower()] if q.strip() else history
    st.dataframe(shown_rows, use_container_width=True, hide_index=True)
    col_csv, col_del = st.columns(2)
    with col_csv:
      st.download_button("📥 Export Log to CSV", data=log_csv(history), file_name="diagnostic_scan_log.csv", mime="text/csv")
    with col_del:
      confirm = st.checkbox("Yes, delete all log entries")
      if st.button("🗑️ Clear Log History", disabled=not confirm):
        store_delete("log")
        queue_update(toast="Log cleared")
  else:
    st.info("No vehicles or DTCs logged yet. Connect the scanner (📊 Scanner tab) or run a diagnostic tree (🔧 Diagnose tab) to start logging.")

  # ---------- 📅 Callbacks due ----------
  st.write("---")
  st.subheader("📅 Callbacks due")
  _today = datetime.now()
  def _jdate(d):
    for k in ("updated", "created"):
      try:
        return datetime.strptime(str(d.get(k, "")), "%Y-%m-%d %I:%M %p")
      except ValueError:
        continue
    return None
  _due = []
  for _r in store_list("job", 300, {"status": "closed"}):
    _d = _r.get("data") or {}
    _days, _dt = _d.get("follow_up_days") or 0, _jdate(_d)
    if not _days or _d.get("follow_up_done") or not _dt:
      continue
    _when = _dt + __import__("datetime").timedelta(days=int(_days))
    if _when <= _today + __import__("datetime").timedelta(days=7):
      _due.append((_when, _r["id"], _d))
  if not _due:
    st.caption("Nothing due. Set a follow-up when you close a job (Diagnose tab → section 6) and it shows up here on time.")
  else:
    for _when, _jid, _d in sorted(_due):
      _cb1, _cb2 = st.columns([5, 1])
      _late = "🔴 overdue" if _when < _today else "🟡 this week"
      _cb1.markdown(f"{_late} · **{_d.get('customer_name') or 'No name'}** ({_d.get('customer_phone') or 'no phone'}) · "
                    f"{_d.get('vehicle_info') or 'vehicle'}  \n<small>Due {_when:%b %d}: "
                    f"{_d.get('follow_up_note') or FOLLOW_UP_LABELS.get(_d.get('follow_up_days'), '')}</small>", unsafe_allow_html=True)
      if _cb2.button("✔️ Called", key=f"fu_done_{_jid}", use_container_width=True):
        _rec = store_get("job", _jid) or {}
        _rec["follow_up_done"] = True
        store_put("job", _jid, _rec)
        st.rerun()

  # ---------- 📈 Shop summary ----------
  st.write("---")
  with st.expander("📈 Shop summary — cars, top codes, top fixes and comebacks"):
    _all_jobs = [dict(_r.get("data") or {}, _id=_r["id"]) for _r in store_list("job", 500)]
    _all_fixes = [_r.get("data") or {} for _r in store_list("fix", 500)]
    _months = sorted({_jdate(j).strftime("%Y-%m") for j in _all_jobs if _jdate(j)}, reverse=True)
    if not _months:
      st.caption("No jobs recorded yet.")
    else:
      _mo = st.selectbox("Month", _months, format_func=lambda m: datetime.strptime(m, "%Y-%m").strftime("%B %Y"))
      _mo_jobs = [j for j in _all_jobs if _jdate(j) and _jdate(j).strftime("%Y-%m") == _mo]
      _mo_fixes = [f for f in _all_fixes if str(f.get("date", "")).startswith(_mo)]
      _m1, _m2, _m3 = st.columns(3)
      _m1.metric("Cars worked", len(_mo_jobs))
      _m2.metric("Confirmed fixes", len(_mo_fixes))
      _code_count = {}
      for _j in _mo_jobs:
        for _c in re.split(r"[,\s]+", str(_j.get("codes") or "")):
          if DTC_RE.fullmatch(_c):
            _code_count[_c] = _code_count.get(_c, 0) + 1
      # comebacks across ALL jobs: same VIN, same code, two different jobs within 60 days
      _byvin = {}
      for _j in _all_jobs:
        if _j.get("active_vin") and _jdate(_j):
          _byvin.setdefault(_j["active_vin"], []).append(_j)
      _comebacks = []
      for _vin, _js in _byvin.items():
        _js.sort(key=_jdate)
        for _i in range(1, len(_js)):
          _gap = (_jdate(_js[_i]) - _jdate(_js[_i - 1])).days
          _shared = set(re.split(r"[,\s]+", str(_js[_i].get("codes") or ""))) &                     set(re.split(r"[,\s]+", str(_js[_i - 1].get("codes") or ""))) - {""}
          if 0 < _gap <= 60 and _shared:
            _comebacks.append({"vehicle": _js[_i].get("vehicle_info", ""), "customer": _js[_i].get("customer_name", ""),
                               "code(s)": ", ".join(sorted(_shared)), "days apart": _gap,
                               "first": _jdate(_js[_i - 1]).strftime("%b %d"), "back": _jdate(_js[_i]).strftime("%b %d")})
      _m3.metric("Comebacks (60 days)", len(_comebacks))
      if _code_count:
        st.markdown("**Most common codes this month**")
        st.dataframe([{"Code": c, "Cars": n} for c, n in sorted(_code_count.items(), key=lambda x: -x[1])[:10]],
                     use_container_width=True, hide_index=True)
      if _mo_fixes:
        st.markdown("**Fixes this month**")
        st.dataframe([{"Vehicle": f.get("vehicle", ""), "Codes": ", ".join(f.get("codes") or []), "Fix": f.get("fix", ""),
                       "Tech": f.get("tech", "")} for f in _mo_fixes], use_container_width=True, hide_index=True)
      if _comebacks:
        st.markdown("**⚠️ Comebacks** — same car, same code, within 60 days (all time)")
        st.dataframe(_comebacks, use_container_width=True, hide_index=True)

  # ---------- 🚗 Test drive review ----------
  st.write("---")
  st.subheader("🚗 Test drive review")
  drives = load_drives()
  if not drives:
    st.caption("Every test drive is saved automatically when you tap Stop Test Drive (and on your phone, even if the page "
               "reloads mid-drive). Older drives on your phone: 📊 Scanner tab → 🎯 Guided Tests → 📁 Saved test drives → Send to app.")
  else:
    ids = list(drives)
    if ss.get("drive_pick") not in ids:
      ss.drive_pick = ids[0]
    pick = st.selectbox("Drive", ids, key="drive_pick",
                        format_func=lambda i: f"{drives[i].get('started')} · {drives[i].get('vehicle') or 'vehicle'} · "
                                              f"{drives[i].get('minutes')} min · {len(drives[i].get('alerts') or [])} alert(s)")
    rec = drives[pick]
    alerts = rec.get("alerts") or []
    if alerts:
      st.markdown("**Spoken alerts** (with the readings at that moment)")
      st.dataframe([{"time": a.get("at"), "alert": a.get("text"), "fuel system": (a.get("snap") or {}).get("fss"),
                     "decel": "yes" if (a.get("snap") or {}).get("decel") else "",
                     **{k: (a.get("snap") or {}).get(k) for k in ("rpm", "spd", "load", "stft1", "ltft1", "o2b1s1")}} for a in alerts],
                   use_container_width=True)
    if rec.get("report"):
      with st.expander("Drive report"):
        st.text(rec["report"])
    rows = drive_rows(rec)
    if rows:
      st.line_chart([{"seconds": r["sec"], "STFT B1": r.get("stft1"), "LTFT B1": r.get("ltft1")} for r in rows], x="seconds",
                    height=220)
    txt = drive_text(rec)
    c1, c2 = st.columns(2)
    with c1:
      if st.button("🧠 Have the AI team review this drive" + (" again" if pick in (ss.get("drive_reviews") or {}) else "")):
        review_drive(rec)
    with c2:
      csv_rows = ["seconds," + ",".join(rec.get("keys") or []) + ",fuel_system,decel"] + [
          ",".join("" if r.get(k) is None else str(r.get(k)) for k in ["sec", *(rec.get("keys") or []), "fuel_system"]) + ("," + ("yes" if r["decel"] else ""))
          for r in rows]
      st.download_button("⬇️ Download drive data (CSV)", data="\n".join(csv_rows), file_name=f"{pick}.csv", mime="text/csv")
    if pick in (ss.get("drive_reviews") or {}):
      st.markdown("##### 🤖 AI team review of this drive")
      st.markdown(ss.drive_reviews[pick])
    st.markdown("**Copy this to Claude** — tap the copy icon in the top-right corner of the box:")
    st.code(txt[:30000], language=None)

  # ---------- 🐞 Problem log ----------
  st.write("---")
  st.subheader("🐞 Problem log")
  st.caption("Crashes, AI/API failures and Bluetooth scanner errors are saved here automatically. If something goes wrong, "
             "describe it below, tap the copy icon on the report and paste it to Claude." +
             ("" if store_on() else " (Until permanent storage is set up, this log resets when the app restarts, so copy it soon.)"))
  problems = load_problems()
  if problems:
    st.dataframe([{k: p.get(k, "") for k in ("time", "kind", "where", "message")} for p in problems[:50]], use_container_width=True)
  else:
    st.success("No problems logged.")
  what = st.text_area("What went wrong? (what you tapped, what you expected, what happened)", key="problem_note", height=80)
  dbg = ss.get("scanner_debug") or {}
  recent = problems[:12]
  report = "\n".join([
      "TEST DON'T GUESS — PROBLEM REPORT",
      f"App version: {APP_VERSION} · {datetime.now():%Y-%m-%d %I:%M %p}",
      f"Vehicle: {ss.vehicle_info or 'none'} · VIN {ss.active_vin or 'none'} · OEM profile {make_profile()}",
      f"Codes in Diagnose tab: {ss.active_dtc or 'none'}",
      f"What happened: {what.strip() or '(not described)'}",
      "",
      f"RECENT LOGGED PROBLEMS ({len(recent)}):",
      *[f"- [{p.get('time')}] {p.get('kind')} in {p.get('where')}: {p.get('message')}"
        + (f"\n    {p.get('details', '').strip()[-1500:]}" if p.get("details") else "") for p in recent],
      "",
      "SCANNER STATE: " + (json.dumps({k: v for k, v in dbg.items() if k != "trace"}) if dbg else "not sent (tap 🐞 Send debug info on the 📊 Scanner tab)"),
      *(["LAST ADAPTER EXCHANGES:", *dbg.get("trace", [])[-60:]] if dbg.get("trace") else []),
  ])
  st.markdown("**Report to send Claude** — tap the copy icon in the top-right corner of the box:")
  st.code(report, language=None)
  c1, c2 = st.columns(2)
  with c1:
    st.download_button("⬇️ Download full problem log", data="\n".join(json.dumps(p) for p in problems[::-1]) or "empty",
                       file_name=f"problem_log_{datetime.now():%Y%m%d_%H%M}.txt", mime="text/plain")
  with c2:
    if problems and st.button("🧹 Clear problem log"):
      try:
        os.remove(PROBLEM_LOG)
      except OSError:
        pass
      store_delete("problem")
      queue_update(toast="Problem log cleared")

  # ---------- 💾 Backup ----------
  st.write("---")
  st.subheader("💾 Backup")
  st.caption("Downloads everything — jobs, fixes, scan log, test drives, photos, waveforms — as one file. "
             "Keep a copy somewhere safe now and then.")
  if st.button("📦 Prepare backup file"):
    with st.spinner("Gathering everything..."):
      _bk = {"app_version": APP_VERSION, "made": datetime.now().isoformat(),
             **{k: store_list(k, 1000) for k in ("job", "fix", "log", "drive", "jobphoto", "wave", "sent", "problem")}}
      ss._backup = json.dumps(_bk)
      ss._backup_counts = " · ".join(f"{k}: {len(_bk.get(k) or [])}" for k in ("job", "fix", "log", "drive", "jobphoto", "wave"))
    st.toast("Backup ready — tap Download")
  if ss.get("_backup"):
    st.download_button("⬇️ Download backup", data=ss._backup, mime="application/json",
                       file_name=f"tdg_backup_{datetime.now():%Y%m%d}.json")
    st.caption(f"Backup size: {len(ss._backup) / 1e6:.1f} MB · " + ss.get("_backup_counts", ""))


# ========================================================
# --- AUTOSAVE: the current car is saved after every change ---
# ========================================================
with guard("Autosave"):
  autosave_job()
