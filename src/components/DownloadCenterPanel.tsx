import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Download, FileBarChart, Mic, Trash2 } from "lucide-react";
import type { GeneratedReport } from "./WSRReportPanel";
import type { MeetingReport } from "./MeetingSummaryPanel";

export type DownloadItem = (GeneratedReport | MeetingReport) & { id: string };

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  items: DownloadItem[];
  onRemove: (id: string) => void;
}

function downloadPdf(base64: string, filename: string) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  const blob = new Blob([bytes], { type: "application/pdf" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function downloadMarkdown(markdown: string, filename: string) {
  const blob = new Blob([markdown], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function safeFilename(name: string) {
  return name.replace(/[^a-zA-Z0-9_\- ]/g, "_").trim();
}

export function DownloadCenterPanel({ open, onOpenChange, items, onRemove }: Props) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-md flex flex-col gap-0 p-0">
        <SheetHeader className="px-5 pt-5 pb-3 border-b">
          <SheetTitle className="flex items-center gap-2">
            <Download className="h-5 w-5 text-blue-600" />
            Download Centre
          </SheetTitle>
        </SheetHeader>

        <ScrollArea className="flex-1 px-5 py-4">
          {items.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-40 gap-3 text-slate-400">
              <Download className="h-8 w-8 opacity-40" />
              <p className="text-sm">No reports generated yet this session.</p>
              <p className="text-xs text-center text-slate-300">Generate a WSR or meeting summary to see it here.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {items.map((item) => {
                const isWsr = item.type === "wsr";
                const wsr = isWsr ? (item as GeneratedReport) : null;
                const meeting = !isWsr ? (item as MeetingReport) : null;
                const name = safeFilename(item.name);

                return (
                  <div key={item.id} className="rounded-xl border border-slate-100 bg-white p-3 flex items-start gap-3">
                    <div className="mt-0.5 shrink-0">
                      {isWsr ? (
                        <FileBarChart className="h-5 w-5 text-blue-500" />
                      ) : (
                        <Mic className="h-5 w-5 text-purple-500" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-slate-700 truncate">{item.name}</p>
                      <p className="text-xs text-slate-400 mt-0.5">
                        {new Date(item.generatedAt).toLocaleString()}
                      </p>
                      <div className="flex gap-2 mt-2 flex-wrap">
                        <Badge variant="outline" className="text-[10px]">
                          {isWsr ? "WSR" : "Meeting"}
                        </Badge>
                        {wsr?.pdfBase64 && (
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-6 text-xs rounded-lg px-2"
                            onClick={() => downloadPdf(wsr.pdfBase64!, `${name}.pdf`)}
                          >
                            <Download className="h-3 w-3 mr-1" />
                            PDF
                          </Button>
                        )}
                        {wsr?.html && (
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-6 text-xs rounded-lg px-2"
                            onClick={() => {
                              const blob = new Blob([wsr.html], { type: "text/html" });
                              const url = URL.createObjectURL(blob);
                              const a = document.createElement("a");
                              a.href = url; a.download = `${name}.html`; a.click();
                              URL.revokeObjectURL(url);
                            }}
                          >
                            HTML
                          </Button>
                        )}
                        {meeting?.markdown && (
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-6 text-xs rounded-lg px-2"
                            onClick={() => downloadMarkdown(meeting.markdown, `${name}.md`)}
                          >
                            <Download className="h-3 w-3 mr-1" />
                            Markdown
                          </Button>
                        )}
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="shrink-0 h-7 w-7 text-slate-300 hover:text-red-400"
                      onClick={() => onRemove(item.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                );
              })}
            </div>
          )}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
