export type Severity = "critical" | "urgent" | "routine" | "fyi"

export interface Call {
  id: number
  call_sid: string
  from_number: string
  received_at: string
  audio_path: string
  transcript: string
  channel: string
  urgency: string
  request_type: string
  no_callback: boolean
  insufficient_detail: boolean
  confidence: number
  summary: string
  suggested_action: string
  raw_classification_json: string
  severity: Severity
  patient_name: string
  room: string
  caller_name: string
  caller_role: string
  resolved: boolean
}
