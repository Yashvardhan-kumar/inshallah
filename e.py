import streamlit as st
from google.cloud import vision
from google.oauth2 import service_account
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from PIL import Image
import io
import pandas as pd
import random
import time

# Streamlit config
st.set_page_config(page_title="Next-Gen Dish Recommender + Gamification", layout="wide")
st.title("🍽️ Next-Gen AI Menu + Gamified Recommendation Engine")

# Credentials Initialization (use your secrets.toml)
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
def fetch_dishes():
    return [doc.to_dict() | {"id": doc.id} for doc in db.collection("visual_challenges").stream()]

def calculate_score(entry):
    base = entry.get("views", 0) + entry.get("likes", 0) * 2 + entry.get("orders", 0) * 3
    if entry.get("trendy"): base += 5
    if entry.get("diet_match"): base += 3
    rating_score = entry.get("avg_rating", 0) * 5  # Weight customer ratings heavily
    favorites = entry.get("favorites", 0) * 2
    return base + rating_score + favorites

# Sidebar Preferences
st.sidebar.header("Customer Preferences")
dietary = st.sidebar.multiselect("Diet", ["Vegan", "Vegetarian", "Keto", "Gluten-Free", "Paleo"], default=[])
allergies = st.sidebar.multiselect("Allergies", ["Nut-Free", "Shellfish-Free", "Soy-Free", "Dairy-Free"], default=[])

# TABS
tab1, tab2, tab3, tab4 = st.tabs(["📷 AI Dish Detection", "🎯 Personalized Menu", "🏅 Customer Feedback Loop", "📊 Leaderboard & Rewards"])

# TAB 1: AI Dish Detection
with tab1:
    st.header("Visual Dish Detection (AI + Vision API)")
    uploaded_file = st.file_uploader("Upload Food Image", type=["jpg", "jpeg", "png"])
    if uploaded_file:
        image = Image.open(uploaded_file)
        st.image(image, caption="Uploaded", use_column_width=True)
        img_bytes = io.BytesIO()
        image.save(img_bytes, format=image.format)
        content = img_bytes.getvalue()

        response = vision_client.label_detection(image=vision.Image(content=content))
        labels = [label.description for label in response.label_annotations][:5]
        dish_guess = gemini_model.generate_content(
            f"Predict the most likely dish from these labels: {labels}"
        ).text.strip()

        st.success(f"Predicted Dish: {dish_guess}")

# TAB 2: Personalized Menu Recommendations
with tab2:
    st.header("Personalized AI Menu")

    menu = fetch_menu()
    dishes = fetch_dishes()

    menu_text = "\n".join([
        f"- {item['name']}: {item.get('description', '')} ({', '.join(item.get('dietary_tags', []))})"
        for item in menu
    ])

    user_profile = f"Diet: {dietary}, Allergies: {allergies}"

    # AI-based menu recommendation (from static menu)
    prompt = f"Given user profile ({user_profile}) recommend 5 dishes:\n{menu_text}"
    ai_result = gemini_model.generate_content(prompt).text.strip()
    st.markdown(ai_result)

    st.subheader("🔥 Top Rated Visual Dishes")
    # Show top-rated visual dishes
    sorted_dishes = sorted(dishes, key=lambda e: calculate_score(e), reverse=True)
    for entry in sorted_dishes[:5]:
        st.write(f"⭐ {entry['dish']} by {entry['staff']} — Avg Rating: {entry.get('avg_rating', 0):.1f}")

# TAB 3: Customer Feedback Loop (Gamified)
with tab3:
    st.header("Customer Interaction & Feedback")

    entries = fetch_dishes()

    for entry in entries:
        with st.container():
            st.subheader(f"{entry['dish']} by {entry['staff']}")
            st.write(f"Style: {entry['style']}")
            st.write(f"Ingredients: {', '.join(entry['ingredients'])}")
            st.write(f"Total Views: {entry.get('views',0)}, Likes: {entry.get('likes',0)}, Orders: {entry.get('orders',0)}")

            col1, col2, col3, col4 = st.columns(4)

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

            with col4:
                if st.button(f"⭐ Favorite ({entry.get('favorites',0)})", key=f"fav_{entry['id']}"):
                    db.collection("visual_challenges").document(entry['id']).update(
                        {"favorites": entry.get("favorites", 0) + 1}
                    )
                    st.experimental_rerun()

            # Customer Ratings
            rating = st.slider("Rate this dish (1-5)", 1, 5, key=f"rating_{entry['id']}")
            if st.button("Submit Rating", key=f"submit_rating_{entry['id']}"):
                prev_sum = entry.get("rating_sum", 0)
                prev_count = entry.get("rating_count", 0)
                new_sum = prev_sum + rating
                new_count = prev_count + 1
                avg_rating = new_sum / new_count

                db.collection("visual_challenges").document(entry['id']).update({
                    "rating_sum": new_sum,
                    "rating_count": new_count,
                    "avg_rating": avg_rating
                })
                st.success("Thank you for rating!")
                st.experimental_rerun()

# TAB 4: Leaderboard & Rewards
with tab4:
    st.header("Leaderboard & Rewards System")

    entries = fetch_dishes()
    leaderboard = sorted(entries, key=lambda e: calculate_score(e), reverse=True)

    st.subheader("🏆 Top Weekly Dishes")
    for i, entry in enumerate(leaderboard[:5]):
        st.write(
            f"**#{i+1} {entry['dish']} by {entry['staff']}** → {calculate_score(entry)} pts "
            f"(⭐ {entry.get('avg_rating',0):.1f} | ❤️ {entry.get('likes',0)} | 🛒 {entry.get('orders',0)} | 👀 {entry.get('views',0)})"
        )

    st.markdown("---")
    st.success("🎁 Monthly winners receive bonus prizes for highest customer scores!")

