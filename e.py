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
st.title("\U0001F37D️ Visual Menu Challenge & Recommendation Platform")

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
def fetch_challenge_entries():
    return [doc.to_dict() | {"id": doc.id} for doc in db.collection("visual_challenges").stream()]

def calculate_score(entry):
    base_score = entry.get("views", 0) + entry.get("likes", 0) * 2 + entry.get("orders", 0) * 3
    if entry.get("trendy"): base_score += 5
    if entry.get("diet_match"): base_score += 3
    return base_score

# Sidebar Preferences
st.sidebar.header("Customer Preferences")
dietary = st.sidebar.multiselect("Diet", ["Vegan", "Vegetarian", "Keto", "Gluten-Free", "Paleo"], default=[])
allergies = st.sidebar.multiselect("Allergies", ["Nut-Free", "Shellfish-Free", "Soy-Free", "Dairy-Free"], default=[])

# TABS
tab1, tab2, tab3, tab4, tab5 = st.tabs(["\U0001F4F7 AI Dish Detection", "\U0001F3AF Personalized Menu", "\u2699\ufe0f Custom Filters", "\U0001F3C5 Visual Menu Challenge", "\U0001F4CA Leaderboard"])

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
        dish_guess = genai.GenerativeModel("gemini-1.5-flash").generate_content(
            f"Predict the most likely dish from these labels: {labels}"
        ).text.strip()

        st.success(f"Predicted Dish: {dish_guess}")

# TAB 2: Personalized Menu Recommendations
with tab2:
    st.header("Personalized AI Menu")
    menu = fetch_menu()
    menu_text = "\n".join([
        f"- {item['name']}: {item.get('description', '')} ({', '.join(item.get('dietary_tags', []))})"
        for item in menu
    ])
    user_profile = f"Diet: {dietary}, Allergies: {allergies}"
    prompt = f"Given user profile ({user_profile}) recommend 5 dishes:\n{menu_text}"
    ai_result = gemini_model.generate_content(prompt).text.strip()
    st.markdown(ai_result)

# TAB 3: Custom Filtering Options
with tab3:
    st.header("Custom Menu Filters")
    portion = st.selectbox("Portion Size", ["Regular", "Small", "Large"])
    ingredient_swap = st.text_input("Ingredient Swap")

    filtered_menu = []
    for item in menu:
        tags = item.get("dietary_tags", [])
        ingredients = item.get("ingredients", [])
        if (not dietary or any(d in tags for d in dietary)) and \
           (not allergies or all(a not in ingredients for a in allergies)):
            item_copy = item.copy()
            item_copy["portion_size"] = portion
            item_copy["ingredient_swap"] = ingredient_swap
            filtered_menu.append(item_copy)
    st.write(pd.DataFrame(filtered_menu))

# TAB 4: Staff Gamification Upload (Upgraded UI)
with tab4:
    st.header("\U0001F680 Participate in the Visual Menu Challenge")
    st.markdown("Encourage your creativity and plating skills. Upload your best dish photos, get votes, and climb the leaderboard!")

    with st.form("challenge_form"):
        col1, col2 = st.columns(2)
        with col1:
            staff_name = st.text_input("\U0001F469‍‍\U0001F373 Your Name")
            dish_name = st.text_input("🍽️ Dish Name")
            plating_style = st.selectbox("\U0001F3A8 Plating Style", ["Minimalist", "Classic", "Fusion", "Artistic", "Rustic"])
        with col2:
            ingredients = st.text_area("📝 Ingredients (comma separated)")
            challenge_image = st.file_uploader("📸 Upload Dish Photo", type=["jpg", "jpeg", "png"])

        trendy = st.checkbox("🔥 Trending Dish?")
        diet_match = st.checkbox("🥗 Matches Dietary Preferences?")

        submitted = st.form_submit_button("✅ Submit Entry")

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
            st.success("\U0001F389 Dish submitted successfully!")

# TAB 5: Leaderboard & Customer Feedback (Fully Upgraded UI)
with tab5:
    st.header("\U0001F3C6 Visual Menu Leaderboard")

    entries = fetch_challenge_entries()

    if entries:
        leaderboard = sorted(entries, key=lambda e: calculate_score(e), reverse=True)

        for i, entry in enumerate(leaderboard):
            with st.container():
                st.subheader(f"#{i+1} - {entry['dish']} by {entry['staff']}")
                col1, col2 = st.columns([1, 2])
                with col1:
                    st.image("https://via.placeholder.com/250x200.png?text=Dish+Image", caption="Dish Image")

                with col2:
                    st.write(f"🎨 Style: {entry['style']}")
                    st.write(f"📝 Ingredients: {', '.join(entry['ingredients'])}")
                    st.write(f"🔥 Current Score: **{calculate_score(entry)} pts**")

                    like_col, view_col, order_col = st.columns(3)

                    with like_col:
                        if st.button(f"❤️ Like ({entry['likes']})", key=f"like_{entry['id']}"):
                            db.collection("visual_challenges").document(entry['id']).update({"likes": entry['likes'] + 1})
                            st.experimental_rerun()
                    with view_col:
                        if st.button(f"👀 View ({entry['views']})", key=f"view_{entry['id']}"):
                            db.collection("visual_challenges").document(entry['id']).update({"views": entry['views'] + 1})
                            st.experimental_rerun()
                    with order_col:
                        if st.button(f"🛒 Order ({entry['orders']})", key=f"order_{entry['id']}"):
                            db.collection("visual_challenges").document(entry['id']).update({"orders": entry['orders'] + 1})
                            st.experimental_rerun()
    else:
        st.warning("🚫 No entries submitted yet. Encourage your staff to participate!")
