import { getApiBaseUrl } from "@/lib/apiClient";

export async function transcribeAudio(blob: Blob, opts?: { filename?: string; language?: string }) {
  const filename = opts?.filename || "audio.webm";
  const language = opts?.language;

  const form = new FormData();
  form.append("file", blob, filename);
  if (language) form.append("language", language);

  const url = `${getApiBaseUrl()}/speech/transcribe-file`;
  const resp = await fetch(url, { method: "POST", body: form });
  let data: any = null;
  try {
    data = await resp.json();
  } catch {
    // ignore
  }

  if (!resp.ok) {
    const message =
      data && typeof data === "object" && "error" in data && (data as any).error
        ? String((data as any).error)
        : data && typeof data === "object" && "detail" in data && (data as any).detail
          ? String((data as any).detail)
        : resp.statusText || "Transcription failed";
    throw new Error(message);
  }

  if (!data?.ok) throw new Error(data?.error || "Transcription failed");
  return String(data.text || "");
}
