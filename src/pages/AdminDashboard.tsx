import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiCall } from "@/lib/apiClient";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import {
  CheckCircle2, XCircle, Loader2, RefreshCw, ArrowLeft,
  Database, Brain, Zap, ShieldCheck, Activity, FileText,
} from "lucide-react";

interface HealthCard {
  label: string;
  status: "ok" | "error" | "loading" | "unknown";
  detail?: string;
  icon: React.ElementType;
  color: string;
}

interface RagStatus {
  size?: number;
  backend?: string;
  error?: string;
}

interface SupportedData {
  env?: Record<string, string>;
  async_jobs?: Record<string, unknown>;
  chat_detected?: Record<string, unknown>;
}

const AGENT_IMAGE_SRC = "/businessnext.jpeg";

export default function AdminDashboard() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [healthStatus, setHealthStatus] = useState<"ok" | "error" | "loading">("loading");
  const [dbStatus, setDbStatus] = useState<"ok" | "error" | "loading">("loading");
  const [ragStatus, setRagStatus] = useState<RagStatus | null>(null);
  const [supported, setSupported] = useState<SupportedData | null>(null);
  const [rebuilding, setRebuilding] = useState(false);
  const [rebuildJobId, setRebuildJobId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setHealthStatus("loading");
    setDbStatus("loading");

    const [health, readyz, supportedRes] = await Promise.all([
      apiCall("healthz", undefined, { method: "GET" }),
      apiCall("readyz", undefined, { method: "GET" }),
      apiCall("usecases/supported", undefined, { method: "GET" }),
    ]);

    setHealthStatus(health.data?.ok ? "ok" : "error");
    setDbStatus(readyz.data?.ok ? "ok" : "error");

    if (supportedRes.data) setSupported(supportedRes.data);

    // RAG index status — check via a 0-result search
    const ragProbe = await apiCall("rag/rebuild/status/probe", undefined, { method: "GET" });
    // 404 = no active job (good), anything else = check body
    if (ragProbe.error?.message?.includes("job_not_found") || ragProbe.data === null) {
      setRagStatus({ backend: "available", error: undefined });
    } else if (ragProbe.data) {
      setRagStatus(ragProbe.data);
    }

    setLoading(false);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const triggerRebuild = async () => {
    setRebuilding(true);
    const { data, error } = await apiCall("rag/rebuild", {});
    setRebuilding(false);
    if (error || !data?.ok) { toast.error(error?.message || "Rebuild failed"); return; }
    setRebuildJobId(data.job_id);
    toast.success("RAG rebuild queued — job " + data.job_id.slice(0, 8));
  };

  const statusIcon = (s: "ok" | "error" | "loading" | "unknown") => {
    if (s === "ok") return <CheckCircle2 className="h-5 w-5 text-emerald-500" />;
    if (s === "error") return <XCircle className="h-5 w-5 text-red-500" />;
    if (s === "loading") return <Loader2 className="h-5 w-5 text-blue-400 animate-spin" />;
    return <span className="h-5 w-5 rounded-full bg-slate-200 inline-block" />;
  };

  const statusBadge = (s: "ok" | "error" | "loading" | "unknown") => {
    const map = { ok: "bg-emerald-100 text-emerald-700", error: "bg-red-100 text-red-700", loading: "bg-blue-100 text-blue-700", unknown: "bg-slate-100 text-slate-500" };
    return <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${map[s]}`}>{s}</span>;
  };

  const envVars = supported?.env ?? {};
  const chatHandlers = supported?.chat_detected ?? {};

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50/30">
      {/* Header */}
      <header className="h-14 flex items-center gap-3 border-b border-slate-200/80 px-6 bg-white/80 backdrop-blur-sm">
        <Button variant="ghost" size="icon" className="rounded-xl" onClick={() => navigate("/")}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 overflow-hidden rounded-lg border border-slate-200 bg-white">
            <img src={AGENT_IMAGE_SRC} alt="BUSINESSNEXT" className="h-full w-full object-contain" />
          </div>
          <span className="font-semibold text-slate-800">Admin Dashboard</span>
        </div>
        <div className="ml-auto">
          <Button variant="outline" className="rounded-xl text-sm gap-2" onClick={refresh} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-6 py-8 space-y-8">

        {/* System health cards */}
        <section>
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-4">System Health</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {[
              { label: "API Server", status: healthStatus, icon: Activity, detail: "FastAPI /healthz" },
              { label: "Database", status: dbStatus, icon: Database, detail: "Connection pool" },
              { label: "RAG Index", status: ragStatus ? "ok" as const : loading ? "loading" as const : "unknown" as const, icon: Brain, detail: ragStatus?.error || (ragStatus?.backend ?? "") },
            ].map((card) => (
              <div key={card.label} className="rounded-2xl border border-slate-100 bg-white p-4 flex items-center gap-4 shadow-sm">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-50 shrink-0">
                  <card.icon className="h-5 w-5 text-slate-500" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-slate-700">{card.label}</p>
                  {card.detail && <p className="text-xs text-slate-400 truncate">{card.detail}</p>}
                </div>
                {loading ? <Skeleton className="h-5 w-5 rounded-full" /> : statusIcon(card.status)}
              </div>
            ))}
          </div>
        </section>

        {/* RAG management */}
        <section>
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-4">RAG Index Management</h2>
          <div className="rounded-2xl border border-slate-100 bg-white p-5 shadow-sm space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-slate-700">Project knowledge index</p>
                <p className="text-xs text-slate-400 mt-0.5">
                  Rebuilding re-embeds all project rows. Use after DB schema changes or initial setup.
                  {rebuildJobId && <span className="ml-2 font-mono text-blue-500">Job: {rebuildJobId.slice(0, 8)}…</span>}
                </p>
              </div>
              <Button
                className="rounded-xl bg-blue-700 hover:bg-blue-800 shrink-0"
                onClick={triggerRebuild}
                disabled={rebuilding}
              >
                {rebuilding ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <RefreshCw className="h-4 w-4 mr-2" />}
                {rebuilding ? "Queuing…" : "Rebuild Index"}
              </Button>
            </div>
            <div className="text-xs text-slate-400 bg-slate-50 rounded-xl p-3 font-mono">
              Set <span className="text-blue-600">CHROMA_PERSIST_DIR</span> for persistent storage.
              Unset = in-memory FAISS (resets on restart).
            </div>
          </div>
        </section>

        {/* Intent Router */}
        <section>
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-4">
            <span className="flex items-center gap-2"><Zap className="h-4 w-4" />Semantic Intent Router</span>
          </h2>
          <div className="rounded-2xl border border-slate-100 bg-white p-5 shadow-sm space-y-2 text-sm">
            <p className="text-slate-600">Embedding-based router sits above keyword chain. Handles paraphrased queries by finding nearest canonical intent.</p>
            <div className="flex flex-wrap gap-3 mt-3 text-xs">
              <div className="bg-slate-50 rounded-xl px-3 py-2 font-mono">
                <span className="text-slate-400">INTENT_ROUTING_THRESHOLD</span>
                <span className="text-blue-600 ml-2">default 0.55</span>
              </div>
              <div className="bg-slate-50 rounded-xl px-3 py-2 font-mono">
                <span className="text-slate-400">INTENT_ROUTING_ENABLED</span>
                <span className="text-blue-600 ml-2">default 1 (true)</span>
              </div>
            </div>
          </div>
        </section>

        {/* Active handlers */}
        <section>
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-4">
            <span className="flex items-center gap-2"><ShieldCheck className="h-4 w-4" />Active Chat Handlers</span>
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {loading
              ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-2xl" />)
              : Object.entries(chatHandlers).map(([key, items]) => (
                  <div key={key} className="rounded-2xl border border-slate-100 bg-white p-4 shadow-sm">
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">{key.replace(/_/g, " ")}</p>
                    <div className="flex flex-wrap gap-1">
                      {Array.isArray(items)
                        ? items.map((item, i) => (
                            <Badge key={i} variant="secondary" className="text-[10px]">{String(item)}</Badge>
                          ))
                        : <Badge variant="secondary" className="text-[10px]">{String(items)}</Badge>}
                    </div>
                  </div>
                ))}
          </div>
        </section>

        {/* Env vars reference */}
        {Object.keys(envVars).length > 0 && (
          <section>
            <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-4">
              <span className="flex items-center gap-2"><FileText className="h-4 w-4" />Environment Variables</span>
            </h2>
            <div className="rounded-2xl border border-slate-100 bg-white p-4 shadow-sm divide-y divide-slate-50">
              {Object.entries(envVars).map(([key, desc]) => (
                <div key={key} className="py-2.5 flex items-start gap-3">
                  <code className="text-xs text-blue-700 bg-blue-50 px-2 py-0.5 rounded font-mono shrink-0">{key}</code>
                  <p className="text-xs text-slate-500 leading-relaxed">{desc}</p>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
