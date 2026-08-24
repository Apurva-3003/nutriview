<div align="center">
  <img src="https://github.com/shahviransh/Nutri-View/blob/main/src-tauri/icons/128x128.png" alt="Logo" width="80" height="80">
  <h3 align="center">Nutri-View</h3>
  <p align="center">
    A cross-platform desktop application for exploring and analyzing Integrated Modeling for Watershed Evaluation of BMPs (IMWEBs) environmental datasets.
    <br />
    <a href="https://github.com/shahviransh/Nutri-View">View on GitHub</a>
  </p>
</div>

<p align="center">
  <a href="https://www.youtube.com/watch?v=KNyyVSygOWY">
    <img src="https://img.youtube.com/vi/KNyyVSygOWY/0.jpg" alt="NutriView Demo" /><br/>🎥 See the application in action (33 mins)
  </a>
</p>

---

## Table of Contents

<details>
  <summary>Click to expand</summary>
  <ol>
    <li><a href="#-about-the-project">About The Project</a>
      <ul>
        <li><a href="#-key-features">Key Features</a></li>
      </ul>
    </li>
    <li><a href="#%EF%B8%8F-architecture">Architecture</a></li>
    <li><a href="#-getting-started">Getting Started</a>
      <ul>
        <li><a href="#-installation">Installation</a></li>
        <li><a href="#-backend-admin-authentication-flask">Backend admin authentication (Flask)</a></li>
        <li><a href="#web-and-cloud-deployment">Web and Cloud Deployment</a></li>
      </ul>
    </li>
    <li><a href="#%EF%B8%8F-common-issues">Common Issues</a></li>
    <li><a href="#-freeing-up-space-after-uninstalling">Freeing Up Space After Uninstalling</a></li>
    <li><a href="#-technical-report">Technical Report</a></li>
    <li><a href="#security">Security</a></li>
    <li><a href="#contributors">Contributors</a></li>
    <li><a href="#-acknowledgments">Acknowledgments</a></li>
  </ol>
</details>

---

## About The Project

**Nutri-View** is a tool designed for exploring, analyzing, and visualizing environmental model data. It supports both tabular and geospatial data formats and provides features for data filtering, aggregation, calculation, graphing, mapping, and exporting.

Built with **Tauri**, **Vue 3**, and **Flask**, this application provides a rich, interactive, and offline-capable experience for analyzing tabular and geospatial data.

### Key Features

- **Cross-Platform Support:** Packages available for Windows, macOS, and Linux.
- **Dynamic Visualization:** Interactive charts using ECharts and maps using Leaflet.
- **Geospatial Intelligence:** Support for shapefiles, GeoTIFFs, and export to SHP and GeoJSON.
- **Custom Formula Builder:** Combine numerical columns using mathematical expressions, evaluated through a sandboxed expression engine (no `eval`/`exec` on user input).
- **Data Export:** Export tables, graphs, and maps to multiple formats (CSV, TXT, XLSX, PNG, SVG, PDF, SHP).
- **Authentication Support:** Login/logout with JWT-based token security, bcrypt-hashed credentials (no plaintext passwords or default fallbacks), and enforced password complexity at account creation. See [Security](#security).
- **Hardened Input Handling:** Parameterized SQL, SQL-identifier allowlisting, and path-traversal guards across every API route that touches the filesystem or a database.
- **Integrated Build Pipeline:** Docker, Makefile, and PowerShell scripts included for CI/CD and version control.

---

## Architecture

<p align="center">
  <a href="https://www.youtube.com/watch?v=x69xOCFa_0c">
    <img src="https://img.youtube.com/vi/x69xOCFa_0c/0.jpg" alt="NutriView Demo" /><br/>🎥 See the application in action (20 mins)
  </a>
</p>

![Diagram](https://github.com/shahviransh/Nutri-View/blob//main/Diagram.png)

### Structure

- **Frontend (Vue 3):**
  - UI components in `src/components/`
  - Pages like Graphs, Maps, Login, and Help in `src/pages/`
  - Vue Router and Vuex for routing and state management
  - Lightning-fast development and optimized production builds using Vite
- **Backend (Flask):**
  - `apppy.py`: Entry point
  - `routes.py`: API endpoints (data, maps, export, authentication)
  - `services.py`: Data fetching and transformation logic
  - `validate.py`: Request validation
- **Desktop Runtime (Tauri):**
  - Bundled with Rust
  - Defined in `src-tauri/`

---

## Getting Started

### Installation

Download the latest release from the [GitHub Releases Page](https://github.com/shahviransh/Nutri-View/releases/latest).

### Download for your platform

#### **Linux**

- **Available Packages**: `.deb`, `.rpm`, or `.AppImage`
  - **`.deb`**: Suitable for Debian-based distributions like **Ubuntu**, **Linux Mint**, or **Kali**. Install with:

    ```bash
    sudo apt install ./<filename>.deb
    ```

  - **`.rpm`**: Suitable for RPM-based distributions like **Fedora**, **Red Hat Enterprise Linux (RHEL)**, or **openSUSE**. Install with:

    ```bash
    sudo rpm -i <filename>.rpm
    ```

  - **`.AppImage`**: Universal package for most distributions. Make it executable using:

    ```bash
    chmod +x <filename>.AppImage
    ./<filename>.AppImage
    ```

- Once installed, you can launch the application from your application menu or terminal.

#### **Windows**

- **Available Packages**: `.msi` or `.exe`
  - **`.msi`**: Requires admin privileges for installation. Double-click the file and follow the setup instructions. The application will launch automatically after installation.
  - **`.exe`**: Suitable for users without admin rights. Run the `.exe` file, and the application will launch immediately.
- After installation, you can find the application in your Start Menu or Desktop.

#### **macOS**

- **Available Packages**: `.dmg` or `.app.tar.gz`
  - **Intel vs ARM**: Check your Mac's architecture before downloading.  
    - **Intel Macs**: Download the **x64** package.  
    - **Apple Silicon (M1/M2)**: Download the **aarch64** package.
  - **`.dmg`**: Open the `.dmg` file, then drag and drop the application into your **Applications** folder. Launch the application from the Applications folder or via Spotlight Search.
  - **`.app.tar.gz`**: Extract the file using:

    ```bash
    tar -xzf <filename>.app.tar.gz
    ```

    Then move the extracted application to your **Applications** folder. Launch the application as usual.

Launch the Application: The application connects the Vue 3 frontend with the Flask backend and should be ready to use.

### Backend admin authentication (Flask)

The backend reads credentials from the environment. On startup, `apppy.py` loads variables from **`backend/.env`** (gitignored) via `python-dotenv` before the rest of the app imports. If `ADMIN_USERNAME` and `ADMIN_PASSWORD_HASH` are still not set after that (for example in tests that import `routes` alone), `routes.py` loads the same file again.

**Required:** If any of the variables below are missing, the process **exits at import time** with a `RuntimeError`—there are no default usernames or passwords.

| Variable | Description |
|----------|-------------|
| `ADMIN_USERNAME` | Admin login name (plain text) |
| `ADMIN_PASSWORD_HASH` | Bcrypt hash of the admin password (never store the plain password here) |
| `GUEST_USERNAME` | Guest login name (plain text) |
| `GUEST_PASSWORD` | Bcrypt hash of the guest password (same format as `ADMIN_PASSWORD_HASH`) |
| `JWT_SECRET_KEY` | Secret used to sign JWT session tokens (required when `PRODUCTION=True`) |

The login API verifies passwords with `bcrypt.checkpw` against the stored hashes.

Copy `backend/.env.example` to `backend/.env` before first run, or use the helper scripts below.

**Create credentials with the helper scripts (recommended)**

1. Open a terminal in the `backend` directory.
2. Run:

   ```bash
   python create_admin.py
   python create_guest.py
   ```

3. Enter usernames and passwords when prompted. Passwords are hashed with bcrypt and written to `backend/.env`. `create_admin.py` also generates `JWT_SECRET_KEY` if it is not already set.

   **Password requirements:** at least 12 characters, and at least 3 of the following character classes: lowercase letter, uppercase letter, digit, symbol. The script rejects weaker passwords and exits without writing to `.env`.

**Generate a bcrypt hash manually**

If you prefer not to use the script, you can generate a hash in Python (from `backend` with dependencies installed):

```bash
python -c "import bcrypt; print(bcrypt.hashpw(input('Password: ').encode('utf-8'), bcrypt.gensalt()).decode('ascii'))"
```

Then set in `backend/.env` (use quotes around hashes because they contain `$`). Generate a separate bcrypt hash for the guest account and include all four variables:

```env
ADMIN_USERNAME="your-username"
ADMIN_PASSWORD_HASH="$2b$12$..."
GUEST_USERNAME="guest"
GUEST_PASSWORD="$2b$12$..."
JWT_SECRET_KEY="64-character-hex-from-secrets-token-hex-32"
```

You can also export the variables in your shell instead of using `backend/.env`.

**Docker**

Use the same `backend/.env` as local development. From the repository root:

```bash
docker run -p 0.0.0.0:5000:5000 --env-file backend/.env nutriview
```

`--env-file` injects variables into the container process. The Flask app does not read any other env file name (there is no separate root-level `backend.env`); `load_dotenv` only loads `backend/.env` when variables are not already set.

### Web and Cloud Deployment

If you're running the Flask backend as a web service rather than behind the desktop app (Docker, `PRODUCTION=True`, or any hosted deployment), set `CORS_ALLOWED_ORIGINS` in `backend/.env` to your frontend's real origin(s), comma-separated:

```env
CORS_ALLOWED_ORIGINS="https://your-frontend-domain.com"
```

Without this set, CORS defaults to local development (`http://localhost:1420`) and the Tauri desktop webview origins only — a hosted web frontend on any other origin will have its API requests rejected by the browser until this is configured.

## Common Issues

### Can't Find Exported Files or Export Fails: “Permission Denied” or Files Not Saved

If you're trying to **export files (e.g., CSV, PNG, SHP, etc.)**, and the operation fails or you see a **permission error**, it's likely due to **write restrictions** on the default export directory. If you **can’t find the exported files**, see below.

> By default, the backend saves export files **relative to the Nutri-View app’s installation directory**, typically at: `{Nutri-View App Path}/_up_/backend/apppy/_internal/dataExport`

### Why This Happens

- If the app is installed in a **system directory** (like `/usr/lib/` or `Program Files`), the backend might not have **write access** there **without admin privileges**.
- Since the backend writes export files **relative to its own location**, it fails if that location is **read-only** for the current user.

### Solution

To avoid export issues:

1. **Change the export path to a folder the user has write access to**, such as:
   - Desktop
   - Downloads
   - Documents
   - A custom folder inside the user's home directory (e.g., `~/IMWEBs-Exports`)

## Freeing Up Space After Uninstalling

After uninstalling **Nutri-View**, you can delete leftover temporary files to free up space. Each platform has a **TempFiles** folder in the user data folder that can be safely deleted.

Run the following commands to delete the **TempFiles** folder:

### **Linux**

```bash
rm -rf ~/.local/share/Nutri-View/TempFiles
```

### Windows

```powershell
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\Nutri-View\TempFiles"
```

### macOS

```bash
rm -rf ~/Library/Application\ Support/Nutri-View/TempFiles
```

## Technical Report

For a detailed explanation of the application's architecture, data processing workflows, and design decisions, please refer to the full technical report:

[Download the Nutri-View Technical Report (.docx)](https://github.com/shahviransh/Nutri-View/raw/refs/heads/main/Technical%20Report.docx)

## Security

Nutri-View has been through a security assessment covering credential handling, input validation, cross-platform packaging, and multi-user/cloud deployment concerns. Highlights:

- **No default or hardcoded credentials.** The backend refuses to start unless `ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH`, `GUEST_USERNAME`, and `GUEST_PASSWORD` are all set — see [Backend admin authentication](#-backend-admin-authentication-flask).
- **Passwords are bcrypt-hashed and complexity-checked** at creation time (see above); plaintext passwords are never stored or documented.
- **Input validation** on every API route: parameterized SQL, SQL-identifier allowlisting, path-traversal guards on all file operations, and a sandboxed (non-`eval`) formula evaluator for the custom formula builder.
- **CORS is restricted to an explicit allow-list** rather than open to any origin — see [Web and Cloud Deployment](#web-and-cloud-deployment).

**Known open gaps** (tracked, not yet resolved): no external identity-provider (e.g. Entra ID) integration, no per-person user identifiers (only shared `admin`/`guest` roles), no password expiry/rotation policy, and several places where the app's original single-user/desktop design assumptions don't yet hold up under concurrent multi-user or cloud deployment (shared global state, a shared temp-file directory without per-user ownership checks, and an in-memory session-revocation list that won't work across multiple server instances).

Full findings, evidence, and a prioritized remediation plan: **[SECURITY_ASSESSMENT.md](./SECURITY_ASSESSMENT.md)**.

## Contributors

- **Apurva Agrawal** — Lead Developer ([@Apurva-3003](https://github.com/Apurva-3003))

## Acknowledgments

- Core Technologies:
  - Tauri, Rust
  - Vue 3
  - Python, Flask
- Frontend Libraries:
  - Vite
  - ECharts
  - Leaflet
- Python Libraries & Tools:
  - Data Handling & Analysis:
    - `pandas`, `numpy`, `xlsxwriter`, `scipy`, `scikit-learn`
  - Geospatial Processing:
    - `geopandas`, `pyogrio`, `osgeo (gdal, ogr, osr)`, `cmocean`
  - Visualization:
    - `matplotlib`, `cycler`, `PIL (Pillow)`
- Contributors & Community:
  - Special thanks to the following individuals for their guidance, data, and support:
    - Julia Rutledge (CWA)
    - Daniel DeOcampo (CWA)
    - Yongbo Liu (ECCC)
    - Wanhong Yang (UoG)
- Open-Source Maintainers:
  - A heartfelt thank-you to the developers behind the core libraries that power this application.
