# 🚀 TaskOps (PWA Edition)

**Operational Task Management & Per-Task Material Requisition System**

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Flask 3.x](https://img.shields.io/badge/Flask-3.0.3-black.svg)](https://flask.palletsprojects.com/)
[![Tailwind CSS](https://img.shields.io/badge/TailwindCSS-CDN-38B2AC.svg)](https://tailwindcss.com/)
[![PWA Ready](https://img.shields.io/badge/PWA-Installable-purple.svg)](https://web.dev/progressive-web-apps/)
[![VAPID Push](https://img.shields.io/badge/Web%20Push-Native%20VAPID-success.svg)](https://developer.mozilla.org/en-US/docs/Web/API/Push_API)
[![Docker Ready](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://www.docker.com/)

TaskOps is a production-ready, mobile-first Progressive Web App (PWA) built with **Python 3.12**, **Flask**, and **SQLAlchemy**. Designed specifically for operational workflows, maintenance crews, field technicians, and logistics coordination, TaskOps combines task scheduling, subtask checklists, field material requests, logistics fulfillment, and administrative quality control into a unified, installable application.

TaskOps operates with **zero external cloud push or auth dependencies**: authentication is completely self-contained, and background push notifications rely on native browser VAPID Web Push with automatic cryptographic key generation and local persistence.

---

## 📋 Table of Contents

- [Key Features](#-key-features)
  - [1. Operational Task Lifecycle](#1-operational-task-lifecycle)
  - [2. Subtask Checklists & Execution](#2-subtask-checklists--execution)
  - [3. Per-Task Material Requisition & Logistics](#3-per-task-material-requisition--logistics)
  - [4. Quality Control & Review Queue](#4-quality-control--review-queue)
  - [5. Activity Audit Trail & Attachments](#5-activity-audit-trail--attachments)
  - [6. Progressive Web App (PWA) & Native Web Push](#6-progressive-web-app-pwa--native-web-push)
  - [7. Role-Based Access & Team Management](#7-role-based-access--team-management)
- [Architecture & Tech Stack](#-architecture--tech-stack)
- [Directory Structure](#-directory-structure)
- [Environment Variables](#-environment-variables)
- [Local Development Setup](#-local-development-setup)
- [Step-by-Step Deployment to Docker](#-step-by-step-deployment-to-docker)
  - [Prerequisites](#prerequisites)
  - [Step 1: Clone Repository & Prepare Directory](#step-1-clone-repository--prepare-directory)
  - [Step 2: Configure Environment (.env)](#step-2-configure-environment-env)
  - [Step 3: Deploy with Docker Compose (Recommended)](#step-3-deploy-with-docker-compose-recommended)
  - [Step 4: Alternative — Standalone Docker Run](#step-4-alternative--standalone-docker-run)
  - [Step 5: Multi-Container Setup with PostgreSQL](#step-5-multi-container-setup-with-postgresql)
  - [Step 6: Production Reverse Proxy (HTTPS / Nginx)](#step-6-production-reverse-proxy-https--nginx)
  - [Step 7: Backup and Maintenance](#step-7-backup-and-maintenance)
- [Testing](#-testing)
- [License](#-license)

---

## ✨ Key Features

### 1. Operational Task Lifecycle
- **Status Progression Pipeline:**
  - `TODO` ➔ `IN_PROGRESS` ➔ `PENDING` ➔ `WAITING_REVIEW` ➔ `COMPLETED`.
- **Assignment Flexibility:** Assign tasks directly to an individual User or to an entire Team (automatically accessible to all active team members).
- **Priority Classification:** `LOW`, `MEDIUM`, `HIGH`, and `URGENT` priority levels with visual color badges.
- **Due Date Tracking:** Smart date tracking with real-time overdue alerts for delayed jobs.
- **Mandatory Pending Reason:** When pausing work (`PENDING`), staff must provide an explicit explanation (e.g., waiting for parts or client access), instantly alerting administrators with an amber alert banner across task cards and detail views.
- **Printable Work Orders:** One-click print-optimized view (`/tasks/<id>/print`) designed for physical sign-offs, field documentation, and offline handover.
- **Task Archival:** Soft-archive tasks to keep operational boards clean while preserving historical records.

### 2. Subtask Checklists & Execution
- **Dynamic Checklists:** Break down complex operations into manageable, trackable checkpoints.
- **Auto-Progression:** Adding or completing subtasks automatically transitions the parent task to `IN_PROGRESS` and clears any pending flags.
- **Subtask Progress Metrics:** Real-time completion progress bar (e.g., `3/5 subtasks completed`).
- **Subtask Summaries & Notes:** Attach progress notes and status summaries directly to individual subtasks.

### 3. Per-Task Material Requisition & Logistics
- **Context-Bound Material Requests:** Items are directly coupled to specific tasks (e.g., specific pipes, fittings, or tools needed for a maintenance job).
- **Dynamic Multi-Item Entry:** Staff can submit multiple items at once using the dynamic inline form (`item_names[]`, `quantities[]`, `notes[]`).
- **4-Stage Logistics Pipeline:**
  1. `REQUESTED` — Staff submits requisition; administrators are notified.
  2. `ORDERED` — Administrator approves and orders the item (`ordered_at` timestamp recorded).
  3. `SHIPPED` — Logistics dispatches the item (`shipped_at` timestamp recorded).
  4. `RECEIVED` — Field staff confirms receipt on site (`received_at` timestamp recorded).
- **Admin Logistics Dashboard (`/admin/logistics`):** Centralized view to monitor, filter, and advance item statuses individually or via bulk actions (**Order All**, **Ship All**).

### 4. Quality Control & Review Queue
- **Verification Workflow:** Field technicians submit completed jobs for review (`WAITING_REVIEW`), notifying supervisory staff.
- **Admin Review Queue (`/admin/review-queue`):** Supervisors review subtasks, photo evidence, and item fulfillments in one place.
- **Approve or Request Continuation:**
  - **Approve:** Marks the task `COMPLETED` and logs final sign-off.
  - **Needs Continuation:** Reverts status to `IN_PROGRESS` and attaches supervisor feedback notes (`review_notes`) displayed prominently to technicians.

### 5. Activity Audit Trail & Attachments
- **Automated Audit Logging:** Complete timeline recording every state transition, assignment change, subtask action, and material update.
- **File & Photo Evidence:**
  - Attach images, technical PDFs, and diagnostic files directly to tasks or specific subtasks.
  - Secure storage in `instance/uploads/` with UUID-prefixed filenames and mime-type verification.
  - In-browser image previews, instant downloads, and deletion controls.

### 6. Progressive Web App (PWA) & Native Web Push
- **Installable PWA:** Full "Add to Home Screen" support on Android and iOS (iOS 16.4+ standalone mode) with custom SVG branding and web app manifest.
- **Mobile-First UX:** Sticky header with notification bell, bottom navigation bar on mobile (`md:hidden`), and desktop sidebar.
- **Zero Third-Party Push Dependency:** Self-hosted ECDSA SECP256R1 (P-256) VAPID Web Push notifications via `pywebpush` and `cryptography`.
- **Auto-Generating Keypair:** Generates and persists VAPID cryptographic keys automatically on startup inside `instance/vapid_keys.json` and updates `.env`.
- **In-App Notification Center:** Unread count badge, instant status alerts, and one-click "Mark All as Read".
- **HTMX Reactive UI:** Smooth asynchronous interactions without full-page reloads.

### 7. Role-Based Access & Team Management
- **User Roles:** Distinct privileges for `ADMIN` (supervisory, logistics, dispatch, user management) and `STAFF` (operational execution, subtasks, material intake).
- **Multi-Team Association:** Many-to-Many team model where users can belong to multiple specialized operational crews.
- **Auto-Provisioned Admin:** Automatic bootstrap of the default Super Admin account on first startup based on `.env` variables.
- **User Life Cycle:** Activate, deactivate, edit profile details, and reset passwords securely.

---

## 🏗 Architecture & Tech Stack

```mermaid
flowchart TD
    subgraph Client["Client Tier (Mobile / Desktop)"]
        PWA["PWA Frontend (HTML5 / Tailwind CDN / HTMX)"]
        SW["Service Worker (/sw.js) & Web Push Manager"]
    end

    subgraph Server["Application Tier (Python 3.12)"]
        Gunicorn["Gunicorn WSGI Server (2 Workers, 4 Threads)"]
        Flask["Flask 3.0 Application"]
        AuthBP["Auth Blueprint (Flask-Login, CSRF)"]
        TaskBP["Tasks Blueprint (HTMX, Lifecycle, Uploads)"]
        AdminBP["Admin Blueprint (Logistics, Teams, Users, Review)"]
        NotifService["Notification Service (pywebpush, DB alerts)"]
    end

    subgraph Storage["Persistence Tier (Docker Volume)"]
        DB[("SQLite / PostgreSQL Database")]
        Uploads[("Uploaded Files (/app/instance/uploads)")]
        Keys[("VAPID Keys (/app/instance/vapid_keys.json)")]
    end

    PWA <-->|HTTP / HTMX / REST| Gunicorn
    SW <-->|Web Push Protocol / VAPID| NotifService
    Gunicorn --> Flask
    Flask --> AuthBP
    Flask --> TaskBP
    Flask --> AdminBP
    Flask --> NotifService
    Flask --> DB
    Flask --> Uploads
    NotifService --> Keys
```

| Layer | Technology | Description |
|---|---|---|
| **Language & Runtime** | Python 3.12 | Modern Python runtime |
| **Web Framework** | Flask 3.0.3 | Lightweight, modular WSGI application |
| **Database ORM** | Flask-SQLAlchemy 3.1.1 | Object-Relational Mapping with connection pooling |
| **Database Engine** | SQLite (Default) / PostgreSQL | Zero-config local SQLite or scalable PostgreSQL |
| **Migrations** | Flask-Migrate 4.0.7 (Alembic) | Database schema migrations |
| **Authentication** | Flask-Login 0.6.3 | Session management & RBAC |
| **Security** | Flask-WTF 1.2.1 | Global CSRF protection & form security |
| **Push Protocol** | pywebpush 1.14.0 + cryptography | RFC 8291/8292 standard VAPID Web Push |
| **WSGI Server** | Gunicorn 23.0.0 | High-performance multi-process WSGI server |
| **Frontend Styling** | Tailwind CSS (CDN) | Mobile-first utility-first design |
| **Dynamic UI** | HTMX 1.9 | Fast server-driven AJAX & DOM swapping |
| **Containerization** | Docker & Docker Compose | Multi-stage slim container with non-root user |

---

## 📂 Directory Structure

```text
TaskOps/
├── app/
│   ├── __init__.py                 # Application factory & VAPID bootstrap
│   ├── extensions.py               # Shared extensions (db, migrate, login, csrf)
│   ├── models/                     # SQLAlchemy data models & associations
│   │   ├── activity.py             # Task activity audit trail
│   │   ├── associations.py         # Many-to-many user_teams mapping
│   │   ├── attachment.py           # File upload records
│   │   ├── enums.py                # TaskStatus, TaskPriority, ItemStatus, RoleEnum
│   │   ├── item_request.py         # Per-task material requests
│   │   ├── notification.py         # In-app notification records
│   │   ├── push_subscription.py    # Browser Web Push endpoints
│   │   ├── subtask.py              # Subtask checklist models
│   │   ├── task.py                 # Core Task model
│   │   ├── team.py                 # Team models
│   │   └── user.py                 # User authentication & roles
│   ├── blueprints/                 # Modular route handlers
│   │   ├── admin/routes.py         # User, team, logistics & review management
│   │   ├── auth/routes.py          # Login, logout, profile & push subscription
│   │   ├── notifications/routes.py # In-app notification endpoints
│   │   └── tasks/routes.py         # Task execution, subtasks, items & uploads
│   ├── services/
│   │   ├── activity.py             # Activity logging service
│   │   └── notification.py         # Notification dispatch & pywebpush delivery
│   ├── static/
│   │   ├── icons/                  # PWA SVG & PNG application icons
│   │   └── js/
│   │       ├── htmx.min.js         # Reactive interaction library
│   │       └── push.js             # Service worker registration & push manager
│   └── templates/
│       ├── base.html               # Main layout (topbar, sidebar, bottom nav, PWA meta)
│       ├── manifest.json           # Web App Manifest
│       ├── sw.js                   # Service Worker (push notifications, caching)
│       ├── admin/                  # Admin templates (users, teams, logistics, reviews)
│       ├── auth/                   # Authentication templates (login, profile)
│       ├── components/             # Reusable macros (status & priority badges)
│       ├── notifications/          # Notification center template
│       └── tasks/                  # Task templates (index, detail, create, edit, print)
├── instance/                       # Persistent volume mount: SQLite DB, VAPID keys, uploads
├── migrations/                     # Alembic database migration scripts
├── tests/                          # Automated test suite and milestone verifications
├── .dockerignore                   # Docker build exclusions
├── .env.example                    # Environment variable template
├── config.py                       # Configuration loader
├── Dockerfile                      # Production container build specification
├── docker-compose.yml              # Container orchestration with volume persistence
├── requirements.txt                # Pinned Python dependencies
└── run.py                          # Development entrypoint
```

---

## ⚙️ Environment Variables

Copy `.env.example` to `.env` and adjust the variables to fit your environment:

```ini
# Flask Security
SECRET_KEY=replace-with-a-very-strong-secret-key-in-production

# Database Configuration
# - SQLite (Default): sqlite:///task_management.db (stored in instance/)
# - PostgreSQL: postgresql://user:password@hostname:5432/dbname
DATABASE_PATH=sqlite:///task_management.db

# Server Binding
GUNICORN_BIND=127.0.0.1:5000

# Initial Admin Bootstrap (Auto-provisioned on startup if not present)
INITIAL_ADMIN_NAME=Super Admin
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_EMAIL=admin@example.com
INITIAL_ADMIN_PHONE=+6281234567890
INITIAL_ADMIN_PASSWORD=AdminPassword123!

# Web Push Notification Keys (VAPID)
# Note: Leave empty to auto-generate ECDSA P-256 keys on first boot
VAPID_PUBLIC_KEY=
VAPID_PRIVATE_KEY=
VAPID_CLAIM_EMAIL=mailto:admin@example.com
```

---

## 💻 Local Development Setup

To run the application locally without Docker:

### 1. Prerequisites
- Python 3.12+
- Git

### 2. Setup Virtual Environment
```bash
# Clone the repository
git clone <repository-url>
cd TaskOps

# Create and activate virtual environment
# Windows (PowerShell):
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Linux / macOS:
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment
```bash
# Windows:
Copy-Item .env.example .env

# Linux / macOS:
cp .env.example .env
```
*(Open `.env` and verify your settings. Default values work out of the box for local development).*

### 5. Run Migrations & Start Server
```bash
# Apply database migrations
flask db upgrade

# Run development server
python run.py
```

The application will be live at `http://127.0.0.1:5000`. Log in using:
- **Email / Username:** `admin@example.com` or `admin`
- **Password:** `AdminPassword123!` (or the value configured in `.env`)

---

## 🐳 Step-by-Step Deployment to Docker

Deploying TaskOps with Docker guarantees consistent runtime isolation, automated migrations, non-root security (`appuser`), and permanent data persistence.

### Prerequisites
- [Docker Engine](https://docs.docker.com/engine/install/) (v20.10 or newer)
- [Docker Compose](https://docs.docker.com/compose/) (v2.0 or newer)

---

### Step 1: Clone Repository & Prepare Directory

```bash
# Clone the project repository
git clone <repository-url> taskops
cd taskops
```

---

### Step 2: Configure Environment (`.env`)

Before starting the containers, create your production `.env` configuration:

```bash
# Linux / macOS:
cp .env.example .env

# Windows (PowerShell):
Copy-Item .env.example .env
```

Edit `.env` using your preferred text editor (e.g. `nano .env` or `notepad .env`):
1. **Set a secure `SECRET_KEY`**:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   Paste the generated string into `SECRET_KEY`.
2. **Set your Initial Admin credentials**:
   Change `INITIAL_ADMIN_EMAIL` and `INITIAL_ADMIN_PASSWORD` to your desired production login.
3. **Leave `VAPID_PUBLIC_KEY` and `VAPID_PRIVATE_KEY` blank**:
   TaskOps will automatically generate a valid ECDSA P-256 keypair on first boot and save it inside the persistent volume.
4. **Set `VAPID_CLAIM_EMAIL`**:
   Set this to your admin email address prefixed with `mailto:` (e.g., `mailto:admin@yourcompany.com`).

---

### Step 3: Deploy with Docker Compose (Recommended)

Docker Compose manages container build, environment loading, port forwarding, and persistent volume attachments automatically.

#### 1. Inspect `docker-compose.yml`
TaskOps includes a production-ready `docker-compose.yml`:
```yaml
version: '3.8'

services:
  web:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: taskops_web
    restart: unless-stopped
    env_file:
      - .env
    environment:
      - GUNICORN_BIND=0.0.0.0:5000
    ports:
      - "5000:5000"
    volumes:
      - sqlite_data:/app/instance

volumes:
  sqlite_data:
    name: taskops_sqlite_data
```

> **Why Volume Persistence Matters:**
> The named volume `taskops_sqlite_data` mounts directly to `/app/instance`. This guarantees that:
> - SQLite database file (`task_management.db`)
> - Auto-generated VAPID push keys (`vapid_keys.json`)
> - Uploaded attachments (`uploads/`)
> **remain 100% persistent** even when containers are stopped, removed, or updated.

#### 2. Build and Start the Application
Run the following command in the project directory:

```bash
docker compose up -d --build
```

#### 3. Verify Container Status & Logs
```bash
# Check if the container is running
docker compose ps

# View real-time logs
docker compose logs -f web
```

You should see logs indicating:
- `flask db upgrade` completed successfully.
- Initial admin user checked/created.
- VAPID keys loaded or generated.
- Gunicorn listening at `http://0.0.0.0:5000` with 2 workers and 4 threads.

#### 4. Access the Application
Open your browser and navigate to:
```text
http://localhost:5000
```
Log in with your administrator credentials from `.env`.

#### 5. Stopping or Updating the Container
```bash
# Gracefully stop the application
docker compose down

# Rebuild after pulling new code
git pull
docker compose up -d --build
```

---

### Step 4: Alternative — Standalone Docker Run

If you prefer not using Docker Compose, you can build and run the image directly with the standard Docker CLI:

```bash
# 1. Build the Docker image
docker build -t taskops:latest .

# 2. Create the persistent data volume
docker volume create taskops_data

# 3. Run the container
docker run -d \
  --name taskops_web \
  --restart unless-stopped \
  -p 5000:5000 \
  --env-file .env \
  -e GUNICORN_BIND=0.0.0.0:5000 \
  -v taskops_data:/app/instance \
  taskops:latest

# 4. Inspect container logs
docker logs -f taskops_web
```

---

### Step 5: Multi-Container Setup with PostgreSQL

For large enterprise deployments requiring PostgreSQL instead of SQLite, use this multi-container compose configuration:

```yaml
version: '3.8'

services:
  db:
    image: postgres:16-alpine
    container_name: taskops_postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: taskops_user
      POSTGRES_PASSWORD: StrongDbPasswordHere
      POSTGRES_DB: taskops_db
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U taskops_user -d taskops_db"]
      interval: 5s
      timeout: 5s
      retries: 5

  web:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: taskops_web
    restart: unless-stopped
    depends_on:
      db:
        condition: service_healthy
    env_file:
      - .env
    environment:
      - GUNICORN_BIND=0.0.0.0:5000
      - DATABASE_PATH=postgresql://taskops_user:StrongDbPasswordHere@db:5432/taskops_db
    ports:
      - "5000:5000"
    volumes:
      - app_instance:/app/instance

volumes:
  postgres_data:
  app_instance:
```

---

### Step 6: Production Reverse Proxy (HTTPS / Nginx)

> [!IMPORTANT]
> **PWA & Web Push Requirement:** Modern web browsers (Chrome, Safari, Firefox, Edge) require a secure **HTTPS** origin (or `localhost`) to register Service Workers and activate Web Push notifications.

Here is an example Nginx virtual host configuration with SSL termination and WebSocket/SSE headers:

```nginx
server {
    listen 80;
    server_name tasks.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name tasks.yourdomain.com;

    # SSL Certificates (e.g. Let's Encrypt Certbot)
    ssl_certificate /etc/letsencrypt/live/tasks.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/tasks.yourdomain.com/privkey.pem;

    client_max_body_size 20M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket / Long-lived connections
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Cache static assets
    location /static/ {
        proxy_pass http://127.0.0.1:5000;
        proxy_cache_valid 200 30d;
        add_header Cache-Control "public, max-age=2592000";
    }
}
```

---

### Step 7: Backup and Maintenance

#### Backing Up SQLite Database and Uploaded Files
Because all state is contained inside the Docker volume attached to `/app/instance`, creating a complete backup is as simple as running:

```bash
# Create a timestamped compressed backup tarball
docker run --rm \
  -v taskops_sqlite_data:/source:ro \
  -v $(pwd):/backup \
  alpine tar -czvf /backup/taskops_backup_$(date +%Y%m%d_%H%M%S).tar.gz -C /source .
```

#### Restoring from Backup
```bash
# Stop the web container
docker compose down

# Restore into the volume
docker run --rm \
  -v taskops_sqlite_data:/target \
  -v $(pwd):/backup \
  alpine sh -c "rm -rf /target/* && tar -xzvf /backup/taskops_backup_<timestamp>.tar.gz -C /target"

# Restart the application
docker compose up -d
```

---

## 🧪 Testing

TaskOps comes with end-to-end integration and unit verification test suites under `tests/`.

```bash
# Run automated tests using python
python -m unittest discover -s tests -p "test_*.py"

# Or run specific milestone verification suites:
python tests/verify_milestone_6_e2e.py
python tests/test_htmx_interactions.py
python tests/test_subtask_summary_and_attachments.py
```

---

## 🔒 Security Best Practices

1. **Change Default Credentials:** Always update `INITIAL_ADMIN_EMAIL` and `INITIAL_ADMIN_PASSWORD` in your `.env` before public deployment.
2. **Rotate `SECRET_KEY`:** Never use the fallback secret key in production; generate a 256-bit cryptographic hex string.
3. **Non-Root Execution:** The production `Dockerfile` drops root privileges to `appuser` (UID 1000) for security hardening.
4. **CSRF Protection:** Flask-WTF enforces CSRF token validation on all state-altering requests (standard POST and HTMX headers).
5. **Upload Sanitation:** File uploads are checked against an extension whitelist and stored using random UUIDs to prevent directory traversal and arbitrary script execution.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

