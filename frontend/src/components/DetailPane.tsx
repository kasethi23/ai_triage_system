import { useState } from "react"
import { ChevronDown, ChevronUp, Phone, X } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { useTimeAgo } from "@/hooks/useTimeAgo"
import { audioUrl, resolveCall } from "@/lib/api"
import { SEVERITY_LABELS } from "@/lib/severity"
import type { Call } from "@/types"

interface DetailPaneProps {
  call: Call | null
  onResolved: (call: Call) => void
  onClose?: () => void
}

export function DetailPane({ call, onResolved, onClose }: DetailPaneProps) {
  const [transcriptOpen, setTranscriptOpen] = useState(false)
  const [resolving, setResolving] = useState(false)
  const timeAgo = useTimeAgo(call?.received_at ?? "")

  if (!call) {
    return (
      <div className="flex h-full items-center justify-center rounded-card border border-[#E5E2DC] bg-white p-8 text-center text-[#6B6B6B]">
        Select a call to view details
      </div>
    )
  }

  const handleResolve = async () => {
    setResolving(true)
    try {
      const updated = await resolveCall(call.id)
      onResolved(updated)
    } finally {
      setResolving(false)
    }
  }

  const callbackHref = `tel:${call.from_number}`

  return (
    <div className="h-full overflow-y-auto rounded-card border border-[#E5E2DC] bg-white p-6 pb-24 md:pb-6">
      {onClose && (
        <button
          onClick={onClose}
          className="mb-4 flex items-center gap-1 text-sm text-[#6B6B6B] md:hidden"
        >
          <X className="h-4 w-4" /> Close
        </button>
      )}

      <h2 className="font-serif text-2xl font-medium text-[#1A1A1A]">
        {call.patient_name || "Unknown patient"}
      </h2>

      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[13px] text-[#6B6B6B]">
        {call.room && <span>Room {call.room}</span>}
        {call.caller_name && <span>&middot; {call.caller_name}</span>}
        {call.caller_role && <span>&middot; {call.caller_role}</span>}
        <span>&middot; {timeAgo}</span>
      </div>

      <div className="mt-4">
        <Badge variant={call.severity} className="px-3 py-1 text-sm">
          {SEVERITY_LABELS[call.severity]}
        </Badge>
        {call.resolved && (
          <Badge variant="outline" className="ml-2 px-3 py-1 text-sm">
            Handled
          </Badge>
        )}
      </div>

      <p className="mt-5 font-serif text-lg leading-relaxed text-[#1A1A1A]">{call.summary}</p>

      <p className="mt-3 text-sm italic text-[#6B6B6B]">{call.suggested_action}</p>

      <div className="mt-5">
        <audio controls src={audioUrl(call.id)} className="w-full" />
      </div>

      <div className="mt-5 border-t border-[#E5E2DC] pt-4">
        <button
          onClick={() => setTranscriptOpen((open) => !open)}
          className="flex w-full items-center justify-between text-sm font-medium text-[#1A1A1A]"
        >
          Transcript
          {transcriptOpen ? (
            <ChevronUp className="h-4 w-4" />
          ) : (
            <ChevronDown className="h-4 w-4" />
          )}
        </button>
        {transcriptOpen && (
          <p className="mt-3 whitespace-pre-wrap font-serif text-sm leading-relaxed text-[#1A1A1A]">
            {call.transcript || "No transcript available."}
          </p>
        )}
      </div>

      <div className="mt-5 border-t border-[#E5E2DC] pt-4 text-xs text-[#6B6B6B]">
        <div>
          Classified as <span className="font-medium">{call.request_type}</span> /{" "}
          <span className="font-medium">{call.urgency}</span>
        </div>
        <div className="mt-2 flex items-center gap-2">
          <span>Confidence</span>
          <div className="h-1.5 w-32 rounded-full bg-[#E5E2DC]">
            <div
              className="h-1.5 rounded-full bg-[#3A5FC7]"
              style={{ width: `${Math.round(call.confidence * 100)}%` }}
            />
          </div>
          <span>{Math.round(call.confidence * 100)}%</span>
        </div>
      </div>

      <div className="mt-6 flex flex-col gap-3">
        <Button asChild className="w-full">
          <a href={callbackHref}>
            <Phone className="h-4 w-4" />
            Call back {call.from_number}
          </a>
        </Button>
        <Button
          variant="secondary"
          className="w-full"
          disabled={call.resolved || resolving}
          onClick={handleResolve}
        >
          {call.resolved ? "Handled" : resolving ? "Marking..." : "Mark as handled"}
        </Button>
      </div>
    </div>
  )
}
