from cerberus import Validator
import re
import os
import json
import logging

from security_validation import (
    EXCEL_UPLOAD_EXTENSIONS,
    GPKG_UPLOAD_EXTENSIONS,
    UPLOAD_FOLDER_EXTENSIONS,
    is_safe_db_filename,
    is_safe_relative_data_path,
    is_safe_sql_identifier,
    is_safe_geospatial_layer_name,
    is_safe_subprocess_layer_name,
    normalized_upload_relative_path,
    secure_path_segment,
    upload_has_allowed_extension,
)

logger = logging.getLogger(__name__)

# ID list as JSON: [] or ["1","2"] (quoted decimal string IDs only).
_ID_JSON_PATTERN = r'^\[\s*(?:"\d+"\s*,\s*)*"\d+"\s*\]$|^\[\s*\]$'

# Column / identifier-like names for id_column (no quotes or semicolons).
_ID_COLUMN_PATTERN = r"^[\w][\w\s-]{0,127}$|^$"

# Column names (may include table prefix e.g. MyTable-MyCol).
_COLUMN_NAME_REGEX = re.compile(r"^[\w][\w\s.\-]{0,127}$")

_METHOD_ALLOWED = frozenset(
    {"Equal", "Average", "Sum", "Maximum", "Minimum"}
)
_STATISTICS_ALLOWED = frozenset(
    {"None", "Average", "Sum", "Maximum", "Minimum", "Standard Deviation"}
)

# Export subfolder under export root (relative); traversal blocked separately.
_EXPORT_PATH_PATTERN = r"^[A-Za-z0-9_][A-Za-z0-9_ ./\\-]{0,255}$"
_MATH_FORMULA_PATTERN = r"^[0-9A-Za-z_\s+\-*/^().,]{1,2000}$"

_GENERIC_VALIDATION_ERROR = {"error": "Request validation failed."}


def validate_request_args(schema, request_args):
    """
    Validates the request arguments using Cerberus and applies path checks.
    On failure, logs details server-side and returns a generic client message.
    """
    validator = Validator(schema)
    data = {
        key: request_args.get(key) for key in schema.keys() if key in request_args
    }

    if not validator.validate(data):
        logger.warning("Cerberus validation failed: %s", validator.errors)
        return dict(_GENERIC_VALIDATION_ERROR)

    for key, value in data.items():
        if isinstance(value, str):
            if re.search(r"(\.\.\/|\.\.\\)", value):
                logger.warning("Path traversal pattern rejected for field %r", key)
                return dict(_GENERIC_VALIDATION_ERROR)

    return validator.document


def _validate_db_tables_json(raw: str) -> bool:
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(parsed, list) or len(parsed) > 500:
        return False
    for item in parsed:
        if not isinstance(item, dict):
            return False
        db = item.get("db")
        tbl = item.get("table")
        if not isinstance(db, str) or not isinstance(tbl, str):
            return False
        if not is_safe_relative_data_path(db):
            return False
        dbl = db.lower()
        if not (dbl.endswith(".db3") or dbl.endswith(".gpkg")):
            return False
        if not is_safe_sql_identifier(tbl.strip()):
            return False
    return True


def _validate_columns_json(raw: str) -> bool:
    if raw == "All":
        return True
    try:
        cols = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(cols, list) or len(cols) > 5000:
        return False
    for c in cols:
        if not isinstance(c, str) or not _COLUMN_NAME_REGEX.fullmatch(c.strip()):
            return False
    return True


def _validate_string_list_json(
    raw: str, *, allowed: frozenset[str] | None = None, max_items: int = 50
) -> bool:
    try:
        items = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(items, list) or len(items) > max_items:
        return False
    for item in items:
        if not isinstance(item, str) or len(item) > 128:
            return False
        if allowed is not None and item not in allowed:
            return False
    return True


def _validate_filter_json(raw: str) -> bool:
    if not raw:
        return True
    try:
        filt = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(filt, dict) or len(filt) > 500:
        return False
    for k, values in filt.items():
        if not isinstance(k, str) or not _COLUMN_NAME_REGEX.fullmatch(k.strip()):
            return False
        if not isinstance(values, list) or len(values) > 10_000:
            return False
        for v in values:
            if not isinstance(v, (str, int, float, bool)) and v is not None:
                return False
            if isinstance(v, str) and len(v) > 500:
                return False
    return True


def _validate_excel_mapping_payload(mapping_raw: str, header_raw: str, merged_raw: str) -> bool:
    try:
        mapping = json.loads(mapping_raw)
        header_mapping = json.loads(header_raw)
        merged_mapping = json.loads(merged_raw)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(mapping, dict) or len(mapping) > 100:
        return False
    if not isinstance(header_mapping, (dict, list)) or not isinstance(
        merged_mapping, (dict, list)
    ):
        return False
    for db_name, file_map in mapping.items():
        if not isinstance(db_name, str) or not re.fullmatch(
            r"[A-Za-z0-9_.-]{1,120}\.db3", db_name
        ):
            return False
        if not isinstance(file_map, dict) or len(file_map) > 500:
            return False
        for excel_name, sheets in file_map.items():
            if not isinstance(excel_name, str) or len(excel_name) > 255:
                return False
            if not isinstance(sheets, list) or len(sheets) > 500:
                return False
            for sheet in sheets:
                if not isinstance(sheet, str) or not is_safe_sql_identifier(sheet.strip()):
                    return False
    return True


def _validate_get_data_common(out: dict) -> dict | None:
    """Extra JSON field checks shared by get_data and export_data validators."""
    if not _validate_columns_json(out.get("columns", "")):
        logger.warning("Invalid columns JSON")
        return dict(_GENERIC_VALIDATION_ERROR)
    if not _validate_string_list_json(
        out.get("method", "['Equal']"), allowed=_METHOD_ALLOWED
    ):
        logger.warning("Invalid method JSON")
        return dict(_GENERIC_VALIDATION_ERROR)
    if not _validate_string_list_json(
        out.get("statistics", "['None']"), allowed=_STATISTICS_ALLOWED
    ):
        logger.warning("Invalid statistics JSON")
        return dict(_GENERIC_VALIDATION_ERROR)
    filt = out.get("filter")
    if filt and not _validate_filter_json(filt):
        logger.warning("Invalid filter JSON")
        return dict(_GENERIC_VALIDATION_ERROR)
    return None


def validate_get_data_args(request_args):
    schema = {
        "db_tables": {"type": "string", "required": True},
        "columns": {"type": "string", "required": True},
        "id": {"type": "string", "required": True, "regex": _ID_JSON_PATTERN},
        "id_column": {"type": "string", "required": True, "regex": _ID_COLUMN_PATTERN},
        "start_date": {
            "type": "string",
            "required": True,
            "regex": r"^\d*$|^\d{4}-\d{2}-\d{2}$|^$",
        },
        "end_date": {
            "type": "string",
            "required": True,
            "regex": r"^\d*$|^\d{4}-\d{2}-\d{2}$|^$",
        },
        "date_type": {
            "type": "string",
            "required": True,
            "allowed": ["Time", "Date", "Month", "Year", ""],
        },
        "interval": {
            "type": "string",
            "required": True,
            "default": "daily",
            "regex": r"^[a-zA-Z]+$",
        },
        "method": {"type": "string", "required": True, "default": "['Equal']"},
        "statistics": {"type": "string", "required": True, "default": "['None']"},
        "month": {
            "type": "string",
            "required": False,
            "allowed": [
                "1",
                "2",
                "3",
                "4",
                "5",
                "6",
                "7",
                "8",
                "9",
                "10",
                "11",
                "12",
                "",
            ],
        },
        "season": {
            "type": "string",
            "required": False,
            "allowed": ["summer", "winter", "fall", "spring", ""],
        },
        "feature": {"type": "string", "required": False, "maxlength": 256},
        "feature_statistic": {
            "type": "string",
            "required": False,
            "allowed": ["mean", "sum", "max", "min"],
        },
        "spatial_scale": {
            "type": "string",
            "required": False,
            "allowed": ["subarea", "field", "reach", "subbasin", "unknown"],
        },
        "math_formula": {
            "type": "string",
            "required": False,
            "maxlength": 2000,
            "regex": _MATH_FORMULA_PATTERN,
        },
        "filter": {"type": "string", "required": False, "maxlength": 500_000},
    }
    out = validate_request_args(schema, request_args)
    if out.get("error"):
        return out
    if not _validate_db_tables_json(out.get("db_tables", "")):
        logger.warning("Invalid db_tables JSON structure")
        return dict(_GENERIC_VALIDATION_ERROR)
    extra = _validate_get_data_common(out)
    if extra:
        return extra
    return out


def validate_export_data_args(request_args):
    schema = {
        "db_tables": {"type": "string", "required": True},
        "columns": {"type": "string", "required": True},
        "id": {"type": "string", "required": True, "regex": _ID_JSON_PATTERN},
        "id_column": {"type": "string", "required": True, "regex": _ID_COLUMN_PATTERN},
        "start_date": {
            "type": "string",
            "required": True,
            "regex": r"^\d*$|^\d{4}-\d{2}-\d{2}$|^$",
        },
        "end_date": {
            "type": "string",
            "required": True,
            "regex": r"^\d*$|^\d{4}-\d{2}-\d{2}$|^$",
        },
        "date_type": {
            "type": "string",
            "required": True,
            "allowed": ["Time", "Date", "Month", "Year", ""],
        },
        "interval": {
            "type": "string",
            "required": True,
            "default": "daily",
            "regex": r"^[a-zA-Z]+$",
        },
        "method": {"type": "string", "required": True, "default": "['Equal']"},
        "statistics": {"type": "string", "required": True, "default": "['None']"},
        "export_filename": {
            "type": "string",
            "required": True,
            "regex": r"^[\w,\s-]{1,200}$",
        },
        "export_format": {
            "type": "string",
            "required": True,
            "allowed": [
                "csv",
                "txt",
                "xlsx",
                "png",
                "jpg",
                "jpeg",
                "svg",
                "pdf",
                "shp",
            ],
        },
        "export_path": {"type": "string", "required": True, "regex": _EXPORT_PATH_PATTERN},
        "options": {"type": "string", "required": True},
        "month": {
            "type": "string",
            "required": False,
            "allowed": [
                "1",
                "2",
                "3",
                "4",
                "5",
                "6",
                "7",
                "8",
                "9",
                "10",
                "11",
                "12",
                "",
            ],
        },
        "season": {
            "type": "string",
            "required": False,
            "allowed": ["summer", "winter", "fall", "spring", ""],
        },
        "geojson_data": {"type": "string", "required": False, "maxlength": 50_000_000},
        "feature": {"type": "string", "required": False, "maxlength": 256},
        "feature_statistic": {
            "type": "string",
            "required": False,
            "allowed": ["mean", "sum", "max", "min"],
        },
        "spatial_scale": {
            "type": "string",
            "required": False,
            "allowed": ["subarea", "field", "reach", "subbasin", "unknown"],
        },
        "default_crs": {
            "type": "string",
            "required": False,
            "allowed": ["EPSG:4326", "EPSG:26917"],
        },
        "math_formula": {
            "type": "string",
            "required": False,
            "maxlength": 2000,
            "regex": _MATH_FORMULA_PATTERN,
        },
        "filter": {"type": "string", "required": False, "maxlength": 500_000},
    }
    out = validate_request_args(schema, request_args)
    if out.get("error"):
        return out
    if not _validate_db_tables_json(out.get("db_tables", "")):
        logger.warning("Invalid db_tables JSON structure")
        return dict(_GENERIC_VALIDATION_ERROR)
    extra = _validate_get_data_common(out)
    if extra:
        return extra
    opts = out.get("options")
    if opts:
        try:
            parsed_opts = json.loads(opts)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Invalid export options JSON")
            return dict(_GENERIC_VALIDATION_ERROR)
        if not isinstance(parsed_opts, dict) or len(parsed_opts) > 50:
            return dict(_GENERIC_VALIDATION_ERROR)
        for k, v in parsed_opts.items():
            if not isinstance(k, str) or k not in (
                "table",
                "stats",
                "graph",
                "map",
            ):
                return dict(_GENERIC_VALIDATION_ERROR)
            if not isinstance(v, bool):
                return dict(_GENERIC_VALIDATION_ERROR)
    geo = out.get("geojson_data")
    if geo:
        try:
            gj = json.loads(geo)
        except (json.JSONDecodeError, TypeError):
            return dict(_GENERIC_VALIDATION_ERROR)
        if not isinstance(gj, dict):
            return dict(_GENERIC_VALIDATION_ERROR)
    return out


def validate_get_tables_args(request_args):
    schema = {"db_path": {"type": "string", "required": True}}
    out = validate_request_args(schema, request_args)
    if out.get("error"):
        return out
    if not is_safe_db_filename(out["db_path"]):
        logger.warning("Invalid db_path for get_tables")
        return dict(_GENERIC_VALIDATION_ERROR)
    return out


def validate_list_files_args(request_args):
    schema = {
        "folder_path": {
            "type": "string",
            "required": True,
            "regex": r"^[\w][\w\s./\\-]{0,255}$",
        },
        "is_tauri": {
            "type": "string",
            "required": False,
            "allowed": ["true", "false", ""],
        },
    }
    return validate_request_args(schema, request_args)


def validate_get_table_details_args(request_args):
    schema = {"db_tables": {"type": "string", "required": True}}
    out = validate_request_args(schema, request_args)
    if out.get("error"):
        return out
    if not _validate_db_tables_json(out.get("db_tables", "")):
        logger.warning("Invalid db_tables JSON in get_table_details")
        return dict(_GENERIC_VALIDATION_ERROR)
    return out


def _validate_file_paths_json(raw: str, *, min_count: int = 1) -> bool:
    try:
        paths = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(paths, list) or len(paths) > 200 or len(paths) < min_count:
        return False
    for p in paths:
        if not isinstance(p, str) or not is_safe_relative_data_path(p):
            return False
        low = p.lower()
        if not (
            low.endswith(".shp")
            or low.endswith(".gpkg")
            or low.endswith(".tif")
            or low.endswith(".tiff")
        ):
            return False
    return True


def validate_geospatial_args(request_args):
    schema = {"file_paths": {"type": "string", "required": True, "maxlength": 100_000}}
    out = validate_request_args(schema, request_args)
    if out.get("error"):
        return out
    if not _validate_file_paths_json(out.get("file_paths", "")):
        logger.warning("Invalid file_paths for geospatial")
        return dict(_GENERIC_VALIDATION_ERROR)
    raw_ln = request_args.get("layer_names")
    if raw_ln is not None:
        if not isinstance(raw_ln, str) or len(raw_ln) > 500_000:
            return dict(_GENERIC_VALIDATION_ERROR)
        try:
            ln = json.loads(raw_ln)
        except (json.JSONDecodeError, TypeError):
            return dict(_GENERIC_VALIDATION_ERROR)
        if not isinstance(ln, dict):
            return dict(_GENERIC_VALIDATION_ERROR)
        for k, v in ln.items():
            if not isinstance(k, str) or not is_safe_relative_data_path(k):
                return dict(_GENERIC_VALIDATION_ERROR)
            if not isinstance(v, list) or len(v) > 500:
                return dict(_GENERIC_VALIDATION_ERROR)
            for name in v:
                if not isinstance(name, str) or not is_safe_geospatial_layer_name(
                    name.strip()
                ):
                    return dict(_GENERIC_VALIDATION_ERROR)
    return out


def validate_export_map_args(image, form_data):
    if image is not None:
        mt = getattr(image, "mimetype", None) or ""
        if not mt.startswith("image/"):
            return {"error": "Invalid image file format"}
    schema = {
        "export_format": {
            "type": "string",
            "required": True,
            "allowed": ["png", "jpg", "jpeg", "pdf"],
        },
        "export_path": {"type": "string", "required": True, "regex": _EXPORT_PATH_PATTERN},
        "export_filename": {
            "type": "string",
            "required": True,
            "regex": r"^[\w,\s-]{1,200}$",
        },
        "file_paths": {"type": "string", "required": True, "maxlength": 100_000},
    }
    out = validate_request_args(schema, form_data)
    if out.get("error"):
        return out
    if not _validate_file_paths_json(out.get("file_paths", ""), min_count=0):
        logger.warning("Invalid file_paths for export_map")
        return dict(_GENERIC_VALIDATION_ERROR)
    return out


def validate_geotiff_path_param(filename: str) -> dict:
    if not filename or not isinstance(filename, str):
        return {"error": "Invalid file path."}
    low = filename.lower()
    if not low.endswith((".tif", ".tiff", ".png")):
        return {"error": "Only .tif or .tiff files are allowed"}
    if not is_safe_relative_data_path(filename):
        return {"error": "Invalid file path."}
    return {"ok": True}


def validate_serve_tif_args(resolved_path):
    if not resolved_path or not os.path.isfile(resolved_path):
        return {"error": "Invalid path specified for the GeoTIFF file."}
    return {"filename": resolved_path}


def validate_convert_excels_to_db_args(data):
    schema = {
        "mapping": {"type": "string", "required": True, "maxlength": 5_000_000},
        "header_mapping": {"type": "string", "required": True, "maxlength": 500_000},
        "merged_mapping": {"type": "string", "required": True, "maxlength": 5_000_000},
        "conflict_action": {
            "type": "string",
            "required": True,
            "allowed": ["replace", "append"],
        },
    }
    out = validate_request_args(schema, data)
    if out.get("error"):
        return out
    if not _validate_excel_mapping_payload(
        out.get("mapping", ""),
        out.get("header_mapping", ""),
        out.get("merged_mapping", ""),
    ):
        logger.warning("Invalid Excel mapping JSON")
        return dict(_GENERIC_VALIDATION_ERROR)
    return out


def validate_login_payload(data) -> dict:
    if not isinstance(data, dict):
        return dict(_GENERIC_VALIDATION_ERROR)
    username = data.get("username")
    password = data.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        return dict(_GENERIC_VALIDATION_ERROR)
    username = username.strip()
    if (
        not username
        or len(username) > 128
        or re.search(r"[\x00\r\n]", username)
        or ";" in username
    ):
        return dict(_GENERIC_VALIDATION_ERROR)
    if not password or len(password) > 256 or "\x00" in password:
        return dict(_GENERIC_VALIDATION_ERROR)
    return {"username": username, "password": password}


def validate_upload_folder_files(files) -> dict:
    if not files:
        return {"error": "No files uploaded"}
    if len(files) > 5000:
        return dict(_GENERIC_VALIDATION_ERROR)
    for file in files:
        raw = file.filename or ""
        if not upload_has_allowed_extension(raw, UPLOAD_FOLDER_EXTENSIONS):
            return {"error": "File type not allowed."}
        if normalized_upload_relative_path(raw) is None:
            return {"error": "Invalid file name."}
    return {"ok": True}


def validate_convert_to_gpkg_files(files) -> dict:
    if not files:
        return {"error": "No files uploaded"}
    if len(files) > 500:
        return dict(_GENERIC_VALIDATION_ERROR)
    for file in files:
        raw = file.filename or ""
        if any(
            seg in (".", "..")
            for seg in re.split(r"[/\\]+", raw)
            if seg
        ):
            return {"error": "Invalid file name."}
        if not upload_has_allowed_extension(raw, GPKG_UPLOAD_EXTENSIONS):
            return {"error": "Unsupported file type."}
        stem, _ext = os.path.splitext(raw)
        stem_safe = secure_path_segment(stem)
        if not stem_safe or not is_safe_subprocess_layer_name(stem_safe):
            return {"error": "Invalid file name."}
    return {"ok": True}


def validate_convert_excel_files(files) -> dict:
    if not files:
        return {"error": "Files and mapping data required"}
    if len(files) > 200:
        return dict(_GENERIC_VALIDATION_ERROR)
    for file in files:
        raw = file.filename or ""
        if not upload_has_allowed_extension(raw, EXCEL_UPLOAD_EXTENSIONS):
            return {"error": "Invalid Excel file name."}
        stem, _ext = os.path.splitext(raw)
        if not secure_path_segment(stem):
            return {"error": "Invalid Excel file name."}
    return {"ok": True}


def validate_guest_permissions_payload(body):
    """Admin-only JSON: only boolean flags for known keys."""
    if body is None or not isinstance(body, dict):
        return dict(_GENERIC_VALIDATION_ERROR)
    if not body:
        return {"ok": True}
    allowed = frozenset(["read", "write", "upload", "download"])
    for k, v in body.items():
        if k not in allowed:
            logger.warning("Unknown guest permission key rejected")
            return dict(_GENERIC_VALIDATION_ERROR)
        if not isinstance(v, bool):
            return dict(_GENERIC_VALIDATION_ERROR)
    return {"ok": True}
