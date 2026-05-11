import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { TimesheetPromptPlan } from "@/lib/timesheetPrompt";

function timeframeLabel(plan: TimesheetPromptPlan) {
  if (plan.timeframe.kind === "single") return plan.timeframe.dateISO;
  return `${plan.timeframe.label} (${plan.timeframe.datesISO.length} workdays)`;
}

export function TimesheetPromptDialog({
  open,
  onOpenChange,
  plan,
  employeeName,
  projectLabel,
  options,
  onPlanChange,
  onConfirm,
  confirming,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  plan: TimesheetPromptPlan;
  employeeName: string;
  projectLabel: string;
  options?: { items: string[] } | null;
  onPlanChange: (next: TimesheetPromptPlan) => void;
  onConfirm: () => void;
  confirming?: boolean;
}) {
  const hours = (plan.effort_minutes / 60).toFixed(2);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-w-2xl h-[86vh] min-h-0 flex-col rounded-3xl p-0">
        <div className="p-6 pb-4">
          <DialogHeader>
            <DialogTitle>Confirm timesheet entry</DialogTitle>
            <DialogDescription>
              Review the detected inputs. Confirm will create timesheet rows in the database.
            </DialogDescription>
          </DialogHeader>
        </div>

        <ScrollArea className="flex-1 min-h-0 px-6">
          <div className="grid gap-4 pb-6 md:grid-cols-2">
          <div className="space-y-2">
            <div className="text-sm font-medium">Employee</div>
            <Input value={employeeName} disabled />
          </div>
          <div className="space-y-2">
            <div className="text-sm font-medium">Project</div>
            <Input value={projectLabel} disabled />
          </div>
          <div className="space-y-2">
            <div className="text-sm font-medium">Timeframe</div>
            <Input value={timeframeLabel(plan)} disabled />
          </div>
          <div className="space-y-2">
            <div className="text-sm font-medium">Effort</div>
            <Input
              value={String(plan.effort_minutes)}
              onChange={(e) => onPlanChange({ ...plan, effort_minutes: Number(e.target.value || 0) })}
              type="number"
              min={0}
              step={15}
            />
            <div className="text-xs text-muted-foreground">{hours} hours</div>
          </div>
          <div className="space-y-2">
            <div className="text-sm font-medium">Category</div>
            <Input value={plan.category ?? ""} onChange={(e) => onPlanChange({ ...plan, category: e.target.value })} placeholder="Development / Leave / ..." />
          </div>
          <div className="space-y-2">
            <div className="text-sm font-medium">Item</div>
            {options?.items?.length ? (
              <Select
                value={plan.item ?? ""}
                onValueChange={(value) =>
                  onPlanChange({
                    ...plan,
                    item: value,
                    category: (plan.category ?? "").trim() ? plan.category : value,
                  })
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select item" />
                </SelectTrigger>
                <SelectContent>
                  {options.items.map((opt) => (
                    <SelectItem key={opt} value={opt}>
                      {opt}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <Input value={plan.item ?? ""} onChange={(e) => onPlanChange({ ...plan, item: e.target.value })} placeholder="Config / Development / ..." />
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <div className="text-sm font-medium">Start</div>
              <Input value={plan.start_time ?? "09:00"} onChange={(e) => onPlanChange({ ...plan, start_time: e.target.value })} type="time" />
            </div>
            <div className="space-y-2">
              <div className="text-sm font-medium">End</div>
              <Input value={plan.end_time ?? "17:00"} onChange={(e) => onPlanChange({ ...plan, end_time: e.target.value })} type="time" />
            </div>
          </div>
          <div className="space-y-2">
            <div className="text-sm font-medium">Related to</div>
            <Input value={plan.related_to ?? ""} onChange={(e) => onPlanChange({ ...plan, related_to: e.target.value })} placeholder="Project Module" />
          </div>
          <div className="space-y-2">
            <div className="text-sm font-medium">Role</div>
            <Input value={plan.engagement_role ?? ""} onChange={(e) => onPlanChange({ ...plan, engagement_role: e.target.value })} placeholder="Technical Consultant" />
          </div>
          <div className="space-y-2">
            <div className="text-sm font-medium">Location</div>
            <Input value={plan.engagement_location ?? ""} onChange={(e) => onPlanChange({ ...plan, engagement_location: e.target.value })} placeholder="Offsite" />
          </div>
          <div className="space-y-2 md:col-span-2">
            <div className="text-sm font-medium">Description</div>
            <Textarea
              value={plan.description ?? ""}
              onChange={(e) => onPlanChange({ ...plan, description: e.target.value })}
              className="min-h-[90px] rounded-2xl"
              placeholder="What did you work on?"
            />
          </div>
          </div>
        </ScrollArea>

        <DialogFooter className="gap-2 border-t bg-background/80 p-4 backdrop-blur-sm sm:gap-0">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={Boolean(confirming)}>
            Cancel
          </Button>
          <Button onClick={onConfirm} disabled={Boolean(confirming) || !plan.effort_minutes}>
            {confirming ? "Filling..." : "Confirm & Fill"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
