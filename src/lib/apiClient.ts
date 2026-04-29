/**
 * Base URL for your FastAPI backend
 */
export function getApiBaseUrl(): string {
  const envUrl = String((import.meta as any)?.env?.VITE_API_BASE_URL || "").trim();
  return envUrl || "http://127.0.0.1:8000/api";
}

/**
 * Generic API caller
 */
export async function apiCall(
  functionName: string,
  body?: Record<string, unknown>,
  options?: { method?: string; query?: Record<string, string> }
): Promise<{ data: any; error: any }> {
  const baseUrl = getApiBaseUrl();
  const method = options?.method || "POST";

  let url = `${baseUrl}/${functionName}`;

  // add query params if present
  if (options?.query) {
    const qs = new URLSearchParams(options.query).toString();
    url += `?${qs}`;
  }

  const fetchOpts: RequestInit = {
    method,
    headers: {
      "Content-Type": "application/json",
    },
  };

  if (body && method !== "GET" && method !== "DELETE") {
    fetchOpts.body = JSON.stringify(body);
  }

  try {
    const resp = await fetch(url, fetchOpts);
    let data: any = null;
    try {
      data = await resp.json();
    } catch {
      const text = await resp.text();
      data = text ? { error: text } : null;
    }

    if (!resp.ok) {
      let message =
        (data && typeof data === "object" && "error" in data && (data as any).error)
          ? String((data as any).error)
          : resp.statusText;

      if (data && typeof data === "object" && "hint" in data && (data as any).hint) {
        message = `${message} (hint: ${String((data as any).hint)})`;
      }
      return { data: null, error: { message } };
    }

    return { data, error: null };
  } catch (err: any) {
    return { data: null, error: { message: err.message } };
  }
}
