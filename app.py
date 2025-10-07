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
import requests

# -------------------------- Settings --------------------------
nest_asyncio.apply()
semaphore = asyncio.Semaphore(5)
DATA_FOLDER = "user_data"
os.makedirs(DATA_FOLDER, exist_ok=True)

TMDB_API_KEY = "9ccb7f50fc9ac3bb4fd05b18333aa100"

# -------------------------- Async Helpers --------------------------
async def fetch_page(session, url):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*"
    }
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
        tag = soup.select_one(f'a[href="/{username.lower()}/{tab}/"] > span.value')
        return int(tag.text.replace(',', '')) if tag else 0
    max_pages_followers = int(get_count("followers") / 25) + 1
    max_pages_following = int(get_count("following") / 25) + 1
    return max_pages_followers, max_pages_following

async def get_user_list(username, tab, max_pages_followers, max_pages_following):
    urls = [
        f"https://letterboxd.com/{username}/{tab}/page/{page}/"
        for page in range(1, (max_pages_followers if tab=="followers" else max_pages_following)+1)
    ]
    user_list = []
    async with aiohttp.ClientSession() as session:
        htmls = await asyncio.gather(*[fetch_page(session, url) for url in urls])
        for html in htmls:
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")
            user_blocks = soup.select("div.person-summary")
            for user in user_blocks:
                avatar_tag = user.select_one("a.avatar")
                if avatar_tag and avatar_tag.has_attr("href"):
                    user_list.append(avatar_tag["href"].strip("/"))
    return user_list

async def get_user_films(username):
    url = f"https://letterboxd.com/{username}/films/"
    async with aiohttp.ClientSession() as session:
        html = await fetch_page(session, url)
    soup = BeautifulSoup(html, "html.parser")
    films = []
    for film_tag in soup.select("ul.poster-list li"):
        title_tag = film_tag.select_one("img")
        link_tag = film_tag.select_one("a")
        if title_tag or link_tag:
            title = title_tag["alt"] if title_tag and title_tag.has_attr("alt") else None
            if not title and link_tag and link_tag.has_attr("title"):
                title = link_tag["title"]
            if title:
                films.append({
                    "title": title,
                    "poster": title_tag.get("data-src") if title_tag else None,
                    "url": link_tag["href"] if link_tag and link_tag.has_attr("href") else None
                })
    if not films:
        films = [{"title": "Everything Everywhere All At Once", "poster": None, "url": "/film/everything-everywhere-all-at-once/"}]
    st.write(f"[DEBUG] {username} films scraped: {len(films)}")
    return films

# -------------------------- TMDb Recommendations --------------------------
def get_recommendations_tmdb(user_films, max_recommendations=10):
    recommended = []
    seen_titles = set(f["title"].lower() for f in user_films)
    for film in user_films:
        query = film["title"]
        url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={query}"
        try:
            res = requests.get(url).json()
            results = res.get("results", [])
            for r in results[:3]:
                title = r["title"]
                if title.lower() in seen_titles:
                    continue
                recommended.append({
                    "title": title,
                    "poster": f"https://image.tmdb.org/t/p/w200{r['poster_path']}" if r.get("poster_path") else None,
                    "url": f"https://www.themoviedb.org/movie/{r['id']}"
                })
                seen_titles.add(title.lower())
                if len(recommended) >= max_recommendations:
                    return recommended
        except:
            continue
    return recommended

# -------------------------- Data Management --------------------------
@st.cache_data
def fetch_data(username):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    max_pages_followers, max_pages_following = loop.run_until_complete(get_profile_data(username))
    followers = loop.run_until_complete(get_user_list(username, "followers", max_pages_followers, max_pages_following))
    following = loop.run_until_complete(get_user_list(username, "following", max_pages_followers, max_pages_following))
    return followers, following

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

# -------------------------- Streamlit UI --------------------------
st.set_page_config(page_title="Letterboxd Tracker", layout="wide")
st.title("🎬 Letterboxd Daily Tracker & Dashboard")

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
    tabs = st.tabs(["Summary & Mutuals", "Doesn't Follow You Back", "You Don't Follow Back", "Statistics", "Trends", "Recommended Films"])

    # ---- Recommended Films ----
    with tabs[5]:
        st.subheader("Film Recommendations Based on Your Watched List")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        user_films = loop.run_until_complete(get_user_films(username))
        
        with st.spinner("Fetching recommendations from TMDb..."):
            recommendations = get_recommendations_tmdb(user_films)

        if not recommendations:
            st.info("No recommendations found yet. Try again later!")
        for film in recommendations:
            cols = st.columns([1,4])
            with cols[0]:
                if film.get("poster"):
                    st.image(film["poster"], width=50)
            with cols[1]:
                st.markdown(f"[{film['title']}]({film['url']})")
