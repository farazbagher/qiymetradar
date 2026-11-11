import json
import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

SCHEMA = Path(__file__).with_name("schema.sql")


@contextmanager
def get_conn():
    conn = psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def migrate() -> None:
    with get_conn() as conn:
        conn.execute(SCHEMA.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- scraping
def create_run(site: str, strategy: str, status: str, items: int = 0, error: str = "", seconds: float = 0.0) -> int:
    with get_conn() as conn:
        return conn.execute(
            "INSERT INTO scrape_runs (site, strategy, status, items, error, seconds) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
            (site, strategy, status, items, error, seconds)).fetchone()["id"]


def last_ok_runs(site: str, limit: int = 2) -> list:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM scrape_runs WHERE site=%s AND status='ok' ORDER BY id DESC LIMIT %s", (site, limit)).fetchall()


def snapshot_map(run_id: int) -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT p.slug, p.name, p.url, s.price, s.currency, s.in_stock FROM price_snapshots s JOIN products p ON p.id=s.product_id WHERE s.run_id=%s",
            (run_id,)).fetchall()
    return {r["slug"]: {"name": r["name"], "price": float(r["price"]), "in_stock": r["in_stock"], "currency": r["currency"], "url": r["url"]} for r in rows}


def save_snapshots(run_id: int, site: str, items: dict) -> None:
    """items: {slug: {name, price, currency, in_stock, url}}"""
    with get_conn() as conn:
        for slug, it in items.items():
            pid = conn.execute(
                "INSERT INTO products (site, slug, name, url) VALUES (%s,%s,%s,%s) "
                "ON CONFLICT (site, slug) DO UPDATE SET name=EXCLUDED.name, url=CASE WHEN EXCLUDED.url<>'' THEN EXCLUDED.url ELSE products.url END "
                "RETURNING id", (site, slug, it["name"], it.get("url", ""))).fetchone()["id"]
            conn.execute("INSERT INTO price_snapshots (product_id, run_id, price, currency, in_stock) VALUES (%s,%s,%s,%s,%s)",
                         (pid, run_id, it["price"], it.get("currency", "AZN"), it.get("in_stock", True)))


def list_runs(limit: int = 20) -> list:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM scrape_runs ORDER BY id DESC LIMIT %s", (limit,)).fetchall()


def list_products(site: str | None = None) -> list:
    with get_conn() as conn:
        q = ("SELECT p.id, p.site, p.slug, p.name, p.url, s.price, s.currency, s.in_stock, s.run_id FROM products p "
             "JOIN LATERAL (SELECT * FROM price_snapshots WHERE product_id=p.id ORDER BY run_id DESC LIMIT 1) s ON TRUE "
             + ("WHERE p.site=%s " if site else "") + "ORDER BY p.name")
        rows = conn.execute(q, (site,) if site else ()).fetchall()
    for r in rows:
        r["price"] = float(r["price"])
    return rows


def product_history(product_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT s.run_id, s.price, s.in_stock, s.created_at FROM price_snapshots s WHERE s.product_id=%s ORDER BY s.run_id", (product_id,)).fetchall()
    for r in rows:
        r["price"] = float(r["price"])
    return rows


def find_product(query: str) -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT id, site, slug, name FROM products WHERE name ILIKE %s OR slug ILIKE %s ORDER BY name LIMIT 5", (f"%{query}%", f"%{query}%")).fetchall()
    return rows


# ---------------------------------------------------------------- sənədlər
def save_document(filename: str, kind: str, method: str, extractor: str, status: str, data: dict, issues: list,
                  text_chars: int, seconds: float) -> int:
    with get_conn() as conn:
        return conn.execute(
            "INSERT INTO documents (filename, kind, method, extractor, status, data, issues, text_chars, seconds) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (filename, kind, method, extractor, status, Json(data), Json(issues), text_chars, seconds)).fetchone()["id"]


def list_documents(limit: int = 50) -> list:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM documents ORDER BY id DESC LIMIT %s", (limit,)).fetchall()


# ---------------------------------------------------------------- hesabat və eval
def save_report(text: str, stats: dict, source: str) -> int:
    with get_conn() as conn:
        return conn.execute("INSERT INTO reports (text, stats, source) VALUES (%s,%s,%s) RETURNING id", (text, Json(stats), source)).fetchone()["id"]


def latest_report() -> dict | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM reports ORDER BY id DESC LIMIT 1").fetchone()


def save_eval(label: str, summary: dict) -> None:
    with get_conn() as conn:
        conn.execute("INSERT INTO eval_runs (label, summary) VALUES (%s,%s)", (label, Json(summary)))


def reset_all() -> None:
    """Test və demo üçün: bütün məlumatı sil."""
    with get_conn() as conn:
        conn.execute("TRUNCATE price_snapshots, products, scrape_runs, documents, reports RESTART IDENTITY CASCADE")
