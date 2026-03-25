"""SQLite persistence layer for books, favorites and reviews."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from sample_data import BOOTSTRAP_RATINGS, SAMPLE_BOOKS

DB_PATH = Path(__file__).resolve().parent / "books.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL UNIQUE,
            author TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            cover_url TEXT,
            publish_year INTEGER
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            book_id INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(username, book_id),
            FOREIGN KEY(book_id) REFERENCES books(id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            book_id INTEGER NOT NULL,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            comment TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(book_id) REFERENCES books(id)
        )
        """
    )

    conn.commit()

    cur.execute("SELECT COUNT(1) AS count FROM books")
    count = cur.fetchone()["count"]
    if count == 0:
        cur.executemany(
            """
            INSERT INTO books (title, author, category, description, cover_url, publish_year)
            VALUES (:title, :author, :category, :description, :cover_url, :publish_year)
            """,
            SAMPLE_BOOKS,
        )
        conn.commit()

    cur.execute("SELECT COUNT(1) AS count FROM reviews")
    review_count = cur.fetchone()["count"]
    if review_count == 0:
        for username, title, rating in BOOTSTRAP_RATINGS:
            cur.execute("SELECT id FROM books WHERE title = ?", (title,))
            row = cur.fetchone()
            if row:
                cur.execute(
                    "INSERT INTO reviews (username, book_id, rating, comment) VALUES (?, ?, ?, ?)",
                    (username, row["id"], rating, "系统初始化评分"),
                )
        conn.commit()

    conn.close()


def fetch_categories() -> list[str]:
    conn = get_connection()
    rows = conn.execute("SELECT DISTINCT category FROM books ORDER BY category").fetchall()
    conn.close()
    return [r["category"] for r in rows]


def fetch_books(category: str | None = None, keyword: str | None = None) -> list[sqlite3.Row]:
    conn = get_connection()
    query = "SELECT * FROM books WHERE 1=1"
    params: list[str] = []

    if category and category != "全部":
        query += " AND category = ?"
        params.append(category)

    if keyword:
        query += " AND (title LIKE ? OR author LIKE ? OR description LIKE ?)"
        kw = f"%{keyword}%"
        params.extend([kw, kw, kw])

    query += " ORDER BY id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def get_book(book_id: int) -> sqlite3.Row | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    conn.close()
    return row


def add_favorite(username: str, book_id: int) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO favorites (username, book_id) VALUES (?, ?)",
        (username, book_id),
    )
    conn.commit()
    conn.close()


def remove_favorite(username: str, book_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM favorites WHERE username = ? AND book_id = ?", (username, book_id))
    conn.commit()
    conn.close()


def fetch_favorites(username: str) -> list[int]:
    conn = get_connection()
    rows = conn.execute("SELECT book_id FROM favorites WHERE username = ?", (username,)).fetchall()
    conn.close()
    return [r["book_id"] for r in rows]


def add_review(username: str, book_id: int, rating: int, comment: str) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO reviews (username, book_id, rating, comment) VALUES (?, ?, ?, ?)",
        (username, book_id, rating, comment),
    )
    conn.commit()
    conn.close()


def fetch_reviews(book_id: int) -> list[sqlite3.Row]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT username, rating, comment, created_at
        FROM reviews
        WHERE book_id = ?
        ORDER BY id DESC
        """,
        (book_id,),
    ).fetchall()
    conn.close()
    return rows


def fetch_top_books(limit: int = 6) -> list[sqlite3.Row]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT b.*, AVG(r.rating) AS avg_rating, COUNT(r.id) AS review_count
        FROM books b
        LEFT JOIN reviews r ON r.book_id = b.id
        GROUP BY b.id
        ORDER BY avg_rating DESC, review_count DESC, b.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return rows


def fetch_all_ratings() -> Iterable[sqlite3.Row]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT username, book_id, rating
        FROM reviews
        """
    ).fetchall()
    conn.close()
    return rows
