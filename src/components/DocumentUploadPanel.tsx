import { useCallback, useEffect, useRef, useState } from "react";
import { apiCall, getApiBaseUrl } from "@/lib/apiClient";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { toast } from "sonner";
import { FileText, Trash2, Upload, Search, X, FileCheck } from "lucide-react";

interface Doc {
  doc_id: string;
  filename: string;
  file_type: string;
  uploaded_at: string;
  chunks: number;
}

interface SearchHit {
  text: string;
  filename: string;
  page: number;
}

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}

export function DocumentUploadPanel({ open, onOpenChange }: Props) {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchHits, setSearchHits] = useState<SearchHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const fetchDocs = useCallback(async () => {
    setLoading(true);
    const { data } = await apiCall("documents", undefined, { method: "GET" });
    if (data?.documents) setDocs(data.documents);
    setLoading(false);
  }, []);

  useEffect(() => {
    if (open) fetchDocs();
  }, [open, fetchDocs]);

  const uploadFile = async (file: File) => {
    const allowed = [".pdf", ".docx", ".txt"];
    const ext = "." + file.name.split(".").pop()?.toLowerCase();
    if (!allowed.includes(ext)) {
      toast.error(`Unsupported file type: ${ext}. Use PDF, DOCX, or TXT.`);
      return;
    }
    setUploading(true);
    const form = new FormData();
    form.append("file", file);
    try {
      const resp = await fetch(`${getApiBaseUrl()}/documents/upload`, { method: "POST", body: form });
      const data = await resp.json();
      if (data.ok) {
        toast.success(`"${file.name}" uploaded — ${data.chunks} chunks indexed`);
        fetchDocs();
      } else {
        toast.error(data.error || "Upload failed");
      }
    } catch {
      toast.error("Upload failed — server unreachable");
    } finally {
      setUploading(false);
    }
  };

  const handleFiles = (files: FileList | null) => {
    if (!files) return;
    Array.from(files).forEach(uploadFile);
  };

  const deleteDoc = async (doc: Doc) => {
    const { data } = await apiCall(`documents/${doc.doc_id}`, undefined, { method: "DELETE" });
    if (data?.ok) {
      toast.success(`"${doc.filename}" removed`);
      setDocs((prev) => prev.filter((d) => d.doc_id !== doc.doc_id));
    } else {
      toast.error("Delete failed");
    }
  };

  const doSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    const { data } = await apiCall("documents/search", { query: searchQuery, top_k: 5 });
    setSearchHits(data?.hits || []);
    setSearching(false);
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-xl flex flex-col gap-0 p-0">
        <SheetHeader className="px-5 pt-5 pb-3 border-b">
          <SheetTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-blue-600" />
            Intelligent Document Management
          </SheetTitle>
        </SheetHeader>

        <ScrollArea className="flex-1">
          <div className="px-5 py-4 space-y-5">
            {/* Drop zone */}
            <div
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files); }}
              onClick={() => fileRef.current?.click()}
              className={`flex flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed p-8 cursor-pointer transition-colors
                ${dragOver ? "border-blue-500 bg-blue-50" : "border-slate-200 bg-slate-50 hover:border-blue-400 hover:bg-blue-50/50"}`}
            >
              <Upload className={`h-8 w-8 ${dragOver ? "text-blue-500" : "text-slate-400"}`} />
              <p className="text-sm font-medium text-slate-600">
                {uploading ? "Uploading…" : "Drop files here or click to browse"}
              </p>
              <p className="text-xs text-slate-400">PDF, DOCX, TXT supported</p>
              <input
                ref={fileRef}
                type="file"
                accept=".pdf,.docx,.txt"
                multiple
                className="hidden"
                onChange={(e) => handleFiles(e.target.files)}
              />
            </div>

            {/* Search */}
            <div className="flex gap-2">
              <Input
                placeholder="Search across documents…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && doSearch()}
                className="rounded-xl"
              />
              <Button variant="outline" className="rounded-xl shrink-0" onClick={doSearch} disabled={searching}>
                <Search className="h-4 w-4" />
              </Button>
              {searchHits !== null && (
                <Button variant="ghost" size="icon" className="rounded-xl shrink-0" onClick={() => setSearchHits(null)}>
                  <X className="h-4 w-4" />
                </Button>
              )}
            </div>

            {/* Search results */}
            {searchHits !== null && (
              <div className="space-y-2">
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">
                  {searchHits.length} result{searchHits.length !== 1 ? "s" : ""}
                </p>
                {searchHits.length === 0 ? (
                  <p className="text-sm text-slate-400 italic">No matching chunks found.</p>
                ) : (
                  searchHits.map((h, i) => (
                    <div key={i} className="rounded-xl border border-slate-100 bg-slate-50 p-3 text-xs space-y-1">
                      <div className="flex items-center gap-2">
                        <FileCheck className="h-3.5 w-3.5 text-blue-500" />
                        <span className="font-medium text-slate-600">{h.filename}</span>
                        {h.page > 0 && <Badge variant="secondary" className="text-[10px]">p.{h.page}</Badge>}
                      </div>
                      <p className="text-slate-500 line-clamp-3 leading-relaxed">{h.text}</p>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* Document list */}
            <div className="space-y-2">
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">
                {loading ? "Loading…" : `${docs.length} document${docs.length !== 1 ? "s" : ""} indexed`}
              </p>
              {loading ? (
                Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-12 rounded-xl" />)
              ) : docs.length === 0 ? (
                <p className="text-sm text-slate-400 italic py-4 text-center">No documents uploaded yet.</p>
              ) : (
                docs.map((doc) => (
                  <div key={doc.doc_id} className="flex items-center gap-3 rounded-xl border border-slate-100 bg-white p-3">
                    <FileText className="h-5 w-5 shrink-0 text-blue-400" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-slate-700">{doc.filename}</p>
                      <p className="text-xs text-slate-400">
                        {doc.chunks} chunk{doc.chunks !== 1 ? "s" : ""} · {new Date(doc.uploaded_at).toLocaleDateString()}
                      </p>
                    </div>
                    <Badge variant="outline" className="text-[10px] shrink-0">{doc.file_type.toUpperCase()}</Badge>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="shrink-0 h-7 w-7 text-slate-400 hover:text-red-500"
                      onClick={() => deleteDoc(doc)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                ))
              )}
            </div>
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
