export type Msg = { role: "user" | "assistant"; content: string };

import { getApiBaseUrl } from "./apiClient";

function getChatUrl(): string {
    const localBase = getApiBaseUrl();
    if (localBase) return `${localBase}/chat`;
    return `${import.meta.env.VITE_SUPABASE_URL}/functions/v1/chat`;
}

export async function streamChat({
    messages,
    employeeName,
    onDelta,
    onDone,
    onError,
    signal,
}: {
    messages: Msg[];
    employeeName?: string;
    onDelta: (deltaText: string) => void;
    onDone: () => void;
    onError?: () => void;
    signal?: AbortSignal;
}) {
    try {
        const url = getChatUrl();

        const resp = await fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ messages, employee_name: employeeName }),
            signal,
        });

        if (!resp.ok) {
            throw new Error("Failed to fetch");
        }

        const data = await resp.json();

        console.log("API Response:", data);

        let content = data.message || data.response || "";
        const lastUserMessage = [...messages].reverse().find((m) => m.role === "user")?.content || "";
        const lastUserLower = lastUserMessage.toLowerCase();

        // Back-compat: if backend only returns rows/data, render a minimal list.
        const rows = data.rows || data.data || [];
        if (!content && Array.isArray(rows) && rows.length > 0) {
            content = rows
                .map((row: any) => `${row.project_name || "N/A"} (${row.status || ""})`)
                .join("\n");
        }

        // Only append row previews for explicitly "list/show" intents; avoid breaking summary-style answers.
        const wantsList =
            ["show", "list", "results", "find", "search", "table"].some((t) => lastUserLower.includes(t)) &&
            !["summary", "two liner", "2 liner", "two-line", "two line"].some((t) => lastUserLower.includes(t));
        if (wantsList && content && !content.includes("```json") && Array.isArray(rows) && rows.length > 0) {
            content += "\n\n";
            content += rows
                .slice(0, 10)
                .map((row: any) => `${row.project_name || "N/A"} (${row.status || ""})`)
                .join("\n");
        }

        onDelta(content);

        onDone();
        return data;

    } catch (err) {
        console.error(err);
        onError?.();
    }
}
