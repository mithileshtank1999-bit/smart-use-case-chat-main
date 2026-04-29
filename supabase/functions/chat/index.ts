import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type, x-supabase-client-platform, x-supabase-client-platform-version, x-supabase-client-runtime, x-supabase-client-runtime-version",
};

serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders });

  try {
    const { messages } = await req.json();
    const LOVABLE_API_KEY = Deno.env.get("LOVABLE_API_KEY");
    if (!LOVABLE_API_KEY) throw new Error("LOVABLE_API_KEY is not configured");

    const response = await fetch("https://ai.gateway.lovable.dev/v1/chat/completions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${LOVABLE_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "google/gemini-3-flash-preview",
        messages: [
          {
            role: "system",
            content: `You are a Project Intelligence Assistant (Agent PMP). You operate using a two-stage prompt architecture:

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
Project Planning Intelligence, Timesheet Management, Defect & Case Management, Test Cases Management, Intelligent Document Management, Report Automation, AI Meeting Summary, Smart Issue/Risk Analysis, Resource Allocation & Optimization`,
          },
          ...messages,
        ],
        stream: true,
      }),
    });

    if (!response.ok) {
      if (response.status === 429) {
        return new Response(JSON.stringify({ error: "Rate limits exceeded, please try again later." }), {
          status: 429,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
      }
      if (response.status === 402) {
        return new Response(JSON.stringify({ error: "Payment required, please add funds to your Lovable AI workspace." }), {
          status: 402,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
      }
      const t = await response.text();
      console.error("AI gateway error:", response.status, t);
      return new Response(JSON.stringify({ error: "AI gateway error" }), {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    return new Response(response.body, {
      headers: { ...corsHeaders, "Content-Type": "text/event-stream" },
    });
  } catch (e) {
    console.error("chat error:", e);
    return new Response(JSON.stringify({ error: e instanceof Error ? e.message : "Unknown error" }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
