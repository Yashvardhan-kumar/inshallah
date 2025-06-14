import streamlit as st
import datetime

# Your existing code remains fully intact above this point
# --- We start adding gamification layer below ---

# Gamification Firestore Setup (reuse existing db)
def get_user_profile(user_id):
    user_ref = db.collection("user_profiles").document(user_id)
    user_doc = user_ref.get()
    if user_doc.exists:
        return user_doc.to_dict()
    else:
        profile = {"xp": 0, "level": 1, "stars": 0, "badges": [], "last_active": str(datetime.date.today())}
        user_ref.set(profile)
        return profile

def update_user_profile(user_id, updates):
    user_ref = db.collection("user_profiles").document(user_id)
    user_ref.update(updates)

# Dummy user (replace with login system if needed)
USER_ID = "demo_user"
profile = get_user_profile(USER_ID)

# Gamification Functions
def add_xp(user_id, xp):
    profile = get_user_profile(user_id)
    new_xp = profile["xp"] + xp
    new_level = 1 + new_xp // 100
    update_user_profile(user_id, {"xp": new_xp, "level": new_level, "last_active": str(datetime.date.today())})

def add_stars(user_id, stars):
    profile = get_user_profile(user_id)
    update_user_profile(user_id, {"stars": profile["stars"] + stars})

def add_badge(user_id, badge):
    profile = get_user_profile(user_id)
    if badge not in profile["badges"]:
        profile["badges"].append(badge)
        update_user_profile(user_id, {"badges": profile["badges"]})

# Create new tab
with st.sidebar.expander("🎮 Gamification & Profile"):
    st.subheader("Player Profile")
    st.write(f"**Level:** {profile['level']}")
    st.write(f"**XP:** {profile['xp']}")
    st.write(f"**Stars:** {profile['stars']}")
    st.write(f"**Badges:** {', '.join(profile['badges']) if profile['badges'] else 'No badges yet'}")

# Daily Challenge
st.sidebar.markdown("---")
today = str(datetime.date.today())
if profile.get("last_active") != today:
    challenge_dish = random.choice(["Pizza", "Sushi", "Burger", "Salad", "Tacos"])
    st.sidebar.success(f"🎯 Daily Challenge: Upload an image of {challenge_dish} today!")
    update_user_profile(USER_ID, {"last_active": today})

# Check challenge completion during dish detection
if 'dish_name' in locals() and dish_name.lower() == challenge_dish.lower():
    add_xp(USER_ID, 50)
    add_badge(USER_ID, "Daily Streak!")
    st.sidebar.balloons()
    st.sidebar.success("✅ Daily Challenge Completed! You earned 50 XP & a badge!")

# Word Search reward integration
if 'found_count' in locals() and found_count == total_words and st.session_state.stars == 5:
    add_xp(USER_ID, 20)
    add_stars(USER_ID, 5)
    add_badge(USER_ID, "Word Search Master")
    st.sidebar.success("🏅 Perfect Word Search! +20 XP, +5 Stars, Badge earned!")

# Simple leaderboard (local)
@st.cache_data(ttl=300)
def load_leaderboard():
    docs = db.collection("user_profiles").stream()
    data = sorted([{**doc.to_dict(), "id": doc.id} for doc in docs], key=lambda x: x['xp'], reverse=True)
    return data

with st.sidebar.expander("🏆 Leaderboard"):
    leaderboard = load_leaderboard()
    for rank, player in enumerate(leaderboard[:5], start=1):
        st.write(f"{rank}. {player['id']} - Level {player['level']} ({player['xp']} XP)")
