import { AlertTriangle, CalendarDays, CircleAlert, CircleCheckBig, CircleDashed, DollarSign, FolderKanban, Gauge, ShieldAlert, Target, Users } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export interface ExecutiveProjectSummary {
  overview?: {
    project_name?: string;
    project_id?: string;
    status?: string;
    completion?: string;
    billing_model?: string;
    modules_delivered?: string;
    objective?: string;
    portfolio?: string;
    portfolio_owner?: string;
    customer_name?: string;
    contract_id?: string;
    contract_title?: string;
    project_currency?: string;
    billable?: string;
    assign_to?: string;
  };
  health?: {
    overall?: string;
    schedule?: string;
    financial?: string;
    delivery?: string;
    risk?: string;
  };
  timeline?: {
    start_date?: string;
    dev_start_date?: string;
    dev_end_date?: string;
    sit_start_date?: string;
    sit_end_date?: string;
    uat_start_date?: string;
    uat_end_date?: string;
    go_live_date?: string;
    fsd_sign_off?: string;
    actual_effort?: string;
  };
  governance?: {
    summary?: string;
    project_manager?: string;
    hod?: string;
    svp?: string;
    portfolio_owner?: string;
    action_owner?: string;
  };
  financial?: {
    project_service_value?: string;
    revenue_recognized?: string;
    cumulative_invoice?: string;
    advance?: string;
    revenue_available?: string;
    left_over?: string;
  };
  risks?: {
    risk_statement?: string;
    severity?: string;
    impact?: string;
    aging?: string;
    pending?: string;
  };
  highlights?: {
    summary?: string;
    key_win?: string;
    module?: string;
  };
  milestones?: Array<{
    label: string;
    date: string;
    status?: string;
  }>;
  key_information?: {
    active?: string;
    monitor_project?: string;
    troubled?: string;
    percent_completion?: string;
    days_elapsed?: string;
    days_to_go_live?: string;
    expected_uat_completion?: string;
    uat_release?: string;
    revenue_area?: string;
    revenue_type?: string;
    product_focus?: string;
    delivery_rag?: string;
    product_rag?: string;
    revenue_risk?: string;
    forecasted_project_hours?: string;
    budgeted_project_hours?: string;
    efforts_remaining?: string;
    budgeted_man_months?: string;
    start_date_history?: string;
    sit_date_history?: string;
    uat_date_history?: string;
    uat_release_date_history?: string;
    go_live_date_history?: string;
    project_criticality?: string;
    sa_spoc?: string;
    sdg_spoc?: string;
    product_spoc?: string;
    pipeline_remarks?: string;
    lowlights?: string;
    financial_documents?: string;
    comments?: string;
    reopened_cases?: string;
    untouched_cases?: string;
    total_cases?: string;
    untouched_requirements?: string;
    total_requirements?: string;
  };
}

interface ExecutiveSummaryPanelProps {
  projectName?: string;
  summary: ExecutiveProjectSummary | null;
  loading?: boolean;
  error?: string | null;
  onFillTimesheet?: () => void;
  fillingTimesheet?: boolean;
}

function summaryValue(value?: string | null) {
  return value && value.trim() ? value : "Not available";
}

function badgeTone(value?: string | null) {
  const normalizedValue = value?.toLowerCase() ?? "";
  if (normalizedValue.includes("healthy") || normalizedValue.includes("on track") || normalizedValue.includes("completed") || normalizedValue.includes("green")) {
    return "bg-emerald-500/10 text-emerald-700 border-emerald-200";
  }
  if (normalizedValue.includes("moderate") || normalizedValue.includes("yellow") || normalizedValue.includes("attention")) {
    return "bg-amber-500/10 text-amber-700 border-amber-200";
  }
  if (normalizedValue.includes("high") || normalizedValue.includes("delayed") || normalizedValue.includes("red") || normalizedValue.includes("critical")) {
    return "bg-rose-500/10 text-rose-700 border-rose-200";
  }
  return "bg-slate-500/10 text-slate-700 border-slate-200";
}

function SummaryMetric({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Gauge;
  label: string;
  value?: string;
}) {
  return (
    <div className="rounded-xl border bg-background/70 p-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        <Icon className="h-3.5 w-3.5" />
        <span>{label}</span>
      </div>
      <p className="text-sm font-semibold text-foreground">{summaryValue(value)}</p>
    </div>
  );
}

function LoadingPanel() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-32 rounded-3xl" />
      <div className="grid gap-4 lg:grid-cols-4">
        <Skeleton className="h-28 rounded-2xl" />
        <Skeleton className="h-28 rounded-2xl" />
        <Skeleton className="h-28 rounded-2xl" />
        <Skeleton className="h-28 rounded-2xl" />
      </div>
      <div className="grid gap-4 xl:grid-cols-[1.35fr_0.9fr]">
        <Skeleton className="h-80 rounded-3xl" />
        <Skeleton className="h-80 rounded-3xl" />
      </div>
    </div>
  );
}

export function ExecutiveSummaryPanel({
  projectName,
  summary,
  loading,
  error,
  onFillTimesheet,
  fillingTimesheet,
}: ExecutiveSummaryPanelProps) {
  if (loading) {
    return <LoadingPanel />;
  }

  if (error) {
    return (
      <Card className="rounded-3xl border-rose-200 bg-rose-50/80 shadow-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-rose-700">
            <CircleAlert className="h-5 w-5" />
            Summary unavailable
          </CardTitle>
          <CardDescription className="text-rose-600">{error}</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  if (!summary) {
    return null;
  }

  const overview = summary.overview ?? {};
  const health = summary.health ?? {};
  const timeline = summary.timeline ?? {};
  const governance = summary.governance ?? {};
  const financial = summary.financial ?? {};
  const keyInfo = summary.key_information ?? {};
  const risks = summary.risks ?? {};
  const highlights = summary.highlights ?? {};
  const milestones = summary.milestones ?? [];
  const governanceSummary = "summary" in governance && typeof governance.summary === "string"
    ? governance.summary
    : "";

  return (
    <div className="space-y-5">
      <Card className="overflow-hidden rounded-3xl border-0 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-800 text-white shadow-xl">
        <CardHeader className="space-y-5 p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-3">
              <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs font-medium uppercase tracking-[0.18em] text-white/80">
                <FolderKanban className="h-3.5 w-3.5" />
                Executive Project Summary
              </div>
              <div>
                <CardTitle className="text-3xl font-semibold tracking-tight text-white">
                  {summaryValue(overview.project_name || projectName)}
                </CardTitle>
                <CardDescription className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">
                  {summaryValue(highlights.summary || overview.objective)}
                </CardDescription>
              </div>
            </div>
            <div className="grid gap-2 text-sm text-slate-200 sm:grid-cols-2">
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">Project ID</div>
                <div className="font-medium">{summaryValue(overview.project_id)}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">Customer</div>
                <div className="font-medium">{summaryValue(overview.customer_name)}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">Status</div>
                <div className="font-medium">{summaryValue(overview.status)}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">Contract</div>
                <div className="font-medium">{summaryValue(overview.contract_id || overview.contract_title)}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">Portfolio</div>
                <div className="font-medium">{summaryValue(overview.portfolio)}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">Owner</div>
                <div className="font-medium">{summaryValue(overview.portfolio_owner || governance.portfolio_owner)}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">Billable</div>
                <div className="font-medium">{summaryValue(overview.billable)}</div>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-400">Currency</div>
                <div className="font-medium">{summaryValue(overview.project_currency)}</div>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <Badge className={cn("border", badgeTone(health.overall || overview.status))}>
              Overall: {summaryValue(health.overall || overview.status)}
            </Badge>
            <Badge className={cn("border", badgeTone(health.schedule))}>
              Schedule: {summaryValue(health.schedule)}
            </Badge>
            <Badge className={cn("border", badgeTone(health.financial))}>
              Financial: {summaryValue(health.financial)}
            </Badge>
            <Badge className={cn("border", badgeTone(health.risk || risks.severity))}>
              Risk: {summaryValue(health.risk || risks.severity)}
            </Badge>
          </div>
        </CardHeader>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SummaryMetric icon={Gauge} label="Completion" value={overview.completion || health.delivery} />
        <SummaryMetric icon={DollarSign} label="Billing Model" value={overview.billing_model} />
        <SummaryMetric icon={Target} label="Module" value={highlights.module || overview.modules_delivered} />
        <SummaryMetric icon={AlertTriangle} label="Risk Impact" value={risks.impact || risks.pending} />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.35fr_0.9fr]">
        <div className="space-y-4">
          <Card className="rounded-3xl shadow-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <FolderKanban className="h-5 w-5 text-primary" />
                Key Information
              </CardTitle>
              <CardDescription>Aligned fields from the portal Key Information tab.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              <SummaryMetric icon={Gauge} label="Active" value={keyInfo.active} />
              <SummaryMetric icon={CircleAlert} label="Monitor Project" value={keyInfo.monitor_project} />
              <SummaryMetric icon={ShieldAlert} label="Troubled" value={keyInfo.troubled} />
              <SummaryMetric icon={Gauge} label="% Completion" value={keyInfo.percent_completion || overview.completion} />
              <SummaryMetric icon={CalendarDays} label="UAT Release" value={keyInfo.uat_release || keyInfo.uat_release_date_history} />
              <SummaryMetric icon={CalendarDays} label="Expected UAT" value={keyInfo.expected_uat_completion} />
              <SummaryMetric icon={Gauge} label="Delivery RAG" value={keyInfo.delivery_rag} />
              <SummaryMetric icon={Gauge} label="Product RAG" value={keyInfo.product_rag} />
              <SummaryMetric icon={DollarSign} label="Revenue Risk" value={keyInfo.revenue_risk} />
              <SummaryMetric icon={FolderKanban} label="Revenue Area" value={keyInfo.revenue_area} />
              <SummaryMetric icon={FolderKanban} label="Revenue Type" value={keyInfo.revenue_type} />
              <SummaryMetric icon={Target} label="Product Focus" value={keyInfo.product_focus} />
              <SummaryMetric icon={CalendarDays} label="Days Elapsed" value={keyInfo.days_elapsed} />
              <SummaryMetric icon={CalendarDays} label="Days to Go Live" value={keyInfo.days_to_go_live} />
              <SummaryMetric icon={CircleCheckBig} label="Reopened Cases" value={keyInfo.reopened_cases} />
              <SummaryMetric icon={CircleDashed} label="Untouched Cases" value={keyInfo.untouched_cases} />
              <SummaryMetric icon={CircleDashed} label="Untouched Req." value={keyInfo.untouched_requirements} />
              <SummaryMetric icon={FolderKanban} label="Financial Docs" value={keyInfo.financial_documents} />
              <SummaryMetric icon={FolderKanban} label="Pipeline Remarks" value={keyInfo.pipeline_remarks} />
            </CardContent>
          </Card>

          <Card className="rounded-3xl shadow-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <CalendarDays className="h-5 w-5 text-primary" />
                Delivery Timeline
              </CardTitle>
              <CardDescription>Key milestones and lifecycle checkpoints for the selected project.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              <SummaryMetric icon={CircleDashed} label="Start Date" value={timeline.start_date} />
              <SummaryMetric icon={CircleDashed} label="FSD Sign-off" value={timeline.fsd_sign_off} />
              <SummaryMetric icon={CircleDashed} label="Development" value={[timeline.dev_start_date, timeline.dev_end_date].filter(Boolean).join(" to ")} />
              <SummaryMetric icon={CircleDashed} label="SIT" value={[timeline.sit_start_date, timeline.sit_end_date].filter(Boolean).join(" to ")} />
              <SummaryMetric icon={CircleDashed} label="UAT" value={[timeline.uat_start_date, timeline.uat_end_date].filter(Boolean).join(" to ")} />
              <SummaryMetric icon={CircleCheckBig} label="Go Live" value={timeline.go_live_date} />
              <SummaryMetric icon={CircleDashed} label="Actual Effort" value={timeline.actual_effort} />
            </CardContent>
          </Card>

          <Card className="rounded-3xl shadow-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <DollarSign className="h-5 w-5 text-primary" />
                Financial Snapshot
              </CardTitle>
              <CardDescription>Current commercial position and revenue realization.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">
              <SummaryMetric icon={DollarSign} label="Service Value" value={financial.project_service_value} />
              <SummaryMetric icon={DollarSign} label="Revenue Recognized" value={financial.revenue_recognized} />
              <SummaryMetric icon={DollarSign} label="Cumulative Invoice" value={financial.cumulative_invoice} />
              <SummaryMetric icon={DollarSign} label="Advance" value={financial.advance} />
              <SummaryMetric icon={DollarSign} label="Revenue Available" value={financial.revenue_available} />
              <SummaryMetric icon={DollarSign} label="Left Over" value={financial.left_over} />
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card className="rounded-3xl shadow-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <ShieldAlert className="h-5 w-5 text-primary" />
                Risks and Attention Areas
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-2xl border bg-muted/30 p-4">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <span className="text-sm font-semibold text-foreground">Primary risk</span>
                  <Badge className={cn("border", badgeTone(risks.severity))}>
                    {summaryValue(risks.severity)}
                  </Badge>
                </div>
                <p className="text-sm leading-6 text-muted-foreground">{summaryValue(risks.risk_statement)}</p>
              </div>
              <SummaryMetric icon={AlertTriangle} label="Impact" value={risks.impact} />
              <SummaryMetric icon={AlertTriangle} label="Pending With" value={risks.pending} />
              <SummaryMetric icon={AlertTriangle} label="Aging" value={risks.aging} />
            </CardContent>
          </Card>

          <Card className="rounded-3xl shadow-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <Users className="h-5 w-5 text-primary" />
                Governance
              </CardTitle>
              {governanceSummary && (
                <CardDescription>{governanceSummary}</CardDescription>
              )}
            </CardHeader>
            <CardContent className="space-y-3">
              <SummaryMetric icon={Users} label="Project Manager" value={governance.project_manager} />
              <SummaryMetric icon={Users} label="HOD" value={governance.hod} />
              <SummaryMetric icon={Users} label="SVP" value={governance.svp} />
              <SummaryMetric icon={Users} label="Action Owner" value={governance.action_owner} />
            </CardContent>
          </Card>
        </div>
      </div>

      {(milestones.length > 0 || highlights.key_win || overview.modules_delivered) && (
        <Card className="rounded-3xl shadow-sm">
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <CardTitle className="flex items-center gap-2 text-lg">
                <CircleCheckBig className="h-5 w-5 text-primary" />
                Highlights
              </CardTitle>
              {onFillTimesheet && (
                <Button onClick={onFillTimesheet} disabled={Boolean(fillingTimesheet)} className="rounded-2xl">
                  {fillingTimesheet ? "Filling timesheet…" : "Fill Timesheet (8h)"}
                </Button>
              )}
            </div>
            <CardDescription>Delivered capabilities and recent wins for the selected project.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-2xl border bg-muted/20 p-4">
                <div className="mb-2 text-sm font-semibold text-foreground">Delivered modules</div>
                <p className="text-sm leading-6 text-muted-foreground">
                  {summaryValue(overview.modules_delivered || highlights.module)}
                </p>
              </div>
              <div className="rounded-2xl border bg-muted/20 p-4">
                <div className="mb-2 text-sm font-semibold text-foreground">Key highlight</div>
                <p className="text-sm leading-6 text-muted-foreground">
                  {summaryValue(highlights.key_win || highlights.summary)}
                </p>
              </div>
            </div>

            {milestones.length > 0 && (
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                {milestones.map((milestone) => (
                  <div key={`${milestone.label}-${milestone.date}`} className="rounded-2xl border bg-background/80 p-4">
                    <div className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      {milestone.label}
                    </div>
                    <div className="text-sm font-semibold text-foreground">{summaryValue(milestone.date)}</div>
                    {milestone.status && (
                      <div className="mt-2">
                        <Badge className={cn("border", badgeTone(milestone.status))}>{milestone.status}</Badge>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
