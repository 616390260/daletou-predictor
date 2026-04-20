"""
基础自测：schema 能否建、工具函数能否算对、模型能否生成合法号码
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd

from backend.src.config import BACK_COUNT, FRONT_COUNT, PRIZE_TABLE
from backend.src.db import get_conn, init_db
from backend.src.models import get_model
from backend.src.utils.numbers import count_hits, decode, encode, validate_ticket


def test_encode_decode():
    assert encode([5, 1, 22, 9, 33]) == "01,05,09,22,33"
    assert decode("01,05,09,22,33") == [1, 5, 9, 22, 33]


def test_count_hits():
    f, b = count_hits([1, 2, 3, 4, 5], [6, 7], [1, 3, 5, 7, 9], [7, 8])
    assert f == 3 and b == 1


def test_prize_table_shape():
    assert (5, 2) in PRIZE_TABLE
    assert PRIZE_TABLE[(5, 2)][1] > PRIZE_TABLE[(0, 2)][1]


def test_init_db_ok():
    init_db()
    with get_conn() as conn:
        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"draws", "predictions", "results"}.issubset(tables)


def test_models_generate_valid_tickets():
    rows = [
        {
            "issue": f"{25000 + i:05d}",
            "front": [(i + j) % 35 + 1 for j in range(5)],
            "back": [(i + j) % 12 + 1 for j in range(2)],
        }
        for i in range(100)
    ]
    df = pd.DataFrame(rows)

    for name in ["random", "frequency", "markov"]:
        m = get_model(name)
        tickets = m.predict(df, n=4)
        assert len(tickets) == 4
        for t in tickets:
            assert validate_ticket(t.front, t.back)
            assert len(t.front) == FRONT_COUNT
            assert len(t.back) == BACK_COUNT


if __name__ == "__main__":
    test_encode_decode()
    test_count_hits()
    test_prize_table_shape()
    test_init_db_ok()
    test_models_generate_valid_tickets()
    print("所有基础测试通过")
