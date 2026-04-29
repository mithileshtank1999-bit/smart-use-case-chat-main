export type TimesheetTimeframe =
  | { kind: "single"; dateISO: string }
  | { kind: "multi"; datesISO: string[]; label: string };

export type TimesheetPromptPlan = {
  project_id?: string;
  project_name?: string;
  effort_minutes: number;
  category?: string;
  description?: string;
  start_time?: string;
  end_time?: string;
  timeframe: TimesheetTimeframe;
};

function pad2(n: number) {
  return String(n).padStart(2, "0");
}

function toISODate(d: Date) {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function startOfWeekMonday(d: Date) {
  const day = d.getDay(); // 0=Sun
  const diff = (day + 6) % 7; // Mon=0
  const start = new Date(d);
  start.setDate(d.getDate() - diff);
  start.setHours(0, 0, 0, 0);
  return start;
}

function endOfWeekSunday(d: Date) {
  const start = startOfWeekMonday(d);
  const end = new Date(start);
  end.setDate(start.getDate() + 6);
  end.setHours(0, 0, 0, 0);
  return end;
}

function isWeekday(d: Date) {
  const day = d.getDay();
  return day !== 0 && day !== 6;
}

function datesBetweenInclusive(start: Date, end: Date, weekdaysOnly = true) {
  const out: string[] = [];
  const cur = new Date(start);
  cur.setHours(0, 0, 0, 0);
  const last = new Date(end);
  last.setHours(0, 0, 0, 0);
  while (cur <= last) {
    if (!weekdaysOnly || isWeekday(cur)) out.push(toISODate(cur));
    cur.setDate(cur.getDate() + 1);
  }
  return out;
}

function parseEffortMinutes(text: string): number {
  const lower = text.toLowerCase();
  const hourMatch = lower.match(/(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours)\b/);
  if (hourMatch?.[1]) {
    const hours = Number(hourMatch[1]);
    if (!Number.isNaN(hours) && hours > 0) return Math.round(hours * 60);
  }
  const minMatch = lower.match(/(\d+)\s*(m|min|mins|minute|minutes)\b/);
  if (minMatch?.[1]) {
    const mins = Number(minMatch[1]);
    if (!Number.isNaN(mins) && mins > 0) return mins;
  }
  if (lower.includes("half day")) return 240;
  if (lower.includes("full day")) return 480;
  return 480;
}

function parseCategory(text: string): string | undefined {
  const lower = text.toLowerCase();
  const under = lower.match(/\bunder\s+the\s+([a-z][a-z\s/&-]{2,40})\s+category\b/);
  if (under?.[1]) return under[1].trim();
  const cat = lower.match(/\bunder\s+([a-z][a-z\s/&-]{2,40})\b/);
  if (cat?.[1] && cat[1].trim().length <= 30) return cat[1].trim();
  if (lower.includes("leave")) return "leave";
  if (lower.includes("development") || lower.includes("dev")) return "development";
  return undefined;
}

function parseTimeframe(text: string): TimesheetTimeframe {
  const lower = text.toLowerCase();
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  if (/\btoday\b/.test(lower)) {
    return { kind: "single", dateISO: toISODate(today) };
  }
  if (/\byesterday\b/.test(lower)) {
    const d = new Date(today);
    d.setDate(d.getDate() - 1);
    return { kind: "single", dateISO: toISODate(d) };
  }

  const lastWeek = /\b(last|past)\s+week\b/.test(lower);
  const thisWeek = /\b(this|current)\s+week\b/.test(lower) || /\bweekly\b/.test(lower);
  if (lastWeek || thisWeek) {
    const anchor = new Date(today);
    if (lastWeek) anchor.setDate(anchor.getDate() - 7);
    const start = startOfWeekMonday(anchor);
    const end = endOfWeekSunday(anchor);
    return {
      kind: "multi",
      datesISO: datesBetweenInclusive(start, end, true),
      label: lastWeek ? "last week" : "this week",
    };
  }

  const lastMonth = /\b(last|past)\s+month\b/.test(lower);
  const thisMonth = /\b(this|current)\s+month\b/.test(lower) || /\bmonthly\b/.test(lower);
  if (lastMonth || thisMonth) {
    const d = new Date(today);
    if (lastMonth) d.setMonth(d.getMonth() - 1);
    const start = new Date(d.getFullYear(), d.getMonth(), 1);
    const end = new Date(d.getFullYear(), d.getMonth() + 1, 0);
    return {
      kind: "multi",
      datesISO: datesBetweenInclusive(start, end, true),
      label: lastMonth ? "last month" : "this month",
    };
  }

  // Default to today if nothing specified.
  return { kind: "single", dateISO: toISODate(today) };
}

export function looksLikeTimesheetPrompt(message: string) {
  const lower = message.toLowerCase();
  const mentionsTimesheet =
    lower.includes("timesheet") ||
    lower.includes("time sheet") ||
    lower.includes("time-sheet") ||
    /\bts\b/.test(lower);

  const intent =
    lower.includes("fill") ||
    lower.includes("enter") ||
    lower.includes("log") ||
    lower.includes("submit") ||
    (lower.includes("time") && lower.includes("sheet"));

  return mentionsTimesheet && intent;
}

export function parseTimesheetPrompt(message: string): TimesheetPromptPlan {
  const effort_minutes = parseEffortMinutes(message);
  const category = parseCategory(message);
  const timeframe = parseTimeframe(message);

  // Project parsing is handled by the caller (needs the loaded project list + selected project).
  return {
    effort_minutes,
    category,
    timeframe,
    start_time: "09:00",
    end_time: "17:00",
    description: category ? `Timesheet - ${category}` : "Timesheet entry",
  };
}
