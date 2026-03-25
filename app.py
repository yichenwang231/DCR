import os
import sqlite3
from functools import wraps
from typing import Dict, List, Tuple

import numpy as np
import requests
from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "novel_recommender.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            genre TEXT NOT NULL,
            description TEXT,
            avg_rating REAL DEFAULT 0,
            rating_count INTEGER DEFAULT 0,
            cover_url TEXT,
            external_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            book_id INTEGER NOT NULL,
            rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
            comment TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, book_id),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(book_id) REFERENCES books(id)
        );
        """
    )
    admin = db.execute("SELECT id FROM users WHERE username='admin'").fetchone()
    if not admin:
        db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
            ("admin", generate_password_hash("admin123")),
        )
    seed = db.execute("SELECT COUNT(1) c FROM books").fetchone()["c"]
    if seed == 0:
        db.executemany(
            """
            INSERT INTO books (title, author, genre, description, cover_url)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("三体", "刘慈欣", "科幻", "地球文明与三体文明的震撼交锋。", "https://covers.openlibrary.org/b/isbn/9787536692930-M.jpg"),
                ("活着", "余华", "现实", "普通人在时代洪流中的生命韧性。", "https://covers.openlibrary.org/b/isbn/9787506365437-M.jpg"),
                ("白夜行", "东野圭吾", "悬疑", "跨越二十年的犯罪与救赎。", "https://covers.openlibrary.org/b/isbn/9787544242516-M.jpg"),
                ("解忧杂货店", "东野圭吾", "治愈", "时空交错中传递希望和答案。", "https://covers.openlibrary.org/b/isbn/9787544270878-M.jpg"),
                ("百年孤独", "加西亚·马尔克斯", "魔幻现实", "布恩迪亚家族七代人的命运。", "https://covers.openlibrary.org/b/isbn/9787544253994-M.jpg"),
            ],
        )
    db.commit()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("请先登录。", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            flash("需要管理员权限。", "danger")
            return redirect(url_for("index"))
        return view(*args, **kwargs)

    return wrapped


def refresh_book_rating(book_id: int):
    db = get_db()
    row = db.execute(
        "SELECT AVG(rating) avg_rating, COUNT(*) cnt FROM ratings WHERE book_id=?", (book_id,)
    ).fetchone()
    avg_rating = round(float(row["avg_rating"]), 2) if row["avg_rating"] is not None else 0
    db.execute(
        "UPDATE books SET avg_rating=?, rating_count=? WHERE id=?",
        (avg_rating, row["cnt"], book_id),
    )
    db.commit()


def collaborative_recommend(user_id: int, top_n: int = 8) -> List[sqlite3.Row]:
    db = get_db()
    ratings = db.execute("SELECT user_id, book_id, rating FROM ratings").fetchall()
    if len(ratings) < 4:
        return []

    users = sorted(set(r["user_id"] for r in ratings))
    books = sorted(set(r["book_id"] for r in ratings))
    user_index = {u: i for i, u in enumerate(users)}
    book_index = {b: i for i, b in enumerate(books)}

    matrix = np.zeros((len(users), len(books)), dtype=np.float32)
    mask = np.zeros((len(users), len(books)), dtype=np.float32)

    for r in ratings:
        ui = user_index[r["user_id"]]
        bi = book_index[r["book_id"]]
        matrix[ui, bi] = float(r["rating"])
        mask[ui, bi] = 1.0

    if user_id not in user_index:
        return []

    user_means = np.divide(
        matrix.sum(axis=1),
        np.maximum(mask.sum(axis=1), 1),
    )
    centered = (matrix - user_means[:, None]) * mask

    target_i = user_index[user_id]
    target_vec = centered[target_i]
    sims = []
    for i in range(len(users)):
        if i == target_i:
            sims.append(0.0)
            continue
        num = float(np.dot(target_vec, centered[i]))
        den = float(np.linalg.norm(target_vec) * np.linalg.norm(centered[i]) + 1e-8)
        sims.append(max(num / den, 0.0))
    sims = np.array(sims, dtype=np.float32)

    scores: Dict[int, float] = {}
    for b in books:
        bi = book_index[b]
        if mask[target_i, bi] > 0:
            continue
        raters = mask[:, bi] > 0
        if not np.any(raters):
            continue
        weights = sims[raters]
        if float(weights.sum()) <= 0:
            continue
        candidate_ratings = matrix[raters, bi]
        pred = float(np.dot(weights, candidate_ratings) / (weights.sum() + 1e-8))
        scores[b] = pred

    if not scores:
        return []

    top_ids = [bid for bid, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_n]]
    placeholder = ",".join("?" for _ in top_ids)
    rows = db.execute(
        f"SELECT * FROM books WHERE id IN ({placeholder})",
        top_ids,
    ).fetchall()
    by_id = {r["id"]: r for r in rows}
    return [by_id[i] for i in top_ids if i in by_id]


def fetch_books_from_openlibrary(keyword: str, limit: int = 12) -> List[Tuple]:
    url = "https://openlibrary.org/search.json"
    resp = requests.get(url, params={"q": keyword, "limit": limit}, timeout=15)
    resp.raise_for_status()
    data = resp.json().get("docs", [])
    result = []
    for d in data:
        title = d.get("title")
        if not title:
            continue
        author = ", ".join(d.get("author_name", ["未知作者"])[:2])
        genre = (d.get("subject", ["未分类"]) or ["未分类"])[0]
        year = d.get("first_publish_year")
        desc = f"来自OpenLibrary抓取。首版年份：{year or '未知'}。"
        cover_id = d.get("cover_i")
        cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else None
        external_id = d.get("key")
        result.append((title, author, genre, desc, cover_url, external_id))
    return result


@app.route("/")
def index():
    db = get_db()
    q = request.args.get("q", "").strip()
    author = request.args.get("author", "").strip()
    genre = request.args.get("genre", "").strip()
    min_rating = request.args.get("min_rating", "").strip()

    query = "SELECT * FROM books WHERE 1=1"
    params = []
    if q:
        query += " AND title LIKE ?"
        params.append(f"%{q}%")
    if author:
        query += " AND author LIKE ?"
        params.append(f"%{author}%")
    if genre:
        query += " AND genre LIKE ?"
        params.append(f"%{genre}%")
    if min_rating:
        try:
            query += " AND avg_rating >= ?"
            params.append(float(min_rating))
        except ValueError:
            pass

    query += " ORDER BY avg_rating DESC, rating_count DESC, id DESC"
    books = db.execute(query, params).fetchall()

    recs = []
    if session.get("user_id"):
        recs = collaborative_recommend(session["user_id"])
        if not recs:
            recs = db.execute(
                "SELECT * FROM books ORDER BY avg_rating DESC, rating_count DESC LIMIT 8"
            ).fetchall()

    return render_template("index.html", books=books, recs=recs)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("用户名和密码不能为空。", "danger")
            return redirect(url_for("register"))
        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'user')",
                (username, generate_password_hash(password)),
            )
            db.commit()
            flash("注册成功，请登录。", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("用户名已存在。", "danger")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            flash("登录成功。", "success")
            return redirect(url_for("index"))
        flash("用户名或密码错误。", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("你已安全退出。", "info")
    return redirect(url_for("index"))


@app.route("/book/<int:book_id>")
def book_detail(book_id: int):
    db = get_db()
    book = db.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
    if not book:
        flash("图书不存在。", "warning")
        return redirect(url_for("index"))

    comments = db.execute(
        """
        SELECT r.*, u.username FROM ratings r
        JOIN users u ON r.user_id = u.id
        WHERE r.book_id=?
        ORDER BY r.updated_at DESC
        """,
        (book_id,),
    ).fetchall()

    user_rating = None
    if session.get("user_id"):
        user_rating = db.execute(
            "SELECT * FROM ratings WHERE user_id=? AND book_id=?",
            (session["user_id"], book_id),
        ).fetchone()

    return render_template(
        "book_detail.html", book=book, comments=comments, user_rating=user_rating
    )


@app.route("/rate/<int:book_id>", methods=["POST"])
@login_required
def rate_book(book_id: int):
    try:
        rating = int(request.form.get("rating", "0"))
    except ValueError:
        rating = 0
    comment = request.form.get("comment", "").strip()
    if rating < 1 or rating > 5:
        flash("评分应为1~5。", "danger")
        return redirect(url_for("book_detail", book_id=book_id))

    db = get_db()
    existing = db.execute(
        "SELECT id FROM ratings WHERE user_id=? AND book_id=?",
        (session["user_id"], book_id),
    ).fetchone()
    if existing:
        db.execute(
            "UPDATE ratings SET rating=?, comment=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (rating, comment, existing["id"]),
        )
    else:
        db.execute(
            "INSERT INTO ratings (user_id, book_id, rating, comment) VALUES (?, ?, ?, ?)",
            (session["user_id"], book_id, rating, comment),
        )
    db.commit()
    refresh_book_rating(book_id)
    flash("评分已提交。", "success")
    return redirect(url_for("book_detail", book_id=book_id))


@app.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    db = get_db()
    users = db.execute("SELECT id, username, role, created_at FROM users ORDER BY id DESC").fetchall()
    books = db.execute("SELECT * FROM books ORDER BY id DESC").fetchall()
    ratings = db.execute(
        """
        SELECT r.id, u.username, b.title, r.rating, r.comment, r.updated_at
        FROM ratings r
        JOIN users u ON r.user_id = u.id
        JOIN books b ON r.book_id = b.id
        ORDER BY r.updated_at DESC
        """
    ).fetchall()
    return render_template("admin.html", users=users, books=books, ratings=ratings)


@app.route("/admin/book/save", methods=["POST"])
@login_required
@admin_required
def admin_save_book():
    db = get_db()
    book_id = request.form.get("book_id", "").strip()
    data = (
        request.form.get("title", "").strip(),
        request.form.get("author", "").strip(),
        request.form.get("genre", "").strip(),
        request.form.get("description", "").strip(),
        request.form.get("cover_url", "").strip() or None,
    )
    if not all(data[:3]):
        flash("书名、作者、类型必填。", "danger")
        return redirect(url_for("admin_dashboard"))

    if book_id:
        db.execute(
            """
            UPDATE books SET title=?, author=?, genre=?, description=?, cover_url=?
            WHERE id=?
            """,
            (*data, int(book_id)),
        )
        flash("图书已更新。", "success")
    else:
        db.execute(
            """
            INSERT INTO books (title, author, genre, description, cover_url)
            VALUES (?, ?, ?, ?, ?)
            """,
            data,
        )
        flash("图书已新增。", "success")
    db.commit()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/book/delete/<int:book_id>")
@login_required
@admin_required
def admin_delete_book(book_id: int):
    db = get_db()
    db.execute("DELETE FROM ratings WHERE book_id=?", (book_id,))
    db.execute("DELETE FROM books WHERE id=?", (book_id,))
    db.commit()
    flash("图书及相关评分已删除。", "info")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/user/save", methods=["POST"])
@login_required
@admin_required
def admin_save_user():
    db = get_db()
    user_id = request.form.get("user_id", "").strip()
    username = request.form.get("username", "").strip()
    role = request.form.get("role", "user").strip()
    password = request.form.get("password", "").strip()

    if not username or role not in {"user", "admin"}:
        flash("用户信息不完整。", "danger")
        return redirect(url_for("admin_dashboard"))

    try:
        if user_id:
            if password:
                db.execute(
                    "UPDATE users SET username=?, role=?, password_hash=? WHERE id=?",
                    (username, role, generate_password_hash(password), int(user_id)),
                )
            else:
                db.execute(
                    "UPDATE users SET username=?, role=? WHERE id=?",
                    (username, role, int(user_id)),
                )
            flash("用户已更新。", "success")
        else:
            if not password:
                flash("新增用户必须设置密码。", "warning")
                return redirect(url_for("admin_dashboard"))
            db.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, generate_password_hash(password), role),
            )
            flash("用户已新增。", "success")
        db.commit()
    except sqlite3.IntegrityError:
        flash("用户名重复，请更换。", "danger")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/user/delete/<int:user_id>")
@login_required
@admin_required
def admin_delete_user(user_id: int):
    if user_id == session.get("user_id"):
        flash("不能删除当前登录管理员。", "warning")
        return redirect(url_for("admin_dashboard"))
    db = get_db()
    db.execute("DELETE FROM ratings WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM users WHERE id=?", (user_id,))
    db.commit()
    flash("用户已删除。", "info")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/rating/delete/<int:rating_id>")
@login_required
@admin_required
def admin_delete_rating(rating_id: int):
    db = get_db()
    row = db.execute("SELECT book_id FROM ratings WHERE id=?", (rating_id,)).fetchone()
    if row:
        db.execute("DELETE FROM ratings WHERE id=?", (rating_id,))
        db.commit()
        refresh_book_rating(row["book_id"])
    flash("评分已删除。", "info")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/import", methods=["POST"])
@login_required
@admin_required
def admin_import_books():
    keyword = request.form.get("keyword", "novel").strip() or "novel"
    db = get_db()
    try:
        items = fetch_books_from_openlibrary(keyword)
        added = 0
        for item in items:
            exists = db.execute(
                "SELECT id FROM books WHERE title=? AND author=?", (item[0], item[1])
            ).fetchone()
            if exists:
                continue
            db.execute(
                """
                INSERT INTO books (title, author, genre, description, cover_url, external_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                item,
            )
            added += 1
        db.commit()
        flash(f"联网导入完成，新增 {added} 本图书。", "success")
    except Exception as e:
        flash(f"导入失败：{e}", "danger")
    return redirect(url_for("admin_dashboard"))


if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
