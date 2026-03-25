"""Collaborative filtering recommendation engine."""

from __future__ import annotations

from collections import defaultdict
from math import sqrt


def cosine_similarity(vec_a: dict[int, float], vec_b: dict[int, float]) -> float:
    common = set(vec_a).intersection(vec_b)
    if not common:
        return 0.0

    dot = sum(vec_a[item] * vec_b[item] for item in common)
    norm_a = sqrt(sum(v * v for v in vec_a.values()))
    norm_b = sqrt(sum(v * v for v in vec_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def build_user_vectors(ratings: list[tuple[str, int, float]]) -> dict[str, dict[int, float]]:
    matrix: dict[str, dict[int, float]] = defaultdict(dict)
    for username, book_id, rating in ratings:
        matrix[username][book_id] = float(rating)
    return matrix


def recommend_by_user_cf(
    username: str,
    ratings: list[tuple[str, int, float]],
    top_k_users: int = 5,
    top_n_books: int = 6,
) -> list[int]:
    """User-based collaborative filtering.

    1. Calculate similarity between current user and all users.
    2. Pick top-k nearest neighbors.
    3. Aggregate weighted ratings for unread books.
    """

    user_vectors = build_user_vectors(ratings)
    if username not in user_vectors:
        return []

    target = user_vectors[username]
    neighbors: list[tuple[str, float]] = []
    for other_user, vector in user_vectors.items():
        if other_user == username:
            continue
        sim = cosine_similarity(target, vector)
        if sim > 0:
            neighbors.append((other_user, sim))

    neighbors.sort(key=lambda x: x[1], reverse=True)
    neighbors = neighbors[:top_k_users]

    if not neighbors:
        return []

    scores: dict[int, float] = defaultdict(float)
    sim_sums: dict[int, float] = defaultdict(float)

    for other_user, sim in neighbors:
        for book_id, rating in user_vectors[other_user].items():
            if book_id in target:
                continue
            scores[book_id] += sim * rating
            sim_sums[book_id] += sim

    rank = []
    for book_id, score in scores.items():
        if sim_sums[book_id] > 0:
            rank.append((book_id, score / sim_sums[book_id]))

    rank.sort(key=lambda x: x[1], reverse=True)
    return [book_id for book_id, _ in rank[:top_n_books]]
