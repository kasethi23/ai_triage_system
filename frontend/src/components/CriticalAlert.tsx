import { AlertTriangle } from "lucide-react"

interface CriticalAlertProps {
  count: number
  onClick: () => void
}

export function CriticalAlert({ count, onClick }: CriticalAlertProps) {
  if (count === 0) return null

  return (
    <button
      onClick={onClick}
      className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-full bg-[#C73E3A] px-5 py-3 text-sm font-semibold text-white shadow-lg transition-transform hover:scale-105"
    >
      <AlertTriangle className="h-4 w-4" />
      Critical Queue: Action Required ({count})
    </button>
  )
}
