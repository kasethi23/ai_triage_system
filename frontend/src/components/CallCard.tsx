import { useEffect, useState } from "react"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { useTimeAgo } from "@/hooks/useTimeAgo"
import { SEVERITY_LABELS } from "@/lib/severity"
import { cn } from "@/lib/utils"
import type { Call } from "@/types"

interface CallCardProps {
  call: Call
  selected: boolean
  isNew: boolean
  onSelect: () => void
}

export function CallCard({ call, selected, isNew, onSelect }: CallCardProps) {
  const timeAgo = useTimeAgo(call.received_at)
  const [highlight, setHighlight] = useState(isNew)

  useEffect(() => {
    if (!isNew) return
    const timeout = setTimeout(() => setHighlight(false), 1500)
    return () => clearTimeout(timeout)
  }, [isNew])

  return (
    <Card
      id={`call-card-${call.id}`}
      onClick={onSelect}
      className={cn(
        "cursor-pointer p-4 transition-colors",
        isNew && "animate-slide-in",
        highlight && "animate-highlight-fade",
        selected ? "border-2 border-[#3A5FC7]" : "border border-[#E5E2DC]",
        call.resolved && "opacity-60"
      )}
    >
      <div className="mb-2 flex items-center justify-between">
        <Badge variant={call.severity}>{SEVERITY_LABELS[call.severity]}</Badge>
        <span className="font-mono text-xs text-[#6B6B6B]">{timeAgo}</span>
      </div>
      <div className="font-sans text-base font-bold text-[#1A1A1A]">
        {call.patient_name || "Unknown patient"}
      </div>
      {call.room && (
        <div className="font-mono text-[13px] text-[#6B6B6B]">Room {call.room}</div>
      )}
      <p className="mt-2 font-serif text-sm text-[#1A1A1A]">{call.summary}</p>
    </Card>
  )
}
