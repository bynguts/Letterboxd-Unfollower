import streamlit as st
from bs4 import BeautifulSoup
import aiohttp
import asyncio
import nest_asyncio
import pandas as pd
import os
import matplotlib.pyplot as plt

nest_asyncio.apply()
semaphore = asyncio.Semaphore(5)

# -------------------------------
# FETCH PAGE
# -------------------------------
async def fetch_page(session, url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://letterboxd.com/",
        "Connection": "keep-alive"
    }

    timeout = aiohttp.ClientTimeout(total=60)
    async with semaphore:
        try:
            async with session.get(url, headers=headers, timeout=timeout) as response:
                if response.status != 200:
                    print(f"❌ Gagal fetch {url} ({response.status})")
                    return ""
                return await response.text()
        except Exception as e:
            print(f"Error fetch {url}: {e}")
            return ""

# -------------------------------
# PROFILE DATA
# -------------------------------
async def get_profile_data(username):
    url = f"https://letterboxd.com/{username}/"
    headers = {"User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            html = await response.text()

    soup = BeautifulSoup(html, "html.parser")

    def get_count(tab):
        selector = f'a[href="/{username.lower()}/{tab}/"] > span.value'
        tag = soup.select_one(selector)
        return int(tag.text.replace(',', '')) if tag else 0

    followers_count = get_count("followers")
    following_count = get_count("following")

    max_pages_followers = int(followers_count / 25) + 1
    max_pages_following = int(following_count / 25) + 1
    return followers_count, following_count, max_pages_followers, max_pages_following

# -------------------------------
# USER LIST
# -------------------------------
async def get_user_list(username, tab, max_pages_followers, max_pages_following):
    max_pages = max_pages_followers if tab == "followers" else max_pages_following
    urls = [f"https://letterboxd.com/{username}/{tab}/page/{p}/" for p in range(1, max_pages + 1)]
    user_list = []

    async with aiohttp.ClientSession() as session:
        htmls = await asyncio.gather(*[fetch_page(session, url) for url in urls])
        for html in htmls:
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")
            for user in soup.select("div.person-summary"):
                avatar_tag = user.select_one("a.avatar img")
                user_link = user.select_one("a.avatar")
                if user_link and user_link.has_attr("href"):
                    username_lb = user_link["href"].strip("/")
                    avatar_url = avatar_tag["data-src"] if avatar_tag and avatar_tag.has_attr("data-src") else None
                    user_list.append({"username": username_lb, "avatar": avatar_url})
    return user_list

# -------------------------------
# MAIN ASYNC
# -------------------------------
async def main_async(username):
    followers_count, following_count, max_pages_followers, max_pages_following = await get_profile_data(username)
    followers = await get_user_list(username, "followers", max_pages_followers, max_pages_following)
    following = await get_user_list(username, "following", max_pages_followers, max_pages_following)
    return followers_count, following_count, followers, following

# -------------------------------
# STREAMLIT UI
# -------------------------------
st.set_page_config(page_title="Letterboxd Unfollower Checker", layout="wide")
st.title("🎬 Letterboxd Unfollower Checker & Tracker")
st.write("Compare your following vs followers, view stats, and track **all-time unfollowers**.")

username = st.text_input("Letterboxd username: ").strip()
_, mid, _ = st.columns(3)
if mid.button("Check now!", use_container_width=True) and username:
    with st.status(f"Fetching data for '{username}'...", expanded=True) as status:
        with st.spinner("Retrieving data..."):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            followers_count, following_count, followers, following = loop.run_until_complete(main_async(username))
        status.update(label="✅ Data loaded successfully!", state="complete", expanded=False)

    set_followers = {u["username"] for u in followers}
    set_following = {u["username"] for u in following}

    unfollowers = [u for u in following if u["username"] not in set_followers]
    unfollowing = [u for u in followers if u["username"] not in set_following]

    # -------------------------------
    # All-time unfollower tracker
    # -------------------------------
    os.makedirs("data", exist_ok=True)
    file_path = f"data/{username}_followers.csv"

    previous_followers = set()
    if os.path.exists(file_path):
        old_df = pd.read_csv(file_path)
        previous_followers = set(old_df["username"].tolist())

    # simpan followers terbaru
    pd.DataFrame(list(set_followers), columns=["username"]).to_csv(file_path, index=False)

    all_time_unfollowers = list(previous_followers - set_followers)

    # -------------------------------
    # Stats
    # -------------------------------
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("🚀 Following", following_count)
    col2.metric("🎟️ Followers", followers_count)
    col3.metric("😒 Doesn't Follow Back", len(unfollowers))
    col4.metric("💔 You Don't Follow Back", len(unfollowing))
    col5.metric("🕓 All-time Unfollowers", len(all_time_unfollowers))

    # -------------------------------
    # Chart comparison
    # -------------------------------
    st.subheader("📊 Profile Comparison Overview")
    labels = ["Following", "Followers", "Unfollowers", "Unfollowing", "All-time Unfollowers"]
    values = [following_count, followers_count, len(unfollowers), len(unfollowing), len(all_time_unfollowers)]

    fig, ax = plt.subplots()
    ax.bar(labels, values)
    ax.set_ylabel("Count")
    ax.set_title(f"Comparison for @{username}")
    st.pyplot(fig)

    # -------------------------------
    # Tabs
    # -------------------------------
    st.divider()
    tabs = st.tabs(["Doesn't Follow You Back", "You Don't Follow Back", "All-time Unfollowers"])

    def display_user_list(user_list, color):
        for u in user_list:
            c1, c2 = st.columns([1, 5])
            with c1:
                if isinstance(u, dict) and u.get("avatar"):
                    st.image(u["avatar"], width=45)
            with c2:
                uname = u["username"] if isinstance(u, dict) else u
                st.markdown(
                    f"<span style='color:{color};font-weight:600;'>"
                    f"[{uname}](https://letterboxd.com/{uname}/)</span>",
                    unsafe_allow_html=True
                )

    # Tab 1
    with tabs[0]:
        if unfollowers:
            st.caption("People you follow but they don't follow you back:")
            display_user_list(unfollowers, "#FF4C4C")
        else:
            st.success("Everyone you follow also follows you back!")

    # Tab 2
    with tabs[1]:
        if unfollowing:
            st.caption("People who follow you but you don't follow them:")
            display_user_list(unfollowing, "#4C9EFF")
        else:
            st.success("You follow back everyone who follows you!")

    # Tab 3
    with tabs[2]:
        if all_time_unfollowers:
            st.caption("People who used to follow you but no longer do:")
            display_user_list(all_time_unfollowers, "#FF9900")
        else:
            st.success("No one has unfollowed you yet — nice!")

    st.divider()
    st.markdown(
        "🐞 Found a bug? Contact — Made by [Bynguts](https://boxd.it/9BaD9)"
    )
