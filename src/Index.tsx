import { useEffect, useRef, useState } from "react";
import { streamChat, type Msg } from "./lib/streamChat";
import { ProjectResultsTable, type ProjectRecord } from "./components/ProjectResultsTable";
import { apiCall } from "./lib/apiClient";

interface ProjectSummary {
    overview?: {
        project_name?: string;
        status?: string;
        portfolio?: string;
        portfolio_owner?: string;
    };
    timeline?: {
        go_live_date?: string;
        start_date?: string;
        end_date?: string;
    };
    governance?: string;
    financial?: {
        revenue?: string;
        revenue_remaining?: string;
    };
    risks?: {
        risk_statement?: string;
        severity?: string;
    };
    highlights?: {
        module?: string;
    };
}

function hasText(value: string | null | undefined) {
    return Boolean(value && value.trim());
}

function formatSummary(summary: ProjectSummary, project: ProjectRecord): string {
    const lines: string[] = [`Project summary for ${project.project_name}`];
    const overview = [
        summary.overview?.project_name && `Project: ${summary.overview.project_name}`,
        summary.overview?.status && `Status: ${summary.overview.status}`,
        summary.overview?.portfolio && `Portfolio: ${summary.overview.portfolio}`,
        summary.overview?.portfolio_owner && `Portfolio owner: ${summary.overview.portfolio_owner}`,
    ].filter(Boolean) as string[];

    const timeline = [
        summary.timeline?.go_live_date && `Go live: ${summary.timeline.go_live_date}`,
        summary.timeline?.start_date && `Start: ${summary.timeline.start_date}`,
        summary.timeline?.end_date && `End: ${summary.timeline.end_date}`,
    ].filter(Boolean) as string[];

    const financial = [
        summary.financial?.revenue && `Revenue: ${summary.financial.revenue}`,
        summary.financial?.revenue_remaining && `Remaining revenue: ${summary.financial.revenue_remaining}`,
    ].filter(Boolean) as string[];

    const risks = [
        summary.risks?.risk_statement && `Risk: ${summary.risks.risk_statement}`,
        summary.risks?.severity && `Severity: ${summary.risks.severity}`,
    ].filter(Boolean) as string[];

    if (overview.length > 0) {
        lines.push("", "Overview", ...overview);
    }

    if (timeline.length > 0) {
        lines.push("", "Timeline", ...timeline);
    }

    if (hasText(summary.governance)) {
        lines.push("", "Governance", summary.governance!.trim());
    }

    if (financial.length > 0) {
        lines.push("", "Financial", ...financial);
    }

    if (risks.length > 0) {
        lines.push("", "Risks", ...risks);
    }

    if (hasText(summary.highlights?.module)) {
        lines.push("", "Highlights", summary.highlights!.module!.trim());
    }

    return lines.length > 1
        ? lines.join("\n")
        : `No summary details are available yet for ${project.project_name}.`;
}

function normalizeProjects(data: unknown[]): ProjectRecord[] {
    return data.map((project) => {
        const record = project as Record<string, unknown>;

        return {
            project_id: String(record.project_id ?? ""),
            project_name: String(record.project_name ?? "Untitled Project"),
            status: String(record.status ?? "Unknown"),
            go_live_date: record.go_live_date ? String(record.go_live_date) : null,
            portfolio_name: record.portfolio_name
                ? String(record.portfolio_name)
                : record.portfolio
                    ? String(record.portfolio)
                    : null,
            portfolio_owner: record.portfolio_owner ? String(record.portfolio_owner) : null,
            account_name: record.account_name
                ? String(record.account_name)
                : record.customer_name
                    ? String(record.customer_name)
                    : null,
            project_manager: record.project_manager
                ? String(record.project_manager)
                : record.hod
                    ? String(record.hod)
                    : null,
        };
    }).filter((project) => project.project_id);
}

export default function Index() {
    const [messages, setMessages] = useState<Msg[]>([]);
    const [input, setInput] = useState("");
    const [loading, setLoading] = useState(false);
    const [projects, setProjects] = useState<ProjectRecord[]>([]);
    const [selectedProject, setSelectedProject] = useState<ProjectRecord | null>(null);
    const [loadingSummaryProjectId, setLoadingSummaryProjectId] = useState<string | null>(null);

    const bottomRef = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    const sendMessage = async () => {
        if (!input.trim() || loading) return;

        const userMsg: Msg = { role: "user", content: input };
        const updated = [...messages, userMsg];

        setMessages(updated);
        setInput("");
        setLoading(true);

        const result = await streamChat({
            messages: updated,
            onDelta: (text) => {
                setMessages((prev) => {
                    const last = prev[prev.length - 1];

                    if (last?.role === "assistant") {
                        return [
                            ...prev.slice(0, -1),
                            { role: "assistant", content: text },
                        ];
                    }

                    return [...prev, { role: "assistant", content: text }];
                });
            },
            onDone: () => setLoading(false),
        });

        if (result?.data?.length > 0) {
            setProjects(normalizeProjects(result.data));
        }
    };

    const handleProjectClick = async (project: ProjectRecord) => {
        if (!project.project_id || loadingSummaryProjectId === project.project_id) {
            return;
        }

        setSelectedProject(project);
        setLoadingSummaryProjectId(project.project_id);

        const placeholderIndex = messages.length;
        setMessages((prev) => [
            ...prev,
            {
                role: "assistant",
                content: `Generating project summary for ${project.project_name}...`,
            },
        ]);

        try {
            const { data, error } = await apiCall("summary", {
                project_id: project.project_id,
            });

            const content = error
                ? `I couldn't generate a summary for ${project.project_name}. ${error.message}`
                : data?.summary && Object.keys(data.summary).length > 0
                    ? formatSummary(data.summary as ProjectSummary, project)
                    : `No summary details are available yet for ${project.project_name}.`;

            setMessages((prev) =>
                prev.map((message, index) =>
                    index === placeholderIndex ? { role: "assistant", content } : message
                )
            );
        } catch (error) {
            const message = error instanceof Error ? error.message : "Unknown error";

            setMessages((prev) =>
                prev.map((entry, index) =>
                    index === placeholderIndex
                        ? {
                            role: "assistant",
                            content: `I couldn't generate a summary for ${project.project_name}. ${message}`,
                        }
                        : entry
                )
            );
        } finally {
            setLoadingSummaryProjectId((current) =>
                current === project.project_id ? null : current
            );
        }
    };

    return (
        <div style={{ display: "flex", height: "100vh" }}>
            <div
                style={{
                    width: 250,
                    background: "#202123",
                    color: "#fff",
                    padding: 15,
                }}
            >
                <h3>Chats</h3>
                <div style={{ marginTop: 10, fontSize: 14, color: "#aaa" }}>
                    (History coming soon)
                </div>
            </div>

            <div
                style={{
                    flex: 1,
                    display: "flex",
                    flexDirection: "column",
                    background: "#343541",
                    color: "#fff",
                }}
            >
                <div
                    style={{
                        flex: 1,
                        overflowY: "auto",
                        padding: 20,
                    }}
                >
                    {messages.map((message, index) => (
                        <div
                            key={index}
                            style={{
                                display: "flex",
                                justifyContent:
                                    message.role === "user" ? "flex-end" : "flex-start",
                                marginBottom: 12,
                            }}
                        >
                            <div
                                style={{
                                    maxWidth: "70%",
                                    padding: "10px 14px",
                                    borderRadius: 10,
                                    background:
                                        message.role === "user" ? "#0b93f6" : "#444654",
                                    whiteSpace: "pre-wrap",
                                }}
                            >
                                {message.content}
                            </div>
                        </div>
                    ))}

                    {loading && (
                        <div style={{ color: "#aaa" }}>Assistant is typing...</div>
                    )}

                    <div ref={bottomRef} />
                    {projects.length > 0 && (
                        <div style={{ padding: 20 }}>
                            <ProjectResultsTable
                                projects={projects}
                                onProjectClick={handleProjectClick}
                            />
                        </div>
                    )}
                </div>

                {loadingSummaryProjectId && selectedProject && (
                    <div style={{ padding: 20, color: "#aaa" }}>
                        Generating summary for {selectedProject.project_name}...
                    </div>
                )}

                <div
                    style={{
                        padding: 15,
                        borderTop: "1px solid #555",
                        display: "flex",
                        gap: 10,
                    }}
                >
                    <input
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && sendMessage()}
                        placeholder="Send a message..."
                        style={{
                            flex: 1,
                            padding: 12,
                            borderRadius: 8,
                            border: "none",
                            outline: "none",
                            background: "#40414f",
                            color: "#fff",
                        }}
                    />

                    <button
                        onClick={sendMessage}
                        disabled={loading}
                        style={{
                            padding: "12px 18px",
                            borderRadius: 8,
                            border: "none",
                            background: "#19c37d",
                            color: "#fff",
                            cursor: "pointer",
                        }}
                    >
                        Send
                    </button>
                </div>
            </div>
        </div>
    );
}
