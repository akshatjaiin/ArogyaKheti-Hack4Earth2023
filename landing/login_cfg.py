import googlemaps
import os
from dotenv import load_dotenv

# Load API key from .env file
load_dotenv()
google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY")

# Initialize Google Maps client
gmaps = googlemaps.Client(key=google_maps_api_key)

def GetAddressDetails(pincode):
    geocode_result = gmaps.geocode(str(pincode))
    if geocode_result:
        address_components = geocode_result[0]["address_components"]
        state, country = None, None
        for component in address_components:
            if "administrative_area_level_1" in component["types"]:
                state = component["long_name"]
            if "country" in component["types"]:
                country = component["long_name"]
        return state, country
    return None, None

def GetCoordinates(pincode):
    geocode_result = gmaps.geocode(str(pincode))
    if geocode_result:
        location = geocode_result[0]["geometry"]["location"]
        return location["lat"], location["lng"]
    return None, None

# Example usage
pincode = "110001"  # Example: New Delhi Pincode
state, country = GetAddressDetails(pincode)
lat, lon = GetCoordinates(pincode)

print(f"State: {state}, Country: {country}")
print(f"Latitude: {lat}, Longitude: {lon}")
