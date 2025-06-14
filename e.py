import streamlit as st
from google.cloud import vision
from google.oauth2 import service_account
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from PIL import Image
import io
import pandas as pd
import time

# Streamlit config
st.set_page_config(page_title="Next-Gen Dish Recommender + Gamification", layout="wide")
st.title("\U0001F37D\ufe0f Dish Recognition and Menu Matching")

# Credentials Initialization
try:
    vision_credentials_dict = dict(st.secrets["GOOGLE_CLOUD_VISION_CREDENTIALS"])
    vision_credentials = service_account.Credentials.from_service_account_info(vision_credentials_dict)
    vision_client = vision.ImageAnnotatorClient(credentials=vision_credentials)

    firebase_credentials_dict = dict(st.secrets["FIREBASE_CREDENTIALS"])
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(firebase_credentials_dict))
    db = firestore.client()

    gemini_api_key = st.secrets["GEMINI"]["api_key"]
    genai.configure(api_key=gemini_api_key)
    gemini_model = genai.GenerativeModel("gemini-1.5-flash")

except Exception as e:
    st.error(f"Initialization failed: {e}")
    st.stop()

# Utility Functions
@st.cache_data(ttl=300)
def fetch_menu():
    return [doc.to_dict() | {"id": doc.id} for doc in db.collection("menu").stream()]

@st.cache_data(ttl=60)
def fetch_challenge_entries():
    return [doc.to_dict() | {"id": doc.id} for doc in db.collection("visual_challenges").stream()]

def calculate_score(entry):
    base_score = entry.get("views", 0) + entry.get("likes", 0) * 2 + entry.get("orders", 0) * 3
    if entry.get("trendy"): base_score += 5
    if entry.get("diet_match"): base_score += 3
    return base_score

# Sidebar Preferences
st.sidebar.header("Dietary Preferences")
dietary = st.sidebar.multiselect("Select Dietary Preferences", ["Vegan", "Vegetarian", "Keto", "Gluten-Free", "Paleo"], default=[])

# MAIN MENU NAVIGATION
menu_choice = st.sidebar.radio("", ["Dish Recognition", "Menu Exploration", "Gamification Challenge", "Leaderboard"])

# Dish Recognition Page
if menu_choice == "Dish Recognition":
    st.header("Upload and Match Dish")
    uploaded_file = st.file_uploader("Upload an image of the dish (JPG or PNG)", type=["jpg", "jpeg", "png"])
    if uploaded_file:
        image = Image.open(uploaded_file)
        st.image(image, caption="Uploaded", use_column_width=True)
        img_bytes = io.BytesIO()
        image.save(img_bytes, format=image.format)
        content = img_bytes.getvalue()

        response = vision_client.label_detection(image=vision.Image(content=content))
        labels = [label.description for label in response.label_annotations][:5]
        dish_guess = genai.GenerativeModel("gemini-1.5-flash").generate_content(
            f"Predict the most likely dish from these labels: {labels}"
        ).text.strip()

        st.success(f"Predicted Dish: {dish_guess}")

# Menu Exploration Page
elif menu_choice == "Menu Exploration":
    st.header("Personalized Menu Suggestions")
    menu = fetch_menu()
    menu_text = "\n".join([
        f"- {item['name']}: {item.get('description', '')} ({', '.join(item.get('dietary_tags', []))})"
        for item in menu
    ])
    user_profile = f"Diet: {dietary}"
    prompt = f"Given user profile ({user_profile}) recommend 5 dishes:\n{menu_text}"
    ai_result = gemini_model.generate_content(prompt).text.strip()
    st.markdown(ai_result)

# Gamification Upload Page
elif menu_choice == "Gamification Challenge":
    st.header("\U0001F947 Submit Your Visual Menu Challenge")

    with st.form("challenge_form"):
        staff_name = st.text_input("Staff Name")
        dish_name = st.text_input("Dish Name")
        ingredients = st.text_area("Ingredients (comma separated)")
        plating_style = st.text_input("Plating Style")
        challenge_image = st.file_uploader("Dish Photo", type=["jpg", "png"])
        trendy = st.checkbox("Matches current food trends")
        diet_match = st.checkbox("Matches dietary preferences")
        
        submitted = st.form_submit_button("Submit Dish")

        if submitted and challenge_image:
            img_bytes = challenge_image.read()
            img_blob = db.collection("visual_challenges").document()
            img_blob.set({
                "staff": staff_name,
                "dish": dish_name,
                "ingredients": [i.strip() for i in ingredients.split(",")],
                "style": plating_style,
                "trendy": trendy,
                "diet_match": diet_match,
                "timestamp": time.time(),
                "views": 0,
                "likes": 0,
                "orders": 0
            })
            st.success("Dish submitted successfully!")

# Leaderboard Page
elif menu_choice == "Leaderboard":
    st.header("\U0001F3C6 Live Leaderboard & Voting")

    entries = fetch_challenge_entries()
    for entry in entries:
        with st.container():
            st.subheader(f"{entry['dish']} by {entry['staff']}")
            st.write(f"Style: {entry['style']}")
            st.write(f"Ingredients: {', '.join(entry['ingredients'])}")

            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button(f"❤️ Like ({entry['likes']})", key=f"like_{entry['id']}"):
                    db.collection("visual_challenges").document(entry['id']).update({"likes": entry['likes'] + 1})
                    st.experimental_rerun()
            with col2:
                if st.button(f"👀 View ({entry['views']})", key=f"view_{entry['id']}"):
                    db.collection("visual_challenges").document(entry['id']).update({"views": entry['views'] + 1})
                    st.experimental_rerun()
            with col3:
                if st.button(f"🛒 Order ({entry['orders']})", key=f"order_{entry['id']}"):
                    db.collection("visual_challenges").document(entry['id']).update({"orders": entry['orders'] + 1})
                    st.experimental_rerun()

    st.subheader("Top Scoring Dishes")
    leaderboard = sorted(entries, key=lambda e: calculate_score(e), reverse=True)
    for i, entry in enumerate(leaderboard[:5]):
        st.write(f"**#{i+1} - {entry['dish']} by {entry['staff']} → {calculate_score(entry)} pts**")
