

## Run the App Locally with Your Own DB

### Current Architecture Problem
Right now, the app depends on Lovable Cloud for three things:
1. **Frontend hosting** (Vite dev server — easy to run locally)
2. **Edge functions** (`chat`, `db-proxy`, `search-projects` — these run on Supabase/Deno)
3. **Database** (conversations, messages, db_connections tables — stored in Lovable Cloud)

To run locally, we need to replace the edge functions with a local backend and point the app at your own database.

### Plan

#### 1. Add a Local Express API Server
Create a small Node.js/Express server (`server/` folder) that replicates the three edge functions locally:

| Endpoint | Replaces | Purpose |
|----------|----------|---------|
| `POST /api/chat` | `chat` edge function | Proxies AI chat (calls Lovable AI gateway or OpenAI directly) |
| `POST /api/db-proxy` | `db-proxy` edge function | Connects to your SQL Server/PostgreSQL and runs parameterized queries |
| `POST /api/search-projects` | `search-projects` edge function | Queries your DB for project data |

- Uses `mssql` and `pg` npm packages (same drivers as the edge functions)
- Reads connection config from a local `.env` file or from a local SQLite/JSON config

#### 2. Add Environment Toggle in Frontend
- Add a `VITE_API_BASE_URL` env variable
- When set (e.g., `http://localhost:3001/api`), the frontend calls the local server instead of Supabase edge functions
- Update `streamChat.ts` and `Index.tsx` to use this base URL
- When not set, falls back to Supabase (current behavior — works in Lovable)

#### 3. Local Database for App State
For conversations/messages storage locally, two options:
- **Option A**: Keep using Lovable Cloud for conversations (simplest — just the project data comes from your DB)
- **Option B**: Add SQLite or use your same DB server for conversations too

I recommend **Option A** for now — your external DB serves project data, Lovable Cloud handles chat history.

#### 4. Local Run Instructions
```text
# 1. Clone repo from GitHub
git clone <your-repo-url>
cd project

# 2. Install frontend deps
npm install

# 3. Install server deps
cd server && npm install && cd ..

# 4. Create server/.env with your DB credentials
#    DB_HOST=your-server
#    DB_PORT=1433
#    DB_NAME=your-db
#    DB_USER=your-user
#    DB_PASSWORD=your-password
#    DB_TYPE=sqlserver
#    LOVABLE_API_KEY=your-key (for AI chat)

# 5. Start local API server
npm run server  (port 3001)

# 6. Start frontend
npm run dev     (port 8080)
```

#### 5. Files to Create/Modify

| File | Action |
|------|--------|
| `server/index.ts` | Create — Express server with 3 API endpoints |
| `server/package.json` | Create — server dependencies (express, mssql, pg, cors, dotenv) |
| `server/.env.example` | Create — template for DB credentials |
| `src/lib/streamChat.ts` | Modify — use `VITE_API_BASE_URL` when set |
| `src/pages/Index.tsx` | Modify — use local API for db-proxy calls when configured |
| `src/pages/Settings.tsx` | Modify — use local API for connection management |
| `package.json` | Modify — add `server` script |

### What This Gives You
- Run the full app on your machine or app server
- Connect directly to your SQL Server/PostgreSQL
- AI chat still works (via API key)
- Same UI, same features, no cloud dependency for project data
- Easy to deploy to any Node.js app server later

