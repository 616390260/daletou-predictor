"""
SQLite 数据库访问层
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from ..config import DB_PATH

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def init_db() -> None:
    """
    初始化数据库（建表、建索引）
    """
    with get_conn() as conn:
        with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()


@contextmanager
def get_conn():
    """
    获取数据库连接，自动开启外键与 Row 工厂
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()
