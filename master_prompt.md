# PROJECT SPECIFICATION: TaskOps (Task Management & Per-Task Material Request System - PWA Edition)

You are a Senior Full-Stack Python Developer. Build a production-ready, mobile-first Progressive Web App (PWA) for To-Do List, Task Management, and Material Request using **Python 3.12**, **Flask**, and **SQLAlchemy** with **zero external third-party cloud dependencies** (self-contained local auth, installable PWA, and standard VAPID Web Push notifications).

Follow these strict architectural rules, business workflows, and step-by-step development guidelines with 100% consistency across the entire codebase.

---

## 1. TECH STACK & CORE CONSTRAINTS (STRICT)
- **Language & Runtime:** Python 3.12 (`python:3.12-slim` for Docker).
- **Entrypoint:** `run.py` (exposing `app = create_app()`).
- **Server & Port Binding:**
  - Gunicorn binding MUST read from `GUNICORN_BIND` in `.env`, defaulting to `127.0.0.1:5000` (`GUNICORN_BIND=127.0.0.1:5000`).
  - `run.py` local development server must also parse host and port from `GUNICORN_BIND` (defaulting to `127.0.0.1` and `5000`).
- **Framework & Extensions:** Flask 3.x, Flask-SQLAlchemy, Flask-Migrate, Flask-Login, Flask-WTF (CSRF protection enabled globally), `python-dotenv`, `pywebpush` (which includes `cryptography` and `py-vapid` for self-hosted VAPID Web Push Notifications), `gunicorn`, `psycopg2-binary`.
- **Database Configuration:**
  - Read from `DATABASE_PATH` in `.env`.
  - Default to SQLite (`sqlite:///task_management.db`) if `DATABASE_PATH` is not set.
  - Seamlessly support PostgreSQL when `DATABASE_PATH` is set to a PostgreSQL URI (`postgresql://...`).
- **Zero Dummy Seeding:** DO NOT create any dummy/seed data or CLI seed commands.
- **Auto-Initialize Admin from `.env`:** On application startup (`create_app`), automatically check if the user defined by `INITIAL_ADMIN_EMAIL` in `.env` exists. If not, create this Admin user using `INITIAL_ADMIN_NAME`, `INITIAL_ADMIN_EMAIL`, and `INITIAL_ADMIN_PASSWORD` from `.env`.
- **Auto-Generate & Persist VAPID Keys if `.env` is Empty:**
  - On application startup (`_ensure_vapid_keys(app)` inside `app/__init__.py`), check if `app.config['VAPID_PUBLIC_KEY']` and `app.config['VAPID_PRIVATE_KEY']` are populated.
  - If empty, first check if `instance/vapid_keys.json` exists. If it exists, load `public_key` and `private_key` from that file into `app.config`.
  - If `instance/vapid_keys.json` does not exist, automatically generate a new ECDSA SECP256R1 (P-256) keypair using `cryptography.hazmat.primitives.asymmetric.ec` (encode the raw 65-byte uncompressed public point and raw 32-byte private value as URL-safe Base64 without `=` padding so both browser `PushManager` and `pywebpush` accept them directly).
  - Save the generated keys to `instance/vapid_keys.json` (so they persist across restarts and Gunicorn workers) AND attempt to update/append `VAPID_PUBLIC_KEY` and `VAPID_PRIVATE_KEY` in `.env` if the `.env` file is writable. Set both keys in `app.config`.
- **Frontend, PWA & Mobile-First UX:**
  - Server-side rendered Jinja2 templates + **Tailwind CSS (via CDN)**.
  - **Installable PWA (Android & iOS):** Full support for "Add to Home Screen" (`standalone` display mode) so iOS 16.4+ and Android devices can receive background Web Push notifications reliably.
  - **Mobile-First Navigation:** Sticky top bar (App title + Notification bell with unread badge + Push/Install status button + Profile/Logout), thumb-friendly fixed Bottom Navigation Bar on mobile (`md:hidden`) and Sidebar on desktop, minimum touch target height of 44px (`py-2.5` or `py-3`), clean card layout, and consistent status badges.

---

## 2. DATABASE SCHEMA & BUSINESS LOGIC (`app/models.py`)
Use Python `enum.Enum` (inheriting from `str, enum.Enum`) for all status and role fields to ensure consistency across DB, Backend, and Templates:
1. **`RoleEnum`**: `ADMIN`, `STAFF`
2. **`TaskStatus`**: `TODO`, `IN_PROGRESS`, `PENDING`, `WAITING_REVIEW`, `COMPLETED`
3. **`ItemStatus`**: `REQUESTED`, `ORDERED`, `SHIPPED`, `RECEIVED`

### Models & Relationships:
- **`user_teams` (Many-to-Many Association Table):**
  - Links `users.id` and `teams.id` (`ondelete='CASCADE'`).
  - **Crucial Rule:** One Staff/Admin can belong to multiple Teams.
- **`User` (`UserMixin, db.Model`):**
  - Fields: `id`, `name`, `email` (unique, indexed), `password_hash`, `role` (`RoleEnum`, default `STAFF`), `is_active` (default `True`).
  - Methods: `set_password(password)` and `check_password(password)` using `werkzeug.security`.
  - Helper property: `is_admin` returns `self.role == RoleEnum.ADMIN`.
  - **Crucial Rule:** Admins are also Users—they can be assigned to Teams and can receive Tasks directly or via a Team.
- **`Team` (`db.Model`):**
  - Fields: `id`, `name` (unique), `description`.
  - Relationships: `members` (many-to-many with `User`), `tasks` (one-to-many with `Task`).
- **`Task` (`db.Model`):**
  - Fields:
    - `id`, `title`, `description`
    - `status` (`TaskStatus`, default `TODO`, indexed)
    - `pending_reason` (nullable Text — stores the reason when staff marks the task as `PENDING`, e.g., "Waiting for tools/materials: Pipa & Stopkran belum datang")
    - `review_notes` (nullable Text — stores admin feedback when rejecting/requesting continuation)
    - `due_date` (nullable), `created_at`
    - `created_by_id` (FK to `users.id`)
    - `assigned_user_id` (nullable FK to `users.id`), `assigned_team_id` (nullable FK to `teams.id`)
  - Relationships: `subtasks` (cascade delete-orphan), `item_requests` (cascade delete-orphan).
- **`SubTask` (`db.Model`):**
  - Fields: `id`, `task_id` (FK to `tasks.id`), `title`, `is_completed` (Boolean, default `False`), `created_by_id` (FK to `users.id`).
- **`ItemRequest` (`db.Model`):**
  - **Crucial Rule:** Item requests are strictly tied to a specific `Task` (e.g., Task "Perbaikan Pipa Air" has requests for "Pipa", "Sock", "Stopkran").
  - Fields: `id`, `task_id` (FK to `tasks.id`), `requested_by_id` (FK to `users.id`), `item_name`, `quantity` (String, e.g., "4 Batang", "2 Pcs"), `notes`, `status` (`ItemStatus`, default `REQUESTED`), `requested_at`, `ordered_at`, `shipped_at`, `received_at`.
- **`Notification` (`db.Model`):**
  - Fields: `id`, `user_id` (FK to `users.id`), `title`, `message`, `target_url`, `is_read` (default `False`), `created_at`.
- **`PushSubscription` (`db.Model`):**
  - Stores standard browser Web Push subscriptions per user (allows multiple devices per user).
  - Fields: `id`, `user_id` (FK to `users.id`), `endpoint` (unique), `p256dh`, `auth`, `created_at`.

---

## 3. END-TO-END WORKFLOWS & PERMISSIONS
Define a reusable helper `is_authorized_for_task(user, task)` that returns `True` if `user.is_admin`, OR `task.assigned_user_id == user.id`, OR (`task.assigned_team_id` and `task.assigned_team in user.teams`).

1. **Separated User Page & Team Page (Admin Only):**
   - **User Page (`admin/users.html`):** Admin manages user accounts ONLY (Create, Edit Name/Email/Password/Role `ADMIN` or `STAFF`, Toggle Active status). Do NOT assign teams on the user form. Display read-only badges of teams the user currently belongs to.
   - **Team Page (`admin/teams.html`):** Admin creates/edits/deletes Teams AND assigns/removes users (Staff or Admin) directly inside the Team Page using a mobile-friendly multi-select checkbox list of active users. Since it's Many-to-Many, assigning a user to Team B will not remove them from Team A.
2. **Task Assignment & Notification (Admin Only):**
   - Admin creates a Task and assigns it either to a specific User (Staff or Admin) OR to a Team.
   - Trigger in-app + Web Push notification to the assigned User or all members of the assigned Team.
3. **Subtasks & Task Status Execution (Authorized Staff/Admin):**
   - Assigned user can add multiple Subtasks to a Task and toggle `is_completed` (mark done/undone).
   - Adding or completing a subtask automatically moves Task status from `TODO` or `PENDING` to `IN_PROGRESS` (and clears `pending_reason`).
4. **Mark Task as PENDING with Reason (Authorized Staff/Admin):**
   - On the Task Detail page (`tasks/detail.html`), provide a dedicated action/form for the assigned user to mark the task as `PENDING` with a required `pending_reason` input (e.g., "Waiting for tools/materials: Pipa & Stopkran belum datang").
   - When marked `PENDING`, save `pending_reason`, display an amber alert banner on the task detail & task card showing the pending reason, and notify all Admins via in-app + Web Push notification.
   - Provide a button to resume the task (`IN_PROGRESS`), which clears `pending_reason`.
5. **Per-Task Multi-Item Material Request (Authorized Staff/Admin):**
   - Inside the Task Detail page (`tasks/detail.html`), provide a dynamic form (`item_names[]`, `quantities[]`, `notes[]`) with an "Add Row (+)" button so the user can request multiple items at once for that task (e.g., Pipa, Sock, Stopkran for "Perbaikan Pipa Air").
   - Submitting item requests notifies all Admins via in-app + Web Push notification.
6. **Logistics / Material Fulfillment Workflow:**
   - **Admin Logistics View & Task Detail View:** Admin sees all requested items grouped by or linked to their Task.
   - Admin can mark `REQUESTED` -> `ORDERED` (sets `ordered_at`, notifies requester).
   - Admin can mark `ORDERED` -> `SHIPPED` (sets `shipped_at`, notifies requester).
   - **Staff / Assigned User:** Can mark `SHIPPED` -> `RECEIVED` (sets `received_at`, notifies all Admins).
7. **Task Completion & Admin Review:**
   - Assigned user clicks "Tandai Tugas Selesai (Ajukan Review)" -> changes Task status to `WAITING_REVIEW` (clears `pending_reason`) and notifies all Admins.
   - **Admin Review:** Admin inspects the task (subtasks & items) and chooses:
     - **Approve (`COMPLETED`):** Task is marked `COMPLETED` and assigned user/team is notified.
     - **Needs Continuation / Revision (`IN_PROGRESS`):** Admin provides `review_notes`, status returns to `IN_PROGRESS`, and assigned user/team is notified with the notes.

---

## 4. PROGRESSIVE WEB APP (PWA), NATIVE WEB PUSH & AUTO-VAPID SPECIFICATION

### 4.1 Automatic VAPID Key Generation Helper (`_ensure_vapid_keys(app)` in `app/__init__.py`)
```python
import os, json, base64
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from dotenv import set_key

def _ensure_vapid_keys(app):
    pub = app.config.get("VAPID_PUBLIC_KEY", "").strip()
    priv = app.config.get("VAPID_PRIVATE_KEY", "").strip()
    if pub and priv:
        return

    os.makedirs(app.instance_path, exist_ok=True)
    vapid_file = os.path.join(app.instance_path, "vapid_keys.json")

    if os.path.exists(vapid_file):
        with open(vapid_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            app.config["VAPID_PUBLIC_KEY"] = data["public_key"]
            app.config["VAPID_PRIVATE_KEY"] = data["private_key"]
            return

    # Generate new ECDSA P-256 keypair in URL-safe Base64 (unpadded)
    private_key = ec.generate_private_key(ec.SECP256R1())
    priv_bytes = private_key.private_numbers().private_value.to_bytes(32, byteorder="big")
    pub_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )
    pub_b64 = base64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode("utf-8")
    priv_b64 = base64.urlsafe_b64encode(priv_bytes).rstrip(b"=").decode("utf-8")

    with open(vapid_file, "w", encoding="utf-8") as f:
        json.dump({"public_key": pub_b64, "private_key": priv_b64}, f, indent=2)

    env_path = os.path.join(os.path.dirname(app.root_path), ".env")
    if os.path.exists(env_path) and os.access(env_path, os.W_OK):
        try:
            set_key(env_path, "VAPID_PUBLIC_KEY", pub_b64)
            set_key(env_path, "VAPID_PRIVATE_KEY", priv_b64)
        except Exception:
            pass

    app.config["VAPID_PUBLIC_KEY"] = pub_b64
    app.config["VAPID_PRIVATE_KEY"] = priv_b64
```

### 4.2 Web App Manifest (`/manifest.json`) & Self-Contained SVG App Icons
- Create a clean, modern SVG app icon at `app/static/icons/icon.svg` (indigo `#4f46e5` rounded square background with a white checklist/lightning icon).
- Serve `/manifest.json` from root in `app/__init__.py` (or static file) with `Content-Type: application/manifest+json`:
```json
{
  "name": "TaskOps - Task & Material Management",
  "short_name": "TaskOps",
  "description": "Operational Task Management & Per-Task Material Request System",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "background_color": "#f8fafc",
  "theme_color": "#4f46e5",
  "orientation": "portrait-primary",
  "icons": [
    {
      "src": "/static/icons/icon.svg",
      "sizes": "192x192 512x512 any",
      "type": "image/svg+xml",
      "purpose": "any maskable"
    }
  ]
}
```

### 4.3 Required PWA Meta Tags in `app/templates/base.html`
Include these exact tags inside `<head>` of `base.html` so both Android Chrome and iOS Safari support "Add to Home Screen" in standalone fullscreen mode:
```html
<meta name="theme-color" content="#4f46e5">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="TaskOps">
<link rel="manifest" href="/manifest.json">
<link rel="icon" type="image/svg+xml" href="{{ url_for('static', filename='icons/icon.svg') }}">
<link rel="apple-touch-icon" href="{{ url_for('static', filename='icons/icon.svg') }}">
```

### 4.4 Service Worker (`/sw.js`) & Client Push + PWA Install Manager (`app/static/js/push.js`)
- Serve `/sw.js` at root with headers `Content-Type: application/javascript` and `Service-Worker-Allowed: /`.
- `/sw.js` must handle:
  - `install` (`self.skipWaiting()`) and `activate` (`event.waitUntil(clients.claim())`) so PWA criteria are satisfied immediately.
  - `push` event: parse JSON payload (`title`, `body`, `url`) and call `self.registration.showNotification(...)` with icon `/static/icons/icon.svg`.
  - `notificationclick` event: close notification, focus existing client window if open or `clients.openWindow(targetUrl)`.
- `app/static/js/push.js` must handle:
  - Registering `/sw.js` on page load.
  - Capturing `beforeinstallprompt` event on Android/Desktop to show an optional "Install App" button in the UI (`#btn-install-pwa`).
  - Providing an explicit user-triggered button (`#btn-enable-push`, required for iOS standalone PWA and modern browsers) AND automatic subscription renewal if permission is already `granted`.
  - Posting subscription JSON (`endpoint`, `keys.p256dh`, `keys.auth`) to `/auth/push-subscribe` with the `X-CSRFToken` header.
- Centralize all notifications in `app/services/notification.py` (`notify_user`, `notify_team`, `notify_all_admins`). Every call must create a `Notification` DB record AND attempt Web Push delivery via `pywebpush` (deleting expired 404/410 subscriptions).

---

## 5. DIRECTORY STRUCTURE
Maintain this exact directory structure:
```text
task_app/
├── app/
│   ├── __init__.py
│   ├── extensions.py
│   ├── models.py
│   ├── services/
│   │   └── notification.py
│   ├── blueprints/
│   │   ├── auth/
│   │   │   └── routes.py
│   │   ├── admin/
│   │   │   └── routes.py
│   │   ├── tasks/
│   │   │   └── routes.py
│   │   └── notifications/
│   │       └── routes.py
│   ├── static/
│   │   ├── icons/
│   │   │   └── icon.svg
│   │   └── js/
│   │       └── push.js
│   └── templates/
│       ├── base.html
│       ├── sw.js
│       ├── manifest.json
│       ├── components/
│       │   └── badges.html
│       ├── auth/
│       │   └── login.html
│       ├── tasks/
│       │   ├── index.html
│       │   ├── create.html
│       │   └── detail.html
│       ├── admin/
│       │   ├── users.html
│       │   ├── teams.html
│       │   ├── logistics.html
│       │   └── review_queue.html
│       └── notifications/
│           └── index.html
├── .env.example
├── config.py
├── run.py
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

---

## 6. ENVIRONMENT & DOCKER SPECIFICATION
- **`.env.example`** must include:
  ```ini
  SECRET_KEY=change-this-secret-key-in-production
  DATABASE_PATH=sqlite:///task_management.db
  GUNICORN_BIND=127.0.0.1:5000

  INITIAL_ADMIN_NAME=Super Admin
  INITIAL_ADMIN_EMAIL=admin@example.com
  INITIAL_ADMIN_PASSWORD=AdminPassword123!

  # Leave empty to auto-generate and persist in instance/vapid_keys.json & .env
  VAPID_PUBLIC_KEY=
  VAPID_PRIVATE_KEY=
  VAPID_CLAIM_EMAIL=mailto:admin@example.com
  ```
- **`Dockerfile`**:
  - Base image: `python:3.12-slim`
  - Default `ENV GUNICORN_BIND=127.0.0.1:5000`
  - Ensure `/app/instance` directory exists and is owned by `appuser` so SQLite and `vapid_keys.json` can be written without permission errors.
  - Command: `CMD ["sh", "-c", "gunicorn --workers 3 --bind \${GUNICORN_BIND:-127.0.0.1:5000} run:app"]`
- **`docker-compose.yml`**:
  - Load `.env` via `env_file: - .env`
  - Mount persistent volume `sqlite_data:/app/instance` (which stores both SQLite DB and auto-generated `vapid_keys.json`).
  - Use `network_mode: "host"` OR map ports matching `GUNICORN_BIND` (include clear comments in `docker-compose.yml` so binding to `127.0.0.1:5000` works out of the box).

---

## 7. STEP-BY-STEP EXECUTION PLAN

### Execution Protocol (Applies to Every Step)
Each step below follows this strict workflow — do not skip any stage:

1. **Plan** — Before writing any code, present a clear plan for the step: files to create/modify, key design decisions, and any assumptions.
2. **Grill** — Use `/grill-me` to interactively challenge the plan with clarifying questions. Resolve all open decisions before proceeding.
3. **User Reviews Plan** — Wait for explicit user approval of the plan before executing.
4. **Execute** — Implement exactly what was approved. No scope creep, no unrequested extras.
5. **User Reviews Work** — Wait for user to review the output and provide feedback.
6. **Revise or Advance** — Apply any requested revisions, then confirm before moving to the next step.

> Do not proceed to the next step until the current step has been explicitly approved.

---

### Steps

**Step 1 — Create `requirements.txt`**
List all required packages with pinned versions: `Flask`, `Flask-SQLAlchemy`, `Flask-Migrate`, `Flask-Login`, `Flask-WTF`, `python-dotenv`, `pywebpush`, `cryptography`, `gunicorn`, `psycopg2-binary`.

**Step 2 — Create `.env.example`**
Include all required env vars (`SECRET_KEY`, `DATABASE_PATH`, `GUNICORN_BIND`, `INITIAL_ADMIN_NAME`, `INITIAL_ADMIN_EMAIL`, `INITIAL_ADMIN_PASSWORD`, `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_CLAIM_EMAIL`) with placeholder values and inline comments.

**Step 3 — Create `config.py`**
Define `Config` class that reads all env vars via `os.environ.get(...)`, sets `SQLALCHEMY_DATABASE_URI` from `DATABASE_PATH`, and defaults to SQLite if unset.

**Step 4 — Create `app/extensions.py`**
Instantiate shared Flask extensions (`db`, `migrate`, `login_manager`, `csrf`) without binding them to an app yet.

**Step 5 — Create `app/models.py`**
Define all enums (`RoleEnum`, `TaskStatus`, `ItemStatus`), the `user_teams` association table, and all models (`User`, `Team`, `Task`, `SubTask`, `ItemRequest`, `Notification`, `PushSubscription`) with all fields, relationships, and helper methods (`set_password`, `check_password`, `is_admin`).

**Step 6 — Create `app/services/notification.py`**
Implement `notify_user`, `notify_team`, and `notify_all_admins` — each creates a `Notification` DB record and attempts Web Push delivery via `pywebpush`, deleting stale 404/410 subscriptions.

**Step 7 — Create `app/__init__.py`**
Implement `create_app()` factory with `_ensure_initial_admin()` (auto-create admin from `.env` on startup) and `_ensure_vapid_keys()` (auto-generate and persist VAPID keys), register all blueprints, and add `/manifest.json` and `/sw.js` routes with correct `Content-Type` and `Service-Worker-Allowed` headers.

**Step 8 — Create `run.py`**
Parse host and port from `GUNICORN_BIND` env var (defaulting to `127.0.0.1:5000`), call `create_app()`, and run the development server.

**Step 9 — Environment Initialization Verification**
Install dependencies (`pip install -r requirements.txt`), copy `.env.example` to `.env`, run `flask db init && flask db migrate && flask db upgrade`, and start the dev server to confirm the app boots, auto-creates the admin user, and auto-generates VAPID keys without errors.

**Step 10 — Implement `auth` blueprint (`app/blueprints/auth/routes.py`)**
Build login (email + password via Flask-Login), logout, and push-subscription endpoint (`POST /auth/push-subscribe`) that saves/updates a `PushSubscription` record for the current user.

**Step 11 — Implement `notifications` blueprint (`app/blueprints/notifications/routes.py`)**
Provide routes to list all notifications for the current user (with unread count), mark individual notifications as read, and mark all as read.

**Step 12 — Create PWA SVG App Icon (`app/static/icons/icon.svg`)**
Design a clean indigo (`#4f46e5`) rounded-square background with a white checklist/lightning icon, fully self-contained as a single SVG file.

**Step 13 — Create Web App Manifest (`app/templates/manifest.json`)**
Include `name`, `short_name`, `description`, `start_url`, `scope`, `display: standalone`, `background_color`, `theme_color`, `orientation`, and the SVG icon entry.

**Step 14 — Create Service Worker (`app/templates/sw.js`)**
Handle `install` (`skipWaiting`), `activate` (`clients.claim`), `push` (parse JSON payload and call `showNotification` with icon), and `notificationclick` (focus or open target URL) events.

**Step 15 — Create Client Push & PWA Install Manager (`app/static/js/push.js`)**
Register `/sw.js` on page load, capture `beforeinstallprompt` for `#btn-install-pwa`, provide `#btn-enable-push` for explicit push opt-in, auto-renew subscription if permission is already `granted`, and POST subscription JSON to `/auth/push-subscribe` with the `X-CSRFToken` header.

**Step 16 — Base Layout (`app/templates/base.html`)**
Implement sticky top bar (app title, notification bell with unread badge, push/install button, profile/logout), fixed bottom navigation bar on mobile (`md:hidden`), sidebar on desktop, and all required PWA meta tags (`theme-color`, `apple-mobile-web-app-capable`, `manifest` link, `apple-touch-icon`).

**Step 17 — Status Badge Component (`app/templates/components/badges.html`)**
Define reusable Jinja2 macros for `TaskStatus` and `ItemStatus` badges with consistent Tailwind color-coding.

**Step 18 — Login Page (`app/templates/auth/login.html`)**
Full-page centered card with email/password inputs, CSRF token, and Tailwind-styled submit button; include PWA install prompt area.

**Step 19 — App Initialization Verification**
Log in as the auto-created admin, verify the dashboard loads, bottom nav and sidebar render correctly, and the PWA manifest is served at `/manifest.json`.

**Step 20 — User List & Creation (`GET/POST /admin/users`)**
Show paginated list of all users with name, email, role badge, active status, and read-only team membership badges. Provide a form to create a new user (name, email, password, role).

**Step 21 — User Management Page (`app/templates/admin/users.html`)**
Responsive table/card list of users with role badge, active toggle, team membership badges (read-only), and create/edit form with CSRF token.

**Step 22 — User Edit & Toggle Active**
Routes: `GET/POST /admin/users/<id>/edit` and `POST /admin/users/<id>/toggle`. Allow admin to update name, email, password (optional), and role. Provide a toggle to activate/deactivate the user account.

**Step 23 — User Creation Verification**
Create a test Staff user and an additional Admin user via the UI. Verify role badges display correctly and team membership badges are read-only.

**Step 24 — Team List & Creation (`GET/POST /admin/teams`)**
Show all teams with name, description, and member count. Provide a form to create a new team.

**Step 25 — Team Edit & Member Assignment (`GET/POST /admin/teams/<id>/edit`)**
Allow admin to edit team name/description and assign/remove active users via a mobile-friendly multi-select checkbox list (many-to-many, does not remove user from other teams).

**Step 26 — Team Delete (`POST /admin/teams/<id>/delete`)**
Delete a team and its memberships (cascade); include a confirmation step to prevent accidental deletion.

**Step 27 — Team Management Page (`app/templates/admin/teams.html`)**
List of teams with member count, and edit form showing multi-select checkbox list of all active users; CSRF tokens on all forms.

**Step 28 — Team Creation Verification**
Create test teams and assign users to multiple teams. Verify many-to-many membership is correct and user's team badges update on the User page.

**Step 29 — Task Creation (`GET/POST /tasks/create`)**
Admin-only form with title, description, due date, and assignment dropdown (specific user OR team). Submission triggers in-app + Web Push notification to the assigned user or all team members.

**Step 30 — Task Create Page (`app/templates/tasks/create.html`)**
Form with title, description, due date picker, and assignment dropdown (user or team), CSRF token, and submit button.

**Step 31 — Task Creation Verification**
Create tasks assigned to individual users and to teams. Verify notifications are created in DB and delivered as Web Push (check browser).

**Step 32 — My Tasks / Team Tasks Dashboard (`GET /tasks/`)**
Show tasks assigned to the current user or their teams with filter tabs: All, TODO, IN_PROGRESS, PENDING, WAITING_REVIEW, COMPLETED. Display task cards with title, status badge, due date, and pending reason amber banner.

**Step 33 — Task List / Dashboard (`app/templates/tasks/index.html`)**
Filter tab bar at top, task cards with title, status badge, due date chip, pending reason amber banner, and quick-action links to task detail.

**Step 34 — Task Detail View (`GET /tasks/<id>`)**
Show full task info (title, description, assignment, due date, status, `pending_reason` banner, `review_notes` banner), subtask list with completion toggles, item request list with statuses, and all action buttons based on role and task state.

**Step 35 — Task Detail Page (`app/templates/tasks/detail.html`)**
Full task detail with status/pending/review banners, subtask checklist with add-subtask form, item request table with receive buttons, multi-item request form with dynamic "Add Row" button, and all status-transition action buttons; all POST forms include CSRF tokens.

**Step 36 — Add & Toggle Subtask**
Routes: `POST /tasks/<id>/subtasks` and `POST /tasks/<id>/subtasks/<sid>/toggle`. Allow authorized user to add and toggle subtask completion. Auto-advance task from `TODO` or `PENDING` to `IN_PROGRESS` and clear `pending_reason` on first subtask action.

**Step 37 — Mark Task as PENDING (`POST /tasks/<id>/pending`)**
Require a non-empty `pending_reason` input; save reason, set status to `PENDING`, display amber alert on task card and detail, and notify all admins via in-app + Web Push.

**Step 38 — Resume Task from PENDING (`POST /tasks/<id>/resume`)**
Set status back to `IN_PROGRESS`, clear `pending_reason`, and display updated task detail.

**Step 39 — Subtask & Pending Verification**
Add subtasks, toggle completion, mark a task PENDING with a reason, verify amber banner appears on card and detail, then resume and verify status returns to IN_PROGRESS.

**Step 40 — Multi-Item Material Request (`POST /tasks/<id>/request-items`)**
Dynamic form with `item_names[]`, `quantities[]`, `notes[]` arrays and a JS "Add Row (+)" button; bulk-create `ItemRequest` records for the task and notify all admins.

**Step 41 — Mark Item RECEIVED (`POST /tasks/<id>/items/<iid>/receive`)**
Staff/assigned user marks a `SHIPPED` item as `RECEIVED` (set `received_at`), notifies all admins.

**Step 42 — Global Logistics Dashboard (`GET /admin/logistics`)**
Display all `ItemRequest` records grouped by Task, filterable by `ItemStatus`. Allow admin to advance `REQUESTED` → `ORDERED` (set `ordered_at`, notify requester) and `ORDERED` → `SHIPPED` (set `shipped_at`, notify requester).

**Step 43 — Logistics Dashboard Page (`app/templates/admin/logistics.html`)**
Item requests grouped by task with status badges, timestamps, and one-click action buttons (CSRF-protected POST forms).

**Step 44 — Logistics Verification**
Request multiple items on a task, advance each through REQUESTED → ORDERED → SHIPPED → RECEIVED, and verify all timestamps and notifications fire correctly at each transition.

**Step 45 — Submit Task for Review (`POST /tasks/<id>/submit-review`)**
Set status to `WAITING_REVIEW`, clear `pending_reason`, notify all admins via in-app + Web Push.

**Step 46 — Task Review Queue (`GET /admin/review-queue`)**
List all tasks in `WAITING_REVIEW` status. Allow admin to Approve (→ `COMPLETED`, notify assigned user/team) or Request Continuation (→ `IN_PROGRESS`, save `review_notes`, notify assigned user/team).

**Step 47 — Review Queue Page (`app/templates/admin/review_queue.html`)**
Cards for each `WAITING_REVIEW` task showing subtask summary and item request summary, with Approve and Needs Continuation buttons (CSRF-protected, `review_notes` textarea for the latter).

**Step 48 — Review Workflow Verification**
Submit a task for review, approve it as admin, verify status is COMPLETED and notifications sent. Repeat with Needs Continuation, verify `review_notes` banner appears on task detail and status returns to IN_PROGRESS.

**Step 49 — Notifications Page (`app/templates/notifications/index.html`)**
Paginated list of notifications with read/unread styling, mark-as-read links, and "Mark All Read" button (CSRF-protected).

**Step 50 — Full End-to-End Verification**
Run through the complete workflow: environment init → login → create user → create team → create task → subtasks → pending → item request → logistics fulfillment → submit review → approve. Confirm all UI, notifications, PWA install, and Web Push work correctly on both mobile and desktop.

**Step 51 — Create `Dockerfile`**
Use `python:3.12-slim` base image, set `ENV GUNICORN_BIND=127.0.0.1:5000`, copy project files, install dependencies, create `appuser`, ensure `/app/instance` is owned by `appuser`, switch to `appuser`, and set `CMD` to launch Gunicorn with `${GUNICORN_BIND}`.

**Step 52 — Create `docker-compose.yml`**
Load `.env` via `env_file`, map ports matching `GUNICORN_BIND`, mount named volume `sqlite_data:/app/instance` for SQLite DB and `vapid_keys.json` persistence, with clear inline comments for host-binding and port configuration.

**Step 53 — Docker Verification**
Run `docker compose up --build`, verify the app starts correctly inside the container, admin is auto-created, and the SQLite DB and VAPID keys persist across container restarts.