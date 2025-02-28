import requests
import pandas as pd
from sklearn.preprocessing import LabelEncoder
import google.generativeai as palm
import os
from dotenv import load_dotenv
import base64
from google import genai
from google.genai import types

# Load environment variables
load_dotenv()

# Load dataset
fertilizerdata = pd.read_csv("datasets/Fertilizer Prediction.csv") 

# API Keys from .env (Ensure they are set)
weather_api_key = os.environ.get('WEATHER_API_KEY')
newsapi_api_key = os.environ.get('NEWSAPI_API_KEY')
palm_api_key = os.environ.get('GOOGLE_GEMINI_API_KEY')
govdata_api_key = os.environ.get('GOVDATA_API_KEY')

# 🟢 Get Weather Details
def getWeatherDetails(coords):
    try:
        lat, lon = coords[0], coords[1]
        weather_url = f"http://api.weatherapi.com/v1/current.json?key={weather_api_key}&q={lat},{lon}&aqi=no"
        response = requests.get(weather_url, timeout=10)
        response.raise_for_status()  # Raise HTTP errors (e.g., 404, 500)

        data = response.json()
        if "error" in data:
            print(f"Error: {data['error']['message']}")
            return None
        
        return [
            data["current"]["condition"]["text"], 
            data["current"]["temp_c"], 
            data["current"]["humidity"], 
            data["current"]["wind_kph"], 
            data["current"]["pressure_mb"]
        ]

    except requests.exceptions.RequestException as e:
        print(f"Network Error in getWeatherDetails: {e}")
        return None
    except KeyError:
        print("Unexpected response format in getWeatherDetails.")
        return None

# 🟢 Get Agriculture News
def getAgroNews():
    try:
        newsapi_url = f"https://newsapi.org/v2/everything?q=agriculture&apiKey={newsapi_api_key}"
        response = requests.get(newsapi_url, timeout=10)
        response.raise_for_status()

        data = response.json()
        return data.get("articles", [])[:20]

    except requests.exceptions.RequestException as e:
        print(f"Network Error in getAgroNews: {e}")
        return []
    except KeyError:
        print("Unexpected response format in getAgroNews.")
        return []

# 🟢 Fertilizer Recommendation
def getFertilizerRecommendation(model, nitrogen, phosphorus, potassium, temp, humidity, moisture, soil_type, crop):
    try:
        le_soil = LabelEncoder()
        fertilizerdata['Soil Type'] = le_soil.fit_transform(fertilizerdata['Soil Type'])
        le_crop = LabelEncoder()
        fertilizerdata['Crop Type'] = le_crop.fit_transform(fertilizerdata['Crop Type'])

        soil_enc = le_soil.transform([str(soil_type)])[0]
        crop_enc = le_crop.transform([crop])[0]
        user_input = [[temp, humidity, moisture, soil_enc, crop_enc, nitrogen, potassium, phosphorus]]
        
        prediction = model.predict(user_input)
        return prediction[0]

    except Exception as e:
        print(f"Error in getFertilizerRecommendation: {e}")
        return None

# 🟢 Get Market Prices from Government API
def getMarketPricesAllStates():
    states = ["Kerala", "Uttrakhand", "Uttar Pradesh", "Rajasthan", "Nagaland", "Gujarat", "Maharashtra", "Tripura", "Punjab", "Bihar", "Telangana", "Meghalaya"]
    final_list = []

    for state in states:
        try:
            state = state.replace(" ", "+")
            govdata_url = f"https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070?api-key={govdata_api_key}&format=json&filters%5Bstate%5D={state}"
            response = requests.get(govdata_url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            final_list.extend(data.get("records", []))

        except requests.exceptions.RequestException as e:
            print(f"Network Error in getMarketPricesAllStates ({state}): {e}")
        except KeyError:
            print(f"Unexpected response format for state: {state}")

    return final_list

# 🟢 Get AI Response from Google Gemini
def GetResponse(query):
    try:
        client = genai.Client(api_key=os.environ.get('GOOGLE_GEMINI_API_KEY'))
        model = "gemini-2.0-flash"
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=query)],
            ),
        ]
        generate_content_config = types.GenerateContentConfig(
            temperature=1,
            top_p=0.95,
            top_k=40,
            max_output_tokens=8192,
            response_mime_type="text/plain",
            system_instruction="You are a farmer assistance helper. Help with agriculture practices.",
        )
        
        complete_response = ""
        for chunk in client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=generate_content_config,
        ):
            if chunk.text:
                complete_response += chunk.text
        return complete_response

    except Exception as e:
        print(f"Error in GetResponse: {e}")
        return "Sorry, I couldn't process your request."

