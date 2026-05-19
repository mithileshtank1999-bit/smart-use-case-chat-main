import { useEffect, useState } from "react";
import { apiCall } from "@/lib/apiClient";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle, BriefcaseBusiness, CircleAlert, DollarSign, FolderKanban, Gauge, Users } from "lucide-react";

interface PortfolioData {
  portfolio_id: string;
  portfolio_name: string;
  start_date?: string;
  close_date?: string;
  total_projects: number;
  total_escalated: number;
  total_billable: number;
  project_status_breakdown: Array<{ status: string; count: number; escalated: number; billable: number }>;
  financials: {
    total_service_value?: number | null;
    total_recognized?: number | null;
    total_invoiced?: number | null;
    total_unbilled?: number | null;
    total_advance?: number | null;
  };
  milestone_health: {
    total_modules: number;
    completed_golive: number;
    delayed_modules: number;
  };
  resources: {
    allocated_employees: number;
    total_allocated_hours?: number | null;
    avg_allocation_perc?: number | null;
  };
  case_summary: {
    total_cases: number;
    high_severity: number;
    medium_severity: number;
    low_severity: number;
    total_reopens: number;
  };
  top_projects: Array<{
    project_id: string;
    project_name: string;
    status: string;
    escalated: boolean;
    start_date?: string;
    end_date?: string;
    client?: string;
    pm?: string;
  }>;
}

interface PortfolioSummaryPanelProps {
  portfolioId: string;
  portfolioName?: string;
}

function Metric({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string | number | undefined | null }) {
  return (
    <div className="rounded-xl border bg-background/70 p-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        <Icon className="h-3.5 w-3.5" />
        <span>{label}</span>
      </div>
      <p className="text-sm font-semibold text-foreground">
        {value !== undefined && value !== null ? String(value) : "—"}
      </p>
    </div>
  );
}

function fmt(v?: number | null) {
  if (v === undefined || v === null) return "—";
  return v.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-44 rounded-3xl" />
      <div className="grid gap-4 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-2xl" />)}
      </div>
      <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        <Skeleton className="h-64 rounded-3xl" />
        <div className="space-y-4">
          <Skeleton className="h-36 rounded-3xl" />
          <Skeleton className="h-36 rounded-3xl" />
        </div>
      </div>
    </div>
  );
}

export function PortfolioSummaryPanel({ portfolioId, portfolioName }: PortfolioSummaryPanelProps) {
  const [data, setData] = useState<PortfolioData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setData(null);
    setError(null);
    apiCall(`portfolios/${portfolioId}/summary`, undefined, { method: "GET" }).then(({ data: res, error: err }) => {
      if (err) {
        setError(err.message || "Failed to load portfolio summary.");
      } else if (res?.summary) {
        setData(res.summary as PortfolioData);
      } else {
        setError("Portfolio not found.");
      }
      setLoading(false);
    });
  }, [portfolioId]);

  if (loading) return <LoadingSkeleton />;

  if (error) {
    return (
      <Card className="rounded-3xl border-rose-200 bg-rose-50/80">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-rose-700">
            <CircleAlert className="h-5 w-5" /> Portfolio unavailable
          </CardTitle>
          <CardDescription className="text-rose-600">{error}</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  if (!data) return null;

  const f = data.financials;
  const m = data.milestone_health;
  const r = data.resources;
  const c = data.case_summary;

  return (
    <div className="space-y-5">
      {/* Header */}
      <Card className="overflow-hidden rounded-3xl border-0 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-800 text-white shadow-xl">
        <CardHeader className="p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-2">
              <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs font-medium uppercase tracking-[0.18em] text-white/80">
                <BriefcaseBusiness className="h-3.5 w-3.5" />
                Portfolio Summary
              </div>
              <CardTitle className="text-3xl font-semibold tracking-tight text-white">
                {data.portfolio_name || portfolioName}
              </CardTitle>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm text-slate-200">
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">Portfolio ID</div>
                <div className="font-medium">{data.portfolio_id}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">Start Date</div>
                <div className="font-medium">{data.start_date || "—"}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">Close Date</div>
                <div className="font-medium">{data.close_date || "—"}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">Employees</div>
                <div className="font-medium">{r.allocated_employees.toLocaleString()}</div>
              </div>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Badge className="border border-white/20 bg-white/10 text-white">
              {data.total_projects} Projects
            </Badge>
            {data.total_escalated > 0 && (
              <Badge className="border border-rose-300/30 bg-rose-400/20 text-rose-200">
                ⚠️ {data.total_escalated} Escalated
              </Badge>
            )}
            <Badge className="border border-emerald-300/30 bg-emerald-400/20 text-emerald-200">
              {data.total_billable} Billable
            </Badge>
            <Badge className="border border-blue-300/30 bg-blue-400/20 text-blue-200">
              {m.total_modules} Modules
            </Badge>
          </div>
        </CardHeader>
      </Card>

      {/* KPI strip */}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Metric icon={Gauge} label="Go-lives Completed" value={m.completed_golive} />
        <Metric icon={AlertTriangle} label="Delayed Modules" value={m.delayed_modules} />
        <Metric icon={Users} label="Allocated Employees" value={r.allocated_employees} />
        <Metric icon={AlertTriangle} label="Total Defects" value={c.total_cases} />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        {/* Financial rollup */}
        <Card className="rounded-3xl shadow-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <DollarSign className="h-5 w-5 text-primary" />
              Revenue Pipeline
            </CardTitle>
            <CardDescription>Financial rollup across all projects in this portfolio.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            <Metric icon={DollarSign} label="Service Value" value={fmt(f.total_service_value)} />
            <Metric icon={DollarSign} label="Revenue Recognised" value={fmt(f.total_recognized)} />
            <Metric icon={DollarSign} label="Cumulative Invoiced" value={fmt(f.total_invoiced)} />
            <Metric icon={DollarSign} label="Unbilled" value={fmt(f.total_unbilled)} />
            <Metric icon={DollarSign} label="Advance" value={fmt(f.total_advance)} />
            <Metric
              icon={Users}
              label="Avg Allocation %"
              value={r.avg_allocation_perc != null ? `${Number(r.avg_allocation_perc).toFixed(1)}%` : "—"}
            />
          </CardContent>
        </Card>

        <div className="space-y-4">
          {/* Defect summary */}
          <Card className="rounded-3xl shadow-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <AlertTriangle className="h-5 w-5 text-primary" />
                Defect Summary
              </CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">
              <Metric icon={AlertTriangle} label="Total Cases" value={c.total_cases} />
              <Metric icon={AlertTriangle} label="High Severity" value={c.high_severity} />
              <Metric icon={AlertTriangle} label="Medium Severity" value={c.medium_severity} />
              <Metric icon={AlertTriangle} label="Reopens" value={c.total_reopens} />
            </CardContent>
          </Card>

          {/* Project status breakdown */}
          <Card className="rounded-3xl shadow-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <FolderKanban className="h-5 w-5 text-primary" />
                Project Status
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {data.project_status_breakdown.map((row) => (
                  <div key={row.status} className="flex items-center justify-between rounded-xl border bg-muted/30 px-3 py-2 text-sm">
                    <span className="font-medium text-foreground capitalize">{row.status || "Unknown"}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-muted-foreground">{row.count}</span>
                      {row.escalated > 0 && (
                        <Badge className="border-rose-200 bg-rose-50 text-rose-700 text-xs">⚠️ {row.escalated}</Badge>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Top projects */}
      {data.top_projects.length > 0 && (
        <Card className="rounded-3xl shadow-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <FolderKanban className="h-5 w-5 text-primary" />
              Projects in Portfolio
            </CardTitle>
            <CardDescription>Up to 15 most recently updated projects.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="pb-2 pr-4 text-left font-medium">Project</th>
                    <th className="pb-2 pr-4 text-left font-medium">Status</th>
                    <th className="pb-2 pr-4 text-left font-medium">PM</th>
                    <th className="pb-2 text-left font-medium">Client</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {data.top_projects.map((proj) => (
                    <tr key={proj.project_id} className="hover:bg-muted/30">
                      <td className="py-2 pr-4 font-medium text-foreground">
                        {proj.project_name}
                        {proj.escalated && <span className="ml-1 text-rose-500">⚠️</span>}
                      </td>
                      <td className="py-2 pr-4 text-muted-foreground capitalize">{proj.status || "—"}</td>
                      <td className="py-2 pr-4 text-muted-foreground">{proj.pm || "—"}</td>
                      <td className="py-2 text-muted-foreground">{proj.client || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
