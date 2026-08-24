from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS
from flask_caching import Cache
import os
import shutil

# Load backend/.env before importing routes (routes validates admin env vars at import time)
load_dotenv(Path(__file__).resolve().parent / ".env")

from routes import register_routes
from error_handlers import register_error_handlers
from config import Config

if os.path.exists(Config.TEMPDIR):
    shutil.rmtree(Config.TEMPDIR)

os.makedirs(Config.TEMPDIR, exist_ok=True)

app = Flask(__name__)

# Comma-separated list of allowed origins, e.g. "https://app.example.com,https://admin.example.com".
# Defaults cover local dev (Vite) and the Tauri desktop webview; override for web/cloud deployments.
_DEFAULT_CORS_ORIGINS = "http://localhost:1420,tauri://localhost,http://tauri.localhost"
_CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", _DEFAULT_CORS_ORIGINS).split(",")
    if origin.strip()
]
CORS(app, origins=_CORS_ALLOWED_ORIGINS)

# Configure caching
cache = Cache(app, config={"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 300})

# Register routes and error handlers
register_routes(app, cache)
register_error_handlers(app)

if __name__ == "__main__":
    if os.getenv("PRODUCTION") == "True":
        from waitress import serve

        os.environ["WAITRESS"] = "1"
        serve(app, host="0.0.0.0", port=5000)
    else:
        app.run(host="0.0.0.0", port=5000)
