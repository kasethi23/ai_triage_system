import { useEffect, useRef, useState } from "react"
import { TopBar } from "@/components/TopBar"
import { CallCard } from "@/components/CallCard"
import { DetailPane } from "@/components/DetailPane"
import { CriticalAlert } from "@/components/CriticalAlert"
import { fetchCalls, subscribeToCallStream } from "@/lib/api"
import type { Call } from "@/types"

function App() {
  const [calls, setCalls] = useState<Call[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [newIds, setNewIds] = useState<Set<number>>(new Set())

  useEffect(() => {
    fetchCalls().then((data) => {
      setCalls(data)
      if (data.length > 0) setSelectedId((current) => current ?? data[0].id)
    })
  }, [])

  useEffect(() => {
    const unsubscribe = subscribeToCallStream((call) => {
      setCalls((prev) => {
        const existingIndex = prev.findIndex((c) => c.id === call.id)
        if (existingIndex >= 0) {
          const next = [...prev]
          next[existingIndex] = call
          return next
        }
        return [call, ...prev]
      })

      setNewIds((prev) => new Set(prev).add(call.id))
      setTimeout(() => {
        setNewIds((prev) => {
          const next = new Set(prev)
          next.delete(call.id)
          return next
        })
      }, 1500)

      setSelectedId((current) => current ?? call.id)
    })

    return unsubscribe
  }, [])

  const selectedCall = calls.find((c) => c.id === selectedId) ?? null

  const criticalCalls = calls.filter((c) => c.severity === "critical" && !c.resolved)

  const handleResolved = (updated: Call) => {
    setCalls((prev) => prev.map((c) => (c.id === updated.id ? updated : c)))
  }

  const scrollToFirstSevere = () => {
    if (criticalCalls.length === 0) return
    const el = document.getElementById(`call-card-${criticalCalls[0].id}`)
    el?.scrollIntoView({ behavior: "smooth", block: "center" })
    setSelectedId(criticalCalls[0].id)
  }

  const [detailOpenMobile, setDetailOpenMobile] = useState(false)
  const queueRef = useRef<HTMLDivElement>(null)

  const handleSelect = (id: number) => {
    setSelectedId(id)
    setDetailOpenMobile(true)
  }

  return (
    <div className="min-h-screen bg-[#FAF8F5]">
      <div className="mx-auto max-w-[1280px] px-4 md:px-6">
        <TopBar />

        <main className="grid gap-6 py-6 md:grid-cols-5">
          <section className="md:col-span-2">
            <h1 className="mb-3 font-sans text-sm font-semibold uppercase tracking-wide text-[#6B6B6B]">
              Live Alert Queue
            </h1>
            <div ref={queueRef} className="flex max-h-[calc(100vh-160px)] flex-col gap-3 overflow-y-auto pr-1">
              {calls.length === 0 && (
                <div className="rounded-card border border-[#E5E2DC] bg-white p-6 text-center text-sm text-[#6B6B6B]">
                  No calls yet.
                </div>
              )}
              {calls.map((call) => (
                <CallCard
                  key={call.id}
                  call={call}
                  selected={call.id === selectedId}
                  isNew={newIds.has(call.id)}
                  onSelect={() => handleSelect(call.id)}
                />
              ))}
            </div>
          </section>

          <section className="hidden md:col-span-3 md:block">
            <div className="h-[calc(100vh-96px)]">
              <DetailPane call={selectedCall} onResolved={handleResolved} />
            </div>
          </section>
        </main>
      </div>

      {/* Mobile full-screen detail overlay */}
      {detailOpenMobile && selectedCall && (
        <div className="fixed inset-0 z-40 bg-[#FAF8F5] p-4 md:hidden">
          <DetailPane
            call={selectedCall}
            onResolved={handleResolved}
            onClose={() => setDetailOpenMobile(false)}
          />
        </div>
      )}

      <CriticalAlert count={criticalCalls.length} onClick={scrollToFirstSevere} />
    </div>
  )
}

export default App
