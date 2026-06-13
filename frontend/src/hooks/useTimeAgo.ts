import { useEffect, useState } from "react"

function formatTimeAgo(isoDate: string): string {
  if (!isoDate) return ""
  const then = new Date(isoDate + (isoDate.endsWith("Z") ? "" : "Z")).getTime()
  const now = Date.now()
  const seconds = Math.max(0, Math.floor((now - then) / 1000))

  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export function useTimeAgo(isoDate: string): string {
  const [label, setLabel] = useState(() => formatTimeAgo(isoDate))

  useEffect(() => {
    setLabel(formatTimeAgo(isoDate))
    const interval = setInterval(() => {
      setLabel(formatTimeAgo(isoDate))
    }, 1000)
    return () => clearInterval(interval)
  }, [isoDate])

  return label
}
