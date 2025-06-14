# Only replacing TAB 4 and TAB 5 --- rest of your code stays exactly same

# TAB 4: Staff Gamification Upload (Improved UI)
with tab4:
    st.header("🚀 Participate in the Visual Menu Challenge")
    st.markdown("Encourage your creativity and plating skills. Upload your best dish photos, get votes, and climb the leaderboard!")

    with st.form("challenge_form"):
        col1, col2 = st.columns(2)
        with col1:
            staff_name = st.text_input("👩‍🍳 Your Name")
            dish_name = st.text_input("🍽️ Dish Name")
            plating_style = st.selectbox("🎨 Plating Style", ["Minimalist", "Classic", "Fusion", "Artistic", "Rustic"])
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
            st.success("🎉 Dish submitted successfully!")

# TAB 5: Leaderboard & Customer Feedback (Upgraded UI)
with tab5:
    st.header("🏆 Visual Menu Leaderboard")

    entries = fetch_challenge_entries()

    if entries:
        leaderboard = sorted(entries, key=lambda e: calculate_score(e), reverse=True)

        for i, entry in enumerate(leaderboard):
            with st.container():
                st.subheader(f"#{i+1} - {entry['dish']} by {entry['staff']}")
                col1, col2 = st.columns([1, 2])
                with col1:
                    # If you want to store & retrieve images from firestore storage later, here we use placeholder
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
