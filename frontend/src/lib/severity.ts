import type { Severity } from "@/types"

export const SEVERITY_LABELS: Record<Severity, string> = {
  critical: "Critical",
  urgent: "Urgent",
  routine: "Routine",
  fyi: "FYI",
}

export const SEVERITY_COLORS: Record<Severity, string> = {
  critical: "#C73E3A",
  urgent: "#E07A1F",
  routine: "#3A5FC7",
  fyi: "#6B6B6B",
}

export const SEVERITY_ORDER: Record<Severity, number> = {
  critical: 0,
  urgent: 1,
  routine: 2,
  fyi: 3,
}
