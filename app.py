import streamlit as st
from bs4 import BeautifulSoup
import aiohttp
import asyncio
import nest_asyncio
import pandas as pd

nest_asyncio.apply()
semaphore = asyncio.Semaphore(5)

# --------------------------
# Helper functions
# --------------------------
async def fetch_page(session, url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Referer": "https://letterboxd.com/",
        "Connection": "keep-alive"
    }
    timeout = aiohttp.ClientTimeout(total=60)
    async with semaphore:
        try:
            async with session.get(url, headers=headers, timeout=timeout) as response:
                if response.status != 200:
                    print(f"Gagal fetch {url}, status: {response.status}")
                    return ""
                print(f"✅ Fetched: {url}")
                return await response.text()
        except asyncio.TimeoutError:
            print(f"Timeout saat fetch: {url}")
            return ""
        except Exception as e:
            print(f"Error saat fetch {url}: {e}")
            return ""

async def get_profile_data(username):
    url = f"https://letterboxd.com/{username}/"
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            html = await response.text()

    soup = BeautifulSoup(html, "html.parser")
    def get_count(tab):
        selector = f'a[href="/{username.lower()}/{tab}/"] > span.value'
        tag = soup.select_one(selector)
        return int(tag.text.replace(',', '')) if tag else 0

    max_pages_followers = int(get_count("followers") / 25) + 1
    max_pages_following = int(get_count("following") / 25) + 1
    return max_pages_followers, max_pages_following

async def get_user_list(username, tab, max_pages_followers, max_pages_following):
    urls = [f"https://letterboxd.com/{username}/{tab}/page/{page}/"
            for page in range(1, (max_pages_followers if tab=="followers" else max_pages_following)+1)]
    user_list = []
    async with aiohttp.ClientSession() as session:
        for i, url in enumerate(urls, start=1):
            html = await fetch_page(session, url)
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")
            user_blocks = soup.select("div.person-summary")
            for user in user_blocks:
                avatar_tag = user.select_one("a.avatar img")
                username_lb = user.select_one("a.avatar")["href"].strip("/") if user.select_one("a.avatar") else None
                avatar_url = avatar_tag["data-src"] if avatar_tag and avatar_tag.has_attr("data-src") else None
                if username_lb:
                    user_list.append({"username": username_lb, "avatar": avatar_url})
            st.progress(i / len(urls))  # Update progress bar
    return user_list

async def main_async(username):
    max_pages_followers, max_pages_following = await get_profile_data(username)
    followers = await get_user_list(username, "followers", max_pages_followers, max_pages_following)
    following = await get_user_list(username, "following", max_pages_followers, max_pages_following)
    return followers, following

# --------------------------
# Streamlit UI
# --------------------------
st.set_page_config(page_title="Letterboxd Unfollower Checker", layout="wide")
st.title("🎬 Letterboxd Unfollower Checker")
st.write("Compare your following & followers and see who doesn't follow you back!")

username = st.text_input("Letterboxd username:").strip()
_, middle, _ = st.columns(3)
check_button = middle.button("Check now!", use_container_width=True)

if check_button and username:
    st.session_state.progress = st.progress(0)
    with st.spinner(f"Fetching data for {username}..."):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        followers, following = loop.run_until_complete(main_async(username))

    set_followers = {u["username"] for u in followers}
    set_following = {u["username"] for u in following}

    unfollowers = [u for u in following if u["username"] not in set_followers]
    unfollowing = [u for u in followers if u["username"] not in set_following]

    # Stats
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🚀 Following", len(following))
    col2.metric("🎟️ Followers", len(followers))
    col3.metric("😒 Doesn't Follow Back", len(unfollowers))
    col4.metric("💔 You Don't Follow Back", len(unfollowing))

    st.divider()
    tabs = st.tabs(["Doesn't Follow You Back", "You Don't Follow Back"])

    def display_user_list(user_list, highlight_color="#FF6B6B"):
        for u in user_list:
            cols = st.columns([1, 4])
            with cols[0]:
                if u.get("avatar"):
                    st.image(u["avatar"], width=40)
            with cols[1]:
                st.markdown(f"<span style='color:{highlight_color};font-weight:bold;'>"
                            f"[{u['username']}](https://letterboxd.com/{u['username']}/)</span>", unsafe_allow_html=True)

    # Tab 1: Doesn't Follow Back (red)
    with tabs[0]:
        if unfollowers:
            st.caption("People you follow but they don’t follow you")
            display_user_list(unfollowers, highlight_color="#FF4C4C")
            df_unfollowers = pd.DataFrame([u["username"] for u in unfollowers], columns=["username"])
            st.download_button("Download CSV", df_unfollowers.to_csv(index=False), "unfollowers.csv")
        else:
            st.success("Everyone you follow also follows you back! 🎉")

    # Tab 2: You Don't Follow Back (blue)
    with tabs[1]:
        if unfollowing:
            st.caption("People who follow you but you don’t follow them")
            display_user_list(unfollowing, highlight_color="#4C9EFF")
            df_unfollowing = pd.DataFrame([u["username"] for u in unfollowing], columns=["username"])
            st.download_button("Download CSV", df_unfollowing.to_csv(index=False), "unfollowing.csv")
        else:
            st.success("You follow back everyone who follows you! 👍")

    st.divider()
    st.markdown("🐞 Found a bug? Contact me — Made by [rafilajhh](https://letterboxd.com/rafilajhh/)")
