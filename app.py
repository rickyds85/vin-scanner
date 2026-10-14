import base64
import csv
from datetime import datetime
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
APP_VERSION = "2026-10-12"
PROBLEM_LOG = "problem_log.jsonl"
LOG_COLUMNS = ["Timestamp", "Customer", "Phone", "VIN", "Vehicle", "Fault Code (DTC)"]
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
  return entry


def load_problems(limit: int = 200) -> list[dict]:
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


def claude(prompt: str, *, max_tokens: int = 4000, timeout: int = 120) -> str:
  key = secret("ANTHROPIC_API_KEY")
  if not key:
    raise AIError("ANTHROPIC_API_KEY is missing from Streamlit Secrets.")
  try:
    res = http().post(CLAUDE_URL, timeout=timeout, json={
        "model": secret("CLAUDE_MODEL") or CLAUDE_DEFAULT_MODEL, "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}]},
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
  except requests.RequestException as e:
    raise AIError(f"Claude connection error: {e}") from e
  if res.status_code != 200:
    raise AIError(f"Claude API error ({res.status_code}): {res.text[:300]}")
  try:
    text = "".join(b.get("text", "") for b in res.json().get("content", []) if b.get("type") == "text")
  except ValueError as e:
    raise AIError("Claude returned an unreadable answer.") from e
  if not text.strip():
    raise AIError("Claude returned an empty answer.")
  return text


# --- DeepSeek (second independent draft) ---
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_DEFAULT_MODEL = "deepseek-flash"   # change with DEEPSEEK_MODEL in Secrets (e.g. deepseek-v4-pro)


def has_deepseek() -> bool:
  return bool(secret("DEEPSEEK_API_KEY"))


def deepseek_label() -> str:
  m = secret("DEEPSEEK_MODEL") or DEEPSEEK_DEFAULT_MODEL
  return m.replace("deepseek-", "DeepSeek ").replace("-", " ").replace("v4", "V4").title().replace("Deepseek", "DeepSeek").replace("V4 ", "V4 ")


def _deepseek_raw(key: str, model: str, session: requests.Session, prompt: str, max_tokens: int, timeout: int) -> str:
  """No Streamlit calls in here, so it is safe to run in a background thread."""
  try:
    res = session.post(DEEPSEEK_URL, timeout=timeout, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                       json={"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]})
  except requests.RequestException as e:
    raise RuntimeError(f"DeepSeek connection error: {e}") from e
  if res.status_code != 200:
    raise RuntimeError(f"DeepSeek API error ({res.status_code}, {model}): {res.text[:300]}")
  try:
    text = res.json()["choices"][0]["message"].get("content") or ""
  except (KeyError, IndexError, ValueError) as e:
    raise RuntimeError("DeepSeek returned an unreadable answer.") from e
  if not text.strip():
    raise RuntimeError("DeepSeek returned an empty answer.")
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
- Order the tests from fastest/cheapest and most likely to least, so the tech doesn't throw parts at it.
- Never invent TSB numbers or specs; only use ones from the research or that you are sure of.
- End with "### Team Notes": 2-5 bullets on what you changed, and where Gemini, DeepSeek and the research disagreed and who was right."""


def team_answer(prompt: str, vehicle: str, codes: str, symptoms: str, use_web: bool, status=None) -> tuple[str, str, str, str]:
  """Perplexity researches -> Gemini and DeepSeek draft at the same time -> Claude reviews both and writes the final plan.
  Steps are skipped if their key isn't set. Returns (final answer, research, gemini draft, deepseek draft)."""
  research, draft, ds_draft, gem_err = "", "", "", ""
  if use_web:
    if status:
      status.update(label="🌐 Perplexity is researching TSBs, recalls and known fixes...")
    research = web_research(vehicle, codes, symptoms)
  full = prompt + (TEAM_RULES.format(research=research[:6000]) if research else "")
  writers = f"✨ {gemini_label()}" + (f" and 🐋 {deepseek_label()} are" if has_deepseek() else " is")
  if status:
    status.update(label=f"{writers} drafting the plan" + (" with the web research..." if research else "..."))
  pool, ds_job = None, None
  if has_deepseek():   # DeepSeek runs in the background while Gemini works, so it adds no wait time
    pool = ThreadPoolExecutor(max_workers=1)
    ds_job = pool.submit(_deepseek_raw, secret("DEEPSEEK_API_KEY"), secret("DEEPSEEK_MODEL") or DEEPSEEK_DEFAULT_MODEL, http(), full, 4000, 120)
  try:
    draft = gemini([{"text": full}])
  except AIError as e:
    gem_err = str(e)
  if ds_job:
    try:
      ds_draft = ds_job.result(timeout=150)
    except Exception as e:
      log_problem("ai", "DeepSeek draft", str(e))
      ds_draft = ""
    pool.shutdown(wait=False)
  if has_claude():
    if status:
      status.update(label=f"🧠 {claude_label()} is reviewing the drafts and finalizing the plan...")
    try:
      final = claude(REVIEW_PROMPT.format(task=prompt, research=research[:6000] or "none",
                                          draft=draft or "(Gemini draft unavailable)",
                                          ds_draft=ds_draft or "(DeepSeek draft unavailable)"))
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
with tab1, guard("VIN & Customer tab"):
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
  st.markdown("#### 📸 VIN from a photo")
  st.caption("Tip: use **Take or upload photo** — on a phone it opens the full-resolution camera, which reads far better than "
             "the small in-app camera. Get close, fill the frame with the VIN, avoid glare. Works with the door sticker, "
             "windshield plate, registration/insurance card or a scan-tool screen. (Connecting the scanner reads the VIN "
             "straight from the car and needs no photo.)")
  col_up, col_cam = st.columns(2)
  with col_up:
    uploaded = st.file_uploader("📷 Take or upload photo of the VIN", type=["png", "jpg", "jpeg", "webp"], key="vin_upload")
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
async function readOem(cmd) {
  await setAddr(cmd.hdr, cmd.rax);
  const msgs = messages(await sendCmd(cmd.req, 500));
  if (msgs.some((m) => m.startsWith("7F"))) return { bytes: null, replied: true };   // module there, request refused
  const pre = respCode(cmd.req.slice(0, 2)) + cmd.req.slice(2);
  for (const m of msgs) if (m.startsWith(pre)) return { bytes: bytesOf(m.slice(pre.length)), replied: true };
  return { bytes: null, replied: msgs.length > 0 };
}
async function pollEnhanced() {
  const fresh = oemCmds.filter((c) => c.state === "new").slice(0, 6);      // discovery: probe a few new requests
  const live = oemCmds.filter((c) => c.state === "live");
  const graphed = live.filter((c) => c.sigs.some((g) => g.tile && graphSel.includes(g.tile)));   // graphed = every pass
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
  if (msgs.some((m) => /^7F..78/.test(m))) msgs = messages(await sendCmd(req, 2000));   // "busy, wait" -> ask again
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
      ? m.codes.map((c) => `<span class="chip" title="${c.status}" style="color:var(--${color[c.status]});border-color:var(--${color[c.status]})">${esc(c.code)}<span style="font-weight:400;font-size:.7rem"> ${c.status}</span></span>`).join("")
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
    driveChecks();
    testsTick();
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

function driveChecks() {
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
  sendValue({ type: "ai", id: aiPendingId, mode, at: new Date().toLocaleTimeString(), pids: snapshot(), dtcs, readiness: readinessSummary, mode6: mode6Summary, tests: T.results || {} });
  const id = aiPendingId;
  setTimeout(() => { if (aiPendingId === id) { aiPendingId = null; if (mode === "full") $("aiBox").textContent = "AI request timed out. Try again."; logEvent("ai", "AI check (" + mode + ")", "No answer from the app within 90 s"); } }, 90000);
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
const BTN_IDS = ["pauseBtn", "driveBtn", "readBtn", "clearBtn", "aiBtn", "syncBtn", "modBtn"];
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
    pids: snapshot(), readiness: readinessSummary, mode6: mode6Summary, at: new Date().toLocaleTimeString() });
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
  if (m) { const [, B, C, D] = bytesOf(m.slice(4, 12)); r41 = { B, C, D, at: new Date().toLocaleTimeString() }; }
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
    T.crank.result = !crankT ? { error: "No cranking detected (voltage never dipped). Arm the test, then crank within 20 s." } : {
      base, minV: isFinite(minV) ? minV : null, crankTime: startT ? startT - crankT : null, started: !!startT,
      crankRpm: crRpm.length ? avg(crRpm) : null, afterV: after.length ? avg(after) : null,
    };
    T.crank.phase = "done";
  });
  const R = T.crank.result;
  if (R && !R.error) reportTest("Cranking / starting", { resting_V: R.base && +R.base.toFixed(2), min_crank_V: R.minV && +R.minV.toFixed(2), crank_s: R.crankTime && +R.crankTime.toFixed(1),
    crank_rpm: R.crankRpm && Math.round(R.crankRpm), started: R.started, verdict: crankVerdict(R).text.replace(/<[^>]+>/g, "") });
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
  return `<div class="tsteps">Calculates the overall gear ratio (RPM ÷ speed) while you drive, finds each gear, and looks for slipping, flares and torque-converter slip. Accelerate through all gears a few times and cruise at highway speed. Records automatically on a test drive. <b>Beta.</b></div>
    ${X.on ? btn("trans-stop", "■ Stop") : btn("trans-start", "● Start recording")}${btn("trans-reset", "Reset", 1)} <span class="note">${X.pts.length} samples</span>
    <canvas class="tplot" id="transPlot"></canvas>
    <div class="note">RPM per mph over time. Flat steps = gears.</div>
    ${a ? `<div class="verdict">Gears found: ${a.gears.length ? a.gears.map((g, i) => `<b>${i + 1}</b>: ${g.ratio.toFixed(1)} rpm/mph`).join(" · ") : "not enough steady driving yet"}<br>
      ${a.flags.length ? a.flags.join("<br>") : a.gears.length >= 3 ? "<span class='grade-g'>No slip or converter problems detected.</span>" : ""}</div>` : ""}`;
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
function extraTicks() { vacTick(); warmTick(); transTick(); }
function extraDriveStart() {
  Object.values(misLive).forEach((L) => (L.tot = 0)); misEvents = [];
  T.trans.pts = [];
  if ((num.ect ?? 999) < 150) T.warm = { on: true, pts: [], t0: nowS(), result: null };
}
function extraDriveStop() { if (T.warm.on) T.warm.on = false; }
function extraDriveChips(chip) {
  const m = misAnalyze(), a = transAnalyze();
  return chip(true, m.all ? `${m.all} misfire(s)` : "No misfires") + chip(a && a.gears.length >= 3, `Gears found (${a ? a.gears.length : 0})`) +
    (T.warm.on ? chip(!!T.warm.result, "Warm-up") : "") + (r41 ? chip(readinessRows(r41.B, r41.C, r41.D, true).every((r) => r.done), "Monitors this drive") : "");
}
function extraReportRows(add) {
  const m = misAnalyze();
  add("🔥 Misfires", m.all ? `${m.all} new${m.worst ? " · mostly cyl " + m.worst[0] : ""}` : "none", m.all ? (m.all > 20 ? "r" : "y") : "g", m.all ? m.text.replace(/<[^>]+>/g, "").slice(0, 140) + "…" : "");
  const a = transAnalyze();
  if (a) add("⚙️ Transmission", `${a.gears.length} gears found`, a.flags.length ? "y" : a.gears.length >= 3 ? "g" : null, a.flags.length ? a.flags.map((f) => f.replace(/<[^>]+>/g, "")).join(" ").slice(0, 160) : "");
  if (T.warm.result) add("🌡️ Warm-up", T.warm.result.g === "g" ? "normal" : "check", T.warm.result.g, T.warm.result.text.replace(/<[^>]+>/g, "").slice(0, 160));
  if (r41) { const rows = readinessRows(r41.B, r41.C, r41.D, true), left = rows.filter((r) => !r.done); add("📋 Monitors (this drive)", `${rows.length - left.length}/${rows.length} complete`, left.length ? "y" : "g", left.length ? "still running: " + left.map((r) => r.n).join(", ") : ""); }
  if (misAnalyze().all) reportTest("Misfire monitor", { total_new: m.all, worst_cylinder: m.worst && m.worst[0], verdict: m.text.replace(/<[^>]+>/g, "") }, true);
  if (a && a.gears.length) reportTest("Transmission ratio analysis", { gears: a.gears.map((g) => +g.ratio.toFixed(1)), flags: a.flags.map((f) => f.replace(/<[^>]+>/g, "")), grade: a.flags.length ? "MARGINAL" : "GOOD" }, true);
}


// ===================== Test drive recorder (auto-saved on this device + sent to the app) =====================
const DRIVE_KEYS = ["rpm", "spd", "load", "tps", "stft1", "ltft1", "stft2", "ltft2", "maf", "map", "ect", "iat", "o2b1s1", "o2b1s2", "timing", "volt", "frp"];
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


def _fmt_dtcs(d: dict) -> str:
  out = (f"Engine/emissions (OBD-II) stored: {', '.join(d.get('stored') or []) or 'none'} | pending: "
         f"{', '.join(d.get('pending') or []) or 'none'} | permanent: {', '.join(d.get('permanent') or []) or 'none'}")
  mods = [f"{m.get('name')} [{m.get('addr')}]: " + ", ".join(f"{c.get('code')} ({c.get('status')})" for c in m.get("codes", []))
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
    ss.scan_data = {k: ev.get(k) for k in ("pids", "readiness", "mode6", "at")}
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
      ss.setdefault("drives", {})[rec["id"]] = rec
      try:
        os.makedirs("drives", exist_ok=True)
        with open(os.path.join("drives", re.sub(r"[^\w\-]", "", rec["id"]) + ".json"), "w", encoding="utf-8") as f:
          json.dump(rec, f)
      except OSError:
        pass
      ss.drive_pick = rec["id"]
      ss._toast = "Test drive saved — see 📋 Log → 🚗 Test drive review"

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

MODE $06 RESULTS (value [min..max]):
{ev.get('mode6') or 'Not read'}

GUIDED TEST RESULTS (fuel trim / VE / catalyst / charging / power & braking, if run):
{json.dumps(ev.get('tests') or ss.test_results or {}) or 'none'}

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


with tab2, guard("Live Telemetry tab"):
  st.subheader("📊 Live Telemetry, OEM Enhanced PIDs & Monitors")
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

# ========================================================
# --- TAB 3: DIAGNOSE (STRATEGY + SCOPE LAB + COPILOT) ---
# ========================================================
def scan_context() -> str:
  """Everything the scanner captured, for the AI prompts."""
  tests = ("\nGuided test results: " + json.dumps(ss.test_results)) if ss.test_results else ""
  if not ss.ble_dtcs and not ss.scan_data:
    return "No scanner data (codes entered by hand)." + tests
  sd = ss.scan_data or {}
  pids = json.dumps(sd.get("pids") or {}, indent=0) if sd.get("pids") else "not captured"
  return (f"Scanner codes: {_fmt_dtcs(ss.ble_dtcs)}\n"
          f"I/M readiness: {sd.get('readiness') or 'not read'}\n"
          f"Mode $06 results: {sd.get('mode6') or 'not read'}\n"
          f"Live data snapshot at sync ({sd.get('at') or '?'}): {pids}" + tests)


with tab3, guard("Diagnose tab"):
  st.subheader("🔧 Diagnose: Strategy, Scope Lab & Copilot")
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
    st.caption("Connect the scanner on the Live Telemetry tab — the codes it reads show up here automatically.")
  st.text_input("Add codes by hand (optional):", key="manual_dtc", placeholder="e.g. P0171, P0174")
  st.text_area("Symptoms / customer complaint (optional — works with or without codes):", key="symptoms", height=80,
               placeholder="e.g. Rough idle when cold, stumbles on hard acceleration, no check engine light")

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
"""
    with st.status("Working on it...", expanded=False) as status:
      text, research, draft, ds_draft = team_answer(sym_prompt, vehicle, "", symptoms, use_web, status)
      status.update(label="Done", state="complete")
    ss.dtc_result = {"title": f"Symptoms · {vehicle}", "text": text, "research": research, "draft": draft, "ds_draft": ds_draft}

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
    with st.status("Working on it...", expanded=False) as status:
      text, research, draft, ds_draft = team_answer(dtc_prompt, vehicle, code_str, symptoms, use_web, status)
      status.update(label="Done", state="complete")
    ss.dtc_result = {"title": f"{code_str} · {vehicle}", "text": text, "research": research, "draft": draft, "ds_draft": ds_draft}

  if ss.dtc_result:  # stays on screen while you use other tabs
    team = " + ".join(x for x in ["🌐 Perplexity" if ss.dtc_result.get("research") else "", "✨ " + gemini_label(),
                                   "🐋 " + deepseek_label() if ss.dtc_result.get("ds_draft") else "",
                                   "🧠 " + claude_label() if ss.dtc_result.get("draft") else ""] if x)
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

Web research already found for this job (TSBs / known fixes, if any):
{(ss.dtc_result or {}).get("research", "")[:2500] or 'none'}

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

Earlier web research for this job (if any): {(ss.dtc_result or {}).get("research", "")[:2500] or 'none'}

Respond directly, practically, and concisely to the latest question. Focus on physical shop tests, circuit checks, and logical isolation.
"""
    with st.chat_message("assistant"):
      with st.status("Working on it...", expanded=False) as status:
        research = ""
        if ss.get("use_web", False) and secret("PERPLEXITY_API_KEY"):
          status.update(label="🌐 Perplexity is searching for this question...")
          research = web_research(ss.vehicle_info or "General vehicle", code_str, ss.symptoms.strip(), question=user_question)
        q = chat_prompt + (TEAM_RULES.format(research=research[:4000]) if research else "")
        reply = None
        if has_claude():   # Claude answers chat when available (Gemini is the backup)
          status.update(label=f"🧠 {claude_label()} is answering...")
          try:
            reply = claude(q, max_tokens=2000)
          except AIError:
            reply = None
        if reply is None and has_deepseek():   # DeepSeek is the next backup
          status.update(label=f"🐋 {deepseek_label()} is answering...")
          try:
            reply = deepseek(q, max_tokens=2000)
          except AIError:
            reply = None
        if reply is None:
          status.update(label=f"✨ {gemini_label()} is answering...")
          try:
            reply = gemini([{"text": q}])
          except AIError as e:
            reply = f"⚠️ {e}" + (f"\n\n**Web research:**\n{research}" if research else "")
        status.update(label="Done", state="complete")
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
  try:
    for fn in os.listdir("drives"):
      if fn.endswith(".json") and fn[:-5] not in drives:
        with open(os.path.join("drives", fn), encoding="utf-8") as f:
          d = json.load(f)
          drives[d.get("id", fn[:-5])] = d
  except (OSError, ValueError):
    pass
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
      *[f"- {a.get('at')} (+{a.get('t')}s): {a.get('text')} | {json.dumps(a.get('snap'))}" for a in alerts],
      "", f"MISFIRE EVENTS: {json.dumps((rec.get('misfires') or [])[-30:])}",
      "", f"TIMELINE every {step} s (fuel_system CL=closed loop; decel=Y means fuel cut/closed throttle):",
      *lines,
  ])


# ========================================================
# --- CUSTOMER / SHOP REPORT (shown at the bottom of the Diagnose tab) ---
# ========================================================
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
<tr><th>Engine</th><td>{e(eng)}</td><th>Complaint</th><td>{e(ss.symptoms or '')}</td></tr></table>
<h2>Trouble codes</h2><table><tr><th>Module</th><th>Code</th><th>Status</th></tr>{rows_codes}</table>
{ff_html}
<h2>Test results</h2><table><tr><th>Test</th><th>Result</th><th>Details</th></tr>{rows_tests}</table>
{"<h2>Technician notes & recommendation</h2><pre>" + e(notes) + "</pre>" if notes.strip() else ""}
{"<h2>Diagnostic plan</h2><pre>" + e(plan) + "</pre>" if plan else ""}
<p class="muted">Results from on-board diagnostic data and road/bay tests. Further pinpoint testing may be required before parts replacement.</p>
</body></html>"""


with tab3, guard("Diagnose tab"):
  st.write("---")
  st.markdown("#### 4 · Customer / shop report")
  st.caption("One page with the vehicle, all codes, freeze frame, every test result (green / yellow / red) and the plan. "
             "Open it on your phone and use Print → Save as PDF, or text it to the customer.")
  notes = st.text_area("Technician notes / recommendation (goes on the report):", key="tech_notes", height=80,
                       placeholder="e.g. Recommend replacing cylinder 3 ignition coil and spark plugs. Fuel trims normal after repair.")
  _rep_name = re.sub(r"\W+", "_", ss.vehicle_info or "vehicle")
  st.download_button("🧾 Download report", data=build_report_html(notes).encode("utf-8"), mime="text/html",
                     file_name=f"report_{_rep_name}_{datetime.now():%Y%m%d}.html")

# ========================================================
# --- TAB 5: VEHICLE & DTC LOG ---
# ========================================================
with tab5, guard("Log tab"):
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

  # ---------- 🚗 Test drive review ----------
  st.write("---")
  st.subheader("🚗 Test drive review")
  drives = load_drives()
  if not drives:
    st.caption("Every test drive is saved automatically when you tap Stop Test Drive (and on your phone, even if the page "
               "reloads mid-drive). Older drives on your phone: Live Telemetry tab → 🎯 Guided Tests → 📁 Saved test drives → Send to app.")
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
      if st.button("🧠 Have the AI team review this drive"):
        prompt = ("You are an expert ASE master diagnostic technician. Review this recorded test drive. Explain each spoken "
                  "alert (was it a real problem or normal behavior such as decel fuel cut, open loop, or warm-up?), evaluate "
                  "fuel trims by condition, and list anything that needs follow-up testing with the specific test to do.\n\n" + txt)
        with st.status("Reviewing the drive...") as status:
          ans, research, draft, ds_draft = team_answer(prompt, rec.get("vehicle") or ss.vehicle_info or "vehicle", ss.active_dtc, "", False, status)
          status.update(label="Done", state="complete")
        ss.drive_review = {"id": pick, "text": ans}
    with c2:
      csv_rows = ["seconds," + ",".join(rec.get("keys") or []) + ",fuel_system,decel"] + [
          ",".join("" if r.get(k) is None else str(r.get(k)) for k in ["sec", *(rec.get("keys") or []), "fuel_system"]) + ("," + ("yes" if r["decel"] else ""))
          for r in rows]
      st.download_button("⬇️ Download drive data (CSV)", data="\n".join(csv_rows), file_name=f"{pick}.csv", mime="text/csv")
    if (ss.get("drive_review") or {}).get("id") == pick:
      st.markdown(ss.drive_review["text"])
    st.markdown("**Copy this to Claude** — tap the copy icon in the top-right corner of the box:")
    st.code(txt[:30000], language=None)

  # ---------- 🐞 Problem log ----------
  st.write("---")
  st.subheader("🐞 Problem log")
  st.caption("Crashes, AI/API failures and Bluetooth scanner errors are saved here automatically. If something goes wrong, "
             "describe it below, tap the copy icon on the report and paste it to Claude. (On Streamlit Cloud this log "
             "resets when the app restarts, so copy it soon after the problem.)")
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
      "SCANNER STATE: " + (json.dumps({k: v for k, v in dbg.items() if k != "trace"}) if dbg else "not sent (tap 🐞 Send debug info on the Live Telemetry tab)"),
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
      queue_update(toast="Problem log cleared")
