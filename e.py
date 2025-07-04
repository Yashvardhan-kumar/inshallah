import streamlit as st
from google.cloud import vision
from google.oauth2 import service_account
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from PIL import Image, ImageEnhance
import io
import pandas as pd
import time
from fuzzywuzzy import fuzz

# Streamlit config
st.set_page_config(page_title="Next-Gen Dish Recommender + Gamification", layout="wide")
st.title("🍽️ Visual Menu Challenge & Recommendation Platform")

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

@st.cache_data(ttl=300)
def fetch_order_history(user_id):
    # Assuming user_id is stored in session state or passed; for simplicity, using a placeholder
    if not user_id:
        return []
    orders = db.collection("orders").where("user_id", "==", user_id).stream()
    return [order.to_dict() | {"id": order.id} for order in orders]

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
user_id = st.sidebar.text_input("User ID (for Order History)", value="test_user")  # Placeholder for user ID input

# TABS
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📷 AI Dish Detection", "🎯 Personalized Menu", "⚙️ Custom Filters", "🏅 Visual Menu Challenge", "📊 Leaderboard"])

# TAB 1: AI Dish Detection (Enhanced)
with tab1:
    st.header("Visual Dish Detection (AI + Vision API)")
    uploaded_file = st.file_uploader("Upload Food Image", type=["jpg", "jpeg", "png"])
    if uploaded_file:
        # Preprocess image
        image = Image.open(uploaded_file).convert("RGB")
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.3)
        enhancer = ImageEnhance.Brightness(image)
        image = enhancer.enhance(1.1)
        st.image(image, caption="Uploaded Image", use_column_width=True)
        img_bytes = io.BytesIO()
        image.save(img_bytes, format="JPEG")
        content = img_bytes.getvalue()

        # Vision API: Label detection, object localization, text detection, and properties for style
        vision_image = vision.Image(content=content)
        label_response = vision_client.label_detection(image=vision_image)
        labels = [(label.description, label.score) for label in label_response.label_annotations if label.score > 0.7]
        obj_response = vision_client.object_localization(image=vision_image)
        objects = [(obj.name, obj.score) for obj in obj_response.localized_object_annotations]
        text_response = vision_client.text_detection(image=vision_image)
        texts = [text.description.lower().strip() for text in text_response.text_annotations[1:] if text.description.strip()]
        # Detect plating style via image properties or labels
        properties_response = vision_client.image_properties(image=vision_image)
        dominant_colors = properties_response.image_properties_annotation.dominant_colors.colors
        style_indicators = [label[0].lower() for label in labels if "style" in label[0].lower() or "plating" in label[0].lower()]
        if not style_indicators:
            # Infer style from colors (e.g., vibrant colors might indicate modern plating)
            style_indicators.append("modern" if any(color.color.red > 200 or color.color.green > 200 for color in dominant_colors) else "classic")

        # Combine and filter detections
        combined_labels = [desc.lower() for desc, score in labels + objects]
        combined_labels = list(set(combined_labels + texts))
        st.write(f"Detected Labels, Objects, and Text: {combined_labels}")
        st.write(f"Detected Plating Style: {', '.join(style_indicators) if style_indicators else 'Not identified'}")

        # Check if food-related
        food_related = any(
            label.lower() in ["food", "dish", "meal"] or "food" in label.lower() or any(food_term in label.lower() for food_term in ["pizza", "burger", "pasta", "salad", "sushi"])
            for label in combined_labels
        )
        if not food_related:
            st.warning("The image doesn't appear to contain food. Please upload a food-related image.")
            st.stop()

        # Cross-reference with Firestore menu
        menu = fetch_menu()
        menu_text = "\n".join([
            f"{item['name']}: {item.get('description', '')} (Ingredients: {', '.join(item.get('ingredients', []))}; Tags: {', '.join(item.get('dietary_tags', []))})"
            for item in menu
        ])
        user_profile = f"Diet: {', '.join(dietary) if dietary else 'None'}, Allergies: {', '.join(allergies) if allergies else 'None'}"

        # Calculate similarity scores for menu items
        matching_dishes = []
        for item in menu:
            item_text = ' '.join([
                item['name'].lower(),
                item.get('description', '').lower(),
                ' '.join(item.get('ingredients', [])).lower(),
                ' '.join(item.get('dietary_tags', [])).lower()
            ])
            score = max(fuzz.partial_ratio(label, item_text) for label in combined_labels)
            if score > 60:
                matching_dishes.append({
                    "name": item['name'],
                    "score": score,
                    "description": item.get('description', ''),
                    "ingredients": item.get('ingredients', []),
                    "dietary_tags": item.get('dietary_tags', []),
                    "id": item['id']
                })
        matching_dishes = sorted(matching_dishes, key=lambda x: x['score'], reverse=True)[:5]

        # Gemini prompt for precise dish prediction with event-inspired dishes and AI-based suggestions
        prompt = f"""
        Analyze the following:
        - Image labels and objects: {labels + objects}
        - Detected text: {texts if texts else 'None'}
        - Plating style: {', '.join(style_indicators) if style_indicators else 'Not identified'}
        - User profile: {user_profile}
        - Menu items: {menu_text}
        - Event context: Current season is summer, and there is a 'Summer Feast' event with focus on light, refreshing dishes.

        Tasks:
        1. Predict the most likely dish from the menu that matches the image, prioritizing high-confidence labels (score > 0.8), detected text, and plating style.
        2. If no exact match, suggest the closest dish and explain why it fits the labels, text, style, and user profile.
        3. Recommend 3 additional relevant dishes from the menu that align with the detected dish's characteristics, user preferences, and event context.
        4. For pasta dishes, suggest variations like gluten-free penne, zucchini noodles, or customizable sauces.
        5. For desserts, suggest low-sugar, dairy-free, or healthy alternatives.

        Format the response as:
        **Predicted Dish**: [Dish Name]
        **Explanation**: [Reasoning]
        **Related Menu Items**:
        - [Dish Name]: [Description] (Similarity: [Score]%)
        - ...
        **Relevant Recommendations**:
        - [Dish Name]: [Reason]
        - ...
        **Pasta Variations (if applicable)**:
        - [Variation]: [Description]
        - ...
        **Dessert Alternatives (if applicable)**:
        - [Alternative]: [Description]
        - ...
        """
        try:
            dish_guess = gemini_model.generate_content(prompt).text.strip()
            st.success(f"AI Dish Analysis:\n{dish_guess}")

            # Display related menu items as a table
            if matching_dishes:
                st.subheader("Related Menu Items")
                df = pd.DataFrame([
                    {
                        "Dish Name": dish['name'],
                        "Description": dish['description'],
                        "Ingredients": ', '.join(dish['ingredients']),
                        "Dietary Tags": ', '.join(dish['dietary_tags']),
                        "Similarity Score": f"{dish['score']}%"
                    }
                    for dish in matching_dishes
                ])
                st.dataframe(df, use_container_width=True)
            else:
                st.info("No closely related menu items found.")

        except Exception as e:
            st.error(f"AI analysis failed: {e}")

with tab2:
    st.header("Personalized AI Menu")
    menu = fetch_menu()
    
    # Build allergy keywords map (simplified)
    allergy_keywords = {
        "Dairy-Free": ["milk", "cheese", "butter", "cream", "yogurt", "paneer", "ghee", "curd", "ice cream", "whey", "casein"],
        "Nut-Free": ["almond", "cashew", "peanut", "hazelnut", "walnut", "pistachio", "pecan"],
        "Shellfish-Free": ["shrimp", "crab", "lobster", "prawn", "clam", "mussel", "oyster", "scallop"],
        "Soy-Free": ["soy", "tofu", "soya", "edamame", "soybean", "soy milk"]
    }
    
    # Pre-filter menu based on allergies and dietary
    filtered_menu = []
    for item in menu:
        ingredients = [ing.lower() for ing in item.get('ingredients', [])]
        tags = [tag.lower() for tag in item.get('dietary_tags', [])]

        allergy_safe = True
        for allergy in allergies:
            allergy_list = allergy_keywords.get(allergy, [])
            if any(allergen in ing for allergen in allergy_list for ing in ingredients):
                allergy_safe = False
                break
        
        diet_safe = all(diet.lower() in tags for diet in dietary) if dietary else True
        
        if allergy_safe and diet_safe:
            filtered_menu.append(item)

    if not filtered_menu:
        st.warning("No menu items match your preferences and allergy restrictions.")
        st.stop()

    # Prepare menu text for Gemini after filtering
    menu_text = "\n".join([
        f"- {item['name']}: {item.get('description', '')} (Ingredients: {', '.join(item.get('ingredients', []))}; Tags: {', '.join(item.get('dietary_tags', []))})"
        for item in filtered_menu
    ])

    user_profile = f"Diet: {', '.join(dietary) if dietary else 'None'}, Allergies: {', '.join(allergies) if allergies else 'None'}"
    order_history = fetch_order_history(user_id)
    order_summary = "\n".join([f"- {order['dish_name']} (Ordered on: {time.ctime(order['timestamp'])})" for order in order_history]) if order_history else "No order history available."

    popular_trends = "Current popular trends include plant-based proteins, fermented foods, and low-carb options."

    prompt = f"""
    Given the following:
    - User profile: {user_profile}
    - Order history: {order_summary}
    - Popular trends: {popular_trends}
    - Menu: {menu_text}

    Tasks:
    1. Recommend 5 dishes that align strictly with the user's dietary preferences and allergy restrictions.
    2. Ensure that dairy-free dishes contain no milk, cheese, butter, cream, yogurt, paneer, or ghee.
    3. For pasta dishes, suggest variations like gluten-free penne, zucchini noodles, or customizable sauces.
    4. For desserts, suggest low-sugar, dairy-free, or healthy alternatives.

    Format the response as:
    **Recommended Dishes**:
    - [Dish Name]: [Reason]
    - ...
    **Pasta Variations (if applicable)**:
    - [Variation]: [Description]
    - ...
    **Dessert Alternatives (if applicable)**:
    - [Alternative]: [Description]
    - ...
    """

    try:
        ai_result = gemini_model.generate_content(prompt).text.strip()
        st.markdown(ai_result)
    except Exception as e:
        st.error(f"AI analysis failed: {e}")


with tab3:
    st.header("Custom Menu Filters")
    portion = st.selectbox("Portion Size", ["Regular", "Small", "Large"])
    ingredient_swap = st.text_input("Ingredient Swap")

    allergy_map = {
        "Nut-Free": ["almond", "cashew", "walnut", "pecan", "hazelnut", "macadamia", "brazil nut", "pistachio", "peanut", "nut"],
        "Shellfish-Free": ["shrimp", "prawn", "crab", "lobster", "oyster", "scallop", "clam", "mussel", "shellfish"],
        "Soy-Free": ["soy", "tofu", "soya", "edamame", "soy sauce", "miso", "tempeh"],
        "Dairy-Free": ["milk", "cheese", "butter", "yogurt", "cream", "paneer", "curd", "ghee", "whey", "casein", "lactose"]
    }

    filtered_menu = menu

    # Apply diet filter first
    if dietary:
        filtered_menu = [
            item for item in filtered_menu 
            if any(d.lower() in [tag.lower() for tag in item.get("dietary_tags", [])] for d in dietary)
        ]

    # Apply allergy filter next
    if allergies:
        final_filtered_menu = []
        for item in filtered_menu:
            ingredients = [i.lower() for i in item.get("ingredients", [])]
            allergy_safe = True
            for allergy in allergies:
                forbidden = allergy_map.get(allergy, [])
                if any(bad in ingredient for bad in forbidden for ingredient in ingredients):
                    allergy_safe = False
                    break
            if allergy_safe:
                final_filtered_menu.append(item)
        filtered_menu = final_filtered_menu

    # Add portion + ingredient swap info
    for item in filtered_menu:
        item["portion_size"] = portion
        item["ingredient_swap"] = ingredient_swap

    if filtered_menu:
        st.write(pd.DataFrame(filtered_menu))
    else:
        st.warning("No menu items match the selected filters.")


# TAB 5: Leaderboard & Customer Feedback
with tab5:
    st.header("Leaderboard & Voting")

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
                    st.rerun()
            with col2:
                if st.button(f"👀 View ({entry['views']})", key=f"view_{entry['id']}"):
                    db.collection("visual_challenges").document(entry['id']).update({"views": entry['views'] + 1})
                    st.rerun()
            with col3:
                if st.button(f"🛒 Order ({entry['orders']})", key=f"order_{entry['id']}"):
                    db.collection("visual_challenges").document(entry['id']).update({"orders": entry['orders'] + 1})
                    st.rerun()

    # Show leaderboard
    st.subheader("🏆 Live Leaderboard")
    leaderboard = sorted(entries, key=lambda e: calculate_score(e), reverse=True)
    for i, entry in enumerate(leaderboard[:5]):
        st.write(f"**#{i+1} - {entry['dish']} by {entry['staff']} → {calculate_score(entry)} pts**")
