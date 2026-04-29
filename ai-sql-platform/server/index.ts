import "dotenv/config";
import express from "express";
import cors from "cors";
import mssql from "mssql";
import pg from "pg";

const app = express();
app.use(cors());
app.use(express.json());

const PORT = parseInt(process.env.PORT || "3001");

// ─── DB helpers ───────────────────────────────────────────────

function getDbConfig() {
  return {
    db_type: process.env.DB_TYPE || "sqlserver",
    host: process.env.DB_HOST || "",
    port: parseInt(process.env.DB_PORT || (process.env.DB_TYPE === "postgres" ? "5432" : "1433")),
    database_name: process.env.DB_NAME || "",
    username: process.env.DB_USER || "",
    password: process.env.DB_PASSWORD || "",
  };
}

async function querySqlServer(sql: string, params: any[] = []) {
  const cfg = getDbConfig();
  const pool = await mssql.connect({
    user: cfg.username,
    password: cfg.password,
    server: cfg.host,
    port: cfg.port,
    database: cfg.database_name,
    options: { encrypt: true, trustServerCertificate: true },
    connectionTimeout: 10000,
    requestTimeout: 15000,
  });
  try {
    const request = pool.request();
    params.forEach((p, i) => request.input(`p${i}`, p));
    const result = await request.query(sql);
    return result.recordset;
  } finally {
    await pool.close();
  }
}

async function queryPostgres(sql: string, params: any[] = []) {
  const cfg = getDbConfig();
  const client = new pg.Client({
    host: cfg.host,
    port: cfg.port,
    database: cfg.database_name,
    user: cfg.username,
    password: cfg.password,
    ssl: { rejectUnauthorized: false },
    connectionTimeoutMillis: 10000,
  });
  await client.connect();
  try {
    const pgSql = sql.replace(/@p(\d+)/g, (_, n: string) => `$${parseInt(n) + 1}`);
    const result = await client.query(pgSql, params);
    return result.rows;
  } finally {
    await client.end();
  }
}

async function query(sql: string, params: any[] = []) {
  const cfg = getDbConfig();
  if (cfg.db_type === "postgres") return queryPostgres(sql, params);
  return querySqlServer(sql, params);
}

// ─── /api/db-proxy ────────────────────────────────────────────

app.post("/api/db-proxy", async (req, res) => {
  try {
    const { query_type, filters } = req.body;
    if (!query_type) return res.status(400).json({ error: "query_type is required" });

    const cfg = getDbConfig();
    if (!cfg.host) {
      return res.json({ error: "no_connection", message: "No database configured. Set DB_* env vars in server/.env" });
    }

    switch (query_type) {
      case "test_connection": {
        await query("SELECT 1 AS test");
        return res.json({ success: true, message: "Connection successful" });
      }
      case "list_projects": {
        const results = await query("SELECT project_id, project_name FROM projects ORDER BY project_name");
        return res.json({ results });
      }
      case "search_projects": {
        let sql = "SELECT * FROM projects WHERE 1=1";
        const params: any[] = [];
        let pi = 0;
        if (filters?.project_id) { sql += ` AND project_id = @p${pi}`; params.push(filters.project_id); pi++; }
        if (filters?.project_name) { sql += ` AND project_name LIKE @p${pi}`; params.push(`%${filters.project_name}%`); pi++; }
        if (filters?.account_name) { sql += ` AND account_name LIKE @p${pi}`; params.push(`%${filters.account_name}%`); pi++; }
        if (filters?.account_id) { sql += ` AND account_id = @p${pi}`; params.push(filters.account_id); pi++; }
        if (filters?.portfolio_name) { sql += ` AND portfolio_name LIKE @p${pi}`; params.push(`%${filters.portfolio_name}%`); pi++; }
        if (filters?.status) { sql += ` AND status LIKE @p${pi}`; params.push(`%${filters.status}%`); pi++; }
        if (filters?.project_manager) { sql += ` AND project_manager LIKE @p${pi}`; params.push(`%${filters.project_manager}%`); pi++; }
        sql += " ORDER BY project_id";
        const results = await query(sql, params);
        return res.json({ results });
      }
      default:
        return res.status(400).json({ error: `Unknown query_type: ${query_type}` });
    }
  } catch (e: any) {
    console.error("db-proxy error:", e);
    res.status(500).json({ error: e.message || "Unknown error" });
  }
});

// ─── /api/search-projects (same as db-proxy search_projects) ──

app.post("/api/search-projects", async (req, res) => {
  try {
    const { filters } = req.body;
    let sql = "SELECT * FROM projects WHERE 1=1";
    const params: any[] = [];
    let pi = 0;
    if (filters?.project_id) { sql += ` AND project_id = @p${pi}`; params.push(filters.project_id); pi++; }
    if (filters?.project_name) { sql += ` AND project_name LIKE @p${pi}`; params.push(`%${filters.project_name}%`); pi++; }
    if (filters?.account_name) { sql += ` AND account_name LIKE @p${pi}`; params.push(`%${filters.account_name}%`); pi++; }
    if (filters?.account_id) { sql += ` AND account_id = @p${pi}`; params.push(filters.account_id); pi++; }
    if (filters?.portfolio_name) { sql += ` AND portfolio_name LIKE @p${pi}`; params.push(`%${filters.portfolio_name}%`); pi++; }
    if (filters?.status) { sql += ` AND status LIKE @p${pi}`; params.push(`%${filters.status}%`); pi++; }
    if (filters?.project_manager) { sql += ` AND project_manager LIKE @p${pi}`; params.push(`%${filters.project_manager}%`); pi++; }
    sql += " ORDER BY project_id";
    const results = await query(sql, params);
    res.json({ results });
  } catch (e: any) {
    console.error("search-projects error:", e);
    res.status(500).json({ error: e.message || "Unknown error" });
  }
});

// ─── /api/chat (streaming proxy to Lovable AI gateway) ────────

const SYSTEM_PROMPT = `You are a Project Intelligence Assistant (Agent PMP). You operate using a two-stage prompt architecture:

**Stage 1 — Query Understanding (NL → Structured Filters):**
When a user asks a question, first extract structured search filters from their natural language query. Identify fields such as:
- project_id, project_name, account_name, account_id, portfolio_name, module_name, journey_name
- employee_name, resource_name, case_id, test_case_id
- status (Active, Delayed, Completed, In Progress, On Hold, etc.)
- date ranges, model_name, search queries

Present the extracted filters as a JSON block so the user can confirm or adjust before retrieval.

**Stage 2 — Data Retrieval & Response:**
After filters are confirmed, present the structured query that would be sent to the portal API. Since the portal API is not yet connected, generate a realistic mock/demo response.

IMPORTANT: When returning project data results, you MUST format them as a JSON code block containing an array of objects with these exact fields:
\`\`\`json
[
  {
    "project_id": "PRJ001",
    "project_name": "Example Project",
    "status": "Active",
    "go_live_date": "2026-06-30",
    "portfolio_name": "Banking Portfolio",
    "portfolio_owner": "John Smith",
    "account_name": "ABC Bank",
    "project_manager": "Alice Johnson"
  }
]
\`\`\`

This format will be automatically rendered as an interactive table in the UI.

**Response Guidelines:**
- Always show the extracted filters first as a JSON code block
- Then show the simulated structured response using the project array format above
- Use markdown tables for non-project tabular data (timesheets, defects, test cases)
- Use bullet points and headers for readability
- Clearly label mock data as "[Demo Data — API not yet connected]"
- When the user selects a use case from the sidebar, treat the pre-filled prompt template as their query and proceed with Stage 1

**Supported Use Case Categories:**
Project Planning Intelligence, Timesheet Management, Defect & Case Management, Test Cases Management, Intelligent Document Management, Report Automation, AI Meeting Summary, Smart Issue/Risk Analysis, Resource Allocation & Optimization`;

app.post("/api/chat", async (req, res) => {
  try {
    const { messages } = req.body;
    const LOVABLE_API_KEY = process.env.LOVABLE_API_KEY;
    if (!LOVABLE_API_KEY) {
      return res.status(500).json({ error: "LOVABLE_API_KEY is not configured in server/.env" });
    }

    const response = await fetch("https://ai.gateway.lovable.dev/v1/chat/completions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${LOVABLE_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "google/gemini-3-flash-preview",
        messages: [{ role: "system", content: SYSTEM_PROMPT }, ...messages],
        stream: true,
      }),
    });

    if (!response.ok || !response.body) {
      const status = response.status;
      if (status === 429) return res.status(429).json({ error: "Rate limited" });
      if (status === 402) return res.status(402).json({ error: "Payment required" });
      return res.status(500).json({ error: "AI gateway error" });
    }

    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");

    const reader = (response.body as any).getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      res.write(decoder.decode(value, { stream: true }));
    }
    res.end();
  } catch (e: any) {
    console.error("chat error:", e);
    if (!res.headersSent) {
      res.status(500).json({ error: e.message || "Unknown error" });
    }
  }
});

// ─── Start ────────────────────────────────────────────────────

app.listen(PORT, () => {
  console.log(`✅ Local API server running at http://localhost:${PORT}`);
  console.log(`   DB_TYPE: ${process.env.DB_TYPE || "sqlserver"}`);
  console.log(`   DB_HOST: ${process.env.DB_HOST || "(not set)"}`);
});
