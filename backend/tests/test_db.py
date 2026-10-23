"""The report store's SQL must run on Postgres (deployed) as well as SQLite (local and tests)."""

import os
import re
from pathlib import Path

import pytest

from app.db import PostgresDatabase, Row, connect
from app.report_store import SCHEMA, ReportStore

STORE_SOURCE = (Path(__file__).resolve().parent.parent / "app" / "report_store.py").read_text(encoding="utf-8")


def test_translate_placeholders_and_types():
    sql = PostgresDatabase.render("SELECT * FROM reports WHERE num = ? AND description = ? AND latitude > ? AND x = ?",
                                  (3, "it's 100% ?", 3.123456789, None))
    assert sql == ("SELECT * FROM reports WHERE num = 3 AND description = 'it''s 100% ?' AND latitude > 3.123456789"
                   " AND x = NULL")
    with pytest.raises(ValueError):
        PostgresDatabase.render("SELECT ?", ())
    schema = PostgresDatabase.translate(SCHEMA)
    assert "AUTOINCREMENT" not in schema and "SERIAL PRIMARY KEY" in schema
    assert not re.search(r"\bREAL\b", schema) and "DOUBLE PRECISION" in schema  # lat/lon keep full precision


def test_store_avoids_sqlite_only_sql():
    for pattern in (r"INSERT OR ", r"lastrowid", r"SUM\(\w*\.?still_there =", r"PRAGMA"):
        assert not re.search(pattern, STORE_SOURCE), pattern


def test_row_by_name_and_position():
    row = Row([("num", 3), ("status", "pending")])
    assert row["num"] == 3 and row[1] == "pending" and dict(row) == {"num": 3, "status": "pending"}


def test_sqlite_store_round_trip(tmp_path):
    store = ReportStore(str(tmp_path / "w.db"))
    report = store.create("1-2", "flooding", None, 3.1, 101.6, device="phone-a")
    assert report["id"] == "report_1" and report["confirmations"]["still_there"] == 1
    for device in ("phone-b", "phone-c"):
        store.confirm(report["id"], device, True)
    assert store.community_blocked_segment_ids() == {"1-2"}
    store.clear()
    assert store.create("1-2", "flooding", None, 3.1, 101.6)["id"] == "report_1"


@pytest.mark.skipif(not os.environ.get("WALKLAH_TEST_DATABASE_URL"), reason="needs a Postgres database")
def test_postgres_store_round_trip():
    db = connect(os.environ["WALKLAH_TEST_DATABASE_URL"])
    assert db.dialect == "postgres"
    store = ReportStore(os.environ["WALKLAH_TEST_DATABASE_URL"])
    store.clear_all()
    report = store.create("1-2", "flooding", "test", 3.123456789, 101.6, device="phone-a")
    assert store.get(report["id"])["latitude"] == pytest.approx(3.123456789, abs=1e-9)
    for device in ("phone-b", "phone-c"):
        store.confirm(report["id"], device, True)
    assert store.community_blocked_segment_ids() == {"1-2"}
    store.clear_all()
