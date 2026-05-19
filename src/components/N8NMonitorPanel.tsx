import { useCallback, useEffect, useRef, useState } from "react";
import { apiCall } from "@/lib/apiClient";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  AlertTriangle,
  CheckCircle2,
  CircleAlert,
  Clock,
  RefreshCw,
  Sparkles,
  Wifi,
  WifiOff,
  Zap,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip as RechartTooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import ReactMarkdown from "react-markdown";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface N8nDashboard {
  total_workflows: number;
  active_workflows: number;
  total_runs_24h: number;
  total_errors_24h: number;
  failure_rate_24h: number;
  avg_duration_ms: number;
  hourly_chart: Array<{ hour: string; success: number; error: number }>;
}

interface N8nWorkflow {
  workflow_id: string;
  name: string;
  active: boolean;
  trigger_type: string;
  last_run?: string | null;
  run_count: number;
  failure_count: number;
  avg_duration_ms: number;
}

interface N8nExecution {
  execution_id: string;
  workflow_id: string;
  status: string;
  mode: string;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms: number;
  error_message: string;
}

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function fmtDuration(ms: number): string {
  if (!ms) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function fmtTs(ts?: string | null): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString("en-IN", {
      dateStyle: "short",
      timeStyle: "short",
    });
  } catch {
    return ts;
  }
}

function StatusBadge({ status }: { status: string }) {
  const s = (status || "").toLowerCase();
  if (s === "success")
    return (
      <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700 text-xs gap-1">
        <CheckCircle2 className="h-3 w-3" /> success
      </Badge>
    );
  if (s === "error")
    return (
      <Badge className="border-rose-200 bg-rose-50 text-rose-700 text-xs gap-1">
        <AlertTriangle className="h-3 w-3" /> error
      </Badge>
    );
  if (s === "running")
    return (
      <Badge className="border-blue-200 bg-blue-50 text-blue-700 text-xs gap-1">
        <Clock className="h-3 w-3" /> running
      </Badge>
    );
  return (
    <Badge className="border-slate-200 bg-slate-50 text-slate-600 text-xs">
      {status || "unknown"}
    </Badge>
  );
}

function Metric({
  icon: Icon,
  label,
  value,
  danger,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  danger?: boolean;
}) {
  return (
    <div className="rounded-xl border bg-background/70 p-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        <Icon className="h-3.5 w-3.5" />
        <span>{label}</span>
      </div>
      <p
        className={`text-sm font-semibold ${danger ? "text-rose-600" : "text-foreground"}`}
      >
        {value}
      </p>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-44 rounded-3xl" />
      <div className="grid gap-4 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-2xl" />
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        <Skeleton className="h-72 rounded-3xl" />
        <Skeleton className="h-72 rounded-3xl" />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

export function N8NMonitorPanel() {
  const [dashboard, setDashboard] = useState<N8nDashboard | null>(null);
  const [workflows, setWorkflows] = useState<N8nWorkflow[]>([]);
  const [executions, setExecutions] = useState<N8nExecution[]>([]);
  const [selectedWorkflow, setSelectedWorkflow] = useState<N8nWorkflow | null>(
    null
  );
  const [aiReport, setAiReport] = useState<string | null>(null);

  const [n8nStatus, setN8nStatus] = useState<"checking" | "reachable" | "unreachable" | "not_configured">("checking");
  const [n8nUrl, setN8nUrl] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [execLoading, setExecLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ---------------------------------------------------------------------------
  // Fetch helpers
  // ---------------------------------------------------------------------------

  const fetchDashboardAndWorkflows = useCallback(async () => {
    const [dashRes, wfRes] = await Promise.all([
      apiCall("n8n/dashboard", undefined, { method: "GET" }),
      apiCall("n8n/workflows", undefined, { method: "GET" }),
    ]);

    if (dashRes.error) {
      setError(dashRes.error.message || "Failed to load automation data.");
    } else {
      const d = dashRes.data?.data;
      if (d) setDashboard(d as N8nDashboard);
    }

    if (!wfRes.error && Array.isArray(wfRes.data?.data)) {
      setWorkflows(wfRes.data.data as N8nWorkflow[]);
    }
  }, []);

  const fetchExecutions = useCallback(async (workflowId: string) => {
    setExecLoading(true);
    const { data, error: err } = await apiCall("n8n/executions", undefined, {
      method: "GET",
      query: { workflow_id: workflowId, limit: "30" },
    });
    setExecLoading(false);
    if (!err && Array.isArray(data?.data)) {
      setExecutions(data.data as N8nExecution[]);
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Lifecycle
  // ---------------------------------------------------------------------------

  useEffect(() => {
    // Check n8n connectivity first
    apiCall("n8n/health", undefined, { method: "GET" }).then(({ data }) => {
      const status = data?.status ?? "unreachable";
      setN8nStatus(status);
      setN8nUrl(data?.n8n_url ?? null);
    });

    setLoading(true);
    fetchDashboardAndWorkflows().finally(() => setLoading(false));

    intervalRef.current = setInterval(fetchDashboardAndWorkflows, 20_000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchDashboardAndWorkflows]);

  const handleSelectWorkflow = (wf: N8nWorkflow) => {
    setSelectedWorkflow(wf);
    setExecutions([]);
    fetchExecutions(wf.workflow_id);
  };

  const handleSync = async () => {
    setSyncing(true);
    await apiCall("n8n/sync", undefined, { method: "POST" });
    await fetchDashboardAndWorkflows();
    setSyncing(false);
  };

  const handleGenerateReport = async () => {
    setReportLoading(true);
    const { data } = await apiCall("n8n/report", undefined, {
      method: "GET",
      query: { days: "1" },
    });
    setReportLoading(false);
    if (data?.report) setAiReport(data.report as string);
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (loading) return <LoadingSkeleton />;

  if (error) {
    return (
      <Card className="rounded-3xl border-rose-200 bg-rose-50/80">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-rose-700">
            <CircleAlert className="h-5 w-5" /> Automation data unavailable
          </CardTitle>
          <CardDescription className="text-rose-600">{error}</CardDescription>
          <CardDescription className="text-rose-500 text-xs mt-1">
            Ensure N8N_BASE_URL and N8N_API_KEY are set in .env, then run{" "}
            <code>POST /api/n8n/sync</code> once.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const d = dashboard;

  // Hourly chart — label to HH:MM
  const chartData = (d?.hourly_chart ?? []).map((r) => ({
    ...r,
    hour: r.hour ? new Date(r.hour).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false }) : "",
  }));

  return (
    <div className="space-y-5">
      {/* ---- Header ---- */}
      <Card className="overflow-hidden rounded-3xl border-0 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-800 text-white shadow-xl">
        <CardHeader className="p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-2">
              <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs font-medium uppercase tracking-[0.18em] text-white/80">
                <Zap className="h-3.5 w-3.5" />
                Automation Monitor
              </div>
              <CardTitle className="text-3xl font-semibold tracking-tight text-white">
                n8n Workflows
              </CardTitle>
              <p className="text-sm text-slate-300">
                Live execution tracking &amp; AI-powered reporting
              </p>
            </div>
            <div className="flex flex-col gap-2 items-end">
              {/* n8n connection status pill */}
              {n8nStatus === "checking" && (
                <div className="flex items-center gap-1.5 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs text-white/70">
                  <RefreshCw className="h-3 w-3 animate-spin" /> Checking n8n…
                </div>
              )}
              {n8nStatus === "reachable" && (
                <div className="flex items-center gap-1.5 rounded-full border border-emerald-400/30 bg-emerald-400/15 px-3 py-1 text-xs text-emerald-300">
                  <Wifi className="h-3 w-3" /> Connected{n8nUrl ? ` · ${n8nUrl}` : ""}
                </div>
              )}
              {(n8nStatus === "unreachable" || n8nStatus === "not_configured") && (
                <div className="flex items-center gap-1.5 rounded-full border border-rose-400/30 bg-rose-400/15 px-3 py-1 text-xs text-rose-300">
                  <WifiOff className="h-3 w-3" />
                  {n8nStatus === "not_configured" ? "n8n not configured" : `Unreachable · ${n8nUrl ?? "check N8N_BASE_URL"}`}
                </div>
              )}
              <Button
                size="sm"
                variant="outline"
                className="border-white/20 bg-white/10 text-white hover:bg-white/20"
                onClick={handleSync}
                disabled={syncing || n8nStatus !== "reachable"}
              >
                <RefreshCw
                  className={`h-3.5 w-3.5 mr-1.5 ${syncing ? "animate-spin" : ""}`}
                />
                {syncing ? "Syncing…" : "Sync from n8n"}
              </Button>
              <p className="text-xs text-slate-400">Auto-refreshes every 20s</p>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Badge className="border border-white/20 bg-white/10 text-white">
              {d?.total_workflows ?? 0} Workflows
            </Badge>
            <Badge className="border border-emerald-300/30 bg-emerald-400/20 text-emerald-200">
              {d?.active_workflows ?? 0} Active
            </Badge>
            <Badge className="border border-blue-300/30 bg-blue-400/20 text-blue-200">
              {d?.total_runs_24h ?? 0} Runs (24h)
            </Badge>
            {(d?.total_errors_24h ?? 0) > 0 && (
              <Badge className="border border-rose-300/30 bg-rose-400/20 text-rose-200">
                ⚠️ {d?.total_errors_24h} Failures (24h)
              </Badge>
            )}
          </div>
        </CardHeader>
      </Card>

      {/* ---- KPI strip ---- */}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Metric icon={Zap} label="24h Runs" value={d?.total_runs_24h ?? 0} />
        <Metric
          icon={AlertTriangle}
          label="24h Failures"
          value={d?.total_errors_24h ?? 0}
          danger={(d?.total_errors_24h ?? 0) > 0}
        />
        <Metric
          icon={AlertTriangle}
          label="Failure Rate"
          value={`${d?.failure_rate_24h ?? 0}%`}
          danger={(d?.failure_rate_24h ?? 0) > 20}
        />
        <Metric
          icon={Clock}
          label="Avg Duration"
          value={fmtDuration(d?.avg_duration_ms ?? 0)}
        />
      </div>

      {/* ---- Workflow list + Chart ---- */}
      <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        {/* Workflow list */}
        <Card className="rounded-3xl shadow-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Zap className="h-5 w-5 text-primary" />
              Workflows
            </CardTitle>
            <CardDescription>
              Click a row to view execution history.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {workflows.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No workflows synced yet. Click "Sync from n8n" above.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-xs uppercase tracking-wide text-muted-foreground">
                      <th className="pb-2 pr-4 text-left font-medium">Name</th>
                      <th className="pb-2 pr-4 text-left font-medium">Status</th>
                      <th className="pb-2 pr-4 text-left font-medium">Runs</th>
                      <th className="pb-2 pr-4 text-left font-medium">Fails</th>
                      <th className="pb-2 text-left font-medium">Last Run</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {workflows.map((wf) => (
                      <tr
                        key={wf.workflow_id}
                        className={`cursor-pointer hover:bg-muted/40 transition-colors ${
                          selectedWorkflow?.workflow_id === wf.workflow_id
                            ? "bg-muted/60"
                            : ""
                        }`}
                        onClick={() => handleSelectWorkflow(wf)}
                      >
                        <td className="py-2 pr-4 font-medium text-foreground max-w-[160px] truncate">
                          {wf.name}
                        </td>
                        <td className="py-2 pr-4">
                          {wf.active ? (
                            <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700 text-xs">
                              active
                            </Badge>
                          ) : (
                            <Badge className="border-slate-200 bg-slate-50 text-slate-500 text-xs">
                              inactive
                            </Badge>
                          )}
                        </td>
                        <td className="py-2 pr-4 text-muted-foreground">
                          {wf.run_count}
                        </td>
                        <td className="py-2 pr-4">
                          {wf.failure_count > 0 ? (
                            <span className="text-rose-600 font-medium">
                              {wf.failure_count}
                            </span>
                          ) : (
                            <span className="text-muted-foreground">0</span>
                          )}
                        </td>
                        <td className="py-2 text-muted-foreground text-xs">
                          {fmtTs(wf.last_run)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Execution trend chart */}
        <Card className="rounded-3xl shadow-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <CheckCircle2 className="h-5 w-5 text-primary" />
              Execution Trend (24h)
            </CardTitle>
            <CardDescription>
              Hourly success vs failure breakdown.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {chartData.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No execution data in the last 24 hours.
              </p>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: -16 }}>
                  <XAxis
                    dataKey="hour"
                    tick={{ fontSize: 10 }}
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis
                    allowDecimals={false}
                    tick={{ fontSize: 10 }}
                    tickLine={false}
                    axisLine={false}
                  />
                  <RechartTooltip
                    contentStyle={{ fontSize: 12, borderRadius: 8 }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar
                    dataKey="success"
                    stackId="a"
                    fill="#10b981"
                    radius={[0, 0, 0, 0]}
                    name="Success"
                  />
                  <Bar
                    dataKey="error"
                    stackId="a"
                    fill="#f43f5e"
                    radius={[4, 4, 0, 0]}
                    name="Error"
                  />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ---- Execution history (when workflow selected) ---- */}
      {selectedWorkflow && (
        <Card className="rounded-3xl shadow-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Clock className="h-5 w-5 text-primary" />
              Executions — {selectedWorkflow.name}
            </CardTitle>
            <CardDescription>Last 30 executions for this workflow.</CardDescription>
          </CardHeader>
          <CardContent>
            {execLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 rounded-xl" />
                ))}
              </div>
            ) : executions.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No executions found for this workflow.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-xs uppercase tracking-wide text-muted-foreground">
                      <th className="pb-2 pr-4 text-left font-medium">ID</th>
                      <th className="pb-2 pr-4 text-left font-medium">Status</th>
                      <th className="pb-2 pr-4 text-left font-medium">Mode</th>
                      <th className="pb-2 pr-4 text-left font-medium">Started</th>
                      <th className="pb-2 pr-4 text-left font-medium">Duration</th>
                      <th className="pb-2 text-left font-medium">Error</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {executions.map((ex) => (
                      <tr key={ex.execution_id} className="hover:bg-muted/30">
                        <td className="py-2 pr-4 font-mono text-xs text-muted-foreground">
                          {ex.execution_id.slice(-8)}
                        </td>
                        <td className="py-2 pr-4">
                          <StatusBadge status={ex.status} />
                        </td>
                        <td className="py-2 pr-4 text-muted-foreground capitalize">
                          {ex.mode || "—"}
                        </td>
                        <td className="py-2 pr-4 text-muted-foreground text-xs">
                          {fmtTs(ex.started_at)}
                        </td>
                        <td className="py-2 pr-4 text-muted-foreground">
                          {fmtDuration(ex.duration_ms)}
                        </td>
                        <td className="py-2 text-rose-600 text-xs max-w-[200px] truncate">
                          {ex.error_message || "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ---- AI Report ---- */}
      <Card className="rounded-3xl shadow-sm">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Sparkles className="h-5 w-5 text-primary" />
              AI Automation Report
            </CardTitle>
            <Button
              size="sm"
              onClick={handleGenerateReport}
              disabled={reportLoading}
            >
              {reportLoading ? (
                <>
                  <RefreshCw className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                  Generating…
                </>
              ) : (
                <>
                  <Sparkles className="h-3.5 w-3.5 mr-1.5" />
                  Generate Report
                </>
              )}
            </Button>
          </div>
          <CardDescription>
            AI-generated daily automation health summary using your execution data.
          </CardDescription>
        </CardHeader>
        {aiReport && (
          <CardContent>
            <div className="prose prose-sm max-w-none rounded-2xl border bg-muted/30 p-4 text-sm">
              <ReactMarkdown>{aiReport}</ReactMarkdown>
            </div>
          </CardContent>
        )}
      </Card>
    </div>
  );
}
