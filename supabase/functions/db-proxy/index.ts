import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.49.1";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type, x-supabase-client-platform, x-supabase-client-platform-version, x-supabase-client-runtime, x-supabase-client-runtime-version",
};

async function getActiveConnection(supabase: any) {
  const { data, error } = await supabase
    .from("db_connections")
    .select("*")
    .eq("is_active", true)
    .limit(1)
    .single();
  if (error || !data) return null;
  return data;
}

async function connectAndQuerySqlServer(conn: any, sql: string, params: any[] = []) {
  const mssql = await import("npm:mssql@11.0.1");

  const config = {
    user: conn.username,
    password: conn.encrypted_password,
    server: conn.host,
    port: conn.port,
    database: conn.database_name,
    options: {
      encrypt: true,
      trustServerCertificate: true,
    },
    connectionTimeout: 10000,
    requestTimeout: 15000,
  };

  const pool = await mssql.default.connect(config);
  try {
    const request = pool.request();
    params.forEach((p, i) => {
      request.input(`p${i}`, p);
    });
    const result = await request.query(sql);
    return result.recordset;
  } finally {
    await pool.close();
  }
}

async function connectAndQueryPostgres(conn: any, sql: string, params: any[] = []) {
  const pg = await import("npm:pg@8.13.1");

  const client = new pg.default.Client({
    host: conn.host,
    port: conn.port,
    database: conn.database_name,
    user: conn.username,
    password: conn.encrypted_password,
    ssl: { rejectUnauthorized: false },
    connectionTimeoutMillis: 10000,
  });

  await client.connect();
  try {
    // Convert @p0, @p1 style params to $1, $2 for pg
    const pgSql = sql.replace(/@p(\d+)/g, (_, n) => `$${parseInt(n) + 1}`);
    const result = await client.query(pgSql, params);
    return result.rows;
  } finally {
    await client.end();
  }
}

async function connectAndQuery(conn: any, sql: string, params: any[] = []) {
  if (conn.db_type === "postgres") {
    return connectAndQueryPostgres(conn, sql, params);
  }
  return connectAndQuerySqlServer(conn, sql, params);
}

serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders });

  try {
    const { query_type, filters } = await req.json();

    if (!query_type || typeof query_type !== "string") {
      return new Response(JSON.stringify({ error: "query_type is required" }), {
        status: 400,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const supabaseKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const supabase = createClient(supabaseUrl, supabaseKey);

    const conn = await getActiveConnection(supabase);
    if (!conn) {
      return new Response(JSON.stringify({ error: "no_connection", message: "No active database connection configured" }), {
        status: 200,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    let results: any[];

    switch (query_type) {
      case "test_connection": {
        await connectAndQuery(conn, "SELECT 1 AS test");
        return new Response(JSON.stringify({ success: true, message: "Connection successful" }), {
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
      }

      case "list_projects": {
        results = await connectAndQuery(
          conn,
          "SELECT project_id, project_name FROM projects ORDER BY project_name"
        );
        break;
      }

      case "search_projects": {
        let sql = "SELECT * FROM projects WHERE 1=1";
        const params: any[] = [];
        let paramIndex = 0;

        if (filters?.project_id) {
          sql += ` AND project_id = @p${paramIndex}`;
          params.push(filters.project_id);
          paramIndex++;
        }
        if (filters?.project_name) {
          sql += ` AND project_name LIKE @p${paramIndex}`;
          params.push(`%${filters.project_name}%`);
          paramIndex++;
        }
        if (filters?.account_name) {
          sql += ` AND account_name LIKE @p${paramIndex}`;
          params.push(`%${filters.account_name}%`);
          paramIndex++;
        }
        if (filters?.account_id) {
          sql += ` AND account_id = @p${paramIndex}`;
          params.push(filters.account_id);
          paramIndex++;
        }
        if (filters?.portfolio_name) {
          sql += ` AND portfolio_name LIKE @p${paramIndex}`;
          params.push(`%${filters.portfolio_name}%`);
          paramIndex++;
        }
        if (filters?.status) {
          sql += ` AND status LIKE @p${paramIndex}`;
          params.push(`%${filters.status}%`);
          paramIndex++;
        }
        if (filters?.project_manager) {
          sql += ` AND project_manager LIKE @p${paramIndex}`;
          params.push(`%${filters.project_manager}%`);
          paramIndex++;
        }

        sql += " ORDER BY project_id";
        results = await connectAndQuery(conn, sql, params);
        break;
      }

      default:
        return new Response(JSON.stringify({ error: `Unknown query_type: ${query_type}` }), {
          status: 400,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
    }

    return new Response(JSON.stringify({ results: results || [] }), {
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (e) {
    console.error("db-proxy error:", e);
    return new Response(JSON.stringify({ error: e instanceof Error ? e.message : "Unknown error" }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
