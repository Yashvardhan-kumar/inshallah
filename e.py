import streamlit as st
from google.cloud import vision
from google.oauth2 import service_account
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from PIL import Image
import io
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import random
import string

# Streamlit config
st.set_page_config(page_title="Next-Gen Dish Recommender", layout="wide")
st.title("🍽️ Next-Gen Dish Recommender")

# Credentials & API initialization
try:
    if not all(key in st.secrets for key in ["GOOGLE_CLOUD_VISION_CREDENTIALS", "FIREBASE_CREDENTIALS", "GEMINI"]):
        st.error("Missing credentials in secrets.toml")
        st.stop()

    # Google Vision Client
    vision_credentials_dict = dict(st.secrets["GOOGLE_CLOUD_VISION_CREDENTIALS"])
    vision_credentials = service_account.Credentials.from_service_account_info(vision_credentials_dict)
    vision_client = vision.ImageAnnotatorClient(credentials=vision_credentials)

    # Firebase Client
    firebase_credentials_dict = dict(st.secrets["FIREBASE_CREDENTIALS"])
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(firebase_credentials_dict))
    db = firestore.client()

    # Gemini Client
    gemini_api_key = st.secrets["GEMINI"]["api_key"]
    genai.configure(api_key=gemini_api_key)
    gemini_model = genai.GenerativeModel("gemini-1.5-flash")

except Exception as e:
    st.error(f"Initialization failed: {e}")
    st.stop()

# Dietary Preferences + Allergies
st.sidebar.header("Your Preferences")
dietary_options = ["Vegan", "Vegetarian", "Gluten-Free", "Keto", "Dairy-Free", "Low-Sugar", "No Preference"]
selected_diet = st.sidebar.multiselect("Dietary Preferences", dietary_options, default=["No Preference"])

allergy_options = ["Nut-Free", "Shellfish-Free", "Soy-Free", "Egg-Free", "Gluten-Free", "No Allergy"]
selected_allergies = st.sidebar.multiselect("Allergies", allergy_options, default=["No Allergy"])

# --- DATABASE FUNCTIONS ---
@st.cache_data(ttl=3600)
def fetch_menu():
    try:
        menu_ref = db.collection("menu")
        docs = menu_ref.stream()
        return [{"id": doc.id, **doc.to_dict()} for doc in docs]
    except Exception as e:
        st.error(f"DB Error: {e}")
        return []

# --- VISION DISH DETECTION ---
def detect_dish(image_content):
    image = vision.Image(content=image_content)
    response = vision_client.label_detection(image=image)
    labels = [label.description for label in response.label_annotations][:5]
    prompt = f"Given these labels: {labels}, predict the likely food dish:"
    response = gemini_model.generate_content(prompt)
    return response.text.strip()

# --- ADVANCED MATCHING ---
def match_dish_to_menu(dish_name, menu_items):
    menu_text = "\n".join([f"- {item['name']}: {item.get('description','')}" for item in menu_items])
    prompt = f"""
    Match the dish '{dish_name}' to this menu list:
    {menu_text}
    Return the most relevant dish name or 'No match'.
    """
    response = gemini_model.generate_content(prompt)
    match_name = response.text.strip()

    for item in menu_items:
        if match_name.lower() == item['name'].lower():
            return item, "Exact Match Found"
    return None, "No Match"

# --- PERSONALIZED RECOMMENDATION ENGINE ---
def recommend_menu(dish_name, menu_items, diet, allergies):
    menu_text = "\n".join([
        f"- {item['name']}: {item.get('description','')}, Ingredients: {', '.join(item.get('ingredients',[]))}, Tags: {', '.join(item.get('dietary_tags',[]))}" 
        for item in menu_items
    ])
    prompt = f"""
    Based on detected dish '{dish_name}', dietary preferences {diet}, allergies {allergies}, and recent food trends,
    recommend 3 personalized dishes from this menu. 
    Provide output in markdown list with name, description, tags & suggested customizations:
    {menu_text}
    """
    response = gemini_model.generate_content(prompt)
    return response.text.strip()

# --- EXAMPLE BASED SUGGESTIONS ---
def example_based_suggestions(category):
    prompt = f"""
    For the category '{category}', suggest variations with healthy alternatives like gluten-free, dairy-free, low sugar etc.
    Provide output as markdown list.
    """
    response = gemini_model.generate_content(prompt)
    return response.text.strip()

# --- CUSTOMIZATION FILTER ---
def filter_menu(menu_items, diet, allergies, portion=None, swap=None):
    filtered = []
    for item in menu_items:
        tags = item.get("dietary_tags", [])
        ingredients = item.get("ingredients", [])

        if (("No Preference" in diet) or any(d in tags for d in diet)) and \
           (("No Allergy" in allergies) or all(a not in ingredients for a in allergies)):
            item_copy = item.copy()
            if portion:
                item_copy["portion_size"] = portion
            if swap:
                item_copy["ingredient_swap"] = swap
            filtered.append(item_copy)
    return filtered

# --- HISTORY MOCKUP (to simulate user past orders) ---
user_history = random.sample(["Pizza", "Burger", "Sushi", "Curry", "Salad", "Pasta"], 3)

# --- MAIN UI TABS ---
tab1, tab2, tab3, tab4 = st.tabs(["📷 Upload Dish", "📊 Personalized Menu", "⚙️ Custom Menu", "📸 Visual Discovery"])

# TAB 1 - Upload Image
with tab1:
    st.header("Visual Dish Recognition")
    uploaded_file = st.file_uploader("Upload Food Image", type=["jpg", "jpeg", "png"])
    if uploaded_file:
        image = Image.open(uploaded_file)
        st.image(image, caption="Uploaded", use_column_width=True)
        img_bytes = io.BytesIO()
        image.save(img_bytes, format=image.format)
        img_content = img_bytes.getvalue()

        with st.spinner("Detecting Dish..."):
            dish_detected = detect_dish(img_content)
        st.success(f"Detected Dish: **{dish_detected}**")

        menu_items = fetch_menu()
        matched_item, message = match_dish_to_menu(dish_detected, menu_items)
        st.subheader("Menu Matching")
        st.write(message)
        if matched_item:
            st.write(matched_item)

        st.subheader("Personalized Recommendations")
        recommendations = recommend_menu(dish_detected, menu_items, selected_diet, selected_allergies)
        st.markdown(recommendations)

# TAB 2 - Personalized Menu
with tab2:
    st.header("Personalized Menu (Based on History)")
    st.write(f"🧾 Your previous orders: {', '.join(user_history)}")

    menu_items = fetch_menu()
    history_text = "\n".join([
        f"- {item['name']}: {item.get('description','')}, Tags: {', '.join(item.get('dietary_tags',[]))}" 
        for item in menu_items
    ])
    prompt = f"""
    Given user history ({', '.join(user_history)}), dietary: {selected_diet}, allergies: {selected_allergies}, 
    recommend 5 diverse dishes from this menu:
    {history_text}
    """
    with st.spinner("AI Generating Personalized Menu..."):
        response = gemini_model.generate_content(prompt)
    st.markdown(response.text.strip())

# TAB 3 - Fully Custom Menu
with tab3:
    st.header("Advanced Custom Filters")
    portion = st.selectbox("Portion Size", ["Regular", "Small", "Large"])
    swap = st.text_input("Ingredient Swaps (e.g. replace cheese with avocado)")

    menu_items = fetch_menu()
    filtered_menu = filter_menu(menu_items, selected_diet, selected_allergies, portion, swap)
    
    if filtered_menu:
        df = pd.DataFrame([
            {
                "Dish": item["name"],
                "Description": item.get("description", ""),
                "Ingredients": ", ".join(item.get("ingredients", [])),
                "Tags": ", ".join(item.get("dietary_tags", [])),
                "Portion": item.get("portion_size", "Regular"),
                "Ingredient Swap": item.get("ingredient_swap", "None")
            } for item in filtered_menu
        ])
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("No dishes match the filters.")

# TAB 4 - Visual Discovery with Example Suggestions
with tab4:
    st.header("Visual Discovery")
    category = st.selectbox("Pick Food Type", ["Pasta", "Dessert", "Salad", "Burger", "Soup", "Breakfast"])
    st.write(f"Showing variations for **{category}**")

    with st.spinner("Generating Variations..."):
        suggestions = example_based_suggestions(category)
    st.markdown(suggestions)
