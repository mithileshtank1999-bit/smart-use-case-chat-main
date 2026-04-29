# Local Deployment Guide — Project Intelligence

> **Choose your backend:** This app supports two backend options — **Node.js (Express)** or **Python (FastAPI)**. Pick whichever fits your stack. Both expose identical API endpoints and work with the same frontend.

---

## Table of Contents

1. [How It Works](#how-it-works)
2. [Prerequisites](#prerequisites)
3. [Project Structure](#project-structure)
4. [Option A: Node.js (Express) Server](#option-a-nodejs-express-server)
5. [Option B: Python (FastAPI) Server](#option-b-python-fastapi-server)
6. [Frontend Configuration](#frontend-configuration)
7. [Database Setup](#database-setup)
8. [Running the Full Stack](#running-the-full-stack)
9. [Health Check & Troubleshooting](#health-check--troubleshooting)
10. [Deploying to an App Server](#deploying-to-an-app-server)

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                        ARCHITECTURE                             │
│                                                                 │
│  ┌──────────────┐     ┌──────────────────────┐     ┌─────────┐ │
│  │   Browser     │────▶│  Backend Server       │────▶│  Your   │ │
│  │   (Vite)      │     │  Express (:3001)      │     │   DB    │ │
│  │   :8080       │     │  — OR —               │     │  SQL /  │ │
│  │               │◀────│  FastAPI (:8000)       │◀────│  PG     │ │
│  └──────────────┘     └──────────┬───────────┘     └─────────┘ │
│                                  │                              │
│                                  ▼                              │
│                        ┌──────────────────┐                     │
│                        │  Lovable AI      │                     │
│                        │  Gateway         │                     │
│                        │  (Chat/Streaming)│                     │
│                        └──────────────────┘                     │
└─────────────────────────────────────────────────────────────────┘
```

### Request Flow

1. **User opens the app** at `http://localhost:8080`
2. **Frontend checks** `VITE_API_BASE_URL`:
   - If set → calls your **local backend** (Express or FastAPI)
   - If not set → falls back to **Lovable Cloud** edge functions
3. **Backend receives the request** and routes it:
   - `/api/db-proxy` → Queries your SQL Server / PostgreSQL for project data
   - `/api/search-projects` → Searches projects with filters
   - `/api/chat` → Streams AI responses via the Lovable AI gateway
4. **Results are returned** to the frontend and rendered in the UI

### API Endpoints (identical for both backends)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/db-proxy` | POST | General DB operations (test connection, list/search projects) |
| `/api/search-projects` | POST | Search projects with filters |
| `/api/chat` | POST | AI chat with streaming SSE responses |

---

## Prerequisites

| Requirement | Express (Option A) | FastAPI (Option B) |
|-------------|--------------------|--------------------|
| Runtime | Node.js 18+ | Python 3.10+ |
| Package Manager | npm or bun | pip |
| Database | SQL Server or PostgreSQL | SQL Server or PostgreSQL |
| AI Key | `LOVABLE_API_KEY` | `LOVABLE_API_KEY` |

---

## Project Structure

```
project-root/
├── src/                        # Frontend (React + Vite)
│   ├── lib/
│   │   ├── apiClient.ts        # Switches between local/cloud API
│   │   └── streamChat.ts       # Handles SSE streaming for chat
│   ├── pages/
│   │   ├── Index.tsx            # Main chat page
│   │   └── Settings.tsx         # DB connection settings
│   └── ...
│
├── server/                     # Option A — Node.js backend
│   ├── index.ts                # Express server with all endpoints
│   ├── package.json            # Node dependencies
│   ├── tsconfig.json           # TypeScript config
│   └── .env.example            # Environment template
│
├── server-python/              # Option B — Python backend
│   ├── main.py                 # FastAPI server with all endpoints
│   ├── requirements.txt        # Python dependencies
│   └── .env.example            # Environment template
│
├── supabase/functions/         # Cloud edge functions (used when no local server)
│   ├── chat/index.ts
│   ├── db-proxy/index.ts
│   └── search-projects/index.ts
│
├── LOCAL_SETUP.md              # ← You are here
└── .env.local                  # Frontend env override (create this)
```

---

## Option A: Node.js (Express) Server

### Step 1 — Install dependencies

```bash
# From project root
npm install
cd server && npm install
```

### Step 2 — Configure environment

```bash
cp server/.env.example server/.env
```

Edit `server/.env`:

```env
# Database
DB_TYPE=sqlserver              # "sqlserver" or "postgres"
DB_HOST=your-server.database.windows.net
DB_PORT=1433                   # 1433 for SQL Server, 5432 for PostgreSQL
DB_NAME=your-database
DB_USER=your-username
DB_PASSWORD=your-password

# AI Chat
LOVABLE_API_KEY=your-lovable-api-key

# Server
PORT=3001
```

### Step 3 — Start the server

```bash
cd server && npm start
```

You should see:
```
✅ Local API server running at http://localhost:3001
   DB_TYPE: sqlserver
   DB_HOST: your-server.database.windows.net
```

---

## Option B: Python (FastAPI) Server

### Step 1 — Set up Python environment

```bash
cd server-python
python -m venv venv

# Activate:
source venv/bin/activate       # macOS / Linux
venv\Scripts\activate          # Windows
```

### Step 2 — Install dependencies

```bash
pip install -r requirements.txt
```

This installs: `fastapi`, `uvicorn`, `httpx`, `python-dotenv`, `asyncpg` (PostgreSQL), `pymssql` (SQL Server).

### Step 3 — Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Database
DB_TYPE=sqlserver              # "sqlserver" or "postgres"
DB_HOST=your-server.database.windows.net
DB_PORT=1433                   # 1433 for SQL Server, 5432 for PostgreSQL
DB_NAME=your-database
DB_USER=your-username
DB_PASSWORD=your-password

# AI Chat
LOVABLE_API_KEY=your-lovable-api-key

# Server
PORT=8000
```

### Step 3 — Start the server

```bash
python main.py
```

You should see:
```
✅ FastAPI server running at http://localhost:8000
   DB_TYPE: sqlserver
   DB_HOST: your-server.database.windows.net
```

---

## Frontend Configuration

Create a `.env.local` file in the **project root** (not inside `server/`):

```env
# For Express (Option A):
VITE_API_BASE_URL=http://localhost:3001/api

# For FastAPI (Option B):
VITE_API_BASE_URL=http://localhost:8000/api
```

> **How the switch works:** The file `src/lib/apiClient.ts` checks this variable.
> - If `VITE_API_BASE_URL` is set → all API calls go to your local server
> - If it's not set → calls go to Lovable Cloud edge functions
> - This means the **same codebase** works in both local and cloud environments

---

## Database Setup

Your database needs a `projects` table. Here are creation scripts for both engines:

### SQL Server

```sql
CREATE TABLE projects (
    project_id    VARCHAR(50) PRIMARY KEY,
    project_name  VARCHAR(200) NOT NULL,
    status        VARCHAR(50)  NULL,
    go_live_date  DATE         NULL,
    portfolio_name VARCHAR(200) NULL,
    portfolio_owner VARCHAR(200) NULL,
    account_name  VARCHAR(200) NULL,
    account_id    VARCHAR(50)  NULL,
    project_manager VARCHAR(200) NULL
);

-- Sample data
INSERT INTO projects VALUES
('PRJ001', 'Banking Portal Redesign', 'Active', '2026-06-30', 'Digital Banking', 'John Smith', 'ABC Bank', 'ACC001', 'Alice Johnson'),
('PRJ002', 'Mobile App Migration', 'In Progress', '2026-09-15', 'Mobile Solutions', 'Jane Doe', 'XYZ Corp', 'ACC002', 'Bob Williams');
```

### PostgreSQL

```sql
CREATE TABLE projects (
    project_id    VARCHAR(50) PRIMARY KEY,
    project_name  VARCHAR(200) NOT NULL,
    status        VARCHAR(50),
    go_live_date  DATE,
    portfolio_name VARCHAR(200),
    portfolio_owner VARCHAR(200),
    account_name  VARCHAR(200),
    account_id    VARCHAR(50),
    project_manager VARCHAR(200)
);

-- Sample data
INSERT INTO projects VALUES
('PRJ001', 'Banking Portal Redesign', 'Active', '2026-06-30', 'Digital Banking', 'John Smith', 'ABC Bank', 'ACC001', 'Alice Johnson'),
('PRJ002', 'Mobile App Migration', 'In Progress', '2026-09-15', 'Mobile Solutions', 'Jane Doe', 'XYZ Corp', 'ACC002', 'Bob Williams');
```

### Column Reference

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `project_id` | VARCHAR(50) | ✅ | Unique project identifier |
| `project_name` | VARCHAR(200) | ✅ | Display name of the project |
| `status` | VARCHAR(50) | Optional | Active, In Progress, Delayed, Completed, On Hold |
| `go_live_date` | DATE | Optional | Target go-live date |
| `portfolio_name` | VARCHAR(200) | Optional | Portfolio grouping |
| `portfolio_owner` | VARCHAR(200) | Optional | Portfolio owner name |
| `account_name` | VARCHAR(200) | Optional | Client/account name |
| `account_id` | VARCHAR(50) | Optional | Client/account ID |
| `project_manager` | VARCHAR(200) | Optional | Assigned project manager |

---

## Running the Full Stack

### With Express:

```bash
# Terminal 1 — Backend
cd server && npm start

# Terminal 2 — Frontend
npm run dev
```

### With FastAPI:

```bash
# Terminal 1 — Backend
cd server-python && source venv/bin/activate && python main.py

# Terminal 2 — Frontend
npm run dev
```

Then open **http://localhost:8080** in your browser.

---

## Health Check & Troubleshooting

### Test your database connection

Use `curl` or Postman to verify the backend is working:

```bash
# Test connection (Express)
curl -X POST http://localhost:3001/api/db-proxy \
  -H "Content-Type: application/json" \
  -d '{"query_type": "test_connection"}'

# Test connection (FastAPI)
curl -X POST http://localhost:8000/api/db-proxy \
  -H "Content-Type: application/json" \
  -d '{"query_type": "test_connection"}'

# Expected response:
# {"success": true, "message": "Connection successful"}
```

### List projects

```bash
curl -X POST http://localhost:3001/api/db-proxy \
  -H "Content-Type: application/json" \
  -d '{"query_type": "list_projects"}'

# Expected: {"results": [{"project_id": "PRJ001", "project_name": "..."}]}
```

### Search projects with filters

```bash
curl -X POST http://localhost:3001/api/search-projects \
  -H "Content-Type: application/json" \
  -d '{"filters": {"status": "Active"}}'
```

### Test AI chat

```bash
curl -X POST http://localhost:3001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Show me active projects"}]}'

# Expected: Streaming SSE response
```

### Common Issues

| Problem | Cause | Fix |
|---------|-------|-----|
| `ECONNREFUSED` on DB | Wrong host/port | Check `DB_HOST` and `DB_PORT` in `.env` |
| `Login failed` | Bad credentials | Verify `DB_USER` and `DB_PASSWORD` |
| `relation "projects" does not exist` | Table not created | Run the CREATE TABLE script above |
| `LOVABLE_API_KEY` error | Missing key | Add your API key to `.env` |
| Frontend still calls cloud | `VITE_API_BASE_URL` not set | Create `.env.local` in project root, restart `npm run dev` |
| CORS errors | Backend not running | Start the backend server first |

---

## Deploying to an App Server

### Express on a Linux/Windows Server

```bash
# 1. Build frontend
npm run build

# 2. Serve dist/ with nginx (or copy to IIS wwwroot)
# nginx config:
#   location / { root /path/to/dist; try_files $uri /index.html; }

# 3. Run backend (use pm2 for production)
npm install -g pm2
cd server && pm2 start "node --loader ts-node/esm index.ts" --name api

# 4. Set VITE_API_BASE_URL during build:
VITE_API_BASE_URL=https://your-server.com/api npm run build
```

### FastAPI on a Linux Server

```bash
# 1. Build frontend
npm run build

# 2. Serve dist/ with nginx

# 3. Run backend with gunicorn + uvicorn workers
cd server-python
pip install gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# 4. Set VITE_API_BASE_URL during build:
VITE_API_BASE_URL=https://your-server.com/api npm run build
```

### FastAPI on Windows (IIS)

```bash
# 1. Build frontend → copy dist/ to IIS site

# 2. Run FastAPI as a Windows service or use waitress:
pip install waitress
cd server-python
waitress-serve --port=8000 main:app
```

---

## Environment Variables Reference

### Backend (server/.env or server-python/.env)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DB_TYPE` | Yes | `sqlserver` | `sqlserver` or `postgres` |
| `DB_HOST` | Yes | — | Database server hostname |
| `DB_PORT` | No | `1433`/`5432` | Database port |
| `DB_NAME` | Yes | — | Database name |
| `DB_USER` | Yes | — | Database username |
| `DB_PASSWORD` | Yes | — | Database password |
| `LOVABLE_API_KEY` | Yes | — | Lovable AI gateway API key |
| `PORT` | No | `3001`/`8000` | Server port |

### Frontend (.env.local)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VITE_API_BASE_URL` | No | — | When set, routes API calls to local server. When absent, uses Lovable Cloud. |

---

## Timesheet (Minimum Command)

The backend exposes helpers for **schema introspection** and a **single-string command** runner to keep timesheet inserts aligned with your real DB schema:

- `GET /api/timesheet/schema` — returns columns for `timesheet`, `employee`, `employeeallocation`, and your configured `DB_PROJECT_TABLE`.
- `POST /api/timesheet/command` — runs one validated command string.

Example command strings:

- `today 8h item=Config desc="SDG development" template=12345`
- `2026-04-29 09:00-17:00 item=Config desc="SDG development" template=12345`

Note: For **100% accuracy**, the server requires an existing template row (either `template=...` or an existing timesheet row for the same employee+project) so it can copy platform-required IDs instead of guessing defaults.
