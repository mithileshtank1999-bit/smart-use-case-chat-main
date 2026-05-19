import { useState, useEffect, useRef, useCallback } from "react";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/AppSidebar";
import { ChatMessage, TypingIndicator } from "@/components/ChatMessage";
import { ChatInput } from "@/components/ChatInput";
import { apiCall, getApiBaseUrl } from "@/lib/apiClient";
import { supabase } from "@/integrations/supabase/client";
import { streamChat, type Msg } from "@/lib/streamChat";
import { toast } from "sonner";
import { ExecutiveSummaryPanel, type ExecutiveProjectSummary } from "@/components/ExecutiveSummaryPanel";
import type { ProjectRecord } from "@/components/ProjectResultsTable";
import type { CSSProperties } from "react";
import { format } from "date-fns";
import { TimesheetDialog } from "@/components/TimesheetDialog";
import { Button } from "@/components/ui/button";
import { TimesheetPromptDialog } from "@/components/TimesheetPromptDialog";
import { looksLikeTimesheetPrompt, parseTimesheetPrompt, type TimesheetPromptPlan } from "@/lib/timesheetPrompt";
import { JobProgressBanner } from "@/components/JobProgressBanner";
import { DocumentUploadPanel } from "@/components/DocumentUploadPanel";
import { WSRReportPanel, type GeneratedReport } from "@/components/WSRReportPanel";
import { MeetingSummaryPanel, type MeetingReport } from "@/components/MeetingSummaryPanel";
import { DownloadCenterPanel, type DownloadItem } from "@/components/DownloadCenterPanel";
import { N8NMonitorPanel } from "@/components/N8NMonitorPanel";
import { PortfolioSummaryPanel } from "@/components/PortfolioSummaryPanel";
import { OrgSummaryPanel } from "@/components/OrgSummaryPanel";

const AGENT_IMAGE_SRC = "/businessnext.jpeg";

interface ProjectOption {
  project_id: string;
  project_name: string;
  status?: string | null;
  go_live_date?: string | null;
  portfolio_name?: string | null;
  portfolio_owner?: string | null;
  account_name?: string | null;
  project_manager?: string | null;
  [key: string]: unknown;
}

interface PortfolioOption {
  portfolio_id: string;
  portfolio_name: string;
  project_count?: number;
  active_projects?: number;
  escalated_projects?: number;
}

type LevelType = "organisation" | "portfolio" | "project";
type PanelName = "documents" | "wsr" | "meeting" | "downloads" | "n8n-monitor";

// Only patterns with NO backend handler at all. Everything else goes to the server.
const unsupportedUseCasePatterns = [
  "resource allocation",
  "optimize resource",
];

function isUnsupportedUseCase(message: string) {
  const normalizedMessage = message.toLowerCase();
  return unsupportedUseCasePatterns.some((pattern) => normalizedMessage.includes(pattern));
}

function buildNoDataMessage(message: string, projectName?: string | null) {
  return [
    "No data available yet",
    "",
    `Use case: ${message}`,
    projectName ? `Project: ${projectName}` : "",
    "",
    "This use case is not connected to live data yet.",
    "The project summary cards and project search dataset are available now.",
  ]
    .filter(Boolean)
    .join("\n");
}

interface Conversation {
  id: string;
  title: string;
  updated_at: string;
}

const isLocal = () => !!getApiBaseUrl();

const Index = () => {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [projectsQuery, setProjectsQuery] = useState("");
  const [isProjectsLoading, setIsProjectsLoading] = useState(false);
  const [employeeName, setEmployeeName] = useState<string>(() => localStorage.getItem("employee_name") || "Mithilesh Tank");
  const [selectedProject, setSelectedProject] = useState<ProjectOption | null>(null);
  const [activeUseCaseLabel, setActiveUseCaseLabel] = useState<string | null>(null);
  const [projectSummary, setProjectSummary] = useState<ExecutiveProjectSummary | null>(null);
  const [isSummaryLoading, setIsSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [isTimesheetFilling, setIsTimesheetFilling] = useState(false);
  const [timesheetOpen, setTimesheetOpen] = useState(false);
  const [timesheetPromptOpen, setTimesheetPromptOpen] = useState(false);
  const [timesheetPromptPlan, setTimesheetPromptPlan] = useState<TimesheetPromptPlan | null>(null);
  const [timesheetPromptOptions, setTimesheetPromptOptions] = useState<{
    items: string[];
    engagementroleids: number[];
    engagementlocationids: number[];
  } | null>(null);
  const [isTimesheetPromptConfirming, setIsTimesheetPromptConfirming] = useState(false);
  const [openPanel, setOpenPanel] = useState<PanelName | null>(null);
  const [downloads, setDownloads] = useState<DownloadItem[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [level, setLevel] = useState<LevelType>("project");
  const [portfolios, setPortfolios] = useState<PortfolioOption[]>([]);
  const [portfoliosLoading, setPortfoliosLoading] = useState(false);
  const [selectedPortfolio, setSelectedPortfolio] = useState<PortfolioOption | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fetchProjectOptions = useCallback(
    async (query: string) => {
      setProjectsQuery(query);
      setIsProjectsLoading(true);

      const name = employeeName.trim();

      const { data, error } = name
        ? await apiCall("employee/projects", undefined, { method: "GET", query: { name, q: query, limit: "200" } })
        : await apiCall("project-options", undefined, { method: "GET", query: { q: query, limit: "200", offset: "0" } });

      if (!error && Array.isArray(data?.results)) {
        setProjects(data.results as ProjectOption[]);
        setIsProjectsLoading(false);
        return;
      }

      // Back-compat fallback: older endpoint shapes.
      const legacy = await apiCall("db-proxy", { query_type: "list_projects" });
      if (!legacy.error && Array.isArray(legacy.data?.results)) {
        setProjects(legacy.data.results as ProjectOption[]);
        setIsProjectsLoading(false);
        return;
      }

      setIsProjectsLoading(false);
      toast.error(error?.message || "Unable to load projects.");
    },
    [employeeName],
  );

  useEffect(() => {
    (async () => {
      await fetchProjectOptions("");
    })();
  }, [fetchProjectOptions]);

  useEffect(() => {
    // When the sidebar employee changes, refresh the project list automatically.
    // This is what enables "Mithilesh Tank" -> allocated projects without manual searching.
    fetchProjectOptions(projectsQuery);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [employeeName]);

  useEffect(() => {
    localStorage.setItem("employee_name", employeeName);
  }, [employeeName]);

  const loadConversations = useCallback(async () => {
    if (isLocal()) {
      setConversations([]);
    } else {
      const { data } = await supabase
        .from("conversations")
        .select("id, title, updated_at")
        .order("updated_at", { ascending: false });
      if (data) setConversations(data);
    }
  }, []);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  useEffect(() => {
    if (!activeConversationId) {
      setMessages([]);
      return;
    }
    (async () => {
      if (isLocal()) {
        return;
      } else {
        const { data } = await supabase
          .from("messages")
          .select("role, content")
          .eq("conversation_id", activeConversationId)
          .order("created_at", { ascending: true });
        if (data) setMessages(data as Msg[]);
      }
    })();
  }, [activeConversationId]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, projectSummary, isSummaryLoading]);

  const fetchProjectSummary = useCallback(async (project: ProjectOption) => {
    setSelectedProject(project);
    setSummaryError(null);
    setProjectSummary(null);
    setIsSummaryLoading(true);

    const { data, error } = await apiCall("summary", {
      project_id: project.project_id || undefined,
      project_name: project.project_name || undefined,
      project_data: project,
    });

    if (error) {
      setSummaryError(error.message || "Unable to load executive summary.");
      setIsSummaryLoading(false);
      return;
    }

    setProjectSummary((data?.summary as ExecutiveProjectSummary) ?? null);
    setSummaryError(null);
    setIsSummaryLoading(false);
  }, []);

  const fetchPortfolios = useCallback(async () => {
    setPortfoliosLoading(true);
    const { data, error } = await apiCall("portfolios", undefined, { method: "GET" });
    setPortfoliosLoading(false);
    if (!error && Array.isArray(data?.results)) {
      setPortfolios(data.results as PortfolioOption[]);
    }
  }, []);

  const handleLevelChange = useCallback((newLevel: LevelType) => {
    setLevel(newLevel);
    if (newLevel === "portfolio" && portfolios.length === 0) {
      fetchPortfolios();
    }
  }, [portfolios.length, fetchPortfolios]);

  const handleSelectPortfolio = useCallback((portfolioId: string) => {
    const portfolio = portfolios.find((p) => p.portfolio_id === portfolioId) || null;
    setSelectedPortfolio(portfolio);
  }, [portfolios]);

  const handleFillTimesheet = useCallback(async () => {
    if (!selectedProject?.project_id) {
      toast.error("Select a project first.");
      return;
    }
    setIsTimesheetFilling(true);
    try {
      const today = format(new Date(), "yyyy-MM-dd");
      const { data, error } = await apiCall("timesheet/fill", {
        project_id: Number(selectedProject.project_id),
        employee_name: "Mithilesh Tank",
        work_date: today,
        start_time: "09:00",
        end_time: "17:00",
        effort_minutes: 480,
        description: "SDG development",
        related_to: "Project Module",
        item: "Config",
        engagement_role: "Technical Consultant",
        engagement_location: "Offsite",
      });
      if (error) {
        toast.error(error.message || "Failed to fill timesheet.");
        return;
      }
      if (data?.already_exists) {
        toast.message(`Timesheet already exists for ${today} (ID ${data.timesheetid}).`);
        return;
      }
      toast.success(`Timesheet filled for ${today}.`);
    } finally {
      setIsTimesheetFilling(false);
    }
  }, [selectedProject?.project_id]);

  const handleNewChat = () => {
    setActiveConversationId(null);
    setMessages([]);
    setInputValue("");
    setActiveUseCaseLabel(null);
  };

  const handleSelectConversation = (id: string) => {
    setActiveConversationId(id);
    setInputValue("");
  };

  const handleDeleteConversation = async (id: string) => {
    if (isLocal()) {
      await apiCall(`conversations/${id}`, undefined, { method: "DELETE" });
    } else {
      await supabase.from("conversations").delete().eq("id", id);
    }
    if (activeConversationId === id) handleNewChat();
    loadConversations();
  };

  const handleSelectUseCase = (prompt: string, label: string) => {
    setActiveUseCaseLabel(label);
    let resolved = prompt;
    if (selectedProject) {
      resolved = resolved.replace(/\{project_name\}/g, selectedProject.project_name);
      if (selectedProject.portfolio_name)
        resolved = resolved.replace(/\{portfolio_name\}/g, selectedProject.portfolio_name as string);
      if (selectedProject.account_name)
        resolved = resolved.replace(/\{account_name\}/g, selectedProject.account_name as string);
    }
    if (employeeName.trim())
      resolved = resolved.replace(/\{employee_name\}/g, employeeName.trim());
    setInputValue(resolved);
  };

  const handleSelectProject = async (projectId: string) => {
    const project = projects.find((entry) => entry.project_id === projectId) || null;
    setSelectedProject(project);
    setSummaryError(null);

    if (!project) {
      setProjectSummary(null);
      return;
    }

    await fetchProjectSummary(project);
  };

  const handleProjectResultClick = async (project: ProjectRecord) => {
    const selected = {
      project_id: project.project_id,
      project_name: project.project_name,
    };
    setActiveUseCaseLabel("Project search result");
    await fetchProjectSummary(selected);
  };

  const handleSend = async (message: string) => {
    setInputValue("");
    const userMsg: Msg = { role: "user", content: message };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);

    const lower = message.toLowerCase();
    const wantsMyProjects =
      (lower.includes("show") || lower.includes("list")) &&
      lower.includes("my") &&
      lower.includes("projects");

    if (wantsMyProjects) {
      const payload = projects.map((p) => ({
        project_id: String(p.project_id),
        project_name: String(p.project_name),
        status: String(p.status ?? ""),
        go_live_date: (p as any).go_live_date ?? null,
        portfolio_name: (p as any).portfolio_name ?? null,
        portfolio_owner: (p as any).portfolio_owner ?? null,
        account_name: (p as any).account_name ?? null,
        project_manager: (p as any).project_manager ?? null,
      }));
      setMessages([
        ...newMessages,
        {
          role: "assistant",
          content:
            `Here are the projects allocated to **${employeeName.trim() || "the selected employee"}**:\n\n` +
            "```json\n" +
            JSON.stringify(payload, null, 2) +
            "\n```",
        },
      ]);
      return;
    }

    if (looksLikeTimesheetPrompt(message)) {
      const basePlan = parseTimesheetPrompt(message);
      const projectIdMatch = message.match(/\bproject\s*id\b[^\d]*(\d{1,10})\b/i) || message.match(/\bpid\b[^\d]*(\d{1,10})\b/i);
      let project = null as ProjectOption | null;
      if (projectIdMatch?.[1]) {
        project = projects.find((p) => String(p.project_id) === String(projectIdMatch[1])) ?? null;
      }

      if (!project) {
        const phraseMatch =
          message.match(/\bin\s+the\s+(.+?)\s+project\b/i) ||
          message.match(/\bin\s+(.+?)\s+project\b/i) ||
          message.match(/\bfor\s+the\s+(.+?)\s+project\b/i) ||
          message.match(/\bfor\s+(.+?)\s+project\b/i);
        const phrase = (phraseMatch?.[1] || "").trim();

        if (phrase) {
          const phraseNorm = phrase.toLowerCase().replace(/[^a-z0-9\s]/g, " ").trim();
          project =
            projects.find((p) => String(p.project_name).toLowerCase().includes(phraseNorm)) ||
            projects.find((p) => phraseNorm.includes(String(p.project_name).toLowerCase().slice(0, 8))) ||
            null;
        }

        if (!project) {
          const msgNorm = message.toLowerCase().replace(/[^a-z0-9\s]/g, " ");
          const tokens = msgNorm
            .split(/\s+/)
            .map((t) => t.trim())
            .filter((t) => t.length >= 3 && !["fill", "timesheet", "today", "week", "weekly", "month", "monthly", "hours", "hour", "under", "category", "using", "project", "id", "for", "in", "the", "my", "past", "last", "current", "specific", "based", "status"].includes(t));

          // Pick the project with the highest token overlap.
          let best: { p: ProjectOption; score: number } | null = null;
          for (const p of projects) {
            const nameNorm = String(p.project_name).toLowerCase().replace(/[^a-z0-9\s]/g, " ");
            let score = 0;
            for (const tok of tokens) {
              if (nameNorm.includes(tok)) score += 1;
            }
            if (score > 0 && (!best || score > best.score)) best = { p, score };
          }
          project = best?.p ?? null;
        }

        if (!project) project = (selectedProject as any) ?? null;
      }

      if (!project?.project_id) {
        setMessages([
          ...newMessages,
          { role: "assistant", content: "Which project should I use for this timesheet? Select a project in the sidebar or include the project ID/name in your prompt." },
        ]);
        return;
      }

      const plan: TimesheetPromptPlan = {
        ...basePlan,
        project_id: String(project.project_id),
        project_name: String(project.project_name),
      };
      setTimesheetPromptPlan(plan);

      try {
        const { data } = await apiCall("timesheet/options", undefined, { method: "GET", query: { project_id: String(project.project_id) } });
        const next = (data?.options as any) ?? null;
        if (next?.items && Array.isArray(next.items)) setTimesheetPromptOptions(next);
        else setTimesheetPromptOptions(null);
      } catch {
        setTimesheetPromptOptions(null);
      }

      setTimesheetPromptOpen(true);
      setMessages([
        ...newMessages,
        { role: "assistant", content: "I parsed your request. Please confirm the timesheet details in the dialog." },
      ]);
      return;
    }

    if (isUnsupportedUseCase(message)) {
      setMessages([
        ...newMessages,
        {
          role: "assistant",
          content: buildNoDataMessage(message, selectedProject?.project_name ?? null),
        },
      ]);
      return;
    }

    setIsStreaming(true);

    let convId = activeConversationId;

    try {
      if (!convId) {
        convId = "local-temp-id";
        setActiveConversationId(convId);
      }

      if (!isLocal()) {
        await supabase
          .from("messages")
          .insert({ conversation_id: convId, role: "user", content: message });

        await supabase.from("conversations").update({ updated_at: new Date().toISOString() }).eq("id", convId);
      }

      const controller = new AbortController();
      abortRef.current = controller;

      await streamChat({
        messages: newMessages,
        employeeName: employeeName.trim() || undefined,
        signal: controller.signal,
        onDelta: (text) => {
          setMessages((prev) => {
            const last = prev[prev.length - 1];

            if (last?.role === "assistant") {
              return prev.map((msg, index) =>
                index === prev.length - 1
                  ? { ...msg, content: text }
                  : msg
              );
            }

            return [...prev, { role: "assistant", content: text }];
          });
        },
        onDone: async () => {
          setIsStreaming(false);
        },
      });
    } catch (err: any) {
      setIsStreaming(false);
      if (err.name !== "AbortError") {
        toast.error(err.message || "Something went wrong");
      }
    }
  };

  const showSummaryPanel = Boolean(selectedProject || isSummaryLoading || summaryError || projectSummary);

  const confirmTimesheetFromPrompt = async () => {
    if (!timesheetPromptPlan?.project_id) return;
    if (!employeeName.trim()) {
      toast.error("Employee name is required.");
      return;
    }

    const projectId = Number(timesheetPromptPlan.project_id);
    if (Number.isNaN(projectId)) {
      toast.error("Invalid project ID.");
      return;
    }

    const dates: string[] =
      timesheetPromptPlan.timeframe.kind === "single"
        ? [timesheetPromptPlan.timeframe.dateISO]
        : timesheetPromptPlan.timeframe.datesISO;

    setIsTimesheetPromptConfirming(true);
    try {
      // Try to use a recent template so required IDs (role/location/task) map cleanly.
      const templatesResp = await apiCall("timesheet/templates", undefined, {
        method: "GET",
        query: { employee_name: employeeName.trim(), project_id: String(projectId), limit: "10" },
      });
      const templateId = (templatesResp.data?.results?.[0]?.timesheetid as number | undefined) ?? undefined;

      const optionsResp = await apiCall("timesheet/options", undefined, { method: "GET", query: { project_id: String(projectId) } });
      const items: string[] = (optionsResp.data?.options?.items as string[]) ?? [];
      const category = (timesheetPromptPlan.category || "").trim().toLowerCase();
      const matchedItem =
        items.find((x) => x.toLowerCase() === category) ||
        items.find((x) => category && x.toLowerCase().includes(category)) ||
        (category.includes("leave") ? items.find((x) => x.toLowerCase().includes("leave")) : undefined);

      const item =
        (timesheetPromptPlan.item || "").trim() ||
        matchedItem ||
        (category ? category : "Config");
      const description = (timesheetPromptPlan.description || "").trim() || "SDG development";
      const related_to = (timesheetPromptPlan.related_to || "").trim() || "Project Module";
      const engagement_role = (timesheetPromptPlan.engagement_role || "").trim() || "Technical Consultant";
      const engagement_location = (timesheetPromptPlan.engagement_location || "").trim() || "Offsite";

      let okCount = 0;
      for (const work_date of dates) {
        const payload: any = {
          project_id: projectId,
          employee_name: employeeName.trim(),
          work_date,
          start_time: timesheetPromptPlan.start_time || "09:00",
          end_time: timesheetPromptPlan.end_time || "17:00",
          effort_minutes: Number(timesheetPromptPlan.effort_minutes || 480),
          description,
          related_to,
          item,
          engagement_role,
          engagement_location,
        };
        if (templateId) payload.template_timesheetid = templateId;

        const { data, error } = await apiCall("timesheet/fill", payload);
        if (error) {
          toast.error(error.message || `Failed to fill timesheet for ${work_date}.`);
          continue;
        }
        if (data?.already_exists) {
          toast.message(`Timesheet already exists for ${work_date} (ID ${data.timesheetid}).`);
          continue;
        }
        okCount += 1;
      }

      setTimesheetPromptOpen(false);
      setTimesheetPromptPlan(null);
      toast.success(`Timesheet filled for ${okCount}/${dates.length} day(s).`);
    } finally {
      setIsTimesheetPromptConfirming(false);
    }
  };

  return (
    <SidebarProvider style={{ "--sidebar-width": "24rem" } as CSSProperties}>
      <div className="flex h-screen w-full overflow-hidden bg-[radial-gradient(circle_at_top,_rgba(236,72,153,0.08),_transparent_32%),linear-gradient(180deg,_#f8fafc_0%,_#fdf2f8_100%)]">
        <AppSidebar
          conversations={conversations}
          activeConversationId={activeConversationId}
          onSelectConversation={handleSelectConversation}
          onNewChat={handleNewChat}
          onDeleteConversation={handleDeleteConversation}
          onSelectUseCase={handleSelectUseCase}
          projects={projects}
          employeeName={employeeName}
          onEmployeeNameChange={setEmployeeName}
          projectsQuery={projectsQuery}
          projectsLoading={isProjectsLoading}
          onSearchProjects={fetchProjectOptions}
          selectedProject={selectedProject}
          currentUseCaseLabel={activeUseCaseLabel}
          summaryError={summaryError}
          onSelectProject={handleSelectProject}
          onRetrySummary={selectedProject ? () => fetchProjectSummary(selectedProject) : undefined}
          onOpenPanel={setOpenPanel}
          level={level}
          onLevelChange={handleLevelChange}
          portfolios={portfolios}
          portfoliosLoading={portfoliosLoading}
          selectedPortfolio={selectedPortfolio}
          onSelectPortfolio={handleSelectPortfolio}
        />
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <header className="shrink-0 border-b border-slate-200/80 bg-white/80 backdrop-blur-sm">
            <div className="h-14 flex items-center gap-3 px-4">
              <SidebarTrigger className="text-muted-foreground hover:text-foreground" />
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center overflow-hidden rounded-full border border-slate-200/70 bg-white/90">
                  <img src={AGENT_IMAGE_SRC} alt="BUSINESSNEXT" className="h-full w-full object-contain" />
                </div>
                <h1 className="text-base font-semibold text-foreground">
                  {level === "organisation" ? "Organisation Intelligence" : level === "portfolio" ? "Portfolio Intelligence" : "Project Intelligence"}
                </h1>
              </div>
              <div className="ml-auto flex items-center gap-2">
                {selectedProject && (
                  <Button
                    variant="outline"
                    className="rounded-2xl"
                    onClick={() => setTimesheetOpen(true)}
                  >
                    Timesheet
                  </Button>
                )}
              </div>
            </div>
            {activeJobId && (
              <JobProgressBanner
                jobId={activeJobId}
                onDismiss={() => setActiveJobId(null)}
              />
            )}
          </header>

          <div className="min-h-0 flex-1 overflow-hidden">
            <div ref={scrollRef} className="h-full overflow-y-auto">
              <div className="mx-auto w-full max-w-7xl px-4 py-6 md:px-6 xl:px-8">
                {timesheetPromptPlan && (
                  <TimesheetPromptDialog
                    open={timesheetPromptOpen}
                    onOpenChange={(open) => {
                      setTimesheetPromptOpen(open);
                      if (!open) {
                        setTimesheetPromptPlan(null);
                        setTimesheetPromptOptions(null);
                      }
                    }}
                    plan={timesheetPromptPlan}
                    onPlanChange={setTimesheetPromptPlan}
                    employeeName={employeeName}
                    projectLabel={`${timesheetPromptPlan.project_name ?? ""} (ID ${timesheetPromptPlan.project_id})`}
                    options={timesheetPromptOptions}
                    onConfirm={confirmTimesheetFromPrompt}
                    confirming={isTimesheetPromptConfirming}
                  />
                )}
                {level === "organisation" && (
                  <div className="mb-8">
                    <OrgSummaryPanel />
                  </div>
                )}

                {level === "portfolio" && selectedPortfolio && (
                  <div className="mb-8">
                    <PortfolioSummaryPanel
                      portfolioId={selectedPortfolio.portfolio_id}
                      portfolioName={selectedPortfolio.portfolio_name}
                    />
                  </div>
                )}

                {level === "project" && showSummaryPanel && (
                  <div className="mb-8">
                    <ExecutiveSummaryPanel
                      projectName={selectedProject?.project_name}
                      summary={projectSummary}
                      loading={isSummaryLoading}
                      error={summaryError}
                      onFillTimesheet={selectedProject ? handleFillTimesheet : undefined}
                      fillingTimesheet={isTimesheetFilling}
                    />
                  </div>
                )}

                <TimesheetDialog
                  open={timesheetOpen}
                  onOpenChange={setTimesheetOpen}
                  projects={projects}
                  selectedProjectId={selectedProject?.project_id ?? null}
                  employeeName={employeeName}
                  onEmployeeNameChange={setEmployeeName}
                />

                <DocumentUploadPanel
                  open={openPanel === "documents"}
                  onOpenChange={(v) => setOpenPanel(v ? "documents" : null)}
                />

                <WSRReportPanel
                  open={openPanel === "wsr"}
                  onOpenChange={(v) => setOpenPanel(v ? "wsr" : null)}
                  defaultProjectName={selectedProject?.project_name}
                  onReportGenerated={(r: GeneratedReport) =>
                    setDownloads((prev) => [r as DownloadItem, ...prev])
                  }
                />

                <MeetingSummaryPanel
                  open={openPanel === "meeting"}
                  onOpenChange={(v) => setOpenPanel(v ? "meeting" : null)}
                  onReportGenerated={(r: MeetingReport) =>
                    setDownloads((prev) => [r as DownloadItem, ...prev])
                  }
                />

                <DownloadCenterPanel
                  open={openPanel === "downloads"}
                  onOpenChange={(v) => setOpenPanel(v ? "downloads" : null)}
                  items={downloads}
                  onRemove={(id) => setDownloads((prev) => prev.filter((d) => d.id !== id))}
                />

                {openPanel === "n8n-monitor" && (
                  <div className="mb-8">
                    <div className="mb-4 flex items-center justify-between">
                      <h2 className="text-xl font-semibold tracking-tight">Automation Monitor</h2>
                      <button
                        onClick={() => setOpenPanel(null)}
                        className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                      >
                        ✕ Close
                      </button>
                    </div>
                    <N8NMonitorPanel />
                  </div>
                )}

                {messages.length === 0 ? (
                  !(level === "organisation" || (level === "portfolio" && selectedPortfolio) || (level === "project" && showSummaryPanel)) && (
                    <div className="flex min-h-[58vh] flex-col items-center justify-center rounded-[2rem] border border-white/70 bg-white/65 px-6 text-center shadow-[0_18px_60px_rgba(15,23,42,0.08)] backdrop-blur-sm">
                      <div className="mb-6 flex h-24 w-24 items-center justify-center overflow-hidden rounded-[2rem] border border-slate-200/70 bg-white/90">
                        <img src={AGENT_IMAGE_SRC} alt="BUSINESSNEXT" className="h-full w-full object-contain p-3" />
                      </div>
                      <h2 className="mb-3 text-4xl font-semibold tracking-tight text-foreground">
                        {level === "portfolio" ? "Portfolio Intelligence" : "Project Intelligence Assistant"}
                      </h2>
                      <p className="max-w-2xl text-lg leading-8 text-muted-foreground">
                        {level === "portfolio"
                          ? selectedPortfolio
                            ? `Viewing ${selectedPortfolio.portfolio_name}. Ask about portfolio summary, timesheet hours, revenue, or project health.`
                            : "Select a portfolio from the sidebar, then ask about its summary, timesheet hours, revenue pipeline, or project health."
                          : "Select a project from the sidebar to view the executive summary, then choose a use case or ask your own question about planning, timesheets, defects, or test cases."}
                      </p>
                    </div>
                  )
                ) : (
                  <div className="mx-auto max-w-4xl rounded-[2rem] border border-white/80 bg-white/75 shadow-[0_18px_60px_rgba(15,23,42,0.08)] backdrop-blur-sm">
                    {messages.map((msg, index) => (
                      <ChatMessage
                        key={index}
                        role={msg.role}
                        content={msg.content}
                        onProjectClick={handleProjectResultClick}
                      />
                    ))}
                    {isStreaming && messages[messages.length - 1]?.role === "user" && <TypingIndicator />}
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="shrink-0 border-t border-slate-200/80 bg-white/70 backdrop-blur-sm">
            <ChatInput
              value={inputValue}
              onChange={setInputValue}
              onSend={handleSend}
              disabled={isStreaming}
            />
          </div>
        </div>
      </div>
    </SidebarProvider>
  );
};

export default Index;
