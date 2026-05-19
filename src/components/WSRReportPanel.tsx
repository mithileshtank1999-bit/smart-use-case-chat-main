import { useEffect, useRef, useState } from "react";
import { apiCall } from "@/lib/apiClient";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { Download, FileBarChart, Loader2, Eye, Send } from "lucide-react";

export interface GeneratedReport {
  id: string;
  name: string;
  type: "wsr";
  html: string;
  pdfBase64: string | null;
  generatedAt: string;
}

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  defaultProjectName?: string;
  onReportGenerated?: (report: GeneratedReport) => void;
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

export function WSRReportPanel({ open, onOpenChange, defaultProjectName, onReportGenerated }: Props) {
  const [tab, setTab] = useState<"paste" | "preview">("paste");
  const [rawText, setRawText] = useState("");
  const [loading, setLoading] = useState(false);
  const [html, setHtml] = useState<string | null>(null);
  const [pdfBase64, setPdfBase64] = useState<string | null>(null);
  const [projectName, setProjectName] = useState(defaultProjectName || "");
  const [recipients, setRecipients] = useState("");
  const [sending, setSending] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const blobUrlRef = useRef<string | null>(null);

  useEffect(() => {
    if (defaultProjectName) setProjectName(defaultProjectName);
  }, [defaultProjectName]);

  useEffect(() => {
    if (!open) {
      // cleanup blob URL
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current);
        blobUrlRef.current = null;
      }
    }
  }, [open]);

  const generate = async () => {
    if (!rawText.trim()) {
      toast.error("Paste your WSR notes first.");
      return;
    }
    setLoading(true);
    const { data, error } = await apiCall("reports/wsr/from-text", { text: rawText, send_email: false });
    setLoading(false);
    if (error || !data?.ok) {
      toast.error(error?.message || data?.error || "Generation failed");
      return;
    }
    setHtml(data.html);
    setPdfBase64(data.pdf_base64 || null);
    setTab("preview");

    const id = crypto.randomUUID();
    onReportGenerated?.({
      id,
      name: `${data.project_name || "WSR"} — ${data.reporting_period || ""}`.trim(),
      type: "wsr",
      html: data.html,
      pdfBase64: data.pdf_base64 || null,
      generatedAt: new Date().toISOString(),
    });
    toast.success("Report generated");
  };

  const sendEmail = async () => {
    if (!rawText.trim() || !recipients.trim()) {
      toast.error("Provide WSR text and at least one recipient email.");
      return;
    }
    setSending(true);
    const emailList = recipients.split(",").map((e) => e.trim()).filter(Boolean);
    const { data, error } = await apiCall("reports/wsr/from-text", {
      text: rawText,
      send_email: true,
    });
    setSending(false);
    if (error || !data?.ok) {
      toast.error(error?.message || "Email send failed");
      return;
    }
    const sent = data.email?.sent?.length ?? 0;
    toast.success(`Report emailed to ${sent} recipient${sent !== 1 ? "s" : ""}`);
  };

  // Render HTML into iframe via blob URL
  useEffect(() => {
    if (!html || tab !== "preview" || !iframeRef.current) return;
    if (blobUrlRef.current) URL.revokeObjectURL(blobUrlRef.current);
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    blobUrlRef.current = url;
    iframeRef.current.src = url;
  }, [html, tab]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl h-[90vh] flex flex-col p-0 gap-0">
        <DialogHeader className="px-6 pt-5 pb-3 border-b shrink-0">
          <DialogTitle className="flex items-center gap-2">
            <FileBarChart className="h-5 w-5 text-blue-600" />
            Weekly Status Report Generator
          </DialogTitle>
        </DialogHeader>

        <Tabs value={tab} onValueChange={(v) => setTab(v as "paste" | "preview")} className="flex flex-col flex-1 min-h-0">
          <TabsList className="mx-6 mt-3 shrink-0 w-fit">
            <TabsTrigger value="paste">Write / Paste</TabsTrigger>
            <TabsTrigger value="preview" disabled={!html}>
              <Eye className="h-4 w-4 mr-1" />
              Preview
            </TabsTrigger>
          </TabsList>

          {/* ---- Paste tab ---- */}
          <TabsContent value="paste" className="flex-1 overflow-auto px-6 pb-6 pt-3 space-y-4">
            <p className="text-sm text-slate-500">
              Paste your raw WSR notes below. The AI will extract the structure, generate a branded HTML report, and produce a PDF.
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Project name (optional override)</Label>
                <Input
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder="Auto-detected from text"
                  className="rounded-xl text-sm"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Email recipients (comma-separated)</Label>
                <Input
                  value={recipients}
                  onChange={(e) => setRecipients(e.target.value)}
                  placeholder="pm@bank.ae, lead@businessnext.com"
                  className="rounded-xl text-sm"
                />
              </div>
            </div>
            <Textarea
              value={rawText}
              onChange={(e) => setRawText(e.target.value)}
              placeholder={`Project Name - Abu Dhabi Islamic Bank (ADIB)\nReporting Period - May 5 - May 9 2026\nProject Module - Liabilities\n\nKey Highlights This Week-\n...\n\nBlockers\n-...\n\nKey Risks / Issues\n...\n\nDefects Status\nOpen Defects Count - 25\nClosed Defects Count - 50`}
              className="min-h-[320px] rounded-xl text-sm font-mono leading-relaxed resize-none"
            />
            <div className="flex gap-2 justify-end">
              {recipients.trim() && (
                <Button variant="outline" className="rounded-xl" onClick={sendEmail} disabled={sending || loading}>
                  {sending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Send className="h-4 w-4 mr-2" />}
                  Generate & Email
                </Button>
              )}
              <Button className="rounded-xl bg-blue-700 hover:bg-blue-800" onClick={generate} disabled={loading || !rawText.trim()}>
                {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <FileBarChart className="h-4 w-4 mr-2" />}
                {loading ? "Generating…" : "Generate Report"}
              </Button>
            </div>
          </TabsContent>

          {/* ---- Preview tab ---- */}
          <TabsContent value="preview" className="flex-1 flex flex-col min-h-0 px-6 pb-4 pt-3 gap-3">
            {loading ? (
              <div className="space-y-3">
                <Skeleton className="h-8 w-48" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-32 w-full" />
              </div>
            ) : html ? (
              <>
                <div className="flex items-center gap-2 shrink-0">
                  {pdfBase64 && (
                    <Button
                      variant="outline"
                      className="rounded-xl"
                      onClick={() => downloadPdf(pdfBase64, `${projectName || "WSR"}_Report.pdf`)}
                    >
                      <Download className="h-4 w-4 mr-2" />
                      Download PDF
                    </Button>
                  )}
                  <Button variant="ghost" className="rounded-xl" onClick={() => setTab("paste")}>
                    Edit notes
                  </Button>
                </div>
                <iframe
                  ref={iframeRef}
                  title="WSR Preview"
                  className="flex-1 min-h-0 rounded-2xl border border-slate-200 bg-white w-full"
                  sandbox="allow-same-origin"
                />
              </>
            ) : null}
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
