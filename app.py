import base64
import copy
import csv
from datetime import datetime, timezone
import hashlib
import hmac
import html as html_lib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageEnhance, ImageOps
import numpy as np
import requests
import streamlit as st
import streamlit.components.v1 as components
import zxingcpp

st.set_page_config(page_title="Test Don't Guess", page_icon="⚡", layout="wide")

APP_VERSION = "2026-11-20"
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
    "NEW: 📖 Knowledge tab — photograph book pages and the app keeps only the testing facts as short notes (pages are "
    "never saved); the AI team applies the notes that fit each car on every diagnosis",
    "SECURITY: login now expires after 30 days and lives in the browser, not the address bar — a shared job link no "
    "longer logs someone in. Log out button under ⚙️ Setup. (Everyone logs in once after this update.)",
    "FIX: crank wheels with several gaps per turn (e.g. 36-2-2-2) read the right pattern and RPM",
    "FIX: big scope files load ~5x faster with far less memory; AI answers with stray braces no longer break parsing",
    "FIX: if Anthropic or DeepSeek retires a model name, the app switches to one your key has and tells you",
    "FIX: AI Check no longer times out — Claude's thinking is kept in check (Anthropic's 'effort' setting), the check "
    "runs in the background so nothing on the page can cut it off, and the scanner shows a live seconds counter",
    "FIX: Glitch catcher no longer cries wolf on direct-injection engines when you lift off the throttle",
    "NEW: 🪜 Step-by-step cards — work the test plan one test at a time: Done → Next, notes on what you found, and "
    "quick buttons for 'Where is it?', 'How do I hook up the tool?' and 'How does it work?'",
    "NEW: 🌟 Simple view (top right) — big status cards, plain-English codes, one test at a time; pro sections tucked away",
    "NEW: Cam/crank correlation — cam edges in crank degrees after the gap (green = intake, red = exhaust), "
    "compared with your known-good captures in degrees",
    "NEW: NHTSA owner complaints for the vehicle, including the ones that sound like this car",
    "NEW: One-tap symptom buttons on the Diagnose tab",
    "NEW: 📷 Camera on the Knowledge tab (snap book pages one at a time) and on Job photos — uploading still works too",
    "FIX: 'Stumble caught' no longer goes off when you lift off the gas, on upshifts, or when the converter locks up — "
    "it now reads the gas pedal sensor (every pass) and only alarms when RPM drops with your foot held on the gas",
    "FASTER: a blurry VIN photo no longer waits on NHTSA lookups for readings that can't be right",
    "NEW: 💬 Quick help chat at the top of every page — knows the open car, codes, scanner data, test plan, shop history "
    "and your Knowledge notes (it picks the notes that match your question)",
    "NEW: Every chat is saved permanently, the AI remembers earlier chats (same car first), 🕘 Past chats to search them, "
    "and 📌 Save to Knowledge turns a good answer into a note",
    "BETTER: The scanner's live drive check, test drive reviews, step-card questions, drive cycle plans and scope data "
    "checks now use your Knowledge notes too",
    "NEW: 🎥 Videos in the chat — Gemini watches and listens (noises, shakes, smoke, scope or scan-tool screens) and "
    "reports to the rest of the team; follow-up questions keep using the same video",
    "NEW: 🤝 Chat answers now come from all the AIs checking each other by default (untick it for a quick one-AI answer)",
    "NEW: 🔆 Keep screen on (top right) stops the phone locking while the app is open; chat answers are worked out in "
    "the background and saved, so locking the phone or switching tabs can't lose them, and a reload brings the chat back",
    "NEW: 🧪 The AI runs its own tests — after an AI Check it lists the tests it wants (O2 sensor response, purge leak, "
    "fuel pressure hold, idle, vacuum, charging, cranking, Mode $06, monitors, test drive). Tap Run and the app does them, "
    "tells you out loud when to rev it, snap it or pinch a hose, then sends the results back to the AI team for a follow-up",
    "FIX: Factory (enhanced) readings that can't be right — like 138 psi barometric pressure or a 2961 gear ratio — are "
    "now hidden, and a group that disagrees with the standard readings is dropped, so they don't confuse you or the AI",
    "NEW: 👀 Let the AI see my screen or camera (top of the page) — share your Autel / Snap-on screen from a computer, or point "
    "the phone camera at it. The AI reads the screen every half minute and uses it in every chat answer and AI Check; "
    "🤔 Ask the AI about this screen gets an answer about exactly what you're looking at",
    "NEW: 📖 Your own test methods from Knowledge come first — the AI uses your method (your steps and values) when it plans a "
    "test and marks it 📖 Shop method, and each step card shows the matching note",
    "NEW: 📐 The AI asks for the wiring diagram when a test needs exact pins or wire colors (it won't guess them). Add a photo, "
    "a screenshot, or one tap from your shared Topdon / Autel screen — it reads the diagram and puts the exact hookup on the "
    "test step, and every later answer uses it",
    "BETTER: ⚙️ Trans → 🌀 TCC now shows TCC slip, TCC desired slip and the TCC command duty % live with a graph, and flags "
    "commanded-on-but-slipping, slip not following desired, stuck applied, command hunting, and lock-up never commanded",
    "NEW: 🧠 Meaning search — Knowledge notes, past fixes (from ANY vehicle) and old chats are found by what they mean, not just "
    "matching words; the Knowledge search box works that way too, and new book-page notes that repeat ones you have are flagged",
    "NEW: 📲 Phone alerts (ntfy) when an AI answer, AI Check, test follow-up, test plan or test drive review is ready",
    "FIX: The chat always knows the car that's open (VIN + engine, drive, transmission) and won't ask for it again; opening the "
    "app on another device picks up the car you were working on in the last few hours",
    "NEW LOOK: 🏠 Home opens on the AI chat (type it or 🎙️ say it), with the car you're on and the cars in the shop below; "
    "the screens moved to a bar along the bottom (Home · Car · Scan · Diagnose · Log · Notes); settings are under ⚙️ top right",
    "FIX: Knowledge now loads ALL your notes (it stopped at 1,000 before)",
    "EASIER: 📋 Paste a diagram — snip it (Windows+Shift+S), click the paste box, Ctrl+V. Or share the diagram's tab once (👀) "
    "and 📺 Use my shared screen grabs a fresh, sharp picture every time you tap it",
    "NEW LOOK: 💬 The app opens on just the chat — type, 📎 add a photo or video, or 🎙️ talk right in the box at the bottom "
    "(⋯ has screen share, all-AIs, past chats; 🧹 New chat is pinned at the top). Buttons along the bottom: 🚗 Vehicle Scan (VIN search, then the "
    "scanner) · 🔧 Diagnostics · 🔬 Scope & Tests (wiring diagrams, scope, test results, test drive review) · 🧾 Customer & "
    "RO · ☰ More (cars in the shop, log, Knowledge)",
    "NEW: ✍️ RO write-up — one tap writes the Concern / Cause / Correction from the job (only what you actually did); it "
    "prints on the repair order with the estimate and goes out with the email",
    "FIX: 🚗 Vehicle Scan's VIN search works again (it crashed on a button name); 🔬 Scope & Tests now opens on the scope, "
    "with wiring diagrams under it; 💬 Chat is just the conversation now — no car bubble",
    "FIX: The ⚡ firing-line logo is back (top left and above the greeting)",
    "NEW: 🔎 Find every reading this car has (🚗 Vehicle Scan → scanner → OEM enhanced data): tries every factory request "
    "on file for the make and its sister brands, plus every standard reading, keeps what the car answers, and remembers it "
    "for that year / make / model / engine — so the next one shows them right away",
    "NEW: 🔗 Sites on the bottom bar — one tap opens ALLDATA, ProDemand, Identifix, MOTOLOGIC or any link you add (you log in "
    "yourself; the app only opens the page). The open car's VIN is right there to copy",
    "NEW: 📄 PDFs — tap ＋ in the chat box to add a PDF (service info, wiring diagram, TSB, manual) and ask about it; and "
    "📖 Knowledge → Learn from book pages or a PDF turns a PDF into notes (pick the pages if it's a big one)",
    "BETTER: 📖 Knowledge leaves out notes you already have when it reads pages or a PDF (same words, or same meaning with the "
    "same numbers) — you only see the new ones",
    "NEW: 💬 ChatGPT joined the AI team (add OPENAI_API_KEY in Secrets). Who does what now: Perplexity searches the web · Gemini "
    "watches videos, listens, reads PDFs and writes a draft · ChatGPT writes its own diagnosis (it sees your photos) · DeepSeek "
    "gives a third opinion · Claude checks every draft against the data and writes the final answer. If one is down its backup "
    "takes over (ChatGPT can do the final check and the web search). See ⚙️ → Setup → Who does what",
    "BETTER THINKING: every AI is told to reason from the evidence (what was measured, what each reading rules in or out, the "
    "test that separates the top causes); Claude's final check runs at high effort; DeepSeek and Gemini think it through "
    "instead of rushing; test plans get deeper web research; wiring diagrams are read twice by two different AIs and any pin "
    "or wire color they read differently is flagged",
    "NEW: 📊 Every standard reading — all ~190 SAE PIDs are built in (second O2 banks, wide-range O2, torque, turbo, EGR, diesel "
    "aftertreatment, hybrid battery, trans gear…). The car is only asked for the ones it supports; they show under the Std "
    "groups. The freeze frame now shows everything the car stored, and 🪪 Computer software shows the calibration IDs",
    "NEW: 🔎 Find every reading runs by itself the first time a car is connected, and it reaches a lot more: each make's master "
    "list, multi-frame readings, newer GM (29-bit) computers, Nissan / Infiniti and Stellantis readings that need a diagnostic "
    "session. FIX: cars whose own network is 29-bit (most Hondas) now connect and read correctly",
]

st.markdown(
    f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
:root {{ --tdg-cyan: #22D3EE; --tdg-teal: #14B8A6; --tdg-green: #34D399; --tdg-card: rgba(22,25,30,.92); --tdg-line: rgba(255,255,255,.08);
         --tdg-muted: #9AA3AD; }}
.stApp {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  background: radial-gradient(900px 520px at 0% 0%, rgba(20,184,166,.13), transparent 62%),
              radial-gradient(900px 700px at 100% 100%, rgba(16,185,129,.12), transparent 60%), #0b0e12 !important; }}
.block-container {{ position: relative; padding-top: 3.6rem !important; padding-bottom: 120px !important; max-width: 1100px !important; }}
#MainMenu, footer {{ visibility: hidden; }}
h1, h2, h3, .tdg-title {{ font-family: 'Space Grotesk', 'Inter', sans-serif !important; letter-spacing: -.01em; }}
/* top bar */
.tdg-top {{ display: flex; align-items: center; gap: 12px; margin: 0 0 .4rem; min-height: 46px; }}
.tdg-top .t1 {{ font-family: 'Space Grotesk', sans-serif; font-weight: 700; font-size: 1.15rem; line-height: 1.1; }}
.tdg-top .t2 {{ font-family: 'JetBrains Mono', monospace; font-size: .68rem; color: var(--tdg-muted); letter-spacing: .18em; }}
.st-key-gear {{ position: absolute !important; top: calc(3.6rem + 4px); right: 1rem; width: auto !important; z-index: 60; }}
/* "Today" header + section labels + cards */
.tdg-today h1 {{ font-size: 2.6rem !important; font-weight: 700 !important; margin: .2rem 0 0 !important; padding: 0 !important; }}
.tdg-today .sub {{ color: var(--tdg-muted); font-size: 1.02rem; margin: .1rem 0 1rem; }}
.tdg-label {{ font-family: 'JetBrains Mono', monospace; color: var(--tdg-muted); letter-spacing: .32em; font-size: .78rem;
  text-transform: uppercase; margin: 1.3rem 0 .55rem; }}
.tdg-hero {{ display: flex; align-items: center; gap: 16px; margin-bottom: .6rem; }}
.tdg-hero .ic {{ width: 54px; height: 54px; border-radius: 16px; background: #0d1116; border: 1px solid rgba(34,211,238,.45);
  box-shadow: 0 0 22px rgba(34,211,238,.25); display: flex; align-items: center; justify-content: center; flex: none; }}
.tdg-hero .k {{ font-family: 'JetBrains Mono', monospace; letter-spacing: .3em; font-size: .72rem; color: var(--tdg-muted); }}
.tdg-hero .h {{ font-family: 'Space Grotesk', sans-serif; font-size: 1.55rem; font-weight: 700; line-height: 1.15; }}
.tdg-hero .h b {{ color: var(--tdg-cyan); }}
.tdg-hero .s {{ color: var(--tdg-muted); font-size: .95rem; }}
.st-key-quickhelp {{ background: linear-gradient(135deg, rgba(34,211,238,.07), rgba(22,25,30,.92) 45%) !important;
  border: 1px solid rgba(34,211,238,.38) !important; border-radius: 22px !important; padding: 18px 16px !important;
  box-shadow: 0 0 34px -12px rgba(34,211,238,.35); }}
[class*="st-key-jobcard_"], .st-key-carnow {{ background: var(--tdg-card) !important; border: 1px solid var(--tdg-line) !important;
  border-left: 4px solid var(--tdg-teal) !important; border-radius: 20px !important; padding: 14px 16px !important; }}
.tdg-car .v {{ font-family: 'Space Grotesk', sans-serif; font-size: 1.2rem; font-weight: 600; }}
.tdg-car .m {{ font-family: 'JetBrains Mono', monospace; font-size: .74rem; letter-spacing: .14em; color: var(--tdg-muted); text-transform: uppercase; }}
.tdg-car .codes {{ font-family: 'JetBrains Mono', monospace; color: var(--tdg-green); font-weight: 600; }}
/* bottom tab bar (the app's tabs, moved to the bottom like a phone app) */
[data-testid="stTabs"] > div:first-child {{ position: static; }}
[data-testid="stTabs"] [role="tablist"], div[data-baseweb="tab-list"] {{ position: fixed !important; left: 50%; bottom: 0; transform: translateX(-50%);
  width: min(100%, 760px); z-index: 999; margin: 0 !important; display: flex !important; justify-content: space-around; gap: 0 !important;
  background: rgba(12,15,19,.97) !important; border: none !important; border-top: 1px solid var(--tdg-line) !important; border-radius: 0 !important;
  padding: 4px 2px calc(6px + env(safe-area-inset-bottom)) !important; overflow: visible !important; backdrop-filter: blur(10px); }}
[data-testid="stTabs"] [role="tablist"]::after {{ display: none !important; content: none !important; }}
[data-testid="stTabs"] [role="tab"], button[data-baseweb="tab"] {{ position: relative; flex: 1 1 0 !important; flex-direction: column !important;
  justify-content: center; align-items: center; gap: 3px; min-width: 0 !important; padding: 7px 2px 4px !important; border: none !important;
  background: transparent !important; box-shadow: none !important; height: auto !important; color: var(--tdg-muted) !important; }}
[data-testid="stTabs"] [role="tab"]::before {{ content: ""; width: 25px; height: 25px; background-color: currentColor;
  -webkit-mask-repeat: no-repeat; mask-repeat: no-repeat; -webkit-mask-position: center; mask-position: center;
  -webkit-mask-size: contain; mask-size: contain; }}
[data-testid="stTabs"] [role="tab"]:nth-child(1)::before {{ -webkit-mask-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M21 11.5a8.4 8.4 0 0 1-12.3 7.4L3 20.5l1.6-5.2A8.4 8.4 0 1 1 21 11.5z'/><path d='M8.5 11.5h.01M12.5 11.5h.01M16.5 11.5h.01'/></svg>"); mask-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M21 11.5a8.4 8.4 0 0 1-12.3 7.4L3 20.5l1.6-5.2A8.4 8.4 0 1 1 21 11.5z'/><path d='M8.5 11.5h.01M12.5 11.5h.01M16.5 11.5h.01'/></svg>"); }}
[data-testid="stTabs"] [role="tab"]:nth-child(2)::before {{ -webkit-mask-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M3 16v-3l2-6h14l2 6v3z'/><path d='M3 16v3h3v-3M18 16v3h3v-3'/><circle cx='7.5' cy='13' r='1'/><circle cx='16.5' cy='13' r='1'/></svg>"); mask-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M3 16v-3l2-6h14l2 6v3z'/><path d='M3 16v3h3v-3M18 16v3h3v-3'/><circle cx='7.5' cy='13' r='1'/><circle cx='16.5' cy='13' r='1'/></svg>"); }}
[data-testid="stTabs"] [role="tab"]:nth-child(3)::before {{ -webkit-mask-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z'/></svg>"); mask-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z'/></svg>"); }}
[data-testid="stTabs"] [role="tab"]:nth-child(4)::before {{ -webkit-mask-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><rect x='2.5' y='4' width='19' height='14' rx='2'/><path d='M5 12c1.4-4 2.8-4 4.2 0s2.8 4 4.2 0 2.8-4 4.2 0'/><path d='M8 21h8'/></svg>"); mask-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><rect x='2.5' y='4' width='19' height='14' rx='2'/><path d='M5 12c1.4-4 2.8-4 4.2 0s2.8 4 4.2 0 2.8-4 4.2 0'/><path d='M8 21h8'/></svg>"); }}
[data-testid="stTabs"] [role="tab"]:nth-child(5)::before {{ -webkit-mask-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><rect x='5' y='4' width='14' height='17' rx='2'/><path d='M9 3h6v3H9zM9 11h6M9 15h6'/></svg>"); mask-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><rect x='5' y='4' width='14' height='17' rx='2'/><path d='M9 3h6v3H9zM9 11h6M9 15h6'/></svg>"); }}
[data-testid="stTabs"] [role="tab"]:nth-child(6)::before {{ -webkit-mask-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M10 14a4.5 4.5 0 0 0 6.4 0l3.2-3.2a4.5 4.5 0 0 0-6.4-6.4l-1.1 1.1'/><path d='M14 10a4.5 4.5 0 0 0-6.4 0l-3.2 3.2a4.5 4.5 0 0 0 6.4 6.4l1.1-1.1'/></svg>"); mask-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M10 14a4.5 4.5 0 0 0 6.4 0l3.2-3.2a4.5 4.5 0 0 0-6.4-6.4l-1.1 1.1'/><path d='M14 10a4.5 4.5 0 0 0-6.4 0l-3.2 3.2a4.5 4.5 0 0 0 6.4 6.4l1.1-1.1'/></svg>"); }}
[data-testid="stTabs"] [role="tab"]:nth-child(7)::before {{ -webkit-mask-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M4 7h16M4 12h16M4 17h16'/></svg>"); mask-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M4 7h16M4 12h16M4 17h16'/></svg>"); }}
[data-testid="stTabs"] [role="tab"] p {{ font-size: .6rem !important; font-weight: 600 !important; letter-spacing: .07em; text-transform: uppercase;
  color: var(--tdg-muted) !important; margin: 0 !important; white-space: normal; text-align: center; line-height: 1.15 !important; }}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {{ color: var(--tdg-cyan) !important; }}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] p {{ color: #F1F5F9 !important; }}
[data-testid="stTabs"] [role="tab"][aria-selected="true"]::after {{ content: ""; position: absolute; top: 0; left: 28%; right: 28%; height: 3px;
  border-radius: 0 0 3px 3px; background: var(--tdg-cyan); }}
div[data-baseweb="tab-highlight"], div[data-baseweb="tab-border"], [data-testid="stTabs"] .react-aria-SelectionIndicator {{ display: none !important; }}
/* 💬 chat front screen: greeting, conversation, and the message bar pinned above the bottom buttons */
.tdg-greet {{ text-align: center; margin: 8vh auto 1rem; max-width: 560px; }}
.tdg-greet .ic {{ width: 86px; height: 62px; margin: 0 auto 16px; border-radius: 18px; background: #0d1116;
  border: 1px solid rgba(34,211,238,.45); box-shadow: 0 0 26px rgba(34,211,238,.28); display: flex; align-items: center; justify-content: center; }}
.tdg-greet h1 {{ font-size: 2.05rem !important; font-weight: 600 !important; margin: 0 !important; padding: 0 !important; line-height: 1.2 !important; }}
.tdg-greet .q {{ color: var(--tdg-muted); font-size: 1.15rem; margin-top: .35rem; }}
.tdg-greet .car {{ display: inline-block; margin-top: 1.2rem; background: rgba(34,211,238,.08); border: 1px solid rgba(34,211,238,.3);
  color: #E2E8F0; padding: 6px 14px; border-radius: 999px; font-size: .88rem; }}
.tdg-greet .tip {{ color: #6B7682; font-size: .84rem; margin-top: 1.1rem; }}
.tdg-chathead {{ font-family: 'JetBrains Mono', monospace; font-size: .75rem; letter-spacing: .08em; color: var(--tdg-muted);
  text-align: center; margin: 0 0 .4rem; }}
.tdg-chatpad {{ height: 64px; }}
.st-key-newchat {{ position: fixed !important; top: calc(11px + env(safe-area-inset-top)); right: 12px; width: auto !important;
  z-index: 1000001; }}
.st-key-newchat button {{ min-height: 38px !important; border-radius: 999px !important; padding: 0 16px !important;
  background: rgba(13,17,22,.96) !important; border: 1px solid rgba(34,211,238,.5) !important; box-shadow: 0 0 16px rgba(34,211,238,.18); }}
.st-key-chatbar {{ position: fixed !important; left: 0; right: 0; margin: 0 auto !important; bottom: calc(76px + env(safe-area-inset-bottom));
  width: min(calc(100% - 20px), 740px) !important; max-width: none !important; z-index: 998; display: flex !important;
  flex-direction: row !important; flex-wrap: nowrap !important; align-items: flex-end !important; gap: 8px !important;
  padding: 7px !important; background: rgba(13,17,22,.96); border: 1px solid rgba(34,211,238,.35); border-radius: 24px;
  box-shadow: 0 -8px 30px rgba(0,0,0,.5); backdrop-filter: blur(10px); }}
.st-key-chatbar > div {{ width: auto !important; flex: 0 0 auto !important; min-width: 0 !important; margin: 0 !important; }}
.st-key-chatbar > div:has([data-testid="stChatInput"]) {{ flex: 1 1 auto !important; }}
.st-key-chatbar [data-testid="stChatInput"] {{ border: none !important; background: transparent !important; }}
.st-key-chatbar [data-testid="stPopover"] button, .st-key-chatbar [data-testid="stPopoverButton"] {{ min-height: 46px; border-radius: 16px !important;
  padding: 0 12px !important; font-size: 1.15rem !important; }}
.st-key-jobbar [data-testid="stHorizontalBlock"] {{ flex-wrap: nowrap !important; gap: .45rem !important; }}
.st-key-jobbar [data-testid="stColumn"], .st-key-jobbar [data-testid="column"] {{ min-width: 0 !important; }}
.st-key-jobbar button p {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
@media (max-width: 520px) {{
  [data-testid="stTabs"] [role="tab"] p {{ text-transform: none; letter-spacing: 0; font-size: .64rem !important; }}
  [data-testid="stTabs"] [role="tab"], button[data-baseweb="tab"] {{ flex: 1 1 0 !important; min-width: min-content !important;
    padding-left: 1px !important; padding-right: 1px !important; }}
  .tdg-greet {{ margin-top: 5vh; }}
  .tdg-greet h1 {{ font-size: 1.7rem !important; }}
}}
/* cards, expanders, inputs, buttons */
div[data-testid="stExpander"] {{ border: 1px solid var(--tdg-line) !important; border-radius: 18px !important; overflow: hidden;
  background: rgba(22,25,30,.7); }}
div[data-baseweb="input"] > div, div[data-baseweb="select"] > div, div[data-baseweb="textarea"] > div {{ border-radius: 12px !important; }}
button[kind="primary"], button[data-testid="stBaseButton-primary"], button[data-testid="stFormSubmitButton"] {{
  background: linear-gradient(135deg, #14B8A6, #22D3EE) !important; color: #04131a !important; border: none !important; font-weight: 700 !important; }}
.stButton > button, .stDownloadButton > button {{ border-radius: 12px !important; }}
/* context bar on each screen */
.tdg-bar {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; background: var(--tdg-card); border:1px solid var(--tdg-line);
  padding:10px 14px; border-radius:18px; margin-bottom:12px; font-size:.85rem; }}
.tdg-bar .pill {{ background:rgba(255,255,255,.05); color:#E2E8F0; padding:3px 10px; border-radius:8px; font-weight:600; }}
.tdg-bar .dtc {{ font-family:'JetBrains Mono',monospace; font-weight:600; padding:3px 10px; border-radius:8px; }}
.tdg-next {{ flex-basis:100%; color:#8B9BB4; font-size:.8rem; }}
.tdg-next b {{ color: var(--tdg-cyan); }}
/* simple view: big status cards + step cards */
.tdg-card {{ border-radius:16px; padding:12px 14px; margin-bottom:10px; border:1px solid var(--tdg-line); color:#F1F5F9; }}
.tdg-card small {{ color:rgba(241,245,249,.8); }}
.tdg-big {{ font-size:1.45rem; font-weight:800; margin:2px 0; font-family:'JetBrains Mono',monospace; }}
.tdg-green {{ background:linear-gradient(135deg,#064E3B,#065F46); border-left:6px solid #10B981; }}
.tdg-yellow {{ background:linear-gradient(135deg,#713F12,#854D0E); border-left:6px solid #F59E0B; }}
.tdg-red {{ background:linear-gradient(135deg,#7F1D1D,#991B1B); border-left:6px solid #EF4444; }}
.tdg-blue {{ background:linear-gradient(135deg,#0E3A4A,#0E5266); border-left:6px solid var(--tdg-cyan); }}
.tdg-gray {{ background:rgba(51,65,85,.55); border-left:6px solid #64748B; }}
.tdg-step {{ background:#121a24; border:2px solid var(--tdg-cyan); border-radius:20px; padding:16px 18px; margin:8px 0 10px; color:#F1F5F9; }}
.tdg-step h3 {{ margin:.2rem 0 .4rem; color: var(--tdg-cyan); }}
.tdg-step p {{ margin:.25rem 0; font-size:1.02rem; line-height:1.5; }}
.tdg-badge {{ display:inline-block; background: var(--tdg-cyan); color:#0F172A; font-weight:800; padding:2px 10px; border-radius:999px; font-size:.8rem; }}
.tdg-spec {{ color:#FDE68A; }}
.tdg-safe {{ color:#FCA5A5; }}
</style>

<div class="tdg-top">
  <svg width="50" height="30" viewBox="0 0 120 70" fill="none" xmlns="http://www.w3.org/2000/svg" style="filter: drop-shadow(0 0 6px rgba(34,211,238,.55));">
    <defs><linearGradient id="tdgG" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#14B8A6"/><stop offset="1" stop-color="#22D3EE"/></linearGradient></defs>
    <path d="M 5 45 L 22 45 L 24 60 L 42 60 L 43 5 L 46 36 Q 48 34 54 36 T 64 36 T 74 35 T 80 36 Q 84 18 88 50 Q 92 24 96 44 Q 100 32 104 42 L 118 42" stroke="url(#tdgG)" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>
  <div><div class="t1">Test Don't Guess</div><div class="t2">AI DIAGNOSTICS · v{APP_VERSION}</div></div>
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
    "tech_notes": "", "customer_summary": "", "fix_part": "", "fix_test": "", "fix_notes": "", "ro_story": "",
    "customer_email": "", "odometer": "", "estimate_rows": [], "follow_up_days": 0, "follow_up_note": "",
    "follow_up_done": False, "drive_plan": "", "wave_result": None, "know_pending": None,
    "plan_steps": None, "plan_idx": 0, "plan_done": [], "plan_notes": {}, "plan_qa": None, "diag_requests": [],
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
             "go to ☰ More → 📋 Log & history → 🐞 Problem log and copy the report to Claude.")
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


_TLS = threading.local()


def http() -> requests.Session:
  """Keep-alive connection pool (faster repeat API calls) — one per worker thread, so two techs using the app at the
  same moment never share a connection."""
  sess = getattr(_TLS, "session", None)
  if sess is None:
    sess = _TLS.session = requests.Session()
  return sess


def find_json(text: str, want=dict):
  """Pull the first real JSON object (or list) out of an AI answer, even if it's wrapped in ```code fences``` or has
  chatty text with {braces} before or after it."""
  t = re.sub(r"```(?:json)?", "", text or "")
  dec = json.JSONDecoder()
  for mt in re.finditer(r"\{" if want is dict else r"\[", t):
    try:
      obj, _ = dec.raw_decode(t[mt.start():])
    except ValueError:
      continue
    if isinstance(obj, want):
      return obj
  return None


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


# ---- 📲 Phone alerts through ntfy (free app: subscribe to your NTFY_TOPIC) ----
def ntfy_ready() -> bool:
  return bool(secret("NTFY_TOPIC"))


def app_link(job_id: str | None = None, chat: str | None = None) -> str:
  """A link back into the app (tapping the phone alert opens this job / conversation)."""
  base = secret("APP_URL") or ""
  if not base:
    try:
      host = st.context.headers.get("host") or ""
      base = f"https://{host}" if host else ""
    except Exception:
      base = ""
  if not base:
    return ""
  q = "&".join(x for x in (f"job={job_id}" if job_id else "", f"chat={chat}" if chat else "") if x)
  return base.rstrip("/") + ("/?" + q if q else "/")


def notify(title: str, message: str, tags: str = "wrench", priority: int = 3, click: str = "") -> bool:
  """Push a phone alert (never customer names or numbers — just the car and the result). Sent in the background."""
  topic = (secret("NTFY_TOPIC") or "").strip()
  if not topic:
    return False
  server = (secret("NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
  body = {"topic": topic, "title": str(title)[:120], "message": str(message)[:900] or " ",
          "tags": [t for t in str(tags).split(",") if t], "priority": int(priority)}
  if click:
    body["click"] = click
  headers = {"Authorization": f"Bearer {secret('NTFY_TOKEN')}"} if secret("NTFY_TOKEN") else {}
  def send():
    try:
      r = requests.post(server, json=body, headers=headers, timeout=15)
      if r.status_code >= 300:
        log_problem("alerts", "Phone alert (ntfy)", f"HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
      log_problem("alerts", "Phone alert (ntfy)", str(e))
  threading.Thread(target=send, daemon=True).start()
  return True


def first_line(text: str, n: int = 160) -> str:
  for ln in str(text or "").splitlines():
    ln = re.sub(r"[#*_`>|]+", "", ln).strip(" -•")
    if len(ln) > 3:
      return ln[:n]
  return ""


# ---- Background AI jobs: a long AI answer can't be cut off by a page refresh, a tap, or the phone locking ----
@st.cache_resource
def _ai_jobs() -> dict:
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
      if re.fullmatch(r"[\w .\-]{1,80}", str(v)):   # plain text only; anything else gets matched below, never sent
        params[f"data->>{k}"] = f"eq.{v}"
    try:
      r = http().get(_supa_url(), headers=_supa_headers(), params=params, timeout=10)
      if r.status_code == 200:
        rows = [x for x in r.json() if all(str((x.get("data") or {}).get(k, "")) == str(v) for k, v in where.items())]
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


def store_put_many(kind: str, rows: list) -> bool:
  """Save many records in one request: rows = [(id, data), ...]."""
  if not rows:
    return True
  _bump(kind)
  if store_on():
    try:
      now = datetime.now(timezone.utc).isoformat()
      for i in range(0, len(rows), 200):
        r = http().post(_supa_url(), timeout=30, json=[{"kind": kind, "id": rid, "data": _clean(d), "updated_at": now}
                                                         for rid, d in rows[i:i + 200]],
                        headers=_supa_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}))
        if r.status_code >= 300:
          _store_error(f"Saving {kind} failed: HTTP {r.status_code} {r.text[:200]}")
          break
      else:
        return True
    except requests.RequestException as e:
      _store_error(f"Saving {kind} failed: {e}")
  for rid, d in rows:   # no permanent storage (or it failed): keep them on the temporary disk
    try:
      with open(os.path.join(_local_dir(kind), re.sub(r"[^\w\-]", "", rid) + ".json"), "w", encoding="utf-8") as f:
        json.dump({"id": rid, "data": _clean(d), "updated_at": datetime.now(timezone.utc).isoformat()}, f)
    except OSError:
      pass
  return False


def store_list_all(kind: str, where: dict | None = None) -> list[dict]:
  """Every record of a kind (pages past the database's 1,000-row limit)."""
  return _store_list_all(kind, json.dumps(where or {}, sort_keys=True), _store_versions().get(kind, 0), store_on())


@st.cache_data(ttl=600, show_spinner=False, max_entries=40)
def _store_list_all(kind: str, where_json: str, ver: int, online: bool) -> list[dict]:
  where = json.loads(where_json)
  if not online:
    return _store_list(kind, 100000, where_json, ver, online)
  rows, off = [], 0
  while True:
    params = {"kind": f"eq.{kind}", "select": "id,data", "order": "id.asc", "limit": "1000", "offset": str(off)}
    for k, v in where.items():
      params[f"data->>{k}"] = f"eq.{v}"
    try:
      r = http().get(_supa_url(), headers=_supa_headers(), params=params, timeout=30)
    except requests.RequestException as e:
      _store_error(f"Listing {kind} failed: {e}")
      break
    if r.status_code != 200:
      _store_error(f"Listing {kind} failed: HTTP {r.status_code}")
      break
    page = r.json()
    rows += page
    if len(page) < 1000:
      break
    off += 1000
  return rows


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


@st.cache_resource
def _model_swaps() -> dict:
  """Shared notes about the AI models: a retired name -> its replacement, settings a model doesn't take."""
  return {}


def gemini_model() -> str:
  return ss.get("_gemini_model_ok") or secret("GEMINI_MODEL") or GEMINI_DEFAULT_MODEL


def gemini_label() -> str:
  m = gemini_model().replace("gemini-", "Gemini ").replace("-flash", " Flash").replace("-pro", " Pro").replace("-lite", " Lite")
  return m


def gemini(parts: list, *, json_mode: bool = False, timeout: int = 60, think: str | None = None) -> str:
  """Ask Gemini. `think` is how hard it reasons before it answers: "minimal" / "low" / "medium" / "high" (None = the
  model's own default, which is medium). Diagnosis drafts and the video / PDF / diagram reports ask for "high"; quick
  reads (voice, a scan-tool screen) ask for "low" so they stay fast. A model that doesn't take the setting is asked
  again without it, and if Google is busy (429 / 5xx) the request is tried once more."""
  key = secret("GEMINI_API_KEY")
  if not key:
    raise AIError("GEMINI_API_KEY is missing from Streamlit Secrets.")
  model = gemini_model()
  fell_back = retried = False
  res = None
  for _attempt in range(5):
    cfg = {}
    if json_mode:
      cfg["response_mime_type"] = "application/json"
    if think and not _model_swaps().get(("gemini_no_think", model)):
      cfg["thinkingConfig"] = {"thinkingLevel": think}
    payload = {"contents": [{"parts": parts}]}
    if cfg:
      payload["generationConfig"] = cfg
    try:
      res = http().post(GEMINI_URL.format(model=model), headers={"x-goog-api-key": key}, json=payload, timeout=timeout)
    except requests.RequestException as e:
      raise AIError(f"Gemini connection error: {e}") from e
    if res.status_code == 400 and "thinkingConfig" in cfg and re.search(r"think", res.text or "", re.I):
      _model_swaps()[("gemini_no_think", model)] = True   # this model doesn't take a thinking level: ask without it
      continue
    # Model not available on this key/region -> fall back once to the older model
    if res.status_code in (400, 404) and model != GEMINI_FALLBACK_MODEL and "model" in res.text.lower() and not fell_back:
      model = GEMINI_FALLBACK_MODEL
      ss["_gemini_model_ok"] = model
      fell_back = True
      continue
    if res.status_code in (429, 500, 502, 503, 504) and not retried:   # busy: wait a moment and try once more
      retried = True
      time.sleep(2.5)
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


GEMINI_UPLOAD_URL = "https://generativelanguage.googleapis.com/upload/v1beta/files"
GEMINI_FILE_URL = "https://generativelanguage.googleapis.com/v1beta/{name}"
VIDEO_TYPES = {"mp4": "video/mp4", "m4v": "video/mp4", "mov": "video/mov", "webm": "video/webm", "3gp": "video/3gpp",
               "avi": "video/avi", "mpeg": "video/mpeg", "mpg": "video/mpg", "wmv": "video/wmv"}
PHOTO_TYPES = ["png", "jpg", "jpeg", "webp"]


def video_mime(name: str) -> str:
  return VIDEO_TYPES.get(str(name).rsplit(".", 1)[-1].lower(), "video/mp4")


def is_video(name: str) -> bool:
  return str(name).rsplit(".", 1)[-1].lower() in VIDEO_TYPES


DOC_TYPES = {"pdf": "application/pdf"}


def is_doc(name: str) -> bool:
  return str(name).rsplit(".", 1)[-1].lower() in DOC_TYPES


def media_mime(name: str) -> str:
  """Videos and PDFs both go to Gemini's file store; this is the type to send."""
  return DOC_TYPES.get(str(name).rsplit(".", 1)[-1].lower()) or video_mime(name)


def gemini_upload(data: bytes, mime: str, name: str = "video", wait: int = 240) -> dict:
  """Send a video to Gemini's file store (videos are too big to send inline) and wait until Gemini has processed it.
  Returns {"uri", "mime", "name", "at"}. Google deletes these files by itself after 48 hours."""
  key = secret("GEMINI_API_KEY")
  if not key:
    raise AIError("GEMINI_API_KEY is missing from Streamlit Secrets — Gemini is the AI that watches and listens to videos.")
  s = http()
  try:
    r = s.post(GEMINI_UPLOAD_URL, timeout=30, json={"file": {"display_name": str(name)[:100]}},
               headers={"x-goog-api-key": key, "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
                        "X-Goog-Upload-Header-Content-Length": str(len(data)), "X-Goog-Upload-Header-Content-Type": mime,
                        "Content-Type": "application/json"})
    url = r.headers.get("x-goog-upload-url")
    if r.status_code != 200 or not url:
      raise AIError(f"Couldn't start sending the video to Gemini (HTTP {r.status_code}): {r.text[:200]}")
    r = s.post(url, data=data, timeout=600, headers={"Content-Length": str(len(data)), "X-Goog-Upload-Offset": "0",
                                                     "X-Goog-Upload-Command": "upload, finalize"})
    if r.status_code != 200:
      raise AIError(f"Sending the video to Gemini failed (HTTP {r.status_code}): {r.text[:200]}")
    f = r.json().get("file") or {}
    t0 = time.time()
    while f.get("name") and f.get("state") not in ("ACTIVE", "FAILED") and time.time() - t0 < wait:
      time.sleep(3)
      g = s.get(GEMINI_FILE_URL.format(name=f["name"]), headers={"x-goog-api-key": key}, timeout=20)
      if g.status_code == 200:
        f = g.json()
  except requests.RequestException as e:
    raise AIError(f"Video upload connection error: {e}") from e
  except ValueError as e:
    raise AIError("Gemini sent back an unreadable answer about the video.") from e
  if f.get("state") != "ACTIVE" or not f.get("uri"):
    raise AIError(f"Gemini couldn't process the video (state: {f.get('state') or 'unknown'}). Try a shorter clip (under a minute works best).")
  return {"uri": f["uri"], "mime": f.get("mimeType") or mime, "name": str(name), "at": time.time()}


# ========================================================
# --- 🧠 MEANING SEARCH (embeddings): notes, past fixes and chats found by what they MEAN, not just matching words ---
# Uses a free model on this server if fastembed is installed (pip install fastembed), otherwise Gemini's embedding
# model (same Gemini key), or Hugging Face if HF_TOKEN is set. EMBED_PROVIDER = "local" / "gemini" / "hf" forces one.
# ========================================================
GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
HF_EMBED_URL = "https://router.huggingface.co/hf-inference/models/{model}/pipeline/feature-extraction"


@st.cache_resource
def _local_embedder():
  try:
    from fastembed import TextEmbedding
    return TextEmbedding(secret("LOCAL_EMBED_MODEL") or "BAAI/bge-small-en-v1.5")
  except Exception:
    return None


@st.cache_resource
def _embed_state() -> dict:
  return {}


def embed_provider() -> str:
  want = (secret("EMBED_PROVIDER") or "").strip().lower()
  if want == "local" or (not want and _local_embedder() is not None):
    if _local_embedder() is not None:
      return "local"
  if want in ("", "gemini") and secret("GEMINI_API_KEY") and not _embed_state().get("gemini_off"):
    return "gemini"
  if want in ("", "hf") and secret("HF_TOKEN"):
    return "hf"
  return ""


def _gemini_embed_model() -> str:
  st_ = _embed_state()
  if secret("EMBED_MODEL"):
    return secret("EMBED_MODEL")
  if st_.get("gemini_model"):
    return st_["gemini_model"]
  model = "gemini-embedding-001"
  try:   # pick the newest embedding model this key has (they get renamed over time)
    r = http().get(GEMINI_MODELS_URL, headers={"x-goog-api-key": secret("GEMINI_API_KEY")}, params={"pageSize": 200}, timeout=15)
    names = [m["name"].split("/")[-1] for m in (r.json().get("models") or [])
             if "embedContent" in (m.get("supportedGenerationMethods") or []) and "embedding" in m.get("name", "")
             and "exp" not in m.get("name", "")]
    best = sorted([n for n in names if n.startswith("gemini-embedding")], reverse=True) or names
    if best:
      model = best[0]
  except Exception:
    pass
  st_["gemini_model"] = model
  return model


def embed_model_key() -> str:
  p = embed_provider()
  if p == "local":
    return "local:" + (secret("LOCAL_EMBED_MODEL") or "BAAI/bge-small-en-v1.5")
  if p == "gemini":
    return "gemini:" + _gemini_embed_model()
  if p == "hf":
    return "hf:" + (secret("HF_EMBED_MODEL") or "BAAI/bge-small-en-v1.5")
  return ""


def embed_texts(texts: list[str], kind: str = "doc") -> np.ndarray:
  """Meaning fingerprints for these texts (one normalized row each). kind: doc = stored item, query = a search."""
  p = embed_provider()
  texts = [str(t or " ")[:6000] for t in texts]
  if not p or not texts:
    raise AIError("No meaning-search engine set up.")
  if p == "local":
    m = _local_embedder()
    vecs = list(m.query_embed(texts) if kind == "query" else m.embed(texts))
    out = np.array(vecs, dtype=np.float32)
  elif p == "gemini":
    model, out_rows = _gemini_embed_model(), []
    task = "RETRIEVAL_QUERY" if kind == "query" else "RETRIEVAL_DOCUMENT"
    for i in range(0, len(texts), 100):
      body = {"requests": [{"model": f"models/{model}", "content": {"parts": [{"text": t}]}, "taskType": task,
                            "outputDimensionality": 768} for t in texts[i:i + 100]]}
      try:
        r = http().post(f"{GEMINI_MODELS_URL}/{model}:batchEmbedContents", headers={"x-goog-api-key": secret("GEMINI_API_KEY")},
                        json=body, timeout=60)
        if r.status_code == 400 and "imensionality" in r.text:   # an older model without the size option
          for q in body["requests"]:
            q.pop("outputDimensionality", None)
          r = http().post(f"{GEMINI_MODELS_URL}/{model}:batchEmbedContents", headers={"x-goog-api-key": secret("GEMINI_API_KEY")},
                          json=body, timeout=60)
      except requests.RequestException as e:
        raise AIError(f"Meaning search (Gemini) connection error: {e}") from e
      if r.status_code in (403, 404):
        _embed_state().pop("gemini_model", None)
      if r.status_code != 200:
        raise AIError(f"Meaning search (Gemini) error {r.status_code}: {r.text[:200]}")
      out_rows += [e_.get("values") or [] for e_ in r.json().get("embeddings") or []]
    out = np.array(out_rows, dtype=np.float32)
  else:
    try:
      r = http().post(HF_EMBED_URL.format(model=secret("HF_EMBED_MODEL") or "BAAI/bge-small-en-v1.5"), timeout=60,
                      headers={"Authorization": f"Bearer {secret('HF_TOKEN')}"}, json={"inputs": texts, "normalize": True})
    except requests.RequestException as e:
      raise AIError(f"Meaning search (Hugging Face) connection error: {e}") from e
    if r.status_code != 200:
      raise AIError(f"Meaning search (Hugging Face) error {r.status_code}: {r.text[:200]}")
    out = np.array(r.json(), dtype=np.float32)
    if out.ndim == 3:   # token vectors: average them
      out = out.mean(axis=1)
  if out.ndim != 2 or out.shape[0] != len(texts):
    raise AIError("Meaning search returned the wrong number of results.")
  return out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-9)


@st.cache_data(ttl=3600, show_spinner=False, max_entries=500)
def _query_vec(model_key: str, text: str) -> np.ndarray:
  return embed_texts([text], "query")[0]


def _vpack(v: np.ndarray) -> str:
  return base64.b64encode(np.asarray(v, dtype=np.float16).tobytes()).decode()


def _vunpack(s: str) -> np.ndarray:
  return np.frombuffer(base64.b64decode(s), dtype=np.float16).astype(np.float32)


def ensure_vectors(src: str, items: list) -> dict:
  """Fingerprints for these (id, text) items, making and saving any that are missing or out of date. {} if unavailable."""
  mkey = embed_model_key()
  if not mkey or not items:
    return {}
  have = {}
  for r in store_list_all("emb", {"model": mkey, "src": src}):
    d = r.get("data") or {}
    if d.get("sid") and d.get("v"):
      have[d["sid"]] = (d.get("h"), d["v"])
  todo = [(sid, t) for sid, t in items if have.get(sid, (None,))[0] != hashlib.md5(t.encode()).hexdigest()[:12]]
  if todo:   # a big library is built a few hundred at a time (each batch is saved, so nothing is redone)
    with st.spinner(f"🧠 Building meaning search for {len(todo)} item(s) — one time…" if len(todo) > 20 else "🧠 …"):
      for i in range(0, min(len(todo), 400), 100):
        chunk = todo[i:i + 100]
        try:
          vecs = embed_texts([t for _, t in chunk], "doc")
        except Exception as e:
          if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):   # going too fast for the free tier: finish next time
            break
          if not _embed_state().get("warned"):
            _embed_state()["warned"] = True
            log_problem("ai", "Meaning search", str(e))
          break
        rows = []
        for (sid, t), v in zip(chunk, vecs):
          packed = _vpack(v)
          have[sid] = (hashlib.md5(t.encode()).hexdigest()[:12], packed)
          rows.append((hashlib.md5(f"{mkey}|{src}|{sid}".encode()).hexdigest(),
                       {"model": mkey, "src": src, "sid": sid, "h": have[sid][0], "v": packed}))
        store_put_many("emb", rows)
  wanted = {sid for sid, _ in items}
  return {sid: _vunpack(v) for sid, (h, v) in have.items() if sid in wanted}


def meaning_scores(query: str, src: str, items: list) -> dict:
  """How close in meaning each (id, text) item is to the query: {id: 0..1}. {} when meaning search isn't available."""
  if not str(query or "").strip() or not items:
    return {}
  try:
    vecs = ensure_vectors(src, items)
    if not vecs:
      return {}
    q = _query_vec(embed_model_key(), str(query)[:2000])
  except Exception as e:
    if not _embed_state().get("warned"):
      _embed_state()["warned"] = True
      log_problem("ai", "Meaning search", str(e))
    return {}
  return {sid: float(np.dot(v[:len(q)], q[:len(v)])) for sid, v in vecs.items()}


def note_text(e: dict) -> str:
  return f"{e.get('topic', '')} ({e.get('type', '')}; applies to {e.get('applies_to') or 'All'}): {e.get('rule', '')}"


def video_parts(refs: list) -> list:
  return [{"file_data": {"mime_type": v["mime"], "file_uri": v["uri"]}} for v in refs or [] if v.get("uri")]


def ask_gemini(prompt: str) -> str:
  try:
    return gemini([{"text": prompt}])
  except AIError as e:
    return f"⚠️ {e}"


def ask_perplexity(prompt: str, effort: str = "low", timeout: int = 60) -> str:
  """Perplexity's search agent. effort = how deep it digs: "low" (a few searches, quick) · "medium" (chains many
  searches across sources) · "high" (deep and slow)."""
  key = secret("PERPLEXITY_API_KEY")
  if not key:
    return "⚠️ PERPLEXITY_API_KEY is not configured in Streamlit Secrets."
  def post(field: str):
    return http().post("https://api.perplexity.ai/v1/responses", timeout=timeout,
                       headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                       json={field: effort, "input": prompt})
  try:
    res = post("effort")
    if res.status_code in (400, 422):   # an older version of their API calls this setting "preset"
      res = post("preset")
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


# --- AI TEAM: who does what ---
# 🌐 Perplexity   web research (TSBs, recalls, known fixes) — built for live search with sources. Backup: ChatGPT web search.
# ✨ Gemini       the eyes and ears: watches videos, listens to voice, reads PDFs and scan-tool screens; first draft.
# 💬 ChatGPT      an independent second diagnosis (it sees the photos too); backup for the final check and quick answers.
# 🐋 DeepSeek     a third opinion from the text alone — cheap, and it reasons differently from the others.
# 🧠 Claude       the senior tech: checks every draft against the data, writes the final answer; step cards, diagrams, notes.
AI_ROLES = [
    ("🌐 Perplexity", "Searches the web for TSBs, recalls and known fixes", "ChatGPT's web search"),
    ("✨ Gemini", "Watches videos, listens to voice, reads PDFs and your scan tool screen; writes a first draft", "—"),
    ("💬 ChatGPT", "Writes its own diagnosis without seeing the others (it sees your photos too)", "—"),
    ("🐋 DeepSeek", "A third opinion from the text alone", "—"),
    ("🧠 Claude", "The senior tech: checks every draft against the data and writes the final answer; "
                  "also step cards, wiring diagrams, Knowledge notes and the customer write-ups", "ChatGPT, then Gemini"),
]
RESEARCH_BY_GPT = "_Web research by ChatGPT (Perplexity wasn't available)._"


def web_research(vehicle: str, codes: str, symptoms: str, question: str = "", deep: bool = False) -> str:
  """Live web research. Perplexity does it (deep=True chains more searches — used for test plans); if it isn't set up
  or fails, ChatGPT searches the web instead. Returns '' if nobody could."""
  focus = question or f"fault code(s) {codes or 'none'}; symptoms: {symptoms or 'none given'}"
  prompt = f"""Research for a professional auto technician. Vehicle: {vehicle}. Problem: {focus}.
Find from current, reputable sources (manufacturer TSBs and recalls, NHTSA, technician forums like iATN, repair databases):
1. TSBs / recalls / service campaigns that match (give bulletin numbers and what they fix).
2. Known pattern failures for this exact platform and how often they're the cause.
3. Published factory specs relevant to testing (resistance, voltage, pressure, duty cycle, pinouts) if available.
4. Common misdiagnoses or parts that get replaced for nothing.
Be specific to this vehicle, list sources, and say clearly when something could not be confirmed."""
  out = ""
  if secret("PERPLEXITY_API_KEY"):
    out = ask_perplexity(prompt, "medium" if deep else "low", 100 if deep else 60)
    if deep and out.startswith("⚠️"):   # the deeper search failed or ran out of time: one quick search instead
      out = ask_perplexity(prompt, "low", 45)
    if out.startswith("⚠️") or out == "No response text received.":
      log_problem("ai", "Perplexity web research", out)
      out = ""
  if not out and has_openai():
    try:
      out = RESEARCH_BY_GPT + "\n\n" + chatgpt(prompt, max_tokens=6000, timeout=150, effort="low", web=True)
    except AIError:
      out = ""
  return out


# How every AI on the team is told to reason through a diagnosis (added to the drafts and to the final check)
DIAG_THINK = """

HOW TO THINK IT THROUGH (do this before you write; show the result, not the scratch work):
1. Evidence first. List what was actually MEASURED or read (codes and what sets them, freeze frame, live data, test
   results) apart from what is only assumed or reported by the customer.
2. For each likely cause ask: if this were the fault, what would the data show? Does it? Drop every cause the data
   already rules out, and say which reading ruled it out.
3. Rank what's left by how well it explains ALL the evidence (one cause that explains everything beats two that each
   explain half), then by how common it is on this platform.
4. Choose the next test by what it will tell you: the fastest, cheapest test whose result separates the top causes.
   Say what each result would mean.
5. Never condemn a part on a code alone — name the test and the reading that proves it. If the evidence isn't enough
   yet, say so and say exactly what is missing.
(If the question is just a fact or a spec, skip all this and answer it.)
"""


TEAM_RULES = """
WEB RESEARCH (live sources; may contain errors):
{research}

TEAM RULES:
- Use the web research to sharpen your answer: name the TSBs, recalls and pattern failures it found.
- Cross-check it against sound diagnostic logic. If the research conflicts with good practice or the scan data, say so.
- Never invent TSB numbers or specs that aren't in the research or that you aren't sure of.
- Finish with a short "### Team Notes" section: where the web research and your analysis agree or disagree.
"""


# --- When a model name is retired: ask the provider which models this key can use and switch to the closest one ---
_MODEL_GONE = re.compile(r"model[^\n]{0,60}(not[ _](exist|found|available|supported)|does ?n[o']t exist|invalid|deprecated|retired)"
                         r"|(unknown|invalid|unsupported|nonexistent)[ _]model|not_found_error", re.I)


def _model_error(res) -> bool:
  """True only when the provider says the MODEL NAME itself doesn't exist — not for other errors that mention a model."""
  return res is not None and res.status_code in (400, 404) and bool(_MODEL_GONE.search(res.text or ""))


def _pick_model(ids: list[str], wanted: str, prefer: tuple[str, ...]) -> str | None:
  ids = [i for i in ids if i and i != wanted]
  if not ids:
    return None
  fam = next((w for w in ("opus", "sonnet", "haiku", "flash", "chat", "pro", "reasoner") if w in wanted.lower()), None)
  for want in ([fam] if fam else []) + list(prefer):
    hit = [i for i in ids if want in i.lower()]
    if hit:
      return hit[0]   # providers list newest first
  return ids[0]


def claude_model() -> str:
  wanted = secret("CLAUDE_MODEL") or CLAUDE_DEFAULT_MODEL
  return _model_swaps().get(("claude", wanted), wanted)


def _claude_replacement(key: str, wanted: str) -> str | None:
  try:
    r = http().get("https://api.anthropic.com/v1/models", params={"limit": 100}, timeout=15,
                   headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
    ids = [m.get("id", "") for m in (r.json().get("data") or [])] if r.status_code == 200 else []
  except (requests.RequestException, ValueError):
    ids = []
  pick = _pick_model(ids, wanted, ("sonnet", "opus"))
  if pick:
    _model_swaps()[("claude", wanted)] = pick
    log_problem("ai", "Claude model", f"Model '{wanted}' isn't available on your key any more — switched to '{pick}'. "
                                      f"Put CLAUDE_MODEL = \"{pick}\" in Secrets to make it permanent.")
  return pick


# --- Claude (Anthropic) ---
CLAUDE_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_DEFAULT_MODEL = "claude-sonnet-5-5"   # change with CLAUDE_MODEL in Secrets (e.g. claude-opus-5-5)


def has_claude() -> bool:
  return bool(secret("ANTHROPIC_API_KEY"))


def claude_label() -> str:
  m = claude_model()
  return m.replace("claude-", "Claude ").replace("-", " ").title().replace(" 5 5", " 5.5").replace("Claude Claude", "Claude")


def _img_list(image_b64) -> list:
  """One photo (a string) or several (a list) -> list of photos."""
  if isinstance(image_b64, str):
    return [image_b64] if image_b64 else []
  return [x for x in (image_b64 or []) if x]


def claude(prompt: str, *, max_tokens: int = 4000, timeout: int = 120, image_b64="", effort: str | None = "medium") -> str:
  """Ask Claude.
  `effort` (low / medium / high) is Anthropic's setting for how hard the model thinks before answering. Current Claude
  models default to "high", which can spend the whole budget thinking — slow, and sometimes an EMPTY answer. Most jobs
  here run at "medium"; time-critical ones at "low". If the budget still runs out mid-thought, ask once more with a
  bigger budget AND low effort (fast) instead of giving up."""
  key = secret("ANTHROPIC_API_KEY")
  if not key:
    raise AIError("ANTHROPIC_API_KEY is missing from Streamlit Secrets.")
  content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b}}
             for b in _img_list(image_b64)] + [{"type": "text", "text": prompt}]
  tries = [(max_tokens, effort), (min(max(max_tokens * 2, 12000), 32000), "low")]
  why = ""
  model = claude_model()
  for attempt, (budget, eff) in enumerate(tries):
    def post(mdl):
      body = {"model": mdl, "max_tokens": budget, "messages": [{"role": "user", "content": content}]}
      if eff and not _model_swaps().get(("no_effort", mdl)):
        body["output_config"] = {"effort": eff}
      return http().post(CLAUDE_URL, timeout=timeout if attempt == 0 else max(timeout, 180), json=body,
                         headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
      res = post(model)
      if _model_error(res):   # model name retired -> find what this key can use and try once more
        alt = _claude_replacement(key, model)
        if alt:
          model = alt
          res = post(model)
      if res.status_code == 400 and re.search(r"effort|output_config", res.text or "", re.I):
        _model_swaps()[("no_effort", model)] = True   # this model doesn't take the effort setting: ask without it
        res = post(model)
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
    why = f"stop_reason={stop}, blocks={','.join(kinds)}, max_tokens={budget}, effort={eff or 'default'}"
    if stop == "refusal":
      raise AIError(f"Claude declined to answer this request ({why}).")
    if stop != "max_tokens" or attempt == len(tries) - 1:
      break
    log_problem("ai", "Claude", f"Empty answer — thinking used the whole budget ({why}). Retrying with "
                               f"{tries[attempt + 1][0]} tokens at low effort.")
  raise AIError(f"Claude returned an empty answer ({why}).")


# --- DeepSeek (second independent draft) ---
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_DEFAULT_MODEL = "deepseek-flash"   # change with DEEPSEEK_MODEL in Secrets (e.g. deepseek-v4-pro)


def has_deepseek() -> bool:
  return bool(secret("DEEPSEEK_API_KEY"))


def deepseek_label() -> str:
  m = deepseek_model()
  return m.replace("deepseek-", "DeepSeek ").replace("-", " ").replace("v4", "V4").title().replace("Deepseek", "DeepSeek").replace("V4 ", "V4 ")


def deepseek_model() -> str:
  wanted = secret("DEEPSEEK_MODEL") or DEEPSEEK_DEFAULT_MODEL
  return _model_swaps().get(("deepseek", wanted), wanted)


def _deepseek_replacement(key: str, session: requests.Session, wanted: str) -> str | None:
  """Thread-safe (no Streamlit calls): ask DeepSeek which models this key can use."""
  try:
    r = session.get("https://api.deepseek.com/models", headers={"Authorization": f"Bearer {key}"}, timeout=15)
    ids = [m.get("id", "") for m in (r.json().get("data") or [])] if r.status_code == 200 else []
  except (requests.RequestException, ValueError):
    ids = []
  return _pick_model(ids, wanted, ("flash", "chat"))


def _deepseek_raw(key: str, model: str, session: requests.Session, prompt: str, max_tokens: int, timeout: int,
                  swaps: dict | None = None, think: bool = False) -> str:
  """No Streamlit calls in here, so it is safe to run in a background thread.
  DeepSeek "thinks" by default, and the thinking counts against max_tokens — on a small budget it can use the whole
  thing and return an EMPTY answer. think=False (quick jobs) switches thinking off. think=True (a full diagnosis)
  lets it reason, with a budget big enough for the thinking AND the answer; if the answer still comes back empty,
  it is asked once more without thinking."""
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
  off, budget0 = not think, (max(max_tokens, 16000) if think else max_tokens)
  res = call(off, budget0)
  if _model_error(res) and "think" not in res.text.lower():   # model name retired -> switch to one this key has
    alt = _deepseek_replacement(key, session, model)
    if alt:
      if swaps is not None:
        swaps[("deepseek", model)] = alt
        swaps["_deepseek_note"] = (model, alt)
      model = alt
      res = call(off, budget0)
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
    res = call(False, max(max_tokens * 3, 12000)) if off else call(True, max_tokens)   # thinking ate the budget
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
    return _deepseek_raw(key, deepseek_model(), http(), prompt, max_tokens, timeout, _model_swaps())
  except RuntimeError as e:
    raise AIError(str(e)) from e
  finally:
    _note_deepseek_swap()


def _note_deepseek_swap():
  note = _model_swaps().pop("_deepseek_note", None)
  if note:
    log_problem("ai", "DeepSeek model", f"Model '{note[0]}' isn't available on your key any more — switched to '{note[1]}'. "
                                        f"Put DEEPSEEK_MODEL = \"{note[1]}\" in Secrets to make it permanent.")


# --- ChatGPT (OpenAI): an independent second diagnosis, and the backup for the final check ---
OPENAI_URL = "https://api.openai.com/v1/responses"
OPENAI_MODELS_URL = "https://api.openai.com/v1/models"
OPENAI_DEFAULT_MODEL = "gpt-6.1-sol"   # change with OPENAI_MODEL in Secrets (e.g. gpt-6-astra = their most capable)
_OPENAI_NOT_CHAT = re.compile(r"image|audio|realtime|transcri|tts|whisper|embed|moderat|search|cyber|rosalind|daybreak|"
                              r"codex|live|translate|instruct", re.I)


def has_openai() -> bool:
  return bool(secret("OPENAI_API_KEY"))


def openai_model() -> str:
  wanted = secret("OPENAI_MODEL") or OPENAI_DEFAULT_MODEL
  return _model_swaps().get(("openai", wanted), wanted)


def openai_label() -> str:
  m = re.sub(r"^gpt-", "", openai_model())
  return "ChatGPT " + " ".join(w.upper() if w in ("gpt",) else w.capitalize() for w in m.split("-"))


def _openai_pick(ids: list, wanted: str) -> str | None:
  """The closest model this key can use: same family name first (sol / astra / terra / luna), newest version first."""
  def ver(i):
    m = re.match(r"gpt-(\d+)(?:\.(\d+))?", i)
    return (int(m.group(1)), int(m.group(2) or 0)) if m else (0, 0)
  ids = [i for i in ids if i and i != wanted and i.startswith("gpt-") and not _OPENAI_NOT_CHAT.search(i)
         and not re.search(r"\d{4}-\d{2}-\d{2}$", i)]
  if not ids:
    return None
  fam = next((w for w in ("sol", "astra", "terra", "luna", "pro", "mini", "nano") if re.search(rf"\b{w}\b", wanted)), "sol")
  order = [fam] + [w for w in ("sol", "astra", "terra", "luna") if w != fam]
  for want in order:
    hit = sorted((i for i in ids if re.search(rf"\b{want}\b", i)), key=ver, reverse=True)
    if hit:
      return hit[0]
  return sorted(ids, key=ver, reverse=True)[0]


def _openai_replacement(key: str, session: requests.Session, wanted: str) -> str | None:
  """Thread-safe (no Streamlit calls): ask OpenAI which models this key can use."""
  try:
    r = session.get(OPENAI_MODELS_URL, headers={"Authorization": f"Bearer {key}"}, timeout=15)
    ids = [m.get("id", "") for m in (r.json().get("data") or [])] if r.status_code == 200 else []
  except (requests.RequestException, ValueError):
    ids = []
  return _openai_pick(ids, wanted)


def _openai_raw(key: str, model: str, session: requests.Session, prompt: str, max_tokens: int, timeout: int,
                images: list | None = None, effort: str | None = "medium", web: bool = False,
                swaps: dict | None = None) -> str:
  """One question to ChatGPT (OpenAI's Responses API). No Streamlit calls in here, so it is safe in a background thread.
  effort = how hard it reasons (low / medium / high). The reasoning counts against max_tokens, so if the answer comes
  back empty because the thinking used the whole budget, it is asked once more with a bigger budget at low effort.
  web=True lets it search the web. A setting this model doesn't take is dropped and the question is asked again."""
  content = [{"type": "input_text", "text": prompt}] + [
      {"type": "input_image", "image_url": "data:image/jpeg;base64," + b} for b in (images or []) if b]
  drop = set()
  def call(mdl: str, eff: str | None, budget: int):
    body = {"model": mdl, "input": [{"role": "user", "content": content}], "max_output_tokens": budget, "store": False}
    if eff:
      body["reasoning"] = {"effort": eff}
    if web:
      body["tools"] = [{"type": "web_search"}]
    for k in drop:
      body.pop(k, None)
    try:
      return session.post(OPENAI_URL, timeout=timeout, json=body,
                          headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    except requests.RequestException as e:
      raise RuntimeError(f"ChatGPT connection error: {e}") from e
  def ask(eff: str | None, budget: int):
    nonlocal model
    res = call(model, eff, budget)
    if _model_error(res) or (res.status_code in (400, 404) and "model_not_found" in (res.text or "")):
      alt = _openai_replacement(key, session, model)   # model name retired -> switch to one this key has
      if alt:
        if swaps is not None:
          swaps[("openai", model)] = alt
          swaps["_openai_note"] = (model, alt)
        model = alt
        res = call(model, eff, budget)
    for _ in range(3):   # a setting this model doesn't take ("reasoning", "store", ...): drop it and ask again
      m = re.search(r"(?:Unsupported|Unknown|Unrecognized|Invalid)[^'\"]{0,40}(?:parameter|argument|value)[^'\"]{0,20}['\"]([a-z_]+)",
                    res.text or "", re.I) if res.status_code == 400 else None
      if not m or m.group(1) not in ("reasoning", "store", "tools", "max_output_tokens"):
        break
      if m.group(1) == "tools" and web:
        raise RuntimeError(f"ChatGPT model {model} can't search the web.")
      drop.add(m.group(1))
      res = call(model, eff, budget)
    if res.status_code in (429, 500, 502, 503, 504) and "insufficient_quota" not in (res.text or ""):
      time.sleep(2.5)   # busy: one more try
      res = call(model, eff, budget)
    if res.status_code != 200:
      why = res.text[:300]
      if "insufficient_quota" in why:
        why = "the OpenAI account is out of credit (add credit at platform.openai.com → Billing)."
      raise RuntimeError(f"ChatGPT API error ({res.status_code}, {model}): {why}")
    try:
      data = res.json()
      text = "".join(c.get("text", "") for item in (data.get("output") or []) if item.get("type") == "message"
                     for c in (item.get("content") or []) if c.get("type") in ("output_text", "text"))
    except (ValueError, AttributeError) as e:
      raise RuntimeError("ChatGPT returned an unreadable answer.") from e
    return text, data
  text, data = ask(effort, max_tokens)
  if not text.strip() and (data.get("incomplete_details") or {}).get("reason") == "max_output_tokens":
    text, data = ask("low" if effort else None, min(max(max_tokens * 2, 16000), 64000))
  if not text.strip():
    raise RuntimeError(f"ChatGPT returned an empty answer (status={data.get('status')}, "
                       f"reason={(data.get('incomplete_details') or {}).get('reason')}).")
  if data.get("status") == "incomplete":
    text += "\n\n_(ChatGPT's answer hit the length limit and may be cut off.)_"
  return text


def _note_openai_swap():
  note = _model_swaps().pop("_openai_note", None)
  if note:
    log_problem("ai", "ChatGPT model", f"Model '{note[0]}' isn't available on your key any more — switched to '{note[1]}'. "
                                       f"Put OPENAI_MODEL = \"{note[1]}\" in Secrets to make it permanent.")


def chatgpt(prompt: str, *, max_tokens: int = 8000, timeout: int = 150, image_b64="", effort: str | None = "medium",
            web: bool = False) -> str:
  key = secret("OPENAI_API_KEY")
  if not key:
    raise AIError("OPENAI_API_KEY is missing from Streamlit Secrets.")
  try:
    return _openai_raw(key, openai_model(), http(), prompt, max_tokens, timeout, _img_list(image_b64)[:6], effort, web,
                       _model_swaps())
  except RuntimeError as e:
    raise AIError(str(e)) from e
  finally:
    _note_openai_swap()


REVIEW_PROMPT = """You are the senior master technician on a diagnostic team. {writers} each wrote a first-draft answer on their own, without seeing each other's work.
Your job: produce the FINAL answer the technician will follow.

ORIGINAL TASK (vehicle, codes, symptoms, scan data and test results, plus required format):
{task}

WEB RESEARCH (may contain errors):
{research}

{drafts}

INSTRUCTIONS:
- Keep the exact section format the original task requires.
- Work from the EVIDENCE in the task (codes, freeze frame, live data, test results), not from the drafts. Then check every draft against it: keep what the evidence supports, fix what it contradicts, remove generic or irrelevant steps, add important tests or pattern failures they missed.
- Where the drafts disagree, decide by the evidence — not by how many drafts say it. If the evidence can't settle it yet, say so and give the one test that will.
- If photos are attached (scope / meter capture, wiring diagram, connector, part), look at them yourself and check that what the drafts say they show is right. For wiring diagrams, read wire colors, pin numbers and splice/ground locations carefully.
- Your main job is making sure NOTHING IS MISSED: any reading, code, alert or test result in the task that no draft explained, you explain.
- For every cause you keep, say which reading or test points to it; for every cause the data rules out, say which reading rules it out. Never condemn a part on a code alone.
- Order the tests from fastest/cheapest and most likely to least, so the tech doesn't throw parts at it. For each test say what result proves or clears the suspect.
- Never invent TSB numbers or specs; only use ones from the research or that you are sure of.
- End with "### Team Notes": 2-5 bullets on what you changed, and where the drafts and the research disagreed and who was right."""


def final_effort() -> str:
  """How hard Claude thinks on the final check. "high" unless FINAL_CHECK_EFFORT in Secrets says otherwise
  (medium = faster answers, xhigh = slower and deeper)."""
  e = (secret("FINAL_CHECK_EFFORT") or "").strip().lower()
  return e if e in ("low", "medium", "high", "xhigh", "max") else "high"


def team_answer(prompt: str, vehicle: str, codes: str, symptoms: str, use_web: bool, status=None, *,
                question: str = "", image_b64="", fast: bool = False, research: str = "",
                effort: str | None = None, extra_parts: list | None = None) -> tuple[str, str, str, str, dict]:
  """The whole team on one job: the web is searched -> Gemini, ChatGPT and DeepSeek each write their own draft at the
  same time, without seeing each other's -> Claude checks every draft against the data (and the photos) and writes
  the final answer. If Claude can't, ChatGPT does the final check. Steps are skipped if their key isn't set.
  fast=True = short answers (live test drive checks): Gemini + DeepSeek drafts only, low effort.
  Returns (final answer, research, Gemini's draft, DeepSeek's draft, more) — more = {"gpt": ChatGPT's draft,
  "judge": who did the final check}."""
  draft, ds_draft, gpt_draft, gem_err = "", "", "", ""
  imgs = _img_list(image_b64)
  tokens = 900 if fast else 4000
  t0 = time.time()
  if use_web and not research:
    if status:
      status.update(label="🌐 Searching the web for TSBs, recalls and known fixes...")
    research = web_research(vehicle, codes, symptoms, question=question, deep=not question and not fast)
  full = prompt + ("" if fast else DIAG_THINK) + (TEAM_RULES.format(research=research[:6000]) if research else "")
  use_ds, use_gpt = has_deepseek(), has_openai() and not fast
  names = [f"✨ {gemini_label()}"] + ([f"💬 {openai_label()}"] if use_gpt else []) + ([f"🐋 {deepseek_label()}"] if use_ds else [])
  if status:
    status.update(label=(", ".join(names[:-1]) + " and " + names[-1] + " are each" if len(names) > 1 else names[0] + " is")
                  + " working on it" + (" with the web research..." if research else "..."))
  pool = ThreadPoolExecutor(max_workers=2) if (use_ds or use_gpt) else None
  ds_job = gpt_job = None
  if use_ds:   # DeepSeek and ChatGPT run in the background while Gemini works, so they add little or no wait
    ds_prompt = full + ("\n\nNOTE: the technician attached photo(s), a video or a PDF that you cannot see. "
                        "Work from the text (and the VIDEO REPORT / PDF REPORT, if there is one); another technician is "
                        "looking at them." if imgs or extra_parts else "")
    # its own connection: the shared one isn't guaranteed safe while Gemini uses it at the same time
    ds_job = pool.submit(_deepseek_raw, secret("DEEPSEEK_API_KEY"), deepseek_model(), requests.Session(),
                         ds_prompt, tokens, 60 if fast else 150, _model_swaps(), not fast)
  if use_gpt:
    gpt_prompt = full + ("\n\nNOTE: the technician attached a video or PDF that you cannot open. Work from the VIDEO "
                         "REPORT / PDF REPORT in the task; another technician is looking at the file itself."
                         if extra_parts else "")
    gpt_job = pool.submit(_openai_raw, secret("OPENAI_API_KEY"), openai_model(), requests.Session(), gpt_prompt,
                          12000, 150, imgs[:6], "medium", False, _model_swaps())
  try:
    parts = [{"text": full}] + [{"inline_data": {"mime_type": "image/jpeg", "data": b}} for b in imgs] + (extra_parts or [])
    draft = gemini(parts, timeout=45 if fast else (180 if extra_parts else 120), think="low" if fast else "high")
  except AIError as e:
    gem_err = str(e)
  deadline = t0 + (75 if fast else 200)   # nobody holds the answer up for long: a draft that isn't in by then is skipped
  if gpt_job:
    try:
      gpt_draft = gpt_job.result(timeout=max(5, deadline - time.time()))
    except Exception as e:
      log_problem("ai", "ChatGPT draft", str(e) or "took too long")
    _note_openai_swap()
  if ds_job:
    try:   # with two drafts already in, the third opinion gets a short grace period, not the whole wait
      ds_draft = ds_job.result(timeout=max(5, min(deadline - time.time(), 30 if (draft and gpt_draft) else 999)))
    except Exception as e:
      log_problem("ai", "DeepSeek draft", str(e) or "took too long — the others didn't wait for it")
    _note_deepseek_swap()
  if pool:
    pool.shutdown(wait=False)
  more = {"gpt": gpt_draft, "judge": ""}
  have = [x for x in (("Gemini", draft), ("ChatGPT", gpt_draft), ("DeepSeek", ds_draft)) if x[1]]
  blocks = []
  for who, text in (("GEMINI", draft), ("CHATGPT", gpt_draft), ("DEEPSEEK", ds_draft)):
    if who == "CHATGPT" and not use_gpt:
      continue
    if who == "DEEPSEEK" and not use_ds:
      continue
    sees = {"GEMINI": "saw the photos / video / PDF itself" if (imgs or extra_parts) else "",
            "CHATGPT": "saw the photos" if imgs else "",
            "DEEPSEEK": "text only — it could not see the photos or files" if (imgs or extra_parts) else ""}[who]
    blocks.append(f"{who}'S DRAFT" + (f" ({sees})" if sees else "") + ":\n" + (text or f"({who.title()} draft unavailable)"))
  review = REVIEW_PROMPT.format(task=prompt, research=research[:6000] or "none", drafts="\n\n".join(blocks),
                                writers=" and ".join(", ".join(n for n, _ in have).rsplit(", ", 1)) or "The other AIs") \
      + ("\n\nKeep the final answer SHORT (the tech is driving): under 120 words, then 1-2 Team Notes bullets." if fast else "")
  why = ""
  if has_claude():
    if status:
      status.update(label=f"🧠 {claude_label()} is checking everyone's work against the data so nothing is missed...")
    try:
      final = claude(review, max_tokens=4000 if fast else 32000, timeout=60 if fast else 240, image_b64=image_b64,
                     effort=effort or ("low" if fast else final_effort()))
      more["judge"] = "claude"
      return final, research, draft, ds_draft, more
    except AIError as e:
      why = str(e)
  if has_openai() and not (len(have) == 1 and gpt_draft):   # Claude couldn't (or isn't set up): ChatGPT checks
    if status:
      status.update(label=f"💬 {openai_label()} is doing the final check...")
    try:
      final = chatgpt(review, max_tokens=6000 if fast else 24000, timeout=60 if fast else 200, image_b64=imgs[:6],
                      effort="low" if fast else "high")
      more["judge"] = "chatgpt"
      return final + (f"\n\n_⚠️ Claude wasn't available ({why}) — ChatGPT did the final check._" if why else ""), \
          research, draft, ds_draft, more
    except AIError as e:
      why = why or str(e)
  best = draft or gpt_draft or ds_draft
  if best:
    note = f"\n\n_⚠️ Final check unavailable: {why}_" if why else (f"\n\n_⚠️ Gemini failed: {gem_err}_" if gem_err and not draft else "")
    # only the draft that is shown counts as "who answered"
    return best + note, research, "", (ds_draft if best is ds_draft else ""), {"gpt": gpt_draft if best is gpt_draft else "",
                                                                                "judge": "", "solo": "gemini" if best is draft else ""}
  return (f"⚠️ Gemini failed ({gem_err}). Showing the web research instead:\n\n{research}" if research else f"⚠️ {gem_err}"), \
      research, "", "", more


def team_names(draft: str, ds_draft: str, research: str, more: dict | None = None) -> str:
  """Who worked on an answer, for the small line under it."""
  more = more or {}
  judge = more.get("judge", "claude" if (draft or ds_draft) and has_claude() else "")
  return " + ".join(x for x in [
      ("🌐 ChatGPT web search" if research.startswith(RESEARCH_BY_GPT) else "🌐 Perplexity") if research else "",
      "✨ " + gemini_label() if draft or more.get("solo") == "gemini" or (not judge and not ds_draft and not more.get("gpt")) else "",
      "💬 " + openai_label() if more.get("gpt") else "",
      "🐋 " + deepseek_label() if ds_draft else "",
      "🧠 " + claude_label() if judge == "claude" else ("🧠 " + openai_label() + " (final check)" if judge == "chatgpt" else ""),
  ] if x)


def quick_ai(prompt: str, image_b64="", max_tokens: int = 4000, effort: str = "low") -> tuple[str, str]:
  """One AI, one answer: Claude if its key is set, then ChatGPT, then Gemini. Returns (answer, who answered)."""
  if has_claude():
    try:
      return claude(prompt, max_tokens=max_tokens, timeout=90, image_b64=image_b64, effort=effort), "🧠 " + claude_label()
    except AIError:
      pass   # fall through
  if has_openai():
    try:
      return chatgpt(prompt, max_tokens=max(max_tokens, 6000), timeout=90, image_b64=image_b64, effort=effort), \
          "💬 " + openai_label()
    except AIError:
      pass
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
                 json_mode=True, timeout=40, think="low")
    reads["Gemini"] = [c for v in (json.loads(raw).get("vins") or []) for c in clean_vin_text(str(v))]
  except (AIError, ValueError, AttributeError):
    pass
  if has_claude():
    try:
      txt = claude(VIN_READ_PROMPT, max_tokens=3000, timeout=60, image_b64=_jpeg_b64(img, 1568), effort="low")
      obj = find_json(txt, dict)
      vins = (obj or {}).get("vins", []) or []
      reads["Claude"] = [c for v in vins for c in clean_vin_text(str(v))]
    except AIError:
      pass   # already in the problem log
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
    ok_cd = vin_check_digit_ok(c)
    ok_db = ok_cd and nhtsa_ok(c)   # NHTSA always rejects a bad check digit, so don't wait on it for those
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
    return json.loads(gemini([{"text": ask}, img_part(img)], json_mode=True, timeout=25, think="low"))
  except (AIError, ValueError):
    if not has_claude():
      raise
  # Gemini failed (quota, outage, bad answer): let Claude read it instead
  txt = claude(ask + " Reply with the JSON only.", max_tokens=3000, timeout=60, image_b64=img_part(img)["inline_data"]["data"],
               effort="low")
  obj = find_json(txt, dict)
  if obj is None:
    raise ValueError("No customer details found in the AI's answer.")
  return obj


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
OBDB_MAKE_NAMES = {"GMC": "GMC", "BMW": "BMW", "MINI": "MINI", "MERCEDES-BENZ": "Mercedes-Benz", "LAND ROVER": "Land-Rover",
                   "INFINITI": "INFINITI", "ALFA ROMEO": "Alfa-Romeo", "FIAT": "Fiat", "MG": "MG", "BYD": "BYD", "RAM": "Ram",
                   "ROLLS-ROYCE": "Rolls-Royce", "SMART": "smart"}
OBDB_SKIP_PATHS = {"Trips", "Seatbelts", "Lights", "Doors", "Clocks", "Details", "Stats", "DTCs", "ECU", "Cruise control"}
OBDB_UNITS = {
    "celsius": "C", "fahrenheit": "F", "kilopascal": "kPa", "psi": "psi", "bars": "bar", "volts": "V", "millivolts": "mV",
    "rpm": "rpm", "percent": "%", "degrees": "deg", "scalar": "", "unknown": "", "kilometersPerHour": "kph",
    "kilometers": "km", "miles": "mi", "offon": "onoff", "onoff": "onoff", "noyes": "yesno", "yesno": "yesno",
    "milliseconds": "ms", "seconds": "s", "minutes": "min", "hours": "h", "milliamps": "mA", "amps": "A",
    "gramsPerSecond": "g/s", "newtonMeters": "Nm", "liters": "L", "hex": "hex", "metersPerSecondSquared": "m/s²",
    "litersPerHour": "L/h", "kilowattHours": "kWh",
    "gravity": "g", "ampereHours": "Ah", "kilowatts": "kW", "millimeters": "mm", "megaohms": "MΩ",
}


def _obdb_repo_candidates(make: str, model: str) -> list[str]:
  mk = OBDB_MAKE_NAMES.get(make.upper(), make.title().replace(" ", "-"))
  mdl = model.strip()
  cands = [mdl.replace(" ", "-"), mdl.split(" ")[0]]
  if mdl.split(" ")[0] in ("Silverado", "Sierra"):
    cands.append(mdl.split(" ")[0] + "-1500")
  # last: the make's own master list (every factory request known for the make) when there is no list for this model
  return list(dict.fromkeys([f"{mk}-{c}" for c in cands if c] + [mk]))


def _year_ok(f: dict | None, year: int) -> bool:
  if not f or not year:
    return True
  if year in (f.get("years") or []):
    return True
  if "from" not in f and "to" not in f:
    return not f.get("years")
  return f.get("from", 0) <= year <= f.get("to", 9999)


OBDB_SAFE_SESSIONS = {"03", "C0"}   # extended diagnostic session / Nissan's: what every scan tool opens to read data


def obdb_parse(cmds: list, year: int) -> list[dict]:
  """One OBDb list -> the readings the scanner can ask for. Reads only (service 21 / 22). Left out: BMW-style extended
  addressing and K-line requests (this adapter path can't do them), and requests needing an unusual diagnostic session."""
  out = []
  for c in cmds or []:
    hdr, rax = str(c.get("hdr", "")).upper(), str(c.get("rax", "")).upper()
    if c.get("eax") or c.get("proto") or c.get("baud") or c.get("init"):
      continue
    if not (re.fullmatch(r"[0-9A-F]{3}", hdr) or (re.fullmatch(r"[0-9A-F]{4}", hdr) and (hdr.startswith("DA") or len(rax) >= 6))):
      continue
    din = str(c.get("din") or "").upper()
    if din and din not in OBDB_SAFE_SESSIONS:
      continue
    if not _year_ok(c.get("filter"), year):
      continue
    svc, pid = next(iter((c.get("cmd") or {}).items()), ("", ""))
    if svc not in ("21", "22"):
      continue
    ext = len(hdr) == 4
    extra = {}
    if ext and c.get("pri"):
      extra["pri"] = str(c["pri"]).upper()   # 29-bit priority byte (14 on newer GM, 17 VW group, 1D Volvo / Mazda)
    if ext and c.get("tst"):
      extra["tst"] = str(c["tst"]).upper()   # tester address when it isn't F1
    if din:
      extra["din"] = din
      if c.get("dout"):
        extra["dout"] = str(c["dout"]).upper()
    for sig in c.get("signals", []):
      f = sig.get("fmt", {})
      if sig.get("path") in OBDB_SKIP_PATHS or not f.get("len") or f.get("len") > 32:
        continue
      out.append({
          "hdr": hdr, "rax": rax, "req": f"{svc}{pid}".upper(),
          "bix": f.get("bix", 0), "len": f["len"], "mul": f.get("mul", 1), "div": f.get("div", 1), "add": f.get("add", 0),
          "sign": bool(f.get("sign")), "lsb": bool(f.get("blsb")), "unit": OBDB_UNITS.get(f.get("unit", ""), f.get("unit", "")),
          "min": f.get("min"), "max": f.get("max"), "nmin": f.get("nullmin"), "nmax": f.get("nullmax"),
          "map": {k: (v.get("description") or v.get("value")) if isinstance(v, dict) else v for k, v in f["map"].items()} if f.get("map") else None,
          "name": sig.get("name", sig.get("id", "")), "path": sig.get("path", ""), **extra,
      })
  return out


@st.cache_data(ttl=86400, show_spinner=False, max_entries=200)
def obdb_signals(make: str, model: str, year: str) -> tuple[str, list[dict]]:
  """Download this exact model's factory data definitions (one small JSON file) and trim it for the scanner. If the
  database has no list for the model, the make's master list is used instead."""
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
    out = obdb_parse(cmds, y)
    if out:
      return repo, out
  return "", []


def learned_key(vd: dict) -> str:
  """Year + make + model + engine size: cars that match share what 🔎 Find every reading learned."""
  y, mk, md = (str(vd.get(k) or "").strip() for k in ("Model Year", "Make", "Model"))
  if not (y and mk and md):
    return ""
  eng = re.search(r"\d+(\.\d+)?", str(vd.get("Displacement (L)") or vd.get("Engine") or ""))
  return re.sub(r"[^a-z0-9]+", "-", f"{y} {mk} {md} {eng.group(0) if eng else ''}".lower()).strip("-")


def learned_readings(vd: dict) -> dict:
  k = learned_key(vd)
  if not k:
    return {}
  cache = ss.setdefault("_learned", {})
  if k not in cache:
    cache[k] = store_get("oemmap", k) or {}
  return cache[k]


def save_learned(ev: dict):
  """🔎 Find every reading finished: keep every factory request this car answered, merged with what was learned before."""
  vd = ss.vehicle_details or {}
  k = learned_key(vd)
  new = [g for g in (ev.get("sigs") or []) if isinstance(g, dict) and g.get("req") and g.get("hdr")]
  if not k:
    ss._toast = "Set the vehicle first (VIN search) so the readings it found can be saved for this car."
    return
  if not new and not ev.get("complete"):
    return
  old = learned_readings(vd)
  key = lambda g: (g.get("hdr"), g.get("rax", ""), g.get("req"), g.get("pri", ""), g.get("tst", ""))
  keys = {key(g) for g in new}
  merged = [g for g in (old.get("sigs") or []) if key(g) not in keys and not str(g.get("req", "")).startswith("01")] + new
  rec = {"vehicle": ss.vehicle_info, "vin": ss.active_vin, "sigs": merged[:6000], "lid": str(ev.get("id") or ""),
         "requests": len({key(g) for g in merged}), "readings": len(merged), "tech": ss.get("tech_user") or "",
         "at": datetime.now().strftime("%Y-%m-%d %I:%M %p"),
         # ver = the whole search finished on this kind of car (so it isn't run again on the next connect)
         "ver": int(ev.get("ver") or 0) if ev.get("complete") else int(old.get("ver") or 0),
         "checked": int(ev.get("checked") or 0)}
  store_put("oemmap", k, rec)
  ss.setdefault("_learned", {})[k] = rec
  if new:
    ss._toast = (f"🔎 Learned {int(ev.get('found') or len(new))} factory readings for this {ss.vehicle_info or 'car'} — "
                 "saved, so next time they show up right away")


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


def camera_shot(label: str, key: str):
  """Streamlit's in-page camera, asking for 1080p so text on a page is readable (older Streamlit: its default size)."""
  try:
    return st.camera_input(label, key=key, resolution="1080p")
  except TypeError:
    return st.camera_input(label, key=key)


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
    "crank_sig": "Crankshaft sensor (CKP)",
    "cam_in": "Camshaft sensor — INTAKE (green)",
    "cam_ex": "Camshaft sensor — EXHAUST (red)",
    "rel_comp": "Relative compression (starter current, cranking)",
    "px_cyl": "Pressure transducer — in cylinder",
    "px_intake": "Pressure transducer — intake / vacuum",
    "px_exhaust": "Pressure transducer — exhaust / tailpipe",
}
WAVE_COLORS = {"cam_in": "#22C55E", "cam_ex": "#EF4444"}   # shop standard: green = intake cam, red = exhaust cam
WAVE_UNITS = {"sec_ign": "kV", "pri_ign": "V", "coil_amp": "A", "inj_v": "V", "inj_amp": "A", "crank_sig": "V",
              "cam_in": "V", "cam_ex": "V",
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
  enc = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"
  # Only the first part of the file is read as text (to find the format and header). The numbers are loaded straight
  # from the file further down, so a 50 MB PicoScope export isn't copied around in memory several times.
  HEAD = 600_000
  head = raw[:HEAD].decode(enc, errors="replace")
  lines = [ln.strip() for ln in head.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
  if len(raw) > HEAD:
    lines = lines[:-1]   # the last line of the sample may be cut in half
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
    rows = [split(ln, chosen) for ln in lines[:start + 3]]   # header area only
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
    df = pd.read_csv(io.BytesIO(raw), sep=chosen, header=None, skiprows=start, skip_blank_lines=False,
                     encoding=enc, decimal="," if chosen != "," else ".", usecols=list(range(width)),
                     na_values=["∞", "-∞", "+∞", "inf", "-inf", "NaN"], keep_default_na=True, engine="c",
                     on_bad_lines="skip")
    df = df.apply(pd.to_numeric, errors="coerce").dropna(how="all")
    if df.shape[1] == width and len(df) >= 20:
      data = df.to_numpy(dtype=float)
  except Exception:
    data = None
  if data is None:   # fallback: read the whole file the slow, exact way
    full = raw.decode(enc, errors="replace").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    rr = (split(ln.strip(), chosen) for ln in full[start:])
    data = np.array([[_num(v) for v in r] for r in rr if len(r) == width and _is_num_row(r)], dtype=float)
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
  # square-ish sensor signal: many teeth with a missing-tooth gap = crank; a handful of edges = cam
  if hi - lo > 1.0:
    mid, h = (hi + lo) / 2, (hi - lo) * 0.15
    e = _edges(y, mid + h, mid - h)
    if len(e) >= 30:
      iv = np.diff(e).astype(float)
      if np.any(iv > 1.6 * np.median(iv)):
        return "crank_sig"
    elif 2 <= len(e) <= 40:
      return "cam_in"
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


def _crank_sig(t, y, dt, rpm_hint=None):
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
    miss = [max(1, int(round(float(r))) - 1) for r in ratio[gaps]]
    m["missing_teeth_at_gap"] = int(np.median(miss))
    if len(gaps) >= 2:
      between = [int(x) for x in np.diff(gaps)]   # tooth pitches from one gap to the next
      # one revolution = the smallest group of gaps that repeats. 36-1 / 60-2: every gap. 36-2-2-2 style: groups of
      # unevenly spaced gaps. Only trust a group size we actually see repeat in this capture.
      period = None
      for p in range(1, 5):
        if len(between) >= p + 1 and all(abs(between[i] - between[i + p]) <= 1 for i in range(len(between) - p)):
          period = p
          break
      if period is None:
        notes.append("Gaps are unevenly spaced (a wheel with several gaps per turn). Capture at least two full turns "
                     "so the app can work out the pattern and RPM.")
      else:
        pitches = sum(between[:period]) + sum(miss[:period])
        per_rev = period
        rev_s = float(np.median([t[e[gaps[i + period]]] - t[e[gaps[i]]] for i in range(len(gaps) - period)]))
        rpm_w = 60 / rev_s if rev_s > 0 else None
        # evenly spaced gaps look exactly like a smaller one-gap wheel: use the RPM the tech entered to tell them apart
        if rpm_w and rpm_hint and rpm_hint > 0:
          k = rpm_w / rpm_hint
          if round(k) >= 2 and abs(k - round(k)) < 0.15 * round(k):
            per_rev = period * int(round(k))
            pitches *= int(round(k))
            rpm_w /= round(k)
            notes.append(f"Matched to the {int(rpm_hint)} RPM you entered: this wheel has {per_rev} gaps per turn.")
        gap_list = (miss[:period] * (per_rev // period))[:per_rev]
        m["pattern"] = f"{pitches}-" + "-".join(str(x) for x in gap_list)
        m["gaps_per_rev"] = per_rev
        m["rpm_from_wheel"] = _r(rpm_w, 0) if rpm_w else None
        if pitches < 30 and per_rev == 1 and not rpm_hint:
          notes.append(f"Reads as a {m['pattern']} wheel. If this wheel actually has more than one gap per turn, enter "
                       "the engine RPM above and the app will correct the pattern and RPM.")
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


def _cam(t, y, dt):
  hi, lo = float(np.nanpercentile(y, 99)), float(np.nanpercentile(y, 1))
  mid, h = (hi + lo) / 2, (hi - lo) * 0.15
  up, down = _edges(y, mid + h, mid - h), _edges(-y, -(mid - h), -(mid + h))
  m = {"rising_edges": int(len(up)), "falling_edges": int(len(down)), "low_level_v": _r(lo), "high_level_v": _r(hi)}
  notes = []
  if lo > 0.8 and hi < 15:
    notes.append(f"Cam signal never goes fully low (lowest {_r(lo)} V): check the sensor ground and signal circuit.")
  if len(up) < 2:
    notes.append("Too few cam edges — capture at least two full engine cycles (four crank turns is best).")
  return m, [], notes


def _crank_sync(t, y):
  """Crank teeth + where each turn starts (first tooth after the missing-tooth gap). Single-gap wheels only."""
  hi, lo = float(np.nanpercentile(y, 98)), float(np.nanpercentile(y, 2))
  mid, h = (hi + lo) / 2, (hi - lo) * 0.15
  e = _edges(y, mid + h, mid - h)
  if len(e) < 20:
    return None, "Too few crank teeth to find the sync gap."
  iv = np.diff(t[e])
  ref = np.array([np.median(iv[max(0, i - 6): i + 7]) for i in range(len(iv))])
  ratio = iv / ref
  gaps = np.where(ratio > 1.6)[0]
  if len(gaps) < 2:
    return None, "Need at least one full crank turn (two missing-tooth gaps) in the capture to measure cam timing."
  between = np.diff(gaps)
  if np.any(np.abs(between - np.median(between)) > 1):
    return None, "Cam timing needs a crank wheel with one gap per turn (like 60-2 or 36-1); this wheel has several."
  miss = max(1, int(round(float(np.median(ratio[gaps])))) - 1)
  pitches = int(np.median(between)) + miss
  return {"e": e, "gaps": gaps, "miss": miss, "pitch_deg": 360.0 / pitches, "pattern": f"{pitches}-{miss}"}, ""


def cam_crank_angles(t, crank_y, cam_y) -> tuple[dict, list[str]]:
  """Where every cam edge lands in CRANK degrees after the crank's missing-tooth gap — the cam/crank correlation
  check (P0016-P0019, P0340s, VVT, timing chain stretch). Counts teeth, so normal speed wobble doesn't skew it."""
  sync, why = _crank_sync(t, crank_y)
  if not sync:
    return {}, [why]
  e, gaps, miss, pd_ = sync["e"], sync["gaps"], sync["miss"], sync["pitch_deg"]
  te = t[e]
  gap_set = set(int(g) for g in gaps)
  # angle of every crank edge (0 deg = first tooth after the gap); None before the first sync
  ang = np.full(len(e), np.nan)
  cur = None
  for j in range(len(e)):
    if (j - 1) in gap_set:
      cur = 0.0
    elif cur is not None:
      cur += pd_
    ang[j] = np.nan if cur is None else cur
  def where(tc):
    j = int(np.searchsorted(te, tc) - 1)
    if j < 0 or j >= len(e) - 1 or np.isnan(ang[j]):
      return None
    span = (miss + 1) * pd_ if j in gap_set else pd_
    return (ang[j] + (tc - te[j]) / (te[j + 1] - te[j]) * span) % 360.0
  hi, lo = float(np.nanpercentile(cam_y, 99)), float(np.nanpercentile(cam_y, 1))
  mid, h = (hi + lo) / 2, (hi - lo) * 0.15
  out, notes = {"crank_wheel": sync["pattern"]}, []
  for name, idx in (("rising", _edges(cam_y, mid + h, mid - h)), ("falling", _edges(-cam_y, -(mid - h), -(mid + h)))):
    angles = sorted(a for a in (where(t[i]) for i in idx) if a is not None)
    clusters = []
    for a in angles:   # the same cam edge lands at the same crank angle every other turn: group them
      if clusters and min(abs(a - clusters[-1][-1]), 360 - abs(a - clusters[-1][-1])) <= 8:
        clusters[-1].append(a)
      else:
        clusters.append([a])
    if len(clusters) > 1 and min(abs(clusters[0][0] - clusters[-1][-1]), 360 - abs(clusters[0][0] - clusters[-1][-1])) <= 8:
      clusters[0] = clusters.pop() + clusters[0]   # wraps around 0/360
    for k, c in enumerate(clusters[:6]):
      c = np.array(c)
      mean = float(np.degrees(np.arctan2(np.mean(np.sin(np.radians(c))), np.mean(np.cos(np.radians(c)))))) % 360
      spread = float(max(min(abs(x - mean), 360 - abs(x - mean)) for x in c))
      out[f"{name}_edge_{k + 1}_deg"] = _r(mean, 1)
      out[f"{name}_edge_{k + 1}_wobble_deg"] = _r(spread, 1)
      if spread > 3:
        notes.append(f"Cam {name} edge {k + 1} moves ±{_r(spread, 1)}° between turns — cam phaser moving, chain/belt "
                     "slack, or a noisy signal. At a steady idle it should hold within about ±1–2°.")
  if not any(k.endswith("_deg") and "wobble" not in k for k in out):
    notes.append("No cam edges fell inside a full crank turn — capture a longer stretch.")
  else:
    notes.append("Angles are crank degrees after the first tooth past the missing-tooth gap. Compare them with a saved "
                 "known-good capture of the same engine (or the factory correlation spec): a few degrees off on "
                 "both cams = stretched chain/jumped timing; one cam off = that cam's phaser, sprocket or sensor.")
  return out, notes


def measure_channel(t, y, dt, wtype: str, cyl: int | None = None, rpm_hint: float | None = None) -> dict:
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
      m, ev, notes = _crank_sig(t, y, dt, rpm_hint)
    elif wtype in ("cam_in", "cam_ex"):
      m, ev, notes = _cam(t, y, dt)
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


@st.cache_data(ttl=86400, show_spinner=False, max_entries=300)
def nhtsa_complaints(make: str, model: str, year: str) -> list[dict]:
  """Owner complaints filed with NHTSA for this year / make / model (components + what the owner wrote)."""
  if not (make and model and str(year).isdigit()):
    return []
  try:
    r = http().get("https://api.nhtsa.gov/complaints/complaintsByVehicle",
                   params={"make": make, "model": model, "modelYear": str(year)}, timeout=12)
    r.raise_for_status()
    return [{"components": str(x.get("components") or ""), "summary": str(x.get("summary") or ""),
             "date": str(x.get("dateOfIncident") or ""), "crash": bool(x.get("crash")), "fire": bool(x.get("fire"))}
            for x in (r.json().get("results") or [])]
  except (requests.RequestException, ValueError):
    return []


def vehicle_complaints() -> list[dict]:
  vd = ss.vehicle_details or {}
  return nhtsa_complaints(str(vd.get("Make", "")), str(vd.get("Model", "")), str(vd.get("Model Year", "")))


def complaint_summary(comps: list[dict]) -> tuple[list[tuple[str, int]], list[dict]]:
  """(most-reported systems, the complaints most like THIS car's symptoms/codes)."""
  counts = {}
  for c in comps:
    for part in {p.strip() for p in c["components"].split(",") if p.strip()}:
      counts[part] = counts.get(part, 0) + 1
  top = sorted(counts.items(), key=lambda kv: -kv[1])[:6]
  words = {w for w in re.findall(r"[a-z]{4,}", (ss.symptoms or "").lower())} - \
      {"when", "with", "then", "that", "this", "only", "after", "from", "have", "engine", "light", "car", "vehicle"}
  for code in current_codes():
    for pre, w in CODE_WORDS:
      if code.startswith(pre):
        words |= {x for x in w.split() if len(x) >= 4}
        break
  scored = []
  for c in comps:
    text = c["summary"].lower()
    sc = sum(1 for w in words if w in text) + sum(2 for code in current_codes() if code.lower() in text)
    if sc >= 2:
      scored.append((sc, c))
  scored.sort(key=lambda x: -x[0])
  return top, [c for _, c in scored[:4]]


def vehicle_recalls() -> list[dict]:
  vd = ss.vehicle_details or {}
  return nhtsa_recalls(str(vd.get("Make", "")), str(vd.get("Model", "")), str(vd.get("Model Year", "")))


# --- JOBS (each car in the shop is a job, saved automatically) ---
JOB_FIELDS = ["customer_name", "customer_phone", "customer_address", "vin_input", "active_vin", "vehicle_info", "vehicle_make",
              "vehicle_details", "sel_codes", "manual_dtc", "symptoms", "ble_dtcs", "scan_data", "test_results", "dtc_result",
              "scope_result", "chat_history", "tech_notes", "customer_summary", "fix_part", "fix_test", "fix_notes",
              "customer_email", "odometer", "estimate_rows", "follow_up_days", "follow_up_note", "follow_up_done",
              "wave_result", "plan_steps", "plan_idx", "plan_done", "plan_notes", "diag_requests", "ro_story"]


def job_snapshot() -> dict:
  d = {k: ss.get(k) for k in JOB_FIELDS}
  # photos stay out of storage (too big); the text of the chat is kept
  d["chat_history"] = [{"role": m.get("role"), "content": m.get("content"), "photos_n": len(m.get("photos") or []) or m.get("photos_n", 0),
                        "chat_id": m.get("chat_id"), "who": m.get("who", ""), "videos": m.get("videos") or [],
                        "video_names": m.get("video_names") or [], "reused_video": bool(m.get("reused_video"))}
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


# --- SHOP KNOWLEDGE: testing facts the tech has learned (specs, patterns, test methods), in our own words ---
KNOW_KINDS = ["Spec / known-good value", "What a pattern means", "Test procedure", "Rule of thumb"]
# code families -> the systems/words a note about them would mention
CODE_WORDS = [
    ("P0300", "misfire ignition coil plug spark injector compression burn secondary"),
    ("P030", "misfire ignition coil plug spark injector compression burn secondary"),
    ("P017", "fuel trim lean rich vacuum leak maf injector fuel pressure"),
    ("P010", "maf map airflow mass air"), ("P011", "intake air temperature iat"), ("P012", "throttle tps pedal"),
    ("P013", "o2 oxygen sensor heater upstream downstream"), ("P014", "o2 oxygen sensor"), ("P015", "o2 oxygen sensor"),
    ("P016", "o2 oxygen sensor"), ("P0087", "fuel pressure rail pump"), ("P019", "fuel pressure rail"),
    ("P020", "injector circuit"), ("P021", "injector"), ("P026", "injector"), ("P032", "knock sensor"),
    ("P0335", "crank sensor ckp reluctor tooth"), ("P0336", "crank sensor ckp reluctor tooth"),
    ("P034", "cam sensor cmp timing"), ("P036", "cam timing"), ("P001", "cam timing vvt phaser solenoid"),
    ("P040", "egr"), ("P042", "catalyst converter o2"), ("P043", "catalyst converter"), ("P044", "evap purge vent smoke leak"),
    ("P045", "evap purge vent"), ("P050", "idle throttle air"), ("P056", "charging voltage battery alternator"),
    ("P062", "alternator charging"), ("P07", "transmission shift solenoid pressure"), ("P08", "transmission"),
    ("P2096", "fuel trim post catalyst o2"), ("P2097", "fuel trim post catalyst o2"), ("P2", "sensor circuit"),
    ("U", "network can bus communication module"), ("C", "abs wheel speed brake"), ("B", "body airbag"),
]


def knowledge_entries() -> list[dict]:
  return [dict(r.get("data") or {}, _id=r["id"]) for r in store_list_all("know")]


KN_STOP = {"the", "and", "for", "with", "what", "that", "this", "does", "have", "from", "when", "where", "which", "how", "why",
           "are", "was", "you", "your", "can", "should", "would", "could", "there", "they", "its", "not", "but", "all", "any",
           "out", "off", "get", "got", "just", "about", "into", "then", "than", "them", "will", "good", "bad", "need", "know",
           "tell", "give", "look", "want", "car", "vehicle", "truck", "one", "two", "also", "still", "it's", "i'm", "don't"}


def knowledge_for_job(limit: int = 30, extra: str = "") -> list[dict]:
  """The notes that fit THIS job: matching systems (from the codes/symptoms, plus `extra` — the question being asked or
  the kind of check) and this make, never another make's."""
  entries = knowledge_entries()
  if not entries:
    return []
  vd = ss.vehicle_details or {}
  make = str(vd.get("Make") or "").lower()
  words = set()
  for c in current_codes():
    for pre, w in CODE_WORDS:
      if c.startswith(pre):
        words |= set(w.split())
        break
  words |= {w for w in re.findall(r"[a-z0-9]+", ((ss.symptoms or "") + " " + (ss.vehicle_info or "") + " " + (extra or "")).lower())
            if len(w) >= 3}
  words -= KN_STOP
  fam = MAKE_PROFILES.get(make.upper(), make.upper()).lower() if make else ""
  same_family = ({m.lower() for m, f in MAKE_PROFILES.items() if f.lower() == fam} | {fam, make}) if make else set()
  all_makes = {m.lower() for m in MAKE_PROFILES} | {f.lower() for f in MAKE_PROFILES.values()} | \
      {m.lower() for m in MANUAL_MAKES if m != "Other..."}
  # 🧠 meaning: how close each note is to this job (codes, symptoms, vehicle, the question) even with different words
  query = " ".join([", ".join(current_codes()), " ".join(sorted(words)), ss.vehicle_info or "", (ss.symptoms or ""), extra or ""])
  sem = meaning_scores(query, "know", [(e["_id"], note_text(e)) for e in entries]) if len(entries) > 8 else {}
  base = sorted(sem.values())[len(sem) // 2] if sem else 0.0   # typical closeness: only notes above it get credit
  scored = []
  for e in entries:
    text = f"{e.get('topic', '')} {e.get('rule', '')} {e.get('applies_to', '')}".lower()
    applies = str(e.get("applies_to") or "").lower()
    named = {m for m in all_makes if re.search(rf"\b{re.escape(m)}\b", applies)}
    if named and make and not (named & same_family):
      continue   # a note for another make never goes into this car's diagnosis
    kw = sum(1 for w in words if w in text)
    near = max(0.0, sem.get(e["_id"], 0.0) - base) * 40   # 0 .. ~10
    score = kw + near + (3 if named & same_family else 0)
    if (kw > 0 or near > 2) and e.get("type") == "Test procedure":
      score += 2   # the shop's own test methods matter most when planning tests
    scored.append((score, e))
  if len(scored) > limit:
    scored = [x for x in scored if x[0] > 0] or scored
  scored.sort(key=lambda x: -x[0])
  return [e for _, e in scored[:limit]]


def similar_cases(query: str, limit: int = 4) -> list[dict]:
  """🧠 Confirmed fixes from ANY vehicle that match this problem by meaning (same-car and same-model ones are shown elsewhere)."""
  try:
    fixes = [dict(r.get("data") or {}, _id=r["id"]) for r in store_list("fix", 400)]
  except Exception:
    return []
  fixes = [f for f in fixes if f.get("fix") and f.get("_id") != ss.get("job_id")]
  if len(fixes) < 2:
    return []
  sem = meaning_scores(query, "fix", [(f["_id"], f"{f.get('vehicle', '')} {f.get('engine', '')} | codes {', '.join(f.get('codes') or [])} | "
                                                   f"complaint: {f.get('complaint', '')} | fixed by: {f.get('fix', '')} | proved by: "
                                                   f"{f.get('confirmed_by', '')}") for f in fixes])
  if not sem:
    return []
  ranked = sorted(fixes, key=lambda f: -sem.get(f["_id"], 0))
  best = sem.get(ranked[0]["_id"], 0)
  vd = ss.vehicle_details or {}
  same_model = (str(vd.get("Make", "")).upper(), str(vd.get("Model", "")).upper())
  out = [f for f in ranked if sem.get(f["_id"], 0) >= best - 0.08 and (f.get("make"), f.get("model")) != same_model
         and f.get("vin") != ss.get("active_vin")]
  return out[:limit]


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


def knowledge_block(extra: str = "", limit: int = 30) -> str:
  """The shop's Knowledge notes that fit this job / question, ready to drop into an AI prompt ('' if none)."""
  try:
    kn = knowledge_for_job(limit, extra)
  except Exception as e:   # a bonus; never block an answer over it
    log_problem("storage", "Knowledge notes for AI", str(e))
    return ""
  if not kn:
    return ""
  line = lambda e: (f"- [{e.get('topic', 'General')}{(' · ' + e['applies_to']) if e.get('applies_to') and str(e['applies_to']).lower() not in ('all', 'any') else ''}] "
                    f"{e.get('rule', '')}")
  tests = [e for e in kn if e.get("type") == "Test procedure"]
  other = [e for e in kn if e.get("type") != "Test procedure"]
  return ("THIS SHOP'S TESTING KNOWLEDGE (the technician's own notes). Apply the ones that fit and say which you used; "
          "if a note conflicts with the measured data, say so."
          + ("\nTHEIR OWN TEST METHODS — when a test you recommend matches one of these, use THEIR method (their exact steps, "
             "hookup and values) instead of a generic one, and mark it '📖 Shop method':\n" + "\n".join(map(line, tests)) if tests else "")
          + ("\nTHEIR SPECS, PATTERNS AND RULES OF THUMB:\n" + "\n".join(map(line, other)) if other else ""))


def test_methods(extra: str = "", limit: int = 10) -> list[dict]:
  """The shop's own Test procedure notes that fit this job, numbered K1, K2... for the step cards."""
  try:
    kn = [e for e in knowledge_for_job(60, extra) if e.get("type") == "Test procedure"][:limit]
  except Exception:
    return []
  return [dict(e, kid=f"K{i + 1}") for i, e in enumerate(kn)]


def shop_context(extra: str = "") -> str:
  """This shop's own history + Knowledge notes for the AI prompts ('' if there is none). `extra` = the question or the
  kind of check, so the notes that fit it are picked."""
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
    comps = vehicle_complaints()
    if comps:
      top, like = complaint_summary(comps)
      out.append(f"NHTSA OWNER COMPLAINTS for this year/make/model ({len(comps)} filed; owner reports, not confirmed "
                 f"fixes). Most reported: " + ", ".join(f"{n.title()} ({k})" for n, k in top[:5]))
      out += [f"- Similar complaint: {c['summary'][:260]}" for c in like[:3]]
    kb = knowledge_block(extra)
    if kb:
      out.append(kb)
    if ss.get("vehicle_info") or current_codes() or (ss.get("symptoms") or "").strip():
      sim = similar_cases(" ".join([", ".join(current_codes()), ss.symptoms or "", ss.vehicle_info or "", extra or ""]))
      if sim:
        out.append("SIMILAR CASES THIS SHOP FIXED ON OTHER VEHICLES (matched by meaning — leads to check, not proof):")
        out += [f"- {f.get('vehicle', '')}: codes {', '.join(f.get('codes') or []) or 'none'}; complaint: {(f.get('complaint') or '-')[:120]} "
                f"-> FIXED BY {f.get('fix')} (proved by: {f.get('confirmed_by') or '-'})" for f in sim]
  except Exception as e:   # history is a bonus; never block a diagnosis over it
    log_problem("storage", "Shop history for AI", str(e))
  return ("\n\n" + "\n".join(out)) if out else ""


# --- WIRING DIAGRAMS: the AI asks for the diagram a test needs; the tech adds a photo, screenshot or the shared screen ---
DIAGRAM_RULE = """

WIRING DIAGRAMS: never guess pin numbers, wire colors or connector IDs. If a test needs them and they aren't in the
technician's added diagrams (below, if any), ask for the diagram: end your answer with one line exactly like
NEED_DIAGRAM: Bank 1 Sensor 1 O2 sensor circuit, PCM to sensor; PCM power and ground circuits
(name each circuit plainly, at most 3). If no diagram is needed, leave the line out."""

DIAGRAM_READ_PROMPT = """You are a master automotive electrical diagnostician reading a wiring diagram the technician just added.
Vehicle: {vehicle}
The diagram is for: {circuit}
The tests that need it:
{tests}

Read the diagram carefully and return JSON only:
{{"summary": "<the circuit in plain words: each connector (ID / C-number) with its pin or cavity numbers, wire colors, circuit numbers or names, splices (S-numbers), grounds (G-numbers), fuses and relays, and which module pins it runs to>",
 "tests": [{{"step": <the step number from the list above, or 0>, "hookup": "<exactly where to back-probe (connector, pin, wire color), what to measure it against, key on or engine running, and the reading that means good vs bad>"}}],
 "unclear": "<anything too small, blurry or cut off to read — or ''>"}}
Use only what you can read on the diagram. Never guess a pin number or wire color — put it in "unclear" instead."""

DIAGRAM_CHECK_PROMPT = """You are the second set of eyes on a wiring diagram. Another technician read the attached diagram
and wrote the reading below. A wrong pin number or wire color sends the tech to the wrong wire, so check it.
Vehicle: {vehicle} · Circuit: {circuit}

THEIR READING:
{reading}

Look at the diagram yourself. For every connector ID, pin / cavity number, wire color, splice, ground, fuse and module
pin in their reading, check it against what is printed on the diagram.
Return JSON only: {{"differences": ["<what they wrote> — on the diagram I read <what you read>", ...],
"missed": ["<anything on the diagram the tests need that they left out>", ...]}}
List a difference only if you can clearly read it differently. If everything matches, return {{"differences": [], "missed": []}}."""


def diagram_second_look(b64: str, circuit: str, obj: dict, first_reader: str) -> str:
  """A different AI re-reads the diagram and compares it with the first reading. Returns a note for the tech
  ('' when they agree or no second AI is set up)."""
  reading = json.dumps({k: obj.get(k) for k in ("summary", "tests")}, ensure_ascii=False)[:6000]
  ask = DIAGRAM_CHECK_PROMPT.format(vehicle=ss.vehicle_info or "not given", circuit=circuit, reading=reading)
  try:
    if has_openai() and "ChatGPT" not in first_reader:
      raw, who = chatgpt(ask, max_tokens=8000, timeout=120, image_b64=b64, effort="medium"), "ChatGPT"
    elif secret("GEMINI_API_KEY") and "Gemini" not in first_reader:
      raw, who = gemini([{"text": ask}, {"inline_data": {"mime_type": "image/jpeg", "data": b64}}], json_mode=True,
                        timeout=90, think="high"), "Gemini"
    else:
      return ""
  except AIError:
    return ""
  chk = find_json(raw, dict) or {}
  diffs = [str(x) for x in (chk.get("differences") or []) if str(x).strip()][:8]
  missed = [str(x) for x in (chk.get("missed") or []) if str(x).strip()][:5]
  if not diffs and not missed:
    return f"✅ {who} re-read the diagram and agrees with every pin and wire color."
  return (f"⚠️ {who} re-read the diagram and saw these differently — check them on the diagram before you probe: "
          + " · ".join(diffs + ["(left out) " + m for m in missed]))


def _norm_circ(c) -> set:
  return set(re.findall(r"[a-z0-9]+", str(c or "").lower())) - KN_STOP - {"circuit", "wiring", "diagram", "the", "to"}


def _circ_match(a, b) -> bool:
  A, B = _norm_circ(a), _norm_circ(b)
  return bool(A and B) and len(A & B) / min(len(A), len(B)) >= 0.6


def split_need_diagram(text: str) -> tuple[str, list]:
  """Turn the AI's NEED_DIAGRAM line into a plain note for the tech; returns (text, circuits asked for)."""
  found = []
  def grab(m):
    found.extend(c.strip(" .;,-*_`") for c in re.split(r";|\s\|\s", m.group(1)))
    return ""
  clean = re.sub(r"(?im)^[\s*_`>-]*NEED[_ ]DIAGRAMS?\s*[:=]\s*(.*)$", grab, text or "").rstrip()
  found = [c for c in dict.fromkeys(found) if c and c.lower() not in ("none", "n/a", "no")][:3]
  if found:
    clean += ("\n\n📐 **Wiring diagram needed:** " + "; ".join(found) + " — add it in 📐 Wiring diagrams on the 🔧 Diagnose "
              "tab (photo, screenshot, or your shared screen) and the AI will give you the exact pins and wire colors.")
  return clean, found


def add_diagram_requests(circuits: list, source: str):
  reqs = list(ss.get("diag_requests") or [])
  for c in circuits or []:
    if c and not any(_circ_match(c, r.get("circuit")) for r in reqs):
      reqs.append({"circuit": str(c)[:160], "from": source, "at": datetime.now().strftime("%I:%M %p")})
  ss.diag_requests = reqs[-12:]


def job_diagrams() -> list[dict]:
  rows = []
  if ss.get("job_id"):
    try:
      rows = [dict(r.get("data") or {}, _id=r["id"]) for r in store_list("diagram", 20, {"job": ss.job_id})]
    except Exception:
      rows = []
  have = {r["_id"] for r in rows}
  return rows + [d for d in (ss.get("diagrams_nojob") or []) if d.get("_id") not in have]


def diagram_for(circuit: str, step_idx: int | None = None) -> dict | None:
  for d in job_diagrams():
    if (step_idx is not None and step_idx in (d.get("steps") or [])) or _circ_match(circuit, d.get("circuit")):
      return d
  return None


def diagram_context() -> str:
  ds = job_diagrams()
  if not ds:
    return ""
  out = ["\n\nWIRING DIAGRAMS THE TECHNICIAN ADDED (read from their diagram photos — use these exact connectors, pins and "
         "wire colors; don't contradict them):"]
  for d in ds[:4]:
    r = d.get("read") or {}
    out.append(f"- {d.get('circuit')}: {str(r.get('summary', ''))[:1500]}")
    for t in (r.get("tests") or [])[:6]:
      out.append(f"  · hookup{(' for step ' + str(t.get('step'))) if t.get('step') else ''}: {str(t.get('hookup', ''))[:400]}")
    if r.get("unclear"):
      out.append(f"  · couldn't read on the diagram: {r['unclear']}")
    if str(r.get("second") or "").startswith("⚠️"):
      out.append(f"  · second reader's note (the two readings differ here — tell the tech to verify these on the diagram): {r['second']}")
  return "\n".join(out)


def process_diagram(img_bytes: bytes, circuit: str, step_ids: list):
  """The AI reads a wiring diagram the tech added and turns it into exact hookups for the tests that need it."""
  h = hashlib.md5(img_bytes).hexdigest() + _norm_circ(circuit).__repr__()
  if h in (ss.get("_dg_seen") or set()):
    return
  ss._dg_seen = set(ss.get("_dg_seen") or set()) | {h}
  ss.diag_n = ss.get("diag_n", 0) + 1   # empties the photo boxes for the next one
  try:
    b64 = shrink_to_b64(img_bytes, 2000, 88)   # big enough to read pin numbers and wire colors
  except Exception:
    ss._toast = "Couldn't open that picture — try a JPG or PNG."
    st.rerun()
  ps = ss.get("plan_steps") or {}
  steps = ps.get("steps") or [] if ps.get("_for") == _plan_sig() else []
  match = sorted(set(step_ids) | {i for i, s_ in enumerate(steps) if s_.get("diagram") and _circ_match(circuit, s_["diagram"])})
  tests = "\n".join(f"{i + 1}. {steps[i].get('title')}: {steps[i].get('do')}" for i in match if i < len(steps))
  with st.spinner("📐 The AI is reading the wiring diagram..."):
    raw, who = quick_ai(DIAGRAM_READ_PROMPT.format(vehicle=ss.vehicle_info or "not given", circuit=circuit,
                                                   tests=tests or "(general checks of this circuit — power, ground, signal)"),
                        image_b64=b64, max_tokens=12000, effort="high")
  if str(raw).startswith("⚠️"):
    ss._toast = "Couldn't read the diagram: " + str(raw)[2:150]
    st.rerun()
  obj = find_json(raw, dict) or {"summary": str(raw)[:3000], "tests": [], "unclear": ""}
  with st.spinner("📐 A second AI is double-checking the pins and wire colors..."):
    obj["second"] = diagram_second_look(b64, circuit, obj, who)
  autosave_job(force=True)
  rid = f"{ss.get('job_id') or 'nojob'}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
  rec = {"job": ss.get("job_id") or "", "vin": ss.get("active_vin") or "", "vehicle": ss.vehicle_info or "", "circuit": circuit,
         "b64": b64, "read": obj, "steps": match, "who": who, "at": datetime.now().strftime("%Y-%m-%d %I:%M %p")}
  store_put("diagram", rid, rec)
  if not ss.get("job_id"):
    ss.diagrams_nojob = (ss.get("diagrams_nojob") or []) + [dict(rec, _id=rid)]
  queue_update(toast="📐 Diagram read — the exact pins and wire colors are on the test steps")


def diagram_adder(circuit: str, step_ids: list, key: str):
  """Add the diagram: a photo or screenshot, the camera, or whatever is on the shared Topdon / Autel screen."""
  n = ss.get("diag_n", 0)
  c1, c2 = st.columns([3, 2])
  with c1:
    pasted = _paste_box(key=f"dgp_{key}_{n}", default=None)
    up = st.file_uploader("…or a photo / screenshot file", type=PHOTO_TYPES, key=f"dgu_{key}_{n}")
  with c2:
    if ss.get("eye_on"):
      if st.button("📺 Use my shared screen", key=f"dge_{key}_{n}", use_container_width=True,
                   help="Takes a fresh, sharp picture of your shared screen or tab right now — open the diagram there first"):
        rid = f"dg{time.time():.3f}"
        ss.eye_req, ss._dg_wait = {"id": rid}, {"req": rid, "circuit": circuit, "steps": list(step_ids), "t": time.time()}
        st.rerun()
      if ss.get("_dg_wait"):
        st.caption("📺 Grabbing your shared screen…")
    else:
      st.caption("Tip: share the tab or screen that has the diagram (👀 at the top) — then one tap adds it, every time.")
    cam = camera_shot("📷 Snap the diagram", key=f"dgc_{key}_{n}") if st.toggle("📷 Camera", key=f"dgt_{key}") else None
  if isinstance(pasted, dict) and pasted.get("img"):
    process_diagram(base64.b64decode(pasted["img"]), circuit, step_ids)
  for f in (up, cam):
    if f is not None:
      process_diagram(f.getvalue(), circuit, step_ids)


def diagrams_panel(fold: bool = False):
  ds = job_diagrams()
  ps = ss.get("plan_steps") or {}
  steps = ps.get("steps") or [] if ps.get("_for") == _plan_sig() else []
  wanted = list(ss.get("diag_requests") or [])
  for i, s_ in enumerate(steps):
    if str(s_.get("diagram") or "").strip() and not any(_circ_match(s_["diagram"], w.get("circuit")) for w in wanted):
      wanted.append({"circuit": s_["diagram"], "from": f"step {i + 1}"})
  open_ = [w for w in wanted if not diagram_for(w["circuit"])]
  if not ds and not open_ and not st.session_state.get("dg_more"):
    if st.button("📐 Add a wiring diagram", key="dg_more_btn"):
      ss.dg_more = True
      st.rerun()
    return
  with st.expander(f"📐 Wiring diagrams for this job — {len(ds)} added" + (f", {len(open_)} the AI needs" if open_ else ""),
                   expanded=bool(open_) and not fold):
    st.caption("The AI asks for a diagram when a test needs exact pins or wire colors, and never guesses them. Add a photo, a "
               "screenshot, or your shared scan tool screen — it reads the diagram and puts the exact hookup on each test step.")
    for k, w in enumerate(open_):
      with st.container(border=True):
        st.markdown(f"**📐 Needed: {w['circuit']}**  \n<small>asked for by the {w.get('from', 'AI')}</small>", unsafe_allow_html=True)
        diagram_adder(w["circuit"], [i for i, s_ in enumerate(steps) if _circ_match(w["circuit"], s_.get("diagram"))], f"r{k}")
    for d in ds:
      r = d.get("read") or {}
      with st.container(border=True):
        a, b = st.columns([1, 2])
        try:
          a.image(base64.b64decode(d.get("b64", "")), use_container_width=True, caption=d.get("at", ""))
        except Exception:
          a.caption("(picture unreadable)")
        b.markdown(f"**📐 {d.get('circuit')}**  \n{r.get('summary', '')}")
        for t in r.get("tests") or []:
          b.markdown(f"- {'Step ' + str(t.get('step')) + ': ' if t.get('step') else ''}{t.get('hookup', '')}")
        if r.get("unclear"):
          b.caption(f"⚠️ Couldn't read: {r['unclear']}")
        if r.get("second"):
          b.caption(r["second"])
        if b.button("🗑️ Remove", key=f"dgdel_{d['_id']}"):
          store_delete("diagram", d["_id"])
          ss.diagrams_nojob = [x for x in (ss.get("diagrams_nojob") or []) if x.get("_id") != d["_id"]]
          st.rerun()
    other = st.text_input("➕ Diagram for another circuit — what is it?", key="dg_other",
                          placeholder="e.g. Fuel pump circuit, relay to pump")
    if other.strip():
      diagram_adder(other.strip(), [], "other")


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
    return "On 🚗 Vehicle Scan: type or photo the VIN, or tap <b>Connect &amp; Auto-Scan</b> (fills everything in)."
  if not current_codes() and not (ss.symptoms or "").strip() and not ss.scan_data:
    return "Connect the scanner on 🚗 Vehicle Scan to read codes — or type codes/symptoms on 🔧 Diagnostics."
  if not ss.dtc_result:
    return "Run the <b>Diagnostic Tree</b> on 🔧 Diagnostics to get the test plan."
  if not (ss.fix_part or "").strip():
    return "Work the plan (🔬 scope + guided tests), then record the <b>confirmed fix</b> on 🧾 Customer &amp; RO."
  return "Send the repair order (🧾 Customer &amp; RO), then tap <b>✅ Car is done</b> on 🚗 Vehicle Scan."


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


LOGIN_DAYS = 30
COOKIE = "tdg_login"


def _sign(name: str, exp: int, pw: str) -> str:
  key = hashlib.sha256(("tdg-auth|" + pw + "|" + secret("APP_SECRET")).encode()).digest()
  return hmac.new(key, f"{name}|{exp}".encode(), hashlib.sha256).hexdigest()[:32]


def make_login(name: str, pw: str) -> str:
  """A login pass that EXPIRES (30 days) and stops working the moment that tech's password changes."""
  exp = int(time.time()) + LOGIN_DAYS * 86400
  return base64.urlsafe_b64encode(f"{name}|{exp}|{_sign(name, exp, pw)}".encode()).decode().rstrip("=")


def check_login(tok: str | None) -> tuple[str, int] | None:
  if not tok or len(tok) > 300:
    return None
  try:
    name, exp, sig = base64.urlsafe_b64decode(tok + "=" * (-len(tok) % 4)).decode().rsplit("|", 2)
    exp = int(exp)
  except (ValueError, UnicodeDecodeError):
    return None
  if exp < time.time():
    return None
  for pw, nm in shop_users().items():
    if nm == name and hmac.compare_digest(sig, _sign(name, exp, pw)):
      return name, exp
  return None


def _cookie_login() -> str | None:
  try:
    return st.context.cookies.get(COOKIE)
  except Exception:   # older Streamlit: no cookie access -> the address-bar fallback is used
    return None


def _set_cookie(tok: str, max_age: int):
  """Save the login pass in this browser (not in the address bar, so a shared job link never carries it)."""
  components.html(f"<script>document.cookie = '{COOKIE}={tok}; path=/; max-age={max_age}; SameSite=Lax'"
                  f" + (location.protocol === 'https:' ? '; Secure' : '');</script>", height=0)


def keep_screen_on(on: bool):
  """Screen Wake Lock on the app's page: the phone won't dim and lock while the app is open and on screen. The browser
  drops the lock when you switch away, so it's taken again whenever the app comes back or is tapped."""
  components.html("""<script>
  const w = window.parent;
  w.__tdgKeepOn = %s;
  async function lock() {
    try {
      if (!w.__tdgKeepOn || !("wakeLock" in w.navigator) || w.document.visibilityState !== "visible") return;
      if (w.__tdgWake && !w.__tdgWake.released) return;
      w.__tdgWake = await w.navigator.wakeLock.request("screen");
    } catch (e) {}
  }
  if (!w.__tdgWakeHooked) {
    w.__tdgWakeHooked = true;
    w.document.addEventListener("visibilitychange", lock);
    w.document.addEventListener("click", lock, { passive: true });
    w.document.addEventListener("touchend", lock, { passive: true });
  }
  if (w.__tdgKeepOn) lock();
  else if (w.__tdgWake) { try { w.__tdgWake.release(); } catch (e) {} w.__tdgWake = null; }
  </script>""" % ("true" if on else "false"), height=0)


def require_password():
  users = shop_users()
  if not users:
    return
  found = None
  for cand, src in ((ss.get("_auth_tok"), "session"), (_cookie_login(), "cookie"), (st.query_params.get("k"), "url")):
    ok = check_login(cand)
    if ok:
      found = (cand, src, ok)
      break
  if found:
    tok, src, (name, exp) = found
    ss._auth_tok, ss.tech_user = tok, name
    if exp - time.time() < 10 * 86400:   # renew quietly when it's getting old
      pw = next(p_ for p_, n_ in users.items() if n_ == name)
      tok = ss._auth_tok = make_login(name, pw)
      _set_cookie(tok, LOGIN_DAYS * 86400)
      if "k" in st.query_params:
        st.query_params["k"] = tok
    elif src == "cookie" and "k" in st.query_params:
      del st.query_params["k"]   # the cookie works here, so the address bar no longer needs the pass
    elif src == "url" and not ss.get("_cookie_sent"):
      _set_cookie(tok, LOGIN_DAYS * 86400)   # move it into a cookie; the URL copy is dropped once the cookie is seen
      ss._cookie_sent = True
    return
  if "k" in st.query_params:
    del st.query_params["k"]   # expired or old-style pass: clear it
  box = st.empty()
  with box.container():
    st.markdown("### 🔒 Shop login")
    with st.form("login"):
      entered = st.text_input("Password", type="password")
      submitted = st.form_submit_button("Log in", type="primary")
    if submitted:
      match = next((pw for pw in users if hmac.compare_digest(hashlib.sha256(entered.encode()).digest(),
                                                              hashlib.sha256(pw.encode()).digest())), None)
      if not match:
        st.error("Wrong password.")
  if submitted and match:
    tok = make_login(users[match], match)
    ss._auth_tok, ss.tech_user, ss._cookie_sent = tok, users[match], True
    _set_cookie(tok, LOGIN_DAYS * 86400)
    st.query_params["k"] = tok   # backup in case this browser blocks cookies; removed on the next visit if not needed
    box.empty()
    return   # carry on drawing the app in this same run (so the cookie actually gets written)
  st.stop()


def logout():
  ss._auth_tok, ss.tech_user = None, None
  if "k" in st.query_params:
    del st.query_params["k"]
  _set_cookie("", 0)
  st.success("Logged out on this device.")
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
  ss.chat_conv, ss._chat_pending = None, None   # a different car = a new conversation
  if "chat" in st.query_params:
    del st.query_params["chat"]
  if _jr == "new":
    new_job()
  elif not load_job(_jr):
    ss._toast = "Couldn't open that job."
elif "job_id" not in ss:
  ss.job_id = None
  if _qj := st.query_params.get("job"):
    if not load_job(_qj):   # e.g. the link is from before permanent storage was set up
      del st.query_params["job"]
  elif store_on():   # opened on another device: pick up the car you were working on in the last few hours
    with guard("Pick up where you left off"):
      _now = datetime.now(timezone.utc)
      for _r in store_list("job", 20, {"status": "open"}):
        try:
          _age = (_now - datetime.fromisoformat(str(_r.get("updated_at")).replace("Z", "+00:00"))).total_seconds()
        except ValueError:
          continue
        _d = _r.get("data") or {}
        if _age < 4 * 3600 and (not ss.get("tech_user") or _d.get("tech") in ("", None, ss.get("tech_user"))):
          if load_job(_r["id"]):
            st.toast(f"🚗 Picked up where you left off: {_d.get('vehicle_info') or _d.get('customer_name') or 'your last car'} — switch in 🚗 Cars in the shop")
          break
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
      st.warning(f"⚠️ Last save had a problem: {ss._store_err} (details in ☰ More → 📋 Log → 🐞 Problem log)")
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
      ("💬 ChatGPT 2nd diagnosis", has_openai()), ("🐋 DeepSeek 3rd opinion", has_deepseek()),
      ("🌐 Perplexity research", bool(secret("PERPLEXITY_API_KEY"))),
      ("📧 Email reports", email_ready()), ("💬 Text customers", sms_ready()), ("📲 Phone alerts (ntfy)", ntfy_ready()),
      ("🧠 Meaning search", bool(embed_provider())),
  ]
  on = sum(1 for _, ok in checks if ok)
  with st.expander(("⚙️" if on == len(checks) else "🟡") + f" Setup — {on}/{len(checks)} connected"):
    if ss.get("tech_user"):
      _lo1, _lo2 = st.columns([3, 1])
      _lo1.caption(f"Logged in as **{ss.tech_user}** (stays logged in on this device for {LOGIN_DAYS} days)")
      if _lo2.button("🚪 Log out", key="logout_btn"):
        logout()
    st.markdown("  \n".join(("✅ " if ok else "⬜ ") + n for n, ok in checks))
    if on < len(checks):
      st.caption("Turn one on by adding its key in **Manage app → Settings → Secrets**:  \n"
                 "login → APP_PASSWORD (or APP_USERS = \"Name:pass, Name2:pass2\")  \n"
                 "storage → SUPABASE_URL + SUPABASE_KEY  \n"
                 "AIs → GEMINI_API_KEY · ANTHROPIC_API_KEY · OPENAI_API_KEY (ChatGPT) · DEEPSEEK_API_KEY · PERPLEXITY_API_KEY  \n"
                 "email → SMTP_USER + SMTP_PASSWORD (Gmail app password)  \n"
                 "texting → TWILIO_SID + TWILIO_TOKEN + TWILIO_FROM  \n"
                 "phone alerts → NTFY_TOPIC (make up a long name, subscribe to it in the free ntfy app)  \n"
                 "meaning search → on automatically with the Gemini key (or HF_TOKEN, or fastembed installed on your server)")
    if ntfy_ready() and st.button("📲 Send a test alert to my phone", key="ntfy_test"):
      notify("✅ Test Don't Guess", "Phone alerts are working. You'll get one when an AI answer, AI Check or test drive "
             "review is ready.", "white_check_mark", 3, app_link())
      st.toast("Sent — check your phone")
    if embed_provider():
      st.caption(f"🧠 Meaning search: {embed_model_key()}")
    st.markdown("**🤝 Who does what on the AI team**")
    _on = {"🌐 Perplexity": bool(secret("PERPLEXITY_API_KEY")), "✨ Gemini": bool(secret("GEMINI_API_KEY")),
           "💬 ChatGPT": has_openai(), "🐋 DeepSeek": has_deepseek(), "🧠 Claude": has_claude()}
    st.markdown("  \n".join(("✅ " if _on.get(n) else "⬜ ") + f"**{n}** — {job}" + (f" _(backup: {bk})_" if bk != "—" else "")
                             for n, job, bk in AI_ROLES))
    st.caption(f"Models: {gemini_label()} · {claude_label()}" + (f" · {openai_label()}" if has_openai() else "")
               + (f" · {deepseek_label()}" if has_deepseek() else "")
               + "  \nEach AI is told to think it through before it answers; the final check runs at high effort. If an AI "
                 "is down, its backup takes over and the answer says so.")


# ⚙️ Settings sit in the top-right corner (setup, Simple view, keep screen on, what's new)
with guard("Settings"):
  if "simple_view" not in ss:
    ss.simple_view = st.query_params.get("view") == "simple"
  try:
    _gear = st.container(key="gear")
  except TypeError:   # older Streamlit
    _gear = st.container()
  with _gear:
    _pop = getattr(st, "popover", None)
    with (_pop("⚙️") if _pop else st.expander("⚙️ Settings")):
      setup_panel()
      st.toggle("🌟 Simple view", key="simple_view",
                help="Big status cards, the plan one test at a time, plain-English codes. Hides the AI drafts and "
                     "web research under the test plan — nothing is lost, switch it off to see them.")
      st.toggle("🔆 Keep screen on", value=True, key="keep_on",
                help="Stops the phone from locking while the app is open, so it doesn't reset in the middle of a job. "
                     "Uses a little more battery — turn it off when you don't need it.")
      st.markdown("**🆕 What's new**")
      st.markdown("\n".join(f"- {w}" for w in WHATS_NEW[-8:]))
  if ss.simple_view and st.query_params.get("view") != "simple":
    st.query_params["view"] = "simple"
  elif not ss.simple_view and "view" in st.query_params:
    del st.query_params["view"]
  keep_screen_on(bool(ss.get("keep_on", True)))


STEP_PROMPT = """Turn this diagnostic test plan into step-by-step cards a technician (or a helper learning the trade) can
work through one at a time on the vehicle.

Vehicle: {vehicle}
Codes: {codes}
Symptoms: {symptoms}

THE TEST PLAN:
{plan}

THE SHOP'S OWN TEST METHODS (the technician's Knowledge notes). When a step is one of these tests, write the step using
THEIR method and put its id in "methods":
{methods}

RULES:
- 4 to 8 steps, in the same order as the plan (fastest/cheapest and most likely first).
- Each step is ONE test with a clear pass/fail result. Plain, simple words.
- Keep every spec, value and pin number EXACTLY as the plan gives it. Never invent a spec: if the plan has none,
  write "Look up the spec in service info".
- Add a short safety note where it matters (hot exhaust, moving belts or fan, fuel pressure, airbags, battery).
- If a step tests a circuit (voltage, ground, resistance, continuity, back-probing a pin, scoping a wire), set "diagram" to
  the wiring diagram it needs, named plainly (e.g. "Bank 1 Sensor 1 O2 sensor circuit, PCM to sensor"); otherwise "".
  Never invent pin numbers or wire colors.
- Explain each trouble code in one plain sentence (what the computer noticed), and write a one-line plain headline.

Return JSON only:
{{"headline": "...", "codes": [{{"code": "P0171", "plain": "..."}}],
 "steps": [{{"title": "...", "do": "what to do, step by step", "where": "where on this vehicle", "tools": "tools needed",
            "pass_fail": "what result means good vs bad", "safety": "or empty", "methods": ["K1"], "diagram": "or empty"}}]}}"""


def _plan_sig() -> str:
  r = ss.get("dtc_result") or {}
  return hashlib.md5((str(r.get("title")) + str(r.get("text"))).encode()).hexdigest()[:10]


def build_step_cards() -> bool:
  plan = (ss.get("dtc_result") or {}).get("text", "")
  if not plan.strip():
    return False
  methods = test_methods(plan[:4000])
  with st.spinner("Turning the plan into step-by-step cards..."):
    raw, who = quick_ai(STEP_PROMPT.format(vehicle=ss.vehicle_info or "not given", codes=", ".join(current_codes()) or "none",
                                           symptoms=(ss.symptoms or "").strip() or "not given", plan=plan[:9000],
                                           methods="\n".join(f"- {m['kid']}: [{m.get('topic', '')}] {m.get('rule', '')}" for m in methods)
                                           or "(none on file for this job)") + diagram_context(),
                        max_tokens=12000, effort="medium")
  obj = find_json(raw, dict) or {}
  steps = [x for x in (obj.get("steps") or []) if isinstance(x, dict) and str(x.get("title") or "").strip()]
  if not steps:
    st.error("Couldn't turn the plan into steps. " + (raw[:250] if raw.startswith("⚠️") else "Try again."))
    return False
  obj["steps"], obj["_for"], obj["_who"] = steps[:10], _plan_sig(), who
  obj["_methods"] = {m["kid"]: {"topic": m.get("topic", ""), "rule": m.get("rule", ""), "source": m.get("source", "")} for m in methods}
  for s_ in obj["steps"]:
    if str(s_.get("diagram") or "").strip():
      add_diagram_requests([s_["diagram"]], "step cards")
  ss.plan_steps, ss.plan_idx, ss.plan_done, ss.plan_notes, ss.plan_qa = obj, 0, [], {}, None
  return True


STEP_QUESTIONS = {
    "where": ("📍 Where is it?", "Exactly where is the part or connector for this step on this vehicle, what does it look like, "
                                "and what's in the way? Keep it short and practical."),
    "tool": ("🛠️ How do I hook up the tool?", "Step by step, how do I hook up the tools for this test (leads, back-probe "
                                              "points, settings), and what reading means good vs bad?"),
    "how": ("💡 How does it work?", "Explain how this part or circuit works in plain words with an everyday comparison, "
                                   "and why this test proves whether it's good. Keep it short."),
}


def step_cards_panel(simple: bool):
  ps = ss.get("plan_steps") or {}
  if not ss.get("dtc_result"):
    return
  if ps.get("_for") != _plan_sig():   # no cards yet, or they belong to an older plan
    if st.button("🪜 Work this plan step by step — one test at a time", type="primary" if simple else "secondary",
                 use_container_width=True, key="build_steps"):
      if build_step_cards():
        st.rerun()
    return
  steps, sig = ps["steps"], ps["_for"]
  n, done = len(steps), set(ss.plan_done or [])
  idx = max(0, min(int(ss.plan_idx or 0), n - 1))
  e = html_lib.escape
  if ps.get("headline"):
    st.markdown(f'<div class="tdg-card tdg-blue"><b>🎯 {e(str(ps["headline"]))}</b></div>', unsafe_allow_html=True)
  if ps.get("codes") and simple:
    cc = st.columns(min(3, len(ps["codes"])))
    for i_, c in enumerate(ps["codes"][:6]):
      cc[i_ % len(cc)].markdown(f'<div class="tdg-card tdg-yellow"><b>{e(str(c.get("code", "")))}</b><br>'
                                f'{e(str(c.get("plain", "")))}</div>', unsafe_allow_html=True)
  st.progress(len(done) / n, text=f"{len(done)} of {n} tests done")
  cur = steps[idx]
  row = lambda icon, lab, k: (f'<p><b>{icon} {lab}:</b> {e(str(cur.get(k)))}</p>' if str(cur.get(k) or "").strip() else "")
  st.markdown(
      f'<div class="tdg-step"><span class="tdg-badge">STEP {idx + 1} OF {n}{" ✓ DONE" if idx in done else ""}</span>'
      f'<h3>{e(str(cur.get("title", "")))}</h3>'
      + row("👣", "What to do", "do") + row("📍", "Where", "where") + row("🛠️", "Tools", "tools")
      + (f'<p class="tdg-spec"><b>📏 Pass / fail:</b> {e(str(cur.get("pass_fail")))}</p>' if cur.get("pass_fail") else "")
      + (f'<p class="tdg-safe"><b>⚠️ Safety:</b> {e(str(cur.get("safety")))}</p>' if str(cur.get("safety") or "").strip() else "")
      + "</div>", unsafe_allow_html=True)
  for mid in cur.get("methods") or []:   # 📖 the shop's own method for this test, from Knowledge
    mth = (ps.get("_methods") or {}).get(str(mid))
    if mth:
      st.markdown(f'<div class="tdg-card tdg-green"><b>📖 Your method — {e(str(mth.get("topic", "")))}:</b> {e(str(mth.get("rule", "")))}'
                  + (f'<br><small>from {e(str(mth.get("source")))}</small>' if mth.get("source") else "") + "</div>", unsafe_allow_html=True)
  if str(cur.get("diagram") or "").strip():   # 📐 exact pins from the tech's wiring diagram, or ask for it
    dg = diagram_for(cur["diagram"], idx)
    if dg:
      rd = dg.get("read") or {}
      hook = [t for t in rd.get("tests") or [] if str(t.get("step")) == str(idx + 1)]
      st.markdown(f'<div class="tdg-card tdg-blue"><b>📐 From your wiring diagram ({e(str(dg.get("circuit", "")))}):</b><br>'
                  f'{e(str(hook[0].get("hookup") if hook else str(rd.get("summary", ""))[:700]))}'
                  + (f'<br><small>⚠️ couldn\'t read: {e(str(rd.get("unclear")))}</small>' if rd.get("unclear") else "")
                  + (f'<br><small>{e(str(rd.get("second")))}</small>' if rd.get("second") else "") + "</div>",
                  unsafe_allow_html=True)
    else:
      with st.container(border=True):
        st.markdown(f"**📐 This test needs the wiring diagram for:** {cur['diagram']}  \n"
                    "<small>Add it and the AI gives you the exact pin and wire color to test — it won't guess them.</small>",
                    unsafe_allow_html=True)
        diagram_adder(str(cur["diagram"]), [idx], f"s{sig}_{idx}")
  note = st.text_input("What did you find on this step? (saved with the job, and the AI uses it)",
                       value=(ss.plan_notes or {}).get(str(idx), ""), key=f"pn_{sig}_{idx}",
                       placeholder="e.g. 0.42 V on the signal wire with key on — spec 0.5 V")
  if note != (ss.plan_notes or {}).get(str(idx), ""):
    ss.plan_notes = dict(ss.plan_notes or {}, **{str(idx): note})
  b1, b2, b3 = st.columns([1, 1.6, 1])
  if b1.button("⬅️ Back", disabled=idx == 0, use_container_width=True, key=f"pb_{sig}"):
    ss.plan_idx, ss.plan_qa = idx - 1, None
    st.rerun()
  if b2.button("✅ Done — next test" if idx not in done else "↩️ Mark not done", type="primary", use_container_width=True,
               key=f"pd_{sig}"):
    if idx in done:
      ss.plan_done = sorted(done - {idx})
    else:
      ss.plan_done = sorted(done | {idx})
      ss.plan_idx = min(idx + 1, n - 1)
    ss.plan_qa = None
    st.rerun()
  if b3.button("Skip ➡️", disabled=idx >= n - 1, use_container_width=True, key=f"ps_{sig}"):
    ss.plan_idx, ss.plan_qa = idx + 1, None
    st.rerun()
  q = st.columns(3)
  for i_, (k, (lab, ask)) in enumerate(STEP_QUESTIONS.items()):
    if q[i_].button(lab, use_container_width=True, key=f"pq_{sig}_{k}"):
      _dgr = diagram_for(str(cur.get("diagram") or ""), idx) if cur.get("diagram") else None
      _dg_img = [_dgr["b64"]] if _dgr and _dgr.get("b64") else ""
      with st.spinner("Asking..."):
        ans, who = quick_ai(f"Vehicle: {ss.vehicle_info or 'not given'}. Codes: {', '.join(current_codes()) or 'none'}.\n"
                            f"Current test step: {cur.get('title')} — {cur.get('do')} (where: {cur.get('where')}; "
                            f"pass/fail: {cur.get('pass_fail')}).\n\nQuestion: {ask}\nAnswer in plain words, under 180 words.\n\n"
                            + knowledge_block(f"{cur.get('title')} {cur.get('do')} {cur.get('where')} {cur.get('tools')}", 8)
                            + diagram_context()
                            + ("\nThe attached image is the technician's wiring diagram for this test — use its exact pins and colors."
                               if _dg_img else ""),
                            image_b64=_dg_img,
                            max_tokens=3000, effort="low")
      ss.plan_qa = {"idx": idx, "q": lab, "a": ans}
  qa = ss.get("plan_qa")
  if qa and qa.get("idx") == idx:
    st.info(f"**{qa['q']}**\n\n{qa['a']}")
  with st.expander("All steps"):
    for i_, stp in enumerate(steps):
      mark = "✅" if i_ in done else ("👉" if i_ == idx else "⬜")
      found = (ss.plan_notes or {}).get(str(i_), "")
      st.markdown(f"{mark} **{i_ + 1}. {stp.get('title')}**" + (f" — _found: {found}_" if found else ""))
    if st.button("🔄 Rebuild the cards from the plan", key=f"pr_{sig}"):
      if build_step_cards():
        st.rerun()


def plan_progress_text() -> str:
  ps = ss.get("plan_steps") or {}
  if ps.get("_for") != _plan_sig() or not ps.get("steps"):
    return ""
  done = set(ss.plan_done or [])
  lines = [f"- {'DONE' if i in done else 'not done'}: {s_.get('title')}"
           + (f" — tech found: {(ss.plan_notes or {}).get(str(i))}" if (ss.plan_notes or {}).get(str(i)) else "")
           for i, s_ in enumerate(ps["steps"])]
  return "STEP-BY-STEP PROGRESS ON THE TEST PLAN:\n" + "\n".join(lines)


def _num_from(text) -> float | None:
  m = re.search(r"[-+]?\d+(?:\.\d+)?", str(text or ""))
  return float(m.group(0)) if m else None


def status_cards():
  """Big, plain cards: battery, codes, fuel trim, engine temp, and anything that doesn't add up. Never shows a number
  that wasn't actually read — 'not read yet' instead."""
  sd = ss.scan_data or {}
  pids = sd.get("pids") or {}
  at = sd.get("at")
  def card(col, cls, title, big, small):
    col.markdown(f'<div class="tdg-card {cls}"><b>{title}</b><div class="tdg-big">{big}</div><small>{small}</small></div>',
                 unsafe_allow_html=True)
  c = st.columns(4)
  volt, rpm = _num_from(pids.get("Battery Volt")), _num_from(pids.get("Engine RPM"))
  if volt is None:
    card(c[0], "tdg-gray", "🔋 Battery", "Not read yet", "Connect the scanner")
  elif rpm and rpm > 400:
    ok = 13.5 <= volt <= 15.0
    card(c[0], "tdg-green" if ok else "tdg-red", "🔋 Charging", f"{volt:.1f} V",
         "Alternator charging normally" if ok else ("Low — check alternator, belt, cables" if volt < 13.5 else "High — overcharging"))
  else:
    cls, word = ("tdg-green", "Fully charged") if volt >= 12.4 else (("tdg-yellow", "A bit low") if volt >= 12.2 else ("tdg-red", "Low — test the battery"))
    card(c[0], cls, "🔋 Battery (engine off)", f"{volt:.1f} V", word)
  codes = current_codes()
  card(c[1], "tdg-green" if not codes else "tdg-red", "🚨 Trouble codes", f"{len(codes)} code(s)" if codes else "None",
       ", ".join(codes[:5]) if codes else ("No codes stored" if sd else "Connect the scanner or type codes"))
  st1, lt1 = _num_from(pids.get("STFT B1")), _num_from(pids.get("LTFT B1"))
  if st1 is None or lt1 is None:
    card(c[2], "tdg-gray", "⛽ Fuel trim", "Not read yet", "Shows once the engine is running")
  else:
    tot = st1 + lt1
    cls = "tdg-green" if abs(tot) <= 10 else ("tdg-yellow" if abs(tot) <= 15 else "tdg-red")
    word = "Balanced" if abs(tot) <= 10 else ("Adding fuel — running LEAN" if tot > 0 else "Pulling fuel — running RICH")
    card(c[2], cls, "⛽ Fuel trim (bank 1)", f"{tot:+.0f}%", word + " · normal is within ±10%")
  ect = _num_from(pids.get("Coolant (ECT)"))
  flags = sd.get("flags") or []
  if flags:
    card(c[3], "tdg-red", "⚠️ Doesn't add up", f"{len(flags)} reading(s)", re.sub(r"<[^>]+>", "", flags[0])[:90])
  elif ect is None:
    card(c[3], "tdg-gray", "🌡️ Engine temp", "Not read yet", "Connect the scanner")
  else:
    cls, word = (("tdg-red", "Overheating!") if ect > 230 else ("tdg-green", "Warmed up") if ect >= 180
                 else ("tdg-blue", "Still warming up — idle and trims aren't final yet"))
    card(c[3], cls, "🌡️ Engine temp", f"{ect:.0f}°F", word)
  if at:
    st.caption(f"Readings from the last scan ({at}).")


def pro_section(name: str):
  """A section that Simple view hides (still loaded, so nothing typed in it is lost)."""
  try:
    return st.container(key=f"pro_{name}")
  except TypeError:   # older Streamlit without keyed containers: just show it
    return st.container()


tab0, tab1, tab3, tab_scope, tab_ro, tab_sites, tab_more = st.tabs(["Chat", "Vehicle Scan", "Diagnostics", "Scope & Tests",
                                                                     "Customer & RO", "Sites", "More"])


def _keyed_box(k: str):
  try:
    return st.container(key=k)
  except TypeError:   # older Streamlit without keyed containers: everything shows
    return st.container()


# ☰ More: the cars in the shop, the log and Knowledge — one shows at a time (the others stay loaded, just hidden)
with tab_more:
  _more_opts = ["🚗 Cars in the shop", "📋 Log & history", "📖 Knowledge"]
  _more = st.radio("More", _more_opts, horizontal=True, key="more_pick", label_visibility="collapsed")
  tab_cars, tab5, tab6 = _keyed_box("more_cars"), _keyed_box("more_log"), _keyed_box("more_know")
  st.markdown("<style>" + "".join(f".st-key-{k} {{ display: none !important; }}"
                                  for k, o in zip(("more_cars", "more_log", "more_know"), _more_opts) if o != _more)
              + "</style>", unsafe_allow_html=True)

# ========================================================
# --- 💬 CHAT (the front screen) + 🚗 cars in the shop (under ☰ More) ---
# ========================================================
def _local_now() -> datetime:
  try:
    from zoneinfo import ZoneInfo
    tz = getattr(st.context, "timezone", None) or secret("TIMEZONE") or "America/New_York"
    return datetime.now(ZoneInfo(tz))
  except Exception:
    return datetime.now()


def home_cars():
  """🚗 Cars in the shop as cards — open one, start a new one, close the one you're on, reopen a closed one."""
  e = html_lib.escape
  if not store_on():
    st.warning("⚠️ Permanent storage isn't set up yet, so jobs are erased when the app restarts. Add SUPABASE_URL and "
               "SUPABASE_KEY to Secrets (⚙️ top right).")
  elif ss.get("_store_err"):
    st.warning(f"⚠️ Last save had a problem: {ss._store_err} (details in ☰ More → 📋 Log → 🐞 Problem log)")
  cur = ss.get("job_id")
  st.markdown('<div class="tdg-label">Current car</div>', unsafe_allow_html=True)
  with st.container(key="carnow"):
    if job_has_content(job_snapshot()):
      st.markdown(f'<div class="tdg-car"><div class="m">{e(ss.customer_name or "no customer")}'
                  f'{(" · " + e(ss.odometer) + " mi") if (ss.odometer or "").strip() else ""}</div>'
                  f'<div class="v">{e(ss.vehicle_info or "Vehicle not set")}</div>'
                  f'<div class="codes">{e(ss.active_dtc or "no codes")}</div></div>', unsafe_allow_html=True)
      c1, c2 = st.columns(2)
      if c1.button("➕ Start a new car", use_container_width=True, key="home_new"):
        ss._job_request = "new"
        st.rerun()
      if cur and c2.button("✅ Car is done — close it", use_container_width=True, key="home_close"):
        ss.job_status = "closed"
        autosave_job(force=True)
        ss._job_request = "new"
        ss._toast = "Job closed"
        st.rerun()
    else:
      st.markdown('<div class="tdg-car"><div class="v">No car open</div><div class="m">Start one on 🚗 Vehicle Scan — VIN '
                  'search or connect the scanner</div></div>', unsafe_allow_html=True)
  jobs = [r for r in store_list("job", 60, {"status": "open"}) if r["id"] != cur]
  if jobs:
    st.markdown(f'<div class="tdg-label">Cars in the shop · {len(jobs) + (1 if cur else 0)} open</div>', unsafe_allow_html=True)
    for r in jobs[:12]:
      d = r.get("data") or {}
      with st.container(key=f"jobcard_{re.sub(r'[^A-Za-z0-9_-]', '', r['id'])}"):
        a, b = st.columns([5, 1.3])
        a.markdown(f'<div class="tdg-car"><div class="v">{e(d.get("vehicle_info") or "Vehicle not set")}</div>'
                   f'<div class="m">{e(d.get("customer_name") or "no name")} · updated {e(d.get("updated", ""))}</div>'
                   f'<div class="codes">{e(d.get("codes") or "no codes")}</div></div>', unsafe_allow_html=True)
        if b.button("Open →", key=f"open_{r['id']}", use_container_width=True):
          ss._job_request = r["id"]
          st.rerun()
  closed = store_list("job", 25, {"status": "closed"})
  if closed:
    with st.expander(f"Closed jobs ({len(closed)})"):
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


def job_bar():
  """Top of 🚗 Vehicle Scan: start a new car, jump to another car in the shop, or close this one."""
  cur = ss.get("job_id")
  jobs = [r for r in store_list("job", 60, {"status": "open"}) if r["id"] != cur]
  has_car = job_has_content(job_snapshot())
  with _keyed_box("jobbar"):
    c1, c2, c3 = st.columns([1.1, 2.2, 1.2])
    if c1.button("➕ New car", key="jb_new", use_container_width=True, disabled=not has_car,
                 help="Saves this car and starts a clean one"):
      ss._job_request = "new"
      st.rerun()
    if jobs:
      pick = c2.selectbox("Switch car", [r["id"] for r in jobs], index=None, label_visibility="collapsed",
                          placeholder=f"🔁 Switch car — {len(jobs)} more in the shop",
                          format_func=lambda i: next(f"{(r.get('data') or {}).get('vehicle_info') or 'Vehicle not set'} · "
                                                     f"{(r.get('data') or {}).get('customer_name') or 'no name'}"
                                                     for r in jobs if r["id"] == i), key=f"jb_pick_{ss.get('job_n', 0)}")
      if pick:
        ss._job_request = pick
        st.rerun()
    else:
      c2.caption("No other cars open — all the cars in the shop are under ☰ More")
    if cur and has_car and c3.button("✅ Car is done", key="jb_close", use_container_width=True,
                                     help="Closes this job (reopen it any time under ☰ More → 🚗 Cars in the shop)"):
      ss.job_status = "closed"
      autosave_job(force=True)
      ss._job_request = "new"
      ss._toast = "Job closed"
      st.rerun()


with tab0, guard("Chat"):
  # 💬 the chat — filled in at the very end of the script (it needs helpers defined further down), shown right here
  _quick_box = st.container()

with tab_cars, guard("Cars in the shop"):
  home_cars()


# ========================================================
# --- 🔗 SITES: one tap to your repair sites (you log in yourself — the app only opens the link) ---
# ========================================================
DEFAULT_LINKS = [("ALLDATA", "https://www.alldata.com"), ("ProDemand", "https://www.prodemand.com"),
                 ("Identifix", "https://www.identifix.com"), ("MOTOLOGIC", "https://www.motologic.com")]


def _clean_url(u: str) -> str:
  u = str(u or "").strip()
  if u and not re.match(r"(?i)^https?://", u):
    u = "https://" + u
  return u if re.match(r"(?i)^https?://[^\s/$.?#][^\s]*$", u) else ""


def repair_links() -> list[dict]:
  """The shop's saved links, in order. The first time, the four repair sites are filled in so you can edit them."""
  rows = [dict(r.get("data") or {}, _id=r["id"]) for r in store_list("link", 100)]
  if not rows and not ss.get("_links_seeded"):
    ss._links_seeded = True
    if store_get("setting", "links_seeded"):   # filled in once already; you removed them, so they stay removed
      return []
    store_put("setting", "links_seeded", {"at": datetime.now().strftime("%Y-%m-%d")})
    for i, (n, u) in enumerate(DEFAULT_LINKS):
      store_put("link", f"L{i:02d}", {"name": n, "url": u, "order": i})
    rows = [dict(r.get("data") or {}, _id=r["id"]) for r in store_list("link", 100)] or \
           [{"name": n, "url": u, "order": i, "_id": f"L{i:02d}"} for i, (n, u) in enumerate(DEFAULT_LINKS)]
  return sorted((r for r in rows if r.get("url")), key=lambda r: (r.get("order", 99), str(r.get("name", "")).lower()))


with tab_sites, guard("Sites"):
  st.subheader("🔗 Sites")
  if ss.get("active_vin"):
    st.caption("This car's VIN — tap the copy icon, then paste it into the site:")
    st.code(ss.active_vin, language=None)
  _links = repair_links()
  for _l in _links:
    st.link_button(f"🔗 {_l.get('name') or _l['url']}", _l["url"], use_container_width=True)
  if not _links:
    st.caption("No links yet — add one below.")
  st.caption("Each one opens in a new browser tab and you log in yourself, same as always. The app keeps this page open.")
  with st.expander("➕ Add a link", expanded=not _links):
    with st.form("add_link", clear_on_submit=True):
      _ln = st.text_input("Name", placeholder="e.g. Mitchell 1 TruckSeries, Ford PTS, Tech Authority")
      _lu = st.text_input("Web address", placeholder="e.g. www.motorcraftservice.com")
      if st.form_submit_button("💾 Save link", type="primary"):
        _u = _clean_url(_lu)
        if not _u:
          st.warning("That web address doesn't look right — copy it from the browser's address bar.")
        else:
          store_put("link", "L" + datetime.now().strftime("%Y%m%d%H%M%S%f"),
                    {"name": (_ln or "").strip() or re.sub(r"(?i)^https?://(www\.)?", "", _u).split("/")[0], "url": _u,
                     "order": max([int(x.get("order", 0) or 0) for x in _links] + [0]) + 1})
          queue_update(toast="🔗 Link saved")
  if _links:
    with st.expander("✏️ Change, reorder or remove links"):
      for _i, _l in enumerate(_links):
        with st.container(border=True):
          _n2 = st.text_input("Name", value=_l.get("name", ""), key=f"lk_n_{_l['_id']}")
          _u2 = st.text_input("Web address", value=_l.get("url", ""), key=f"lk_u_{_l['_id']}")
          _c1, _c2, _c3, _c4 = st.columns(4)
          if _c1.button("💾 Save", key=f"lk_s_{_l['_id']}", use_container_width=True):
            if _clean_url(_u2):
              store_put("link", _l["_id"], {"name": _n2.strip() or _l.get("name", ""), "url": _clean_url(_u2), "order": _l.get("order", _i)})
              queue_update(toast="🔗 Link updated")
            else:
              st.warning("That web address doesn't look right.")
          if _c2.button("⬆️ Up", key=f"lk_up_{_l['_id']}", use_container_width=True, disabled=_i == 0):
            _o = _links[_i - 1]
            store_put("link", _l["_id"], {k: v for k, v in _l.items() if k != "_id"} | {"order": _i - 1})
            store_put("link", _o["_id"], {k: v for k, v in _o.items() if k != "_id"} | {"order": _i})
            st.rerun()
          if _c3.button("⬇️ Down", key=f"lk_dn_{_l['_id']}", use_container_width=True, disabled=_i == len(_links) - 1):
            _o = _links[_i + 1]
            store_put("link", _l["_id"], {k: v for k, v in _l.items() if k != "_id"} | {"order": _i + 1})
            store_put("link", _o["_id"], {k: v for k, v in _o.items() if k != "_id"} | {"order": _i})
            st.rerun()
          if _c4.button("🗑️ Remove", key=f"lk_d_{_l['_id']}", use_container_width=True):
            store_delete("link", _l["_id"])
            st.rerun()


# ========================================================
# --- 🚗 VEHICLE SCAN: VIN search at the top, the scanner right under it ---
# ========================================================
with tab1:
  # two fixed boxes, so the scanner never moves in the page (moving it would drop the Bluetooth link)
  _veh_box, _scan_box = st.container(), st.container()

with _veh_box, guard("Vehicle Scan — VIN search"):
  context_bar()
  job_bar()
  st.markdown("#### 🔎 VIN search")
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
          else:
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

    # 📣 What owners of this model complain about
    comps = vehicle_complaints()
    if comps:
      top, like = complaint_summary(comps)
      with st.expander(f"📣 {len(comps)} owner complaint(s) filed with NHTSA — most reported: "
                       f"{', '.join(n.title() for n, _ in top[:3])}"):
        st.caption("What owners of this year/make/model reported to NHTSA. Useful for spotting pattern failures; "
                   "they're owner reports, not confirmed fixes.")
        st.dataframe([{"System": n.title(), "Complaints": k} for n, k in top], use_container_width=True, hide_index=True)
        if like:
          st.markdown("**Complaints that sound like this car** (matched to the codes and symptoms):")
          for c in like:
            st.markdown(f"- _{c['components'].title()}_ — {c['summary'][:350]}{'…' if len(c['summary']) > 350 else ''}")


# ========================================================
# --- 🧾 CUSTOMER & RO: the customer first (the repair order is further down the script) ---
# ========================================================
with tab_ro, guard("Customer info"):
  context_bar()
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
  st.caption("📄 Got a work order? On 🚗 Vehicle Scan open 📸 Read the VIN from a photo and tap "
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
  <div id="ecuBox" class="box" style="display:none"></div>
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
  <div class="bar" style="margin-bottom:6px"><button id="huntBtn" class="tbtn" disabled>🔎 Find every reading this car has</button>
    <span class="note">Runs by itself the first time a car is connected. Tries every factory request on file for this make and its
    sister brands and keeps the ones this car answers — 1 to 4 minutes, key on (engine running is best). What it finds is saved for next time.</span></div>
  <div id="huntBox" class="box" hidden></div>
  <div id="enhBox" class="enh"><div class="box">Factory-level readings appear here as each module answers.</div></div>
  <div class="note" style="margin:-10px 0 16px">Every standard (SAE) reading this car supports is under the "Std" groups. Factory definitions come from the open OBD database (OBDb, github.com/OBDb, CC BY-SA 4.0). Some are model-year specific, so sanity-check new readings against a factory scan tool. ≈ = from a sister brand's list.</div>

  <h3 style="color:var(--b)">📋 I/M READINESS</h3>
  <div id="readyBox" class="box">Loads automatically on connect.</div>

  <h3 style="color:var(--b)">📊 MODE $06 TEST RESULTS</h3>
  <div id="m6Box" class="box">Loads automatically on connect.</div>

  <h3 style="color:var(--o)">🤖 AI MASTER TECH EVALUATION</h3>
  <div id="runBox" class="box" style="display:none;border-color:var(--o)"></div>
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
  const changed = a.make !== ARGS.make || String(a.year) !== String(ARGS.year) || a.oem_src !== ARGS.oem_src ||
    ((a.learned_id || "") !== (ARGS.learned_id || "") && a.learned_id !== myLearnedId);
  if (a.vmake !== ARGS.vmake || a.vmodel !== ARGS.vmodel || String(a.year) !== String(ARGS.year)) autoHuntTried = false;
  ARGS = a;
  if (changed && connected) buildEnhanced();
  if (a.ai && a.ai.id && a.ai.id !== lastAiShown) {
    lastAiShown = a.ai.id;
    if (a.ai.id === aiPendingId) aiPendingId = null;
    showAi(a.ai.text, a.ai.label);
    if (typeof offerTests === "function") offerTests(a.ai.tests || []);
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
let baseProto = "6", curProto = "6", curCra = "", curPri = "";
const base29 = () => baseProto === "7" || baseProto === "9";            // the car's own OBD network uses 29-bit IDs (most Hondas)
const funcHeader = () => (base29() ? "DB33" : "7DF");                   // "everyone answer": 7DF, or 18 DB 33 F1 on 29-bit cars
// Point the adapter at one module.
//  3-char headers are 11-bit CAN (7E0, 700, 7B0...). 4-char headers are 29-bit: the ID sent is  pri + hdr + tester.
//    pri = priority byte: 18 normally (18 DA 10 F1 — Honda, newer Stellantis), 14 on newer GM, 17 on VW group, 1D on Volvo / Mazda
//    tst = tester address: F1 normally
//  rax = where the reply comes from: 2 digits = the module's address · 6 digits = the reply ID under the same priority
//        · 8 digits = the whole reply ID · none = worked out from the header.
async function setAddr(hdr, rax, pri, tst) {
  if (!isCan) return;
  const ext = hdr.length === 4;
  const b29 = base29();
  const want = ext ? (b29 ? baseProto : String(+baseProto + 1)) : (b29 ? String(+baseProto - 1) : baseProto);
  if (want !== curProto) {
    await sendCmd("ATSP" + want, 500);
    curProto = want; curHeader = ""; curCra = "?"; curPri = "";
  }
  let full = hdr, cra = "";
  rax = String(rax || "").toUpperCase();
  if (ext) {
    const p = String(pri || "18").toUpperCase(), t = String(tst || "F1").toUpperCase();
    if (p !== curPri) { await sendCmd("ATCP" + p, 400); curPri = p; }
    full = hdr + t;
    if (rax.length === 8) cra = rax;
    else if (rax.length === 6) cra = p + rax;
    else if (hdr.startsWith("DA")) cra = p + "DA" + t + (rax || hdr.slice(2));
  } else if (rax) cra = rax;
  else if (hdr !== "7DF" && !/^7E[0-7]$/.test(hdr)) cra = (parseInt(hdr, 16) + 8).toString(16).toUpperCase();
  if (full !== curHeader) { await sendCmd("ATSH" + full, 500); curHeader = full; }
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
  "49": { tile: "app", tier: 1, len: 1, fn: pct },   // gas pedal: read every pass, the glitch catcher needs it
  "4A": { tile: "app", tier: 1, len: 1, fn: pct },   // pedal sensor E, for cars that skip D
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
    timing: ["0E"], maf: ["10"], map: ["0B"], app: ["49", "4A"], ect: ["05"], iat: ["0F"], aat: ["46"], eot: ["5C"],
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
  switch (sig.unit || "") {
    case "C": return x <= -39.5 || x > 300 ? null : degF(x) + " °F";
    case "F": return x <= -39.5 || x > 570 ? null : Math.round(x) + " °F";
    case "kPa": return r1(x * 0.145038) + " psi";
    case "bar": return r1(x * 14.5038) + " psi";
    case "psi": return r1(x) + " psi";
    case "kph": return Math.round(x * 0.621371) + " mph";
    case "km": return Math.round(x * 0.621371).toLocaleString() + " mi";
    case "Nm": return Math.round(x * 0.737562) + " lb-ft";
    case "L/h": return (x * 0.264172).toFixed(2) + " gal/h";
    case "gps": return r1(x) + " g/s";
    case "s": return x >= 600 ? Math.floor(x / 3600) + " h " + Math.floor((x % 3600) / 60) + " min" : r1(x) + " s";
    case "onoff": case "onoff2": return x ? "ON" : "OFF";
    case "yesno": case "noyes": return x ? "YES" : "NO";
    case "hex": return v.toString(16).toUpperCase();
    case "V": return x.toFixed(2) + " V";
    case "%": return r1(x) + "%";
    case "deg": return r1(x) + "°";
    case "": return String(r1(x));
    default: return r1(x) + (sig.unit ? " " + sig.unit : "");
  }
}
// Readings that can't physically be right mean the factory data list doesn't fit this car (wrong year or layout): hide them.
function oemSane(g, text) {
  const n = String(g.name || "").toLowerCase(), val = toNumber(text);
  if (/navigation|gps|latitude|longitude|compass|altitude/.test(n)) return false;
  if (val == null || !isFinite(val)) return true;
  const psi = / psi$/.test(text), pctU = /%$/.test(text);
  if (/baro/.test(n)) return !psi || (val >= 7 && val <= 16.5);
  if (/(tank|evap|vapou?r).*press|press.*(tank|evap|vapou?r)/.test(n)) return !psi || Math.abs(val) <= 3;
  if (psi && val > 400 && !/rail|fuel press|inject|high.?press|hydraul|brake|line press|clutch|oil press|refrig|a\/c|ac press|boost|turbo/.test(n)) return false;
  if (/ratio/.test(n) && !pctU) return /speed ratio|slip/.test(n) ? val >= 0 && val <= 2.5 : val >= 0 && val <= 8;
  if (/steer/.test(n) && /angle/.test(n)) return Math.abs(val) <= 1000;
  if (/rpm|engine speed|turbine speed|shaft speed/.test(n) && !pctU) return val >= -50 && val <= 12000;
  if (/ V$/.test(text)) return val >= -1 && val <= 32;
  if (pctU) return val >= -150 && val <= 250;
  if (/ mph$/.test(text)) return val >= 0 && val <= 200;
  return true;
}
// A factory reading that disagrees with the same thing read the standard way = that request is decoded wrong on this car.
function oemDisagrees(g, text) {
  const n = String(g.name || "").toLowerCase(), val = toNumber(text);
  if (val == null || !isFinite(val)) return false;
  const off = (a, b, tol) => Math.abs(a - b) > tol;
  if (/baro/.test(n) && / psi$/.test(text) && fresh("baro", 60)) { const std = num.baro * 0.4912; return off(val, std, Math.max(0.8, std * 0.1)); }
  if (/fuel level/.test(n) && /%$/.test(text) && fresh("fli", 60)) return off(val, num.fli, 15);
  if (/^(engine )?(speed|rpm)$|^engine rpm$/.test(n) && fresh("rpm", 3)) return off(val, num.rpm, Math.max(200, num.rpm * 0.2));
  if (/coolant temp/.test(n) && /°F$/.test(text) && fresh("ect", 60)) return off(val, num.ect, 20);
  return false;
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
  "Chassis, ABS & steering", "Wheel speeds & motion", "Climate & A/C", "Std · engine", "Std · fuel & O2",
  "Std · emissions & diesel", "Std · hybrid / EV", "More standard readings", "Other"];
const GROUP_CLOSED = new Set(["Chassis, ABS & steering", "Wheel speeds & motion", "Climate & A/C", "Std · engine", "Std · fuel & O2",
  "Std · emissions & diesel", "Std · hybrid / EV", "More standard readings", "Other"]);
function oemGroup(sig) {
  if (sig.grp) return sig.grp;
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
// Torque converter readings the TCC test uses: actual slip, desired slip, the TCC command %, apply state, turbine speed
function tccRole(name, unit, map) {
  const n = String(name || "").toLowerCase();
  if (/turbine (shaft )?speed|input shaft speed|\btss\b/.test(n) && !/desired|target/.test(n)) return "turbine";
  if (!/torque conv|converter clutch|\btcc\b|tc slip|lock.?up/.test(n) || /temp/.test(n)) return "";
  if (/slip/.test(n)) return /desired|target|command/.test(n) ? "tccdes" : "tcc";
  if (/duty|pwm|percent/.test(n) || unit === "%") return "tccduty";
  if (/command|status|state|apply|engag|mode|lock/.test(n) && (map || /onoff|yesno|noyes/.test(String(unit || "")))) return "tccstate";
  return "";
}
function buildEnhanced() {
  const year = parseInt(ARGS.year, 10) || 0;
  const model = usingModelData();
  const base = !isCan ? [] : model ? ARGS.oem : (OEM_DB[profile()] || []).filter((g) => yearOk(g.yrs, year));
  // what 🔎 Find every reading found on this car before (standard readings are built in now, so old saved ones are dropped)
  const learned = isCan && Array.isArray(ARGS.learned) ? ARGS.learned.filter((g) => !String(g.req || "").startsWith("01")) : [];
  const lkeys = new Set(learned.map(cmdKey));
  // every other standard reading this car says it supports (the main screen already shows the common ones)
  const std = isCan && sup01 ? STD_SIGS.filter((g) => sup01.has(g.req.slice(2))).map((g) => Object.assign({}, g, { hdr: baseHeader })) : [];
  const sigs = [...learned, ...base.filter((g) => !lkeys.has(cmdKey(g))), ...std].map((g) => Object.assign({}, g));
  const byCmd = new Map();
  sigs.forEach((g) => {
    prepSig(g);
    const k = cmdKey(g);
    if (!byCmd.has(k)) byCmd.set(k, { hdr: g.hdr, rax: g.rax || "", req: g.req, pri: g.pri, tst: g.tst, din: g.din, dout: g.dout,
                                      std: !!g.std, sigs: [], state: "new", miss: 0 });
    byCmd.get(k).sigs.push(g);
  });
  oemCmds = [...byCmd.values()];
  if (!model) {
    // Make-level list mixes layouts from several models: keep one layout per quantity so values never conflict.
    oemCmds.forEach((c) => {
      if (c.std) return;
      const seen = new Set();
      c.sigs = c.sigs.filter((g) => (seen.has(g.label) ? false : (seen.add(g.label), true)));
    });
  }
  // Probe the most useful systems first
  // standard readings first (the car already said it has them), then the most useful systems
  const rank = (c) => (c.std ? -1 : Math.min(...c.sigs.map((g) => { const i = GROUP_ORDER.indexOf(g.group); return i < 0 ? 99 : i; })));
  oemCmds.sort((a, b) => rank(a) - rank(b));
  oemRR = 0; oemFound = 0; oemModules = {}; oemTile.n = 0;
  $("enhBox").innerHTML = '<div class="box">' + (oemCmds.length
    ? `Checking ${oemCmds.length} requests (${esc(oemSourceName() || "standard readings")}${learned.length ? " + what this car taught the app" : ""})…`
    : (isCan ? "No factory definitions for this exact vehicle yet. Tap 🔎 Find every reading this car has to try every list for this make."
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
  LABEL[id] = sig.std ? `${sig.label} [PID ${sig.req.slice(2)}]` : `${sig.label} [OEM ${sig.hdr} ${sig.req}]`;
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
const sessAt = {}, sessOut = new Map();   // sessions this pass opened: when, and how to close them again
async function readOem(cmd, retry = true) {
  await setAddr(cmd.hdr, cmd.rax, cmd.pri, cmd.tst);
  if (cmd.din) {   // this request only answers inside a diagnostic session (Nissan's 10 C0, some Stellantis 10 03): open it first
    const k = cmd.hdr + "|" + cmd.din;
    if (sessAt[k] === false) return { bytes: null, replied: true };   // this module refused the session: don't keep asking
    if (!(sessAt[k] && performance.now() - sessAt[k] < 2500)) {   // sessions lapse after a few seconds: open it again
      const r = messages(await sendCmd("10" + cmd.din, 1200));
      if (r.some((m) => m.startsWith("50" + cmd.din))) {
        sessAt[k] = performance.now();
        if (cmd.dout) sessOut.set(k, cmd);
      } else if (r.some((m) => m.startsWith("7F10"))) { sessAt[k] = false; return { bytes: null, replied: true }; }
      else return { bytes: null, replied: r.length > 0 };
    }
  }
  const pre = respCode(cmd.req.slice(0, 2)) + cmd.req.slice(2);
  const nrc = (ms) => { const m = ms.find((x) => x.startsWith("7F")); return m ? m.slice(4, 6) : ""; };
  let msgs = messages(await sendCmd(cmd.req, 500));
  if (!msgs.some((m) => m.startsWith(pre)) && nrc(msgs) === "78") msgs = messages(await sendCmd(cmd.req, 2500));
  for (const m of msgs) if (m.startsWith(pre)) return { bytes: bytesOf(m.slice(pre.length)), replied: true };
  const code = nrc(msgs);
  if (retry && !cmd.din && cmd.req.startsWith("22") && (code === "7E" || code === "7F") && extSession[cmd.hdr] !== false) {
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
// Put modules back in their normal session when the list says how (Nissan: 10 81)
async function closeSessions() {
  for (const [k, cmd] of sessOut) {
    try { await setAddr(cmd.hdr, cmd.rax, cmd.pri, cmd.tst); await sendCmd("10" + cmd.dout, 600); } catch (e) {}
    delete sessAt[k];
  }
  sessOut.clear();
}
// One request's data bytes -> the readings in it. wrong = it disagrees with the same thing read the standard way.
function decodeCmd(c, bytes) {
  const vals = [];
  for (const g of c.sigs) {
    if (g.sup != null && !((bytes[g.sup >> 3] >> (7 - (g.sup & 7))) & 1)) continue;   // the car says this sensor isn't fitted
    const v = extractBits(bytes, g.bix, g.len, g.lsb, g.sign);
    const text = v == null ? null : fmtOem(g, v);
    if (text == null) continue;
    if (!g.std && oemDisagrees(g, text)) return { vals: [], wrong: true };
    if (g.std || oemSane(g, text)) vals.push([g, text]);
  }
  return { vals, wrong: false };
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
    const mk = c.hdr + "|" + (c.pri || "") + "|" + (c.tst || "");
    const mod = oemModules[mk] || (oemModules[mk] = { alive: false, silent: 0 });
    const { bytes, replied } = await readOem(c);
    if (replied || bytes) mod.alive = true; else mod.silent++;
    let any = false;
    const { vals, wrong } = bytes ? decodeCmd(c, bytes) : { vals: [], wrong: false };
    if (wrong) {   // it disagrees with the same reading done the standard way: this request's layout doesn't fit this car
      c.state = "dead";
      c.sigs.forEach((g) => { delete shown[oemTile(g)]; delete num[oemTile(g)]; });
      logEvent("scanner", "Enhanced PIDs", `Hid ${c.req} (${c.sigs.length} readings): they don't match the standard readings, so that factory layout doesn't fit this car`);
      continue;
    }
    for (const [g, text] of vals) { any = true; setTile(oemTile(g), text); }
    if (c.state === "new") c.state = any ? "live" : "dead";
    else if (any) c.miss = 0;
    else if (++c.miss >= 3) c.state = "dead";
    // A module that never answers (not fitted on this car): skip the rest of its requests
    if (!mod.alive && mod.silent >= 2) oemCmds.forEach((o) => {
      if (o.hdr === c.hdr && (o.pri || "") === (c.pri || "") && (o.tst || "") === (c.tst || "") && o.state === "new") o.state = "dead"; });
  }
  await closeSessions();
  await setAddr(baseHeader, "");
  updateEnhNote();
  if (oemCmds.length && !oemFound && oemCmds.every((c) => c.state !== "new"))
    $("enhBox").innerHTML = '<div class="box">This vehicle did not answer any of the factory requests on file for it.</div>';
}

// ===================== 🔎 Find every reading this car has =====================
// The open OBD database (OBDb) keeps a master factory data list for every make, plus a list for each model. This downloads
// the lists for this model, this make and its sister brands, tries every request on the car, keeps each one it answers,
// and sends them to the app to save — so next time this car (or one just like it) shows them right away.
// It runs by itself the first time a car is connected (once per year / make / model / engine), and from the button.
const OBDB_INDEX = `acura:Acura|Acura-CSX|Acura-ILX|Acura-Integra|Acura-MDX|Acura-RDX|Acura-TL|Acura-TLX|Acura-TSX|Acura-ZDX
aiways:Aiways|Aiways-U5
alfaromeo:Alfa-Romeo
audi:Audi|Audi-A1|Audi-A3|Audi-A3-e-tron|Audi-A4|Audi-A5|Audi-A6|Audi-A7|Audi-e-tron|Audi-e-tron-GT|Audi-Q2|Audi-Q3|Audi-Q4-e-tron|Audi-Q5|Audi-Q7|Audi-Q8|Audi-Q8-e-tron|Audi-RS-3|Audi-RS-5|Audi-RS-e-tron|Audi-S3|Audi-S4|Audi-S5|Audi-S6|Audi-SQ2|Audi-SQ5|Audi-SQ7|Audi-SQ8|Audi-TT|Audi-TTS
bentley:Bentley|Bentley-Bentayga
bmw:BMW|BMW-1-Series|BMW-2-Series|BMW-2-Series-Plug-in-Hybrid|BMW-3-Series|BMW-3-Series-eDrive|BMW-4-Series|BMW-5-Series|BMW-6-Series|BMW-6-Series-Gran-Coupe|BMW-6-Series-Gran-Turismo|BMW-7-Series|BMW-ALPINA-XB7|BMW-i3|BMW-i3s|BMW-i4|BMW-i5|BMW-i8|BMW-iX|BMW-iX1|BMW-iX3|BMW-M2|BMW-M3|BMW-M3-CS|BMW-M4|BMW-M5|BMW-X1|BMW-X2|BMW-X3|BMW-X4|BMW-X5|BMW-X5-M|BMW-X6|BMW-X7|BMW-XM|BMW-Z4
buick:Buick|Buick-Enclave|Buick-Encore|Buick-Envision|Buick-LaCrosse
byd:BYD|BYD-Sealion-6
cadillac:Cadillac|Cadillac-CT4|Cadillac-CT5|Cadillac-CT6|Cadillac-CTS|Cadillac-DTS|Cadillac-ELR|Cadillac-Escalade|Cadillac-LYRIQ|Cadillac-SRX|Cadillac-XT5
chevrolet:Chevrolet|Chevrolet-Avalanche|Chevrolet-Aveo|Chevrolet-Blazer|Chevrolet-Bolt-EUV|Chevrolet-Bolt-EV|Chevrolet-Camaro|Chevrolet-Caprice|Chevrolet-Cobalt|Chevrolet-Colorado|Chevrolet-Corvette|Chevrolet-Cruze|Chevrolet-Cruze-Limited|Chevrolet-Equinox|Chevrolet-Equinox-EV|Chevrolet-Express|Chevrolet-Express-Cargo|Chevrolet-HHR|Chevrolet-Impala|Chevrolet-Impala-Limited|Chevrolet-Malibu|Chevrolet-Orlando|Chevrolet-S-10|Chevrolet-Sail|Chevrolet-Silverado|Chevrolet-Silverado-1500|Chevrolet-Silverado-2500|Chevrolet-Silverado-3500|Chevrolet-Sonic|Chevrolet-Spark|Chevrolet-Spin|Chevrolet-Tahoe|Chevrolet-Trailblazer|Chevrolet-Traverse|Chevrolet-Trax|Chevrolet-Volt
chrysler:Chrysler|Chrysler-200|Chrysler-300|Chrysler-Pacifica
citroen:Citroen|Citroen-eC4-X
cupra:Cupra|Cupra-Born|Cupra-Formentor|Cupra-Leon|Cupra-Tavascan|Cupra-Terramar
dacia:Dacia|Dacia-Dokker|Dacia-Duster|Dacia-Sandero|Dacia-Spring
daihatsu:Daihatsu|Daihatsu-Hijet|Daihatsu-Terios
datsun:Datsun
dodge:Dodge|Dodge-Caliber|Dodge-Challenger|Dodge-Charger|Dodge-Dakota|Dodge-Dart|Dodge-Durango|Dodge-Grand-Caravan|Dodge-Hornet|Dodge-Journey
ds:DS
fiat:Fiat|FIAT-500|FIAT-500e|FIAT-500X|FIAT-Bravo|FIAT-Fastback|FIAT-Panda|FIAT-Qubo
ford:Ford|Ford-B-Max|Ford-Bronco|Ford-Bronco-Sport|Ford-C-Max|Ford-C-Max-Energi|Ford-C-Max-Hybrid|Ford-Crown-Victoria|Ford-E-Series|Ford-E-Series-Wagon|Ford-EcoSport|Ford-Edge|Ford-Escape|Ford-Everest|Ford-Expedition|Ford-Explorer|Ford-Explorer-Sport-Trac|Ford-F-150|Ford-F-150-Lightning|Ford-F-250|Ford-F-350|Ford-Fiesta|Ford-Flex|Ford-Focus|Ford-Focus-Electric|Ford-Focus-RS|Ford-Focus-ST|Ford-Fusion|Ford-Fusion-Energi|Ford-Fusion-Hybrid|Ford-Kuga|Ford-Maverick|Ford-Mondeo|Ford-Mustang|Ford-Mustang-Mach-E|Ford-Puma|Ford-Ranger|Ford-S-Max|Ford-Taurus|Ford-Taurus-X|Ford-Territory|Ford-Tourneo|Ford-Transit|Ford-Transit-Connect
genesis:Genesis|Genesis-G70|Genesis-G80|Genesis-GV60|Genesis-GV80
gmc:GMC|GMC-Acadia|GMC-Canyon|GMC-Sierra-1500|GMC-Sierra-2500HD|GMC-Sierra-3500HD|GMC-Terrain|GMC-Yukon|GMC-Yukon-XL
haval:Haval|Haval-H6-HEV|Haval-Jolion|Haval-Jolion-HEV
holden:Holden|Holden-Colorado|Holden-Commodore|Holden-Cruze
honda:Honda|Honda-Accord|Honda-Accord-Hybrid|Honda-City|Honda-Civic|Honda-Clarity|Honda-CR-V|Honda-CR-V-Hybrid|Honda-CR-Z|Honda-Crosstour|Honda-Element|Honda-Fit|Honda-HR-V|Honda-Insight|Honda-Jazz|Honda-Odyssey|Honda-Pilot|Honda-Prelude|Honda-Prologue|Honda-Ridgeline|Honda-S2000|Honda-Shuttle|Honda-ZR-V
hyundai:Hyundai|Hyundai-Accent|Hyundai-Avante|Hyundai-Azera|Hyundai-Elantra|Hyundai-HB20|Hyundai-HB20S|Hyundai-i10|Hyundai-i20|Hyundai-i30|Hyundai-i40|Hyundai-IONIQ-5|Hyundai-IONIQ-6|Hyundai-IONIQ-9|Hyundai-IONIQ-Electric|Hyundai-IONIQ-PlugIn-Hybrid|Hyundai-Kona|Hyundai-Kona-Electric|Hyundai-Palisade|Hyundai-Santa-Cruz|Hyundai-Santa-Fe|Hyundai-Santa-Fe-Hybrid|Hyundai-Sonata|Hyundai-Tucson|Hyundai-Tucson-Hybrid|Hyundai-Veloster|Hyundai-Venue|Hyundai-Veracruz|Hyundai-Verna
infiniti:INFINITI|INFINITI-Q50|INFINITI-Q60|INFINITI-QX50|INFINITI-QX55|INFINITI-QX60|INFINITI-QX70|INFINITI-QX80
jaguar:Jaguar|Jaguar-E-PACE|Jaguar-F-PACE|Jaguar-F-TYPE|Jaguar-I-PACE
jeep:Jeep|Jeep-Avenger|Jeep-Cherokee|Jeep-Compass|Jeep-Gladiator|Jeep-Grand-Cherokee|Jeep-Grand-Wagoneer|Jeep-Patriot|Jeep-Renegade|Jeep-Wagoneer-L|Jeep-Wrangler|Jeep-Wrangler-4xe|Jeep-Wrangler-JK
kia:Kia|Kia-Cadenza|Kia-Carens|Kia-Carnival|Kia-Ceed|Kia-Cerato|Kia-EV3|Kia-EV6|Kia-EV9|Kia-Forte|Kia-K4|Kia-K5|Kia-Niro|Kia-Niro-EV|Kia-Optima|Kia-Picanto|Kia-Rio|Kia-Seltos|Kia-Sonet|Kia-Sorento|Kia-Soul|Kia-Soul-EV|Kia-Sportage|Kia-Sportage-HEV|Kia-Stinger|Kia-Stonic|Kia-Tasman|Kia-Telluride|Kia-XCeed
lamborghini:Lamborghini
landrover:Land-Rover|Land-Rover-Defender|Land-Rover-Discovery|Land-Rover-LR4|Land-Rover-Range-Rover|Land-Rover-Range-Rover-Evoque|Land-Rover-Range-Rover-Velar
lexus:Lexus|Lexus-CT-200h|Lexus-ES|Lexus-ES-300h|Lexus-GX|Lexus-GX-460|Lexus-GX-470|Lexus-IS|Lexus-LS-600h-L|Lexus-NX|Lexus-NX-350h|Lexus-RC|Lexus-RX|Lexus-UX
lincoln:Lincoln|Lincoln-MKC|Lincoln-MKZ|Lincoln-Nautilus|Lincoln-Navigator|Lincoln-Town-Car
lotus:Lotus
maserati:Maserati
mazda:Mazda|Mazda-2|Mazda-3|Mazda-5|Mazda-6|Mazda-B-Series-Pickup|Mazda-BT50|Mazda-CX-3|Mazda-CX-30|Mazda-CX-5|Mazda-CX-50|Mazda-CX-60|Mazda-CX-9|Mazda-CX-90|Mazda-Mazdaspeed-3|Mazda-Mazdaspeed-MX-5|Mazda-MX-30|Mazda-MX-5|Mazda-Tribute
mercedesbenz:Mercedes-Benz|Mercedes-Benz-A-180|Mercedes-Benz-B-Class|Mercedes-Benz-C-Class|Mercedes-Benz-CL-Class|Mercedes-Benz-CLK-Class|Mercedes-Benz-E-Class|Mercedes-Benz-EQA|Mercedes-Benz-EQB|Mercedes-Benz-EQV|Mercedes-Benz-G-Class|Mercedes-Benz-GLA-Class|Mercedes-Benz-GLC-Class|Mercedes-Benz-GLK-Class|Mercedes-Benz-M-Class|Mercedes-Benz-ML-350|Mercedes-Benz-SL-Class|Mercedes-Benz-SLC-Class|Mercedes-Benz-SLK-Class|Mercedes-Benz-Viano
mg:MG|MG-EHS|MG-HS|MG-MG4|MG-MG5|MG-One|MG-RX9|MG-ZS|MG-ZS-EV
mini:MINI|MINI-Clubman|MINI-Cooper|MINI-Cooper-SE|MINI-Countryman|MINI-Hardtop
mitsubishi:Mitsubishi|Mitsubishi-ASX|Mitsubishi-Eclipse-Cross|Mitsubishi-Outlander|Mitsubishi-Outlander-PHEV|Mitsubishi-Outlander-Sport|Mitsubishi-RVR|Mitsubishi-Triton
nissan:Nissan|Nissan-350Z|Nissan-370Z|Nissan-Altima|Nissan-ARIYA|Nissan-Armada|Nissan-Frontier|Nissan-Juke|Nissan-Kicks|Nissan-Leaf|Nissan-Maxima|Nissan-Micra|Nissan-Murano|Nissan-NV-Passenger|Nissan-Pathfinder|Nissan-Patrol|Nissan-Pulsar|Nissan-Qashqai|Nissan-Rogue|Nissan-Rogue-Sport|Nissan-Sentra|Nissan-Titan|Nissan-Titan-XD|Nissan-Versa|Nissan-X-Trail|Nissan-Xterra|Nissan-Z
nissaninfiniti:NissanInfiniti
peugeot:Peugeot|Peugeot-107|Peugeot-2008|Peugeot-207|Peugeot-208|Peugeot-3008|Peugeot-308|Peugeot-408|Peugeot-5008|Peugeot-508|Peugeot-e-208|Peugeot-Partner|Peugeot-RCZ
polestar:Polestar|Polestar-2|Polestar-4
porsche:Porsche|Porsche-718|Porsche-911|Porsche-Cayenne|Porsche-Cayman|Porsche-Macan|Porsche-Macan-Electric|Porsche-Panamera|Porsche-Taycan
ram:Ram|Ram-1500|Ram-1500-Classic|Ram-2500|Ram-3500|Ram-ProMaster-Window-Van
renault:Renault|Renault-Captur|Renault-Clio|Renault-Duster|Renault-Kadjar|Renault-Laguna|Renault-Megane|Renault-Megane-E-Tech|Renault-Scenic|Renault-Symbioz|Renault-Trafic|Renault-Twingo|Renault-ZOE
rollsroyce:Rolls-Royce
scion:Scion|Scion-FR-S|Scion-iQ|Scion-tC|Scion-xB
seat:SEAT|Seat-Alhambra|Seat-Arona|Seat-Ateca|Seat-Ibiza|Seat-Leon|Seat-Mii|Seat-Mii-Electric|Seat-Tarraco
skoda:Skoda|Skoda-Citigo-e-iV
smart:smart|smart-fortwo
subaru:Subaru|Subaru-Ascent|Subaru-BRZ|Subaru-Crosstrek|Subaru-Forester|Subaru-Impreza|Subaru-Legacy|Subaru-Outback|Subaru-Solterra|Subaru-Tribeca|Subaru-WRX
suzuki:Suzuki|Suzuki-Baleno|Suzuki-Jimny|Suzuki-Splash|Suzuki-Swift|Suzuki-Vitara|Suzuki-XL7
tata:Tata
toyota:Toyota|Toyota-4Runner|Toyota-Allion|Toyota-Aqua|Toyota-Auris|Toyota-Avalon|Toyota-Avalon-Hybrid|Toyota-Aygo|Toyota-bZ4X|Toyota-C-HR|Toyota-Camry|Toyota-Camry-Hybrid|Toyota-Corolla|Toyota-Corolla-Cross|Toyota-Corolla-Hybrid|Toyota-Crown|Toyota-FJ-Cruiser|Toyota-Fortuner|Toyota-GR-Corolla|Toyota-GR-Supra|Toyota-GR86|Toyota-Grand-Highlander|Toyota-Grand-Highlander-Hybrid|Toyota-GT86|Toyota-Hiace|Toyota-Highlander|Toyota-Hilux|Toyota-Land-Cruiser|Toyota-Land-Cruiser-Hybrid|Toyota-Matrix|Toyota-Mirai|Toyota-Prius|Toyota-Prius-Prime|Toyota-Prius-v|Toyota-RAV4|Toyota-RAV4-Hybrid|Toyota-RAV4-Prime|Toyota-Sequoia|Toyota-Sienna|Toyota-Sienna-Hybrid|Toyota-Tacoma|Toyota-Tundra|Toyota-Veloz|Toyota-Venza|Toyota-Venza-Hybrid|Toyota-Vios|Toyota-Yaris|Toyota-Yaris-Cross|Toyota-Yaris-iA
vauxhallopel:VauxhallOpel|VauxhallOpel-Corsa-e|VauxhallOpel-Mokka
volkswagen:Volkswagen|Volkswagen-Amarok|Volkswagen-Arteon|Volkswagen-Atlas|Volkswagen-Beetle|Volkswagen-Beetle-Convertible|Volkswagen-CC|Volkswagen-Crafter|Volkswagen-e-Golf|Volkswagen-e-Up|Volkswagen-Golf|Volkswagen-ID-Buzz|Volkswagen-ID.4|Volkswagen-ID3|Volkswagen-ID5|Volkswagen-ID7-Tourer|Volkswagen-Jetta|Volkswagen-Jetta-GLI|Volkswagen-Multivan|Volkswagen-Passat|Volkswagen-Polo|Volkswagen-Scirocco|Volkswagen-T-Cross|Volkswagen-T-Roc|Volkswagen-T6-Transporter|Volkswagen-Taigo|Volkswagen-Taos|Volkswagen-Tiguan|Volkswagen-Touareg|Volkswagen-Touran|Volkswagen-Transporter|Volkswagen-Up|Volkswagen-Virtus
volvo:Volvo|Volvo-S40|Volvo-S60|Volvo-S80|Volvo-S90|Volvo-V40|Volvo-V60|Volvo-XC40|Volvo-XC40-Recharge|Volvo-XC60|Volvo-XC90`;
const normName = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]/g, "");
const OBDB_REPOS = {};   // "chevrolet" -> ["Chevrolet", "Chevrolet-Tahoe", ...]  (the first one without a model is the make's master list)
OBDB_INDEX.split("\n").forEach((line) => { const i = line.indexOf(":"); OBDB_REPOS[line.slice(0, i)] = line.slice(i + 1).split("|"); });
const MAKE_ALIAS = { vauxhall: "vauxhallopel", opel: "vauxhallopel", mercedes: "mercedesbenz", alfa: "alfaromeo", vw: "volkswagen",
  marutisuzuki: "maruti", chevy: "chevrolet", ramtrucks: "ram" };
const FAMILY = {   // sister brands that share computers (and so most factory requests)
  chevrolet: ["gmc", "buick", "cadillac", "holden"], gmc: ["chevrolet", "buick", "cadillac"], buick: ["chevrolet", "gmc", "cadillac"],
  cadillac: ["chevrolet", "gmc", "buick"], holden: ["chevrolet", "gmc"], pontiac: ["chevrolet", "gmc", "buick"], saturn: ["chevrolet", "gmc"],
  oldsmobile: ["chevrolet", "buick"], hummer: ["chevrolet", "gmc"], saab: ["chevrolet", "cadillac"], isuzu: ["chevrolet", "gmc"],
  geo: ["chevrolet", "toyota"], daewoo: ["chevrolet"],
  ford: ["lincoln"], lincoln: ["ford"], mercury: ["ford", "lincoln"],
  toyota: ["lexus", "scion"], lexus: ["toyota", "scion"], scion: ["toyota", "lexus"], daihatsu: ["toyota"],
  honda: ["acura"], acura: ["honda"],
  nissan: ["infiniti", "nissaninfiniti", "datsun"], infiniti: ["nissan", "nissaninfiniti"], datsun: ["nissan"],
  hyundai: ["kia", "genesis"], kia: ["hyundai", "genesis"], genesis: ["hyundai", "kia"],
  chrysler: ["dodge", "jeep", "ram"], dodge: ["chrysler", "jeep", "ram"], jeep: ["chrysler", "dodge", "ram"], ram: ["dodge", "chrysler", "jeep"],
  plymouth: ["chrysler", "dodge"], eagle: ["chrysler"], fiat: ["chrysler", "alfaromeo", "jeep"], alfaromeo: ["fiat", "jeep"], maserati: ["chrysler"],
  mazda: ["ford"],
  volkswagen: ["audi", "seat", "cupra", "skoda"], audi: ["volkswagen", "seat", "cupra", "skoda"], seat: ["volkswagen", "cupra", "audi"],
  cupra: ["seat", "volkswagen", "audi"], skoda: ["volkswagen", "seat"], porsche: ["volkswagen", "audi"], bentley: ["audi"], lamborghini: ["audi"],
  bmw: ["mini"], mini: ["bmw"], landrover: ["jaguar"], jaguar: ["landrover"], volvo: ["polestar"], polestar: ["volvo"],
  peugeot: ["citroen", "vauxhallopel", "ds"], citroen: ["peugeot", "ds"], ds: ["peugeot", "citroen"], vauxhallopel: ["peugeot", "chevrolet"],
  renault: ["dacia", "nissan"], dacia: ["renault"], smart: ["mercedesbenz"],
};
const OBDB_UNITS_JS = {
  celsius: "C", fahrenheit: "F", kilopascal: "kPa", psi: "psi", bars: "bar", volts: "V", millivolts: "mV", rpm: "rpm", percent: "%",
  degrees: "deg", scalar: "", unknown: "", kilometersPerHour: "kph", kilometers: "km", miles: "mi", offon: "onoff", onoff: "onoff",
  noyes: "yesno", yesno: "yesno", milliseconds: "ms", seconds: "s", minutes: "min", hours: "h", milliamps: "mA", amps: "A",
  gramsPerSecond: "g/s", newtonMeters: "Nm", liters: "L", hex: "hex", metersPerSecondSquared: "m/s²", gravity: "g",
  ampereHours: "Ah", kilowatts: "kW", millimeters: "mm", megaohms: "MΩ", litersPerHour: "L/h", kilowattHours: "kWh",
};
const OBDB_SKIP = new Set(["Trips", "Seatbelts", "Lights", "Doors", "Clocks", "Details", "Stats", "DTCs", "ECU", "Cruise control"]);
const LEARN_VER = 2;   // bumped when the search learns to ask more (so cars searched the old way get searched again once)

function huntRepos() {
  const mk0 = normName(ARGS.vmake), mk = MAKE_ALIAS[mk0] || mk0, mdl = normName(ARGS.vmodel);
  const out = [], seen = new Set();
  const add = (repo, tier) => { if (repo && !seen.has(repo)) { seen.add(repo); out.push([repo, tier]); } };
  const mine = OBDB_REPOS[mk] || [];
  const prefixes = [mk, ...Object.keys(MAKE_ALIAS).filter((a) => MAKE_ALIAS[a] === mk)];
  const modelOf = (repo) => {
    const n = normName(repo);
    for (const p of prefixes) if (n.startsWith(p) && n.length > p.length) return n.slice(p.length);
    const i = repo.indexOf("-");
    return i < 0 ? "" : normName(repo.slice(i + 1));
  };
  const isMaster = (repo) => !repo.includes("-") || normName(repo) === mk;
  // 0 = this exact model · 1 = a model with a close name (Silverado / Silverado-1500) · 2 = the make's master list
  // 3 = sister brands' master lists · 4 = (only when the make has no master list) the make's other models
  mine.forEach((r) => { if (mdl && !isMaster(r) && modelOf(r) === mdl) add(r, 0); });
  mine.forEach((r) => { const m = modelOf(r); if (mdl && !isMaster(r) && m && (m.startsWith(mdl) || mdl.startsWith(m))) add(r, 1); });
  const masters = mine.filter(isMaster);
  masters.forEach((r) => add(r, 2));
  (FAMILY[mk] || []).forEach((f) => (OBDB_REPOS[f] || []).filter((r) => !r.includes("-") || normName(r) === f).forEach((r) => add(r, 3)));
  if (!masters.length) mine.forEach((r) => add(r, 4));
  return out;
}
async function obdbFetch(repo) {
  for (const br of ["main", "master"]) {
    try {
      const r = await fetch(`https://raw.githubusercontent.com/OBDb/${repo}/${br}/signalsets/v3/default.json`);
      if (r.ok) return await r.json();
    } catch (e) {}
  }
  return null;
}
function obdbYearOk(f, y) {
  if (!f || !y) return true;
  if ((f.years || []).includes(y)) return true;
  if (!("from" in f) && !("to" in f)) return !(f.years && f.years.length);
  return (f.from ?? 0) <= y && y <= (f.to ?? 9999);
}
const SAFE_SESSIONS = new Set(["03", "C0"]);   // extended diagnostic session / Nissan's — what every scan tool opens to read data
// One OBDb file -> requests [[sig, sig...], ...]. Reads only (service 21 / 22). Left out: BMW-style extended addressing and
// K-line requests (this adapter path can't do them) and requests that need an unusual diagnostic session.
function obdbCmds(json, year, src, tier) {
  const out = [];
  for (const c of (json && json.commands) || []) {
    const hdr = String(c.hdr || "").toUpperCase(), rax = String(c.rax || "").toUpperCase();
    if (c.eax || c.proto || c.baud || c.init) continue;
    if (!(/^[0-9A-F]{3}$/.test(hdr) || (/^[0-9A-F]{4}$/.test(hdr) && (hdr.startsWith("DA") || rax.length >= 6)))) continue;
    const din = String(c.din || "").toUpperCase();
    if (din && !SAFE_SESSIONS.has(din)) continue;
    if (!obdbYearOk(c.filter, year)) continue;
    const [svc, pid0] = Object.entries(c.cmd || {})[0] || ["", ""];
    if (svc !== "21" && svc !== "22") continue;
    const ext = hdr.length === 4;
    const sigs = [];
    for (const s of c.signals || []) {
      const f = s.fmt || {};
      if (OBDB_SKIP.has(s.path) || !f.len || f.len > 32) continue;
      const g = { hdr, rax, req: (svc + String(pid0)).toUpperCase(), bix: f.bix || 0, len: f.len, mul: f.mul ?? 1, div: f.div ?? 1, add: f.add ?? 0,
        sign: !!f.sign, lsb: !!f.blsb, unit: OBDB_UNITS_JS[f.unit] ?? (f.unit || ""), min: f.min ?? null, max: f.max ?? null,
        nmin: f.nullmin ?? null, nmax: f.nullmax ?? null,
        map: f.map ? Object.fromEntries(Object.entries(f.map).map(([k, v]) => [k, v && typeof v === "object" ? (v.description || v.value) : v])) : null,
        name: s.name || s.id || "", path: s.path || "", src, tier };
      if (ext && c.pri) g.pri = String(c.pri).toUpperCase();
      if (ext && c.tst) g.tst = String(c.tst).toUpperCase();
      if (din) { g.din = din; if (c.dout) g.dout = String(c.dout).toUpperCase(); }
      sigs.push(g);
    }
    if (sigs.length) out.push(sigs);
  }
  return out;
}
// one request = module address + what is asked (+ the 29-bit priority / tester address when they aren't the usual ones)
const cmdKey = (g) => g.hdr + "|" + g.req + "|" + (g.pri || "") + "|" + (g.tst || "");
async function gatherCandidates(progress) {
  const year = parseInt(ARGS.year, 10) || 0;
  const jobs = huntRepos();
  const lists = new Array(jobs.length);
  let next = 0, done = 0;
  const worker = async () => {
    while (next < jobs.length && !(hunt && hunt.stop)) {
      const i = next++, [repo, tier] = jobs[i];
      const j = await obdbFetch(repo);
      lists[i] = j ? obdbCmds(j, year, repo.replace(/-/g, " "), tier) : [];
      progress(++done, jobs.length);
    }
  };
  await Promise.all([1, 2, 3, 4].map(worker));
  // One layout per request: the closest list wins; between equals, the layout the most lists use.
  const byKey = new Map();
  lists.forEach((cmds) => (cmds || []).forEach((sigs) => {
    const g0 = sigs[0], key = cmdKey(g0);
    const lay = sigs.map((g) => [g.name, g.bix, g.len, g.mul, g.div, g.add, g.unit].join(",")).join(";");
    let k = byKey.get(key);
    if (!k) byKey.set(key, (k = new Map()));
    const e = k.get(lay);
    if (!e) k.set(lay, { n: 1, tier: g0.tier, sigs });
    else { e.n++; if (g0.tier < e.tier) { e.tier = g0.tier; e.sigs = sigs; } }
  }));
  const out = [];
  for (const [key, lays] of byKey) {
    const best = [...lays.values()].sort((a, b) => a.tier - b.tier || b.n - a.n)[0];
    const g0 = best.sigs[0];
    out.push({ key, hdr: g0.hdr, rax: g0.rax, req: g0.req, pri: g0.pri, tst: g0.tst, din: g0.din, dout: g0.dout, tier: best.tier,
      sigs: best.sigs.map((g) => Object.assign({}, g)), state: "new", miss: 0 });
  }
  out.sort((a, b) => a.tier - b.tier || (a.hdr + a.rax).localeCompare(b.hdr + b.rax) || a.req.localeCompare(b.req));
  return out;
}
function prepSig(g) {
  if (g.label) return g;
  g.label = (g.tier >= 3 ? "≈ " : "") + cleanName(g.name);
  g.group = oemGroup(g);
  g.watch = tccRole(g.name, g.unit, g.map);
  return g;
}
const slimSig = (g) => {
  const o = {};
  for (const k of ["hdr", "rax", "req", "pri", "tst", "din", "dout", "bix", "len", "mul", "div", "add", "sign", "lsb", "unit", "min", "max",
    "nmin", "nmax", "map", "name", "path", "grp", "src", "tier"])
    if (g[k] !== undefined && g[k] !== "" && g[k] !== null) o[k] = g[k];
  o.unit = g.unit || "";
  return o;
};
let hunt = null, myLearnedId = null, autoHuntTried = false;
function huntShow(text) {
  const b = $("huntBox");
  b.hidden = false;
  if (text) { b.innerHTML = esc(text); fitHeight(); return; }
  const h = hunt, secs = Math.round((Date.now() - h.t0) / 1000), t = Math.floor(secs / 60) + ":" + String(secs % 60).padStart(2, "0");
  b.innerHTML = h.done
    ? `✅ ${h.stop ? "Stopped" : "Done"} (${t}) — checked ${h.checked.toLocaleString()} factory requests and found <b>${h.found}</b> new readings` +
      (h.learned.length ? ". Saved for this car, so next time they show up right away." : ".") +
      (h.stop && h.paused ? " It stopped for the test — it will finish the next time you connect." : "") +
      (h.learned.some((c) => c.tier >= 3) ? `<br><span class="note">≈ = from a sister brand's list. Double-check those against your Topdon before you trust them.</span>` : "")
    : `🔎 ${h.auto ? "First time on this car — finding every reading it has. " : ""}Checking ${h.checked.toLocaleString()} of ${h.total.toLocaleString()} factory requests · <b>${h.found}</b> new readings found · ${t}`;
  fitHeight();
}
const huntBusy = () => T.drive.on || (T.trans && T.trans.on) || !!FOCUS;
async function findEverything(auto) {
  if (hunt && !hunt.done) { if (!auto) { hunt.stop = true; $("huntBtn").textContent = "Stopping…"; } return; }   // the button doubles as Stop
  if (!connected) return;
  const say = (m) => { if (!auto) alert(m); };
  if (!isCan) return say("Factory readings need a CAN vehicle (most 2008 and newer).");
  if (!ARGS.vmake) return say("Set the vehicle first (VIN search above), so the app knows which factory lists to try.");
  if (huntBusy()) return say("Finish the test drive or guided test first, then try again.");
  hunt = { stop: false, done: false, checked: 0, total: 0, found: 0, learned: [], t0: Date.now(), auto: !!auto };
  $("huntBtn").textContent = "⏹ Stop searching";
  huntShow("📥 Getting the factory lists for this make…");
  let cands = [];
  try { cands = await gatherCandidates((d, n) => huntShow(`📥 Getting the factory lists… ${d} of ${n}`)); }
  catch (e) { logEvent("scanner", "Find every reading", "Couldn't get the factory lists: " + e.message, e.stack); }
  const have = new Set(oemCmds.map((c) => cmdKey(c)));
  const todo = cands.filter((c) => !have.has(c.key));
  hunt.total = todo.length;
  const mods = {};
  const other = { tried: 0, alive: false };   // requests on the "other" kind of address (29-bit on an 11-bit car, or the reverse)
  for (let i = 0; i < todo.length && !hunt.stop && connected; i += 4) {
    if (huntBusy()) { hunt.stop = hunt.paused = true; break; }   // a test or test drive started: live data comes first
    await txn(async () => {   // a few at a time, so the live readings keep updating in between
      for (const c of todo.slice(i, i + 4)) {
        if (hunt.stop || !connected) break;
        hunt.checked++;
        const mk = c.hdr + "|" + (c.pri || "") + "|" + (c.tst || "");
        const m = mods[mk] || (mods[mk] = { alive: false, silent: 0 });
        if (!m.alive && m.silent >= 3) continue;   // nothing at that address on this car
        const odd = (c.hdr.length === 4) !== base29();
        if (odd && !other.alive && other.tried >= 9) continue;   // this car has nothing on that kind of address at all
        const { bytes, replied } = await readOem(c);
        if (replied || bytes) { m.alive = true; if (odd) other.alive = true; } else { m.silent++; if (odd) other.tried++; }
        if (!bytes) continue;
        c.sigs.forEach(prepSig);
        const { vals, wrong } = decodeCmd(c, bytes);
        if (wrong || !vals.length) continue;
        c.state = "live";
        oemCmds.push(c);
        hunt.learned.push(c);
        for (const [g, text] of vals) setTile(oemTile(g), text);
        hunt.found += vals.length;
      }
      await closeSessions();
      await setAddr(baseHeader, "");
    });
    huntShow();
  }
  hunt.done = true;
  const complete = cands.length > 0 && !hunt.stop && connected;
  $("huntBtn").textContent = "🔎 Find every reading this car has";
  updateEnhNote();
  if (!cands.length) huntShow(auto ? "" : "Couldn't get the factory lists (no internet on this phone?). Try again in a minute.");
  else if (!todo.length) huntShow(auto ? "" : "Already checked every factory request on file for this car.");
  else huntShow();
  if (!cands.length && auto) $("huntBox").hidden = true;
  if (hunt.learned.length || complete) {
    myLearnedId = "L" + Date.now();
    const sigs = [];
    hunt.learned.forEach((c) => c.sigs.forEach((g) => sigs.push(slimSig(g))));
    sendValue({ type: "oem_learned", id: myLearnedId, sigs, checked: hunt.checked, found: hunt.found, complete, ver: LEARN_VER });
  }
}
$("huntBtn").addEventListener("click", () => {
  findEverything(false).catch((e) => {
    if (hunt) hunt.done = true;
    $("huntBtn").textContent = "🔎 Find every reading this car has";
    logEvent("scanner", "Find every reading", e.message, e.stack);
  });
});
// The first time a car is connected (nothing saved for its year / make / model / engine yet), search by itself.
function maybeAutoHunt() {
  if (autoHuntTried || !connected || !isCan || !ARGS.vmake || !streaming || huntBusy()) return;
  if ((+ARGS.learned_ver || 0) >= LEARN_VER || (hunt && !hunt.done)) { autoHuntTried = true; return; }
  autoHuntTried = true;
  findEverything(true).catch((e) => { if (hunt) hunt.done = true; logEvent("scanner", "Find every reading", e.message, e.stack); });
}

// ===================== Every standard (SAE J1979) reading =====================
// The main screen shows the readings every car has. These are ALL the others in the standard — second O2 banks, wide-range
// sensors, torque, turbo, EGR, diesel aftertreatment, hybrid battery, transmission gear and more. A car only gets asked for
// the ones it says it supports, and a sensor the car says isn't fitted is left out.
// pid|first bit|bits|×|÷|+|flags|unit|min|max|"fitted" bit|group|name|value names      (list: OBDb SAEJ1979, CC BY-SA 4.0)
const STD_RAW = `12|5|3|1|1|0||||||E|Commanded secondary air status|1=Upstream of first catalytic converter~2=Downstream of first catalytic converter inlet~4=Atmosphere / off~8=Pump commanded on for diagnostics
1A|0|8|1|200|0||V||1.275||F|O2S Output Voltage Bank 2, Sensor 3|
1A|8|8|100|128|-100||%|-100|99.22||F|SHRTFT associated with O2S23|
1B|0|8|1|200|0||V||1.275||F|O2S Output Voltage Bank 2, Sensor 4|
1B|8|8|100|128|-100||%|-100|99.22||F|SHRTFT associated with O2S24|
1C|0|8|1|1|0||||||E|OBD requirements to which vehicle is designed|1=OBD II (California ARB)~2=OBD (Federal EPA)~3=OBD & OBD II~4=OBD I~5=Not OBD compliant~6=EOBD~7=EOBD & OBD II~8=EOBD & OBD~9=EOBD, OBD, OBD II~10=JOBD~11=JOBD & OBD II~12=JOBD & EOBD~13=JOBD, EOBD, OBD II~14=Heavy duty vehicles (EURO IV) B1~15=Heavy duty vehicles (EURO V) B2~16=Heavy duty vehicles (EURO EEC) C (gas engines)~17=Engine manufacturer diagnostics (EMD)~18=Engine Manufacturer Diagnostics Enhanced (EMD+)~19=Heavy Duty On-Board Diagnostics (Child/Partial)~20=Heavy Duty On-Board Diagnostics~21=World Wide Harmonized OBD~23=Heavy Duty Euro OBD Stage I without NOx Control~24=Heavy Duty Euro OBD Stage I with NOx Control~25=Heavy Duty Euro OBD Stage II without NOx Control~26=Heavy Duty Euro OBD Stage II with NOx Control~27=Heavy Duty ZEV~28=Brazil OBD Phase 1~29=Brazil OBD Phase 2 and Phase 2+~30=Korean OBD~31=India BS4 OBD I~32=India BS4 OBD II~33=Euro VI~34=OBD, OBD II and HD OBD~35=Brazil OBD Phase 3~36=Motorcycle, Euro OBD-I~37=Motorcycle, Euro OBD-II~38=Motorcycle, China OBD-I~39=Motorcycle, Taiwan OBD-I~40=Motorcycle, Japan OBD-I~41=China Nationwide Stage 6~42=Brazil OBD Phase 7~43=China Heavy Duty VI~44=India BS6 OBD I~45=India BS6 OBD II~46=India BSVI HD OBD~47=Brazil OBD Phase 8~48=Japan Heavy Duty OBD-II~49=Korea Heavy Duty OBD-II~50=China Off-Road IV OBD~51=Light Duty ZEV, ACC-II~52=Motorcycle, Japan OBD-II~53=Motorcycle, California (CARB) OBD~54=Motorcycle, Federal (EPA) OBD~55=Motorcycle, 50-State (CARB & EPA) OBD~56=Heavy Duty ZEV, CARB ZEP~57=Light Duty ZEV, CARB ACC-II and EPA Tier 4 (GTR 22)~58=Light Duty ZEV, EPA Tier 4 (GTR 22)~59=EPA HD OBD
1E|7|1|1|1|0||onoff||1||E|Power take off (PTO) status|
22|0|16|0.079|1|0||kPa||5177.27||E|Fuel pressure relative to manifold vacuum|
25|0|16|1|32768|0||||1.99||F|Lambda value, Equivalence Ratio Bank 1, Sensor 2|
25|16|16|1|8192|0||V||7.999||F|Wide Range O2S Voltage, O2 Sensor Bank 1, Sensor 2|
27|0|16|1|32768|0||||1.99||F|Lambda value, Equivalence Ratio Bank 1, Sensor 4|
27|16|16|1|8192|0||V||7.999||F|Wide Range O2S Voltage, O2 Sensor Bank 1, Sensor 4|
29|0|16|1|32768|0||||1.99||F|Lambda value, Equivalence Ratio Bank 2, Sensor 2|
29|16|16|1|8192|0||V||7.999||F|Wide Range O2S Voltage, O2 Sensor Bank 2, Sensor 2|
2A|0|16|1|32768|0||||1.99||F|Lambda value, Equivalence Ratio Bank 2, Sensor 3|
2A|16|16|1|8192|0||V||7.999||F|Wide Range O2S Voltage, O2 Sensor Bank 2, Sensor 3|
2B|0|16|1|32768|0||||1.99||F|Lambda value, Equivalence Ratio Bank 2, Sensor 4|
2B|16|16|1|8192|0||V||7.999||F|Wide Range O2S Voltage, O2 Sensor Bank 2, Sensor 4|
35|0|16|1|32768|0||||1.99||F|Lambda value, Equivalence Ratio Bank 1, Sensor 2|
35|16|16|1|256|-128||mA|-128|127.996||F|Wide Range O2S Current, O2 Sensor Bank 1, Sensor 2|
37|0|16|1|32768|0||||1.99||F|Lambda value, Equivalence Ratio Bank 1, Sensor 4|
37|16|16|1|256|-128||mA|-128|127.996||F|Wide Range O2S Current, O2 Sensor Bank 1, Sensor 4|
39|0|16|1|32768|0||||1.99||F|Lambda value, Equivalence Ratio Bank 2, Sensor 2|
39|16|16|1|256|-128||mA|-128|127.996||F|Wide Range O2S Current, O2 Sensor Bank 2, Sensor 2|
3A|0|16|1|32768|0||||1.99||F|Lambda value, Equivalence Ratio Bank 2, Sensor 3|
3A|16|16|1|256|-128||mA|-128|127.996||F|Wide Range O2S Current, O2 Sensor Bank 2, Sensor 3|
3B|0|16|1|32768|0||||1.99||F|Lambda value, Equivalence Ratio Bank 2, Sensor 4|
3B|16|16|1|256|-128||mA|-128|127.996||F|Wide Range O2S Current, O2 Sensor Bank 2, Sensor 4|
3E|0|16|1|10|-40||C|-40|6513.5||E|Catalyst temperature bank 1, sensor 2|
3F|0|16|1|10|-40||C|-40|6513.5||E|Catalyst temperature bank 2, sensor 2|
45|0|8|100|255|0||%||100||E|Relative throttle position|
47|0|8|100|255|0||%||100||E|Absolute throttle position B|
48|0|8|100|255|0||%||100||E|Absolute throttle position C|
4B|0|8|100|255|0||%||100||E|Accelerator pedal position F|
4C|0|8|100|255|0||%||100||E|Commanded throttle actuator control|
51|0|8|1|1|0||||||E|Type of fuel currently being used by the vehicle|1=Gasoline/petrol~2=Methanol~3=Ethanol~4=Diesel~5=Liquefied petroleum gas~6=Compressed natural gas~7=Propane~8=Battery/electric~9=Bi-fuel vehicle using gasoline/petrol~10=Bi-fuel vehicle using methanol~11=Bi-fuel vehicle using ethanol~12=Bi-fuel vehicle using LPG~13=Bi-fuel vehicle using CNG~14=Bi-fuel vehicle using propane~15=Bi-fuel vehicle using battery~16=Bi-fuel vehicle using battery and combustion engine for propulsion~17=Hybrid vehicle using gasoline engine for propulsion~18=Hybrid vehicle using gasoline engine on ethanol for propulsion~19=Hybrid vehicle using diesel engine for propulsion~20=Hybrid vehicle using battery for propulsion~21=Hybrid vehicle using battery and combustion engine for propulsion~22=Hybrid vehicle in regeneration mode~23=Bi-fuel vehicle using diesel~24=Bi-fuel vehicle using natural gas~25=Bi-fuel vehicle using diesel~26=Natural gas~27=Dual fuel vehicle using diesel and CNG~28=Dual fuel vehicle using diesel and LNG~29=Fuel cell utilizing hydrogen~30=Hydrogen Internal Combustion Engine~31=Kerosene~32=Heavy Fuel Oil
53|0|16|1|200|0||kPa||327.675||E|Absolute evap system vapor pressure|
54|0|16|1|1000|0|s|kPa||||E|Evap system vapor pressure (wide)|
55|0|8|100|128|-100||%|-100|99.22||E|Short term secondary O2 sensor fuel trim (bank 1)|
56|0|8|100|128|-100||%|-100|99.22||E|Long term secondary O2 sensor fuel trim (bank 1)|
57|0|8|100|128|-100||%|-100|99.22||E|Short term secondary O2 sensor fuel trim (bank 2)|
58|0|8|100|128|-100||%|-100|99.22||E|Long term secondary O2 sensor fuel trim (bank 2)|
5A|0|8|100|255|0||%||100||E|Accelerator pedal position (relative)|
5B|0|8|100|255|0||%||100||H|Hybrid battery pack remaining charge|
5D|0|16|1|128|-210||deg|-210|301.992||E|Fuel injection timing|
61|0|8|1|1|-125||%|-125|130||E|Driver's demand engine torque|
62|0|8|1|1|-125||%|-125|130||E|Actual engine torque|
63|0|16|1|1|0||Nm||65535||E|Engine reference torque|
65|8|4|1|1|0||yesno||15||E|Recommended gear|
65|12|1|1|1|0||yesno||1||E|Glow plug lamp status|
65|13|1|1|1|0||yesno||1||E|Manual Trans Neutral Gear Status|
65|14|1|1|1|0||yesno||1||E|Auto Trans Neutral Drive Status|
65|15|1|1|1|0||yesno||1||E|Power Take Off (PTO) Output Status|
66|8|16|1|32|0||g/s||2047.97|7|E|Mass Air Flow Sensor A|
66|24|16|1|32|0||g/s||2047.97|6|E|Mass Air Flow Sensor B|
67|8|8|1|1|-40||C|-40|215|7|E|Engine coolant temperature 1|
67|16|8|1|1|-40||C|-40|215|6|E|Engine coolant temperature 2|
68|8|8|1|1|-40||C|-40|215|7|E|Intake air temperature, bank 1, sensor 1|
68|16|8|1|1|-40||C|-40|215|6|E|Intake air temperature, bank 1, sensor 2|
68|24|8|1|1|-40||C|-40|215|5|E|Intake air temperature, bank 1, sensor 3|
68|32|8|1|1|-40||C|-40|215|4|E|Intake air temperature, bank 2, sensor 1|
68|40|8|1|1|-40||C|-40|215|3|E|Intake air temperature, bank 2, sensor 2|
68|48|8|1|1|-40||C|-40|215|2|E|Intake air temperature, bank 2, sensor 3|
69|8|8|100|255|0||%||100|7|E|Commanded EGR A duty cycle/position|
69|16|8|100|255|0||%||100|6|E|Actual EGR A duty cycle/position|
69|24|8|100|128|-100||%|-100|99.22|5|E|EGR A error|
69|32|8|100|255|0||%||100|4|E|Commanded EGR B duty cycle/position|
69|40|8|100|255|0||%||100|3|E|Actual EGR B duty cycle/position|
69|48|8|100|128|-100||%|-100|99.22|2|E|EGR B error|
6A|8|8|100|255|0||%||100|7|E|Commanded intake air flow A control|
6A|16|8|100|255|0||%||100|6|E|Relative intake air flow A position|
6A|24|8|100|255|0||%||100|5|E|Commanded intake air flow B control|
6A|32|8|100|255|0||%||100|4|E|Relative intake air flow B position|
6B|8|8|1|1|-40||C|-40|215|7|E|Exhaust Gas Recirculation Temp Sensor A (Bank 1, Sensor 1)|
6B|16|8|1|1|-40||C|-40|215|6|E|Exhaust Gas Recirculation Temp Sensor C (Bank 1, Sensor 2)|
6B|24|8|1|1|-40||C|-40|215|5|E|Exhaust Gas Recirculation Temp Sensor B (Bank 2, Sensor 1)|
6B|32|8|1|1|-40||C|-40|215|4|E|Exhaust Gas Recirculation Temp Sensor D (Bank 2, Sensor 2)|
6C|8|8|100|255|0||%||100||E|Commanded Throttle Actuator A Control|
6C|16|8|100|255|0||%||100||E|Relative Throttle A Position|
6C|24|8|100|255|0||%||100||E|Commanded Throttle Actuator B Control|
6C|32|8|100|255|0||%||100||E|Relative Throttle B Position|
6D|8|16|10|1|0||kPa||655350|7|F|Commanded Fuel Rail Pressure A|
6D|24|16|10|1|0||kPa||655350|6|F|Fuel Rail Pressure A|
6D|40|8|1|1|-40||C|-40|215|5|F|Fuel Rail Temperature A|
6D|48|16|10|1|0||kPa||655350|4|F|Commanded Fuel Rail Pressure B|
6D|64|16|10|1|0||kPa||655350|3|F|Fuel Rail Pressure B|
6D|80|8|1|1|-40||C|-40|215|2|F|Fuel Rail Temperature B|
6E|8|16|10|1|0||kPa||655350|7|E|Commanded injection control pressure A|
6E|24|16|10|1|0||kPa||655350|6|E|Injection control pressure A|
6E|40|16|10|1|0||kPa||655350|5|E|Commanded injection control pressure B|
6E|56|16|10|1|0||kPa||655350|4|E|Injection control pressure B|
70|8|16|1|32|0||kPa||2047.97|7|E|Commanded boost pressure A|
70|40|16|1|32|0||kPa||2047.97|4|E|Commanded boost pressure B|
70|56|16|1|32|0||kPa||2047.97|3|E|Boost pressure sensor B|
71|8|8|100|255|0||%||100|7|E|Commanded variable geometry turbo A position|
71|16|8|100|255|0||%||100|6|E|Variable geometry turbo A position|
71|24|8|100|255|0||%||100|4|E|Commanded variable geometry turbo B position|
71|32|8|100|255|0||%||100|3|E|Variable geometry turbo B position|
71|44|2|1|1|0|||||2|E|Variable geometry turbo B control status|1=Open loop, no fault present~2=Closed loop, no fault present~3=Fault present, VGT data unreliable
71|46|2|1|1|0|||||5|E|Variable geometry turbo A control status|1=Open loop, no fault present~2=Closed loop, no fault present~3=Fault present, VGT data unreliable
72|8|8|100|255|0||%||100|7|E|Commanded wastegate A position|
72|16|8|100|255|0||%||100|6|E|Wastegate A position|
72|24|8|100|255|0||%||100|5|E|Commanded wastegate B position|
72|32|8|100|255|0||%||100|4|E|Wastegate B position|
73|8|16|1|100|0||kPa||655.35|7|E|Exhaust pressure bank 1, sensor 1|
73|24|16|1|100|0||kPa||655.35|6|E|Exhaust pressure bank 2, sensor 1|
74|8|16|10|1|0||rpm||655350|7|E|Turbocharger A speed|
74|24|16|10|1|0||rpm||655350|6|E|Turbocharger B speed|
75|8|8|1|1|-40||C|-40|215|7|E|Turbocharger A compressor inlet temperature|
75|16|8|1|1|-40||C|-40|215|6|E|Turbocharger A compressor outlet temperature|
75|24|16|1|10|-40||C|-40|6513.5|5|E|Turbocharger A turbine inlet temperature|
75|40|16|1|10|-40||C|-40|6513.5|4|E|Turbocharger A turbine outlet temperature|
76|8|8|1|1|-40||C|-40|215|7|E|Turbocharger B compressor inlet temperature|
76|16|8|1|1|-40||C|-40|215|6|E|Turbocharger B compressor outlet temperature|
76|24|16|1|10|-40||C|-40|6513.5|5|E|Turbocharger B turbine inlet temperature|
76|40|16|1|10|-40||C|-40|6513.5|4|E|Turbocharger B turbine outlet temperature|
77|8|8|1|1|-40||C|-40|215|7|E|Charge air cooler temperature bank 1, sensor 1|
77|16|8|1|1|-40||C|-40|215|6|E|Charge air cooler temperature bank 1, sensor 2|
77|24|8|1|1|-40||C|-40|215|5|E|Charge air cooler temperature bank 2, sensor 1|
77|32|8|1|1|-40||C|-40|215|4|E|Charge air cooler temperature bank 2, sensor 2|
78|24|16|1|10|-40||C|-40|6513.5|6|E|Exhaust gas temperature bank 1, sensor 2|
78|40|16|1|10|-40||C|-40|6513.5|5|E|Exhaust gas temperature bank 1, sensor 3|
78|56|16|1|10|-40||C|-40|6513.5|4|E|Exhaust gas temperature bank 1, sensor 4|
79|8|16|1|10|-40||C|-40|6513.5|7|E|Exhaust gas temperature bank 2, sensor 1|
79|24|16|1|10|-40||C|-40|6513.5|6|E|Exhaust gas temperature bank 2, sensor 2|
79|40|16|1|10|-40||C|-40|6513.5|5|E|Exhaust gas temperature bank 2, sensor 3|
79|56|16|1|10|-40||C|-40|6513.5|4|E|Exhaust gas temperature bank 2, sensor 4|
7A|8|16|1|100|0|s|kPa|-327.68|327.67|7|E|Particulate filter bank 1 delta pressure|
7A|24|16|1|100|0||kPa||655.35|6|E|Particulate filter bank 1 inlet pressure|
7A|40|16|1|100|0||kPa||655.35|5|E|Particulate filter bank 1 outlet pressure|
7B|8|16|1|100|0|s|kPa|-327.68|327.67|7|E|Particulate filter bank 2 delta pressure|
7B|24|16|1|100|0||kPa||655.35|6|E|Particulate filter bank 2 inlet pressure|
7B|40|16|1|100|0||kPa||655.35|5|E|Particulate filter bank 2 outlet pressure|
7C|8|16|1|10|-40||C|-40|6513.5|7|E|Particulate filter bank 1 inlet temperature|
7C|24|16|1|10|-40||C|-40|6513.5|6|E|Particulate filter bank 1 outlet temperature|
7C|40|16|1|10|-40||C|-40|6513.5|5|E|Particulate filter bank 2 inlet temperature|
7C|56|16|1|10|-40||C|-40|6513.5|4|E|Particulate filter bank 2 outlet temperature|
7E|4|1|1|1|0||yesno||1||D|NTE deficiency for PM active area|
7E|5|1|1|1|0||yesno||1||D|Inside manufacturer-specific PM NTE carve-out area|
7E|6|1|1|1|0||yesno||1||D|Outside PM control area|
7E|7|1|1|1|0||yesno||1||D|Inside PM control area|
7F|8|32|1|1|0||s||4.29497e+09|7|E|Total Engine Run Time|
7F|40|32|1|1|0||s||4.29497e+09|6|E|Total Idle Run Time|
7F|72|32|1|1|0||s||4.29497e+09|5|E|Total Run Time With PTO Active|
81|8|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #1 timer 1 active|
81|40|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #1 timer 2 active|
81|72|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #2 timer 1 active|
81|104|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #2 timer 2 active|
81|136|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #3 timer 1 active|
81|168|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #3 timer 2 active|
81|200|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #4 timer 1 active|
81|232|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #4 timer 2 active|
81|264|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #5 timer 1 active|
81|296|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #5 timer 2 active|
82|8|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #6 timer 1 active|
82|40|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #6 timer 2 active|
82|72|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #7 timer 1 active|
82|104|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #7 timer 2 active|
82|136|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #8 timer 1 active|
82|168|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #8 timer 2 active|
82|200|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #9 timer 1 active|
82|232|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #9 timer 2 active|
82|264|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #10 timer 1 active|
82|296|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #10 timer 2 active|
83|8|16|1|1|0||||65535|7|D|NOx concentration bank 1, sensor 1|
83|24|16|1|1|0||||65535|6|D|NOx concentration bank 1, sensor 2|
83|40|16|1|1|0||||65535|5|D|NOx concentration bank 2, sensor 1|
83|56|16|1|1|0||||65535|4|D|NOx concentration bank 2, sensor 2|
84|0|8|1|1|-40||C|-40|215||E|Manifold surface temperature|
85|8|16|1|200|0||L/h||327.675|7|D|Average reagent consumption|
85|24|16|1|200|0||L/h||327.675|6|D|Average demanded reagent consumption|
85|40|8|100|255|0||%||100|5|D|Reagent tank level|
85|48|32|1|1|0||s||4.29497e+09|4|D|Run time with NOx warning active|
86|8|16|1|80|0||||819.188|7|D|PM mass concentration bank 1, sensor 1|
86|24|16|1|80|0||||819.188|6|D|PM mass concentration bank 2, sensor 1|
88|0|1|1|1|0||yesno||1||D|SCR inducement system active|
88|4|1|1|1|0||yesno||1||D|SCR inducement for NOx emissions too high|
88|5|1|1|1|0||yesno||1||D|SCR inducement for reagent consumption deviation|
88|6|1|1|1|0||yesno||1||D|SCR inducement for incorrect reagent|
88|7|1|1|1|0||yesno||1||D|SCR inducement for reagent level too low|
88|8|1|1|1|0||yesno||1||D|SCR inducement for NOx emissions too high in the 10,000-20,000 km history block|
88|9|1|1|1|0||yesno||1||D|SCR inducement for reagent consumption deviation in the 10,000-20,000 km history block|
88|10|1|1|1|0||yesno||1||D|SCR inducement for incorrect reagent in the 10,000-20,000 km history block|
88|11|1|1|1|0||yesno||1||D|SCR inducement for reagent level too low in the 10,000-20,000 km history block|
88|12|1|1|1|0||yesno||1||D|SCR inducement for NOx emissions too high in the 0-10,000 km history block|
88|13|1|1|1|0||yesno||1||D|SCR inducement for reagent consumption deviation in the 0-10,000 km history block|
88|14|1|1|1|0||yesno||1||D|SCR inducement for incorrect reagent in the 0-10,000 km history block|
88|15|1|1|1|0||yesno||1||D|SCR inducement for reagent level too low in the 0-10,000 km history block|
88|16|1|1|1|0||yesno||1||D|SCR inducement for NOx emissions too high in the 30,000-40,000 km history block|
88|17|1|1|1|0||yesno||1||D|SCR inducement for reagent consumption deviation in the 30,000-40,000 km history block|
88|18|1|1|1|0||yesno||1||D|SCR inducement for incorrect reagent in the 30,000-40,000 km history block|
88|19|1|1|1|0||yesno||1||D|SCR inducement for reagent level too low in the 30,000-40,000 km history block|
88|20|1|1|1|0||yesno||1||D|SCR inducement for NOx emissions too high in the 20,000-30,000 km history block|
88|21|1|1|1|0||yesno||1||D|SCR inducement for reagent consumption deviation in the 20,000-30,000 km history block|
88|22|1|1|1|0||yesno||1||D|SCR inducement for incorrect reagent in the 20,000-30,000 km history block|
88|23|1|1|1|0||yesno||1||D|SCR inducement for reagent level too low in the 20,000-30,000 km history block|
88|24|16|1|1|0||km||65535||D|Distance with SCR inducement active in the current 10,000 km block|
88|40|16|1|1|0||km||65535||D|Distance travelled in the current 10,000 km block|
88|56|16|1|1|0||km||65535||D|Distance with SCR inducement active in the 10,000-20,000 km block|
88|72|16|1|1|0||km||65535||D|Distance with SCR inducement active in the 20,000-30,000 km block|
88|88|16|1|1|0||km||65535||D|Distance with SCR inducement active in the 30,000-40,000 km block|
89|8|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #11 timer 1 active|
89|40|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #11 timer 2 active|
89|72|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #12 timer 1 active|
89|104|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #12 timer 2 active|
89|136|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #13 timer 1 active|
89|168|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #13 timer 2 active|
89|200|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #14 timer 1 active|
89|232|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #14 timer 2 active|
89|264|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #15 timer 1 active|
89|296|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #15 timer 2 active|
8A|8|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #16 timer 1 active|
8A|40|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #16 timer 2 active|
8A|72|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #17 timer 1 active|
8A|104|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #17 timer 2 active|
8A|136|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #18 timer 1 active|
8A|168|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #18 timer 2 active|
8A|200|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #19 timer 1 active|
8A|232|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #19 timer 2 active|
8A|264|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #20 timer 1 active|
8A|296|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #20 timer 2 active|
8B|12|1|1|1|0||yesno||1|4|D|NOx adsorber desulfurization in progress|
8B|13|1|1|1|0||yesno||1|5|D|NOx adsorber regen in progress|
8B|15|1|1|1|0||yesno||1|7|D|Particulate filter regen in progress|
8B|16|8|100|255|0||%||100|3|D|Normalized trigger for particulate filter regen|
8B|24|16|1|1|0||min||65535|2|D|Average time between particulate filter regens|
8B|40|16|1|1|0||km||65535|1|D|Average distance between particulate filter regens|
8B|14|1|1|1|0|||||6|D|Particulate filter regen type|0=Passive regen~1=Active regen
8C|8|16|100|65535|0||%||100|7|F|O2 concentration bank 1, sensor 1|
8C|24|16|100|65535|0||%||100|6|F|O2 concentration bank 1, sensor 2|
8C|40|16|100|65535|0||%||100|5|F|O2 concentration bank 2, sensor 1|
8C|56|16|100|65535|0||%||100|4|F|O2 concentration bank 2, sensor 2|
8C|72|16|1|8192|0||||7.99988|3|F|O2 sensor lambda bank 1, sensor 1|
8C|88|16|1|8192|0||||7.99988|2|F|O2 sensor lambda bank 1, sensor 2|
8C|104|16|1|8192|0||||7.99988|1|F|O2 sensor lambda bank 2, sensor 1|
8C|120|16|1|8192|0||||7.99988|0|F|O2 sensor lambda bank 2, sensor 2|
8D|0|8|100|255|0||%||100||E|Absolute Throttle Position G|
8E|0|8|1|1|-125||%|-125|130||E|Engine Friction - Percent Torque|
8F|14|1|1|1|0||yesno||1||D|PM sensor bank 1, sensor 1 regenerating|
8F|15|1|1|1|0||yesno||1||D|PM sensor bank 1, sensor 1 measuring|
8F|16|16|1|100|0|s|%|-327.68|327.67|6|D|PM sensor normalized output bank 1, sensor 1|
8F|38|1|1|1|0||yesno||1||D|PM sensor bank 2, sensor 1 regenerating|
8F|39|1|1|1|0||yesno||1||D|PM sensor bank 2, sensor 1 measuring|
8F|40|16|1|100|0|s|%|-327.68|327.67|4|D|PM sensor normalized output bank 2, sensor 1|
92|8|1|1|1|0||yesno||1|0|F|Idle fuel balance control 2 in closed loop|
92|9|1|1|1|0||yesno||1|1|F|Fuel injection timing control 2 in closed loop|
92|10|1|1|1|0||yesno||1|2|F|Fuel injection quantity control 2 in closed loop|
92|11|1|1|1|0||yesno||1|3|F|Fuel pressure control 2 in closed loop|
92|12|1|1|1|0||yesno||1|4|F|Idle fuel balance control 1 in closed loop|
92|13|1|1|1|0||yesno||1|5|F|Fuel injection timing control 1 in closed loop|
92|14|1|1|1|0||yesno||1|6|F|Fuel injection quantity control 1 in closed loop|
92|15|1|1|1|0||yesno||1|7|F|Fuel pressure control 1 in closed loop|
94|15|1|1|1|0||yesno||1|7|D|NOx warning system active|
94|16|16|1|1|0||h||65535|6|D|Engine hours with incorrect reagent quality|
94|32|16|1|1|0||h||65535|5|D|Engine hours with incorrect reagent consumption|
94|48|16|1|1|0||h||65535|4|D|Engine hours with reagent dosing interrupted|
94|64|16|1|1|0||h||65535|3|D|Engine hours with an impeded EGR valve|
94|80|16|1|1|0||h||65535|2|D|Engine hours with a NOx control monitoring system fault|
94|9|2|1|1|0||||||D|Level three inducement status|0=Level three inducement inactive~1=Level three inducement enabled~2=Level three inducement active~3=Level three inducement not supported
94|11|2|1|1|0||||||D|Level two inducement status|0=Level two inducement inactive~1=Level two inducement enabled~2=Level two inducement active~3=Level two inducement not supported
94|13|2|1|1|0||||||D|Level one inducement status|0=Level one inducement inactive~1=Level one inducement enabled~2=Level one inducement active~3=Level one inducement not supported
95|8|16|1|10000|0||g/L||6.5535|7|D|Target SCR catalyst A NH3 storage|
95|24|16|1|10000|0||g/L||6.5535|6|D|Actual SCR catalyst A NH3 storage|
95|40|16|1|10000|0||g/L||6.5535|5|D|Target SCR catalyst B NH3 storage|
95|56|16|1|10000|0||g/L||6.5535|4|D|Actual SCR catalyst B NH3 storage|
96|8|16|1|1200|0||g/s||54.6125|7|D|Hydrocarbon doser flow rate|
96|24|8|100|255|0||%||100|6|D|Hydrocarbon doser injector duty cycle|
96|32|16|1|10|0||kPa||6553.5|5|D|Aftertreatment fuel pressure|
97|8|16|1|10000|0||g/s||6.5535|7|D|Engine-out NOx mass emission rate|
97|24|16|1|10000|0||g/s||6.5535|6|D|Tailpipe NOx mass emission rate|
9A|16|16|1|64|0||V||1023.98|6|H|Hybrid/EV Battery System Voltage|
9A|32|16|1|10|0|s|A|-3276.8|3276.7|5|H|Hybrid/EV Battery System Current|
9A|13|2|1|1|0|||||4|H|Enhanced Hybrid/EV Vehicle Charging State|0=Charge sustaining mode~1=Charge depleting mode~2=Charge increasing mode~3=Not PSA
9A|15|1|1|1|0|||||7|H|Hybrid/EV Vehicle Charging State|0=Charge sustaining mode~1=Charge depleting mode
9B|8|8|1|4|0||%||63.75|6|D|DEF concentration|
9B|16|8|1|1|-40||C|-40|215|5|D|DEF tank temperature|
9B|24|8|100|255|0||%||100|4|D|DEF tank level|
9B|0|4|1|1|0|||||7|D|DEF type|0=Urea concentration too high~1=Urea concentration too low~2=Fluid is diesel or another fluid~3=DEF is the proper mixture~13=No concentration sensor fault, fluid type cannot be determined~14=Concentration sensor fault, no result
9C|8|16|100|65535|0||%||100|7|F|O2 concentration bank 1, sensor 3|
9C|24|16|100|65535|0||%||100|6|F|O2 concentration bank 1, sensor 4|
9C|40|16|100|65535|0||%||100|5|F|O2 concentration bank 2, sensor 3|
9C|56|16|100|65535|0||%||100|4|F|O2 concentration bank 2, sensor 4|
9C|72|16|1|8192|0||||7.99988|3|F|O2 sensor lambda bank 1, sensor 3|
9C|88|16|1|8192|0||||7.99988|2|F|O2 sensor lambda bank 1, sensor 4|
9C|104|16|1|8192|0||||7.99988|1|F|O2 sensor lambda bank 2, sensor 3|
9C|120|16|1|8192|0||||7.99988|0|F|O2 sensor lambda bank 2, sensor 4|
9D|0|16|1|50|0||g/s||1310.7||F|Engine fuel rate (alternate)|
9D|16|16|1|50|0||g/s||1310.7||F|Vehicle fuel rate|
9E|0|16|1|5|0||kg/h||13107||F|Engine exhaust flow rate|
9F|8|8|100|255|0||%||100|7|F|Fuel system A use percentage bank 1|
9F|16|8|100|255|0||%||100|6|F|Fuel system B use percentage bank 1|
9F|24|8|100|255|0||%||100|5|F|Fuel system A use percentage bank 2|
9F|32|8|100|255|0||%||100|4|F|Fuel system B use percentage bank 2|
9F|40|8|100|255|0||%||100|3|F|Fuel system A use percentage bank 3|
9F|48|8|100|255|0||%||100|2|F|Fuel system B use percentage bank 3|
9F|56|8|100|255|0||%||100|1|F|Fuel system A use percentage bank 4|
9F|64|8|100|255|0||%||100|0|F|Fuel system B use percentage bank 4|
A1|8|16|1|1|0||||65535|7|D|Corrected NOx concentration bank 1, sensor 1|
A1|24|16|1|1|0||||65535|6|D|Corrected NOx concentration bank 1, sensor 2|
A1|40|16|1|1|0||||65535|5|D|Corrected NOx concentration bank 2, sensor 1|
A1|56|16|1|1|0||||65535|4|D|Corrected NOx concentration bank 2, sensor 2|
A2|0|16|1|32|0||mg/stroke||2047.97||E|Cylinder fuel rate|
A3|2|1|1|1|0||yesno||1|3|F|Evap system sealed|
A3|8|16|1|4000|0|s|kPa|-8.192|8.19175|7|F|Evap system vapor pressure A|
A3|24|16|1|500|0|s|kPa|-65.536|65.534|6|F|Evap system vapor pressure A, wide range|
A3|40|16|1|4000|0|s|kPa|-8.192|8.19175|5|F|Evap system vapor pressure B|
A3|56|16|1|500|0|s|kPa|-65.536|65.534|4|F|Evap system vapor pressure B, wide range|
A4|8|4|1|1|0||||15|7|E|Transmission actual gear|
A4|16|16|1|1000|0||||65.535|6|E|Transmission actual gear ratio|
A5|8|8|1|2|0||%||100|7|D|Commanded DEF dosing|
A5|16|16|1|2000|0||L||32.7675|6|D|DEF used in the current driving cycle|
A7|8|16|1|1|0||||65535|7|D|NOx concentration bank 1, sensor 3|
A7|24|16|1|1|0||||65535|6|D|NOx concentration bank 1, sensor 4|
A7|40|16|1|1|0||||65535|5|D|NOx concentration bank 2, sensor 3|
A7|56|16|1|1|0||||65535|4|D|NOx concentration bank 2, sensor 4|
A8|8|16|1|1|0||||65535|7|D|Corrected NOx concentration bank 1, sensor 3|
A8|24|16|1|1|0||||65535|6|D|Corrected NOx concentration bank 1, sensor 4|
A8|40|16|1|1|0||||65535|5|D|Corrected NOx concentration bank 2, sensor 3|
A8|56|16|1|1|0||||65535|4|D|Corrected NOx concentration bank 2, sensor 4|
AA|0|8|1|1|0||kph||255||E|Maximum current vehicle speed limit|
AB|8|16|1|32|0||kPa||2047.97|7|F|Alternative fuel rail pressure|
AB|24|8|1|1|-40||C|-40|215|6|F|Alternative fuel rail temperature|
AB|32|16|1|8|0||kPa||8191.88|5|F|Alternative fuel tank pressure|
AB|48|16|1|1|0||kPa||65535|4|F|Alternative fuel tank pressure, wide range|
AB|64|8|2|1|-256||C|-256|254|3|F|Alternative fuel tank temperature|
AC|8|8|1|1|0||||255|7|D|DEF doser A dosing mode|
AC|16|16|3|10000|0||kg/h||19.6605|6|D|DEF doser A maximum dosing rate|
AE|8|16|1|4000|0|s|kPa|-8.192|8.19175|7|F|Evap system purge pressure|
AE|24|16|1|500|0|s|kPa|-65.536|65.534|6|F|Evap system purge pressure, wide range|
AF|0|16|1|20|0||kg/h||3276.75||E|Commanded fresh air flow|
B0|8|16|1|20|0||kg/h||3276.75|7|E|EGR mass flow rate A|
B0|24|16|1|20|0||kg/h||3276.75|6|E|EGR mass flow rate B|
B1|9|1|1|1|0||yesno||1||F|Fuel system bank 2 in open loop due to a malfunction|
B1|10|1|1|1|0||yesno||1||F|Fuel system bank 2 in closed loop|
B1|11|1|1|1|0||yesno||1||F|Fuel system bank 2 in open loop|
B1|13|1|1|1|0||yesno||1||F|Fuel system bank 1 in open loop due to a malfunction|
B1|14|1|1|1|0||yesno||1||F|Fuel system bank 1 in closed loop|
B1|15|1|1|1|0||yesno||1||F|Fuel system bank 1 in open loop|
B1|16|8|100|128|-100||%|-100|99.2188|5|F|Short term fuel trim bank 1, compression ignition|
B1|24|8|100|128|-100||%|-100|99.2188|4|F|Long term fuel trim bank 1, compression ignition|
B1|32|8|100|128|-100||%|-100|99.2188|3|F|Short term fuel trim bank 2, compression ignition|
B1|40|8|100|128|-100||%|-100|99.2188|2|F|Long term fuel trim bank 2, compression ignition|
B2|0|8|100|255|0||%||100||H|Traction battery pack State of Health|
B3|8|16|1|20|0||kW||3276.75||H|HV battery actual charge rate|
B3|24|16|1|20|0||kW||3276.75|7|H|HV battery pack A actual charge rate|
B3|40|16|1|20|0||kW||3276.75|6|H|HV battery pack B actual charge rate|
B3|56|16|1|20|0||kW||3276.75|5|H|HV battery pack C actual charge rate|
B3|72|16|1|20|0||kW||3276.75|4|H|HV battery pack D actual charge rate|
B3|88|16|1|20|0||kW||3276.75|3|H|HV battery pack E actual charge rate|
B3|104|16|1|20|0||kW||3276.75|2|H|HV battery pack F actual charge rate|
B3|120|16|1|20|0||kW||3276.75|1|H|HV battery pack G actual charge rate|
B3|136|16|1|20|0||kW||3276.75|0|H|HV battery pack H actual charge rate|
B4|8|8|1|1|-40||C|-40|215||H|HV battery temperature|
B4|16|8|1|1|-40||C|-40|215|7|H|HV battery pack A temperature|
B4|24|8|1|1|-40||C|-40|215|6|H|HV battery pack B temperature|
B4|32|8|1|1|-40||C|-40|215|5|H|HV battery pack C temperature|
B4|40|8|1|1|-40||C|-40|215|4|H|HV battery pack D temperature|
B4|48|8|1|1|-40||C|-40|215|3|H|HV battery pack E temperature|
B4|56|8|1|1|-40||C|-40|215|2|H|HV battery pack F temperature|
B4|64|8|1|1|-40||C|-40|215|1|H|HV battery pack G temperature|
B4|72|8|1|1|-40||C|-40|215|0|H|HV battery pack H temperature|
B5|8|16|1|20|-1600||A|-1600|1676.75||H|HV battery current|
B5|24|16|1|20|-1600||A|-1600|1676.75|7|H|HV battery pack A current|
B5|40|16|1|20|-1600||A|-1600|1676.75|6|H|HV battery pack B current|
B5|56|16|1|20|-1600||A|-1600|1676.75|5|H|HV battery pack C current|
B5|72|16|1|20|-1600||A|-1600|1676.75|4|H|HV battery pack D current|
B5|88|16|1|20|-1600||A|-1600|1676.75|3|H|HV battery pack E current|
B5|104|16|1|20|-1600||A|-1600|1676.75|2|H|HV battery pack F current|
B5|120|16|1|20|-1600||A|-1600|1676.75|1|H|HV battery pack G current|
B5|136|16|1|20|-1600||A|-1600|1676.75|0|H|HV battery pack H current|
B6|8|16|1|20|0||V||3276.75||H|HV battery voltage|
B6|24|16|1|20|0||V||3276.75|7|H|HV battery pack A voltage|
B6|40|16|1|20|0||V||3276.75|6|H|HV battery pack B voltage|
B6|56|16|1|20|0||V||3276.75|5|H|HV battery pack C voltage|
B6|72|16|1|20|0||V||3276.75|4|H|HV battery pack D voltage|
B6|88|16|1|20|0||V||3276.75|3|H|HV battery pack E voltage|
B6|104|16|1|20|0||V||3276.75|2|H|HV battery pack F voltage|
B6|120|16|1|20|0||V||3276.75|1|H|HV battery pack G voltage|
B6|136|16|1|20|0||V||3276.75|0|H|HV battery pack H voltage|
B7|8|8|1|1|-40||C|-40|215|7|H|HV battery minimum cell temperature|
B7|16|8|1|1|-40||C|-40|215|6|H|HV battery maximum cell temperature|
B7|24|8|1|1|-40||C|-40|215|5|H|HV battery average cell temperature|
B7|32|8|1|1|-40||C|-40|215|4|H|HV battery bus bar temperature|
B7|40|8|1|1|-40||C|-40|215|3|H|HV battery coolant temperature|
B7|48|8|1|1|0|||||2|H|HV battery thermal state|0=Thermal system off~1=Active cooling~2=Passive cooling~3=Active heating~4=Passive heating
B8|0|16|1|1|0||min||65535||H|HV battery active time since cell balancing|
B9|0|16|1|1000|0||V||65.535||H|HV battery minimum cell voltage|
B9|16|16|1|1000|0||V||65.535||H|HV battery maximum cell voltage|
BA|0|8|100|255|0||%||100||H|HV battery continuous rated power available|
BA|8|16|1|10|0|s|A|-3276.8|3276.7||H|HV battery continuous charge current limit|
BA|24|16|1|10|0|s|A|-3276.8|3276.7||H|HV battery continuous discharge current limit|
BB|8|32|1|1|0||kWh||4.29497e+09||H|HV battery cumulative energy in|
BB|40|32|1|1|0||kWh||4.29497e+09|7|H|HV battery pack A cumulative energy in|
BB|72|32|1|1|0||kWh||4.29497e+09|6|H|HV battery pack B cumulative energy in|
BB|104|32|1|1|0||kWh||4.29497e+09|5|H|HV battery pack C cumulative energy in|
BB|136|32|1|1|0||kWh||4.29497e+09|4|H|HV battery pack D cumulative energy in|
BB|168|32|1|1|0||kWh||4.29497e+09|3|H|HV battery pack E cumulative energy in|
BB|200|32|1|1|0||kWh||4.29497e+09|2|H|HV battery pack F cumulative energy in|
BB|232|32|1|1|0||kWh||4.29497e+09|1|H|HV battery pack G cumulative energy in|
BB|264|32|1|1|0||kWh||4.29497e+09|0|H|HV battery pack H cumulative energy in|
BC|8|32|1|1|0||kWh||4.29497e+09||H|HV battery cumulative energy out|
BC|40|32|1|1|0||kWh||4.29497e+09|7|H|HV battery pack A cumulative energy out|
BC|72|32|1|1|0||kWh||4.29497e+09|6|H|HV battery pack B cumulative energy out|
BC|104|32|1|1|0||kWh||4.29497e+09|5|H|HV battery pack C cumulative energy out|
BC|136|32|1|1|0||kWh||4.29497e+09|4|H|HV battery pack D cumulative energy out|
BC|168|32|1|1|0||kWh||4.29497e+09|3|H|HV battery pack E cumulative energy out|
BC|200|32|1|1|0||kWh||4.29497e+09|2|H|HV battery pack F cumulative energy out|
BC|232|32|1|1|0||kWh||4.29497e+09|1|H|HV battery pack G cumulative energy out|
BC|264|32|1|1|0||kWh||4.29497e+09|0|H|HV battery pack H cumulative energy out|
BD|8|32|1|10|0||kWh||4.29497e+08||H|HV battery total energy throughput|
BD|40|32|1|10|0||kWh||4.29497e+08|7|H|HV battery pack A total energy throughput|
BD|72|32|1|10|0||kWh||4.29497e+08|6|H|HV battery pack B total energy throughput|
BD|104|32|1|10|0||kWh||4.29497e+08|5|H|HV battery pack C total energy throughput|
BD|136|32|1|10|0||kWh||4.29497e+08|4|H|HV battery pack D total energy throughput|
BD|168|32|1|10|0||kWh||4.29497e+08|3|H|HV battery pack E total energy throughput|
BD|200|32|1|10|0||kWh||4.29497e+08|2|H|HV battery pack F total energy throughput|
BD|232|32|1|10|0||kWh||4.29497e+08|1|H|HV battery pack G total energy throughput|
BD|264|32|1|10|0||kWh||4.29497e+08|0|H|HV battery pack H total energy throughput|
BE|8|8|2|5|0||%||102||H|HV battery state of health|
BE|16|8|2|5|0||%||102|7|H|HV battery pack A state of health|
BE|24|8|2|5|0||%||102|6|H|HV battery pack B state of health|
BE|32|8|2|5|0||%||102|5|H|HV battery pack C state of health|
BE|40|8|2|5|0||%||102|4|H|HV battery pack D state of health|
BE|48|8|2|5|0||%||102|3|H|HV battery pack E state of health|
BE|56|8|2|5|0||%||102|2|H|HV battery pack F state of health|
BE|64|8|2|5|0||%||102|1|H|HV battery pack G state of health|
BE|72|8|2|5|0||%||102|0|H|HV battery pack H state of health|
BF|8|16|1|640|0||%||102.398||H|HV battery recommended minimum state of charge|
BF|24|16|1|640|0||%||102.398|7|H|HV battery pack A recommended minimum state of charge|
BF|40|16|1|640|0||%||102.398|6|H|HV battery pack B recommended minimum state of charge|
BF|56|16|1|640|0||%||102.398|5|H|HV battery pack C recommended minimum state of charge|
BF|72|16|1|640|0||%||102.398|4|H|HV battery pack D recommended minimum state of charge|
BF|88|16|1|640|0||%||102.398|3|H|HV battery pack E recommended minimum state of charge|
BF|104|16|1|640|0||%||102.398|2|H|HV battery pack F recommended minimum state of charge|
BF|120|16|1|640|0||%||102.398|1|H|HV battery pack G recommended minimum state of charge|
BF|136|16|1|640|0||%||102.398|0|H|HV battery pack H recommended minimum state of charge|
C1|8|16|1|640|0||%||102.398||H|HV battery recommended maximum state of charge|
C1|24|16|1|640|0||%||102.398|7|H|HV battery pack A recommended maximum state of charge|
C1|40|16|1|640|0||%||102.398|6|H|HV battery pack B recommended maximum state of charge|
C1|56|16|1|640|0||%||102.398|5|H|HV battery pack C recommended maximum state of charge|
C1|72|16|1|640|0||%||102.398|4|H|HV battery pack D recommended maximum state of charge|
C1|88|16|1|640|0||%||102.398|3|H|HV battery pack E recommended maximum state of charge|
C1|104|16|1|640|0||%||102.398|2|H|HV battery pack F recommended maximum state of charge|
C1|120|16|1|640|0||%||102.398|1|H|HV battery pack G recommended maximum state of charge|
C1|136|16|1|640|0||%||102.398|0|H|HV battery pack H recommended maximum state of charge|
C2|8|24|1|1000|0||kWh||16777.2||H|HV battery discharge energy capacity|
C2|32|24|1|1000|0||kWh||16777.2|7|H|HV battery pack A discharge energy capacity|
C2|56|24|1|1000|0||kWh||16777.2|6|H|HV battery pack B discharge energy capacity|
C2|80|24|1|1000|0||kWh||16777.2|5|H|HV battery pack C discharge energy capacity|
C2|104|24|1|1000|0||kWh||16777.2|4|H|HV battery pack D discharge energy capacity|
C2|128|24|1|1000|0||kWh||16777.2|3|H|HV battery pack E discharge energy capacity|
C2|152|24|1|1000|0||kWh||16777.2|2|H|HV battery pack F discharge energy capacity|
C2|176|24|1|1000|0||kWh||16777.2|1|H|HV battery pack G discharge energy capacity|
C2|200|24|1|1000|0||kWh||16777.2|0|H|HV battery pack H discharge energy capacity|
C3|8|8|100|255|0||%||100|7|F|Fuel level input A|
C3|16|8|100|255|0||%||100|6|F|Fuel level input B|
C4|0|32|1|1|0||s||4.29497e+09||D|Exhaust particulate control diagnostic time|
C4|32|32|1|1|0||||4.29497e+09||D|Exhaust particulate control diagnostic count|
C5|8|16|79|1000|0||kPa||5177.27|7|F|Low-pressure fuel pressure A|
C5|24|16|79|1000|0||kPa||5177.27|6|F|Low-pressure fuel pressure B|
C6|15|1|1|1|0||yesno||1|7|D|Particulate warning system active|
C6|16|16|1|1|0||h||65535|6|D|Engine hours with the particulate filter removed or blocked|
C6|32|16|1|1|0||h||65535|5|D|Engine hours with a liquid reagent injection system failure|
C6|48|16|1|1|0||h||65535|4|D|Engine hours with a particulate control monitoring system fault|
C6|9|2|1|1|0||||||D|Particulate level three inducement status|0=Level three inducement inactive~1=Level three inducement enabled~2=Level three inducement active~3=Level three inducement not supported
C6|11|2|1|1|0||||||D|Particulate level two inducement status|0=Level two inducement inactive~1=Level two inducement enabled~2=Level two inducement active~3=Level two inducement not supported
C6|13|2|1|1|0||||||D|Particulate level one inducement status|0=Level one inducement inactive~1=Level one inducement enabled~2=Level one inducement active~3=Level one inducement not supported
C8|2|2|1|1|0||||||D|Particulate control (PCD) warning lamp|0=Warning lamp off~1=Warning lamp continuously on~2=Warning lamp blinking~3=Not utilized
C8|4|2|1|1|0||||||D|NOx control (NCD) warning lamp|0=Warning lamp off~1=Warning lamp continuously on~2=Warning lamp blinking~3=Not utilized
C8|6|2|1|1|0||||||D|Shared NCD and PCD warning lamp|0=Warning lamp off~1=Warning lamp continuously on~2=Warning lamp blinking~3=Not utilized
C9|8|16|100|65535|0||%||100|7|F|O2 concentration bank 1, sensor 5|
C9|24|16|100|65535|0||%||100|6|F|O2 concentration bank 1, sensor 6|
C9|40|16|100|65535|0||%||100|5|F|O2 concentration bank 2, sensor 5|
C9|56|16|100|65535|0||%||100|4|F|O2 concentration bank 2, sensor 6|
C9|72|16|1|8192|0||||7.99988|3|F|O2 sensor lambda bank 1, sensor 5|
C9|88|16|1|8192|0||||7.99988|2|F|O2 sensor lambda bank 1, sensor 6|
C9|104|16|1|8192|0||||7.99988|1|F|O2 sensor lambda bank 2, sensor 5|
C9|120|16|1|8192|0||||7.99988|0|F|O2 sensor lambda bank 2, sensor 6|
CB|8|16|1|100|0||kPa||655.35|7|E|Exhaust pressure bank 1, sensor 2|
CB|24|16|1|100|0||kPa||655.35|6|E|Exhaust pressure bank 2, sensor 2|
CC|8|16|1|1|0|s|rpm|-32768|32767|7|E|Electric motor A speed|
CC|24|16|1|1|0|s|rpm|-32768|32767|6|E|Electric motor B speed|
CC|40|16|1|1|0|s|rpm|-32768|32767|5|E|Electric motor C speed|
CC|56|16|1|1|0|s|rpm|-32768|32767|4|E|Electric motor D speed|
CC|72|16|1|1|0|s|rpm|-32768|32767|3|E|Electric motor E speed|
CC|88|16|1|1|0|s|rpm|-32768|32767|2|E|Electric motor F speed|
CC|104|16|1|1|0|s|rpm|-32768|32767|1|E|Electric motor G speed|
CC|120|16|1|1|0|s|rpm|-32768|32767|0|E|Electric motor H speed|
CD|8|16|1|1|0|s|Nm|-32768|32767|7|E|Electric motor A torque|
CD|24|16|1|1|0|s|Nm|-32768|32767|6|E|Electric motor B torque|
CD|40|16|1|1|0|s|Nm|-32768|32767|5|E|Electric motor C torque|
CD|56|16|1|1|0|s|Nm|-32768|32767|4|E|Electric motor D torque|
CD|72|16|1|1|0|s|Nm|-32768|32767|3|E|Electric motor E torque|
CD|88|16|1|1|0|s|Nm|-32768|32767|2|E|Electric motor F torque|
CD|104|16|1|1|0|s|Nm|-32768|32767|1|E|Electric motor G torque|
CD|120|16|1|1|0|s|Nm|-32768|32767|0|E|Electric motor H torque|
CE|8|16|1|4000|0|s|kPa|-8.192|8.19175|7|F|Evap system vapor pressure C|
CE|24|16|1|500|0|s|kPa|-65.536|65.534|6|F|Evap system vapor pressure C, wide range|
CE|40|16|1|4000|0|s|kPa|-8.192|8.19175|5|F|Evap system vapor pressure D|
CE|56|16|1|500|0|s|kPa|-65.536|65.534|4|F|Evap system vapor pressure D, wide range|
CF|8|16|1|10|-40||C|-40|6513.5|7|E|Catalyst temperature A|
CF|24|16|1|10|-40||C|-40|6513.5|6|E|Catalyst temperature B|
CF|40|16|1|10|-40||C|-40|6513.5|5|E|Catalyst temperature C|
CF|56|16|1|10|-40||C|-40|6513.5|4|E|Catalyst temperature D|
D0|8|16|1|1|0||km||65535|7|H|Distance since state of health update|
D0|24|16|1|10|0||kWh||6553.5|6|H|HV battery remaining reserve energy|
D0|40|16|1|10|0||kWh||6553.5|5|H|HV battery initial reserve energy|
D1|0|16|1|20|0||kW||3276.75||H|HV battery charging limit|
D1|16|16|1|20|0||kW||3276.75||H|HV battery charging power|
D2|8|8|100|255|0||%||100|7|H|State of certified energy|
D2|16|8|100|255|0||%||100|6|H|State of certified range|
D4|0|32|36|1e+07|0|s|kW|-7730.94|7730.94||H|HV battery power over the last second|
D5|8|16|1|20|0||V||3276.75|7|H|Fuel cell system voltage|
D5|24|16|1|2000|0||g/s||32.7675|6|H|Fuel cell fuel consumption|
D5|40|16|72|1000|0||A||4718.52|5|H|Fuel cell current over the last second|
D5|56|32|36|100000|0||kW||1.54619e+06|4|H|Fuel cell power over the last second|
D7|8|8|1|2|0||%||100|7|D|DEF doser B commanded dosing|
D7|16|8|1|1|0||||255|6|D|DEF doser B dosing mode|
D7|24|16|3|10000|0||kg/h||19.2765|5|D|DEF doser B maximum dosing rate|
D8|0|8|1|1|0||||||H|Battery capacity calculation|0=Not ready~1=Ready
D9|0|32|1|1000|0||kWh||4.29497e+06||H|HV battery calculated usable energy|
DA|0|32|36|10000|0|s|A|-7.73094e+06|7.73094e+06||H|HV battery current over the last second|
DC|8|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #21 timer 1 active|
DC|40|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #21 timer 2 active|
DC|72|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #22 timer 1 active|
DC|104|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #22 timer 2 active|
DC|136|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #23 timer 1 active|
DC|168|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #23 timer 2 active|
DC|200|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #24 timer 1 active|
DC|232|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #24 timer 2 active|
DC|264|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #25 timer 1 active|
DC|296|32|1|1|0||s||4.29497e+09||E|Total run time with EI-AECD #25 timer 2 active|`;
const STD_GROUPS = { E: "Std · engine", F: "Std · fuel & O2", D: "Std · emissions & diesel", H: "Std · hybrid / EV" };
const STD_SIGS = STD_RAW.split("\n").filter(Boolean).map((line) => {
  const f = line.split("|");
  return { std: true, hdr: "", rax: "", req: "01" + f[0], bix: +f[1], len: +f[2], mul: +f[3], div: +f[4], add: +f[5],
    sign: f[6].includes("s"), lsb: f[6].includes("l"), unit: f[7], min: f[8] === "" ? null : +f[8], max: f[9] === "" ? null : +f[9],
    sup: f[10] === "" ? null : +f[10], grp: STD_GROUPS[f[11]] || STD_GROUPS.E, name: f[12],
    map: f[13] ? Object.fromEntries(f[13].split("~").map((kv) => { const i = kv.indexOf("="); return [kv.slice(0, i), kv.slice(i + 1)]; })) : null };
});
const STD_PIDS = new Set(STD_SIGS.map((g) => g.req.slice(2)));
// Standard readings for one PID's data bytes -> [[name, text], ...] (used by the freeze frame)
function stdDecode(pid, bytes) {
  const out = [];
  for (const g of STD_SIGS) {
    if (g.req !== "01" + pid) continue;
    if (g.sup != null && !((bytes[g.sup >> 3] >> (7 - (g.sup & 7))) & 1)) continue;
    const v = extractBits(bytes, g.bix, g.len, g.lsb, g.sign);
    const text = v == null ? null : fmtOem(g, v);
    if (text != null) out.push([cleanName(g.name), text]);
  }
  return out;
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
  await setHeader(funcHeader());   // functional: every emissions module answers
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
  const add = (hdr, rax, name, pri, tst) => {
    if (!hdr || hdr === "7DF" || !/^([0-9A-F]{3}|DA[0-9A-F]{2})$/.test(hdr)) return;
    if (hdr.length === 3 && base29()) return;   // an 11-bit address on a 29-bit car: nobody there
    const m = map.get(hdr) || { hdr, rax: rax || "", pri: pri || "", tst: tst || "", names: {} };
    if (rax && !m.rax) m.rax = rax;
    if (name) m.names[name] = (m.names[name] || 0) + 1;
    map.set(hdr, m);
  };
  SWEEP.ALL.forEach((a) => add(a));
  (SWEEP[profile()] || []).forEach((a) => { const [h, r] = a.split("|"); add(h, r); });
  if (base29()) SWEEP.HONDA.forEach((a) => add(a));
  (Array.isArray(ARGS.oem) ? ARGS.oem : []).forEach((g) => add(g.hdr, g.rax, PATH_MODULE[g.path], g.pri, g.tst));
  (Array.isArray(ARGS.learned) ? ARGS.learned : []).forEach((g) => add(g.hdr, g.rax, PATH_MODULE[g.path], g.pri, g.tst));
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
  await setAddr(mod.hdr, mod.rax, mod.pri, mod.tst);
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

// Calibration (software) IDs, their check numbers (CVN) and the computer's name — what a reflash TSB is matched against
let ecuInfo = null;
async function readEcuInfo() {
  ecuInfo = null;
  const text = (hex) => bytesOf(hex).filter((b) => b >= 32 && b < 127).map((b) => String.fromCharCode(b)).join("").trim();
  // every reply starts 49 <pid> <count or line number>; what's left is fixed-size items (16 / 4 / 20 bytes)
  const get = async (pid) => messages(await sendCmd("09" + pid, 2500)).filter((m) => m.startsWith("49" + pid)).map((m) => m.slice(6)).join("");
  try {
    const cal = [], cvn = [], name = [];
    let has = null;   // which info items this car has (so it isn't asked for ones it doesn't)
    try { has = await supported("09", ["00"]); } catch (_) {}
    const ok = (pid) => !has || has.has(pid);
    let d = ok("04") ? await get("04") : "";
    for (let i = 0; i + 32 <= d.length; i += 32) { const t = text(d.substr(i, 32)); if (t) cal.push(t); }
    d = ok("06") ? await get("06") : "";
    for (let i = 0; i + 8 <= d.length; i += 8) if (!/^0+$/.test(d.substr(i, 8))) cvn.push(d.substr(i, 8));
    d = ok("0A") ? await get("0A") : "";
    for (let i = 0; i + 40 <= d.length; i += 40) { const t = text(d.substr(i, 40)); if (t) name.push(t); }
    const uniq = (a) => [...new Set(a)];
    if (cal.length || cvn.length || name.length) ecuInfo = { cal: uniq(cal), cvn: uniq(cvn), name: uniq(name) };
  } catch (_) {}
  const box = $("ecuBox");
  if (!ecuInfo) { box.style.display = "none"; return; }
  if (ecuInfo.cal.length) { shown.calid = ecuInfo.cal.join(", "); LABEL.calid = "Calibration ID (software)"; }
  if (ecuInfo.cvn.length) { shown.cvn = ecuInfo.cvn.join(", "); LABEL.cvn = "Calibration check number (CVN)"; }
  box.style.display = "block";
  box.innerHTML = `<b style="color:var(--w)">🪪 Computer software</b> ` +
    [ecuInfo.name.length ? "Module: " + esc(ecuInfo.name.join(", ")) : "", ecuInfo.cal.length ? "Calibration ID: <b>" + esc(ecuInfo.cal.join(", ")) + "</b>" : "",
     ecuInfo.cvn.length ? "CVN: " + esc(ecuInfo.cvn.join(", ")) : ""].filter(Boolean).join(" · ") +
    `<div class="note">Reflash TSBs list the calibration IDs they fix — compare this one before replacing parts.</div>`;
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
    const due = FOCUS ? active.filter((p) => FOCUS.includes(p))   // a test needs these fast: read only them
                      : active.filter((p) => cycle === 1 || cycle % TIER_EVERY[PIDS[p].tier] === 0);
    await txn(() => pollPids(due));
    cmds += batchOK ? Math.ceil(due.length / 6) : due.length;
    if (token !== loopToken) break;
    if (cycle % 6 === 0 && !FOCUS) {
      const r = await txn(() => sendCmd("ATRV", 600));
      const m = (r || "").match(/(\d+\.\d+)/);
      if (m) setTile("volt", parseFloat(m[1]).toFixed(1) + " V", parseFloat(m[1]));
    }
    const discovering = oemCmds.some((c) => c.state === "new");
    if (oemCmds.length && !FOCUS && cycle % (discovering ? 2 : 3) === 0) await txn(pollEnhanced);
    if (cycle > 12 && cycle % 6 === 0) maybeAutoHunt();   // first time on this kind of car: find every reading it has
    if (!FOCUS) await extraPolls(cycle);
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
  const throttleShut = num.tps != null && num.tps <= (minTps ?? closedTps ?? num.tps) + 1.5;
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
function back(secs, key) {   // a reading from `secs` seconds ago in the buffer
  const t = nowS(), i = GB_KEYS.indexOf(key) + 1;
  for (let j = GB.length - 1; j >= 0; j--) if (t - GB[j][0] >= secs) return GB[j][i];
  return null;
}
const GB_KEYS = ["rpm", "spd", "tps", "app", "load", "stft1", "ltft1", "map", "maf", "frp", "volt"];
let glitchCool = {};
function glitchTick() {
  const t = nowS();
  GB.push([t, ...GB_KEYS.map((k) => (frsh(k, 6) ? r2(num[k]) : null))]);
  while (GB.length && t - GB[0][0] > 25) GB.shift();
  learnClosed();   // learn "foot off" any time the engine runs, not only on a test drive
  if (!driveOn) return;
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
  stumbleCheck(t, fire);
  const st = num.stft1, st2 = back(2, "stft1");
  if (st != null && st2 != null && trimsTrustworthy() && Math.abs(st - st2) > 15 && Math.abs(st) > 20)
    fire("trimspike", `Fuel trim spike, bank 1 short term ${Math.round(st)} percent.`);
  const frp = num.frp, frp5 = back(5, "frp"), tps5 = back(5, "tps");
  // Direct injection (rail well over 150 psi): the PCM commands pressure up and down with load, so a drop when the
  // driver lifts off is normal. Only flag it there if the throttle is steady or still opening, and the drop is bigger.
  const gdi = frp5 != null && frp5 > 150;
  const footSteady = num.tps != null && tps5 != null && num.tps >= tps5 - 2;
  if (frp != null && frp5 != null && frp5 > 20 && frp < frp5 * (gdi ? 0.6 : 0.72) && (num.rpm ?? 0) > 500 && (!gdi || footSteady))
    fire("frpdrop", `Fuel pressure dropped from ${Math.round(frp5)} to ${Math.round(frp)} PSI${gdi ? " with steady throttle" : ""}.`);
}
// "Foot off" positions are learned (the lowest reading seen with the engine running), because many throttle sensors
// read 10-20% with the pedal fully released. Prefer the PEDAL sensor (what the foot does) over the throttle blade.
let closedTps = null, closedApp = null, hasPedal = false;
function learnClosed() {
  if ((num.rpm ?? 0) < 400 || GB.length < 2) return;
  const prev = GB[GB.length - 2];
  for (const k of ["tps", "app"]) {
    const p = prev[GB_KEYS.indexOf(k) + 1];
    if (!frsh(k, 3) || p == null) continue;
    const v = Math.max(num[k], p);   // must read low two passes in a row, so one glitchy reading can't fool it
    if (k === "tps") closedTps = closedTps == null ? v : Math.min(closedTps, v);
    else { closedApp = closedApp == null ? v : Math.min(closedApp, v); hasPedal = true; }
  }
}
// Is the driver's foot ON the gas and not lifting? Returns null when off, lifting, or unknown (unknown never alarms).
function footOnSteady() {
  const usePedal = hasPedal || active.includes("49") || active.includes("4A");   // drive-by-wire: the pedal sensor is what the foot does
  const k = usePedal ? "app" : "tps", closed = usePedal ? closedApp : closedTps;
  if (!frsh(k, 3) || closed == null) return null;
  const now = num[k], before = back(1.2, k);
  if (now == null || before == null) return null;
  const margin = usePedal ? 6 : 5;   // electronic throttles can sit a few % open when you lift off
  if (now < closed + margin || before < closed + margin) return null;   // foot is off (or was a moment ago)
  if (now < before - 3) return null;                                     // foot is lifting
  return { k, now, pressed: now - closed };
}
// Stumble = RPM falls while the foot is held ON the gas. Normal RPM drops that are NOT stumbles: lifting off,
// an upshift (speed keeps climbing, RPM stays down), the torque converter clutch locking (RPM drops and stays down).
let dip = null;   // an RPM drop that changed the RPM-to-speed ratio: watch whether RPM comes back (stumble) or stays down
function stumbleCheck(t, fire) {
  const foot = footOnSteady();
  const rpm = num.rpm, spd = num.spd;
  if (!foot || rpm == null || spd == null || spd <= 5 || inDecel()) { dip = null; return; }
  if (dip) {
    if (t - dip.t > 3 || spd > dip.spd + 2 || Math.abs(foot.now - dip.ped) > 4) dip = null;   // stayed down / sped up / foot moved
    else if (rpm >= dip.low + 0.6 * (dip.from - dip.low)) {
      fire("stumble", `RPM dipped ${Math.round(dip.from - dip.low)} and came back with your foot steady on the gas. ` +
                      `Engine stumble, or the torque converter clutch slipping.`);
      dip = null; return;
    } else { dip.low = Math.min(dip.low, rpm); return; }
  }
  const rpm1 = back(1.2, "rpm"), spd1 = back(1.2, "spd");
  if (rpm1 == null || spd1 == null || spd1 <= 5) return;
  const drop = rpm1 - rpm;
  if (drop <= Math.max(250, 0.12 * rpm1)) return;
  if (spd > spd1 + 0.5) return;                                          // still speeding up = an upshift
  if (Math.abs((rpm / spd) / (rpm1 / spd1) - 1) < 0.10)                  // same RPM-to-speed ratio = same gear, no slip change
    fire("stumble", `Stumble caught. RPM dropped ${Math.round(drop)} with your foot steady on the gas.`);
  else dip = { t, from: rpm1, low: rpm, spd: spd1, ped: foot.now };
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
  const id = aiPendingId, t0 = Date.now();
  const tick = () => { if (aiPendingId === id && mode !== "drive")
    $("aiBox").innerHTML = `<span style="color:var(--o)">🤖 The AI team is analyzing live data, codes, monitors, Mode $06 and test results… ${Math.round((Date.now() - t0) / 1000)} s (usually 1–2 min)</span>`; };
  sendValue({ type: "ai", id: aiPendingId, mode, at: new Date().toLocaleTimeString(), pids: snapshot(), dtcs, readiness: readinessSummary, mode6: mode6Summary, tests: T.results || {}, flags: plausNow(),
              ran: RUN.ran.slice() });
  tick();
  const timer = setInterval(() => { if (aiPendingId !== id) clearInterval(timer); else tick(); }, 1000);
  setTimeout(() => { if (aiPendingId === id) { aiPendingId = null; clearInterval(timer);
    if (mode !== "drive") $("aiBox").textContent = "No answer after 6 minutes. If it finishes later it will still show here — or tap AI Check to try again.";
    logEvent("ai", "AI check (" + mode + ")", "No answer from the app within 6 min"); } }, 360000);
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
const BTN_IDS = ["pauseBtn", "driveBtn", "readBtn", "clearBtn", "aiBtn", "syncBtn", "modBtn", "evapBtn", "huntBtn"];
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
  baseProto = curProto = dpn.slice(-1); curCra = ""; curPri = "";
  batchOK = false; fastOK = true; baseHeader = "7DF";

  if (isCan) {   // talk to the engine computer directly: no duplicate replies from other modules, faster
    const direct = base29() ? "DA10" : "7E0";   // 29-bit cars (most Hondas): the engine computer is 18 DA 10 F1
    baseHeader = funcHeader();
    await setHeader(direct);
    if (messages(await sendCmd("0100", 1500)).some((m) => m.startsWith("4100"))) baseHeader = direct;
    else await setHeader(baseHeader);
  }

  log("Reading supported PIDs…");
  const sup = await supported("01", ["00", "20", "40", "60", "80", "A0", "C0"]);
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
    connected = true; enableBtns(true); autoHuntTried = false;
    $("bleBtn").textContent = "✅ Connected";

    log("Reading VIN & codes…");
    await readVin(); await readDtcs(); await readFreezeFrame();
    try { await readEcuInfo(); } catch (_) {}
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
    pids: snapshot(), readiness: readinessSummary, mode6: mode6Summary, flags: plausNow(), at: new Date().toLocaleTimeString(), ecu: ecuInfo });
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
    await setHeader(funcHeader());
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
    await setHeader(funcHeader());
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
  requestAi(RUN.on ? "followup" : "full");   // full AI review including the test results (a follow-up if the AI asked for the drive)
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
    const first = ["03", "04", "05", "06", "07", "08", "09", "0A", "0B", "0C", "0D", "0E", "0F", "10", "11", "23", "2F", "33", "42", "43", "44", "1F", "31", "21", "46"];
    // Ask the car which readings its freeze frame holds, then read every one of them (the usual ones first)
    let ffSup = null;
    try {
      const set = new Set();
      for (const r of ["00", "20", "40", "60", "80", "A0", "C0"]) {
        const m = messages(await sendCmd("02" + r + "00", 1000)).find((x) => x.startsWith("42" + r + "00") && x.length >= 14);
        if (!m) break;
        const bits = parseInt(m.substr(6, 8), 16) >>> 0;
        for (let i = 0; i < 32; i++) if ((bits >>> (31 - i)) & 1) set.add((parseInt(r, 16) + i + 1).toString(16).toUpperCase().padStart(2, "0"));
        if (!(bits & 1)) break;
      }
      if (set.size) ffSup = set;
    } catch (_) {}
    const want = ffSup ? [...first.filter((p) => ffSup.has(p)), ...[...ffSup].filter((p) => !first.includes(p) && (PIDS[p] || STD_PIDS.has(p)))].slice(0, 70)
                       : first.filter((p) => !sup01 || sup01.has(p));
    const vals = {};
    for (const p of want) {
      const m = messages(await sendCmd("02" + p + "00", 700)).find((x) => x.startsWith("42" + p + "00"));
      if (!m) continue;
      const b = bytesOf(m.slice(6));
      const d = PIDS[p];
      if (d) {
        if (b.length < d.len) continue;
        const t = d.fn(b); if (t != null) vals[LABEL[d.tile] || d.tile] = t;
      } else for (const [name, text] of stdDecode(p, b)) vals[name] = text;   // any other standard reading
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
  const focus = T.drive.on || RUN.on || ["mis", "rdy"].includes(testTab);
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
    ${tccLiveHtml()}
    ${(() => { const c = tccAnalyze(); return c ? `<div class="verdict"><b>🌀 Torque converter:</b> ${c.g ? `<b class="${gradeCls(c.g)}">${c.g === "g" ? "OK" : c.g === "r" ? "PROBLEM" : "CHECK"}</b> — ` : ""}${esc(c.text)}${c.events.length ? "<br><span class='note'>" + c.events.slice(-5).map((e) => esc(e.at + " — " + e.text)).join("<br>") + "</span>" : ""}</div>` : ""; })()}`;
}
function tccLiveHtml() {
  const cell = (k, unit, src) => `<td class="tnum" style="font-size:1.3rem">${num[k] != null && fresh(k, 3) ? Math.round(num[k]) + unit : "—"}</td>`;
  const has = TCC && (TCC.src || TCC.desSrc || TCC.dutySrc);
  const st = TCC && TCC.stateSrc ? tccOnFrom(TCC.lastState) : null;
  return `<div class="verdict" style="border-color:var(--o)"><b>🌀 TCC live</b>
    <table class="ttab"><tr><th>TCC slip</th><th>TCC desired</th><th>TCC command</th>${TCC && TCC.stateSrc ? "<th>TCC state</th>" : ""}</tr>
    <tr>${cell("tccslip", " rpm")}${cell("tccdes", " rpm")}${cell("tccduty", "%")}${TCC && TCC.stateSrc ? `<td class="tnum">${st == null ? "—" : st ? "ON" : "OFF"}</td>` : ""}</tr></table>
    ${has ? `<canvas class="tplot" id="tccPlot"></canvas><div class="note">Orange = actual slip · green dashed = desired slip (rpm, left) · blue = TCC command % (right). Last 90 s.</div>`
          : `<div class="note">Waiting for the factory TCC readings — start recording (or a test drive) with Enhanced data loaded. If your car doesn't send them to the adapter, share your scan tool screen (👀) and the AI reads them there.</div>`}
    ${TCC && (TCC.src || TCC.desSrc || TCC.dutySrc) ? `<div class="note">From: ${[TCC.src && "slip = " + esc(TCC.src), TCC.desSrc && "desired = " + esc(TCC.desSrc), TCC.dutySrc && "command = " + esc(TCC.dutySrc), TCC.stateSrc && "state = " + esc(TCC.stateSrc)].filter(Boolean).join(" · ")}</div>` : ""}
  </div>`;
}


// ---------- 🌀 Torque converter clutch (TCC) slip / shudder monitor ----------
// Uses the factory TCC slip reading when the car has one; otherwise watches RPM vs speed at steady cruise.
let TCC = null;
function tccReset() { TCC = { w: [], ev: [], kinds: {}, lastChk: 0, run: 0, runOn: 0, runErr: 0, steadyS: 0, slipSteady: [], cmdSteady: [], trace: [],
                       src: null, desSrc: null, dutySrc: null, stateSrc: null, spokeT: {} }; }
tccReset();
const range = (a) => (a.length ? Math.max(...a) - Math.min(...a) : 0);
const median = (a) => { if (!a.length) return null; const b = [...a].sort((x, y) => x - y); return b[Math.floor(b.length / 2)]; };
function tccSig(role) {
  for (const c of oemCmds) { if (c.state !== "live") continue;
    for (const g of c.sigs) if (g.watch === role && g.tile && fresh(g.tile, 3)) return { tile: g.tile, label: g.label }; }
  return null;
}
function tccSlipTile() { return tccSig("tcc"); }
function tccOnFrom(text) {   // "ON", "Locked", "Applied" -> true; "OFF", "Unlocked", "Released" -> false
  const t = String(text ?? "").toLowerCase();
  if (/\b(off|no|unlocked|released|release|disengaged|open|inactive)\b/.test(t) || t === "0") return false;
  if (/\b(on|yes|locked|lock|applied|apply|engaged|full|closed|active)\b/.test(t) || t === "1") return true;
  return null;
}
const TCC_SAY = {
  shudder: (e) => `Possible torque converter shudder at ${Math.round(e.spd)} miles per hour.`,
  nolock: (e) => `Torque converter slipping at cruise, about ${Math.round(e.slip)} RPM.`,
  flareslip: (e) => `Torque converter slip jumped to ${Math.round(e.slip)} RPM without more throttle.`,
  surge: () => `RPM surging at steady speed. Possible torque converter shudder.`,
  flare: () => `RPM flare without a speed change. Possible converter or clutch slip.`,
};
TCC_SAY.notholding = (e) => `Converter clutch commanded on but still slipping ${Math.round(e.slip)} RPM.`;
TCC_SAY.offtarget = (e) => `Converter slip is ${Math.round(e.slip)}, the transmission computer wants ${Math.round(e.des)}.`;
TCC_SAY.stuckon = () => `Converter clutch looks applied while commanded off.`;
TCC_SAY.dutyhunt = () => `Converter clutch command is hunting at steady speed.`;
TCC_SAY.notcmd = () => `The converter clutch isn't being commanded on at highway cruise.`;
const TCC_NEED = { shudder: 2, nolock: 1, flareslip: 2, surge: 3, flare: 2, notholding: 1, offtarget: 2, stuckon: 2, dutyhunt: 3, notcmd: 1 };
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
  const t = nowS(), src = tccSig("tcc"), dsS = tccSig("tccdes"), duS = tccSig("tccduty"), stS = tccSig("tccstate"), tuS = tccSig("turbine");
  let slip = null;
  if (src) { slip = num[src.tile]; TCC.src = src.label; }
  else if (tuS) { slip = num.rpm - num[tuS.tile]; TCC.src = `engine RPM − ${tuS.label}`; }   // no slip reading: work it out
  const des = dsS ? num[dsS.tile] : null, duty = duS ? num[duS.tile] : null, on = stS ? tccOnFrom(shown[stS.tile] ?? num[stS.tile]) : null;
  if (dsS) TCC.desSrc = dsS.label; if (duS) TCC.dutySrc = duS.label; if (stS) { TCC.stateSrc = stS.label; TCC.lastState = shown[stS.tile] ?? num[stS.tile]; }
  const setV = (k, v, label) => { if (v != null && isFinite(v)) { num[k] = v; numT[k] = t; LABEL[k] = label; } };
  setV("tccslip", slip, "TCC slip (rpm)"); setV("tccdes", des, "TCC desired slip (rpm)"); setV("tccduty", duty, "TCC command (%)");
  const W = TCC.w;
  if (!W.length || t - W[W.length - 1][0] >= 0.15) W.push([t, num.rpm, num.spd, num.tps ?? null, slip, inDecel() ? 1 : 0, des, duty, on]);
  while (W.length && t - W[0][0] > 12) W.shift();
  if (!TCC.trace.length || t - TCC.trace[TCC.trace.length - 1][0] >= 0.25) { TCC.trace.push([t, slip, des, duty]); while (TCC.trace.length && t - TCC.trace[0][0] > 90) TCC.trace.shift(); }
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
    // What the transmission computer is asking for vs what the converter does
    const du = w.map((s) => s[7]).filter((x) => x != null), de = w.map((s) => s[6]).filter((x) => x != null), onS = w.map((s) => s[8]).filter((x) => x != null);
    const mdu = du.length ? median(du) : null, mde = de.length ? median(de) : null;
    const cmdKnown = mdu != null || onS.length > 0 || mde != null;
    const cmdOn = (mdu != null && mdu >= 80) || (onS.length && onS.filter(Boolean).length >= onS.length * 0.75) || (mde != null && mde <= 30);
    const cmdOff = (mdu != null && mdu <= 5) || (onS.length && !onS.some(Boolean));
    const following = mde != null && Math.abs(m - mde) <= Math.max(60, 0.5 * mde);   // the TCM wants this much slip
    TCC.cmdSteady.push([Math.round(ms), Math.round(m), mde != null ? Math.round(mde) : null, mdu != null ? Math.round(mdu) : null]);
    if (TCC.cmdSteady.length > 600) TCC.cmdSteady.shift();
    if (cmdOn && m > 100) {
      if (++TCC.runOn >= 5) { tccEvent("notholding", `TCC commanded ON${mdu != null ? ` (${Math.round(mdu)}% command)` : ""}${mde != null ? `, desired slip ${Math.round(mde)} rpm` : ""} but actual slip stays ${Math.round(m)} rpm at ${Math.round(ms)} mph — converter clutch not holding (worn lining, low line pressure, TCC solenoid/valve, fluid)`, { slip: m, duty: mdu, des: mde }); TCC.runOn = 0; }
    } else TCC.runOn = 0;
    if (mde != null && !cmdOn && Math.abs(m - mde) > Math.max(60, 0.5 * mde)) {
      if (++TCC.runErr >= 6) { tccEvent("offtarget", `Slip ${Math.round(m)} rpm vs desired ${Math.round(mde)} rpm at ${Math.round(ms)} mph — the converter isn't following what the TCM asks for`, { slip: m, des: mde }); TCC.runErr = 0; }
    } else TCC.runErr = 0;
    if (cmdOff && m < 20 && mr > 1100 && ms < 40)
      tccEvent("stuckon", `TCC commanded OFF but slip is only ${Math.round(m)} rpm at ${Math.round(ms)} mph — converter clutch may be stuck applied (does it stall when coming to a stop?)`, { slip: m });
    if (du.length >= 6 && range(du) >= 35)
      tccEvent("dutyhunt", `TCC command swinging ${Math.round(Math.min(...du))}–${Math.round(Math.max(...du))}% at a steady ${Math.round(ms)} mph — the TCM is fighting slip (common with shudder or a worn converter clutch)`, { duty: mdu });
    // Highway cruise, light steady throttle, converter still slipping 120+ rpm for 8 s = not locking / lock-up clutch slipping
    if (ms >= 45 && m >= 120 && m <= 900) {
      if (++TCC.run >= 8) {
        if (cmdKnown && cmdOff) tccEvent("notcmd", `At a steady ${Math.round(ms)} mph the TCM isn't commanding the converter clutch on (slip ${Math.round(m)} rpm) — look for a code or condition blocking lock-up (coolant temp, brake switch, TPS, a trans code)`, { slip: m });
        else if (!cmdOn && !following) tccEvent("nolock", `TCC slip held about ${Math.round(m)} rpm for 8+ s at a steady ${Math.round(ms)} mph cruise — converter not locking, or lock-up clutch slipping`, { slip: m });
        TCC.run = 0;
      }
    } else TCC.run = 0;
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
  const bad = n("nolock") >= 1 || n("notholding") >= 1 || n("stuckon") >= 2 || n("shudder") >= 3 || n("flareslip") >= 3;
  const warn = bad || n("offtarget") >= 2 || n("dutyhunt") >= 2 || n("notcmd") >= 1 || n("shudder") + n("flareslip") + n("surge") + n("flare") >= 2;
  const g = bad ? "r" : warn ? "y" : TCC.steadyS >= 30 ? "g" : null;
  const cr = TCC.slipSteady.filter((s) => s[0] >= 45), typ = cr.length ? median(cr.map((s) => s[1])) : null;
  const parts = [];
  if (n("shudder")) parts.push(`${n("shudder")}× slip swinging at steady speed (shudder)`);
  if (n("nolock")) parts.push(`${n("nolock")}× converter slipping 120+ rpm at highway cruise`);
  if (n("flareslip")) parts.push(`${n("flareslip")}× slip jumped with no extra throttle`);
  if (n("surge")) parts.push(`${n("surge")}× RPM surging at steady speed`);
  if (n("flare")) parts.push(`${n("flare")}× RPM flare with no speed change`);
  if (n("notholding")) parts.push(`${n("notholding")}× commanded ON but still slipping (clutch not holding)`);
  if (n("offtarget")) parts.push(`${n("offtarget")}× actual slip not following the desired slip`);
  if (n("stuckon")) parts.push(`${n("stuckon")}× looks applied while commanded OFF`);
  if (n("dutyhunt")) parts.push(`${n("dutyhunt")}× TCC command hunting at steady speed`);
  if (n("notcmd")) parts.push(`${n("notcmd")}× TCC not commanded on at highway cruise`);
  let text = !g ? "Not enough steady cruising yet (need ~30 s total at a steady 25+ mph)." :
    g === "g" ? `No converter slip or shudder seen in ${TCC.steadyS} s of steady driving.` :
    parts.join("; ") + ". " + (bad ? "Likely torque converter clutch problem." : "Possible torque converter clutch problem.") +
    (n("notcmd") && !bad ? " Next: the TCM is choosing not to lock it — check for trans/engine codes and the lock-up conditions (coolant temp, brake switch, TPS, vehicle speed), then command TCC on with your scan tool to see if it can lock."
     : n("stuckon") ? " Next: check whether it stalls coming to a stop; command TCC off with your scan tool and watch slip — a stuck TCC solenoid/valve or a converter clutch that won't release."
     : " Next: check fluid level/condition and for TSBs (fluid exchange / TCM reflash for shudder), then command TCC on with a scan tool and watch slip.");
  const cc = TCC.cmdSteady.filter((s) => s[0] >= 45);
  const typical = cc.length ? { slip_rpm: median(cc.map((s) => s[1])), desired_rpm: median(cc.map((s) => s[2]).filter((x) => x != null)),
                                command_pct: median(cc.map((s) => s[3]).filter((x) => x != null)) } : null;
  text += hasSlip ? ` Using factory reading: ${TCC.src}${typ != null ? ` (typical slip at 45+ mph cruise: ${typ} rpm${typical && typical.desired_rpm != null ? `, desired ${typical.desired_rpm}` : ""}${typical && typical.command_pct != null ? `, command ${typical.command_pct}%` : ""}; locked is about 0–40)` : ""}.`
    : " No factory TCC slip reading on this car — judged from RPM vs speed, which only catches bigger slip/shudder.";
  if (hasSlip && !TCC.desSrc && !TCC.dutySrc && !TCC.stateSrc) text += " This car doesn't send the TCC desired slip or command to the adapter — share your scan tool screen (👀) to see them.";
  return { g, text, kinds: k, hasSlip, steadyS: TCC.steadyS, events: TCC.ev.slice(-20), typical,
           sources: { slip: TCC.src, desired: TCC.desSrc, command: TCC.dutySrc, state: TCC.stateSrc } };
}

function tccPlot() {
  const P = plotSetup("tccPlot"); if (!P || !TCC) return;
  const { g, c } = P, tr = TCC.trace;
  if (tr.length < 2) { g.fillStyle = c("--muted"); g.font = "12px sans-serif"; g.fillText("Waiting for TCC readings…", 44, 60); return; }
  const t0 = tr[0][0], t1 = Math.max(tr[tr.length - 1][0], t0 + 1);
  const vals = tr.flatMap((p) => [p[1], p[2]]).filter((x) => x != null);
  const hi = Math.max(150, ...vals.map((x) => x + 20)), lo = Math.min(0, ...vals);
  const A = axes(P, t0, t1, lo, hi, 40, 18), R = (pct) => 8 + (1 - pct / 100) * A.ph;   // right axis: 0-100 %
  for (let k = 0; k <= 2; k++) { const v = lo + (hi - lo) * k / 2; g.beginPath(); g.moveTo(A.L, A.Y(v)); g.lineTo(A.L + A.pw, A.Y(v)); g.stroke(); g.textAlign = "right"; g.fillText(Math.round(v) + "", A.L - 4, A.Y(v) + 3); }
  g.textAlign = "left"; [0, 50, 100].forEach((p) => g.fillText(p + "%", A.L + A.pw - 26, R(p) + 3));
  const line = (i, col, dash, y) => { const pts = tr.filter((p) => p[i] != null); if (pts.length < 2) return;
    g.strokeStyle = c(col); g.lineWidth = 2; g.setLineDash(dash); g.beginPath();
    pts.forEach((p, j) => { const X = A.X(p[0]), Y = y(p[i]); j ? g.lineTo(X, Y) : g.moveTo(X, Y); }); g.stroke(); g.setLineDash([]); };
  line(3, "--b", [], (v) => R(Math.max(0, Math.min(100, v))));
  line(2, "--g", [6, 4], A.Y);
  line(1, "--o", [], A.Y);
  g.fillStyle = c("--muted"); g.textAlign = "left"; g.fillText("rpm", 4, 12);
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
  if (testTab === "trans") { linePlot("transPlot", T.trans.pts.map((p) => [p[0], p[1]]), "--p", "rpm/mph", { empty: "Drive to record." }); tccPlot(); }
  if (testTab === "nvh") { const S = T.nvh.spec, R = T.nvh.res; specPlot("nvhPlot", S && S.spec, S && S.fs, S && S.n, S ? S.fmax : 30, R && R.orders ? R.orders.map((o) => [o[1], o[0].split(" ")[0]]) : []); }
  if (testTab === "tail") {
    const P = plotSetup("tailPlot"), R = T.tail.res; if (!P) return; const { g, c } = P;
    if (!R || R.error) { g.fillStyle = c("--muted"); g.font = "12px sans-serif"; g.fillText("No recording yet.", 44, 90); return; }
    const hi = Math.max(...R.orders.map((o) => o.a)) || 1, A = axes(P, 0, R.orders.length + 1, 0, hi), w = A.pw / (R.orders.length + 1) * 0.6;
    R.orders.forEach((o) => { g.fillStyle = o.firing ? c("--g") : c("--r"); const x = A.X(o.k) - w / 2, y = A.Y(o.a); g.fillRect(x, y, w, A.Y(0) - y); g.fillStyle = c("--muted"); g.textAlign = "center"; g.fillText(o.k + "×", A.X(o.k), P.H - 4); });
  }
}

// ===================== 🧪 AI test runner: the app runs the tests the AI asks for =====================
// The AI check ends with a list of tests from this catalog. One tap and the app runs them in order, saying out loud
// when the tech has to do something (rev it, snap it, pinch a hose), then sends the results straight back to the AI team.
const AUTO_TESTS = {
  mode06:   { name: "Re-read Mode $06 results", phase: 0, mins: 0.3 },
  monitors: { name: "Re-read readiness monitors", phase: 0, mins: 0.1 },
  fuelhold: { name: "Fuel pressure hold — key on, engine off (2 min)", phase: 1, mins: 2.5 },
  crank:    { name: "Cranking / starting test", phase: 1, mins: 0.7 },
  idle:     { name: "Warm idle check — trims, O2s, misfires (1 min)", phase: 2, mins: 1.2 },
  purge:    { name: "EVAP purge check — you pinch the purge hose when told", phase: 2, mins: 1.7 },
  o2:       { name: "O2 sensor response — idle, 2,500 RPM, snap, let off", phase: 3, mins: 1.5 },
  vacuum:   { name: "Vacuum test from the MAP sensor — idle, snap, 2,500 hold", phase: 3, mins: 1.3 },
  charging: { name: "Charging — idle, then headlights + blower + defroster on", phase: 3, mins: 0.7 },
  drive:    { name: "Test drive — catalyst, fuel trims under load, transmission", phase: 4, mins: 10 },
};
const RUN = { offer: [], on: false, list: [], i: 0, step: "", left: null, stop: false, skip: false, ran: [] };
let FOCUS = null;   // while a test needs fast readings, the live loop reads only these PIDs
let lastRunRender = 0;
function offerTests(ids) { RUN.offer = (ids || []).filter((x) => AUTO_TESTS[x] && !RUN.ran.includes(x)); renderRun(true); }
function renderRun(force) {
  const box = $("runBox"); if (!box) return;
  if (!force && nowS() - lastRunRender < 0.4) return;
  lastRunRender = nowS();
  if (RUN.on) {
    const id = RUN.list[RUN.i], t = AUTO_TESTS[id];
    box.style.display = "block";
    box.innerHTML = `<b>🧪 Running the AI's tests — ${RUN.i + 1} of ${RUN.list.length}: ${t ? t.name : ""}</b>
      <div style="font-size:1.2rem;margin:8px 0;color:var(--o);font-weight:700">${esc(RUN.step)}${RUN.left != null ? ` <span class="note">(${RUN.left} s)</span>` : ""}</div>
      <button class="tbtn sec" data-run="skip">Skip this test</button> <button class="tbtn sec" data-run="stop">Stop all</button>
      <div class="note" style="margin-top:6px">${RUN.list.map((x, k) => (k < RUN.i ? "✅ " : k === RUN.i ? "▶️ " : "⬜ ") + AUTO_TESTS[x].name).join("<br>")}</div>`;
  } else if (RUN.offer.length) {
    const mins = Math.max(1, Math.round(RUN.offer.filter((x) => x !== "drive").reduce((s, x) => s + AUTO_TESTS[x].mins, 0)));
    box.style.display = "block";
    box.innerHTML = `<b>🧪 The AI wants to run ${RUN.offer.length} test${RUN.offer.length > 1 ? "s" : ""} itself:</b><br>
      ${RUN.offer.map((x) => "• " + AUTO_TESTS[x].name).join("<br>")}
      <div style="margin-top:8px"><button class="tbtn" data-run="go">▶ Run them now</button>
      <span class="note">about ${mins} min${RUN.offer.includes("drive") ? " plus the drive" : ""} · it tells you out loud when to touch the pedal or a hose,
      then sends the results straight back to the AI team</span></div>`;
  } else box.style.display = "none";
  fitHeight();
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-run]"); if (!b) return;
  const a = b.dataset.run;
  if (a === "go") runTests(RUN.offer.slice());
  else if (a === "skip") RUN.skip = true;
  else if (a === "stop") RUN.stop = true;
});
function runSay(text, talk = true) { RUN.step = text; RUN.left = null; renderRun(true); if (talk) { lastSpeak = 0; speak(text); } }
const runAbort = () => RUN.stop || RUN.skip;
async function runWait(cond, secs, countdown = true) {   // wait until cond() is true; false on time-out / skip / stop
  const t0 = nowS();
  while (!runAbort()) {
    if (cond()) { RUN.left = null; return true; }
    const left = secs - (nowS() - t0);
    if (left <= 0) break;
    RUN.left = countdown ? Math.ceil(left) : null; renderRun();
    await sleep(250);
  }
  RUN.left = null;
  return false;
}
async function runRecord(secs, keys, okFn) {   // sample these readings for `secs` seconds of time that okFn() allows
  const out = [], t0 = nowS(), lastT = {};
  let good = 0, last = nowS();
  while (!runAbort() && good < secs && nowS() - t0 < secs * 4 + 30) {
    await sleep(120);
    const t = nowS(), ok = !okFn || okFn();
    if (ok) good += t - last;
    last = t;
    RUN.left = Math.max(0, Math.ceil(secs - good)); renderRun();
    if (!ok) continue;
    if (keys.some((k) => numT[k] && numT[k] !== lastT[k])) {   // a new sample whenever any reading was refreshed
      keys.forEach((k) => (lastT[k] = numT[k]));
      out.push([t, ...keys.map((k) => (fresh(k, 3) ? num[k] : null))]);
    }
  }
  RUN.left = null;
  return out;
}
const runIdling = () => fresh("rpm", 3) && num.rpm > 400 && num.rpm < 1300 && (num.spd ?? 0) < 1;
const runRunning = () => fresh("rpm", 3) && num.rpm > 400;
const runEngineOff = () => !fresh("rpm", 5) || (num.rpm ?? 0) < 50;
async function runNeedWarmIdle() {
  if (!runRunning()) { runSay("Start the engine and let it idle."); if (!await runWait(runRunning, 120)) return false; }
  if ((num.ect ?? 200) < 170) {
    runSay(`Let it warm up first — coolant is ${Math.round(num.ect)}°F, the test needs about 170.`);
    if (!await runWait(() => (num.ect ?? 200) >= 170, 900)) return false;
  }
  if (!runIdling()) { runSay("Let it idle in Park or Neutral, foot off the gas."); if (!await runWait(runIdling, 45)) return false; }
  return true;
}
const colOf = (rows, keys, k) => rows.map((r) => r[keys.indexOf(k) + 1]).filter((x) => x != null && isFinite(x));
const r1 = (x, d = 1) => (x == null || !isFinite(x) ? null : +x.toFixed(d));
function runSkipped(name, why) { reportTest(name, { skipped: true, verdict: why }, true); }
async function runTests(ids) {
  if (!connected) { alert("Connect to the vehicle first."); return; }
  if (RUN.on) return;
  ids = ids.filter((x) => AUTO_TESTS[x]).sort((a, b) => AUTO_TESTS[a].phase - AUTO_TESTS[b].phase);
  Object.assign(RUN, { on: true, list: ids, i: 0, stop: false, skip: false, offer: [], step: "", left: null });
  if (!streaming) startStream();
  wake(true);
  logEvent("tests", "AI test runner", "Running: " + ids.join(", "));
  let drove = false;
  for (RUN.i = 0; RUN.i < ids.length && !RUN.stop; RUN.i++) {
    const id = ids[RUN.i];
    RUN.skip = false; RUN.left = null; renderRun(true);
    try { await AUTO_RUN[id](); }
    catch (e) { logEvent("scanner-crash", "AI test " + id, e.message, e.stack); runSkipped(AUTO_TESTS[id].name, "The test hit an error: " + e.message); }
    FOCUS = null;
    if (RUN.skip) runSkipped(AUTO_TESTS[id].name, "Skipped by the technician (or the conditions never happened)");
    if (!RUN.stop) RUN.ran.push(id);
    if (id === "drive") drove = true;
  }
  FOCUS = null;
  const stopped = RUN.stop;
  if (driveOn && stopped) $("driveBtn").click();
  RUN.on = false; RUN.step = ""; renderRun(true); renderTests();
  if (!driveOn) wake(false);
  lastSpeak = 0;
  if (stopped) { speak("Tests stopped."); return; }
  if (drove) return;   // ending the test drive already sent everything to the AI team
  speak("All done. Sending the results to the AI team.");
  aiPendingId = null; requestAi("followup");
}

const AUTO_RUN = {
  async mode06() {
    runSay("Reading Mode $06 test results…", false);
    await txn(loadMode6);
    reportTest("Mode $06 re-read", { results: (mode6Summary || "").slice(0, 2000) }, true);
  },
  async monitors() {
    runSay("Reading the readiness monitors…", false);
    await txn(loadReadiness);
    await txn(pollMonitors41);
    const s = { since_clear: readinessSummary };
    if (r41) { const rows = readinessRows(r41.B, r41.C, r41.D, true); s.this_drive_complete = rows.filter((r) => r.done).map((r) => r.n); s.this_drive_not_done = rows.filter((r) => !r.done).map((r) => r.n); }
    reportTest("Readiness re-read", s, true);
  },
  async fuelhold() {
    const name = "Fuel pressure hold (KOEO)", pid = ["23", "0A", "59"].find((p) => active.includes(p));
    if (!pid) return runSkipped(name, "This car doesn't report fuel pressure to a scan tool — put a gauge on the rail to check pressure and hold.");
    const tile = PIDS[pid].tile;
    runSay("Fuel pressure hold test. Shut the engine off and leave the key ON. Don't crank it.");
    if (!await runWait(runEngineOff, 120)) return;
    FOCUS = [pid, "0C"];
    runSay("Leave the key on and don't touch anything. Recording fuel pressure for 2 minutes.");
    const rows = await runRecord(120, [tile], null);
    FOCUS = null;
    if (runAbort()) return;
    const v = colOf(rows, [tile], tile);
    if (v.length < 6) return runSkipped(name, "Not enough fuel pressure readings came back.");
    const start = avg(v.slice(0, 4)), end = avg(v.slice(-4)), drop = start > 1 ? (start - end) / start * 100 : null;
    let g = "g", text;
    if (start < 5) { g = "r"; text = `Almost no fuel pressure with the key on (${start.toFixed(0)} psi) → the pump didn't prime or pressure bleeds off right away (pump check valve, leaking injector, regulator). Cycle the key and watch for the prime.`; }
    else if (drop > 35) { g = "r"; text = `Pressure fell ${drop.toFixed(0)}% in 2 minutes (${start.toFixed(0)} → ${end.toFixed(0)} psi) → it's leaking down: leaking injector(s) (raw fuel = rich codes, hard hot start), pump check valve, or regulator. Pinch the return/feed line to split it, or pull the rail and watch the injectors.`; }
    else if (drop > 15) { g = "y"; text = `Pressure fell ${drop.toFixed(0)}% in 2 minutes (${start.toFixed(0)} → ${end.toFixed(0)} psi) — a slow leak-down. Recheck with a gauge over 10–20 minutes before condemning anything.`; }
    else text = `Pressure held (${start.toFixed(0)} → ${end.toFixed(0)} psi over 2 minutes) → no leaking injectors or check valve.`;
    reportTest(name, { start_psi: r1(start, 0), end_psi: r1(end, 0), drop_pct: r1(drop, 0), grade: gradeTxt(g), verdict: text }, true);
    runSay("Done. You can start the engine.");
  },
  async crank() {
    if (!runEngineOff()) { runSay("Cranking test. Shut the engine off and leave the key ON."); if (!await runWait(runEngineOff, 120)) return; }
    await crankTest();
    if (!runRunning()) { runSay("Start the engine for the next test."); await runWait(runRunning, 60); }
  },
  async idle() {
    if (!await runNeedWarmIdle()) return;
    const keys = ["rpm", "stft1", "ltft1", "stft2", "ltft2", "maf", "map", "o2b1s1", "o2b2s1"], m0 = misAnalyze().all;
    runSay("Idle check. Foot off the gas for one minute.");
    const rows = await runRecord(60, keys, runIdling);
    if (runAbort()) return;
    const rpm = colOf(rows, keys, "rpm"), t1 = avg(colOf(rows, keys, "stft1")) + (avg(colOf(rows, keys, "ltft1")) ?? 0);
    const st2 = colOf(rows, keys, "stft2"), t2 = st2.length ? avg(st2) + (avg(colOf(rows, keys, "ltft2")) ?? 0) : null;
    const newMis = misAnalyze().all - m0, wob = rpm.length > 5 ? sd(rpm) : null, out = []; let g = "g";
    if (wob != null && wob > 60) { g = "r"; out.push(`Idle is rough — RPM swings ±${wob.toFixed(0)}.`); } else if (wob != null && wob > 30) { g = "y"; out.push(`Idle is a bit unsteady (±${wob.toFixed(0)} RPM).`); } else if (wob != null) out.push("Idle RPM is steady.");
    for (const [b, t] of [["Bank 1", t1], ["Bank 2", t2]]) if (t != null && isFinite(t)) { const a = Math.abs(t); if (a > 15) g = "r"; else if (a > 10 && g === "g") g = "y"; out.push(`${b} total trim ${fmtF(t)}% ${a <= 10 ? "(normal)" : t > 0 ? "(lean)" : "(rich)"}.`); }
    if (newMis > 0) { g = "r"; out.push(`${newMis} misfire(s) counted during the minute — ${misAnalyze().text.replace(/<[^>]+>/g, "")}`); } else if (misMids.length) out.push("No misfires counted.");
    reportTest("Warm idle check", { rpm_avg: r1(avg(rpm), 0), rpm_swing: r1(wob, 0), total_trim_b1: r1(t1), total_trim_b2: r1(t2), maf_gs: r1(avg(colOf(rows, keys, "maf"))),
      map_psi: r1(avg(colOf(rows, keys, "map"))), new_misfires: newMis, grade: gradeTxt(g), verdict: out.join(" ") }, true);
  },
  async purge() {
    const name = "EVAP purge check";
    if (!await runNeedWarmIdle()) return;
    const keys = ["stft1", "ltft1", "stft2", "ltft2", "evap", "o2b1s1", "o2b2s1"];
    FOCUS = ["0C", "0D", "06", "07", "08", "09", "2E"].filter((p) => active.includes(p));
    runSay("Purge check. Step 1: let it idle. Recording normal fuel trims for 40 seconds.");
    const base = await runRecord(40, keys, runIdling);
    if (runAbort()) return;
    runSay("Step 2: find the purge hose — from the purge valve to the intake. Get ready to pinch it shut.");
    await runWait(() => false, 8);
    if (runAbort()) return;
    runSay("Pinch it shut now and hold it.");
    const pinch = await runRecord(20, keys, runIdling);
    if (runAbort()) return;
    runSay("Let go of the hose.");
    const after = await runRecord(15, keys, runIdling);
    FOCUS = null;
    if (runAbort()) return;
    const tot = (rows) => { const b1 = avg(colOf(rows, keys, "stft1")), l1 = avg(colOf(rows, keys, "ltft1")) ?? 0, b2 = avg(colOf(rows, keys, "stft2")), l2 = avg(colOf(rows, keys, "ltft2")) ?? 0;
      const v = [b1 != null ? b1 + l1 : null, b2 != null ? b2 + l2 : null].filter((x) => x != null); return v.length ? avg(v) : null; };
    const B = tot(base), P = tot(pinch), A = tot(after), cmd = avg(colOf(base, keys, "evap")), cmdP = avg(colOf(pinch, keys, "evap"));
    if (B == null || P == null) return runSkipped(name, "Not enough fuel trim readings came back.");
    const d = P - B; let g = "g", text;
    const cmdTxt = cmd == null ? "commanded purge isn't reported on this car" : `purge commanded ${cmd.toFixed(0)}%`;
    if (Math.abs(d) < 3) text = `Pinching the purge hose barely changed the fuel trims (${fmtF(d)}%, ${cmdTxt}) → purge isn't adding fuel at idle right now, so it's not the cause there.`;
    else if (d > 0 && cmd != null && cmd < 3 && (cmdP ?? 0) < 3) { g = "r"; text = `Purge is commanded OFF, but pinching the hose moved the trims ${fmtF(d)}% → the purge valve is LEAKING (stuck open). That adds fuel vapor all the time: rich codes, rough idle, hard start right after filling up. Replace the purge valve.`; }
    else if (d > 0 && d >= 8) { g = "y"; text = `Purge vapor is adding a lot of fuel (trims went ${fmtF(d)}% leaner with the hose pinched, ${cmdTxt}) → a heavily loaded canister (topping off the tank, saturated canister) can set rich codes. Check the canister for liquid fuel and the vent valve.`; }
    else if (d > 0) text = `Purge adds a normal small amount of fuel (trims ${fmtF(d)}% with the hose pinched, ${cmdTxt}).`;
    else { g = "y"; text = `Pinching the hose made the trims go ${fmtF(d)}% (richer) — unusual: purge may be pulling air (leak at the canister/lines) instead of vapor. Smoke test the EVAP system.`; }
    if (A != null && Math.abs(A - B) > 4) text += ` After letting go the trims didn't settle back (${fmtF(A)}% vs ${fmtF(B)}%), so treat this result as a rough guide and repeat it.`;
    reportTest(name, { trim_base: r1(B), trim_pinched: r1(P), trim_after: r1(A), change_pct: r1(d), purge_cmd_pct: r1(cmd, 0), grade: gradeTxt(g), verdict: text }, true);
  },
  async o2() {
    const name = "O2 sensor response";
    const pids = {};
    ["o2b1s1", "o2b2s1", "o2b1s2", "o2b2s2"].forEach((t) => { const p = active.find((x) => PIDS[x] && PIDS[x].tile === t); if (p) pids[t] = p; });
    if (!pids.o2b1s1 && !pids.o2b2s1) return runSkipped(name, "This car doesn't report the front O2 sensors to a scan tool — scope them instead.");
    if (!await runNeedWarmIdle()) return;
    const keys = ["rpm", "tps", "app", "stft1", "stft2", "o2b1s1", "o2b2s1", "o2b1s2", "o2b2s2"];
    FOCUS = ["0C", "11", "49", "4A", "06", "08", ...Object.values(pids)].filter((p) => active.includes(p));
    runSay("O2 test. Step 1: let it idle, foot off the gas.");
    const idle = await runRecord(20, keys, runIdling);
    if (runAbort()) return;
    runSay("Step 2: bring it up to 2,500 RPM and hold it steady.");
    const at2500 = () => fresh("rpm", 2) && num.rpm >= 2100 && num.rpm <= 2900;
    let hold = [];
    if (await runWait(at2500, 30)) { runSay("Hold it right there.", false); hold = await runRecord(20, keys, at2500); }
    if (runAbort()) return;
    runSay("Step 3: let it drop to idle, then snap the throttle wide open and let go right away.");
    await runWait(runIdling, 15);
    const tpsIdle = avg(colOf(idle, keys, "tps")) ?? num.tps ?? 15;
    const snapped = () => (fresh("tps", 2) && num.tps >= tpsIdle + 30) || (fresh("rpm", 2) && num.rpm > 3600);
    let snap = [];
    if (await runWait(snapped, 20)) snap = await runRecord(6, keys, null);
    FOCUS = null;
    if (runAbort()) return;
    runSay("Done. Let it idle.", false);
    const res = o2Analyze(keys, idle, hold, snap, pids);
    reportTest(name, res, true);
  },
  async vacuum() {
    if (!active.includes("0B")) return runSkipped("Vacuum (MAP)", "This car doesn't report a MAP sensor — use a vacuum gauge or a pressure transducer.");
    if (!await runNeedWarmIdle()) return;
    const step = async (s, say, secs) => { runSay(say); Object.assign(T.vac, { step: s, buf: [], t0: nowS(), relT: null }); await runWait(() => !T.vac.step, secs); if (runAbort()) T.vac.step = null; };
    await step("idle", "Vacuum test. Step 1: idle for 10 seconds.", 20);
    if (runAbort()) return;
    await step("snap", "Step 2: snap the throttle wide open and let go.", 16);
    if (runAbort()) return;
    await step("hold", "Step 3: bring it up to 2,500 RPM and hold it for 30 seconds.", 45);
  },
  async charging() {
    if (!runRunning()) { runSay("Charging test. Start the engine."); if (!await runWait(runRunning, 90)) return; }
    runSay("Charging test. Let it idle with the lights, blower and defroster off.");
    await runWait(() => false, 10);
    if (runAbort() || chgVolts() == null) return;
    chgRecord("idle");
    runSay("Now turn on the headlights, the blower on high and the rear defroster.");
    await runWait(() => false, 15);
    if (runAbort() || chgVolts() == null) return;
    chgRecord("loaded");
    runSay("Done. You can turn them off.");
  },
  async drive() {
    runSay("Last one: a test drive. Drive normally, and when it's safe include steady cruising, one hard pull and one firm stop. Tap Stop Test Drive when you're back.");
    if (!driveOn) $("driveBtn").click();
    await runWait(() => !driveOn, 7200, false);
    if (runAbort() && driveOn) $("driveBtn").click();   // skipped: end the drive (that sends the review)
  },
};

function o2Stats(rows, keys, k, wide) {
  const pts = rows.map((r) => [r[0], r[keys.indexOf(k) + 1]]).filter((p) => p[1] != null);
  if (pts.length < 5) return null;
  const v = pts.map((p) => p[1]), secs = Math.max(1, pts[pts.length - 1][0] - pts[0][0]), mid = wide ? 1.0 : 0.45;
  let cross = 0;
  for (let i = 1; i < v.length; i++) if ((v[i - 1] - mid) * (v[i] - mid) < 0) cross++;
  return { min: r1(Math.min(...v), 3), max: r1(Math.max(...v), 3), avg: r1(avg(v), 3),
           rich_pct: Math.round(v.filter((x) => (wide ? x < 0.98 : x > 0.7)).length / v.length * 100),
           lean_pct: Math.round(v.filter((x) => (wide ? x > 1.02 : x < 0.2)).length / v.length * 100),
           switches_per_10s: r1(cross / 2 / secs * 10), samples_per_s: r1(v.length / secs) };
}
function o2Analyze(keys, idle, hold, snap, pids) {
  const out = { grade: "GOOD" }, notes = []; let g = "g";
  const worse = (x) => { if (x === "r" || (x === "y" && g === "g")) g = x; };
  for (const [bank, up, dn, stft] of [["Bank 1", "o2b1s1", "o2b1s2", "stft1"], ["Bank 2", "o2b2s1", "o2b2s2", "stft2"]]) {
    if (!pids[up]) continue;
    const wide = ["24", "34", "26", "36", "28", "38"].includes(pids[up]);
    const I = o2Stats(idle, keys, up, wide), H = o2Stats(hold, keys, up, wide), S = o2Stats(snap, keys, up, wide);
    const D = pids[dn] ? o2Stats(hold.length ? hold : idle, keys, dn, false) : null;
    const trimH = avg(colOf(hold.length ? hold : idle, keys, stft));
    out[bank + " front sensor"] = { type: wide ? "wideband (lambda)" : "narrowband (volts)", idle: I, at_2500: H, snap: S };
    if (D) out[bank + " rear sensor"] = D;
    const main = H || I; if (!main) continue;
    if (wide) {
      if (main.rich_pct >= 80) { worse("r"); notes.push(`${bank} front (wideband) reads RICH most of the time (avg λ ${main.avg}) ${trimH != null && trimH < -8 ? "and the PCM is pulling fuel (" + fmtF(trimH) + "%) → the mixture really is rich" : "but the PCM isn't pulling much fuel → sensor or its circuit may be skewed"}.`); }
      else if (main.lean_pct >= 80) { worse("r"); notes.push(`${bank} front (wideband) reads LEAN most of the time (avg λ ${main.avg}).`); }
      else notes.push(`${bank} front (wideband) holds near λ 1.00 (avg ${main.avg}) → normal.`);
      if (S) { if (S.min > 0.97) { worse("y"); notes.push(`${bank}: no rich dip on the snap (lowest λ ${S.min}) → slow sensor or the snap wasn't hard enough.`); }
               if (S.max < 1.15) { worse("y"); notes.push(`${bank}: didn't read lean on the let-off (highest λ ${S.max}) — normal if this engine doesn't cut fuel on a short decel.`); } }
    } else {
      const span = main.max - main.min;
      if (main.rich_pct >= 80 && main.min > 0.45) { worse("r"); notes.push(trimH != null && trimH < -8
          ? `${bank} front stays RICH (above 0.7 V ${main.rich_pct}% of the time, never below ${main.min} V) and the PCM is pulling fuel (${fmtF(trimH)}%) → the mixture really is rich: fuel pressure, leaking injector, purge, fuel in the oil, or a MAF reading high.`
          : `${bank} front stays RICH (above 0.7 V ${main.rich_pct}% of the time) but the PCM ISN'T pulling fuel (trim ${fmtF(trimH)}%) → the sensor or its signal circuit is reading rich falsely (contaminated sensor, signal shorted to voltage, bad ground). Check it with propane / a vacuum leak and back-probe the signal.`); }
      else if (main.lean_pct >= 80 && main.max < 0.45) { worse("r"); notes.push(`${bank} front stays LEAN (below 0.2 V ${main.lean_pct}% of the time, never above ${main.max} V).`); }
      else if (span < 0.3) { worse("r"); notes.push(`${bank} front barely moves (${main.min}–${main.max} V) → dead/lazy sensor, heater not working, or the engine is out of closed loop.`); }
      else if (H && H.switches_per_10s < 2) { worse("y"); notes.push(`${bank} front switches slowly at 2,500 RPM (${H.switches_per_10s} times per 10 s; a healthy sensor is usually 5 or more) → lazy sensor.`); }
      else notes.push(`${bank} front switches normally (${main.min}–${main.max} V${H ? ", " + H.switches_per_10s + " times per 10 s at 2,500" : ""}).`);
      if (S) {
        if (S.max < 0.8) { worse("y"); notes.push(`${bank}: didn't go rich on the snap (peak ${S.max} V, should pass 0.8 V) → slow/contaminated sensor or an exhaust leak ahead of it.`); }
        if (S.min > 0.2) { worse("y"); notes.push(`${bank}: didn't go lean when you let off (lowest ${S.min} V, should drop under 0.2 V) → slow sensor, or an injector leaking during decel fuel cut.`); }
        if (S.max >= 0.8 && S.min <= 0.2) notes.push(`${bank}: full rich and lean response on the snap (${S.max} V / ${S.min} V) → sensor responds.`);
      }
      if (D && main.switches_per_10s && D.switches_per_10s >= 0.6 * main.switches_per_10s && D.max - D.min > 0.5) {
        worse("y"); notes.push(`${bank} rear sensor copies the front one (${D.switches_per_10s} vs ${main.switches_per_10s} switches per 10 s) → the catalyst is storing little oxygen (low efficiency).`);
      } else if (D) notes.push(`${bank} rear sensor is steady (${D.min}–${D.max} V) → catalyst storing oxygen.`);
    }
  }
  if (!hold.length) notes.push("The 2,500 RPM hold wasn't recorded, so the switching speed is from idle only.");
  if (!snap.length) notes.push("No throttle snap was detected, so the rich/lean response wasn't tested.");
  out.grade = gradeTxt(g); out.verdict = notes.join(" ");
  return out;
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
    reportTest("Torque converter clutch", { grade: tc.g === "g" ? "GOOD" : tc.g === "r" ? "BAD" : "MARGINAL", verdict: tc.text, factory_slip_pid: tc.hasSlip,
      readings_used: tc.sources, typical_at_45mph_plus: tc.typical, events: tc.events.map((e) => e.at + " " + e.text) }, true); }
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
    <div class="note">"Send to app" puts the drive in 🔬 Scope & Tests → 🚗 Test drive review, where you can copy it to Claude or have the AI team review it.</div></details>`;
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-drv]"); if (!b) return;
  const list = lsGet(LS_DRIVES, []), d = list[+b.dataset.i]; if (!d) return;
  if (b.dataset.drv === "send") { sendDrive(d); log("Drive sent to the app — see 🔬 Scope & Tests → 🚗 Test drive review."); }
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


# ========================================================
# --- 👀 AI EYES: share a screen/window (computer) or a live camera (phone) so the AI sees what you see ---
# ========================================================
EYE_HTML = r'''<!doctype html><html><head><meta charset="utf-8">
<style>
  body { margin: 0; font-family: Inter, system-ui, -apple-system, sans-serif; color: #F1F5F9; background: transparent; }
  .bar { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 6px; }
  button { background: #131B2E; color: #F1F5F9; border: 1px solid rgba(255,255,255,.18); border-radius: 8px; padding: 8px 12px;
           font-weight: 600; cursor: pointer; font-size: .9rem; }
  button.on { border-color: #10B981; color: #10B981; }
  button.go { background: #10B981; color: #04110c; border-color: #10B981; }
  video { width: 100%; max-height: 260px; background: #000; border-radius: 8px; display: none; object-fit: contain; }
  .note { color: #8B9BB4; font-size: .82rem; }
  select { background: #131B2E; color: #F1F5F9; border: 1px solid rgba(255,255,255,.18); border-radius: 6px; padding: 3px; }
</style></head><body>
<div class="bar">
  <button id="scrBtn">🖥️ Share a screen or window</button>
  <button id="camBtn">📹 Live camera</button>
  <button id="askBtn" class="go" hidden>🤔 Ask the AI about this screen</button>
  <button id="stopBtn" hidden>⏹ Stop</button>
  <span class="note" id="autoWrap" hidden>Reads it every <select id="every">
    <option value="15">15 s</option><option value="30" selected>30 s</option><option value="60">60 s</option><option value="0">only when I ask</option>
  </select></span>
</div>
<video id="v" autoplay playsinline muted></video>
<canvas id="c" style="display:none"></canvas>
<div class="note" id="msg"></div>
<script>
function toStreamlit(type, data) { window.parent.postMessage(Object.assign({ isStreamlitMessage: true, type }, data || {}), "*"); }
const sendValue = (value) => toStreamlit("streamlit:setComponentValue", { value, dataType: "json" });
let lastH = 0;
function fit() { const h = document.documentElement.scrollHeight; if (h !== lastH) { lastH = h; toStreamlit("streamlit:setFrameHeight", { height: h }); } }
new ResizeObserver(fit).observe(document.body);
let lastReq = null;
window.addEventListener("message", (e) => {
  if (!e.data || e.data.type !== "streamlit:render") return;
  const r = (e.data.args || {}).req;
  if (r && r.id && r.id !== lastReq) { lastReq = r.id; setTimeout(() => grab(true, false, r.id), 150); }   // the app wants a fresh picture now
  fit();
});
toStreamlit("streamlit:componentReady", { apiVersion: 1 });

const $ = (id) => document.getElementById(id);
// Ask through the app's own page (it always has permission to share a screen or use the camera); fall back to this frame
function md() { try { if (window.parent.navigator.mediaDevices) return window.parent.navigator.mediaDevices; } catch (e) {} return navigator.mediaDevices; }
let stream = null, kind = "", timer = null, lastSig = null, n = 0;
const canScreen = !!(md() && md().getDisplayMedia);
function msg(t) { $("msg").textContent = t; fit(); }
if (!canScreen) { $("scrBtn").hidden = true; msg("Screen sharing only works on a computer (Chrome or Edge). On a phone or tablet, use the live camera and point it at the scan tool screen."); }
async function start(k) {
  stop(true);
  try {
    stream = k === "screen"
      ? await md().getDisplayMedia({ video: { frameRate: 5 }, audio: false })
      : await md().getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false });
  } catch (e) { msg(k === "screen" ? "Screen sharing was cancelled or blocked." : "Couldn't open the camera — allow camera access for this site and try again."); return; }
  kind = k;
  const v = $("v"); v.srcObject = stream; v.style.display = "block";
  try { await v.play(); } catch (e) {}
  stream.getVideoTracks()[0].addEventListener("ended", () => stop());
  ["askBtn", "stopBtn", "autoWrap"].forEach((id) => ($(id).hidden = false));
  $(k === "screen" ? "scrBtn" : "camBtn").classList.add("on");
  msg(k === "screen" ? "👀 The AI can see the window you shared. Ask about it in 💬 Chat, or tap Ask the AI about this screen."
                     : "👀 The AI can see what the camera sees — point it at the scan tool screen (or the engine).");
  sendValue({ type: "state", on: true, kind: k, id: "st-" + Date.now() });
  setTimeout(() => grab(true, false), 1500);
  schedule();
}
function stop(quiet) {
  if (timer) { clearInterval(timer); timer = null; }
  if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null; }
  const v = $("v"); v.style.display = "none"; v.srcObject = null;
  ["askBtn", "stopBtn", "autoWrap"].forEach((id) => ($(id).hidden = true));
  ["scrBtn", "camBtn"].forEach((id) => $(id).classList.remove("on"));
  if (!quiet) { msg(""); sendValue({ type: "state", on: false, id: "st-" + Date.now() }); }
  fit();
}
function schedule() {
  if (timer) clearInterval(timer);
  const secs = +$("every").value;
  timer = secs > 0 ? setInterval(() => grab(false, false), secs * 1000) : null;
}
$("every").addEventListener("change", schedule);
function fingerprint(c) {   // a tiny copy of the picture: skip sending when nothing on screen changed
  const t = document.createElement("canvas"); t.width = 32; t.height = 18;
  const x = t.getContext("2d"); x.drawImage(c, 0, 0, 32, 18);
  const d = x.getImageData(0, 0, 32, 18).data, out = [];
  for (let i = 0; i < d.length; i += 4) out.push((d[i] + d[i + 1] + d[i + 2]) / 3);
  return out;
}
function grab(force, ask, req) {
  const v = $("v"); if (!stream || !v.videoWidth) { if (req) sendValue({ type: "nopic", id: "np" + Date.now(), req }); return; }
  const w = Math.min(req ? 2400 : 1600, v.videoWidth), h = Math.round(v.videoHeight * w / v.videoWidth);   // sharper for a diagram
  const c = $("c"); c.width = w; c.height = h; c.getContext("2d").drawImage(v, 0, 0, w, h);
  const f = fingerprint(c);
  if (!force && lastSig) { let diff = 0; for (let i = 0; i < f.length; i++) diff += Math.abs(f[i] - lastSig[i]); if (diff / f.length < 0.25) return; }
  lastSig = f;
  const img = c.toDataURL("image/jpeg", req ? 0.92 : 0.85).split(",")[1];
  sendValue({ type: "frame", id: "f" + Date.now() + "-" + (++n), img, kind, w, h, ask: !!ask, req: req || null, at: new Date().toLocaleTimeString() });
}
$("scrBtn").onclick = () => start("screen");
$("camBtn").onclick = () => start("camera");
$("stopBtn").onclick = () => stop();
$("askBtn").onclick = () => grab(true, true);
// the picture comes through the app's page, so stop it ourselves if this panel is closed (no orphaned screen share / camera)
window.addEventListener("pagehide", () => stop(true));
window.addEventListener("unload", () => stop(true));
fit();
</script></body></html>
'''


def _eye_component_dir() -> str:
  d = Path(tempfile.gettempdir()) / "ai_eyes"
  d.mkdir(exist_ok=True)
  f = d / "index.html"
  if not f.exists() or f.read_text(encoding="utf-8") != EYE_HTML:
    f.write_text(EYE_HTML, encoding="utf-8")
  return str(d)


_eye = components.declare_component("ai_eyes", path=_eye_component_dir())

PASTE_HTML = r'''<!doctype html><html><head><meta charset="utf-8">
<style>
  body { margin: 0; font-family: Inter, system-ui, -apple-system, sans-serif; color: #F1F5F9; background: transparent; }
  #box { border: 2px dashed rgba(16,185,129,.55); border-radius: 10px; padding: 14px 10px; text-align: center; cursor: text;
         background: rgba(16,185,129,.05); outline: none; font-size: .92rem; }
  #box:focus { border-color: #10B981; background: rgba(16,185,129,.12); }
  .note { color: #8B9BB4; font-size: .78rem; }
  img { max-width: 100%; max-height: 90px; margin-top: 6px; border-radius: 6px; }
</style></head><body>
<div id="box" tabindex="0"><b>📋 Click here, then press Ctrl+V</b> to paste a screenshot<br>
<span class="note">Snip it first: Windows+Shift+S (Mac: Cmd+Ctrl+Shift+4) and drag around the diagram · or drag a picture file in</span>
<div id="got"></div></div>
<script>
function toStreamlit(type, data) { window.parent.postMessage(Object.assign({ isStreamlitMessage: true, type }, data || {}), "*"); }
const sendValue = (value) => toStreamlit("streamlit:setComponentValue", { value, dataType: "json" });
let lastH = 0;
function fit() { const h = document.documentElement.scrollHeight; if (h !== lastH) { lastH = h; toStreamlit("streamlit:setFrameHeight", { height: h }); } }
new ResizeObserver(fit).observe(document.body);
window.addEventListener("message", (e) => { if (e.data && e.data.type === "streamlit:render") fit(); });
toStreamlit("streamlit:componentReady", { apiVersion: 1 });
const box = document.getElementById("box"), got = document.getElementById("got");
function take(file) {
  if (!file || !/^image\//.test(file.type)) { got.textContent = "That isn't a picture — snip the diagram and paste again."; fit(); return; }
  const im = new Image();
  im.onload = () => {
    const s = Math.min(1, 2400 / Math.max(im.width, im.height)), c = document.createElement("canvas");
    c.width = Math.round(im.width * s); c.height = Math.round(im.height * s);
    const g = c.getContext("2d"); g.fillStyle = "#fff"; g.fillRect(0, 0, c.width, c.height); g.drawImage(im, 0, 0, c.width, c.height);
    const url = c.toDataURL("image/jpeg", 0.92);
    got.innerHTML = `<img src="${url}"><div class="note">✓ Got it — the AI is reading it…</div>`; fit();
    sendValue({ id: "p" + Date.now(), img: url.split(",")[1], w: c.width, h: c.height });
  };
  im.src = URL.createObjectURL(file);
}
document.addEventListener("paste", (e) => {
  const items = [...((e.clipboardData && e.clipboardData.items) || [])];
  const it = items.find((x) => x.type && x.type.startsWith("image/"));
  if (it) { e.preventDefault(); take(it.getAsFile()); }
  else { got.textContent = "No picture on the clipboard — snip the diagram first (Windows+Shift+S), then Ctrl+V here."; fit(); }
});
box.addEventListener("dragover", (e) => { e.preventDefault(); box.focus(); });
box.addEventListener("drop", (e) => { e.preventDefault(); take(e.dataTransfer.files && e.dataTransfer.files[0]); });
box.addEventListener("click", () => box.focus());
fit();
</script></body></html>
'''


def _paste_component_dir() -> str:
  d = Path(tempfile.gettempdir()) / "paste_box"
  d.mkdir(exist_ok=True)
  f = d / "index.html"
  if not f.exists() or f.read_text(encoding="utf-8") != PASTE_HTML:
    f.write_text(PASTE_HTML, encoding="utf-8")
  return str(d)


_paste_box = components.declare_component("paste_box", path=_paste_component_dir())


EYE_READ_PROMPT = """This is a live view of what an automotive technician is looking at right now — usually a scan tool screen
(Autel, Snap-on, factory tool) showing live data, codes, freeze frame, Mode $06 or a scope; or a camera view of the
engine bay or a meter.
Read it and return JSON only:
{"what": "<one line: what's on the screen>", "vehicle": "<vehicle if shown, else ''>",
 "readings": [{"name": "<PID / reading name exactly as shown>", "value": "<value exactly as shown>", "unit": "<unit>"}],
 "codes": ["<any trouble codes shown>"], "notes": "<anything that stands out (out of range, flagged red), or ''>"}
Read every value exactly as shown, with units. Leave out anything cut off or too blurry to read — never guess a number."""


def eye_fresh(max_age: int = 120) -> dict | None:
  """The latest picture from the shared screen / camera, if sharing is on and it's recent."""
  e = ss.get("eye")
  return e if (ss.get("eye_on") and e and time.time() - e.get("at", 0) < max_age) else None


def _eye_read(img_b64: str) -> dict:
  try:
    if secret("GEMINI_API_KEY"):   # quick and cheap for reading a screen every half minute
      raw = gemini([{"text": EYE_READ_PROMPT}, {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}],
                   json_mode=True, timeout=45, think="low")
    else:
      raw, _who = quick_ai(EYE_READ_PROMPT, image_b64=img_b64, max_tokens=3000, effort="low")
  except AIError as e:
    return {"error": str(e)}
  obj = find_json(raw, dict) or {}
  obj["readings"] = [r for r in (obj.get("readings") or []) if isinstance(r, dict) and str(r.get("value", "")).strip()][:120]
  return obj


def eye_context() -> str:
  """What the AI read off the technician's shared scan tool screen, for the AI prompts."""
  reads = [r for r in (ss.get("eye_reads") or []) if not r.get("error")]
  if not reads or not ss.get("eye_on"):
    return ""
  last = reads[-1]
  rows = [f"- {r.get('name')}: {r.get('value')} {r.get('unit') or ''}".rstrip() for r in last.get("readings") or []]
  earlier = []
  for r in reads[-4:-1]:
    vals = "; ".join(f"{x.get('name')}={x.get('value')}{x.get('unit') or ''}" for x in (r.get("readings") or [])[:25])
    if vals:
      earlier.append(f"- {r.get('at_txt', '')}: {vals}")
  return ("\n\nTHE TECHNICIAN'S OWN SCAN TOOL SCREEN — read from their live screen share / camera at "
          f"{last.get('at_txt', '')} ({last.get('what') or 'scan tool screen'}). These come from their professional scan tool "
          "(Autel / Snap-on), so trust them over the Bluetooth adapter's 'enhanced' readings:\n"
          + ("\n".join(rows[:100]) or "- (no readings visible)")
          + (f"\nCodes on that screen: {', '.join(last.get('codes') or [])}" if last.get("codes") else "")
          + (f"\nWhat stood out: {last.get('notes')}" if last.get("notes") else "")
          + ("\nEARLIER READS OF THE SAME SCREEN (for trends):\n" + "\n".join(earlier) if earlier else ""))


def _eye_events():
  ev = _eye(key="ai_eyes", req=ss.get("eye_req"), default=None)
  w = ss.get("_dg_wait")
  if w and time.time() - w["t"] > 15:   # the picture never came (sharing stopped?)
    ss._dg_wait = None
    st.warning("Didn't get a picture from the shared screen — is it still sharing? Try again, or paste a screenshot.")
  if not (isinstance(ev, dict) and ev.get("id") and ev["id"] != ss.get("_eye_last")):
    return
  ss._eye_last = ev["id"]
  if w and ev.get("req") == w.get("req"):   # the fresh picture asked for by 📺 Use my shared screen: it's a wiring diagram
    ss._dg_wait = None
    if ev.get("type") == "frame" and ev.get("img"):
      process_diagram(base64.b64decode(ev["img"]), w["circuit"], w["steps"])
    else:
      st.warning("The shared screen isn't showing anything yet — open the diagram there and try again.")
    return
  if ev.get("type") == "state":
    ss.eye_on, ss.eye_kind = bool(ev.get("on")), ev.get("kind", "")
    if not ss.eye_on:
      ss.eye = None
    return
  if ev.get("type") != "frame" or not ev.get("img"):
    return
  ss.eye_on = True
  ss.eye = {"img": ev["img"], "at": time.time(), "at_txt": ev.get("at", ""), "kind": ev.get("kind", ""), "id": ev["id"]}
  job_id = "eye-" + ev["id"]
  if start_ai_job(job_id, lambda b=ev["img"]: _eye_read(b)):
    ss._eye_job = {"job": job_id, "at_txt": ev.get("at", "")}
  else:   # older Streamlit: read it right here
    res = _eye_read(ev["img"])
    ss.eye_reads = (ss.get("eye_reads") or [])[-29:] + [dict(res, at_txt=ev.get("at", ""))]
  if ev.get("ask"):
    ss._eye_ask = True
    st.rerun()   # the whole page: Quick help asks the AI about this screen


def _eye_collect():
  p = ss.get("_eye_job")
  j = _ai_jobs().get(p["job"]) if p else None
  if p and j is None:
    ss._eye_job = None
  elif j and j["state"] != "running":
    _ai_jobs().pop(p["job"], None)
    ss._eye_job = None
    res = j.get("result") if j["state"] == "done" else {"error": j.get("error")}
    ss.eye_reads = (ss.get("eye_reads") or [])[-29:] + [dict(res or {}, at_txt=p.get("at_txt", ""))]


def _eye_show():
  reads = ss.get("eye_reads") or []
  if ss.get("_eye_job"):
    st.caption("👀 Reading your screen…")
  if not reads or not ss.get("eye_on"):
    return
  last = reads[-1]
  if last.get("error"):
    st.caption(f"⚠️ Couldn't read the screen: {last['error']}")
    return
  rows = last.get("readings") or []
  st.caption(f"👀 What the AI reads on your screen ({last.get('at_txt', '')}): {last.get('what') or ''} — {len(rows)} reading(s)"
             + (f" · codes {', '.join(last.get('codes') or [])}" if last.get("codes") else ""))
  if rows:
    st.dataframe([{"Reading": r.get("name"), "Value": f"{r.get('value')} {r.get('unit') or ''}".strip()} for r in rows],
                 use_container_width=True, hide_index=True, height=min(36 * (len(rows) + 1), 220))


if hasattr(st, "fragment"):
  @st.fragment(run_every=3)
  def eye_panel():
    """Runs on its own (every few seconds and on each new picture) so sharing never reloads the whole page."""
    _eye_events()
    _eye_collect()
    _eye_show()
else:
  def eye_panel():
    _eye_events()
    _eye_collect()
    _eye_show()


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


def start_ai_job(job_id: str, fn) -> bool:
  """Run fn() on a background thread. False = this Streamlit can't do it (the caller then runs it the old way)."""
  if not job_id or not hasattr(st, "fragment"):
    return False
  try:
    from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
    ctx = get_script_run_ctx()
  except Exception:
    return False
  if ctx is None:
    return False
  jobs = _ai_jobs()
  for k in [k for k, v in jobs.items() if time.time() - v.get("started", 0) > 3600]:
    jobs.pop(k, None)   # tidy up anything nobody collected
  if job_id in jobs:
    return True
  jobs[job_id] = {"state": "running", "started": time.time()}
  def work():
    try:
      jobs[job_id].update(state="done", result=fn(), finished=time.time())
    except Exception as e:
      jobs[job_id].update(state="error", error=f"{type(e).__name__}: {e}", finished=time.time())
  th = threading.Thread(target=work, daemon=True, name=f"ai-{job_id}")
  add_script_run_ctx(th, ctx)   # lets the job read the job's data and write to the problem log
  th.start()
  return True


if hasattr(st, "fragment"):
  @st.fragment(run_every=2)
  def _ai_watch():
    p = ss.get("_ai_pending")
    if not p:
      return
    j = _ai_jobs().get(p["job"])
    if j is None:   # the server restarted mid-job
      ss._ai_pending = None
      ss.ble_ai = {"id": p["comp_id"] + "-lost", "text": "⚠️ The app restarted during the AI check. Tap AI Check again.",
                   "label": p["label"]}
      st.rerun()
    if j["state"] == "running":
      st.info(f"🤖 {p['what']} — the AI team is working… {int(time.time() - j['started'])} s "
              "(you can keep using the app; the answer appears in the scanner panel)")
      return
    _ai_jobs().pop(p["job"], None)
    ss._ai_pending = None
    if j["state"] == "done":
      text, research, draft, ds_draft, *rest = j["result"]
      if len(rest) > 1:
        add_diagram_requests(rest[1], "AI Check")
      ss.ble_ai = {"id": p["comp_id"], "text": text, "label": " · ".join(x for x in (
          p["label"], rest[2] if len(rest) > 2 else team_names(draft, ds_draft, research),
          f"{int(j['finished'] - j['started'])} s") if x),
                   "tests": (rest[0] if rest else []) or []}
    else:
      log_problem("ai", p["what"], j.get("error", "failed"))
      ss.ble_ai = {"id": p["comp_id"], "text": f"⚠️ The AI check failed: {j.get('error')}", "label": p["label"]}
    st.rerun()   # full refresh so the scanner panel receives the answer


# Tests the app can run by itself from the scanner. The tech only follows spoken prompts (rev it, snap it, pinch a hose).
AUTO_TESTS = {
    "mode06": "Re-read the Mode $06 test results now",
    "monitors": "Re-read the readiness monitors (since clear and this drive)",
    "fuelhold": "Fuel pressure hold for 2 min, key on engine off (only if the car reports fuel rail pressure)",
    "crank": "Cranking / starting test: battery voltage dip, cranking speed, time to start",
    "idle": "1-minute warm idle check: RPM steadiness, total fuel trims per bank, MAF, MAP, misfire counts",
    "purge": "EVAP purge check: fuel trims at idle, then with the purge hose pinched shut, then released — proves a leaking/stuck-open purge valve",
    "o2": "O2 sensor response: front and rear O2s plus short-term trims at idle, a 2,500 RPM hold, a throttle snap and the let-off — "
          "switching speed, stuck rich/lean, rich/lean response, rear copying the front (catalyst)",
    "vacuum": "Vacuum test from the MAP sensor: idle, snap, 2,500 RPM hold (exhaust restriction, valve/ring sealing)",
    "charging": "Charging: voltage at idle, then with headlights, blower and rear defroster on",
    "drive": "Test drive with the automatic tests: catalyst, fuel trims at idle/cruise/load, VE, transmission and converter, misfires",
}
RUN_TESTS_RULES = """

APP TESTS — the app can run these by itself (the technician just follows spoken prompts):
{catalog}
If any of them would help prove or rule out a cause, END your answer with one line exactly like this:
RUN_TESTS: o2, purge, mode06
Use only ids from the list, most useful first, at most 5. Don't list tests already run ({ran}).
Tests that need a meter, scope, gauge, propane or smoke machine go in your normal next-steps list for the technician.
If no app test would help, write: RUN_TESTS: none"""


def run_tests_rules(ran: list) -> str:
  catalog = "\n".join(f"- {k}: {v}" for k, v in AUTO_TESTS.items() if k not in ran)
  return RUN_TESTS_RULES.format(catalog=catalog, ran=", ".join(ran) or "none yet")


def split_run_tests(text: str) -> tuple[str, list | None]:
  """Pull the RUN_TESTS line off the end of an answer. None = the AI didn't write one."""
  found = None
  def grab(m):
    nonlocal found
    found = [t for t in re.findall(r"[a-z0-9]+", m.group(1).lower()) if t in AUTO_TESTS]
    return ""
  clean = re.sub(r"(?im)^[\s*_`>-]*RUN[_ ]TESTS?\s*[:=]\s*(.*)$", grab, text or "").rstrip()
  return clean, (list(dict.fromkeys(found))[:5] if found is not None else None)


def pick_tests(answer: str, ran: list) -> list:
  """The AI didn't say which app tests to run (the final reviewer dropped the line): ask quickly."""
  ask = ("Here is a diagnostic evaluation. Which of these tests that a scan tool app can run by itself would help prove or "
         "rule out the causes it discusses? Reply with JSON only: a list of ids, most useful first, at most 5, [] if none.\n"
         + "\n".join(f"- {k}: {v}" for k, v in AUTO_TESTS.items() if k not in ran) + "\n\nEVALUATION:\n" + answer[:6000])
  try:
    raw, _who = quick_ai(ask, max_tokens=1500, effort="low")
    got = find_json(raw, list) or []
    return [t for t in dict.fromkeys(str(x).strip().lower() for x in got) if t in AUTO_TESTS and t not in ran][:5]
  except Exception:
    return []


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
    upd["sel_codes"] = codes  # scanned codes go straight into 🔧 Diagnostics
    append_to_log(vin=vin or ss.active_vin, vehicle=ss.vehicle_info, dtc=", ".join(codes) or "No codes",
                  customer=ss.customer_name, phone=ss.customer_phone)
    queue_update(toast=f"Scanner synced: {vin or 'no VIN'} · {len(codes)} code(s) sent to 🔧 Diagnostics", **upd)

  elif ev.get("type") == "oem_learned":
    save_learned(ev)
    st.rerun()

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
      ss._toast = "Test drive saved — the AI team is reviewing it (🔬 Scope & Tests → 🚗 Test drive review)"

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
3. Any anomaly to inspect back in the bay.
{knowledge_block("test drive road load fuel trim misfire stumble transmission shift converter slip knock " + (ss.symptoms or ""), 12)}"""
      label = f"[Live Drive AI Check - {ev.get('at')}]"
    elif ev.get("mode") == "followup":
      ran = [t for t in (ev.get("ran") or []) if t in AUTO_TESTS]
      prior = (ss.get("ble_ai") or {}).get("text", "")
      prompt = f"""You are an expert ASE Master / L1 Diagnostic Technician. Earlier you evaluated this vehicle and asked the app
to run some tests by itself. It just ran them ({", ".join(ran) or "see results"}). The results are below — each has the
measurements and the app's own verdict.

Vehicle: {vehicle}
Codes read from the vehicle: {dtcs}
Technician-entered DTC: {ss.active_dtc or 'None'}

YOUR EARLIER EVALUATION (for reference):
{prior[:5000] or 'not available'}

TEST RESULTS (from the app's automatic tests and any guided tests):
{json.dumps(ev.get('tests') or ss.test_results or {}, indent=1)}

LIVE DATA NOW (Mode 01 + OEM enhanced PIDs; enhanced values are unverified beta):
{pids}

I/M READINESS: {ev.get('readiness') or 'Not read'}
MODE $06 RESULTS: {ev.get('mode6') or 'Not read'}
PLAUSIBILITY ALERTS: {"; ".join(ev.get('flags') or []) or 'none'}
{shop_context("o2 sensor purge fuel pressure fuel trim misfire vacuum charging")}{eye_context()}{diagram_context()}

TASK:
1. For each test: what it proved or ruled out, in one or two lines. Say so if a result looks wrong (test not done
   properly, skipped, bad data) instead of trusting it.
2. The updated most likely cause(s), ranked, and how sure you are now.
3. The next step: the single most definitive test or repair for the technician, with the tool and the pass/fail number.

Use clean bold section headers and direct shop-floor language.""" + run_tests_rules(ran) + DIAGRAM_RULE
      label = f"[AI follow-up on the tests - {ev.get('at')}]"
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
{shop_context("live data fuel trim misfire mode 06 readiness sensor o2 maf map charging")}{eye_context()}{diagram_context()}

DIAGNOSTIC TASK:
1. Fuel control: total trim (STFT + LTFT) Bank 1 vs Bank 2; single- vs dual-bank pattern.
2. Powertrain/drivetrain health from whatever enhanced data is present.
3. Air metering & O2/AFR sensors: sensor activity vs catalyst storage on each bank.
4. Mode $06: cylinder misfire counts and any failing or marginal monitor tests.
5. Readiness: which monitors are incomplete and the drive-cycle conditions to set them.
6. The single most definitive next physical/electrical test to confirm the root cause.

Use clean bold section headers and direct shop-floor language. Skip sections with no data.""" + \
          run_tests_rules([t for t in (ev.get("ran") or []) if t in AUTO_TESTS]) + DIAGRAM_RULE
      label = f"[Full AI Check - {ev.get('at')}]"
    drive_mode = ev.get("mode") == "drive"
    symptoms = (ss.symptoms or "").strip()
    ran_before = [t for t in (ev.get("ran") or []) if t in AUTO_TESTS]
    link_now = app_link(ss.get("job_id"))
    eye = None if drive_mode else eye_fresh()
    if eye:
      prompt += ("\n\nThe attached image is the technician's scan tool screen right now (live screen share / camera). "
                 "Use the factory data on it.")
    eye_img = [eye["img"]] if eye else ""
    # Live checks read the live data — no web research here (that's what the Diagnostic Tree is for), so they answer fast.
    def job():
      text, research, draft, ds_draft, more = team_answer(prompt, vehicle, dtcs, symptoms, use_web=False, status=None, fast=drive_mode,
                                                    effort="low" if drive_mode else None, image_b64=eye_img)
      tests, diag = [], []
      if not drive_mode:
        notify("🧪 Test follow-up ready" if ev.get("mode") == "followup" else "🤖 AI Check done", f"{vehicle} — {first_line(text)}",
               "robot", 3, link_now)
      if not drive_mode and not str(text).startswith("⚠️"):
        text, tests = split_run_tests(text)
        text, diag = split_need_diagram(text)
        if tests is None:   # the reviewer dropped the line: ask which tests quickly
          tests = pick_tests(text, ran_before)
        tests = [t for t in tests if t not in ran_before]
      return text, research, draft, ds_draft, tests, diag, team_names(draft, ds_draft, research, more)
    if start_ai_job(ev.get("id"), job):
      ss._ai_pending = {"job": ev.get("id"), "comp_id": ev.get("id"), "label": label,
                        "what": "Live drive check" if drive_mode else ("Follow-up on the tests" if ev.get("mode") == "followup" else "AI check")}
      return
    with st.spinner("🤖 AI team is checking the live data..."):   # older Streamlit: the old way
      text, research, draft, ds_draft, tests, diag, who_ = job()
    add_diagram_requests(diag, "AI Check")
    ss.ble_ai = {"id": ev.get("id"), "text": text, "label": label + " · " + who_, "tests": tests}
    st.rerun()


with _scan_box, guard("Vehicle Scan — scanner"):
  st.write("---")
  st.markdown("#### 📡 Scanner & live data")
  with st.container():   # (a fixed spot, so Simple view's cards don't move the scanner)
    if ss.get("simple_view"):
      status_cards()
  st.caption("Works in Chrome (Android, Windows, macOS, ChromeOS). Connecting reads the VIN and codes and fills them"
             " into the other tabs automatically. The Bluetooth link stays up while you use the rest of the app.")
  _vd = ss.vehicle_details or {}
  oem_repo, oem_sigs = obdb_signals(_vd.get("Make", ""), _vd.get("Model", ""), str(_vd.get("Model Year", "")))
  _learned = learned_readings(_vd)   # what 🔎 Find every reading found on this car (or one just like it) before
  _disp = re.search(r"\d+(\.\d+)?", str(_vd.get("Displacement (L)") or _vd.get("Engine") or ""))
  event = _ble_dashboard(vehicle=ss.vehicle_info, make=make_profile(), year=_vd.get("Model Year", ""),
                         disp=_disp.group(0) if _disp else "",
                         cyl=str(_vd.get("Engine Number of Cylinders") or
                                 (re.search(r"[VIL](\d{1,2})\b|(\d{1,2})\s*cyl", str(_vd.get("Engine", "")), re.I) or [None, ""])[1] or ""),
                         oem=oem_sigs, oem_src=oem_repo, ai=ss.ble_ai,
                         vmake=_vd.get("Make", ""), vmodel=_vd.get("Model", ""),
                         learned=_learned.get("sigs") or [], learned_id=_learned.get("lid", ""),
                         learned_ver=int(_learned.get("ver") or 0), key="ble", default=None)
  if isinstance(event, dict) and event.get("id") and event["id"] != ss.ble_last_event:
    ss.ble_last_event = event["id"]
    handle_ble_event(event)
  if ss.get("_ai_pending") and hasattr(st, "fragment"):
    _ai_watch()

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
for setting these monitors if you are sure of them. Keep it under 300 words.
{knowledge_block("drive cycle readiness monitor " + " ".join(_left), 8)}""", max_tokens=3000)
      ss.drive_plan = ("" if _plan.startswith("⚠️") else f"_{_who}_\n\n") + _plan
    if ss.drive_plan:
      with st.expander("📋 Drive cycle plan", expanded=True):
        st.markdown(ss.drive_plan)

# ========================================================
# --- TAB 3: DIAGNOSE (STRATEGY + SCOPE LAB + COPILOT) ---
# ========================================================
def scan_context(extra: str = "") -> str:
  """Everything the scanner captured + the shop's history and Knowledge notes, for the AI prompts."""
  tests = ("\nGuided test results: " + json.dumps(ss.test_results)) if ss.test_results else ""
  if not ss.ble_dtcs and not ss.scan_data:
    return "No scanner data (codes entered by hand)." + tests + shop_context(extra) + diagram_context()
  sd = ss.scan_data or {}
  pids = json.dumps(sd.get("pids") or {}, indent=0) if sd.get("pids") else "not captured"
  return (f"Scanner codes: {_fmt_dtcs(ss.ble_dtcs)}\n"
          f"I/M readiness: {sd.get('readiness') or 'not read'}\n"
          + ("".join("PLAUSIBILITY ALERT (reading that doesn't add up): " + f + "\n" for f in (sd.get("flags") or [])))
          + f"Mode $06 results: {sd.get('mode6') or 'not read'}\n"
          + f"Live data snapshot at sync ({sd.get('at') or '?'}): {pids}" + tests + shop_context(extra) + diagram_context())


# ========================================================
# --- CHAT (💬 the front screen: one conversation per car, every question and answer saved permanently) ---
# ========================================================
def chat_memory(question: str) -> str:
  """Earlier saved chats worth remembering for this question: this same car first, then ones on the same subject."""
  try:
    rows = [r.get("data") or {} for r in store_list("chat", 300)]
  except Exception:
    return ""
  in_convo = {m.get("chat_id") for m in (ss.chat_history or []) if m.get("chat_id")}
  rows = [d for d in rows if d.get("q") and d.get("a") and d.get("state", "done") == "done"
          and not str(d.get("a")).startswith("⚠️") and d.get("id") not in in_convo]
  same = [d for d in rows if ss.active_vin and d.get("vin") == ss.active_vin][:4]
  words = {w for w in re.findall(r"[a-z0-9]+", question.lower()) if len(w) >= 3} - KN_STOP
  sem = meaning_scores(f"{ss.vehicle_info or ''} {question}", "chat",
                       [(d["id"], f"{d.get('vehicle', '')}: {d.get('q', '')} — {str(d.get('a', ''))[:400]}") for d in rows if d.get("id")])
  top = max(sem.values()) if sem else 0
  scored = []
  for d in rows:
    if d in same:
      continue
    hit = len(words & set(re.findall(r"[a-z0-9]+", f"{d.get('q', '')} {d.get('vehicle', '')}".lower())))
    near = sem.get(d.get("id"), 0)
    if hit >= 2 or (sem and near >= top - 0.05 and near >= 0.6):
      scored.append((hit + near * 10, d))
  scored.sort(key=lambda x: -x[0])
  pick = same + [d for _, d in scored[:3]]
  if not pick:
    return ""
  return ("EARLIER CHATS (this technician's past questions and the AI's past answers — for continuity only, NOT proven "
          "facts; re-check anything you rely on, and say so if one was wrong):\n"
          + "\n".join(f"- {d.get('at', '')} · {d.get('vehicle') or 'no car open'}: Q: {d.get('q', '')[:300]} → A: "
                      + " ".join(str(d.get("a", "")).split())[:450] for d in pick))


def vehicle_facts() -> str:
  """The car that's open, as the AI should know it: VIN plus the decoded details."""
  vd = ss.vehicle_details or {}
  keys = [("Model Year", ""), ("Make", ""), ("Model", ""), ("Trim", ""), ("Displacement (L)", "L"), ("Engine Number of Cylinders", " cyl"),
          ("Engine Model", ""), ("Fuel Type - Primary", ""), ("Drive Type", ""), ("Transmission Style", ""), ("Transmission Speeds", "-speed")]
  parts = [f"{vd.get(k)}{u}" for k, u in keys if str(vd.get(k) or "").strip() and str(vd.get(k)) not in ("Not Applicable", "0")]
  vin = ss.get("active_vin") or ""
  return " · ".join(([f"VIN {vin}"] if vin else []) + parts + ([f"odometer {ss.odometer}"] if str(ss.get("odometer") or "").strip() else []))


def chat_prompt_for(question: str, n_photos: int, n_videos: int = 0, n_docs: int = 0) -> str:
  history = "\n".join(f"{m['role'].upper()}: {m['content']}" + (f" [attached {len(m['photos'])} photo(s)]" if m.get("photos") else "")
                      for m in (ss.chat_history or [])[-6:])
  plan = (ss.dtc_result or {}).get("text", "")[:3000]
  sr = ss.scope_result
  return f"""
You are an expert automotive diagnostic technician assisting a mechanic in the field.
Vehicle: {(ss.vehicle_info + (" — " + vehicle_facts() if vehicle_facts() else "")) if ss.vehicle_info else 'none open — answer in general, and ask for the vehicle if the answer depends on it'}
{"The technician already identified this vehicle in the app (VIN decoded) — use it, don't ask for it again. If a photo shows a different VIN or vehicle, point that out." if ss.vehicle_info else ""}
Fault codes being worked: {", ".join(current_codes()) or 'None'}
Symptoms / complaint: {(ss.symptoms or '').strip() or 'not given'}
{scan_context(question)}
Current test plan (if any): {plan or 'none yet'}
{plan_progress_text()}
Latest scope/readings evaluation (if any): {((sr or {}).get('text', '') if isinstance(sr, dict) else (sr or ''))[:1500] or 'none'}
Latest scope DATA FILE analysis (measured from raw data, if any): {((ss.wave_result or {}).get('text', ''))[:2000] or 'none'}

{chat_memory(question)}

Recent conversation:
{history}

Earlier web research for this job (if any): {(ss.dtc_result or {}).get("research", "")[:2500] or 'none'}
{eye_context()}

Respond directly, practically, and concisely to the latest question. Focus on physical shop tests, circuit checks, and logical isolation.
""" + DIAGRAM_RULE + (f"""
The technician attached {n_photos} photo(s) with this question (wiring diagram, connector, part, scope or meter).
Read them carefully: wire colors, pin/cavity numbers, splices, grounds, connector IDs, component names, readings on screen.
Say what you can read in the photo, and say so plainly if part of it is too blurry or cut off to read.""" if n_photos else "") + ("""
The technician attached a VIDEO (with sound). If you can watch it, watch and listen to the whole thing. If you can't, work
from the VIDEO REPORT below, written by the team member who watched it. Base anything about sounds or movement on the video,
and say plainly what can't be judged from a phone video (e.g. a noise that needs a stethoscope or a pressure test).""" if n_videos else "") + ("""
The technician attached a PDF (service information, a wiring diagram, a TSB, a manual or a scan report). If you can read it,
read the parts that matter to the question. If you can't, work from the PDF REPORT below, written by the team member who read
it. Use its exact specs, pin numbers, wire colors and steps, say which page they're on, and never fill a gap with a guess.""" if n_docs else "")


VIDEO_WATCH_PROMPT = """You are a master automotive technician. The technician recorded this video (with sound) and asks:
{question}
Vehicle: {vehicle} · Codes: {codes} · Symptoms: {symptoms}

Watch and listen to the WHOLE video and write a VIDEO REPORT for the rest of the diagnostic team, who cannot see or hear it:
- What is shown: the part / area of the engine bay / gauge, scan tool, meter or scope screen / dash lights / smoke, leaks,
  movement or shaking — with time stamps (m:ss).
- Every sound: describe it (tick, tap, knock, rattle, whine, hiss, squeal, chirp, grind, misfire "chuff", exhaust puff),
  when it happens, and whether it follows engine speed, half engine speed (valvetrain), road/wheel speed, or none;
  whether it changes with throttle, load, A/C, steering or temperature, and whether it's steady or comes and goes.
- Every number you can read on a screen or gauge, with its time stamp.
- What can't be judged from this video (camera too far, wind noise, too short, too dark) — say so plainly.
Facts only: describe what you see and hear. Don't diagnose beyond pointing out what stands out."""

DOC_READ_PROMPT = """You are a master automotive technician. The technician attached this PDF and asks:
{question}
Vehicle: {vehicle} · Codes: {codes} · Symptoms: {symptoms}

Read the PDF and write a PDF REPORT for the rest of the diagnostic team, who cannot open it:
- What the document is (service procedure, wiring diagram, TSB, owner's or training manual, scan or inspection report) and
  which vehicle(s) it covers.
- Everything in it that bears on the question: specs and known-good values (with their conditions), test steps, connector
  pin numbers and wire colors, component locations, part numbers, DTC setting criteria, readings — copied exactly, each with
  its page number.
- Anything the question needs that the PDF does NOT cover — say so plainly.
Facts only, exactly as written in the document. Don't diagnose beyond pointing out what stands out."""


class _JobStatus:
  """Lets the AI team report its progress ("Claude is checking...") to the screen from a background job."""
  def __init__(self, job_id: str):
    self.job_id = job_id

  def update(self, label: str | None = None, **_kw):
    if label and self.job_id in _ai_jobs():
      _ai_jobs()[self.job_id]["label"] = label


def run_chat_ai(job_id: str, prompt: str, question: str, photos_b64: list, vrefs: list, team: bool,
                vehicle: str, codes: str, symptoms: str) -> tuple[str, str, str]:
  """The AI part of one chat answer (runs in the background). Returns (answer, who answered, web research)."""
  status = _JobStatus(job_id)
  docs = [v for v in vrefs or [] if v.get("mime") in DOC_TYPES.values()]
  vids = [v for v in vrefs or [] if v not in docs]
  vparts = video_parts(vrefs)
  if vparts and not secret("GEMINI_API_KEY"):
    return ("⚠️ Videos and PDFs need the Gemini key (GEMINI_API_KEY) — Gemini is the AI that watches videos and reads PDFs.",
            "", "")
  research = ""
  if team:
    if docs:
      status.update(label="📄 ✨ Gemini is reading the PDF...")
      try:
        report = gemini([{"text": DOC_READ_PROMPT.format(question=question, vehicle=vehicle or "not given",
                                                          codes=codes or "none", symptoms=symptoms or "not given")}]
                        + video_parts(docs), timeout=240, think="high")
        prompt += ("\n\nPDF REPORT (✨ Gemini read the technician's PDF; the other team members can't open it and work from "
                   "this report):\n" + report)
      except AIError as e:
        log_problem("ai", "PDF report", str(e))
        prompt += f"\n\nPDF REPORT: not available ({e}). Say that the PDF couldn't be read."
    if vids:
      status.update(label="🎥 ✨ Gemini is watching and listening to the video...")
      try:
        report = gemini([{"text": VIDEO_WATCH_PROMPT.format(question=question, vehicle=vehicle or "not given",
                                                             codes=codes or "none", symptoms=symptoms or "not given")}]
                        + video_parts(vids), timeout=240, think="high")
        prompt += ("\n\nVIDEO REPORT (✨ Gemini watched and listened to the technician's video; the other team members "
                   "can't see or hear it and work from this report):\n" + report)
      except AIError as e:
        log_problem("ai", "Video report", str(e))
        prompt += f"\n\nVIDEO REPORT: not available ({e}). Say that the video couldn't be checked."
    reply, research, draft, ds_draft, more = team_answer(prompt, vehicle or "General vehicle", codes, symptoms,
                                                   bool(secret("PERPLEXITY_API_KEY")), status, question=question,
                                                   image_b64=photos_b64, extra_parts=vparts)
    who = ("🎥 " if vids else "") + ("📄 " if docs else "") + team_names(draft, ds_draft, research, more) + " · all checked each other"
  elif vparts:   # quick answer about a video or PDF: Gemini is the one that can watch / read it
    status.update(label="📄 ✨ Gemini is reading the PDF..." if docs and not vids else "🎥 ✨ Gemini is watching and listening to the video...")
    try:
      reply = gemini([{"text": prompt}] + [{"inline_data": {"mime_type": "image/jpeg", "data": b}} for b in photos_b64] + vparts,
                     timeout=240)
      who = f"✨ {gemini_label()} · " + " and ".join((["watched the video"] if vids else []) + (["read the PDF"] if docs else [])) + " · quick answer"
    except AIError as e:
      reply, who = f"⚠️ {e}", ""
  else:
    status.update(label="⚡ Quick answer — thinking...")
    reply, who = quick_ai(prompt, image_b64=photos_b64, max_tokens=4000)
    who = (who + " · quick answer") if who else ""
  return reply, who, research


def _recent_video_refs() -> list:
  """Follow-up questions keep using the video from the last few questions (Gemini keeps it for 48 hours)."""
  asked = [m for m in (ss.chat_history or []) if m.get("role") == "user"]
  for m in reversed(asked[-3:]):
    vs = [v for v in (m.get("videos") or []) if v.get("uri") and time.time() - float(v.get("at") or 0) < 40 * 3600]
    if vs:
      return vs[-1:]
  return []


def _chat_add_answer(rid: str, reply: str, who: str = "", research: str = "", vrefs: list | None = None):
  hist = list(ss.chat_history or [])
  ui = next((i for i, m in enumerate(hist) if m.get("role") == "user" and m.get("chat_id") == rid), None)
  if ui is not None and vrefs:
    hist[ui] = dict(hist[ui], videos=vrefs)
  msg = {"role": "assistant", "content": reply, "chat_id": rid, "who": who, "research": research}
  ai = next((i for i, m in enumerate(hist) if m.get("role") == "assistant" and m.get("chat_id") == rid), None)
  if ai is not None:
    hist[ai] = msg
  elif ui is not None:
    hist.insert(ui + 1, msg)
  else:
    hist.append(msg)
  ss.chat_history = hist


def ask_chat(question: str, imgs: list, team: bool, where: str, videos: list | None = None):
  """Ask one question. The answer is worked out in the background (so locking the phone or switching tabs can't lose
  it), saved to permanent memory when it's done, and shown by the progress box (_chat_watch)."""
  videos = list(videos or [])[:3]   # videos and PDFs: [(file name, bytes)]
  photos_b64 = [_jpeg_b64(im, 2000) for im in imgs]      # big enough to read wire colors and pin numbers
  thumbs = []
  for im in imgs:
    t = im.convert("RGB"); t.thumbnail((500, 500)); b = io.BytesIO(); t.save(b, format="JPEG", quality=80); thumbs.append(b.getvalue())
  rid = datetime.now().strftime("%Y%m%d%H%M%S%f")
  if not ss.get("chat_conv"):
    ss.chat_conv = rid
  st.query_params["chat"] = ss.chat_conv   # a reload (phone locked too long) brings this conversation back
  reuse = [] if videos else _recent_video_refs()
  ss.chat_history = (ss.chat_history or []) + [{"role": "user", "content": question, "photos": thumbs, "chat_id": rid,
                                                "video_names": [n for n, _ in videos], "videos": [],
                                                "reused_video": bool(reuse)}]
  eye = eye_fresh()
  if eye:   # the shared screen / camera goes first, so the AI sees what the tech sees
    photos_b64 = [eye["img"]] + photos_b64[:3]
    try:
      t = Image.open(io.BytesIO(base64.b64decode(eye["img"]))).convert("RGB"); t.thumbnail((500, 500))
      b = io.BytesIO(); t.save(b, format="JPEG", quality=80)
      ss.chat_history[-1]["photos"] = [b.getvalue()] + list(ss.chat_history[-1].get("photos") or [])
      ss.chat_history[-1]["eye"] = True
    except Exception:
      pass
  n_doc = sum(1 for n, _ in videos if is_doc(n)) or sum(1 for v in reuse if v.get("mime") in DOC_TYPES.values())
  n_vid = sum(1 for n, _ in videos if not is_doc(n)) or sum(1 for v in reuse if v.get("mime") not in DOC_TYPES.values())
  prompt = chat_prompt_for(question, len(photos_b64), n_vid, n_doc) + (
      "\nThe FIRST image is a live view of what the technician is looking at right now (their shared scan tool screen or "
      "camera). Read it carefully — it is their professional scan tool's data." if eye else "")
  n_notes = len(knowledge_for_job(30, question)) if knowledge_entries() else 0
  vehicle, codes, symptoms = ss.vehicle_info or "", ", ".join(current_codes()), (ss.symptoms or "").strip()
  meta = {"id": rid, "conv": ss.chat_conv, "q": question, "at": datetime.now().strftime("%Y-%m-%d %I:%M %p"),
          "vin": ss.active_vin or "", "vehicle": vehicle, "codes": current_codes(), "job": ss.get("job_id") or "",
          "tech": ss.get("tech_user") or "", "photos_n": len(imgs), "videos_n": len(videos) or len(reuse), "where": where,
          "team": bool(team)}
  store_put("chat", rid, dict(meta, a="", state="working"))
  job_id = "chat-" + rid
  link, t_start = app_link(ss.get("job_id"), ss.chat_conv), time.time()

  def job():
    vrefs = list(reuse)
    try:
      for name, data in videos:
        _JobStatus(job_id).update(label=f"📤 Sending the {'PDF' if is_doc(name) else 'video'} to Gemini "
                                        f"({max(len(data) / 1e6, 0.1):.1f} MB)...")
        vrefs.append(gemini_upload(data, media_mime(name), name))
      reply, who, research = run_chat_ai(job_id, prompt, question, photos_b64, vrefs, team, vehicle, codes, symptoms)
    except AIError as e:
      reply, who, research = f"⚠️ {e}", "", ""
    reply, diag = split_need_diagram(reply)
    if who and n_notes:
      who += f" · 📖 {n_notes} of your notes sent"
    ok = not str(reply).startswith("⚠️")
    store_put("chat", rid, dict(meta, a=reply, who=who, state="done" if ok else "failed",
                                videos=[v for v in vrefs if v not in reuse], reused=bool(reuse)))
    if time.time() - t_start > 20:   # long enough that you may have put the phone down
      notify("💬 Answer ready" if ok else "⚠️ Chat answer failed", f"{vehicle or 'Quick help'} — {question[:70]}\n{first_line(reply)}",
             "speech_balloon", 3, link)
    return reply, who, research, [v for v in vrefs if v not in reuse], diag

  if start_ai_job(job_id, job):
    ss._chat_pending = {"job": job_id, "rid": rid, "where": where}
    st.rerun()   # shows the question and the progress box right away
  with st.spinner("The AI is working on it..."):   # older Streamlit without background jobs: wait here
    reply, who, research, vrefs, diag = job()
  _chat_add_answer(rid, reply, who, research, vrefs)
  add_diagram_requests(diag, "chat")
  st.rerun()


if hasattr(st, "fragment"):
  @st.fragment(run_every=2)
  def _chat_watch():
    """Progress box for the answer being worked on; puts the answer in the chat when it's ready."""
    p = ss.get("_chat_pending")
    if not p:
      return
    j = _ai_jobs().get(p["job"])
    if j is None:   # the app restarted (or another window already collected it): use what was saved
      ss._chat_pending = None
      rec = store_get("chat", p["rid"]) or {}
      _chat_add_answer(p["rid"], rec.get("a") or "⚠️ The app restarted before this answer came back. Please ask again.",
                       rec.get("who", ""), "", rec.get("videos"))
      st.rerun()
    if j["state"] == "running":
      secs = int(time.time() - j["started"])
      st.info(f"{j.get('label') or '🤖 The AI team is working on it...'} · {secs // 60}:{secs % 60:02d}  \n"
              "You can lock your phone or use other tabs — the answer is saved when it's ready.")
      return
    _ai_jobs().pop(p["job"], None)
    ss._chat_pending = None
    if j["state"] == "done":
      reply, who, research, vrefs, *more = j["result"]
      _chat_add_answer(p["rid"], reply, who, research, vrefs)
      if more:
        add_diagram_requests(more[0], "chat")
    else:
      log_problem("ai", "Chat answer", j.get("error", "failed"))
      _chat_add_answer(p["rid"], f"⚠️ The AI couldn't answer: {j.get('error')}", "")
    st.rerun()   # full refresh so the answer shows everywhere
else:
  def _chat_watch():
    pass


def restore_chat(conv: str):
  """After a reload (phone locked for a long time, browser restarted), bring back the conversation and any answer that
  was still being worked on."""
  try:
    recs = sorted((r.get("data") or {} for r in store_list("chat", 200, {"conv": conv})), key=lambda d: str(d.get("id", "")))
  except Exception:
    return
  if not recs:
    return
  hist = list(ss.chat_history or [])
  have = {(m.get("role"), m.get("chat_id")) for m in hist}
  for d in recs:
    rid = d.get("id")
    if ("user", rid) not in have:
      hist.append({"role": "user", "content": d.get("q", ""), "chat_id": rid, "videos": d.get("videos") or [],
                   "reused_video": bool(d.get("reused"))})
    if ("assistant", rid) in have:
      continue
    if d.get("state", "done") != "working":
      hist.append({"role": "assistant", "content": d.get("a") or "", "chat_id": rid, "who": d.get("who", "")})
    elif "chat-" + str(rid) in _ai_jobs():
      ss._chat_pending = {"job": "chat-" + str(rid), "rid": rid, "where": "quick"}   # still working: keep watching it
    else:
      hist.append({"role": "assistant", "content": "⚠️ The app restarted before this answer came back. Please ask again.",
                   "chat_id": rid})
  ss.chat_history, ss.chat_conv = hist, conv


def new_chat():
  ss.chat_history, ss.chat_conv, ss._chat_pending = [], None, None
  if "chat" in st.query_params:
    del st.query_params["chat"]


# After a reload (phone locked a long time, browser closed): the conversation's id is in the address bar — bring it back
if "_chat_restored" not in ss:
  ss._chat_restored = True
  if _qc := st.query_params.get("chat"):
    with guard("Bringing back the chat"):
      restore_chat(_qc)


PIN_PROMPT = """A technician got this answer from the AI and wants to keep the useful testing fact as a note in the shop's
knowledge base (the AI team reads these notes on every future diagnosis).
Vehicle at the time: {vehicle}
Question: {q}
Answer: {a}

Write ONE short note in plain words (1-3 sentences): a spec / known-good value, what a reading or pattern means, a test
procedure, or a rule of thumb. Keep numbers and units exactly as given; add nothing that isn't in the answer.
Return JSON only: {{"topic": "<2-4 words, e.g. Fuel pressure>", "type": "<one of: Spec / known-good value | What a pattern means | Test procedure | Rule of thumb>", "applies_to": "<make / engine / system it applies to, or All>", "rule": "<the note>"}}"""


def chat_pin_form(where: str):
  """📌 Save to Knowledge: the AI writes the answer up as one short note, the tech checks it, then it's saved."""
  p = ss.chat_pin
  if p.get("note") is None:
    with st.spinner("Writing it up as a short note..."):
      raw, _who = quick_ai(PIN_PROMPT.format(vehicle=ss.vehicle_info or "not given", q=p.get("q", "")[:1500], a=p.get("a", "")[:6000]),
                           max_tokens=3000, effort="low")
    o = find_json(raw, dict) or {}
    p["note"] = {"topic": str(o.get("topic") or "General")[:60], "applies_to": str(o.get("applies_to") or "All")[:60],
                 "type": o.get("type") if o.get("type") in KNOW_KINDS else "Rule of thumb",
                 "rule": str(o.get("rule") or "").strip()[:600]}
  n = p["note"]
  with st.form(f"pin_form_{where}"):
    st.markdown("**📌 Save to Knowledge** — fix anything that's off, then save. The AI team will use it on every job it fits.")
    if not n["rule"]:
      st.caption("The AI didn't find a clear testing fact in that answer — write the note in your own words.")
    c1, c2, c3 = st.columns(3)
    topic = c1.text_input("Topic", value=n["topic"])
    kind = c2.selectbox("Type", KNOW_KINDS, index=KNOW_KINDS.index(n["type"]))
    applies = c3.text_input("Applies to", value=n["applies_to"])
    rule = st.text_area("Note", value=n["rule"], height=110)
    s1, s2 = st.columns(2)
    save = s1.form_submit_button("💾 Save to Knowledge", type="primary", use_container_width=True)
    cancel = s2.form_submit_button("✖️ Cancel", use_container_width=True)
  if save and str(rule or "").strip():
    store_put("know", datetime.now().strftime("%Y%m%d%H%M%S%f"),
              {"topic": str(topic or "General").strip(), "type": kind or "Rule of thumb", "applies_to": str(applies or "All").strip(),
               "rule": str(rule).strip(), "source": f"Chat answer, {datetime.now():%Y-%m-%d}", "added": datetime.now().strftime("%Y-%m-%d"),
               "tech": ss.get("tech_user") or ""})
    ss.chat_pin = None
    queue_update(toast="📌 Saved to Knowledge")
  elif cancel:
    ss.chat_pin = None
    st.rerun()


def chat_messages(msgs: list, where: str, start: int = 0):
  """Show the conversation, with 📌 Save to Knowledge under each answer."""
  for i, msg in enumerate(msgs, start):
    with st.chat_message(msg.get("role") or "assistant"):
      for thumb in msg.get("photos") or []:
        st.image(thumb, width=220)
      vnames = msg.get("video_names") or [v.get("name", "video") for v in msg.get("videos") or []]
      if msg.get("role") == "user" and (vnames or msg.get("reused_video")):
        st.caption(" · ".join(("📄 " if is_doc(n) else "🎥 ") + n for n in vnames) if vnames
                   else "🎥 📄 about the same video / PDF as before")
      if msg.get("who"):
        st.caption(msg["who"])
      st.markdown(msg.get("content") or "")
      if msg.get("research"):
        with st.expander("🌐 Sources Perplexity found"):
          st.markdown(msg["research"])
      if msg.get("role") == "assistant" and not str(msg.get("content") or "").startswith("⚠️"):
        mid = str(msg.get("chat_id") or i)
        pin = ss.get("chat_pin") or {}
        if pin.get("id") == mid and pin.get("where") == where:
          chat_pin_form(where)
        elif st.button("📌 Save to Knowledge", key=f"pin_{where}_{mid}_{i}",
                       help="Keep the useful fact from this answer as a Knowledge note the AI uses on every job"):
          q = next((m.get("content", "") for m in reversed((ss.chat_history or [])[:i]) if m.get("role") == "user"), "")
          ss.chat_pin = {"where": where, "id": mid, "q": q, "a": msg.get("content") or "", "note": None}
          st.rerun()


def past_chats_panel():
  rows = [r.get("data") or {} for r in store_list("chat", 300)]
  rows = [d for d in rows if d.get("q")]
  if not rows:
    st.caption("No saved chats yet — every question you ask is saved here.")
    return
  c1, c2 = st.columns([3, 1])
  qq = c1.text_input("🔎 Search past chats", key="qh_search", placeholder="e.g. fuel pressure, Silverado, P0171").strip().lower()
  mine = c2.checkbox("This car only", key="qh_car", disabled=not ss.active_vin)
  shown = [d for d in rows if (not mine or d.get("vin") == ss.active_vin)
           and (not qq or qq in f"{d.get('q', '')} {d.get('a', '')} {d.get('vehicle', '')}".lower())]
  st.caption(f"{len(shown)} of {len(rows)} saved chat(s){' — showing the newest 15' if len(shown) > 15 else ''}")
  for d in shown[:15]:
    with st.container(border=True):
      st.markdown(f"<small>{html_lib.escape(d.get('at', ''))} · {html_lib.escape(d.get('vehicle') or 'no car open')}"
                  f"{(' · ' + html_lib.escape(d['tech'])) if d.get('tech') else ''}</small>", unsafe_allow_html=True)
      st.markdown(f"**Q: {d.get('q', '')}**")
      a = d.get("a", "")
      st.markdown(a if len(a) <= 700 else a[:700] + " …")
      b1, b2 = st.columns(2)
      if b1.button("↩️ Continue this chat", key=f"qh_cont_{d.get('id')}", use_container_width=True):
        ss.chat_history = (ss.chat_history or []) + [{"role": "user", "content": d.get("q", ""), "chat_id": d.get("id")},
                                                     {"role": "assistant", "content": a, "chat_id": d.get("id"), "who": d.get("who", "")}]
        st.rerun()
      if b2.button("🗑️ Delete", key=f"qh_del_{d.get('id')}", use_container_width=True):
        store_delete("chat", d.get("id"))
        st.rerun()


def _try(fn, *a, fallback_drop=(), **kw):
  """Call a Streamlit function with newer options; on an older Streamlit, retry without them."""
  try:
    return fn(*a, **kw)
  except TypeError:
    return fn(*a, **{k: v for k, v in kw.items() if k not in fallback_drop})


def transcribe_audio(data: bytes, mime: str = "audio/wav") -> str:
  """🎙️ What the tech said, as text (Gemini listens). Keeps codes, VINs and numbers exactly."""
  if not secret("GEMINI_API_KEY"):
    raise AIError("voice needs the Gemini key (GEMINI_API_KEY).")
  mime = mime if str(mime).startswith("audio/") else "audio/wav"
  txt = gemini([{"text": "Transcribe exactly what this auto technician says. Keep trouble codes (like P0300), VINs, part "
                         "names, numbers and units exactly as spoken (write codes as P0300, not 'P zero three hundred'). "
                         "Return only their words — no notes. If there is no speech, return the single word NONE."},
                {"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}}], timeout=60, think="low")
  txt = txt.strip().strip('"')
  return "" if txt.upper().startswith("NONE") else txt


def chat_files_split(files: list) -> tuple[list, list]:
  """Uploaded files -> (photos as images, videos and PDFs as (name, bytes))."""
  imgs, vids = [], []
  for f in files or []:
    name = getattr(f, "name", "file")
    if is_video(name) or is_doc(name):
      if len(vids) < 3:
        vids.append((name, f.getvalue()))
      continue
    try:
      if len(imgs) < 4:
        imgs.append(ImageOps.exif_transpose(Image.open(io.BytesIO(f.getvalue()))))
    except Exception:
      st.warning(f"Couldn't open {name} — try a JPG or PNG.")
  return imgs, vids


def _chat_input_box(placeholder: str):
  """The message box at the bottom: type, 📎 attach photos / video, or 🎙️ talk (newer Streamlit) — older ones get a plain box.
  Returns (what was sent, can it take files)."""
  tries = (dict(accept_file="multiple", file_type=PHOTO_TYPES + list(VIDEO_TYPES) + list(DOC_TYPES), accept_audio=True),
           dict(accept_file="multiple", file_type=PHOTO_TYPES + list(VIDEO_TYPES) + list(DOC_TYPES)),
           {})
  for kw in tries:
    try:
      return st.chat_input(placeholder, key="chat_box", **kw), bool(kw)
    except TypeError:
      continue
  return st.chat_input(placeholder), False


def _chat_scroll_down(n: int):
  """When a new message shows up, slide the conversation to the bottom (only while 💬 Chat is the screen you're on)."""
  components.html(f"""<script>
  (function () {{
    const f = window.frameElement;
    if (!f || f.offsetParent === null) return;      // Chat isn't the screen on show
    const d = window.parent.document, w = window.parent;
    const m = d.querySelector('[data-testid="stMain"]') || d.querySelector('section.main');
    const go = () => {{ if (m && m.scrollHeight > m.clientHeight) m.scrollTo({{top: m.scrollHeight, behavior: "smooth"}});
                        else w.scrollTo({{top: d.body.scrollHeight, behavior: "smooth"}}); }};
    setTimeout(go, 150); setTimeout(go, 700);
  }})();   // message {n}
  </script>""", height=0)


def chat_home():
  """💬 The front screen: just the conversation with the AI, like a chat app. Type, 📎 attach or 🎙️ talk in the bar at the
  bottom; ⋯ holds the extras (show the AI your screen, all the AIs checking each other, past chats). 🧹 New chat is pinned
  at the top of the screen."""
  msgs = ss.chat_history or []
  pending = ss.get("_chat_pending")
  # fixed spots, in this order, so the shared screen (👀) never reloads when messages come in
  top, eye_box, past_box, convo, watch_box, tail = (st.container() for _ in range(6))
  bar = _keyed_box("chatbar")
  team = bool(ss.get("qh_team", True))

  # ---------- the bar at the bottom: ＋ extras and the message box ----------
  with bar:
    _pop = getattr(st, "popover", None)
    with (_pop("⋯") if _pop else st.expander("⋯ More")):
      st.toggle("👀 Let the AI see my screen or camera", key="eye_toggle",
                help="Share your scan tool's screen (from a computer) or point the phone camera at it. The AI reads it every "
                     "half minute and uses it in every answer and AI Check — so it sees what you see.")
      st.checkbox("🤝 All AIs check each other (a minute or two)", value=True, key="qh_team",
                  help="On: the web is searched, Gemini, ChatGPT and DeepSeek each write their own answer without seeing "
                       "the others, and Claude checks them all against the data. Off: one AI answers in a few seconds.")
      st.toggle("🕘 Past chats", key="qh_past")
      n_kn = len(knowledge_entries())
      st.caption("The AI knows the open car, the codes, the scanner data, the test plan, your shop history and "
                 + (f"your {n_kn:,} Knowledge notes" if n_kn else "your Knowledge notes")
                 + ", and remembers your earlier chats. Every question and answer is saved.")
      upl_key = f"qh_files_{ss.get('qh_files_n', 0)}"
      old_files = []
    sent, can_attach = _chat_input_box("Ask anything — codes, specs, how to test it…" if not msgs else "Reply…")
    if not can_attach:   # older Streamlit: photos / video go in through 📎
      with (_pop("📎") if _pop else st.expander("📎 Photos / video")):
        old_files = st.file_uploader("📷 🎥 📄 Photos, a video or a PDF for your next question",
                                     type=PHOTO_TYPES + list(VIDEO_TYPES) + list(DOC_TYPES),
                                     accept_multiple_files=True, key=upl_key) or []

  # ---------- top: the greeting on a fresh chat, a slim header once you're talking ----------
  with top:
    if msgs:   # 🧹 New chat — pinned at the very top of the screen, so it's always one tap away
      with _keyed_box("newchat"):
        if st.button("🧹 New chat", key="qh_new",
                     help="Starts fresh. Earlier chats stay saved and the AI still remembers them."):
          new_chat()
          st.rerun()
    if not store_on():
      st.warning("⚠️ Permanent storage isn't set up yet, so jobs and chats are erased when the app restarts. Add SUPABASE_URL "
                 "and SUPABASE_KEY to Secrets (⚙️ top right).")
    elif ss.get("_store_err"):
      st.warning(f"⚠️ Last save had a problem: {ss._store_err} (details in ☰ More → 📋 Log → 🐞 Problem log)")
    if not msgs and not pending:
      _now = _local_now()
      hi = "Good morning" if _now.hour < 12 else ("Good afternoon" if _now.hour < 17 else "Good evening")
      who = html_lib.escape(ss.get("tech_user") or "")
      who = "" if who.lower() == "shop" else who   # the shared shop login has no person's name
      st.markdown('<div class="tdg-greet"><div class="ic"><svg width="62" height="36" viewBox="0 0 120 70" fill="none">'
                  '<path d="M 5 45 L 22 45 L 24 60 L 42 60 L 43 5 L 46 36 Q 48 34 54 36 T 64 36 T 74 35 T 80 36 Q 84 18 88 50 Q 92 24 96 44 Q 100 32 104 42 L 118 42" '
                  'stroke="#22D3EE" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>'
                  f'</div><h1>{hi}{(", " + who) if who else ""}</h1><div class="q">What are we working on?</div>'
                  '<div class="tip">Type it, tap ＋ in the box to add a photo, a video or a PDF, or tap 🎙️ and just talk.</div></div>',
                  unsafe_allow_html=True)

  # ---------- 👀 the shared screen / camera ----------
  with eye_box:
    if ss.get("eye_toggle"):
      eye_panel()
    else:
      ss.eye_on, ss.eye = False, None

  # ---------- 🕘 past chats ----------
  if ss.get("qh_past"):
    with past_box:
      with st.expander("🕘 Past chats", expanded=True):
        past_chats_panel()

  # ---------- what you sent (handled before the progress box, so nothing you send is lost when an answer lands) ----------
  def _go(text: str, imgs: list, vids: list):
    if ss.get("_chat_pending"):
      ss._chat_queue = (text, imgs, vids)    # asked as soon as the current answer is in
      st.toast("Got it — I'll ask that as soon as the answer I'm working on is done.")
      return
    with watch_box:
      ask_chat(text, imgs, team, "quick", vids)

  if ss.pop("_eye_ask", False) and not pending and eye_fresh():
    _go("Here's what I'm looking at right now. What do you see? Anything that doesn't look right, and what should I "
        "check next?", [], [])
  if sent is not None:
    text = (sent if isinstance(sent, str) else (getattr(sent, "text", None) or "")) or ""
    files = [] if isinstance(sent, str) else list(getattr(sent, "files", None) or [])
    files += list(old_files)
    audio = None if isinstance(sent, str) else getattr(sent, "audio", None)
    if audio is not None:
      try:
        with st.spinner("🎙️ Listening to what you said…"):
          said = transcribe_audio(audio.getvalue(), getattr(audio, "type", "") or "audio/wav")
      except AIError as e_:
        said = None
        st.warning(f"Couldn't hear that: {e_}")
      if said:
        text = (text + " " + said).strip()
      elif said == "" and not text and not files:
        st.warning("Didn't catch any words — try again a little closer to the phone.")
    imgs, vids = chat_files_split(files)
    if old_files:
      ss.qh_files_n = ss.get("qh_files_n", 0) + 1   # empty the picker for the next question
    if not text and (imgs or vids):
      text = ("What's in this PDF that matters for this car? Pull out the specs, test steps and pinouts I need."
              if vids and all(is_doc(n) for n, _ in vids) else
              "What do you see in this video (and hear)? Anything that doesn't look or sound right, and what should I check "
              "next?" if vids else "What do you see here? Anything that doesn't look right, and what should I check next?")
    if text:
      _go(text, imgs, vids)
  elif not pending and ss.get("_chat_queue"):
    _go(*ss.pop("_chat_queue"))

  # ---------- the conversation ----------
  with convo:
    start = 0
    if len(msgs) > 24 and not ss.get("qh_all"):
      start = len(msgs) - 24
      if st.button(f"⬆️ Show the {start} earlier message(s)", key="qh_more"):
        ss.qh_all = True
        st.rerun()
    chat_messages(msgs[start:], "quick", start)
  if pending:
    with watch_box:
      _chat_watch()
  with tail:
    st.markdown('<div class="tdg-chatpad"></div>', unsafe_allow_html=True)   # room so the bar never covers the last answer
    if len(msgs) != ss.get("_chat_seen_n", 0):
      ss._chat_seen_n = len(msgs)
      if msgs:
        _chat_scroll_down(len(msgs))


def test_results_panel():
  """🧪 Every guided test on this car (🎯 Guided Tests on the scanner and the tests the AI runs) — also on the repair order."""
  st.write("---")
  st.markdown("#### 🧪 Test results on this car")
  t = ss.test_results or {}
  if not t:
    st.caption("No tests run yet. Connect the scanner on 🚗 Vehicle Scan and use 🎯 Guided Tests — or let the AI run the "
               "tests it asks for. Every result shows up here and on the repair order.")
    return
  dot = {"GOOD": "🟢", "MARGINAL": "🟡", "BAD": "🔴"}
  rows = []
  for k, v in t.items():
    g = str(v.get("grade", "")).upper() if isinstance(v, dict) else ""
    rows.append({"Test": k, "Result": f"{dot.get(g, '⚪')} {g.title()}".strip(),
                 "What it found": str(v.get("verdict", "")) if isinstance(v, dict) else str(v)})
  st.dataframe(rows, use_container_width=True, hide_index=True)


# ========================================================
# --- SCOPE DATA FILE SCREEN (🔬 Scope & Tests) ---
# ========================================================
SYMPTOM_CHIPS = ["⚠️ Check engine light on", "🛑 Cranks, no start", "🐢 Hard start", "🫨 Rough idle",
                 "💨 Hesitates on acceleration", "📉 Stalls", "🔥 Overheating", "⛽ Poor fuel economy",
                 "🔊 Unusual noise", "👃 Smell (fuel, coolant or burning)", "❄️ Only when cold", "🌡️ Only when hot",
                 "🔁 Comes and goes", "🛣️ Only at highway speed", "⚙️ Shifting problem", "🔋 Battery keeps dying"]

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
def measure_cached(raw: bytes, idx: int, wtype: str, factor: float, cyl: int, rpm_hint: float = 0.0) -> dict:
  cap = load_capture(raw)
  return measure_channel(cap["t"], cap["chans"][idx]["y"] * factor, cap["dt"], wtype, cyl or None, rpm_hint or None)


def _pretty_key(k: str) -> str:
  out = k
  for suf, lab in (("_kv_per_ms", " (kV/ms)"), ("_wobble_deg", " wobble (±°)"), ("_deg", " (crank ° after gap)"), ("_kv", " (kV)"), ("_ms", " (ms)"), ("_pct", " (%)"), ("_hz", " (Hz)"),
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
  cams_seen = 0
  for i, ch in enumerate(cap["chans"]):
    a, b, c = st.columns([2.4, 0.8, 1.2])
    g = guess_type(ch)
    if g == "cam_in":
      g = "cam_in" if cams_seen == 0 else "cam_ex"   # first cam = intake (green), second = exhaust (red)
      cams_seen += 1
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
    try:
      rpm_hint = float(re.sub(r"[^\d.]", "", rpm or "") or 0)
    except ValueError:
      rpm_hint = 0.0
    results.append(measure_cached(raw, i, wtype, factor, cyl, rpm_hint))
    setup["chans"].append({"type": wtype, "cyl_no": cyl_no, "unit": unit, "_y": ch["y"] * factor, "name": ch["name"]})

  # ---- cam/crank correlation: where each cam edge lands in crank degrees ----
  crank_i = next((i for i, s_ in enumerate(setup["chans"]) if s_["type"] == "crank_sig"), None)
  if crank_i is not None:
    for i, s_ in enumerate(setup["chans"]):
      if s_["type"] in ("cam_in", "cam_ex"):
        try:
          ang, cnotes = cam_crank_angles(cap["t"], setup["chans"][crank_i]["_y"], s_["_y"])
        except Exception as e:
          ang, cnotes = {}, [f"Couldn't work out cam timing: {e}"]
        results[i] = dict(results[i], measurements={**results[i]["measurements"], **ang}, notes=cnotes + results[i]["notes"])
  elif any(s_["type"] in ("cam_in", "cam_ex") for s_ in setup["chans"]):
    st.caption("💡 Add the crank sensor on another channel to get cam timing in crank degrees (cam/crank correlation).")

  # ---- relative compression: name the cylinders from an ignition sync ----
  sync = next(((r, s_) for r, s_ in zip(results, setup["chans"]) if s_["type"] in ("sec_ign", "pri_ign", "coil_amp")
               and s_["cyl_no"] and r["events"]), None)
  for r in results:
    if r["type"] == "rel_comp" and sync and cyl and fo:
      named = name_cylinders(r["events"], [e["time_ms"] for e in sync[0]["events"]], cyl, fo, sync[1]["cyl_no"])
      if named:   # r is this channel's own result (a fresh copy from the cache), so updating it in place is safe
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
      _col = WAVE_COLORS.get(r["type"])
      st.line_chart({"ms": tt * 1000, f"{ch['name']} ({s_['unit']})": yy}, x="ms", height=200, **({"color": _col} if _col else {}))
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
          if key.endswith("_deg"):   # timing: compare in degrees (wraps at 360)
            dd = (val - rv + 180) % 360 - 180
            shown = f"{dd:+.1f}°"
          else:
            diff = round((val - rv) / abs(rv) * 100) if rv else None
            shown = f"{diff:+d}%" if diff is not None else "—"
          rows.append({"Channel": s_["name"], "Measurement": _pretty_key(key), "This car": val, "Known-good": rv,
                       "Difference": shown})
          lines.append(f"{s_['name']} {key}: this {val} vs known-good {rv} ({shown})")
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
                                symptoms=(ss.symptoms or "").strip() or "not given",
                                scan=scan_context("scope waveform " + " ".join(WAVE_TYPES.get(c_["type"], "") for c_ in setup["chans"])),
                                capture=capture_summary(cap, setup, results), compare=compare_txt)
    with st.status("The AI team is reading the measurements...", expanded=False) as status:
      text, _r, draft, ds_draft, more = team_answer(prompt, ss.vehicle_info or "vehicle", ", ".join(current_codes()),
                                              (ss.symptoms or "").strip(), False, status)
      status.update(label="Done", state="complete")
    ss.wave_result = {"text": text, "team": team_names(draft, ds_draft, "", more), "file": wf.name,
                      "at": datetime.now().strftime("%Y-%m-%d %I:%M %p")}
  if ss.get("wave_result"):
    with st.expander(f"🔬 Scope data analysis · {ss.wave_result.get('team', '')}", expanded=True):
      st.markdown(ss.wave_result["text"])


with tab3, guard("Diagnostics"):
  st.subheader("🔧 Diagnostics")
  context_bar()
  if ss.get("simple_view"):
    status_cards()
    st.markdown("<style>div[class*='st-key-pro_'] { display: none !important; }</style>", unsafe_allow_html=True)

  # ---------- 1. Codes ----------
  st.markdown("#### 🔢 Fault codes & complaint")
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
    st.caption("Connect the scanner on 🚗 Vehicle Scan — the codes it reads show up here automatically.")
  st.text_input("Add codes by hand (optional):", key="manual_dtc", placeholder="e.g. P0171, P0174")
  st.text_area("Symptoms / customer complaint (optional — works with or without codes):", key="symptoms", height=80,
               placeholder="e.g. Rough idle when cold, stumbles on hard acceleration, no check engine light")
  # one-tap symptoms: build the complaint fast without typing
  _chips = SYMPTOM_CHIPS
  _have = (ss.symptoms or "").lower()
  _cc = st.columns(6)
  for _i, _chip in enumerate(_chips):
    _done = _chip.split(" ", 1)[1].lower() in _have
    if _cc[_i % 6].button(("✓ " if _done else "") + _chip, key=f"chip_{_i}", use_container_width=True, disabled=_done):
      _txt = _chip.split(" ", 1)[1]
      queue_update(symptoms=((ss.symptoms or "").rstrip(" ,.") + (", " if (ss.symptoms or "").strip() else "") + _txt))

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
""" + DIAGRAM_RULE
    with st.status("Working on it...", expanded=False) as status:
      text, research, draft, ds_draft, more = team_answer(sym_prompt, vehicle, "", symptoms, use_web, status)
      status.update(label="Done", state="complete")
    text, _dg = split_need_diagram(text)
    add_diagram_requests(_dg, "test plan")
    ss._auto_steps = True
    ss.dtc_result = {"title": f"Symptoms · {vehicle}", "text": text, "research": research, "draft": draft, "ds_draft": ds_draft,
                    "team": team_names(draft, ds_draft, research, more), "gpt_draft": more.get("gpt", "")}

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
""" + DIAGRAM_RULE
    with st.status("Working on it...", expanded=False) as status:
      text, research, draft, ds_draft, more = team_answer(dtc_prompt, vehicle, code_str, symptoms, use_web, status)
      status.update(label="Done", state="complete")
    text, _dg = split_need_diagram(text)
    add_diagram_requests(_dg, "test plan")
    notify("📋 Test plan ready", f"{code_str} · {vehicle} — {first_line(text)}", "clipboard", 3, app_link(ss.get("job_id")))
    ss._auto_steps = True
    ss.dtc_result = {"title": f"{code_str} · {vehicle}", "text": text, "research": research, "draft": draft, "ds_draft": ds_draft,
                    "team": team_names(draft, ds_draft, research, more), "gpt_draft": more.get("gpt", "")}

  if ss.dtc_result:  # stays on screen while you use other tabs
    team = ss.dtc_result.get("team") or team_names(ss.dtc_result.get("draft", ""), ss.dtc_result.get("ds_draft", ""),
                                                    ss.dtc_result.get("research", ""))
    _simple = bool(ss.get("simple_view"))
    if _simple and (ss.get("plan_steps") or {}).get("_for") != _plan_sig() and ss.pop("_auto_steps", False):
      build_step_cards()   # Simple view: go straight to one-test-at-a-time cards after the tree runs
    with st.expander(f"📋 Test plan: {ss.dtc_result['title']} · {team}", expanded=not _simple):
      st.markdown(ss.dtc_result["text"])
    with guard("Step-by-step cards"):
      step_cards_panel(_simple)
    if _simple:
      pass   # drafts and web research stay out of the way in Simple view
    elif ss.dtc_result.get("draft"):
      with st.expander(f"✨ {gemini_label()}'s own draft (before the final check)"):
        st.markdown(ss.dtc_result["draft"])
    if ss.dtc_result.get("gpt_draft") and not _simple:
      with st.expander(f"💬 {openai_label()}'s own draft (written without seeing the others)"):
        st.markdown(ss.dtc_result["gpt_draft"])
    if ss.dtc_result.get("ds_draft") and not _simple:
      with st.expander(f"🐋 {deepseek_label()}'s own draft (text only)"):
        st.markdown(ss.dtc_result["ds_draft"])
    if ss.dtc_result.get("research") and not _simple:
      with st.expander("🌐 Web research (TSBs, recalls, known fixes, sources)"):
        st.markdown(ss.dtc_result["research"])

  st.caption("💬 Questions about the plan or a reading? Ask in Chat — it knows this car, the codes and the plan. "
             "Wiring diagrams, the scope and test results are on 🔬 Scope & Tests; the write-up is on 🧾 Customer & RO.")


# ========================================================
# --- 🔬 SCOPE & TESTS: wiring diagrams, scope & test readings, test results, test drive review ---
# ========================================================
with tab_scope, guard("Scope & Tests"):
  st.subheader("🔬 Scope & Tests")
  context_bar()
  with st.container():
    # ---------- Scope lab ----------
    st.markdown("#### 〰️ Scope & test readings")
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
        text, _r, draft, ds_draft, more = team_answer(prompt, ss.vehicle_info or "vehicle", code_str, ss.symptoms.strip(), False, status,
                                                image_b64=img_b64)
        status.update(label="Done", state="complete")
      ss.scope_result = {"text": text, "team": team_names(draft, ds_draft, "", more), "draft": draft, "ds_draft": ds_draft,
                         "gpt_draft": more.get("gpt", "")}

    if ss.scope_result:
      sr = ss.scope_result if isinstance(ss.scope_result, dict) else {"text": str(ss.scope_result), "team": ""}
      with st.expander(f"🔬 Scope & readings evaluation · {sr.get('team', '')}", expanded=True):
        st.markdown(sr["text"])
      if sr.get("draft") or sr.get("ds_draft") or sr.get("gpt_draft"):
        with st.expander("👀 See each AI's own read"):
          if sr.get("draft"):
            st.markdown(f"**✨ {gemini_label()}** (saw the photo)")
            st.markdown(sr["draft"])
          if sr.get("gpt_draft"):
            st.markdown(f"**💬 {openai_label()}** (saw the photo)")
            st.markdown(sr["gpt_draft"])
          if sr.get("ds_draft"):
            st.markdown(f"**🐋 {deepseek_label()}** (readings only — can't see photos)")
            st.markdown(sr["ds_draft"])

  with guard("Test results"):
    test_results_panel()
  st.write("---")
  st.markdown("#### 📐 Wiring diagrams")
  with guard("Wiring diagrams"):   # the diagrams the AI asked for (test plan, step cards, AI Check, chat) + ones you add
    diagrams_panel(fold=True)

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
# --- CUSTOMER / SHOP REPORT = the repair order (🧾 Customer & RO screen) ---
# ========================================================
FOLLOW_UP_LABELS = {0: "No follow-up", 7: "In about 1 week", 14: "In about 2 weeks", 30: "In about 1 month",
                    60: "In about 2 months", 90: "In about 3 months", 180: "In about 6 months"}

RO_STORY_PROMPT = """Write the repair order story (the "3 Cs") for this job the way a professional technician writes it on
the RO.
Vehicle: {vehicle} · VIN: {vin} · Mileage: {miles}
Customer concern: {complaint}
Trouble codes: {codes}
Tests done and their results: {tests}
Diagnostic steps worked so far: {progress}
Technician's notes: {notes}
Repair done: {fix}
Estimate lines: {estimate}

Format exactly (three short paragraphs, nothing else):
CONCERN: <the customer's concern in one or two sentences>
CAUSE: <what testing found — the tests done and the key readings that proved it, and the codes found>
CORRECTION: <the repair performed and how it was verified — or, if not repaired yet, start with "Recommend:" and give the
recommended repair from the notes / estimate>

RULES: plain professional shop language, past tense, short. Use ONLY the facts above — never invent a test, a reading, a
part, a price or a time. Leave out anything unknown. If the cause isn't confirmed yet, say what testing is still needed."""


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
  shop = secret("SHOP_NAME") or "Test Don't Guess"
  ff_html = ("<h2>Freeze frame (" + e(ff.get("dtc", "")) + ")</h2><p>" +
             " · ".join(f"{e(k)}: <b>{e(str(v))}</b>" for k, v in (ff.get("vals") or {}).items()) + "</p>") if ff.get("dtc") else ""
  return f"""<!doctype html><html><head><meta charset="utf-8"><title>Diagnostic report - {e(ss.vehicle_info or 'Vehicle')}</title>
<style>body{{font-family:Arial,sans-serif;color:#222;max-width:820px;margin:24px auto;padding:0 16px}}h1{{margin:0;font-size:24px}}
h2{{font-size:16px;border-bottom:2px solid #222;padding-bottom:3px;margin-top:22px}}table{{width:100%;border-collapse:collapse;font-size:13px}}
td,th{{border:1px solid #ccc;padding:5px 7px;text-align:left;vertical-align:top}}th{{background:#f2f2f2}}.muted{{color:#666;font-size:12px}}
pre{{white-space:pre-wrap;font-family:inherit;font-size:13px;background:#fafafa;border:1px solid #ddd;padding:10px}}
@media print{{button{{display:none}}}}</style></head><body>
<button onclick="window.print()" style="float:right;padding:8px 14px">Print / Save as PDF</button>
<h1>{e(shop)} — Repair Order</h1><div class="muted">Diagnostic report · {e(datetime.now().strftime("%B %d, %Y %I:%M %p"))}{(" · Job " + e(str(ss.get("job_id")))) if ss.get("job_id") else ""}</div>
<h2>Customer & vehicle</h2><table>
<tr><th>Customer</th><td>{e(ss.customer_name or '')}</td><th>Phone</th><td>{e(ss.customer_phone or '')}</td></tr>
<tr><th>Vehicle</th><td>{e(ss.vehicle_info or '')}</td><th>VIN</th><td>{e(ss.active_vin or 'not provided')}</td></tr>
<tr><th>Engine</th><td>{e(eng)}</td><th>Complaint</th><td>{e(ss.symptoms or '')}</td></tr>
<tr><th>Odometer</th><td>{e(ss.odometer or '')}</td><th>Technician</th><td>{e(ss.get('tech_user') or '')}</td></tr></table>
{"<h2>What we found</h2><p style='font-size:15px;line-height:1.5'>" + e(ss.customer_summary).replace(chr(10), "<br>") + "</p>" if (ss.customer_summary or "").strip() else ""}
{"<h2>Repair performed</h2><p><b>" + e(ss.fix_part) + "</b>" + ("<br>Verified by: " + e(ss.fix_test) if (ss.fix_test or "").strip() else "") + "</p>" if (ss.fix_part or "").strip() else ""}
{"<h2>Repair order write-up</h2><pre>" + e(ss.get("ro_story") or "") + "</pre>" if (ss.get("ro_story") or "").strip() else ""}
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


with tab_ro, guard("Repair order"):
  with st.container():
    st.write("---")
    st.markdown("#### 🧾 Repair order")
    with st.expander("💲 Estimate & job photos", expanded=True):
      st.caption("Photos save with the job and go on the customer report — the leaky gasket or chafed wire sells the repair "
                 "better than words. The estimate prints on the report with a total.")
      _pc1, _pc2 = st.columns(2)
      with _pc1:
        _new_photos = st.file_uploader("📸 Add photos to this job", type=["png", "jpg", "jpeg", "webp"],
                                       accept_multiple_files=True, key=f"job_photos_{ss.get('photo_n', 0)}_{ss.get('job_n', 0)}")
        if st.toggle("📷 Use the camera", key="job_cam_on"):
          _shot = camera_shot("Snap a photo for this job", key=f"job_cam_{ss.get('photo_n', 0)}_{ss.get('job_n', 0)}")
          if _shot is not None and st.button("💾 Attach this photo to the job", key="job_cam_add"):
            autosave_job(force=True)
            if not ss.get("job_id"):
              st.warning("Add a customer, vehicle or code first so there's a job to attach it to.")
            elif len(job_photos()) >= 12:
              st.warning("This job already has 12 photos (the max).")
            else:
              store_put("jobphoto", f"{ss.job_id}-{datetime.now().strftime('%H%M%S%f')}c",
                        {"job": ss.job_id, "b64": shrink_to_b64(_shot.getvalue()), "name": "camera",
                         "at": datetime.now().strftime("%Y-%m-%d %I:%M %p")})
              ss.photo_n = ss.get("photo_n", 0) + 1   # empty the camera for the next one
              queue_update(toast="Photo attached to the job")
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
    with st.expander("📤 Write-up for the customer — RO story, summary, email, text, print", expanded=True):
      st.caption("One page with the customer, the vehicle, the RO write-up, the estimate, all codes, every test result "
                 "(green / yellow / red) and photos. Email it, text the summary, or open it and use Print → Save as PDF.")
      notes = st.text_area("Technician notes / recommendation (goes on the report):", key="tech_notes", height=80,
                           placeholder="e.g. Recommend replacing cylinder 3 ignition coil and spark plugs. Fuel trims normal after repair.")
      _has_findings = bool(ss.dtc_result or ss.test_results or ss.tech_notes.strip() or ss.fix_part.strip() or current_codes())
      if st.button("✍️ Write a plain-English summary for the customer", disabled=not _has_findings):
        with st.spinner("Writing the customer summary..."):
          _sum, _who = quick_ai(CUSTOMER_SUMMARY_PROMPT.format(
              vehicle=ss.vehicle_info or "the vehicle", complaint=ss.symptoms.strip() or "not given", codes=", ".join(current_codes()) or "none",
              tests=json.dumps(ss.test_results or {})[:2500],
                notes=(ss.tech_notes.strip() + "\n" + plan_progress_text()).strip() or "none",
              fix=(ss.fix_part.strip() + (f" (proved by: {ss.fix_test.strip()})" if ss.fix_test.strip() else "")) or "not done yet",
              plan=(ss.dtc_result or {}).get("text", "")[:2500] or "none"), max_tokens=3000)
        if _sum.startswith("⚠️"):
          st.error(_sum)
        else:
          ss.customer_summary = _sum.strip()
      st.text_area("Customer summary (edit it as you like — it goes at the top of the report):", key="customer_summary", height=130,
                   placeholder="Tap the button above, or type your own summary for the customer.")
      st.markdown("**📝 RO write-up** — Concern · Cause · Correction (prints on the repair order)")
      if st.button("✍️ Write up the RO from this job", key="ro_write", disabled=not _has_findings,
                   help="The AI writes the 3 Cs from what's on this job — the complaint, codes, tests, plan steps, notes and fix. "
                        "It never adds a test or part you didn't do."):
        with st.spinner("Writing the repair order..."):
          _ro, _who = quick_ai(RO_STORY_PROMPT.format(
              vehicle=ss.vehicle_info or "the vehicle", vin=ss.active_vin or "not given", miles=ss.odometer or "not given",
              complaint=ss.symptoms.strip() or "not given", codes=", ".join(current_codes()) or "none",
              tests=json.dumps(ss.test_results or {})[:3000], progress=plan_progress_text()[:2500] or "none",
              notes=ss.tech_notes.strip() or "none",
              fix=(ss.fix_part.strip() + (f" (proved by: {ss.fix_test.strip()})" if ss.fix_test.strip() else "")) or "not done yet",
              estimate="; ".join(str(r.get("Item")) for r in (ss.estimate_rows or [])
                                 if isinstance(r, dict) and str(r.get("Item") or "").strip()) or "none"), max_tokens=3000)
        if _ro.startswith("⚠️"):
          st.error(_ro)
        else:
          ss.ro_story = _ro.strip()
      st.text_area("RO write-up", key="ro_story", height=150, label_visibility="collapsed",
                   placeholder="CONCERN: …\nCAUSE: …\nCORRECTION: …  (tap the button above, or type your own)")
      _rep_name = re.sub(r"\W+", "_", ss.vehicle_info or "vehicle")
      _report_html = build_report_html(notes)
      _bat = battery_slip_html() if any(re.search(r"charg|crank|battery|power", k, re.I) for k in (ss.test_results or {})) else ""
      _sc1, _sc2, _sc3, _sc4 = st.columns(4)
      with _sc1:
        st.download_button("🧾 Download repair order", data=_report_html.encode("utf-8"), mime="text/html",
                           file_name=f"RO_{_rep_name}_{datetime.now():%Y%m%d}.html", use_container_width=True)
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
        st.caption("📧 Add the customer's email at the top of this screen to enable emailing.")
      if not sms_ready():
        st.caption("💬 To text customers: make a free trial account at twilio.com, buy a texting number (~$1/mo), and add "
                   "TWILIO_SID, TWILIO_TOKEN and TWILIO_FROM (the number, like +16785551234) to Secrets.")
      _sent = [r.get("data") or {} for r in store_list("sent", 3, {"job": ss.get("job_id")})] if ss.get("job_id") else []
      if _sent:
        st.caption("Sent: " + " · ".join(f"{x.get('what')} by {x.get('how')} to {x.get('to')} ({x.get('at')})" for x in _sent))

      # ---------- 5. Confirmed fix ----------
    st.write("---")
    with st.expander("✅ Confirmed fix & follow-up — teaches the app", expanded=bool((ss.fix_part or "").strip())):
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
        st.caption("Set the vehicle on 🚗 Vehicle Scan first.")

      st.markdown("**📅 Follow up with this customer?**")
      _fu1, _fu2 = st.columns(2)
      _fu_opts = list(FOLLOW_UP_LABELS)
      _cur_fu = ss.follow_up_days if ss.follow_up_days in FOLLOW_UP_LABELS else 0
      _fu_pick = _fu1.selectbox("Call them back", _fu_opts, index=_fu_opts.index(_cur_fu),
                                format_func=lambda d: FOLLOW_UP_LABELS[d], key=f"fu_{ss.get('job_n', 0)}")
      ss.follow_up_days = _fu_pick
      _fu2.text_input("About what:", key="follow_up_note", placeholder="e.g. Rear brakes at 4mm — due soon")
      if _fu_pick:
        st.caption("It'll show under ☰ More → 📋 Log → 📅 Callbacks due when the time comes (counted from the job's last update).")
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
    same_car = not rec.get("vehicle") or rec.get("vehicle") == ss.vehicle_info
    ctx = shop_context("test drive fuel trim misfire stumble transmission shift converter slip charging catalyst") if same_car else ""
    ans, research, draft, ds_draft, more = team_answer(DRIVE_REVIEW_TASK + drive_text(rec) + ctx, rec.get("vehicle") or ss.vehicle_info or "vehicle",
                                                 ss.active_dtc, ss.symptoms.strip(), False, status)
    status.update(label="Done", state="complete")
  ss.setdefault("drive_reviews", {})[rec["id"]] = ans + f"\n\n_{team_names(draft, ds_draft, research, more)}_"
  notify("🚗 Test drive review ready", f"{rec.get('vehicle') or ss.vehicle_info or 'Test drive'} — {first_line(ans)}", "car", 3,
         app_link(ss.get("job_id")))
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
    st.info("No vehicles or DTCs logged yet. Connect the scanner (🚗 Vehicle Scan) or run a diagnostic tree (🔧 Diagnostics) to start logging.")

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
    st.caption("Nothing due. Set a follow-up when you close a job (🧾 Customer & RO → ✅ Confirmed fix) and it shows up here on time.")
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

with tab_scope, guard("Test drive review"):
  # ---------- 🚗 Test drive review ----------
  st.write("---")
  st.markdown("#### 🚗 Test drive review")
  drives = load_drives()
  if not drives:
    st.caption("Every test drive is saved automatically when you tap Stop Test Drive (and on your phone, even if the page "
               "reloads mid-drive). Older drives on your phone: 🚗 Vehicle Scan → 🎯 Guided Tests → 📁 Saved test drives → Send to app.")
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

with tab5, guard("Log tab"):
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
      f"Codes in Diagnostics: {ss.active_dtc or 'none'}",
      f"What happened: {what.strip() or '(not described)'}",
      "",
      f"RECENT LOGGED PROBLEMS ({len(recent)}):",
      *[f"- [{p.get('time')}] {p.get('kind')} in {p.get('where')}: {p.get('message')}"
        + (f"\n    {p.get('details', '').strip()[-1500:]}" if p.get("details") else "") for p in recent],
      "",
      "SCANNER STATE: " + (json.dumps({k: v for k, v in dbg.items() if k != "trace"}) if dbg else "not sent (tap 🐞 Send debug info on 🚗 Vehicle Scan)"),
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
             **{k: store_list(k, 1000) for k in ("job", "fix", "log", "drive", "jobphoto", "diagram", "wave", "csvwave", "know", "chat", "sent", "problem")
                if k != "know"}, "know": store_list_all("know")}
      ss._backup = json.dumps(_bk)
      ss._backup_counts = " · ".join(f"{k}: {len(_bk.get(k) or [])}" for k in ("job", "fix", "log", "drive", "jobphoto", "wave"))
    st.toast("Backup ready — tap Download")
  if ss.get("_backup"):
    st.download_button("⬇️ Download backup", data=ss._backup, mime="application/json",
                       file_name=f"tdg_backup_{datetime.now():%Y%m%d}.json")
    st.caption(f"Backup size: {len(ss._backup) / 1e6:.1f} MB · " + ss.get("_backup_counts", ""))

# ========================================================
# --- TAB 6: SHOP KNOWLEDGE (testing facts learned from books, classes and experience) ---
# ========================================================
KNOW_EXTRACT_PROMPT = """These are photos of pages from an automotive diagnostics book the technician owns. Pull out ONLY the
testing knowledge a technician would write in their own notebook:
- specs and known-good values (with the conditions they apply to: engine state, RPM, temperature, system type)
- what a waveform or reading pattern means (pattern -> likely cause)
- test procedures (how to hook up and what result proves what) as short steps
- rules of thumb

RULES:
- Write every note in YOUR OWN WORDS, short and plain, 1-3 sentences. Never copy sentences from the page.
- Keep numbers and specs exact — those are facts.
- Skip stories, introductions, opinions, marketing and anything that isn't testing knowledge.
- If a note only applies to certain vehicles or systems, say which in applies_to; otherwise "All".
- If the pages are unreadable or have no testing content, return [].

Return JSON only: a list of objects with keys
"topic" (short system name, e.g. "Secondary ignition", "Injector current", "Relative compression", "Pressure transducer"),
"type" (one of: "Spec / known-good value", "What a pattern means", "Test procedure", "Rule of thumb"),
"applies_to" (e.g. "All", "GM 3.6L", "COP ignition", "Port injection"),
"rule" (the note itself, in your own words)."""

def _note_key(text: str) -> str:
  return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _note_nums(text: str) -> list:
  return sorted(re.findall(r"\d+(?:\.\d+)?", str(text or "")))


def know_pending_from(found: list, src: str, who: str):
  """Notes the AI pulled from pages or a PDF -> the review table (nothing is saved until you tap Save).
  Notes you already have are left out: the same words, or the same meaning with the same numbers. A note that reads alike
  but has different numbers is kept — that's a different spec."""
  rows = [{"Keep": True, "Topic": str(x.get("topic") or "General")[:60],
           "Type": x.get("type") if x.get("type") in KNOW_KINDS else "Rule of thumb",
           "Applies to": str(x.get("applies_to") or "All")[:60], "Note": str(x.get("rule")).strip()[:600]}
          for x in found]
  have = knowledge_entries()
  have_keys = {_note_key(e.get("rule")) for e in have}
  keep, seen, skipped = [], set(), 0
  for r in rows:   # word for word the same as a note you have (or one earlier in this batch)
    k = _note_key(r["Note"])
    if k in have_keys or k in seen:
      skipped += 1
      continue
    seen.add(k)
    keep.append(r)
  try:   # 🧠 says the same thing (same numbers) as a note you have, or as one earlier in this batch
    if not (keep and embed_provider()):
      raise LookupError("no meaning search")
    vecs = ensure_vectors("know", [(e["_id"], note_text(e)) for e in have]) if have else {}
    new = embed_texts([f"{r['Topic']} ({r['Type']}; applies to {r['Applies to']}): {r['Note']}" for r in keep], "doc") if keep else []
    if len(new) == len(keep):
      byid = {e["_id"]: e for e in have}
      ids = list(vecs)
      M = np.stack([vecs[i] for i in ids]) if ids else None
      out, kept = [], []
      for r, v in zip(keep, new):
        nums, dup = _note_nums(r["Note"]), False
        if M is not None:
          sims = M[:, :len(v)] @ v[:M.shape[1]]
          dup = any(sims[j] >= 0.92 and _note_nums(byid[ids[j]].get("rule")) == nums for j in np.argsort(-sims)[:3])
        if not dup:
          dup = any(float(v @ v2) >= 0.95 and _note_nums(r2["Note"]) == nums for r2, v2 in kept)
        if dup:
          skipped += 1
        else:
          out.append(r)
          kept.append((r, v))
      keep = out
  except Exception:
    pass   # no meaning search: the word-for-word check above still runs
  ss.know_pending, ss.know_skipped = keep, skipped
  ss.know_pending_src, ss.know_pending_who = src, who


def know_pdf_prompt(pages: str) -> str:
  p = KNOW_EXTRACT_PROMPT.replace("These are photos of pages from an automotive diagnostics book the technician owns.",
                                  "This is a PDF the technician owns (a diagnostics book, training manual or service information).")
  rng = re.sub(r"[^0-9,\- ]", "", pages or "").strip(" ,-")
  if rng:
    p += f"\nOnly read pages {rng} of the PDF (the page numbers of the PDF file itself)."
  return p + "\nIf the document is long, keep the most useful notes — at most 150."


with tab6, guard("Knowledge tab"):
  st.subheader("📖 Shop knowledge")
  context_bar()
  st.caption("Testing facts you've learned — specs, what patterns mean, test methods — written as short notes in plain words. "
             "The AI team checks these on every diagnosis, scope analysis and chat question, using the ones that fit "
             "the car and the codes. Book pages and PDFs are only read, never saved: only the notes are kept.")
  entries = knowledge_entries()

  # ---- learn from book pages ----
  with st.expander("📸 📄 Learn from book pages or a PDF", expanded=not entries):
    st.caption("Lay the page flat in good light, whole page in the frame. A few pages at a time works best "
               "(up to 6 per batch). You'll check every note before it's saved.")
    kc1, kc2 = st.columns([2, 1])
    pages = kc1.file_uploader("Upload page photos (on a phone this also offers Take Photo — the sharpest option)",
                              type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True,
                              key=f"know_pages_{ss.get('know_n', 0)}") or []
    src = kc2.text_input("Source (book, chapter or page)", key="know_src", placeholder="e.g. Steckler scope book, ch. 3")
    # 📷 camera: snap a page, add it, snap the next one
    if st.toggle("📷 Use the camera — snap pages one at a time", key="know_cam_on"):
      st.caption("If it opens the selfie camera, tap the flip-camera icon. Hold the phone straight over the page.")
      shot = camera_shot("Snap a page", key=f"know_cam_{ss.get('know_n', 0)}_{ss.get('know_cam_n', 0)}")
      if shot is not None and st.button("➕ Add this page", key="know_cam_add", type="primary"):
        ss.know_cam_pages = (ss.get("know_cam_pages") or []) + [shot.getvalue()]
        ss.know_cam_n = ss.get("know_cam_n", 0) + 1   # empties the camera for the next page
        st.rerun()
    cam_pages = ss.get("know_cam_pages") or []
    if cam_pages:
      st.caption(f"📷 {len(cam_pages)} page(s) from the camera, ready to read:")
      st.image(cam_pages, width=110)
      if st.button("🗑️ Clear camera pages", key="know_cam_clear"):
        ss.know_cam_pages = []
        st.rerun()
    all_pages = [(getattr(f, "name", "a photo"), f.getvalue()) for f in pages] + \
        [(f"camera page {i + 1}", b) for i, b in enumerate(cam_pages)]
    if len(all_pages) > 6:
      st.caption(f"{len(all_pages)} pages added — the first 6 are read in this batch; do the rest in the next one.")
    if all_pages and st.button(f"🧠 Pull the testing info from {min(len(all_pages), 6)} page(s)", type="primary"):
      imgs = []
      for name_, raw_ in all_pages[:6]:
        try:
          imgs.append(shrink_to_b64(raw_, 1800, 85))
        except Exception:
          st.warning(f"Couldn't open {name_}.")
      if imgs:
        with st.spinner("Reading the pages and writing notes..."):
          raw_ans, who = quick_ai(KNOW_EXTRACT_PROMPT, image_b64=imgs, max_tokens=12000, effort="medium")
        found = find_json(raw_ans, list) or []
        found = [x for x in found if isinstance(x, dict) and str(x.get("rule") or "").strip()]
        if not found:
          st.error("No testing info came back. " + (raw_ans[:300] if raw_ans.startswith("⚠️") else
                                                    "Try sharper photos, or pages with specs and test steps."))
        else:
          know_pending_from(found, src.strip(), who)
          ss.know_cam_pages = cam_pages[max(0, 6 - len(pages)):]   # keep any camera pages that didn't fit in this batch
    # 📄 a PDF: Gemini reads the file itself (a manual, a training book chapter, service info saved as a PDF)
    st.markdown("**📄 Or a PDF** — a manual, a training book chapter, or service info you saved as a PDF")
    pc1, pc2 = st.columns([2, 1])
    kpdf = pc1.file_uploader("PDF file", type=["pdf"], key=f"know_pdf_{ss.get('know_n', 0)}")
    kpages = pc2.text_input("Pages to read (optional)", key="know_pdf_pages", placeholder="e.g. 12-30 — empty = all")
    if kpdf is not None and st.button("🧠 Pull the testing info from this PDF", type="primary", key="know_pdf_go"):
      try:
        with st.spinner("Sending the PDF to Gemini and reading it — a big file can take a couple of minutes..."):
          ref = gemini_upload(kpdf.getvalue(), "application/pdf", getattr(kpdf, "name", "book.pdf"), wait=300)
          raw_ans = gemini([{"text": know_pdf_prompt(kpages)}] + video_parts([ref]), json_mode=True, timeout=420)
        who = f"✨ {gemini_label()} read the PDF"
      except AIError as e_:
        raw_ans, who = f"⚠️ {e_}", ""
      found = [x for x in (find_json(raw_ans, list) or []) if isinstance(x, dict) and str(x.get("rule") or "").strip()]
      if not found:
        st.error("No testing info came back. " + (raw_ans[:300] if raw_ans.startswith("⚠️") else
                                                  "Try the pages with specs and test steps (Pages to read)."))
      else:
        know_pending_from(found, (src.strip() or getattr(kpdf, "name", "PDF")) +
                          (f", pages {kpages.strip()}" if (kpages or "").strip() else ""), who)
    if ss.get("know_pending") == [] and ss.get("know_skipped"):
      st.info(f"🧠 All {ss.know_skipped} note(s) from that are ones you already have — nothing new to save.")
      ss.know_pending = None
    if ss.get("know_pending"):
      st.markdown(f"**{len(ss.know_pending)} new note(s) found** — fix anything that's off, untick what you don't want, then save. "
                  f"<small>({ss.get('know_pending_who', '')})</small>", unsafe_allow_html=True)
      if ss.get("know_skipped"):
        st.caption(f"🧠 Left out {ss.know_skipped} note(s) you already have.")
      edited = st.data_editor(ss.know_pending, use_container_width=True, hide_index=True, num_rows="dynamic",
                              key=f"know_edit_{ss.get('know_n', 0)}",
                              column_config={"Note": st.column_config.TextColumn(width="large"),
                                             "Type": st.column_config.SelectboxColumn(options=KNOW_KINDS)})
      ks1, ks2 = st.columns(2)
      if ks1.button("💾 Save these notes", type="primary", use_container_width=True):
        n_saved = 0
        _have = {_note_key(e.get("rule")) for e in knowledge_entries()}
        for i_, row in enumerate(edited or []):
          if not row.get("Keep") or not str(row.get("Note") or "").strip() or _note_key(row.get("Note")) in _have:
            continue
          _have.add(_note_key(row.get("Note")))
          store_put("know", datetime.now().strftime("%Y%m%d%H%M%S") + f"{i_:03d}",
                    {"topic": str(row.get("Topic") or "General").strip(), "type": row.get("Type") or "Rule of thumb",
                     "applies_to": str(row.get("Applies to") or "All").strip(), "rule": str(row.get("Note")).strip(),
                     "source": ss.get("know_pending_src") or "", "added": datetime.now().strftime("%Y-%m-%d"),
                     "tech": ss.get("tech_user") or ""})
          n_saved += 1
        ss.know_pending = None
        ss.know_n = ss.get("know_n", 0) + 1   # empty the photo box
        queue_update(toast=f"Saved {n_saved} note(s) to shop knowledge")
      if ks2.button("✖️ Throw these away", use_container_width=True):
        ss.know_pending = None
        st.rerun()

  # ---- add one by hand ----
  with st.expander("✍️ Add a note by hand"):
    with st.form("know_manual", clear_on_submit=True):
      h1, h2, h3 = st.columns(3)
      m_topic = h1.text_input("Topic", placeholder="e.g. Secondary ignition")
      m_type = h2.selectbox("Type", KNOW_KINDS)
      m_app = h3.text_input("Applies to", value="All", placeholder="e.g. GM 3.6L, COP, Toyota")
      m_rule = st.text_area("Note", placeholder="e.g. Burn time at hot idle on COP is usually about 1.2–1.6 ms; "
                                                "under 1 ms points to a lean cylinder or high secondary resistance.")
      m_src = st.text_input("Source (optional)", placeholder="e.g. my own experience, a class, a book")
      if st.form_submit_button("💾 Save note") and m_rule.strip():
        if _note_key(m_rule) in {_note_key(e.get("rule")) for e in knowledge_entries()}:
          st.info("You already have that exact note — nothing saved.")
        else:
          store_put("know", datetime.now().strftime("%Y%m%d%H%M%S%f"),
                    {"topic": m_topic.strip() or "General", "type": m_type, "applies_to": m_app.strip() or "All",
                     "rule": m_rule.strip(), "source": m_src.strip(), "added": datetime.now().strftime("%Y-%m-%d"),
                     "tech": ss.get("tech_user") or ""})
          queue_update(toast="Note saved")

  # ---- what the AI will use on THIS car ----
  if entries and (ss.vehicle_info or current_codes()):
    used = knowledge_for_job()
    with st.expander(f"🎯 Notes the AI will use on this job ({len(used)})"):
      for e in used:
        st.markdown(f"- **{e.get('topic')}** · {e.get('applies_to') or 'All'} — {e.get('rule')}")

  # ---- browse / search / delete ----
  st.markdown(f"**All notes ({len(entries)})**")
  if not entries:
    st.info("No notes yet. Add some from book pages or by hand above.")
  else:
    q = st.text_input("🔎 Search notes", key="know_q", placeholder="e.g. intermittent stall when warm, Honda · burn time · injector")
    shown_e = [e for e in entries if not q.strip() or q.strip().lower() in
               f"{e.get('topic')} {e.get('rule')} {e.get('applies_to')} {e.get('source')}".lower()]
    if q.strip():   # 🧠 also find notes that mean the same thing in different words
      sem = meaning_scores(q, "know", [(e["_id"], note_text(e)) for e in entries])
      if sem:
        top = max(sem.values())
        extra_hits = [e for e in sorted(entries, key=lambda e: -sem.get(e["_id"], 0))
                      if e not in shown_e and sem.get(e["_id"], 0) >= top - 0.1][:15]
        shown_e = shown_e + extra_hits
        st.caption(f"🧠 Searching by meaning too — {len(extra_hits)} note(s) found that use different words.")
    topics = {}
    for e in shown_e:
      topics.setdefault(e.get("topic") or "General", []).append(e)
    for tp, es in sorted(topics.items()):
      with st.expander(f"{tp} ({len(es)})", expanded=bool(q.strip())):
        for e in es:
          r1, r2 = st.columns([8, 1])
          r1.markdown(f"**{e.get('type', '')}** · {e.get('applies_to') or 'All'} — {e.get('rule', '')}  \n"
                      f"<small>{e.get('source') or ''}{' · ' if e.get('source') else ''}{e.get('added', '')}"
                      f"{(' · ' + e['tech']) if e.get('tech') else ''}</small>", unsafe_allow_html=True)
          if r2.button("🗑️", key=f"delk_{e['_id']}", help="Delete this note"):
            store_delete("know", e["_id"])
            st.rerun()
    kx1, kx2 = st.columns(2)
    with kx1:
      st.download_button("⬇️ Export notes", data=json.dumps([{k: v for k, v in e.items() if k != "_id"} for e in entries], indent=1),
                         file_name=f"shop_knowledge_{datetime.now():%Y%m%d}.json", mime="application/json")
  with st.expander("⬆️ Import notes from a file"):
    up = st.file_uploader("Notes file (.json from Export)", type=["json"], key=f"know_imp_{ss.get('know_n', 0)}")
    if up and st.button("Import"):
      try:
        items = json.loads(up.getvalue().decode("utf-8"))
        n_ = 0
        for i_, x in enumerate(items if isinstance(items, list) else []):
          if isinstance(x, dict) and str(x.get("rule") or "").strip():
            store_put("know", datetime.now().strftime("%Y%m%d%H%M%S") + f"i{i_:04d}",
                      {k: x.get(k, "") for k in ("topic", "type", "applies_to", "rule", "source", "added", "tech")})
            n_ += 1
        ss.know_n = ss.get("know_n", 0) + 1
        queue_update(toast=f"Imported {n_} note(s)")
      except (ValueError, UnicodeDecodeError):
        st.error("That file isn't a notes export.")


# 💬 The chat front screen (shown on 💬 Chat — see _quick_box)
with _quick_box, guard("Chat"):
  chat_home()


# ========================================================
# --- AUTOSAVE: the current car is saved after every change ---
# ========================================================
with guard("Autosave"):
  autosave_job()
