import streamlit as st
from bs4 import BeautifulSoup
import aiohttp
import asyncio
import nest_asyncio
import pandas as pd
import altair as alt
import os
import json
from datetime import datetime

nest_asyncio.apply()
semaphore = asyncio.Semaphore(5)
DATA_FOLDER = "user_data"
os.makedirs(DATA_FOLDER, exist_ok=True)

# --------------------------
# Async Helpers
# --------------------------
async def fetch_page(session, url):
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "*/*"}
    timeout = aiohttp.ClientTimeout(total=60)
    async with semaphore:
        try:
            async with session.get(url, headers=headers, timeout=timeout) as response:
                if response.status != 200:
                    return ""
                return await response.text()
        except:
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
        for url in urls:
            html = await fetch_page(session, url)
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")
            user_blocks = soup.select("div.person-summary")
            for user in user_blocks:
                username_lb = user.select_one("a.avatar")["href"].strip("/") if user.select_one("a.avatar") else None
                if username_lb:
                    user_list.append(username_lb)
    return user_list

@st.cache_data
def fetch_data(username):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    max_pages_followers, max_pages_following = loop.run_until_complete(get_profile_data(username))
    followers = loop.run_until_complete(get_user_list(username, "followers", max_pages_followers, max_pages_following))
    following = loop.run_until_complete(get_user_list(username, "following", max_pages_followers, max_pages_following))
    return followers, following

# --------------------------
# Daily Data Management
# --------------------------
def load_history(username):
    path = os.path.join(DATA_FOLDER, f"{username}.json")
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}

def save_history(username, followers, following):
    path = os.path.join(DATA_FOLDER, f"{username}.json")
    today = datetime.today().strftime("%Y-%m-%d")
    data = load_history(username)
    data[today] = {"followers": followers, "following": following}
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def get_trends(username):
    data = load_history(username)
    df = pd.DataFrame([
        {"date": d, "followers": len(v["followers"]), "following": len(v["following"])}
        for d, v in sorted(data.items())
    ])
    return df

def get_today_changes(username, followers, following):
    data = load_history(username)
    if not data:
        return [], []
    last_date = sorted(data.keys())[-1]
    last_followers = set(data[last_date]["followers"])
    last_following = set(data[last_date]["following"])
    unfollowed_today = [u for u in last_following if u not in following]
    new_followers = [u for u in followers if u not in last_followers]
    return unfollowed_today, new_followers

# --------------------------
# Recommended Films
# --------------------------
async def get_user_films(username, max_pages=5):
    films = []
    urls = [f"https://letterboxd.com/{username}/films/page/{page}/" for page in range(1, max_pages+1)]
    async with aiohttp.ClientSession() as session:
        for url in urls:
            html = await fetch_page(session, url)
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")
            film_blocks = soup.select("li.poster-container")
            for film in film_blocks:
                a_tag = film.select_one("div.poster > a")
                if a_tag:
                    title = a_tag["title"]
                    link = a_tag["href"]
                    img_tag = film.select_one("img")
                    poster = img_tag["data-src"] if img_tag and img_tag.has_attr("data-src") else None
                    films.append({"title": title, "url": link, "poster": poster})
    return films

def recommend_films_auto(user_films, popular_films):
    watched_titles = {film["title"] for film in user_films}
    return [film for film in popular_films if film["title"] not in watched_titles]

# --------------------------
# Streamlit UI
# --------------------------
st.set_page_config(page_title="Letterboxd Tracker & Recommendations", layout="wide")
st.title("🎬 Letterboxd Tracker & Recommendations")

username = st.text_input("Letterboxd username:").strip()
if username:
    with st.spinner(f"Fetching data for {username}..."):
        followers, following = fetch_data(username)
        save_history(username, followers, following)

    set_followers = set(followers)
    set_following = set(following)
    unfollowers = [u for u in following if u not in set_followers]
    unfollowing = [u for u in followers if u not in set_following]
    mutuals = [u for u in followers if u in set_following]
    unfollowed_today, new_followers_today = get_today_changes(username, followers, following)

    # Stats Cards
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Following", len(following))
    col2.metric("Followers", len(followers))
    col3.metric("Mutuals", len(mutuals))
    col4.metric("Unfollowers Today", len(unfollowed_today))
    col5.metric("New Followers Today", len(new_followers_today))

    # Tabs
    tabs = st.tabs(["Summary & Mutuals", "Doesn't Follow You Back", "You Don't Follow Back", "Statistics", "Trends", "Recommendations"])

    # ---- Summary & Mutuals ----
    with tabs[0]:
        st.subheader("Mutual Followers Preview")
        st.dataframe(pd.DataFrame(mutuals, columns=["username"]).head(10))

    # ---- Doesn't Follow You Back ----
    with tabs[1]:
        st.subheader("People you follow but they don’t follow you")
        search_term = st.text_input("Search username:", key="unfollowers")
        filtered = [u for u in unfollowers if search_term.lower() in u.lower()] if search_term else unfollowers
        st.dataframe(pd.DataFrame(filtered, columns=["username"]))
        st.download_button("Download CSV", pd.DataFrame(filtered, columns=["username"]).to_csv(index=False), "unfollowers.csv")

    # ---- You Don't Follow Back ----
    with tabs[2]:
        st.subheader("People who follow you but you don’t follow them")
        search_term2 = st.text_input("Search username:", key="unfollowing")
        filtered2 = [u for u in unfollowing if search_term2.lower() in u.lower()] if search_term2 else unfollowing
        st.dataframe(pd.DataFrame(filtered2, columns=["username"]))
        st.download_button("Download CSV", pd.DataFrame(filtered2, columns=["username"]).to_csv(index=False), "unfollowing.csv")

    # ---- Statistics ----
    with tabs[3]:
        st.subheader("Followers & Unfollowers Stats")
        df_chart = pd.DataFrame({
            "Category": ["Following", "Followers", "Mutuals", "Doesn't Follow Back", "You Don't Follow Back"],
            "Count": [len(following), len(followers), len(mutuals), len(unfollowers), len(unfollowing)]
        })
        pie = alt.Chart(df_chart).mark_arc().encode(
            theta=alt.Theta(field="Count", type="quantitative"),
            color=alt.Color(field="Category", type="nominal"),
            tooltip=["Category","Count"]
        ).properties(width=300, height=300)
        bar = alt.Chart(df_chart).mark_bar().encode(
            x=alt.X("Category", sort=None),
            y="Count",
            color="Category",
            tooltip=["Category","Count"]
        ).properties(width=400, height=300)
        col1, col2 = st.columns(2)
        col1.altair_chart(pie)
        col2.altair_chart(bar)

    # ---- Trends ----
    with tabs[4]:
        st.subheader("Followers / Following Trend")
        df_trends = get_trends(username)
        if not df_trends.empty:
            line_chart = alt.Chart(df_trends).mark_line(point=True).encode(
                x="date:T",
                y="followers",
                tooltip=["date","followers"]
            ).properties(title="Followers Over Time", width=700, height=400)
            st.altair_chart(line_chart, use_container_width=True)

    # ---- Recommendations ----
    with tabs[5]:
        st.subheader("🎥 Film Recommendations Based on Your Watched List")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        user_films = loop.run_until_complete(get_user_films(username, max_pages=5))

        # Popular films (contoh)
        popular_films = [
            {"title": "Everything Everywhere All At Once", "url": "/film/everything-everywhere-all-at-once/","poster":"https://m.media-amazon.com/images/I/81E0q8Zj0JL._AC_SY679_.jpg"},
            {"title": "Top Gun: Maverick", "url": "/film/top-gun-maverick/","poster":"https://m.media-amazon.com/images/I/71wE8cwPQQL._AC_SY679_.jpg"},
            {"title": "The Batman", "url": "/film/the-batman-2022/","poster":"https://m.media-amazon.com/images/I/71p1w+ULkNL._AC_SY679_.jpg"},
        ]
        recommendations = recommend_films_auto(user_films, popular_films)

        if recommendations:
            for film in recommendations:
                cols = st.columns([1,4])
                with cols[0]:
                    if film.get("poster"):
                        st.image(film["poster"], width=60)
                with cols[1]:
                    st.markdown(f"[**{film['title']}**](https://letterboxd.com{film['url']})", unsafe_allow_html=True)
        else:
            st.success("No recommendations available. You’ve watched all popular films listed!")

st.markdown("🐞 Found a bug? Contact me — Made by [Bynguts](https://boxd.it/9BaD9)")
