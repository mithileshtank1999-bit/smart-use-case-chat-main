import { useEffect, useState } from "react";
import { apiCall } from "@/lib/apiClient";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle, Building2, CircleAlert, DollarSign, FolderKanban, Gauge, Users } from "lucide-react";

interface OrgSummary {
  headcount: number;
  portfolio_count: number;
  total_projects: number;
  active_projects: number;
  escalated_projects: number;
  billable_projects: number;
  client_count: number;
  contract_count: number;
  contract_value?: number | null;
  hours_last_90d: number;
  financials: {
    total_service_value?: number | null;
    total_recognized?: number | null;
    total_invoiced?: number | null;
    total_unbilled?: number | null;
    total_advance?: number | null;
  };
}

interface PortfolioHealthRow {
  portfolio_id: string;
  portfolio_name: string;
  total: number;
  active: number;
  escalated: number;
  closed: number;
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
      <div className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
        <Skeleton className="h-64 rounded-3xl" />
        <Skeleton className="h-64 rounded-3xl" />
      </div>
    </div>
  );
}

export function OrgSummaryPanel() {
  const [summary, setSummary] = useState<OrgSummary | null>(null);
  const [portfolioHealth, setPortfolioHealth] = useState<PortfolioHealthRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      apiCall("org/summary", undefined, { method: "GET" }),
      apiCall("org/portfolio-health", undefined, { method: "GET" }),
    ]).then(([summaryRes, healthRes]) => {
      if (summaryRes.error) {
        setError(summaryRes.error.message || "Failed to load org summary.");
      } else {
        const s = summaryRes.data?.summary;
        if (s && typeof s.headcount === "number") {
          setSummary(s as OrgSummary);
        } else if (s?.error) {
          setError(String(s.error));
        } else {
          setError("No organisation data returned.");
        }
      }
      if (!healthRes.error && Array.isArray(healthRes.data?.results)) {
        setPortfolioHealth(healthRes.data.results as PortfolioHealthRow[]);
      }
      setLoading(false);
    });
  }, []);

  if (loading) return <LoadingSkeleton />;

  if (error || !summary) {
    return (
      <Card className="rounded-3xl border-rose-200 bg-rose-50/80">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-rose-700">
            <CircleAlert className="h-5 w-5" /> Organisation data unavailable
          </CardTitle>
          <CardDescription className="text-rose-600">{error || "No data returned."}</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const f = summary.financials;

  return (
    <div className="space-y-5">
      {/* Header */}
      <Card className="overflow-hidden rounded-3xl border-0 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-800 text-white shadow-xl">
        <CardHeader className="p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-2">
              <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs font-medium uppercase tracking-[0.18em] text-white/80">
                <Building2 className="h-3.5 w-3.5" />
                Organisation Overview
              </div>
              <CardTitle className="text-3xl font-semibold tracking-tight text-white">BUSINESSNEXT</CardTitle>
              <p className="text-sm text-slate-300">Enterprise-wide intelligence snapshot</p>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm text-slate-200">
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">Employees</div>
                <div className="text-lg font-semibold">{summary.headcount.toLocaleString()}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">Portfolios</div>
                <div className="text-lg font-semibold">{summary.portfolio_count}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">Clients</div>
                <div className="text-lg font-semibold">{summary.client_count.toLocaleString()}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">Contracts</div>
                <div className="text-lg font-semibold">{summary.contract_count.toLocaleString()}</div>
              </div>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Badge className="border border-white/20 bg-white/10 text-white">
              {summary.total_projects.toLocaleString()} Total Projects
            </Badge>
            <Badge className="border border-emerald-300/30 bg-emerald-400/20 text-emerald-200">
              {summary.active_projects} Active
            </Badge>
            {summary.escalated_projects > 0 && (
              <Badge className="border border-rose-300/30 bg-rose-400/20 text-rose-200">
                ⚠️ {summary.escalated_projects} Escalated
              </Badge>
            )}
            <Badge className="border border-blue-300/30 bg-blue-400/20 text-blue-200">
              {summary.billable_projects} Billable
            </Badge>
          </div>
        </CardHeader>
      </Card>

      {/* KPI strip */}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Metric icon={Users} label="Headcount" value={summary.headcount.toLocaleString()} />
        <Metric icon={Gauge} label="Hours (last 90d)" value={summary.hours_last_90d.toLocaleString()} />
        <Metric icon={DollarSign} label="Service Value" value={fmt(f.total_service_value)} />
        <Metric icon={DollarSign} label="Unbilled" value={fmt(f.total_unbilled)} />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
        {/* Revenue pipeline */}
        <Card className="rounded-3xl shadow-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <DollarSign className="h-5 w-5 text-primary" />
              Revenue Pipeline
            </CardTitle>
            <CardDescription>Financial rollup across all projects organisation-wide.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            <Metric icon={DollarSign} label="Service Value" value={fmt(f.total_service_value)} />
            <Metric icon={DollarSign} label="Revenue Recognised" value={fmt(f.total_recognized)} />
            <Metric icon={DollarSign} label="Cumulative Invoiced" value={fmt(f.total_invoiced)} />
            <Metric icon={DollarSign} label="Unbilled" value={fmt(f.total_unbilled)} />
            <Metric icon={DollarSign} label="Advance" value={fmt(f.total_advance)} />
            {summary.contract_value != null && (
              <Metric icon={DollarSign} label="Contract Value" value={fmt(summary.contract_value)} />
            )}
          </CardContent>
        </Card>

        {/* Portfolio health grid */}
        <Card className="rounded-3xl shadow-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <FolderKanban className="h-5 w-5 text-primary" />
              Portfolio Health Grid
            </CardTitle>
            <CardDescription>Project counts per portfolio (active / escalated).</CardDescription>
          </CardHeader>
          <CardContent>
            {portfolioHealth.length === 0 ? (
              <p className="text-sm text-muted-foreground">No portfolio data.</p>
            ) : (
              <div className="max-h-72 space-y-2 overflow-y-auto">
                {portfolioHealth.map((row) => (
                  <div key={row.portfolio_id} className="flex items-center justify-between rounded-xl border bg-muted/30 px-3 py-2 text-sm">
                    <span className="max-w-[180px] truncate font-medium text-foreground" title={row.portfolio_name}>
                      {row.portfolio_name}
                    </span>
                    <div className="flex shrink-0 items-center gap-2">
                      <span className="text-xs text-muted-foreground">{row.total} total</span>
                      <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700 text-xs">{row.active}</Badge>
                      {row.escalated > 0 && (
                        <Badge className="border-rose-200 bg-rose-50 text-rose-700 text-xs">⚠️ {row.escalated}</Badge>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Project overview */}
      <Card className="rounded-3xl shadow-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <AlertTriangle className="h-5 w-5 text-primary" />
            Project Overview
          </CardTitle>
          <CardDescription>Organisation-wide project status summary.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Metric icon={FolderKanban} label="Total Projects" value={summary.total_projects.toLocaleString()} />
            <Metric icon={FolderKanban} label="Active" value={summary.active_projects} />
            <Metric icon={AlertTriangle} label="Escalated" value={summary.escalated_projects} />
            <Metric icon={FolderKanban} label="Billable" value={summary.billable_projects} />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
