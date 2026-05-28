from flask import jsonify, request, send_file
import mimetypes
from werkzeug.utils import safe_join
import logging
import os
import sys
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    jwt_required,
    get_jwt,
    verify_jwt_in_request,
    get_jwt_identity,
)
from functools import wraps
from dotenv import load_dotenv
import secrets
import bcrypt
from config import Config
from services import (
    fetch_data_service,
    get_files_and_folders,
    get_table_names,
    export_data_service,
    get_multi_columns_and_time_range,
    process_geospatial_data,
    export_map_service,
    fetch_geojson_colors,
    convert_excels_to_db_service,
    convert_to_gpkg_service,
)
from utils import shutdown_server, clear_cache
from validate import (
    validate_get_data_args,
    validate_export_data_args,
    validate_get_tables_args,
    validate_list_files_args,
    validate_get_table_details_args,
    validate_geospatial_args,
    validate_export_map_args,
    validate_serve_tif_args,
    validate_convert_excels_to_db_args,
    validate_guest_permissions_payload,
    validate_login_payload,
    validate_upload_folder_files,
    validate_convert_to_gpkg_files,
    validate_convert_excel_files,
    validate_geotiff_path_param,
)
from security_validation import normalized_upload_relative_path, path_is_under
import json

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_PATH = os.path.join(_BACKEND_DIR, ".env")

# Merge backend/.env (override=False: explicit env vars e.g. from Docker win over the file).
load_dotenv(_ENV_PATH)

ADMIN_USERNAME = (os.getenv("ADMIN_USERNAME") or "").strip().strip('"').strip("'")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "").strip().strip('"').strip("'")

if not ADMIN_USERNAME:
    raise RuntimeError(
        "ADMIN_USERNAME is not set. Set it as an environment variable or in the .env file. "
        "Do not use hardcoded credentials."
    )
if not ADMIN_PASSWORD_HASH:
    raise RuntimeError(
        "ADMIN_PASSWORD_HASH is not set. Set it as an environment variable or in the .env file. "
        "Do not use hardcoded credentials."
    )

JWT_SECRET_KEY = secrets.token_hex(256)

# Store revoked tokens
revoked_tokens = set()

if not os.path.exists(f"{Config.PATHFILE}/guest_permissions.json"):
    # Create a default guest permissions file if it doesn't exist
    default_permissions = {
        "read": False,
        "write": False,
        "upload": False,
        "download": False,
    }
    with open(f"{Config.PATHFILE}/guest_permissions.json", "w") as f:
        json.dump(default_permissions, f)

# Guest permission flags: read from guest_permissions.json
with open(f"{Config.PATHFILE}/guest_permissions.json", "r") as f:
    GUEST_PERMISSIONS = json.load(f)

# Define what kind of permission each route requires
PERMISSION_REQUIRED = {
    "get_data": "read",
    "get_tables": "read",
    "list_files": "read",
    "get_table_details": "read",
    "geospatial": "read",
    "get_geojson_colors": "read",
    "export_data": "download",
    "export_map": "download",
    "serve_tif": "download",
    "upload_folder": "upload",
    "convert_excels_to_db": "write",
    "convert_to_gpkg": "write",
}

# Guest credentials
GUEST_USERNAME = (os.getenv("GUEST_USERNAME") or "").strip().strip('"').strip("'")
GUEST_PASSWORD = (os.getenv("GUEST_PASSWORD") or "").strip().strip('"').strip("'")

if not GUEST_USERNAME:
    raise RuntimeError(
        "GUEST_USERNAME is not set. Set it as an environment variable or in the .env file. "
        "Do not use hardcoded credentials."
    )
if not GUEST_PASSWORD:
    raise RuntimeError(
        "GUEST_PASSWORD is not set. Set it as an environment variable or in the .env file. "
        "Do not use hardcoded credentials."
    )


logger = logging.getLogger(__name__)


def register_routes(app, cache):
    app.config["JWT_SECRET_KEY"] = JWT_SECRET_KEY
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = 3600  # 1 hour
    jwt = JWTManager(app)

    def require_permission(permission_type):
        def decorator(fn):
            @wraps(fn)
            def wrapper(*args, **kwargs):
                identity = get_jwt_identity()
                role = get_jwt()["role"]

                if role == "admin":
                    return fn(*args, **kwargs)

                if role == "guest":
                    allowed = GUEST_PERMISSIONS.get(permission_type, False)
                    if allowed:
                        return fn(*args, **kwargs)
                    else:
                        return jsonify(
                            {
                                "error": f"Guest does not have '{permission_type}' permission"
                            }
                        )

                return jsonify({"error": "Invalid role"}), 403

            return wrapper

        return decorator

    @app.route("/api/login", methods=["POST"])
    def login():
        """
        Authenticate user using hashed password.
        """
        try:
            data = request.get_json(silent=True) or {}
            creds = validate_login_payload(data)
            if creds.get("error"):
                return jsonify({"error": "Missing username or password"}), 400
            username_in = creds["username"]
            password = creds["password"]

            logger.debug("login: received username=%r", username_in)

            # Case-insensitive username match (env / Docker may differ in casing from the UI).
            ufold = username_in.casefold()
            admin_ok = None
            guest_ok = None
            identity = None
            if ufold == ADMIN_USERNAME.casefold():
                try:
                    admin_ok = bcrypt.checkpw(
                        password.encode("utf-8"),
                        ADMIN_PASSWORD_HASH.encode("utf-8"),
                    )
                except (ValueError, TypeError) as e:
                    logger.warning(
                        "login: admin bcrypt error for username=%r: %s", username_in, e
                    )
                    admin_ok = False
                logger.debug("login: admin bcrypt check succeeded=%s", admin_ok)
                if admin_ok is True:
                    identity = ADMIN_USERNAME
            elif ufold == GUEST_USERNAME.casefold():
                try:
                    guest_ok = bcrypt.checkpw(
                        password.encode("utf-8"), GUEST_PASSWORD.encode("utf-8")
                    )
                except (ValueError, TypeError) as e:
                    logger.warning(
                        "login: guest bcrypt error for username=%r: %s", username_in, e
                    )
                    guest_ok = False
                if guest_ok is True:
                    identity = GUEST_USERNAME

            if admin_ok is True:
                role = "admin"
            elif guest_ok is True:
                role = "guest"
            else:
                logger.warning(
                    "login: authentication failed username=%r admin_bcrypt_ok=%s guest_bcrypt_ok=%s",
                    username_in,
                    admin_ok,
                    guest_ok,
                )
                return jsonify({"error": "Invalid credentials"}), 401

            access_token = create_access_token(
                identity=identity, additional_claims={"role": role}
            )
            return jsonify(access_token=access_token)
        except Exception:
            logger.exception("login: unexpected error")
            return jsonify({"error": "Invalid credentials"}), 401

    @app.route("/api/logout", methods=["POST"])
    @jwt_required()
    def logout():
        """
        Logout the user by revoking the token.
        """
        jti = get_jwt()["jti"]  # Get the unique identifier of the token
        revoked_tokens.add(jti)
        return jsonify({"message": "Logged out successfully"}), 200

    # Token revocation check
    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        return jwt_payload["jti"] in revoked_tokens

    @app.route("/api/verify-token", methods=["GET"])
    def verify_token():
        """
        Verify the JWT token in the request headers.
        """
        try:
            verify_jwt_in_request()
            return jsonify({"valid": True}), 200
        except Exception as e:
            return jsonify({"valid": False}), 401

    @app.route("/api/guest-permissions", methods=["GET", "POST"])
    @jwt_required()
    def edit_guest_permissions():
        role = get_jwt()["role"]
        if role != "admin":
            return jsonify({"error": "Admins only"}), 403

        if request.method == "GET":
            return jsonify(GUEST_PERMISSIONS)

        new_perms = request.get_json()
        perm_check = validate_guest_permissions_payload(new_perms)
        if perm_check.get("error"):
            return jsonify(perm_check), 400
        for perm in ["read", "write", "upload", "download"]:
            if perm in new_perms and isinstance(new_perms[perm], bool):
                GUEST_PERMISSIONS[perm] = new_perms[perm]

        # Save the updated permissions so even server restarts will keep the changes
        with open(f"{Config.PATHFILE}/guest_permissions.json", "w") as f:
            json.dump(GUEST_PERMISSIONS, f)

        return jsonify(
            {"message": "Guest permissions updated", "permissions": GUEST_PERMISSIONS}
        )

    @app.route("/api/upload_folder", methods=["POST"])
    @jwt_required()
    @require_permission("upload")
    def upload_folder():
        """
        Endpoint to upload a folder with files to the server.
        """
        files = request.files.getlist("files")
        upload_check = validate_upload_folder_files(files)
        if upload_check.get("error"):
            return jsonify({"error": upload_check["error"]}), 400

        for file in files:
            raw = file.filename or ""
            rel = normalized_upload_relative_path(raw)
            if rel is None:
                return jsonify({"error": "Invalid file name."}), 400
            file_path = safe_join(Config.PATHFILE, rel)
            if file_path is None or not path_is_under(Config.PATHFILE, file_path):
                return jsonify({"error": "Invalid file path."}), 400

            # Ensure the file is not already there checking for duplicates
            if (
                os.path.exists(file_path)
                and os.path.getsize(file_path) == file.content_length
            ):
                continue

            # Get the folder name from the file's filename
            folder_name = os.path.dirname(file_path)
            os.makedirs(folder_name, exist_ok=True)
            file.save(file_path)

        return (
            jsonify({"message": "Files uploaded successfully"}),
            200,
        )

    @app.route("/api/get_data", methods=["GET"])
    @jwt_required()
    @require_permission("read")
    @cache.cached(timeout=300, query_string=True)
    def get_data():
        data = request.args

        # Validate the request arguments
        validation_response = validate_get_data_args(data)
        if validation_response.get("error", None):
            return jsonify(validation_response), 400

        response = fetch_data_service(data)

        return jsonify(response)

    @app.route("/api/export_data", methods=["GET", "POST"])
    @jwt_required()
    @require_permission("download")
    # This endpoint is not cached because the file is generated dynamically
    def export_data():
        if request.method == "GET":
            data = request.args
        else:
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return jsonify({"error": "Request validation failed."}), 400
        validation_response = validate_export_data_args(data)
        if validation_response.get("error", None):
            return jsonify(validation_response), 400

        if request.method == "POST":
            if data.get("date_type", None):
                is_empty = False
            else:
                is_empty = True
                data["date_type"] = "GeoJson Only"
            file_path = export_data_service(data, is_empty)
        else:
            file_path = export_data_service(data)

        if file_path.get("error", None):
            return jsonify(file_path)

        # Determine the mimetype based on the file extension
        file_extension = file_path.get("file_path").split(".")[-1].lower()
        mimetype = (
            mimetypes.types_map.get(f".{file_extension}", "application/octet-stream")
            if file_extension != "xlsx"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        return send_file(
            file_path.get("file_path"), mimetype=mimetype, as_attachment=True
        )

    @app.route("/api/get_tables", methods=["GET"])
    @jwt_required()
    @require_permission("read")
    @cache.cached(timeout=300, query_string=True)
    def get_tables():
        data = request.args

        # Validate the request arguments
        validation_response = validate_get_tables_args(data)
        if validation_response.get("error", None):
            return jsonify(validation_response), 400

        # Fetch the table names from the database
        tables = get_table_names(data)

        return jsonify(tables.get("tables"))

    @app.route("/api/list_files", methods=["GET"])
    @jwt_required()
    @require_permission("read")
    def list_files():
        """
        Endpoint to list all files and directories in the specified path.
        """
        data = request.args

        # Validate the request arguments
        validation_response = validate_list_files_args(data)
        if validation_response.get("error", None):
            return jsonify(validation_response), 400

        files_and_folders = get_files_and_folders(data)

        return jsonify(files_and_folders.get("files_and_folders"))

    @app.route("/api/get_table_details", methods=["GET"])
    @jwt_required()
    @require_permission("read")
    @cache.cached(
        timeout=300, query_string=True
    )  # Cache this endpoint for 2 minutes (120 seconds)
    def get_table_details():
        """
        Endpoint to get table column names, time start, time end, and ID list, date type, and default interval.
        """
        data = request.args

        # Validate the request arguments
        validation_response = validate_get_table_details_args(data)
        if validation_response.get("error", None):
            return jsonify(validation_response), 400

        columns_and_time_range_dict = get_multi_columns_and_time_range(data)

        return jsonify(columns_and_time_range_dict)

    @app.route("/api/geospatial", methods=["GET"])
    @jwt_required()
    @require_permission("read")
    @cache.cached(timeout=300, query_string=True)
    def geospatial():
        """
        API endpoint to return GeoJSON/Tiff Image Url, bounds, and center.
        """
        data = request.args

        # Validate the request arguments
        validation_response = validate_geospatial_args(data)
        if validation_response.get("error", None):
            return jsonify(validation_response), 400

        geo_data = process_geospatial_data(data)

        return jsonify(geo_data)

    @app.route("/api/geotiff/<path:filename>", methods=["GET"])
    @jwt_required()
    @require_permission("download")
    def serve_tif(filename):
        """
        Serve the TIF file from the specified path.
        """
        path_check = validate_geotiff_path_param(filename)
        if path_check.get("error"):
            return jsonify(path_check), 400

        resolved = safe_join(Config.TEMPDIR, filename)
        if resolved is None or not path_is_under(Config.TEMPDIR, resolved):
            return jsonify({"error": "Invalid file path."}), 400

        # Validate the file path
        validation_response = validate_serve_tif_args(resolved)
        if validation_response.get("error", None):
            return jsonify(validation_response), 400

        return send_file(resolved, mimetype="image/png", as_attachment=True)

    @app.route("/api/get_geojson_colors", methods=["GET"])
    @jwt_required()
    @require_permission("read")
    @cache.cached(timeout=300, query_string=True)
    def get_geojson_colors():
        """
        API endpoint to get GeoJSON colors.
        """
        data = request.args

        # Validate the request arguments
        validation_response = validate_get_data_args(data)
        if validation_response.get("error", None):
            return jsonify(validation_response), 400

        colors = fetch_geojson_colors(data)

        return jsonify(colors)

    @app.route("/api/export_map", methods=["POST"])
    @jwt_required()
    @require_permission("download")
    def export_map():
        """
        API endpoint to export the map image.
        """
        image = request.files.get("image")
        form_data = request.form.to_dict()

        # Validate the request arguments
        validation_response = validate_export_map_args(image, form_data)
        if validation_response.get("error", None):
            return jsonify(validation_response), 400

        file_path = export_map_service(image, form_data)

        if file_path.get("error", None):
            return jsonify(file_path)

        mimetype = mimetypes.types_map.get(".zip", "application/octet-stream")

        return send_file(
            file_path.get("file_path"), mimetype=mimetype, as_attachment=True
        )

    @app.route("/api/convert_excels_to_db", methods=["POST"])
    @jwt_required()
    @require_permission("write")
    def convert_excels_to_db():
        """
        API endpoint to convert Excel files to database entries.
        """
        excel_files = request.files.getlist("files")
        data = request.form.to_dict()

        file_check = validate_convert_excel_files(excel_files)
        if file_check.get("error"):
            return jsonify({"error": file_check["error"]}), 400

        validation_response = validate_convert_excels_to_db_args(data)
        if validation_response.get("error", None):
            return jsonify(validation_response), 400

        result = convert_excels_to_db_service(excel_files, data)

        # Return all created database paths
        return jsonify(result)

    @app.route("/api/convert_to_gpkg", methods=["POST"])
    @jwt_required()
    @require_permission("write")
    def convert_to_gpkg():
        """
        API endpoint to convert uploaded files to GPKG format.
        """
        uploaded_files = request.files.getlist("files")
        gpkg_check = validate_convert_to_gpkg_files(uploaded_files)
        if gpkg_check.get("error"):
            return jsonify({"error": gpkg_check["error"]}), 400

        converted_files = convert_to_gpkg_service(uploaded_files)

        # Return single GPKG file path
        return jsonify(converted_files)

    @app.route("/api/health", methods=["GET"])
    def health():
        return "Server is running...", 200

    @app.route("/api/shutdown", methods=["GET"])
    @jwt_required()
    def shutdown():
        # Shutdown the server if running as a standalone executable
        if getattr(sys, "frozen", False):
            shutdown_server()
            return "Server shutting down...", 200
        else:
            return "Server is not running as a standalone executable.", 200

    @app.route("/api/clear_cache", methods=["GET"])
    @jwt_required()
    def clear_cache_route():
        clear_cache(cache)
        return "Cache cleared.", 200
