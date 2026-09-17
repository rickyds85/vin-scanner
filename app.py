import re
from PIL import Image
import requests
import streamlit as st
import zxingcpp

st.title("🚗 VIN Scanner & Decoder")


def decode_vin(vin_code):
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


# 1. Camera Input
photo = st.camera_input("Snap a photo of the door jamb barcode")

found_vin = ""

if photo:
  st.image(photo, caption="Captured Image", use_container_width=True)

  # Read barcode directly from the photo
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
    st.warning(
        "No barcode detected. Center the barcode on the door sticker and ensure"
        " it is in focus."
    )

st.write("---")

# 2. VIN Lookup (Auto-fills if barcode found)
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
elif not active_vin and st.button("Decode VIN"):
  st.warning("Please take a photo of a barcode or enter a 17-digit VIN.")
