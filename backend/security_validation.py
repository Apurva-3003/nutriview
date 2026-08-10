"""
Shared validation for paths and SQL-related identifiers used with user-influenced input.
"""
from __future__ import annotations

import os
import re
import unicodedata

# SQLite identifiers we embed in SQL: no quote/semicolon; letters, digits, space, underscore, dot, hyphen, parentheses.
_SQL_IDENT_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_ .()\-]{0,127}$")
_FORBIDDEN_IN_IDENT = frozenset('"\';`')

# Relative paths under data root: no NUL, no parent segments after normalization.
_REL_PATH_MAX = 512


def secure_path_segment(name: str) -> str:
    """ASCII-safe single path segment (similar to werkzeug.secure_filename)."""
    if not isinstance(name, str):
        return ""
    normalized = unicodedata.normalize("NFKD", name)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", ascii_only)
    return cleaned.strip("._")


def is_safe_sql_identifier(name: str) -> bool:
    if not name or not isinstance(name, str):
        return False
    s = name.strip()
    if not s or len(s) > 128:
        return False
    if any(c in s for c in _FORBIDDEN_IN_IDENT):
        return False
    return bool(_SQL_IDENT_RE.fullmatch(s))


def quote_sql_identifier(name: str) -> str:
    """Double-quote a validated identifier for SQLite (escape internal quotes)."""
    if not is_safe_sql_identifier(name):
        raise ValueError("Invalid SQL identifier.")
    return '"' + name.replace('"', '""') + '"'


def is_safe_relative_data_path(rel: str) -> bool:
    if not rel or not isinstance(rel, str) or len(rel) > _REL_PATH_MAX:
        return False
    if "\x00" in rel:
        return False
    slash = rel.replace("\\", "/")
    raw_parts = [p for p in slash.split("/") if p]
    if any(p in (".", "..") for p in raw_parts):
        return False
    norm = os.path.normpath(slash)
    if norm.startswith("..") or os.path.isabs(norm):
        return False
    return True


# Upload / conversion file extensions (lowercase, without dot).
UPLOAD_FOLDER_EXTENSIONS = frozenset(
    {
        "shp",
        "tif",
        "gpkg",
        "shx",
        "dbf",
        "cpg",
        "prj",
        "sbn",
        "sbx",
        "db3",
        "tiff",
        "xml",
    }
)
GPKG_UPLOAD_EXTENSIONS = frozenset(
    {"shp", "shx", "dbf", "prj", "cpg", "sbn", "sbx", "tif", "tiff"}
)
EXCEL_UPLOAD_EXTENSIONS = frozenset({"xlsx", "xls"})


def normalized_upload_relative_path(raw_filename: str) -> str | None:
    """
    Build a safe relative path from a browser-provided filename (may include subdirs).
    Returns None if any segment is invalid or traversal is attempted.
    """
    if not raw_filename or not isinstance(raw_filename, str):
        return None

    segments = [p for p in re.split(r"[/\\]+", raw_filename) if p]
    if any(p in (".", "..") for p in segments):
        return None
    parts = [secure_path_segment(p) for p in segments]
    if not parts or any(not p for p in parts):
        return None
    rel = "/".join(parts)
    if not is_safe_relative_data_path(rel):
        return None
    return rel


def upload_has_allowed_extension(
    raw_filename: str, allowed_extensions: frozenset[str]
) -> bool:
    if not raw_filename or "." not in raw_filename:
        return False
    ext = raw_filename.rsplit(".", 1)[1].lower()
    return ext in allowed_extensions


def is_safe_db_filename(name: str) -> bool:
    if not is_safe_relative_data_path(name):
        return False
    lower = name.lower()
    return lower.endswith(".db3") or lower.endswith(".gpkg")


def is_safe_subprocess_layer_name(name: str) -> bool:
    """OGR/GDAL layer names passed as argv (no shell); still restrict metacharacters."""
    if not name or len(name) > 128:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name))


def is_safe_geospatial_layer_name(name: str) -> bool:
    """Layer names from client layer selection (not shell-joined; no quotes/semicolons)."""
    if not name or not isinstance(name, str) or len(name) > 128:
        return False
    s = name.strip()
    if any(c in s for c in _FORBIDDEN_IN_IDENT):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,127}", s))


def path_is_under(base: str, candidate: str) -> bool:
    try:
        base_r = os.path.realpath(base)
        cand_r = os.path.realpath(candidate)
        common = os.path.commonpath([base_r, cand_r])
        return common == base_r
    except (OSError, ValueError):
        return False


def sqlite_table_exists(conn, table: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ? LIMIT 1",
        (table,),
    )
    return cur.fetchone() is not None


def sqlite_table_column_names(conn, table: str) -> set[str]:
    """Return column names for a validated table; empty if table missing."""
    if not is_safe_sql_identifier(table):
        return set()
    if not sqlite_table_exists(conn, table):
        return set()
    cur = conn.execute("SELECT name FROM pragma_table_info(?)", (table,))
    return {row[0] for row in cur.fetchall()}
