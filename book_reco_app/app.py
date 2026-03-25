import math
import os
import sqlite3
from datetime import datetime
from functools import wraps

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
DATABASE = os.path.join(BASE_DIR, "books.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = "book-recommender-secret-key"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def login_required(role=None):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("请先登录。", "warning")
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                flash("无权限访问该页面。", "danger")
                return redirect(url_for("index"))
            return view_func(*args, **kwargs)

        return wrapper

    return decorator


def init_db():
    db = sqlite3.connect(DATABASE)
    with open(os.path.join(BASE_DIR, "schema.sql"), "r", encoding="utf-8") as f:
        db.executescript(f.read())

    admin_pwd = generate_password_hash("admin123")
    demo_pwd = generate_password_hash("user123")

    db.execute(
        "INSERT INTO users(username, password_hash, role) VALUES (?, ?, ?)",
        ("admin", admin_pwd, "admin"),
    )
    db.execute(
        "INSERT INTO users(username, password_hash, role) VALUES (?, ?, ?)",
        ("alice", demo_pwd, "user"),
    )
    db.execute(
        "INSERT INTO users(username, password_hash, role) VALUES (?, ?, ?)",
        ("bob", demo_pwd, "user"),
    )

    books = [
        ("三体", "刘慈欣", "科幻", "地球文明与三体文明的史诗碰撞。", "https://images.unsplash.com/photo-1481627834876-b7833e8f5570"),
        ("活着", "余华", "文学", "平凡人生在时代洪流中的坚韧。", "https://images.unsplash.com/photo-1512820790803-83ca734da794"),
        ("人类简史", "尤瓦尔·赫拉利", "历史", "从认知革命到现代社会的人类发展脉络。", "https://images.unsplash.com/photo-1495446815901-a7297e633e8d"),
        ("白夜行", "东野圭吾", "悬疑", "跨越二十年的罪与救赎。", "https://images.unsplash.com/photo-1507842217343-583bb7270b66"),
        ("原则", "瑞·达利欧", "商业", "生活与工作原则的系统总结。", "https://images.unsplash.com/photo-1455885666463-9d5f1854d761"),
        ("百年孤独", "加西亚·马尔克斯", "文学", "魔幻现实主义的家族兴衰史。", "https://images.unsplash.com/photo-1473755504818-b72b6dfdc226"),
        ("时间简史", "斯蒂芬·霍金", "科普", "宇宙起源与时空奥秘的经典导读。", "https://images.unsplash.com/photo-1463320726281-696a485928c7"),
        ("穷查理宝典", "彼得·考夫曼", "商业", "多元思维模型与投资智慧。", "https://images.unsplash.com/photo-1524995997946-a1c2e315a42f"),
        ("嫌疑人X的献身", "东野圭吾", "悬疑", "天才数学家与完美不在场证明。", "https://images.unsplash.com/photo-1519682337058-a94d519337bc"),
        ("乡土中国", "费孝通", "社会", "中国基层社会结构的深刻观察。", "https://images.unsplash.com/photo-1516979187457-637abb4f9353"),
    ]

    for book in books:
        db.execute(
            "INSERT INTO books(title, author, category, description, cover_url) VALUES (?, ?, ?, ?, ?)",
            book,
        )

    ratings = [
        (2, 1, 5, "科幻迷必读"),
        (2, 2, 5, "非常感人"),
        (2, 3, 4, "视角独特"),
        (2, 4, 4, "结构很巧妙"),
        (2, 5, 3, "干货很多"),
        (3, 1, 4, "想象力惊人"),
        (3, 2, 4, "读完很压抑但很真实"),
        (3, 6, 5, "文笔太美了"),
        (3, 8, 4, "思维模型很受用"),
        (3, 9, 5, "结局震撼"),
    ]

    for r in ratings:
        db.execute(
            "INSERT INTO ratings(user_id, book_id, score, comment, created_at) VALUES (?, ?, ?, ?, ?)",
            (*r, datetime.utcnow().isoformat()),
        )

    favorites = [(2, 1), (2, 2), (3, 6), (3, 9)]
    for fav in favorites:
        db.execute(
            "INSERT INTO favorites(user_id, book_id) VALUES (?, ?)",
            fav,
        )

    db.commit()
    db.close()


def cosine_similarity(vec_a, vec_b):
    common = set(vec_a) & set(vec_b)
    if not common:
        return 0.0
    dot = sum(vec_a[k] * vec_b[k] for k in common)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def collaborative_recommendations(user_id, top_n=6):
    db = get_db()
    rows = db.execute("SELECT user_id, book_id, score FROM ratings").fetchall()

    user_ratings = {}
    for row in rows:
        user_ratings.setdefault(row["user_id"], {})[row["book_id"]] = row["score"]

    target = user_ratings.get(user_id, {})
    similarities = {}
    for other_user, ratings in user_ratings.items():
        if other_user == user_id:
            continue
        sim = cosine_similarity(target, ratings)
        if sim > 0:
            similarities[other_user] = sim

    score_candidates = {}
    for other_user, sim in similarities.items():
        for book_id, score in user_ratings[other_user].items():
            if book_id in target:
                continue
            score_candidates.setdefault(book_id, {"num": 0.0, "den": 0.0})
            score_candidates[book_id]["num"] += sim * score
            score_candidates[book_id]["den"] += sim

    ranked = []
    for book_id, vals in score_candidates.items():
        if vals["den"] > 0:
            ranked.append((book_id, vals["num"] / vals["den"]))

    ranked.sort(key=lambda x: x[1], reverse=True)
    book_ids = [bid for bid, _ in ranked[:top_n]]

    if not book_ids:
        fallback = db.execute(
            """
            SELECT b.id FROM books b
            LEFT JOIN ratings r ON b.id = r.book_id
            GROUP BY b.id
            ORDER BY AVG(r.score) DESC NULLS LAST
            LIMIT ?
            """,
            (top_n,),
        ).fetchall()
        book_ids = [r["id"] for r in fallback]

    if not book_ids:
        return []

    placeholders = ",".join("?" for _ in book_ids)
    books = db.execute(
        f"SELECT * FROM books WHERE id IN ({placeholders})",
        book_ids,
    ).fetchall()
    id_to_book = {b["id"]: b for b in books}
    return [id_to_book[bid] for bid in book_ids if bid in id_to_book]


@app.route("/")
def index():
    db = get_db()
    page = int(request.args.get("page", 1))
    per_page = 6
    keyword = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()

    where = []
    params = []

    if keyword:
        where.append("(title LIKE ? OR author LIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    if category:
        where.append("category = ?")
        params.append(category)

    where_clause = f"WHERE {' AND '.join(where)}" if where else ""

    total = db.execute(
        f"SELECT COUNT(*) AS c FROM books {where_clause}",
        params,
    ).fetchone()["c"]

    total_pages = max(1, math.ceil(total / per_page))
    page = min(max(1, page), total_pages)
    offset = (page - 1) * per_page

    books = db.execute(
        f"SELECT * FROM books {where_clause} ORDER BY id DESC LIMIT ? OFFSET ?",
        [*params, per_page, offset],
    ).fetchall()

    categories = db.execute("SELECT DISTINCT category FROM books ORDER BY category").fetchall()

    recommendations = []
    if "user_id" in session and session.get("role") == "user":
        recommendations = collaborative_recommendations(session["user_id"], top_n=4)

    return render_template(
        "index.html",
        books=books,
        categories=categories,
        current_page=page,
        total_pages=total_pages,
        keyword=keyword,
        category=category,
        recommendations=recommendations,
    )


@app.route("/book/<int:book_id>", methods=["GET", "POST"])
def book_detail(book_id):
    db = get_db()
    book = db.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    if not book:
        flash("书籍不存在。", "danger")
        return redirect(url_for("index"))

    if request.method == "POST":
        if "user_id" not in session:
            flash("请先登录后再评价。", "warning")
            return redirect(url_for("login"))

        score = int(request.form.get("score", 0))
        comment = request.form.get("comment", "").strip()
        if score < 1 or score > 5:
            flash("评分需在1到5之间。", "danger")
            return redirect(url_for("book_detail", book_id=book_id))

        existing = db.execute(
            "SELECT id FROM ratings WHERE user_id = ? AND book_id = ?",
            (session["user_id"], book_id),
        ).fetchone()

        if existing:
            db.execute(
                "UPDATE ratings SET score = ?, comment = ?, created_at = ? WHERE id = ?",
                (score, comment, datetime.utcnow().isoformat(), existing["id"]),
            )
        else:
            db.execute(
                "INSERT INTO ratings(user_id, book_id, score, comment, created_at) VALUES (?, ?, ?, ?, ?)",
                (session["user_id"], book_id, score, comment, datetime.utcnow().isoformat()),
            )
        db.commit()
        flash("评价提交成功。", "success")
        return redirect(url_for("book_detail", book_id=book_id))

    ratings = db.execute(
        """
        SELECT r.*, u.username
        FROM ratings r
        JOIN users u ON r.user_id = u.id
        WHERE r.book_id = ?
        ORDER BY r.created_at DESC
        """,
        (book_id,),
    ).fetchall()

    avg_score = db.execute(
        "SELECT ROUND(AVG(score), 2) AS avg_score FROM ratings WHERE book_id = ?",
        (book_id,),
    ).fetchone()["avg_score"]

    is_favorited = False
    if "user_id" in session:
        favor = db.execute(
            "SELECT id FROM favorites WHERE user_id = ? AND book_id = ?",
            (session["user_id"], book_id),
        ).fetchone()
        is_favorited = favor is not None

    return render_template(
        "book_detail.html",
        book=book,
        ratings=ratings,
        avg_score=avg_score,
        is_favorited=is_favorited,
    )


@app.route("/favorite/<int:book_id>")
@login_required(role="user")
def toggle_favorite(book_id):
    db = get_db()
    existing = db.execute(
        "SELECT id FROM favorites WHERE user_id = ? AND book_id = ?",
        (session["user_id"], book_id),
    ).fetchone()

    if existing:
        db.execute("DELETE FROM favorites WHERE id = ?", (existing["id"],))
        flash("已取消收藏。", "info")
    else:
        db.execute(
            "INSERT INTO favorites(user_id, book_id) VALUES (?, ?)",
            (session["user_id"], book_id),
        )
        flash("收藏成功。", "success")

    db.commit()
    return redirect(request.referrer or url_for("index"))


@app.route("/favorites")
@login_required(role="user")
def favorites_page():
    db = get_db()
    books = db.execute(
        """
        SELECT b.*
        FROM favorites f
        JOIN books b ON f.book_id = b.id
        WHERE f.user_id = ?
        ORDER BY f.id DESC
        """,
        (session["user_id"],),
    ).fetchall()
    return render_template("favorites.html", books=books)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            flash("登录成功。", "success")
            return redirect(url_for("admin_dashboard" if user["role"] == "admin" else "index"))

        flash("用户名或密码错误。", "danger")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if len(username) < 3 or len(password) < 6:
            flash("用户名至少3位，密码至少6位。", "danger")
            return redirect(url_for("register"))

        db = get_db()
        exists = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if exists:
            flash("用户名已存在。", "warning")
            return redirect(url_for("register"))

        db.execute(
            "INSERT INTO users(username, password_hash, role) VALUES (?, ?, 'user')",
            (username, generate_password_hash(password)),
        )
        db.commit()
        flash("注册成功，请登录。", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("已退出登录。", "info")
    return redirect(url_for("index"))


@app.route("/admin")
@login_required(role="admin")
def admin_dashboard():
    db = get_db()
    stats = {
        "users": db.execute("SELECT COUNT(*) c FROM users WHERE role='user'").fetchone()["c"],
        "books": db.execute("SELECT COUNT(*) c FROM books").fetchone()["c"],
        "ratings": db.execute("SELECT COUNT(*) c FROM ratings").fetchone()["c"],
        "favorites": db.execute("SELECT COUNT(*) c FROM favorites").fetchone()["c"],
    }
    books = db.execute("SELECT * FROM books ORDER BY id DESC").fetchall()
    return render_template("admin.html", stats=stats, books=books)


@app.route("/admin/book/new", methods=["GET", "POST"])
@login_required(role="admin")
def admin_new_book():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        author = request.form.get("author", "").strip()
        category = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()
        cover_url = request.form.get("cover_url", "").strip()

        if not title or not author or not category:
            flash("标题、作者、分类为必填项。", "danger")
            return redirect(url_for("admin_new_book"))

        db = get_db()
        db.execute(
            "INSERT INTO books(title, author, category, description, cover_url) VALUES (?, ?, ?, ?, ?)",
            (title, author, category, description, cover_url),
        )
        db.commit()
        flash("书籍新增成功。", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("admin_edit_book.html", book=None)


@app.route("/admin/book/<int:book_id>/edit", methods=["GET", "POST"])
@login_required(role="admin")
def admin_edit_book(book_id):
    db = get_db()
    book = db.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    if not book:
        flash("书籍不存在。", "danger")
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        db.execute(
            """
            UPDATE books
            SET title = ?, author = ?, category = ?, description = ?, cover_url = ?
            WHERE id = ?
            """,
            (
                request.form.get("title", "").strip(),
                request.form.get("author", "").strip(),
                request.form.get("category", "").strip(),
                request.form.get("description", "").strip(),
                request.form.get("cover_url", "").strip(),
                book_id,
            ),
        )
        db.commit()
        flash("书籍更新成功。", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("admin_edit_book.html", book=book)


@app.route("/admin/book/<int:book_id>/delete")
@login_required(role="admin")
def admin_delete_book(book_id):
    db = get_db()
    db.execute("DELETE FROM books WHERE id = ?", (book_id,))
    db.commit()
    flash("书籍已删除。", "info")
    return redirect(url_for("admin_dashboard"))


if __name__ == "__main__":
    if not os.path.exists(DATABASE):
        init_db()
    app.run(debug=True)
