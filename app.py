import streamlit as st
from bs4 import BeautifulSoup
import aiohttp
import asyncio
import nest_asyncio
import pandas as pd
import os
import datetime
import plotly.graph_objects as go

# =======================================
# SETUP
# =======================================
nest_asyncio.apply()
semaphore = asyncio.Semaphore(5)

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
                    return ""
                return await response.text()
        except Exception:
            return ""

# =======================================
# SCRAPE PROFILE
# =======================================
async def get_profile_data(username):
    url = f"https://letterboxd.com/{username}/"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            html = await response.text()
    soup = BeautifulSoup(html, "html.parser")

    def get_count(tab):
        tag = soup.select_one(f'a[href="/{username.lower()}/{tab}/"] > span.value')
        return int(tag.text.replace(',', '')) if tag else 0

    followers_count = get_count("followers")
    following_count = get_count("following")
    max_pages_followers = int(followers_count / 25) + 1
    max_pages_following = int(following_count / 25) + 1
    return followers_count, following_count, max_pages_followers, max_pages_following

# =======================================
# SCRAPE USER LIST
# =======================================
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

# =======================================
# MAIN ASYNC
# =======================================
async def main_async(username):
    followers_count, following_count, max_pages_followers, max_pages_following = await get_profile_data(username)
    followers = await get_user_list(username, "followers", max_pages_followers, max_pages_following)
    following = await get_user_list(username, "following", max_pages_followers, max_pages_following)
    return followers_count, following_count, followers, following

# =======================================
# STREAMLIT UI
# =======================================
st.set_page_config(page_title="Letterboxd Unfollower Tracker", layout="centered")

st.markdown("""
    <style>
    body {background-color:#0e0e0e;color:#f5f5f5;}
    .main {
        max-width: 850px;
        margin: auto;
        background-color: #141414;
        padding: 40px;
        border-radius: 20px;
        box-shadow: 0 0 25px rgba(0,0,0,0.5);
    }
    h1,h2,h3 {text-align:center;}
    .fade-in {animation: fadeIn 1.5s ease;}
    @keyframes fadeIn {from {opacity:0;} to {opacity:1;}}
    .activity-box {
        border: 1px solid #333;
        border-radius: 10px;
        padding: 15px;
        background-color: #1a1a1a;
        margin-bottom: 20px;
    }

    /* 🌌 Aurora Glow Background */
    [data-testid="stAppViewContainer"]::before {
        content: "";
        position: fixed;
        top: 0;
        left: 0;
        width: 200%;
        height: 200%;
        background: radial-gradient(circle at 30% 30%, rgba(61, 220, 132, 0.15), transparent 60%),
                    radial-gradient(circle at 70% 60%, rgba(76, 158, 255, 0.12), transparent 60%),
                    radial-gradient(circle at 50% 80%, rgba(122, 95, 255, 0.10), transparent 70%);
        animation: auroraMove 25s ease-in-out infinite alternate;
        z-index: -1;
        transform: translate(-25%, -25%);
        pointer-events: none;
        filter: blur(60px);
    }

    @keyframes auroraMove {
        0% { transform: translate(-20%, -20%) scale(1); }
        50% { transform: translate(-15%, -25%) scale(1.05); }
        100% { transform: translate(-20%, -20%) scale(1); }
    }
    </style>
""", unsafe_allow_html=True)



st.markdown("<h1 class='fade-in'>🎬 Letterboxd Unfollower Tracker</h1>", unsafe_allow_html=True)
st.write("<p style='text-align:center;'>Track followers, unfollowers, and relationship trends with clean & visualized.</p>", unsafe_allow_html=True)
st.divider()

username = st.text_input("👤 Enter your Letterboxd username:", placeholder="e.g. hsnf", key="uname")
center_btn = st.columns(3)[1]
check_btn = center_btn.button("✨ Check Now!", use_container_width=True)

if check_btn and username:
    with st.status(f"Fetching data for @{username}...", expanded=True) as status:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        followers_count, following_count, followers, following = loop.run_until_complete(main_async(username))
        status.update(label="✅ Data fetched successfully!", state="complete")

    current_date = datetime.date.today().isoformat()
    os.makedirs("data", exist_ok=True)
    follower_file = f"data/{username}_followers.csv"
    unfollow_log = f"data/{username}_unfollow_history.csv"

    set_followers = {u["username"] for u in followers}
    set_following = {u["username"] for u in following}

    old_data = pd.read_csv(follower_file) if os.path.exists(follower_file) else pd.DataFrame(columns=["username"])
    old_followers = set(old_data["username"].tolist())

    new_followers = set_followers - old_followers
    recent_follows = [{"username": u, "follow_date": current_date} for u in new_followers]
    recent_unfollows = old_followers - set_followers
    recent_unfollows_list = [{"username": u, "unfollow_date": current_date} for u in recent_unfollows]

    new_df = pd.DataFrame([{"username": u, "last_seen_date": current_date} for u in set_followers])
    new_df.to_csv(follower_file, index=False)

    # ===============================
    # SUMMARY METRICS
    # ===============================
    st.markdown("<div class='fade-in'>", unsafe_allow_html=True)
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("🚶‍♂️ Following", len(following))
    col2.metric("👥 Followers", len(followers))
    unfollowers = [u for u in following if u["username"] not in set_followers]
    unfollowing = [u for u in followers if u["username"] not in set_following]
    all_time_unfollowers = list(old_followers - set_followers)
    col3.metric("😒 Not Following Back", len(unfollowers))
    col4.metric("💔 You Don’t Follow Back", len(unfollowing))
    col5.metric("🕓 All-time Unfollowers", len(all_time_unfollowers))
    st.markdown("</div>", unsafe_allow_html=True)

    # ===============================
    # VISUAL INSIGHTS (PIE CHART)
    # ===============================
    st.divider()
    st.subheader("📊 Visual Insights")

    stats = {
        "Following": len(following),
        "Followers": len(followers),
        "Doesn't Follow Back": len(unfollowers),
        "You Don't Follow Back": len(unfollowing)
    }

    fig = go.Figure(
        data=[go.Pie(
            labels=list(stats.keys()),
            values=list(stats.values()),
            hole=0.55,
            marker=dict(colors=["#4C9EFF","#3DDC84","#FF6B6B","#F5A623"], line=dict(color="#0E1117", width=2)),
            hoverinfo="label+percent",
            textinfo="value",
            textfont=dict(size=18, color="white")
        )]
    )
    fig.update_traces(pull=[0.05, 0, 0.05, 0])
    fig.update_layout(
        showlegend=True,
        paper_bgcolor="#0E1117",
        plot_bgcolor="#0E1117",
        font=dict(color="white", size=16),
        annotations=[dict(text="Letterboxd Stats", x=0.5, y=0.5, font_size=20, showarrow=False)]
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ===============================
    # ACTIVITY TIMELINE (10 Terbaru)
    # ===============================
    st.divider()
    st.subheader("📆 Activity Timeline")

    tab1, tab2 = st.tabs(["🟢 Recently Followed You", "🔴 Recently Unfollowed You"])
    with tab1:
        if recent_follows:
            for item in recent_follows[:10]:
                st.markdown(
                    f"<div class='activity-box'>"
                    f"<b><a href='https://letterboxd.com/{item['username']}/' target='_blank' style='color:#3DDC84;'>"
                    f"{item['username']}</a></b> followed you on <b>{item['follow_date']}</b> 🎉"
                    f"</div>", unsafe_allow_html=True)
        else:
            st.success("No new followers recently. 🥹")

    with tab2:
        if recent_unfollows_list:
            for item in recent_unfollows_list[:10]:
                st.markdown(
                    f"<div class='activity-box'>"
                    f"<b><a href='https://letterboxd.com/{item['username']}/' target='_blank' style='color:#FF6B6B;'>"
                    f"{item['username']}</a></b> unfollowed you on <b>{item['unfollow_date']}</b> 💔"
                    f"</div>", unsafe_allow_html=True)
        else:
            st.info("No one unfollowed you recently. 😊")

    # ===============================
    # LIST TABS
    # ===============================
    st.divider()
    tabs = st.tabs(["🚫 Not Following Back", "↩️ You Don’t Follow Back", "📉 All-time Unfollowers"])

    def show_users(users, color):
        for u in users:
            uname = u["username"] if isinstance(u, dict) else u
            st.markdown(
                f"<div class='fade-in' style='margin:4px 0;'>"
                f"<a href='https://letterboxd.com/{uname}/' target='_blank' "
                f"style='color:{color};font-weight:600;text-decoration:none;'>• {uname}</a></div>",
                unsafe_allow_html=True,
            )

    with tabs[0]:
        if unfollowers:
            show_users(unfollowers, "#ff5c5c")
        else:
            st.success("Everyone you follow follows you back! 🎉")

    with tabs[1]:
        if unfollowing:
            show_users(unfollowing, "#4c9eff")
        else:
            st.success("You follow back everyone! 👍")

    with tabs[2]:
        if all_time_unfollowers:
            show_users(all_time_unfollowers, "#ffb347")
        else:
            st.success("No one has unfollowed you yet! 🫶")

    st.divider()
    st.markdown(
        "<p style='text-align:center;opacity:0.8;'>Found a bug? Contact me (let's be moots 🥺) - Built with ❤️ by "
        "<a href='https://boxd.it/9BaD9' style='color:#1db954;'>Bynguts</a></p>",
        unsafe_allow_html=True,
    )








