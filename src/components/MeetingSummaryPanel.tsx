import { useRef, useState } from "react";
import { apiCall, getApiBaseUrl } from "@/lib/apiClient";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { toast } from "sonner";
import { Mic, FileText, Loader2, CheckCircle2, Users, TriangleAlert, ClipboardList } from "lucide-react";

export interface MeetingReport {
  id: string;
  name: string;
  type: "meeting";
  markdown: string;
  generatedAt: string;
}

interface ActionItem {
  owner: string;
  description: string;
  due_date: string | null;
  priority: "high" | "medium" | "low";
}

interface Decision {
  description: string;
  owner: string | null;
}

interface Risk {
  description: string;
  severity: "high" | "medium" | "low";
  mitigation: string | null;
}

interface Intel {
  summary: string;
  action_items: ActionItem[];
  decisions: Decision[];
  risks: Risk[];
  participants: string[];
  transcript?: string;
}

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onReportGenerated?: (report: MeetingReport) => void;
}

const PRIORITY_COLOR: Record<string, string> = {
  high: "bg-red-100 text-red-700 border-red-200",
  medium: "bg-amber-100 text-amber-700 border-amber-200",
  low: "bg-green-100 text-green-700 border-green-200",
};

function intelToMarkdown(intel: Intel, tab: "audio" | "text"): string {
  const lines: string[] = [];
  if (intel.summary) lines.push(`## Summary\n${intel.summary}`);
  if (intel.action_items?.length) {
    lines.push("\n## Action Items");
    intel.action_items.forEach((a) =>
      lines.push(`- **${a.owner ?? "?"}**: ${a.description} _(due: ${a.due_date ?? "TBD"}, priority: ${a.priority ?? "?"})_`)
    );
  }
  if (intel.decisions?.length) {
    lines.push("\n## Decisions");
    intel.decisions.forEach((d) => lines.push(`- ${d.description}`));
  }
  if (intel.risks?.length) {
    lines.push("\n## Risks");
    intel.risks.forEach((r) =>
      lines.push(`- [${r.severity ?? "?"}] ${r.description} — ${r.mitigation ?? "no mitigation noted"}`)
    );
  }
  if (intel.participants?.length) {
    lines.push(`\n## Participants\n${intel.participants.join(", ")}`);
  }
  return lines.join("\n");
}

export function MeetingSummaryPanel({ open, onOpenChange, onReportGenerated }: Props) {
  const [tab, setTab] = useState<"audio" | "text">("text");
  const [transcript, setTranscript] = useState("");
  const [intel, setIntel] = useState<Intel | null>(null);
  const [loading, setLoading] = useState(false);
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const analyzeText = async () => {
    if (!transcript.trim()) { toast.error("Paste a transcript first."); return; }
    setLoading(true);
    const { data, error } = await apiCall("speech/analyze", { transcript });
    setLoading(false);
    if (error || !data?.ok) { toast.error(error?.message || data?.error || "Analysis failed"); return; }
    setIntel(data);
    emitReport(data, "text");
  };

  const analyzeAudio = async () => {
    if (!audioFile) { toast.error("Select an audio file first."); return; }
    setLoading(true);
    const form = new FormData();
    form.append("file", audioFile);
    try {
      const resp = await fetch(`${getApiBaseUrl()}/speech/transcribe-and-analyze`, { method: "POST", body: form });
      const data = await resp.json();
      if (!data.ok) { toast.error(data.error || "Analysis failed"); setLoading(false); return; }
      setIntel(data);
      if (data.transcript) setTranscript(data.transcript);
      emitReport(data, "audio");
    } catch { toast.error("Request failed"); }
    finally { setLoading(false); }
  };

  const emitReport = (data: Intel, source: "audio" | "text") => {
    const md = intelToMarkdown(data, source);
    onReportGenerated?.({
      id: crypto.randomUUID(),
      name: `Meeting Summary — ${new Date().toLocaleDateString()}`,
      type: "meeting",
      markdown: md,
      generatedAt: new Date().toISOString(),
    });
    toast.success("Meeting intelligence extracted");
  };

  const copyMarkdown = () => {
    if (!intel) return;
    navigator.clipboard.writeText(intelToMarkdown(intel, tab));
    toast.success("Copied to clipboard");
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl h-[90vh] flex flex-col p-0 gap-0">
        <DialogHeader className="px-6 pt-5 pb-3 border-b shrink-0">
          <DialogTitle className="flex items-center gap-2">
            <Mic className="h-5 w-5 text-blue-600" />
            Meeting Intelligence
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-1 min-h-0 divide-x">
          {/* Left: input */}
          <div className="w-[44%] flex flex-col min-h-0">
            <Tabs value={tab} onValueChange={(v) => setTab(v as "audio" | "text")} className="flex flex-col flex-1 min-h-0">
              <TabsList className="mx-4 mt-3 shrink-0 w-fit">
                <TabsTrigger value="text"><FileText className="h-3.5 w-3.5 mr-1" />Transcript</TabsTrigger>
                <TabsTrigger value="audio"><Mic className="h-3.5 w-3.5 mr-1" />Audio File</TabsTrigger>
              </TabsList>

              <TabsContent value="text" className="flex-1 flex flex-col min-h-0 px-4 pb-4 pt-3 gap-3">
                <p className="text-xs text-slate-500">Paste a meeting transcript. The AI will extract action items, decisions, and risks.</p>
                <Textarea
                  value={transcript}
                  onChange={(e) => setTranscript(e.target.value)}
                  placeholder="Paste meeting transcript here…"
                  className="flex-1 min-h-0 resize-none rounded-xl text-sm leading-relaxed"
                />
                <Button className="rounded-xl bg-blue-700 hover:bg-blue-800 shrink-0" onClick={analyzeText} disabled={loading || !transcript.trim()}>
                  {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
                  {loading ? "Analyzing…" : "Extract Intelligence"}
                </Button>
              </TabsContent>

              <TabsContent value="audio" className="flex-1 flex flex-col min-h-0 px-4 pb-4 pt-3 gap-3">
                <p className="text-xs text-slate-500">Upload a meeting recording. The server transcribes it, then extracts structured insights.</p>
                <div
                  onClick={() => fileRef.current?.click()}
                  className="flex flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-slate-200 bg-slate-50 p-8 cursor-pointer hover:border-blue-400 hover:bg-blue-50/50 transition-colors"
                >
                  <Mic className="h-8 w-8 text-slate-400" />
                  {audioFile ? (
                    <p className="text-sm font-medium text-slate-700">{audioFile.name}</p>
                  ) : (
                    <p className="text-sm text-slate-500">Click to select audio file</p>
                  )}
                  <p className="text-xs text-slate-400">MP3, MP4, M4A, WAV, WebM</p>
                  <input
                    ref={fileRef}
                    type="file"
                    accept="audio/*,.webm,.mp3,.mp4,.m4a,.wav,.ogg"
                    className="hidden"
                    onChange={(e) => setAudioFile(e.target.files?.[0] || null)}
                  />
                </div>
                <Button className="rounded-xl bg-blue-700 hover:bg-blue-800 shrink-0" onClick={analyzeAudio} disabled={loading || !audioFile}>
                  {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
                  {loading ? "Transcribing & analyzing…" : "Transcribe & Analyze"}
                </Button>
              </TabsContent>
            </Tabs>
          </div>

          {/* Right: results */}
          <div className="flex-1 flex flex-col min-h-0">
            <div className="px-4 pt-4 pb-2 shrink-0 flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Intelligence Output</span>
              {intel && (
                <Button variant="ghost" size="sm" className="rounded-xl text-xs h-7" onClick={copyMarkdown}>
                  Copy as Markdown
                </Button>
              )}
            </div>
            <ScrollArea className="flex-1 px-4 pb-4">
              {!intel && !loading && (
                <div className="flex flex-col items-center justify-center h-40 text-slate-400 text-sm gap-2">
                  <Mic className="h-8 w-8 opacity-40" />
                  <p>Output will appear here after analysis</p>
                </div>
              )}
              {loading && (
                <div className="flex items-center gap-2 text-blue-600 text-sm py-6 justify-center">
                  <Loader2 className="h-5 w-5 animate-spin" />
                  Processing…
                </div>
              )}
              {intel && (
                <div className="space-y-5">
                  {/* Summary */}
                  {intel.summary && (
                    <div className="rounded-xl bg-slate-50 border border-slate-100 p-3">
                      <p className="text-xs font-semibold text-slate-500 uppercase mb-1">Summary</p>
                      <p className="text-sm text-slate-700 leading-relaxed">{intel.summary}</p>
                    </div>
                  )}

                  {/* Participants */}
                  {intel.participants?.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold text-slate-500 uppercase mb-2 flex items-center gap-1">
                        <Users className="h-3.5 w-3.5" /> Participants
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {intel.participants.map((p, i) => (
                          <Badge key={i} variant="secondary" className="text-xs">{p}</Badge>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Action Items */}
                  {intel.action_items?.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold text-slate-500 uppercase mb-2 flex items-center gap-1">
                        <ClipboardList className="h-3.5 w-3.5" /> Action Items ({intel.action_items.length})
                      </p>
                      <div className="space-y-2">
                        {intel.action_items.map((a, i) => (
                          <div key={i} className="rounded-xl border border-slate-100 bg-white p-2.5 text-xs">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="font-semibold text-slate-700">{a.owner || "?"}</span>
                              <Badge className={`text-[10px] border ${PRIORITY_COLOR[a.priority] || PRIORITY_COLOR.low}`}>
                                {a.priority}
                              </Badge>
                              {a.due_date && <span className="text-slate-400 ml-auto">Due {a.due_date}</span>}
                            </div>
                            <p className="text-slate-600 leading-relaxed">{a.description}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Decisions */}
                  {intel.decisions?.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold text-slate-500 uppercase mb-2 flex items-center gap-1">
                        <CheckCircle2 className="h-3.5 w-3.5" /> Decisions ({intel.decisions.length})
                      </p>
                      <div className="space-y-1.5">
                        {intel.decisions.map((d, i) => (
                          <div key={i} className="rounded-xl border border-slate-100 bg-white p-2.5 text-xs text-slate-600 leading-relaxed">
                            {d.description}
                            {d.owner && <span className="ml-2 text-slate-400">— {d.owner}</span>}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Risks */}
                  {intel.risks?.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold text-slate-500 uppercase mb-2 flex items-center gap-1">
                        <TriangleAlert className="h-3.5 w-3.5" /> Risks ({intel.risks.length})
                      </p>
                      <div className="space-y-1.5">
                        {intel.risks.map((r, i) => (
                          <div key={i} className="rounded-xl border border-slate-100 bg-white p-2.5 text-xs">
                            <div className="flex items-center gap-2 mb-1">
                              <Badge className={`text-[10px] border ${PRIORITY_COLOR[r.severity] || PRIORITY_COLOR.low}`}>
                                {r.severity}
                              </Badge>
                            </div>
                            <p className="text-slate-600">{r.description}</p>
                            {r.mitigation && <p className="text-slate-400 mt-1 italic">↳ {r.mitigation}</p>}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </ScrollArea>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

