import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BriefcaseBusiness,
  Bug,
  Building2,
  ChevronDown,
  ChevronRight,
  Clock,
  Download,
  FileBarChart,
  FileText,
  FolderOpen,
  LayoutDashboard,
  MessageSquare,
  Mic,
  Plus,
  Search,
  Settings,
  Shield,
  Sparkles,
  TestTube2,
  Trash2,
  Upload,
  Users,
  Wrench,
  Zap,
} from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useNavigate } from "react-router-dom";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { useCaseCategories } from "@/config/useCasePrompts";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from "@/components/ui/tooltip";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { apiCall } from "@/lib/apiClient";

const AGENT_IMAGE_SRC = "/businessnext.jpeg";

const iconMap: Record<string, React.ElementType> = {
  LayoutDashboard,
  Clock,
  Bug,
  TestTube2,
  FileText,
  FileBarChart,
  Users,
  AlertTriangle,
  Settings,
};

const useCaseGroups = [
  {
    id: "planning",
    label: "Planning & Delivery",
    icon: BriefcaseBusiness,
    categories: ["Project Planning Intelligence", "Report Automation"],
  },
  {
    id: "execution",
    label: "Execution & Workforce",
    icon: Wrench,
    categories: ["Timesheet Management", "AI Meeting Summary", "Resource Allocation & Optimization"],
  },
  {
    id: "quality",
    label: "Quality & Cases",
    icon: Bug,
    categories: ["Defect & Case Management", "Test Cases Management"],
  },
  {
    id: "knowledge",
    label: "Knowledge & Risk",
    icon: Sparkles,
    categories: ["Intelligent Document Management", "Smart Issue / Risk Analysis"],
  },
];

interface Conversation {
  id: string;
  title: string;
  updated_at: string;
}

interface ProjectOption {
  project_id: string;
  project_name: string;
  status?: string | null;
  portfolio_name?: string | null;
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

interface AppSidebarProps {
  conversations: Conversation[];
  activeConversationId: string | null;
  onSelectConversation: (id: string) => void;
  onNewChat: () => void;
  onDeleteConversation: (id: string) => void;
  onSelectUseCase: (prompt: string, label: string) => void;
  projects: ProjectOption[];
  employeeName?: string;
  onEmployeeNameChange?: (name: string) => void;
  projectsQuery?: string;
  projectsLoading?: boolean;
  onSearchProjects?: (query: string) => void;
  selectedProject: ProjectOption | null;
  currentUseCaseLabel?: string | null;
  summaryError?: string | null;
  onSelectProject: (projectId: string) => void;
  onRetrySummary?: () => void;
  onOpenPanel?: (panel: PanelName) => void;
  level?: LevelType;
  onLevelChange?: (level: LevelType) => void;
  portfolios?: PortfolioOption[];
  portfoliosLoading?: boolean;
  selectedPortfolio?: PortfolioOption | null;
  onSelectPortfolio?: (portfolioId: string) => void;
}

export function AppSidebar({
  conversations,
  activeConversationId,
  onSelectConversation,
  onNewChat,
  onDeleteConversation,
  onSelectUseCase,
  projects,
  employeeName,
  onEmployeeNameChange,
  projectsQuery,
  projectsLoading,
  onSearchProjects,
  selectedProject,
  currentUseCaseLabel,
  summaryError,
  onSelectProject,
  onRetrySummary,
  onOpenPanel,
  level = "project",
  onLevelChange,
  portfolios = [],
  portfoliosLoading,
  selectedPortfolio,
  onSelectPortfolio,
}: AppSidebarProps) {
  const { state } = useSidebar();
  const collapsed = state === "collapsed";
  const navigate = useNavigate();
  const [projectChooserOpen, setProjectChooserOpen] = useState(false);
  const [portfolioChooserOpen, setPortfolioChooserOpen] = useState(false);
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({
    planning: true,
    execution: false,
    quality: false,
    knowledge: false,
  });
  const [projectSearch, setProjectSearch] = useState(projectsQuery ?? "");
  const [employeeSuggestions, setEmployeeSuggestions] = useState<string[]>([]);

  useEffect(() => {
    setProjectSearch(projectsQuery ?? "");
  }, [projectsQuery]);

  useEffect(() => {
    if (!onEmployeeNameChange) return;
    const q = String(employeeName ?? "").trim();
    if (q.length < 2) {
      setEmployeeSuggestions([]);
      return;
    }

    const handle = window.setTimeout(async () => {
      const { data, error } = await apiCall("employee/search", undefined, {
        method: "GET",
        query: { q, limit: "12" },
      });
      if (error) return;
      const results: string[] = Array.isArray(data?.results) ? data.results : [];
      setEmployeeSuggestions(results);
    }, 250);

    return () => window.clearTimeout(handle);
  }, [employeeName, onEmployeeNameChange]);

  useEffect(() => {
    if (!onSearchProjects) return;
    const handle = window.setTimeout(() => {
      onSearchProjects(projectSearch.trim());
    }, 250);
    return () => window.clearTimeout(handle);
  }, [projectSearch, onSearchProjects]);

  const groupedCategories = useMemo(
    () =>
      useCaseGroups.map((group) => ({
        ...group,
        items: useCaseCategories.filter((category) => group.categories.includes(category.label)),
      })),
    []
  );

  const toggleGroup = (groupId: string) => {
    setOpenGroups((prev) => ({ ...prev, [groupId]: !prev[groupId] }));
  };

  return (
    <Sidebar collapsible="icon" className="border-r-0 bg-sidebar">
      <SidebarContent className="bg-sidebar">
        <ScrollArea className="flex-1">
          <SidebarGroup>
            <SidebarGroupContent className="px-3 pt-3">
              {collapsed ? (
                <SidebarMenu>
                  {(["organisation", "portfolio", "project"] as const).map((l) => (
                    <SidebarMenuItem key={l}>
                      <SidebarMenuButton
                        className={cn("text-sidebar-foreground/80 hover:bg-sidebar-accent", level === l && "text-primary")}
                        onClick={() => onLevelChange?.(l)}
                        title={l.charAt(0).toUpperCase() + l.slice(1)}
                      >
                        {l === "organisation" ? <Building2 className="h-4 w-4" /> : l === "portfolio" ? <BriefcaseBusiness className="h-4 w-4" /> : <FolderOpen className="h-4 w-4" />}
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ))}
                </SidebarMenu>
              ) : (
                <div className="space-y-3">
                  {/* Level switcher */}
                  <div className="flex gap-1 rounded-xl border border-white/10 bg-white/5 p-1">
                    {(["organisation", "portfolio", "project"] as const).map((l) => (
                      <button
                        key={l}
                        onClick={() => onLevelChange?.(l)}
                        className={cn(
                          "flex-1 rounded-lg py-2 text-xs font-semibold capitalize transition",
                          level === l
                            ? "bg-primary text-primary-foreground shadow-sm"
                            : "text-sidebar-foreground/60 hover:bg-white/5 hover:text-sidebar-foreground"
                        )}
                      >
                        {l === "organisation" ? "Org" : l.charAt(0).toUpperCase() + l.slice(1)}
                      </button>
                    ))}
                  </div>

                  {/* Organisation level */}
                  {level === "organisation" && (
                    <div className="rounded-2xl border border-white/10 bg-white/5 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
                      <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/10">
                          <Building2 className="h-5 w-5 text-sidebar-foreground/70" />
                        </div>
                        <div>
                          <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-sidebar-foreground/50">Scope</div>
                          <div className="text-base font-semibold text-sidebar-foreground">Organisation</div>
                        </div>
                      </div>
                      <div className="mt-3 rounded-xl border border-primary/20 bg-primary/10 px-3 py-2 text-xs leading-5 text-sidebar-foreground/80">
                        Ask about org headcount, total revenue, utilization, portfolio health, or project counts.
                      </div>
                    </div>
                  )}

                  {/* Portfolio level */}
                  {level === "portfolio" && (
                    <div className="space-y-3">
                      <div className="rounded-2xl border border-white/10 bg-white/5 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
                        <div className="mb-3 flex items-start justify-between gap-3">
                          <div>
                            <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-sidebar-foreground/50">
                              Active portfolio
                            </div>
                            <div className="mt-2 text-base font-semibold leading-6 text-sidebar-foreground">
                              {selectedPortfolio?.portfolio_name || "Choose a portfolio"}
                            </div>
                          </div>
                          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/10">
                            <BriefcaseBusiness className="h-5 w-5 text-sidebar-foreground/70" />
                          </div>
                        </div>
                        {selectedPortfolio ? (
                          <div className="flex flex-wrap gap-2">
                            <Badge variant="outline" className="border-white/10 bg-white/5 text-sidebar-foreground/80">
                              ID {selectedPortfolio.portfolio_id}
                            </Badge>
                            {selectedPortfolio.project_count !== undefined && (
                              <Badge variant="outline" className="border-white/10 bg-white/5 text-sidebar-foreground/80">
                                {selectedPortfolio.project_count} projects
                              </Badge>
                            )}
                            {(selectedPortfolio.active_projects ?? 0) > 0 && (
                              <Badge variant="outline" className="border-emerald-400/20 bg-emerald-400/10 text-emerald-200/80">
                                {selectedPortfolio.active_projects} active
                              </Badge>
                            )}
                          </div>
                        ) : (
                          <div className="rounded-xl border border-dashed border-white/10 px-3 py-4 text-sm text-sidebar-foreground/60">
                            Select a portfolio to view portfolio-level analytics.
                          </div>
                        )}
                      </div>

                      <Collapsible open={portfolioChooserOpen} onOpenChange={setPortfolioChooserOpen}>
                        <CollapsibleTrigger className="flex w-full items-center justify-between rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-medium text-sidebar-foreground transition hover:bg-white/10">
                          <span>{selectedPortfolio ? "Switch portfolio" : "Browse portfolios"}</span>
                          <ChevronDown className={cn("h-4 w-4 transition-transform", portfolioChooserOpen && "rotate-180")} />
                        </CollapsibleTrigger>
                        <CollapsibleContent className="pt-3">
                          <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
                            {portfoliosLoading ? (
                              <div className="px-3 py-4 text-sm text-sidebar-foreground/60">Loading portfolios…</div>
                            ) : portfolios.length === 0 ? (
                              <div className="rounded-xl border border-dashed border-white/10 px-3 py-4 text-sm text-sidebar-foreground/60">
                                No portfolios found.
                              </div>
                            ) : portfolios.map((portfolio) => {
                              const isSelected = selectedPortfolio?.portfolio_id === portfolio.portfolio_id;
                              return (
                                <button
                                  key={portfolio.portfolio_id}
                                  onClick={() => {
                                    onSelectPortfolio?.(portfolio.portfolio_id);
                                    setPortfolioChooserOpen(false);
                                  }}
                                  className={cn(
                                    "w-full rounded-xl border px-3 py-3 text-left transition",
                                    isSelected
                                      ? "border-primary/40 bg-primary/15 text-white shadow-[0_0_0_1px_rgba(236,72,153,0.25)]"
                                      : "border-white/8 bg-white/5 text-sidebar-foreground/80 hover:bg-white/10 hover:text-sidebar-foreground"
                                  )}
                                >
                                  <div className="truncate text-sm font-medium">{portfolio.portfolio_name}</div>
                                  <div className="mt-1 flex items-center gap-2 text-xs text-sidebar-foreground/50">
                                    <span>ID {portfolio.portfolio_id}</span>
                                    {portfolio.project_count !== undefined && <span>{portfolio.project_count} projects</span>}
                                  </div>
                                </button>
                              );
                            })}
                          </div>
                        </CollapsibleContent>
                      </Collapsible>
                    </div>
                  )}

                  {/* Project level */}
                  {level === "project" && (
                    <div className="space-y-3">
                      <div className="rounded-2xl border border-white/10 bg-white/5 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
                        <div className="mb-3 flex items-start justify-between gap-3">
                          <div>
                            <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-sidebar-foreground/50">
                              Active project
                            </div>
                            <div className="mt-2 text-base font-semibold leading-6 text-sidebar-foreground">
                              {selectedProject?.project_name || "Choose a project to start"}
                            </div>
                          </div>
                          <div className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-white/10 bg-white/10">
                            <img src={AGENT_IMAGE_SRC} alt="BUSINESSNEXT" className="h-full w-full object-contain p-1" />
                          </div>
                        </div>

                        {selectedProject ? (
                          <div className="space-y-3">
                            <div className="flex flex-wrap gap-2">
                              <Badge variant="outline" className="border-white/10 bg-white/5 text-sidebar-foreground/80">
                                ID {selectedProject.project_id}
                              </Badge>
                              {selectedProject.status && (
                                <Badge variant="outline" className="border-white/10 bg-white/5 text-sidebar-foreground/80">
                                  {selectedProject.status}
                                </Badge>
                              )}
                              {selectedProject.portfolio_name && (
                                <Badge variant="outline" className="border-white/10 bg-white/5 text-sidebar-foreground/80">
                                  {selectedProject.portfolio_name}
                                </Badge>
                              )}
                            </div>
                            <div className="rounded-xl border border-primary/20 bg-primary/10 px-3 py-2 text-xs leading-5 text-sidebar-foreground/80">
                              All use cases in this sidebar apply to the currently selected project context.
                            </div>
                            {currentUseCaseLabel && (
                              <div className="rounded-xl border border-emerald-400/20 bg-emerald-400/10 px-3 py-2">
                                <div className="text-[11px] uppercase tracking-[0.16em] text-emerald-200/80">Current activity</div>
                                <div className="mt-1 text-sm font-medium text-white">{currentUseCaseLabel}</div>
                              </div>
                            )}
                            {summaryError && (
                              <div className="rounded-xl border border-rose-400/20 bg-rose-500/10 px-3 py-3">
                                <div className="flex items-center justify-between gap-3">
                                  <div>
                                    <div className="text-[11px] uppercase tracking-[0.16em] text-rose-200/80">Summary issue</div>
                                    <div className="mt-1 text-sm text-white/90">{summaryError}</div>
                                  </div>
                                  {onRetrySummary && (
                                    <Button size="sm" variant="secondary" className="rounded-xl" onClick={onRetrySummary}>
                                      Retry
                                    </Button>
                                  )}
                                </div>
                              </div>
                            )}
                          </div>
                        ) : (
                          <div className="rounded-xl border border-dashed border-white/10 px-3 py-4 text-sm text-sidebar-foreground/60">
                            Select a project to unlock project-tied use cases and executive summary cards.
                          </div>
                        )}

                        {onEmployeeNameChange && (
                          <div className="mt-4 rounded-xl border border-white/10 bg-white/5 px-3 py-3">
                            <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.18em] text-sidebar-foreground/50">
                              Employee
                            </div>
                            <Input
                              value={employeeName ?? ""}
                              onChange={(e) => onEmployeeNameChange(e.target.value)}
                              list="employee-suggestions"
                              placeholder="Type your name (e.g. Mithilesh Tank)"
                              className="h-9 border-white/10 bg-white/5 text-sidebar-foreground placeholder:text-sidebar-foreground/40 focus-visible:ring-1 focus-visible:ring-offset-0"
                            />
                            <datalist id="employee-suggestions">
                              {employeeSuggestions.map((name) => (
                                <option key={name} value={name} />
                              ))}
                            </datalist>
                            <div className="mt-2 text-xs text-sidebar-foreground/50">
                              Shows allocated projects for the entered employee.
                            </div>
                          </div>
                        )}
                      </div>

                      <Collapsible open={projectChooserOpen} onOpenChange={setProjectChooserOpen}>
                        <CollapsibleTrigger className="flex w-full items-center justify-between rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-medium text-sidebar-foreground transition hover:bg-white/10">
                          <span>{selectedProject ? "Switch project" : "Browse projects"}</span>
                          <ChevronDown className={cn("h-4 w-4 transition-transform", projectChooserOpen && "rotate-180")} />
                        </CollapsibleTrigger>
                        <CollapsibleContent className="pt-3">
                          <div className="mb-2 flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2">
                            <Search className="h-4 w-4 text-sidebar-foreground/50" />
                            <Input
                              value={projectSearch}
                              onChange={(e) => setProjectSearch(e.target.value)}
                              placeholder="Search projects..."
                              className="h-8 border-0 bg-transparent px-0 text-sm text-sidebar-foreground placeholder:text-sidebar-foreground/40 focus-visible:ring-0 focus-visible:ring-offset-0"
                            />
                            {projectsLoading ? (
                              <span className="text-xs text-sidebar-foreground/50">Loading…</span>
                            ) : null}
                          </div>
                          <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
                            {!projectsLoading && projects.length === 0 ? (
                              <div className="rounded-xl border border-dashed border-white/10 px-3 py-4 text-sm text-sidebar-foreground/60">
                                No projects found.
                              </div>
                            ) : null}
                            {projects.map((project) => {
                              const isSelected = selectedProject?.project_id === project.project_id;
                              return (
                                <button
                                  key={project.project_id}
                                  onClick={() => {
                                    onSelectProject(project.project_id);
                                    setProjectChooserOpen(false);
                                  }}
                                  className={cn(
                                    "w-full rounded-xl border px-3 py-3 text-left transition",
                                    isSelected
                                      ? "border-primary/40 bg-primary/15 text-white shadow-[0_0_0_1px_rgba(236,72,153,0.25)]"
                                      : "border-white/8 bg-white/5 text-sidebar-foreground/80 hover:bg-white/10 hover:text-sidebar-foreground"
                                  )}
                                >
                                  <div className="truncate text-sm font-medium">{project.project_name}</div>
                                  <div className="mt-1 flex items-center gap-2 text-xs text-sidebar-foreground/50">
                                    <span>{project.project_id}</span>
                                    {project.status && <span>{project.status}</span>}
                                  </div>
                                </button>
                              );
                            })}
                          </div>
                        </CollapsibleContent>
                      </Collapsible>
                    </div>
                  )}
                </div>
              )}
            </SidebarGroupContent>
          </SidebarGroup>

          {level === "project" && selectedProject && !collapsed && (
            <SidebarGroup>
              <SidebarGroupLabel className="px-5 text-sidebar-foreground/60 text-xs uppercase tracking-[0.18em]">
                AI Workspace
              </SidebarGroupLabel>
              <SidebarGroupContent className="px-3">
                <div className="space-y-2">
                  {groupedCategories.map((group) => {
                    const GroupIcon = group.icon;
                    const activeInsideGroup = group.items.some((category) =>
                      category.useCases.some((useCase) => useCase.label === currentUseCaseLabel)
                    );

                    return (
                      <Collapsible
                        key={group.id}
                        open={openGroups[group.id] ?? activeInsideGroup}
                        onOpenChange={() => toggleGroup(group.id)}
                      >
                        <div
                          className={cn(
                            "rounded-2xl border transition",
                            activeInsideGroup
                              ? "border-primary/30 bg-primary/10 shadow-[0_0_0_1px_rgba(236,72,153,0.2)]"
                              : "border-white/8 bg-white/5 hover:bg-white/8"
                          )}
                        >
                          <CollapsibleTrigger className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left">
                            <div className="flex min-w-0 items-center gap-3">
                              <div className={cn(
                                "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl",
                                activeInsideGroup ? "bg-primary/20 text-primary" : "bg-white/8 text-sidebar-foreground/70"
                              )}>
                                <GroupIcon className="h-4 w-4" />
                              </div>
                              <div className="min-w-0">
                                <div className="truncate text-sm font-semibold text-sidebar-foreground">{group.label}</div>
                                <div className="text-xs text-sidebar-foreground/50">
                                  {group.items.reduce((count, category) => count + category.useCases.length, 0)} use cases
                                </div>
                              </div>
                            </div>
                            <ChevronRight className={cn("h-4 w-4 shrink-0 text-sidebar-foreground/50 transition-transform", (openGroups[group.id] ?? activeInsideGroup) && "rotate-90")} />
                          </CollapsibleTrigger>

                          <CollapsibleContent className="px-3 pb-3">
                            <div className="space-y-3 border-t border-white/8 pt-3">
                              {group.items.map((category) => {
                                const CategoryIcon = iconMap[category.icon] || LayoutDashboard;
                                const categoryHasActiveItem = category.useCases.some((useCase) => useCase.label === currentUseCaseLabel);

                                return (
                                  <div key={category.label} className="rounded-xl bg-black/10 px-3 py-3">
                                    <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-[0.14em] text-sidebar-foreground/55">
                                      <CategoryIcon className="h-3.5 w-3.5" />
                                      <span>{category.label}</span>
                                      {categoryHasActiveItem && (
                                        <Badge className="ml-auto border-primary/20 bg-primary/20 text-primary">Active</Badge>
                                      )}
                                    </div>
                                    <div className="space-y-1.5">
                                      {category.useCases.map((useCase) => {
                                        const isActive = currentUseCaseLabel === useCase.label;
                                        return (
                                          <button
                                            key={useCase.label}
                                            onClick={() => onSelectUseCase(useCase.prompt, useCase.label)}
                                            className={cn(
                                              "flex w-full items-start gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition",
                                              isActive
                                                ? "bg-primary text-primary-foreground shadow-sm"
                                                : "text-sidebar-foreground/75 hover:bg-white/10 hover:text-sidebar-foreground"
                                            )}
                                          >
                                            <span className={cn("mt-1 h-2 w-2 rounded-full", isActive ? "bg-white" : "bg-sidebar-foreground/30")} />
                                            <span className="leading-5">{useCase.label}</span>
                                          </button>
                                        );
                                      })}
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          </CollapsibleContent>
                        </div>
                      </Collapsible>
                    );
                  })}
                </div>
              </SidebarGroupContent>
            </SidebarGroup>
          )}

          {!collapsed && onOpenPanel && (
            <SidebarGroup>
              <SidebarGroupLabel className="px-5 text-sidebar-foreground/60 text-xs uppercase tracking-[0.18em]">
                Tools
              </SidebarGroupLabel>
              <SidebarGroupContent className="px-3">
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { label: "Documents", icon: Upload, panel: "documents" as const },
                    { label: "WSR Report", icon: FileBarChart, panel: "wsr" as const },
                    { label: "Meeting", icon: Mic, panel: "meeting" as const },
                    { label: "Downloads", icon: Download, panel: "downloads" as const },
                    { label: "Automation", icon: Zap, panel: "n8n-monitor" as const },
                  ].map(({ label, icon: Icon, panel }) => (
                    <button
                      key={panel}
                      onClick={() => onOpenPanel(panel)}
                      className="flex flex-col items-center gap-1.5 rounded-xl border border-white/10 bg-white/5 px-2 py-3 text-xs text-sidebar-foreground/75 transition hover:bg-white/10 hover:text-sidebar-foreground"
                    >
                      <Icon className="h-4 w-4" />
                      {label}
                    </button>
                  ))}
                </div>
                <button
                  onClick={() => navigate("/admin")}
                  className="mt-2 flex w-full items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-xs text-sidebar-foreground/75 transition hover:bg-white/10 hover:text-sidebar-foreground"
                >
                  <Shield className="h-4 w-4" />
                  Admin Dashboard
                </button>
              </SidebarGroupContent>
            </SidebarGroup>
          )}

          {!collapsed && conversations.length > 0 && (
            <SidebarGroup>
              <SidebarGroupLabel className="px-5 text-sidebar-foreground/60 text-xs uppercase tracking-[0.18em]">
                Recent Chats
              </SidebarGroupLabel>
              <SidebarGroupContent className="px-3">
                <SidebarMenu>
                  {conversations.map((conversation) => (
                    <SidebarMenuItem key={conversation.id}>
                      <TooltipProvider delayDuration={300}>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <SidebarMenuButton
                              onClick={() => onSelectConversation(conversation.id)}
                              className={cn(
                                "group justify-between rounded-xl px-3 py-2 text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                                activeConversationId === conversation.id && "bg-sidebar-accent text-sidebar-accent-foreground"
                              )}
                            >
                              <span className="flex items-center gap-2 truncate">
                                <MessageSquare className="h-3.5 w-3.5 shrink-0" />
                                <span className="truncate text-sm">{conversation.title}</span>
                              </span>
                              <button
                                onClick={(event) => {
                                  event.stopPropagation();
                                  onDeleteConversation(conversation.id);
                                }}
                                className="opacity-0 group-hover:opacity-100 hover:text-destructive transition-opacity"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            </SidebarMenuButton>
                          </TooltipTrigger>
                          <TooltipContent side="right" className="max-w-[300px] break-words">
                            {conversation.title}
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </SidebarMenuItem>
                  ))}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          )}
        </ScrollArea>

        <div className="border-t border-sidebar-border p-3 space-y-2">
          <Button
            onClick={onNewChat}
            variant="outline"
            className={cn(
              "w-full rounded-2xl border-sidebar-border bg-white text-slate-700 hover:bg-slate-100 hover:text-slate-900",
              collapsed && "px-0"
            )}
          >
            <Plus className="h-4 w-4" />
            {!collapsed && <span className="ml-2">{selectedProject ? "New project chat" : "New chat"}</span>}
          </Button>
          <Button
            onClick={() => navigate("/settings")}
            variant="ghost"
            className={cn(
              "w-full rounded-2xl text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
              collapsed && "px-0"
            )}
          >
            <Settings className="h-4 w-4" />
            {!collapsed && <span className="ml-2">Settings</span>}
          </Button>
        </div>
      </SidebarContent>
    </Sidebar>
  );
}
