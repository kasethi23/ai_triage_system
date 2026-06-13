import type { Severity } from "@/types"

export const SEVERITY_LABELS: Record<Severity, string> = {
  severe: "Severe",
  emergent: "Emergent",
  "semi-urgent": "Semi-Urgent",
  "non-urgent": "Non-Urgent",
}

export const SEVERITY_COLORS: Record<Severity, string> = {
  severe: "#C73E3A",
  emergent: "#E07A1F",
  "semi-urgent": "#3A5FC7",
  "non-urgent": "#6B6B6B",
}

export const SEVERITY_ORDER: Record<Severity, number> = {
  severe: 0,
  emergent: 1,
  "semi-urgent": 2,
  "non-urgent": 3,
}
