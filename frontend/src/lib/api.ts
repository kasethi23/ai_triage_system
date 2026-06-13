import type { Call } from "@/types"

// Use the same host the page was loaded from (works for localhost,
// LAN IP, or a tunnel), with the backend's port.
export const API_BASE = `${window.location.protocol}//${window.location.hostname}:8000`

export async function fetchCalls(): Promise<Call[]> {
  const res = await fetch(`${API_BASE}/calls`)
  if (!res.ok) throw new Error(`Failed to fetch calls: ${res.status}`)
  return res.json()
}

export async function resolveCall(id: number): Promise<Call> {
  const res = await fetch(`${API_BASE}/calls/${id}/resolve`, { method: "PATCH" })
  if (!res.ok) throw new Error(`Failed to resolve call: ${res.status}`)
  return res.json()
}

export function audioUrl(id: number): string {
  return `${API_BASE}/calls/${id}/audio`
}

export function subscribeToCallStream(onCall: (call: Call) => void): () => void {
  const source = new EventSource(`${API_BASE}/calls/stream`)

  source.onmessage = (event) => {
    try {
      const call: Call = JSON.parse(event.data)
      onCall(call)
    } catch {
      // ignore malformed events
    }
  }

  return () => source.close()
}
