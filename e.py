import streamlit as st
from google.cloud import vision
from google.oauth2 import service_account
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from cryptography.hazmat.primitives import serialization
from PIL import Image
import io
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import random
import string

# Streamlit configuration
st.set_page_config(page_title="Dish Recognition App", layout="wide")

# Custom CSS
st.markdown("""
    <style>
    .main { background: linear-gradient(to bottom, #1e1e2f, #2a2a3d); color: #e0e0e0; }
    .stButton>button { background-color: #4CAF50; color: white; border-radius: 10px; }
    .stFileUploader { border: 2px dashed #4CAF50; padding: 10px; border-radius: 10px; }
    h1, h2, h3 { color: #4CAF50; font-family: 'Arial', sans-serif; }
    .stDataFrame { border: 1px solid #4CAF50; border-radius: 10px; }
    .game-box {
        position: fixed;
        bottom: 20px;
        right: 20px;
        background: linear-gradient(to bottom, #4B0082, #8A2BE2);
        color: #e0e0e0;
        padding: 15px;
        border-radius: 15px;
        box-shadow: 0 0 15px #BA55D3;
        z-index: 1000;
        font-family: 'Cinzel', serif;
    }
    .word-search-button {
        width: 40px;
        height: 40px;
        margin: 2px;
        font-size: 16px;
        border-radius: 5px;
        border: 1px solid #4CAF50;
        background-color: #2a2a3d;
        color: #e0e0e0;
    }
    .word-search-button.found {
        background-color: #4CAF50;
        color: white;
    }
    .word-search-button.selected {
        background-color: #BA55D3;
        color: white;
    }
    .word-search-button.hint {
        background-color: #FFD700;
        color: #1e1e2f;
    }
    </style>
""", unsafe_allow_html=True)

# Initialize Streamlit app
st.title("🍽️ Dish Recognition and Menu Matching")

# Validate PEM key
def validate_pem_key(key_str, key_name):
    try:
        key_str = key_str.strip().replace('\r\n', '\n')
        if not key_str.startswith("-----BEGIN PRIVATE KEY-----"):
            st.error(f"{key_name} does not start with '-----BEGIN PRIVATE KEY-----'")
            return False
        if not key_str.endswith("-----END PRIVATE KEY-----"):
            st.error(f"{key_name} does not end with '-----END PRIVATE KEY-----'")
            return False
        serialization.load_pem_private_key(key_str.encode('utf-8'), password=None)
        return True
    except Exception as e:
        st.error(f"Invalid PEM key for {key_name}: {str(e)}")
        return False

# Initialize APIs
try:
    if not all(key in st.secrets for key in ["GOOGLE_CLOUD_VISION_CREDENTIALS", "FIREBASE_CREDENTIALS", "GEMINI"]):
        st.error("Missing sections in secrets.toml")
        st.stop()
    vision_credentials_dict = dict(st.secrets["GOOGLE_CLOUD_VISION_CREDENTIALS"])
    required_keys = ["type", "project_id", "private_key_id", "private_key", "client_email", "client_id", "auth_uri", "token_uri", "universe_domain"]
    missing_keys = [key for key in required_keys if key not in vision_credentials_dict]
    if missing_keys:
        st.error(f"Invalid Google Cloud Vision credentials. Missing keys: {', '.join(missing_keys)}.")
        st.stop()
    if not validate_pem_key(vision_credentials_dict["private_key"], "Google Cloud Vision"):
        st.stop()
    vision_credentials = service_account.Credentials.from_service_account_info(vision_credentials_dict)
    vision_client = vision.ImageAnnotatorClient(credentials=vision_credentials)
    firebase_credentials_dict = dict(st.secrets["FIREBASE_CREDENTIALS"])
    missing_keys = [key for key in required_keys if key not in firebase_credentials_dict]
    if missing_keys:
        st.error(f"Invalid Firebase credentials. Missing keys: {', '.join(missing_keys)}.")
        st.stop()
    if not validate_pem_key(firebase_credentials_dict["private_key"], "Firebase"):
        st.stop()
    if not firebase_admin._apps:
        firebase_cred = credentials.Certificate(firebase_credentials_dict)
        firebase_admin.initialize_app(firebase_cred)
    db = firestore.client()
    gemini_api_key = st.secrets["GEMINI"]["api_key"]
    if not gemini_api_key:
        st.error("Gemini API key is empty in secrets.toml.")
        st.stop()
    genai.configure(api_key=gemini_api_key)
    gemini_model = genai.GenerativeModel("gemini-1.5-flash")
except Exception as e:
    st.error(f"Error initializing APIs: {str(e)}")
    st.stop()

# ==============================================
# NEW FEATURE: AI POWERED RECIPE GENERATOR
# ==============================================

st.sidebar.header("🥣 Recipe Generator")
with st.sidebar.expander("Generate a Recipe"):
    dish_input = st.text_input("Enter Dish Name", "Pasta")
    generate_btn = st.button("Generate Recipe")

    if generate_btn and dish_input:
        with st.spinner("Generating recipe..."):
            try:
                recipe_prompt = f"""
                Generate a detailed recipe for {dish_input}. Include:
                - Ingredients list
                - Step-by-step preparation
                - Cooking time
                - Dietary tags (e.g. Vegan, Gluten-Free, Keto, etc)
                Format output in markdown.
                """
                recipe_response = gemini_model.generate_content(recipe_prompt)
                recipe_text = recipe_response.text.strip()
                st.markdown(recipe_text)
            except Exception as e:
                st.error(f"Error generating recipe: {str(e)}")

# The rest of your code remains exactly same (unchanged)
# Word Search, Dish Recognition, Menu Matching, Customization, etc continue as above...
