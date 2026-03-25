from __future__ import annotations

import math
import sys

import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

from database import (
    add_favorite,
    add_review,
    fetch_all_ratings,
    fetch_books,
    fetch_categories,
    fetch_favorites,
    fetch_reviews,
    fetch_top_books,
    get_book,
    init_db,
    remove_favorite,
)
from recommender import recommend_by_user_cf

def is_streamlit_context() -> bool:
    return get_script_run_ctx() is not None


@st.cache_resource
def bootstrap() -> bool:
    init_db()
    return True


def render_book_card(book, favorite_ids: set[int], username: str) -> None:
    with st.container(border=True):
        cols = st.columns([1, 2.5, 1.5])
        with cols[0]:
            st.image(book["cover_url"], use_container_width=True)
        with cols[1]:
            st.subheader(book["title"])
            st.caption(f"作者：{book['author']} ｜ 分类：{book['category']} ｜ 出版年份：{book['publish_year']}")
            st.write(book["description"])
        with cols[2]:
            st.markdown("### 操作")
            details_key = f"details_{book['id']}"
            if st.button("查看详情", key=details_key, use_container_width=True):
                st.session_state["selected_book_id"] = book["id"]

            if book["id"] in favorite_ids:
                if st.button("取消收藏", key=f"unfav_{book['id']}", use_container_width=True):
                    remove_favorite(username, book["id"])
                    st.success("已取消收藏")
                    st.rerun()
            else:
                if st.button("加入收藏", key=f"fav_{book['id']}", use_container_width=True):
                    add_favorite(username, book["id"])
                    st.success("已加入收藏")
                    st.rerun()


def paginate(items: list, page_size: int, page_key: str):
    total_pages = max(1, math.ceil(len(items) / page_size))
    current_page = st.session_state.get(page_key, 1)
    current_page = min(max(1, current_page), total_pages)
    st.session_state[page_key] = current_page

    start = (current_page - 1) * page_size
    end = start + page_size

    nav_cols = st.columns([1, 1, 2, 1, 1])
    with nav_cols[1]:
        if st.button("⬅ 上一页", disabled=current_page == 1, key=f"prev_{page_key}"):
            st.session_state[page_key] = current_page - 1
            st.rerun()
    with nav_cols[2]:
        st.markdown(f"<div style='text-align:center;'>第 <b>{current_page}</b> / {total_pages} 页</div>", unsafe_allow_html=True)
    with nav_cols[3]:
        if st.button("下一页 ➡", disabled=current_page == total_pages, key=f"next_{page_key}"):
            st.session_state[page_key] = current_page + 1
            st.rerun()

    return items[start:end]


def render_home(username: str) -> None:
    st.title("📚 智能书籍推荐系统")
    st.write("首页推荐结合热门书籍 + 协同过滤算法，为你生成个性化阅读列表。")

    top_books = fetch_top_books(limit=6)
    st.markdown("## 🌟 热门推荐")
    for book in top_books:
        with st.container(border=True):
            st.markdown(f"**{book['title']}** ｜ {book['author']} ｜ ⭐ {book['avg_rating']:.1f}（{book['review_count']} 条评价）")
            st.write(book["description"])

    ratings = [(row["username"], row["book_id"], row["rating"]) for row in fetch_all_ratings()]
    rec_ids = recommend_by_user_cf(username, ratings, top_k_users=5, top_n_books=6)

    st.markdown("## 🤖 个性化推荐（协同过滤）")
    if rec_ids:
        favorite_ids = set(fetch_favorites(username))
        for book_id in rec_ids:
            book = get_book(book_id)
            if book:
                render_book_card(book, favorite_ids, username)
    else:
        st.info("当前个性化数据不足，请先去【全部书籍】评分几本书。")


def render_catalog(username: str) -> None:
    st.markdown("## 📖 全部书籍")
    categories = ["全部"] + fetch_categories()

    filter_cols = st.columns([1.2, 2, 1])
    with filter_cols[0]:
        category = st.selectbox("分类筛选", options=categories)
    with filter_cols[1]:
        keyword = st.text_input("搜索（书名/作者/简介）", placeholder="例如：三体、东野圭吾、心理")
    with filter_cols[2]:
        page_size = st.selectbox("每页显示", options=[4, 6, 8], index=1)

    books = fetch_books(category=category, keyword=keyword.strip() if keyword else None)
    st.caption(f"共找到 {len(books)} 本书")

    paged_books = paginate(books, page_size=page_size, page_key="catalog_page")
    favorite_ids = set(fetch_favorites(username))

    for book in paged_books:
        render_book_card(book, favorite_ids, username)


def render_book_details(username: str, book_id: int) -> None:
    book = get_book(book_id)
    if not book:
        st.error("书籍不存在")
        return

    st.markdown("## 📘 书籍详情")
    head = st.columns([1, 2.5])
    with head[0]:
        st.image(book["cover_url"], use_container_width=True)
    with head[1]:
        st.subheader(book["title"])
        st.caption(f"作者：{book['author']} ｜ 分类：{book['category']} ｜ 出版年份：{book['publish_year']}")
        st.write(book["description"])

    if st.button("← 返回上一页"):
        st.session_state["selected_book_id"] = None
        st.rerun()

    st.markdown("### ✍️ 发表评价")
    with st.form(key=f"review_form_{book_id}", clear_on_submit=True):
        rating = st.slider("评分", min_value=1, max_value=5, value=5)
        comment = st.text_area("评论", placeholder="写下你对这本书的看法...")
        submit = st.form_submit_button("提交评价")
        if submit:
            add_review(username, book_id, rating, comment.strip())
            st.success("评价已提交！")
            st.rerun()

    st.markdown("### 🗨️ 用户评价")
    reviews = fetch_reviews(book_id)
    if not reviews:
        st.info("暂无评价，快来抢沙发！")
    for review in reviews:
        with st.container(border=True):
            stars = "⭐" * int(review["rating"])
            st.markdown(f"**{review['username']}**  {stars}")
            if review["comment"]:
                st.write(review["comment"])
            st.caption(review["created_at"])


def render_favorites(username: str) -> None:
    st.markdown("## ❤️ 我的收藏")
    favorite_ids = fetch_favorites(username)
    if not favorite_ids:
        st.info("你还没有收藏书籍。")
        return

    books = [get_book(book_id) for book_id in favorite_ids]
    books = [b for b in books if b is not None]
    for book in books:
        render_book_card(book, set(favorite_ids), username)


def main() -> None:
    if not is_streamlit_context():
        print("请使用 Streamlit 启动应用，而不是直接 python 运行。")
        print("正确命令：streamlit run book_recommender/app.py")
        sys.exit(0)

    st.set_page_config(page_title="智能书籍推荐系统", page_icon="📚", layout="wide")
    bootstrap()

    if "username" not in st.session_state:
        st.session_state["username"] = "guest"
    if "selected_book_id" not in st.session_state:
        st.session_state["selected_book_id"] = None

    with st.sidebar:
        st.header("👤 用户中心")
        username = st.text_input("用户名", value=st.session_state["username"])
        st.session_state["username"] = username.strip() or "guest"

        st.markdown("---")
        page = st.radio("导航", ["首页", "全部书籍", "我的收藏"], index=0)
        st.caption("提示：在“全部书籍”中搜索、筛选并点击“查看详情”进行评分。")

    if st.session_state["selected_book_id"] is not None:
        render_book_details(st.session_state["username"], st.session_state["selected_book_id"])
        return

    if page == "首页":
        render_home(st.session_state["username"])
    elif page == "全部书籍":
        render_catalog(st.session_state["username"])
    else:
        render_favorites(st.session_state["username"])


if __name__ == "__main__":
    main()
