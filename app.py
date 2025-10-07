import streamlit as st
from bs4 import BeautifulSoup
import aiohttp
import asyncio
import nest_asyncio
import pandas as pd
import os
import plotly.graph_objects as go
import datetime
import altair as alt

# =======================================
# SETUP
# =======================================
nest_asyncio.apply()
semaphore = asyncio.Semaphore(5)

# =======================================
# FETCH PAGE
# =======================================
async def fetch_page(session, url):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-US,en;q=0.9"
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

# ---------- CUSTOM STYLING ----------
st.markdown("""
<style>
body { background-color: #0e0e0e; color: #f5f5f5; }
.main {
    max-width: 850px; margin: auto; background-color: #141414;
    padding: 40px; border-radius: 20px; box-shadow: 0px 0px 25px rgba(0,0,0,0.5);
}
.timeline-box {
    border: 1px solid #333;
    border-radius: 15px;
    padding: 20px;
    background-color: #1b1b1b;
    margin-top: 20px;
}
.timeline-item {
    border-bottom: 1px solid #333;
    padding: 8px 0;
}
.timeline-item:last-child { border-bottom: none; }
h1, h2, h3, h4 { text-align: center !important; }
.fade-in { animation: fadeIn 1.5s ease; }
@keyframes fadeIn { from {opacity: 0;} to {opacity: 1;} }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 class='fade-in'>🎬 Letterboxd Unfollower Tracker</h1>", unsafe_allow_html=True)
st.write("<p style='text-align:center;'>Track followers, unfollowers, and visualize your Letterboxd social trends.</p>", unsafe_allow_html=True)
st.divider()

username = st.text_input("👤 Enter your Letterboxd username:", placeholder="e.g. rafilajhh", key="uname")
center_btn = st.columns(3)[1]
check_btn = center_btn.button("✨ Check Now!", use_container_width=True)

# =======================================
# MAIN EXECUTION
# =======================================
if check_btn and username:
    with st.status(f"Fetching data for @{username}...", expanded=True) as status:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        followers_count, following_count, followers, following = loop.run_until_complete(main_async(username))
        status.update(label="✅ Data fetched successfully!", state="complete")

    current_date = datetime.date.today().isoformat()
    set_followers = {u["username"] for u in followers}
    set_following = {u["username"] for u in following}

    os.makedirs("data", exist_ok=True)
    follower_file = f"data/{username}_followers.csv"
    unfollow_log = f"data/{username}_unfollow_history.csv"

    old_data = pd.read_csv(follower_file) if os.path.exists(follower_file) else pd.DataFrame(columns=["username", "last_seen_date"])
    old_followers = set(old_data["username"].tolist())

    new_followers = set_followers - old_followers
    recent_follows = [{"username": u, "follow_date": current_date} for u in new_followers]
    recent_unfollows = old_followers - set_followers
    recent_unfollows_list = [{"username": u, "unfollow_date": current_date} for u in recent_unfollows]

    new_df = pd.DataFrame([{"username": u, "last_seen_date": current_date} for u in set_followers])
    new_df.to_csv(follower_file, index=False)

    if recent_unfollows:
        if os.path.exists(unfollow_log):
            old_unf = pd.read_csv(unfollow_log)
            new_unf = pd.DataFrame(recent_unfollows_list)
            pd.concat([old_unf, new_unf], ignore_index=True).to_csv(unfollow_log, index=False)
        else:
            pd.DataFrame(recent_unfollows_list).to_csv(unfollow_log, index=False)

    # ---------- VISUAL INSIGHTS ----------
    st.divider()
    st.subheader("📊 Visual Insights")

    stats = {
        "Following": len(following),
        "Followers": len(followers),
        "Doesn't Follow Back": len([u for u in following if u["username"] not in set_followers]),
        "You Don't Follow Back": len([u for u in followers if u["username"] not in set_following])
    }

    fig = go.Figure(data=[go.Pie(
        labels=list(stats.keys()),
        values=list(stats.values()),
        hole=0.55,
        marker=dict(colors=["#4C9EFF", "#3DDC84", "#FF6B6B", "#F5A623"]),
        hoverinfo="label+percent",
        textinfo="value",
        textfont=dict(size=18, color="white")
    )])
    fig.update_traces(pull=[0.05, 0, 0.05, 0])
    fig.update_layout(
        showlegend=True,
        paper_bgcolor="#0E1117",
        plot_bgcolor="#0E1117",
        font=dict(color="white", size=16),
        annotations=[dict(text="Letterboxd Stats", x=0.5, y=0.5, font_size=20, showarrow=False)]
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ---------- RECENT TIMELINE ----------
    st.divider()
    st.subheader("📆 Activity Timeline")

    timeline_data = []
    for item in recent_follows:
        timeline_data.append({"username": item["username"], "date": item["follow_date"], "action": "Followed"})
    for item in recent_unfollows_list:
        timeline_data.append({"username": item["username"], "date": item["unfollow_date"], "action": "Unfollowed"})

    if timeline_data:
        df_timeline = pd.DataFrame(timeline_data)
        chart = (
            alt.Chart(df_timeline)
            .mark_circle(size=150)
            .encode(
                x="date:T",
                y=alt.Y("action:N", title=None),
                color=alt.Color("action", scale=alt.Scale(range=["#3DDC84", "#FF6B6B"])),
                tooltip=["username", "action", "date"]
            )
            .properties(height=300, title="🕓 Recent Follow & Unfollow Timeline")
            .interactive()
        )
        st.markdown("<div class='timeline-box'>", unsafe_allow_html=True)
        st.altair_chart(chart, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # ---------- RECENT FOLLOW / UNFOLLOW LISTS ----------
    st.divider()
    tab1, tab2 = st.tabs(["🟢 Recently Followed You", "🔴 Recently Unfollowed You"])

    with tab1:
        if recent_follows:
            for item in recent_follows[:10]:
                st.markdown(f"<div class='timeline-item'>"
                            f"<a href='https://letterboxd.com/{item['username']}/' "
                            f"style='color:#3DDC84;text-decoration:none;'>"
                            f"@{item['username']}</a> — Followed on **{item['follow_date']}** 🎉</div>",
                            unsafe_allow_html=True)
        else:
            st.success("No new followers recently.")

    with tab2:
        if recent_unfollows_list:
            for item in recent_unfollows_list[:10]:
                st.markdown(f"<div class='timeline-item'>"
                            f"<a href='https://letterboxd.com/{item['username']}/' "
                            f"style='color:#FF6B6B;text-decoration:none;'>"
                            f"@{item['username']}</a> — Unfollowed on **{item['unfollow_date']}** 💔</div>",
                            unsafe_allow_html=True)
        else:
            st.info("No one unfollowed you recently.")

    st.divider()
    st.markdown(
        "<p style='text-align:center;opacity:0.8;'>🐞 Built with ❤️ by "
        "<a href='https://letterboxd.com/rafilajhh/' style='color:#1db954;'>rafilajhh</a></p>",
        unsafe_allow_html=True,
    )
