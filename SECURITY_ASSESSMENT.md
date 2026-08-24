# NutriView Security Assessment — 2026-08-24

Scope: verification of 10 previously flagged security issues against the actual
codebase (not documentation claims), as of commit `36cc3b9`. Six contained,
low-risk items were fixed and re-verified in this pass; the remainder are
documented as open work requiring a design decision.

---

## 1. Executive Summary

**Current risk posture, in plain language:** the authentication and input-validation
layers have been substantially hardened in recent history (bcrypt-hashed
credentials, mandatory env vars with no insecure fallback, parameterized SQL,
path-traversal guards, a sandboxed formula evaluator instead of `eval`). The
remaining risk is concentrated in three areas: **(a)** this app was clearly
designed as a single-user desktop tool and is now also being run as a
multi-user web/cloud service without the state-isolation that requires;
**(b)** there is no external identity provider, per-person accountability, or
password lifecycle policy, which matters if this is meant to handle Protected A
data; **(c)** cross-platform packaging (macOS, Linux, Docker) has had latent
bugs that would silently break the app outside Windows.

**What changed in this pass:** six contained, no-judgment-call fixes were
applied and verified — a NaN-serialization gap, a macOS sidecar-launch bug, two
Windows-only pip dependencies breaking non-Windows installs, an unused
near-unrestricted shell-execution capability in the desktop app, unrestricted
CORS, and missing password complexity rules on credential creation. See
§3 for details and §4 for the operational impact of the CORS change.

**What remains open:** everything that needs a product/architecture decision —
identity-provider integration, per-person user identifiers, password expiry
policy, and the cluster of multi-user/cloud-deployment issues (global mutable
state, a shared temp-file store with no per-user ownership check, JWT storage
location, and an in-memory token-revocation list). These are listed with a
prioritized remediation plan in §5.

---

## 2. Status Table

| # | Item | Status | Severity | Summary |
|---|------|--------|----------|---------|
| 1 | Sample data NaN handling | **Fixed** | Low | NaN/NA/NaT could bypass JSON-serialization cleanup depending on scalar type; now caught uniformly. |
| 2 | Cross-platform support (macOS/Linux/Docker/Cargo) | **Partially Fixed** | Medium | Fixed a macOS-only sidecar-launch bug and two Windows-only pip deps breaking non-Windows installs; a hardcoded Windows UNC path and untested end-to-end builds remain. |
| 3 | Plain-text password default install | **Fixed** | High (was) | Setup docs and `.env.example` require a bcrypt hash, never a plaintext password. |
| 4 | `routes.py` `"default"` credential fallback | **Fixed** | Critical (was) | App now fails hard at import time if admin/guest env vars are unset — no silent insecure default. |
| 5 | No identity-provider (Entra ID/Azure AD) integration | **Not Fixed** | High | Auth is entirely local (two hardcoded roles); no OIDC/SAML integration exists. |
| 6 | No password complexity/expiry policy | **Partially Fixed** | Medium | Complexity now enforced at creation time (12+ chars, 3-of-4 classes). Expiry/rotation is explicitly out of scope for this pass. |
| 7 | No unique per-person user identifiers | **Not Fixed** | High | Only two identities exist system-wide (`admin`, `guest`); no per-person attribution. |
| 8 | Hardcoded admin/guest config values | **Fixed** | High (was) | No credentials found in `config.py` or any config file; only permission flags. |
| 9 | Broad input validation / injection risk | **Partially Fixed** | Low–Medium (residual) | SQL, path, and formula-evaluation input is heavily allowlisted/parameterized; one unused near-unrestricted shell-execution capability was found and removed. |
| 10 | Multi-user / cloud-environment flaws | **Not Fixed** | High | Global mutable request-scoped state, a shared temp directory with no per-user ownership check, `localStorage`-held JWTs, and an in-memory token blocklist all assume single-user/single-process trust. CORS was narrowed but the underlying architecture issue remains. |

---

## 3. Detailed Findings

### 1. Sample data NaN handling — Fixed

**Found:** `backend/services.py`, `replace_nan_with_none()` (originally lines
475–482) only checked `isinstance(value, (float, int)) and np.isnan(value)`.
This misses `pd.NA` (produced by the nullable `Int64`→`object` conversion at
`services.py:2678-2679`) and `pd.NaT`, neither of which is JSON-serializable —
these would have reached `jsonify()` unfiltered and either raised a
serialization error or emitted invalid JSON (`NaN` is not valid JSON).

**Fixed:** `backend/services.py:475-483` now uses
`pd.api.types.is_scalar(value) and pd.isna(value)`. `is_scalar` excludes
containers (list/dict/tuple/ndarray) so `pd.isna()` never has to evaluate an
array's truthiness, and `pd.isna()` itself correctly flags every pandas
missing-value representation, not just plain float NaN.

**Verified:** exercised against `float('nan')`, `pd.NA`, `pd.NaT`, `np.nan`,
plus a string, int, bool, list, dict, and `None` in a live pandas/numpy
environment — all four missing-value forms converted to `None`; every other
value passed through unchanged.

---

### 2. Cross-platform support — Partially Fixed

**Found — macOS sidecar launch bug (fixed):** `src-tauri/src/main.rs` computed
the expected backend sidecar filename at runtime as
`{arch}-pc-{os}-{gnu|msvc|unknown}`. This formula happens to produce the
correct real Rust target triple on Windows (`x86_64-pc-windows-msvc`) and
Linux (`x86_64-pc-linux-gnu`), but **not** on macOS, where the real triple is
`{arch}-apple-darwin` — the old code produced `aarch64-pc-macos-unknown`
instead. `src-tauri/move.js:12-13` (which renames the PyInstaller binary after
build) uses `rustc -vV`'s actual host triple and names the file correctly, so
the shipped binary's filename never matched what `start_server()` was looking
for. Net effect: on macOS the app window would open, but the Flask backend
would never launch, and the app would be non-functional.

**Fixed:** `src-tauri/src/main.rs:20-36` now special-cases
`cfg!(target_os = "macos")` to compute `{arch}-apple-darwin` directly,
matching `move.js`'s output.

**⚠️ Verification caveat — treat as unresolved until confirmed on a real build.**
This fix was verified by static inspection and by matching it line-for-line
against `move.js`'s logic and the CI matrix's actual build targets
(`aarch64-apple-darwin`, `x86_64-apple-darwin` in `.github/workflows/main.yml:16-18`).
**No Rust toolchain was available in the environment this fix was made in, so
it has not been compiled or run.** Do not close this out until a macOS CI run
(or a local `cargo check`/build on a Mac) confirms the sidecar actually
launches.

**Found — Windows-only pip dependencies (fixed):** `backend/requirements.txt`
listed `pywin32-ctypes` and `win_inet_pton` (both Windows-only, wrapping native
Windows APIs via ctypes) with no platform marker. `pip install -r
requirements.txt` would very likely fail on Linux/macOS — which is exactly
what `Dockerfile` and the non-Windows legs of the CI matrix
(`.github/workflows/main.yml:79-90`) do.

**Fixed:** `backend/requirements.txt:84,108` — added `; sys_platform ==
'win32'` markers to both packages.

**⚠️ Verification caveat:** this was confirmed by inspection/grep, not by
actually running `pip install` inside a Linux container or CI leg. Recommend
running the Docker build and a Linux/macOS CI leg end-to-end before
considering the Docker/Linux install path fully verified.

**Not fixed / not investigated further — hardcoded Windows network path:**
`backend/config.py:31` hardcodes
`BASE_DIR = "//int.ec.gc.ca/shares/M/MSC&ONT/.../Databases"` — a Windows UNC
path to what appears to be an internal department file share. It's used
conditionally (`os.path.exists(...)` guards in `services.py:442`) so it fails
gracefully rather than crashing, but any feature depending on `Help.db3` or
`Config.BASE_DIR` (Excel-to-DB ingestion writes here — `services.py:2509-2510`)
is effectively Windows/domain-only. This wasn't in the fix list for this pass
and needs a decision: should this path be environment-configurable, and should
the app degrade more visibly (rather than silently) when it's unreachable?

---

### 3. Plain-text password default install — Fixed

**Found:** the concern as flagged was that setup documentation instructed
users to configure plain-text passwords.

**Current state:** `backend/.env.example` and `README.md:147-205` require
`ADMIN_PASSWORD_HASH` / `GUEST_PASSWORD` to be **bcrypt hashes**, generated via
`create_admin.py`/`create_guest.py` or manually with `bcrypt.hashpw`. No file
in the repo instructs or stores plaintext passwords. Nothing to fix here — this
had already been addressed prior to this assessment.

---

### 4. `routes.py` insecure default credential fallback — Fixed

**Found:** the concern as flagged was `os.getenv(...) or "default"` — silently
falling back to a hardcoded weak credential.

**Current state:** `backend/routes.py:59-122` reads `ADMIN_USERNAME`,
`ADMIN_PASSWORD_HASH`, `GUEST_USERNAME`, `GUEST_PASSWORD` via `os.getenv(...)
or ""`, and raises `RuntimeError` at **import time** (`routes.py:62-71,
113-122`) if any is empty — there is no fallback string anywhere in the
codebase. Confirmed by git history (`89aa68f`, `1d75acb`). Nothing to fix here.

---

### 5. No identity-provider integration — Not Fixed

**Found:** authentication is entirely local. `backend/routes.py`'s `/api/login`
handler (lines 160-226) verifies a submitted username/password against exactly
two bcrypt hashes loaded from environment variables — there are only ever two
possible identities, `admin` and `guest`. `backend/requirements.txt` has no
OIDC/SAML/OAuth library. `backend/auth_config.py` only manages the JWT signing
secret, not an external trust relationship.

**Why it matters:** if this application is intended to handle Protected A
data, the absence of integration with an organizational identity provider
(e.g., Entra ID) means there's no centralized access control, no MFA
enforcement path, no ability to disable a compromised or departed user's
access without editing `.env` and restarting the service, and no
organization-wide audit trail of who authenticated when.

**Not touched in this pass** — this requires an architecture decision
(which IdP, which protocol, how roles map) before implementation.

---

### 6. No password complexity/expiry policy — Partially Fixed

**Found:** `create_admin.py`/`create_guest.py` only checked that a password
was non-empty and matched its confirmation — no length or character-class
requirement, and no expiry/rotation mechanism of any kind.

**Fixed (complexity only):** `backend/credential_utils.py:7-30` adds
`password_complexity_error()`, requiring at least 12 characters and at least 3
of {lowercase, uppercase, digit, symbol}. Wired into both
`create_admin.py:59-62` and `create_guest.py:45-48`, which now print an error
and exit non-zero (without writing to `.env`) if the password fails the check.

**Verified:** ran the function against 6 sample passwords (`short`,
`alllowercase12`, `ALLUPPERCASE12`, `NoSymbol123`, `GoodPass123!`,
`exactly12Ch!`) — correctly rejected the four that were too short or too
low-diversity, accepted the two that met both bars.

**Explicitly not touched — expiry/rotation.** Per instruction, this pass did
not implement any password-expiry or forced-rotation policy. That's a
design decision (rotation interval, grace period, notification mechanism) that
needs to be made separately — see §5.

---

### 7. No unique per-person user identifiers — Not Fixed

**Found:** `backend/routes.py:180-205` — the JWT `identity` claim is set to
either `ADMIN_USERNAME` or `GUEST_USERNAME`, both single shared strings read
from environment variables. Every person who logs in as "guest" (or as
"admin", if that credential is shared among multiple staff, which is common in
practice) is indistinguishable from every other person in that role — in logs,
in the JWT, and in `GUEST_PERMISSIONS` (`routes.py:90-91`, also a single global
permission set for "the guest role", not per-person).

**Why it matters:** no individual attributability means no meaningful audit
trail — if data is exported, modified, or deleted, there's no way to determine
which specific person did it. This is a common compliance requirement for
sensitive data classifications.

**Not touched in this pass** — this requires deciding on a user model (e.g.,
per-person accounts backed by an IdP per item 5, or a lighter-weight
per-person local account system) before implementation.

---

### 8. Hardcoded admin/guest config values — Fixed

**Found:** the concern as flagged was hardcoded credentials in config files
specifically (as distinct from the routes.py fallback in item 4).

**Current state:** `backend/config.py` contains no credentials at all — only
filesystem/GDAL paths. `backend/guest_permissions.json` holds only boolean
permission flags (`read`/`write`/`upload`/`download`), no credentials. No
hardcoded credential was found in any config file. Nothing to fix here.

---

### 9. Broad input validation gaps — Partially Fixed

**Found / current state — this is the most heavily hardened area of the
codebase already:**

- **SQL injection:** every SQL identifier (table/column names) is validated
  through `is_safe_sql_identifier()` / `quote_sql_identifier()`
  (`backend/security_validation.py:28-43`) before being embedded in a query
  string; all values are passed as parameterized `?` placeholders (e.g.
  `backend/services.py:589-651`, `fetch_data_from_db`). No string-interpolated
  user data was found in any SQL statement.
- **Path traversal:** uploads, exports, and geotiff serving consistently use
  `safe_join()` + a `path_is_under()` realpath-containment check
  (`security_validation.py:137-144`), e.g. `routes.py:294-299` (upload),
  `routes.py:460-462` (geotiff serving), `services.py:583-587`,
  `services.py:696-701` (export path).
- **Arbitrary code execution via the formula builder:** the "Custom Formula
  Builder" feature does **not** use Python `eval`/`exec`. It uses
  `numexpr.evaluate()` (`backend/services.py:30`), gated by
  `_numexpr_is_safe()` (`services.py:39-55`), which restricts input to a
  character allowlist and a small set of known function names / provided
  variables. This is a sound design choice — numexpr's evaluator doesn't have
  general Python semantics — though see §6 for a residual concern about the
  preprocessing logic above it.
- **General request validation:** nearly every route runs its arguments
  through a Cerberus schema plus additional regex/allowlist checks in
  `backend/validate.py`.

**Found and fixed — unused near-unrestricted shell-execution capability:**
`src-tauri/capabilities/default.json` (previously lines 10-19) granted the
desktop app's webview a `shell:allow-execute` permission running `sh -c` with
a validator of `\S+` — i.e., any non-empty string. Confirmed unused before
removal: no `@tauri-apps/plugin-shell` JS dependency exists to invoke it, and
the plugin is never `.plugin()`-initialized in `src-tauri/src/main.rs`'s
`Builder` (only `tauri_plugin_dialog::init()` is). Removed in this pass — see
§4 for the resulting orphaned Cargo dependency.

**Residual/not fully verified:** the formula-evaluation preprocessing above
`_numexpr_is_safe()` (`services.py:324-414`) — which does string-replacement
and regex-based token substitution to rewrite column names into the formula
before validation — is dense enough that it deserves a dedicated second review
pass to confirm there's no order-of-operations gap between the substitution
logic and the safety check. Flagged in §6, not fixed in this pass (would
require a deeper redesign review, not a contained fix).

---

### 10. Multi-user / cloud-environment flaws — Not Fixed

**Found — this app has several places where it assumes single-user/local
trust that don't hold once multiple concurrent users or a cloud deployment are
in play:**

- **Global mutable state mutated per-request.** `Config.PATHFILE` (a class
  attribute, not a per-request value) is reassigned inside
  `get_files_and_folders()` based on a user-supplied `folder_path`
  (`backend/services.py:1146`). In a threaded multi-user deployment (the
  default Waitress production server serves multiple threads in one process),
  one user's request can change the base data directory used by *concurrent*
  requests from other users — a race condition that can leak one user's data
  path context into another user's session. `alias_mapping`,
  `global_dbs_tables_columns`, and `bmp_db_path_global`
  (`backend/services.py:71-76`) are similarly process-wide mutable globals,
  not scoped per session or per request.
- **Shared temp directory with no per-user ownership check.**
  `Config.TEMPDIR` (`backend/config.py:30`) is a single directory for the
  entire process, wiped and recreated on every app startup
  (`backend/apppy.py:17-20`). Every write into it uses this same shared path
  (`services.py:2149, 2231, 2259, 2498, 2817-2859`). The `/api/geotiff/<path>`
  route (`backend/routes.py:449-469`) lets **any authenticated user —
  including guest** — fetch any file under `Config.TEMPDIR` by filename, with
  no check that the requesting session is the one that generated that file. In
  a shared/cloud deployment, this is broken access control between
  concurrent users/tenants.
- **In-memory token revocation list.** `revoked_tokens = set()`
  (`backend/routes.py:76`) is process-local. It works correctly within a
  single process, but a horizontally-scaled cloud deployment (multiple
  instances behind a load balancer) would not share this state — a user could
  log out on one instance and still have a valid, non-revoked token accepted
  by another instance.
- **JWT stored in `localStorage`.** `src/store/index.js:296,322,349` read the
  auth token from `localStorage` on every authenticated request. This is
  standard practice but carries the usual XSS-exfiltration exposure, and is
  specifically more relevant now that the app supports a web deployment mode
  (vs. purely the desktop Tauri build, where this class of attack is less of
  a concern).
- **CORS was unrestricted (fixed in this pass, see §4)** — `CORS(app)` with
  no origin restriction. This is now narrowed, but it was only ever one piece
  of this cluster of issues, not the root cause.

**Why these are grouped:** all five stem from the same underlying gap — this
codebase was built assuming one user, one process, one machine, and it now
needs to support many concurrent users and (per `PRODUCTION=True`/Docker/
Waitress support already in the code) horizontally-scaled deployment. Fixing
any one of these in isolation without a broader session/request-scoping
redesign risks just moving the bug. See §5 for the recommended approach.

**Not touched in this pass** per explicit instruction — these need a design
decision on session/request scoping and storage architecture before
implementation.

---

## 4. Deployment / Operational Notes

**⚠️ `CORS_ALLOWED_ORIGINS` must be set for any existing web/Docker/cloud
deployment, or requests will start failing.**

`backend/apppy.py:22-32` changed `CORS(app)` (any origin allowed) to an
explicit allow-list, defaulting to `http://localhost:1420` (local Vite dev)
plus the Tauri desktop webview origins (`tauri://localhost`,
`http://tauri.localhost`) when the new `CORS_ALLOWED_ORIGINS` env var is
unset. **If NutriView is already running anywhere as a web app (Docker, a
hosted deployment, `PRODUCTION=True`), that frontend's origin is almost
certainly not in the new default list.** Its browser requests will start
failing CORS preflight/response checks the moment this change is deployed,
with no server-side error to indicate why (it fails client-side, silently,
in the browser).

**Action required before deploying this change to any non-desktop
environment:** set `CORS_ALLOWED_ORIGINS` in that environment's `backend/.env`
(or equivalent secret/env config) to a comma-separated list of the real
frontend origin(s), e.g.:

```env
CORS_ALLOWED_ORIGINS="https://nutriview.example.org"
```

This is documented in `backend/.env.example` but will not self-apply — it
needs to be added to whatever `.env`/secrets configuration each live
deployment actually uses.

**`tauri-plugin-shell` in `src-tauri/Cargo.toml:22` is now an orphaned
dependency worth removing in a follow-up cleanup.** Its only consumer — the
`shell:allow-execute` permission in `capabilities/default.json` — was removed
in this pass because it was unused and over-privileged (§3, item 9). The Cargo
dependency itself was left in place, since removing it touches `Cargo.lock`
and needs a rebuild to verify, which was out of scope for this pass. Removing
it would shrink the desktop app's dependency/attack surface with no functional
loss; recommend doing this as a small standalone follow-up PR, verified by a
full `cargo build`.

---

## 5. Prioritized Remediation Plan (Open Items)

Ordered by risk/severity. Each of these needs a design decision from the
project owner before implementation — none were touched in this pass.

### Tier 1 — High severity, address next

1. **Multi-user/cloud architecture cluster (item 10)** — grouped together
   because they share a root cause and should be redesigned together, not
   patched independently:
   - Eliminate mutation of `Config.PATHFILE` and other module-level globals
     (`alias_mapping`, `global_dbs_tables_columns`, `bmp_db_path_global`) from
     request handlers. These need to become request-scoped (e.g., threaded
     through function arguments, or stored in Flask's request/session context)
     rather than process-wide class/module attributes.
   - Add per-user/per-session ownership to `Config.TEMPDIR` contents (e.g., a
     per-session subdirectory keyed off the JWT identity, with the
     `/api/geotiff/<path>` route checking that the requesting identity owns
     the requested file) — or move to a real per-request temp scope that's
     cleaned up after the request instead of a single shared directory wiped
     only at process startup.
   - Replace the in-memory `revoked_tokens` set with a shared store (Redis,
     the same database backing the app, etc.) if horizontal scaling is a real
     deployment target — otherwise document clearly that this deployment mode
     is single-instance-only.
   - Decide whether JWT storage should move off `localStorage` (e.g., to an
     httpOnly cookie) for the web deployment mode specifically; this is a
     smaller, more independent fix than the rest of this cluster and could be
     picked off separately if useful.

2. **No identity-provider integration (item 5)** — needed before this app can
   reasonably be considered for Protected A data. Decide on IdP (Entra ID
   presumed, given the org context), protocol (OIDC most likely), and how
   `admin`/`guest` roles map to IdP groups/claims.

3. **No per-person user identifiers (item 7)** — closely related to item 5;
   if an IdP integration is built, per-person identity likely comes for free.
   If IdP integration is deferred, this needs its own lighter-weight solution
   (e.g., per-person local accounts) since it's foundational to any audit
   trail.

### Tier 2 — Medium severity

4. **Password expiry/rotation policy (item 6, remainder)** — complexity is
   now enforced (this pass); expiry/rotation still needs a decision on
   interval, enforcement mechanism (forced re-hash on next login? out-of-band
   reminder?), and how that interacts with the current single-shared-account
   model — this may be easier to resolve *after* item 7, since a shared
   account complicates "whose password expired."

5. **Cross-platform build verification (item 2, remainder)** — the macOS
   sidecar fix and the Windows-only pip dependency fix in this pass both need
   to be confirmed against a real build:
   - Run the macOS CI leg (or a local Mac build) to confirm the sidecar
     actually launches post-fix.
   - Run the Docker build and/or a Linux CI leg to confirm `pip install`
     succeeds end-to-end post-fix.
   - Decide what to do about the hardcoded `Config.BASE_DIR` UNC path
     (`config.py:31`) — make it configurable via env var, and make the
     features that depend on it (Excel-to-DB ingestion, `Help.db3` lookups)
     fail more visibly when it's unreachable rather than silently degrading.

### Tier 3 — Lower severity / cleanup

6. **`tauri-plugin-shell` orphaned dependency** (§4) — remove from
   `Cargo.toml`, verify with a full build.
7. **Formula-evaluation preprocessing review (§6 below)** — dedicated review
   of `services.py:324-414`'s token-substitution logic, independent of the
   `numexpr` safety gate itself.

---

## 6. Additional Findings Not on the Original List

- **`shell:allow-execute` Tauri capability** (found and fixed in this pass —
  see §3 item 9 and §4). Flagging here for visibility since it wasn't on the
  original ten-item list: an unused, near-unrestricted shell-execution grant
  in the desktop app's webview capabilities. If the webview were ever
  compromised via content injection, this would have allowed arbitrary shell
  execution with the app's OS-level permissions. Removed; the now-orphaned
  Cargo dependency is tracked in §4/§5.

- **Unrestricted CORS** (found and fixed in this pass — see §3 item 10 and
  §4). Also not on the original list. Narrowed to an explicit allow-list;
  operational action required per §4.

- **Formula-evaluation token-substitution logic deserves a second pair of
  eyes.** `backend/services.py:324-414` (inside `fetch_data_service`) does a
  sequence of string-replacement and regex operations to rewrite column names
  into the `math_formula` string *before* handing it to `_numexpr_is_safe()`
  and `numexpr.evaluate()`. The safety gate itself is sound (character
  allowlist + known-token check, no `eval`), but the surrounding logic is
  dense — multiple sequential `.replace()` calls with `count=1`, a
  `special_chars` stripping step, and separate handling for comma-separated
  multi-column formulas — in a way that makes it hard to fully convince
  yourself there's no ordering issue where a substitution could reintroduce an
  unsafe token after the safety check has already run, or where a
  maliciously-crafted column-name/formula combination could confuse the
  1-count replacement into targeting the wrong occurrence. This wasn't treated
  as a "fix" in this pass because it's not a contained, no-judgment-call
  change — it would benefit from a dedicated review (and likely a test suite
  covering adversarial formula/column-name combinations) before being
  simplified or hardened further.

- **Hardcoded Windows UNC network path in `config.py:31`** — see §3 item 2.
  Not itself a security vulnerability, but a portability/reliability issue
  worth deciding on alongside the rest of the cross-platform remediation.

- **`GUEST_PERMISSIONS` is a single global permission object, not a
  per-session one** (`routes.py:90-91`) — directly related to item 7's
  finding that there's no per-person identity; flagged here because it's the
  concrete mechanism by which "the guest role" (not "this guest user") gets
  its permissions, which will need to change if per-person identifiers are
  ever introduced.

---

*This assessment reflects the state of the codebase at commit `36cc3b9` on
`main`. Six items were fixed and re-verified in this pass (§3); the rest
require product/architecture decisions before implementation (§5).*
