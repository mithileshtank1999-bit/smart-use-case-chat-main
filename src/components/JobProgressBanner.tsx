import { useEffect, useRef, useState } from "react";
import { apiCall } from "@/lib/apiClient";
import { Loader2, CheckCircle2, XCircle, X } from "lucide-react";
import { toast } from "sonner";

interface Props {
  jobId: string | null;
  label?: string;
  onDismiss: () => void;
}

type JobStatus = "queued" | "running" | "done" | "failed";

interface Job {
  status: JobStatus;
  label: string;
  result?: Record<string, unknown>;
  error?: string;
}

const POLL_MS = 2500;

export function JobProgressBanner({ jobId, label, onDismiss }: Props) {
  const [job, setJob] = useState<Job | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!jobId) {
      setJob(null);
      return;
    }

    const poll = async () => {
      const { data } = await apiCall(`rag/rebuild/status/${jobId}`, undefined, { method: "GET" });
      if (!data) return;
      const status: JobStatus = data.status;
      setJob({ status, label: data.label || label || "Background job", result: data.result, error: data.error });

      if (status === "done") {
        clearInterval(intervalRef.current!);
        const docs = (data.result as any)?.documents ?? "";
        toast.success(`RAG index rebuilt — ${docs ? `${docs} documents indexed` : "complete"}`);
      } else if (status === "failed") {
        clearInterval(intervalRef.current!);
        toast.error(`Job failed: ${data.error || "unknown error"}`);
      }
    };

    poll();
    intervalRef.current = setInterval(poll, POLL_MS);
    return () => clearInterval(intervalRef.current!);
  }, [jobId, label]);

  if (!job || !jobId) return null;

  const isDone = job.status === "done" || job.status === "failed";
  const bg =
    job.status === "done"
      ? "bg-emerald-50 border-emerald-200 text-emerald-800"
      : job.status === "failed"
        ? "bg-red-50 border-red-200 text-red-800"
        : "bg-blue-50 border-blue-200 text-blue-800";

  return (
    <div className={`flex items-center gap-3 rounded-xl border px-4 py-2 text-sm font-medium ${bg}`}>
      {job.status === "done" ? (
        <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
      ) : job.status === "failed" ? (
        <XCircle className="h-4 w-4 shrink-0 text-red-600" />
      ) : (
        <Loader2 className="h-4 w-4 shrink-0 animate-spin text-blue-600" />
      )}
      <span className="flex-1 truncate">
        {job.status === "queued" && "Queued: "}
        {job.status === "running" && "Running: "}
        {job.status === "done" && "Done: "}
        {job.status === "failed" && "Failed: "}
        {job.label}
        {job.status === "done" && job.result && ` (${(job.result as any).documents ?? ""} docs)`}
        {job.status === "failed" && job.error && ` — ${job.error}`}
      </span>
      {isDone && (
        <button onClick={onDismiss} className="ml-auto shrink-0 opacity-60 hover:opacity-100">
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
