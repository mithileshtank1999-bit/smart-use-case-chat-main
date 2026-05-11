import { useEffect, useMemo, useState } from "react";
import { apiCall } from "@/lib/apiClient";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { toast } from "sonner";

type ProjectOption = {
  project_id: string;
  project_name: string;
  status?: string | null;
};

type TimesheetTemplate = {
  timesheetid: number;
  subject?: string | null;
  relatedtoname?: string | null;
  effort?: number | string | null;
  projecttaskid?: number | null;
  engagementroleid?: number | null;
  engagementlocationid?: number | null;
  start_time?: string | null;
  end_time?: string | null;
};

const roleLabels: Record<string, string> = {
  "1": "Role 1",
  "2": "Technical Consultant",
  "100014": "Role 100014",
};

const locationLabels: Record<string, string> = {
  "1": "Onsite",
  "2": "Offsite",
};

function todayISO(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export function TimesheetDialog({
  open,
  onOpenChange,
  projects,
  selectedProjectId,
  employeeName,
  onEmployeeNameChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projects: ProjectOption[];
  selectedProjectId?: string | null;
  employeeName: string;
  onEmployeeNameChange: (value: string) => void;
}) {
  const [projectId, setProjectId] = useState<string>(selectedProjectId ?? "");
  const [workDate, setWorkDate] = useState<string>(todayISO());
  const [startTime, setStartTime] = useState("09:00");
  const [endTime, setEndTime] = useState("17:00");
  const [effortMinutes, setEffortMinutes] = useState(480);
  const [description, setDescription] = useState("SDG development");
  const [item, setItem] = useState("Config");
  const [engagementRoleId, setEngagementRoleId] = useState<string>("2");
  const [engagementLocationId, setEngagementLocationId] = useState<string>("2");
  const [templateId, setTemplateId] = useState<string>("");
  const [quickCommand, setQuickCommand] = useState<string>("");

  const [options, setOptions] = useState<{ items: string[]; engagementroleids: number[]; engagementlocationids: number[] } | null>(null);
  const [templates, setTemplates] = useState<TimesheetTemplate[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [schemaHint, setSchemaHint] = useState<string>("");

  const selectedProject = useMemo(
    () => projects.find((p) => p.project_id === projectId) ?? null,
    [projects, projectId],
  );

  useEffect(() => {
    if (!open) return;
    setProjectId(selectedProjectId ?? "");
    setWorkDate(todayISO());
    setQuickCommand("");
  }, [open, selectedProjectId]);

  useEffect(() => {
    if (!open || !projectId) return;
    (async () => {
      const { data, error } = await apiCall("timesheet/options", undefined, { method: "GET", query: { project_id: projectId } });
      if (!error && data?.ok) setOptions(data.options);
    })();
  }, [open, projectId]);

  useEffect(() => {
    if (!open) return;
    setSchemaHint("");
    (async () => {
      const { data, error } = await apiCall("timesheet/schema", undefined, { method: "GET" });
      if (error || !data?.ok) return;
      const t = data?.tables?.timesheet;
      if (t?.ok && t?.schema && t?.table) setSchemaHint(`Using ${t.schema}.${t.table}`);
    })();
  }, [open]);

  const refreshTemplates = async () => {
    if (!employeeName.trim() || !projectId) return;
    const { data, error } = await apiCall("timesheet/templates", undefined, {
      method: "GET",
      query: { employee_name: employeeName.trim(), project_id: projectId, limit: "10" },
    });
    if (!error && data?.ok && Array.isArray(data.results)) {
      setTemplates(data.results as TimesheetTemplate[]);
    }
  };

  useEffect(() => {
    if (!open) return;
    refreshTemplates();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, projectId, employeeName]);

  useEffect(() => {
    if (!templateId) return;
    const t = templates.find((x) => String(x.timesheetid) === templateId);
    if (!t) return;
    if (t.subject) setDescription(t.subject);
    if (t.relatedtoname) setItem(t.relatedtoname);
    const effort = Number(t.effort ?? 480);
    if (!Number.isNaN(effort)) setEffortMinutes(effort);
    if (t.engagementroleid != null) setEngagementRoleId(String(t.engagementroleid));
    if (t.engagementlocationid != null) setEngagementLocationId(String(t.engagementlocationid));
    if (t.start_time) setStartTime(String(t.start_time).slice(0, 5));
    if (t.end_time) setEndTime(String(t.end_time).slice(0, 5));
  }, [templateId, templates]);

  const canSubmit = employeeName.trim() && projectId && workDate && startTime && endTime;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setIsLoading(true);
    try {
      if (quickCommand.trim()) {
        const { data, error } = await apiCall("timesheet/command", {
          project_id: Number(projectId),
          employee_name: employeeName.trim(),
          command: quickCommand.trim(),
        });
        if (error) {
          toast.error(error.message || "Failed to run timesheet command.");
          return;
        }
        if (!data?.ok) {
          toast.error(data?.message || data?.error || "Failed to run timesheet command.");
          return;
        }
        if (data?.already_exists) {
          toast.message(`Timesheet already exists (ID ${data.timesheetid}).`);
          return;
        }
        toast.success(`Timesheet filled${selectedProject ? ` — ${selectedProject.project_name}` : ""}.`);
        await refreshTemplates();
        onOpenChange(false);
        return;
      }

      const payload: any = {
        project_id: Number(projectId),
        employee_name: employeeName.trim(),
        work_date: workDate,
        start_time: startTime,
        end_time: endTime,
        effort_minutes: effortMinutes,
        description,
        item,
        engagementroleid: Number(engagementRoleId),
        engagementlocationid: Number(engagementLocationId),
      };
      if (templateId) payload.template_timesheetid = Number(templateId);

      const { data, error } = await apiCall("timesheet/fill", payload);
      if (error) {
        toast.error(error.message || "Failed to fill timesheet.");
        return;
      }
      if (data?.already_exists) {
        toast.message(`Timesheet already exists for ${workDate} (ID ${data.timesheetid}).`);
        return;
      }
      toast.success(`Timesheet filled for ${workDate}${selectedProject ? ` — ${selectedProject.project_name}` : ""}.`);
      await refreshTemplates();
      onOpenChange(false);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-w-2xl h-[86vh] min-h-0 flex-col rounded-3xl p-0">
        <div className="p-6 pb-4">
          <DialogHeader>
            <DialogTitle>Fill Timesheet</DialogTitle>
            <DialogDescription>
              Fill an 8-hour entry for the selected project. After the first entry, use history and just change the date.
            </DialogDescription>
          </DialogHeader>
          {schemaHint ? <div className="mt-1 text-xs text-muted-foreground">{schemaHint}</div> : null}
        </div>

        <ScrollArea className="flex-1 min-h-0 px-6">
          <div className="grid gap-4 pb-6 md:grid-cols-2">
          <div className="space-y-2 md:col-span-2">
            <div className="text-sm font-medium">Quick command (optional)</div>
            <Input
              value={quickCommand}
              onChange={(e) => setQuickCommand(e.target.value)}
              placeholder='e.g. today 8h item=Config desc="SDG development" template=12345'
            />
            <div className="text-xs text-muted-foreground">
              When set, this runs server-side parsing + validation for accuracy.
            </div>
          </div>
          <div className="space-y-2">
            <div className="text-sm font-medium">Employee name</div>
            <Input value={employeeName} onChange={(e) => onEmployeeNameChange(e.target.value)} placeholder="Mithilesh Tank" />
          </div>
          <div className="space-y-2">
            <div className="text-sm font-medium">Project</div>
            <Select value={projectId} onValueChange={setProjectId}>
              <SelectTrigger>
                <SelectValue placeholder="Select project" />
              </SelectTrigger>
              <SelectContent>
                {projects.map((p) => (
                  <SelectItem key={p.project_id} value={p.project_id}>
                    {p.project_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <div className="text-sm font-medium">Date</div>
            <Input type="date" value={workDate} onChange={(e) => setWorkDate(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <div className="text-sm font-medium">Start</div>
              <Input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} />
            </div>
            <div className="space-y-2">
              <div className="text-sm font-medium">End</div>
              <Input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} />
            </div>
          </div>

          <div className="space-y-2">
            <div className="text-sm font-medium">Category</div>
            <Select value="development" onValueChange={() => {}}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="development">Development</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <div className="text-sm font-medium">Effort (minutes)</div>
            <Input
              type="number"
              value={String(effortMinutes)}
              onChange={(e) => setEffortMinutes(Number(e.target.value || 0))}
              min={0}
              step={15}
            />
          </div>

          <div className="space-y-2 md:col-span-2">
            <div className="text-sm font-medium">Description</div>
            <Input value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>

          <div className="space-y-2">
            <div className="text-sm font-medium">Related to</div>
            <Select value="project_module" onValueChange={() => {}}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="project_module">Project Module</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <div className="text-sm font-medium">Item</div>
            <Select value={item} onValueChange={setItem}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(options?.items?.length ? options.items : ["Config"]).map((x) => (
                  <SelectItem key={x} value={x}>
                    {x}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <div className="text-sm font-medium">Engagement role</div>
            <Select value={engagementRoleId} onValueChange={setEngagementRoleId}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(options?.engagementroleids?.length ? options.engagementroleids : [2]).map((id) => (
                  <SelectItem key={id} value={String(id)}>
                    {roleLabels[String(id)] ?? `Role ${id}`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <div className="text-sm font-medium">Engagement location</div>
            <Select value={engagementLocationId} onValueChange={setEngagementLocationId}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(options?.engagementlocationids?.length ? options.engagementlocationids : [2]).map((id) => (
                  <SelectItem key={id} value={String(id)}>
                    {locationLabels[String(id)] ?? `Location ${id}`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2 md:col-span-2">
            <div className="text-sm font-medium">History (use previous entry)</div>
            <Select value={templateId} onValueChange={setTemplateId}>
              <SelectTrigger>
                <SelectValue placeholder="Select a previous timesheet entry" />
              </SelectTrigger>
              <SelectContent>
                {templates.map((t) => (
                  <SelectItem key={t.timesheetid} value={String(t.timesheetid)}>
                    {t.subject || "Timesheet"} — {t.relatedtoname || "Item"} ({t.effort ?? 0}m)
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {!templates.length ? (
              <div className="text-xs text-amber-700">
                No previous entries found for this project. For 100% accuracy, create one entry in the portal first (or ask an admin for a template timesheet id).
              </div>
            ) : null}
          </div>
        </div>
        </ScrollArea>

        <DialogFooter className="gap-2 border-t bg-background/80 p-4 backdrop-blur-sm sm:gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} className="rounded-2xl">
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!canSubmit || isLoading} className="rounded-2xl">
            {isLoading ? "Filling…" : "Fill Timesheet"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
