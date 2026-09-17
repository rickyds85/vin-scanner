import streamlit as st
import requests

st.title("🚗 VIN Scanner & Decoder")

# 1. Camera Input
photo = st.camera_input("Take a photo of the VIN or barcode")

if photo:
    st.image(photo, caption="Captured Image", use_container_width=True)

st.write("---")

# 2. VIN Lookup
vin = st.text_input("Enter 17-digit VIN manually:", max_chars=17)

if st.button("Decode VIN") and vin:
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/{vin}?format=json"
    response = requests.get(url).json()
    
    details = {}
    for item in response.get("Results", []):
        if item["Value"] and item["Variable"] in [
            "Model Year", "Make", "Model", "Displacement (L)", 
            "Engine Number of Cylinders", "Fuel Type - Primary", 
            "Drive Type", "Vehicle Type"
        ]:
            details[item["Variable"]] = item["Value"]
            
    if details:
        st.subheader("Vehicle Specifications")
        for key, val in details.items():
            st.write(f"**{key}:** {val}")
    else:
        st.error("Could not find vehicle details. Check the VIN and try again.")
