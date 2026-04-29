import { useState } from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TableIcon, LayoutGrid, Download } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ProjectRecord {
  project_id: string;
  project_name: string;
  status: string;
  go_live_date: string | null;
  portfolio_name: string | null;
  portfolio_owner: string | null;
  account_name: string | null;
  project_manager: string | null;
}

interface ProjectResultsTableProps {
  projects: ProjectRecord[];
  filters?: Record<string, string | null>;
  onProjectClick?: (project: ProjectRecord) => void;
}

const statusColor = (status: string) => {
  const normalizedStatus = status.toLowerCase();
  if (normalizedStatus === "active") return "bg-emerald-500/15 text-emerald-700 border-emerald-200";
  if (normalizedStatus === "completed") return "bg-blue-500/15 text-blue-700 border-blue-200";
  if (normalizedStatus === "delayed") return "bg-red-500/15 text-red-700 border-red-200";
  if (normalizedStatus === "in progress") return "bg-amber-500/15 text-amber-700 border-amber-200";
  if (normalizedStatus === "on hold") return "bg-gray-500/15 text-gray-600 border-gray-200";
  return "bg-muted text-muted-foreground";
};

function exportCSV(projects: ProjectRecord[]) {
  const headers = ["Project ID", "Project Name", "Status", "Go Live Date", "Portfolio", "Portfolio Owner", "Account", "Project Manager"];
  const rows = projects.map((project) => [
    project.project_id,
    project.project_name,
    project.status,
    project.go_live_date || "",
    project.portfolio_name || "",
    project.portfolio_owner || "",
    project.account_name || "",
    project.project_manager || "",
  ]);
  const csv = [headers.join(","), ...rows.map((row) => row.map((cell) => `"${cell}"`).join(","))].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "projects.csv";
  anchor.click();
  URL.revokeObjectURL(url);
}

export function ProjectResultsTable({ projects, filters, onProjectClick }: ProjectResultsTableProps) {
  const [view, setView] = useState<"table" | "card">("table");
  const handleProjectSelect = (project: ProjectRecord) => {
    onProjectClick?.(project);
  };

  if (projects.length === 0) {
    return (
      <div className="text-center py-6 text-muted-foreground text-sm">
        No projects found matching your criteria.
      </div>
    );
  }

  const activeFilters = filters
    ? Object.entries(filters).filter(([, value]) => value != null && value !== "")
    : [];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex flex-wrap gap-1.5">
          {activeFilters.map(([key, value]) => (
            <Badge key={key} variant="secondary" className="text-xs">
              {key.replace(/_/g, " ")}: {value}
            </Badge>
          ))}
          <Badge variant="outline" className="text-xs">{projects.length} result{projects.length !== 1 ? "s" : ""}</Badge>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setView("table")} title="Table view">
            <TableIcon className={cn("h-4 w-4", view === "table" ? "text-primary" : "text-muted-foreground")} />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setView("card")} title="Card view">
            <LayoutGrid className={cn("h-4 w-4", view === "card" ? "text-primary" : "text-muted-foreground")} />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => exportCSV(projects)} title="Export CSV">
            <Download className="h-4 w-4 text-muted-foreground" />
          </Button>
        </div>
      </div>

      {view === "table" ? (
        <div className="rounded-lg border overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-xs">Project ID</TableHead>
                <TableHead className="text-xs">Project Name</TableHead>
                <TableHead className="text-xs">Status</TableHead>
                <TableHead className="text-xs">Go Live</TableHead>
                <TableHead className="text-xs">Portfolio</TableHead>
                <TableHead className="text-xs">Owner</TableHead>
                <TableHead className="text-xs">Account</TableHead>
                <TableHead className="text-xs">PM</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {projects.map((project) => (
                <TableRow
                  key={project.project_id}
                  onClick={() => handleProjectSelect(project)}
                  className="cursor-pointer hover:bg-muted transition"
                >
                  <TableCell className="text-xs font-mono">{project.project_id}</TableCell>
                  <TableCell className="text-xs font-medium">{project.project_name}</TableCell>
                  <TableCell>
                    <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium border", statusColor(project.status))}>
                      {project.status}
                    </span>
                  </TableCell>
                  <TableCell className="text-xs">{project.go_live_date || "-"}</TableCell>
                  <TableCell className="text-xs">{project.portfolio_name || "-"}</TableCell>
                  <TableCell className="text-xs">{project.portfolio_owner || "-"}</TableCell>
                  <TableCell className="text-xs">{project.account_name || "-"}</TableCell>
                  <TableCell className="text-xs">{project.project_manager || "-"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {projects.map((project) => (
            <div
              key={project.project_id}
              onClick={() => handleProjectSelect(project)}
              className="cursor-pointer"
            >
              <Card className="text-sm hover:shadow-md hover:scale-[1.01] hover:bg-muted/50 transition">
                <CardHeader className="pb-2 pt-4 px-4">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm font-semibold">
                      {project.project_name}
                    </CardTitle>
                    <span
                      className={cn(
                        "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium border",
                        statusColor(project.status)
                      )}
                    >
                      {project.status}
                    </span>
                  </div>
                </CardHeader>

                <CardContent className="px-4 pb-4 pt-0 space-y-1 text-xs text-muted-foreground">
                  <p><span className="font-medium text-foreground">ID:</span> {project.project_id}</p>
                  <p><span className="font-medium text-foreground">Go Live:</span> {project.go_live_date || "-"}</p>
                  <p><span className="font-medium text-foreground">Portfolio:</span> {project.portfolio_name || "-"} ({project.portfolio_owner || "-"})</p>
                  <p><span className="font-medium text-foreground">Account:</span> {project.account_name || "-"}</p>
                  <p><span className="font-medium text-foreground">PM:</span> {project.project_manager || "-"}</p>
                </CardContent>
              </Card>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
