import { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bot, User } from "lucide-react";
import { cn } from "@/lib/utils";
import { ProjectResultsTable, type ProjectRecord } from "./ProjectResultsTable";

interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  onProjectClick?: (project: ProjectRecord) => void;
}

function tryParseProjectData(content: string): { projects: ProjectRecord[]; filters: Record<string, string | null>; rest: string } | null {
  // Look for ```json ... ``` blocks containing project arrays
  const jsonBlockRegex = /```json\s*\n([\s\S]*?)```/g;
  let match;
  while ((match = jsonBlockRegex.exec(content)) !== null) {
    try {
      const parsed = JSON.parse(match[1]);
      // Check if it's an array of project-like objects
      if (Array.isArray(parsed) && parsed.length > 0 && parsed[0].project_id) {
        const rest = content.replace(match[0], "").trim();
        return { projects: parsed, filters: {}, rest };
      }
      // Check if it's a wrapper object with results array
      if (parsed.results && Array.isArray(parsed.results) && parsed.results.length > 0 && parsed.results[0].project_id) {
        const rest = content.replace(match[0], "").trim();
        return { projects: parsed.results, filters: parsed.filters || {}, rest };
      }
      // Check if it's a filters object (Stage 1)
      if (parsed.project_id !== undefined || parsed.project_name !== undefined || parsed.account_name !== undefined || parsed.portfolio_name !== undefined || parsed.status !== undefined) {
        // This is a filters block — don't render as table, let markdown handle it
        return null;
      }
    } catch {
      // not valid JSON, skip
    }
  }
  return null;
}

export function ChatMessage({ role, content, onProjectClick }: ChatMessageProps) {
  const isUser = role === "user";
  const projectData = useMemo(() => (!isUser ? tryParseProjectData(content) : null), [isUser, content]);

  return (
    <div className={cn("flex gap-3 px-4 py-4", isUser ? "justify-end" : "justify-start")}>
      {!isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Bot className="h-5 w-5" />
        </div>
      )}
      <div
        className={cn(
          "max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed",
          isUser
            ? "bg-chat-user text-chat-user-foreground rounded-br-md"
            : "bg-chat-ai text-chat-ai-foreground rounded-bl-md"
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{content}</p>
        ) : projectData ? (
          <div className="space-y-3">
            {projectData.rest && (
              <div className="prose prose-sm max-w-none dark:prose-invert prose-p:my-1 prose-headings:my-2">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{projectData.rest}</ReactMarkdown>
              </div>
            )}
            <ProjectResultsTable
              projects={projectData.projects}
              filters={projectData.filters}
              onProjectClick={onProjectClick}
            />
          </div>
        ) : (
          <div className="prose prose-sm max-w-none dark:prose-invert prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-ol:my-1 prose-li:my-0.5 prose-table:my-2 prose-pre:my-2">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>
        )}
      </div>
      {isUser && (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <User className="h-5 w-5" />
        </div>
      )}
    </div>
  );
}

export function TypingIndicator() {
  return (
    <div className="flex gap-3 px-4 py-4">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
        <Bot className="h-5 w-5" />
      </div>
      <div className="flex items-center gap-1.5 rounded-2xl rounded-bl-md bg-chat-ai px-4 py-3">
        <span className="h-2 w-2 rounded-full bg-muted-foreground animate-pulse-dot" />
        <span className="h-2 w-2 rounded-full bg-muted-foreground animate-pulse-dot [animation-delay:0.2s]" />
        <span className="h-2 w-2 rounded-full bg-muted-foreground animate-pulse-dot [animation-delay:0.4s]" />
      </div>
    </div>
  );
}
