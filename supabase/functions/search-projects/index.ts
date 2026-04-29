import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.49.1";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type, x-supabase-client-platform, x-supabase-client-platform-version, x-supabase-client-runtime, x-supabase-client-runtime-version",
};

serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders });

  try {
    const { filters } = await req.json();
    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const supabaseKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const supabase = createClient(supabaseUrl, supabaseKey);

    let query = supabase.from("projects").select("*");

    if (filters) {
      if (filters.project_id) {
        query = query.eq("project_id", filters.project_id);
      }
      if (filters.project_name) {
        query = query.ilike("project_name", `%${filters.project_name}%`);
      }
      if (filters.account_name) {
        query = query.ilike("account_name", `%${filters.account_name}%`);
      }
      if (filters.account_id) {
        query = query.eq("account_id", filters.account_id);
      }
      if (filters.portfolio_name) {
        query = query.ilike("portfolio_name", `%${filters.portfolio_name}%`);
      }
      if (filters.status) {
        query = query.ilike("status", `%${filters.status}%`);
      }
      if (filters.project_manager) {
        query = query.ilike("project_manager", `%${filters.project_manager}%`);
      }
    }

    const { data, error } = await query.order("project_id");

    if (error) throw error;

    return new Response(JSON.stringify({ results: data || [] }), {
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (e) {
    console.error("search-projects error:", e);
    return new Response(JSON.stringify({ error: e instanceof Error ? e.message : "Unknown error" }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
