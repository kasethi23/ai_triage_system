import Foundation
import Observation

/// Shared source of truth for calls. Injected via the SwiftUI environment.
@Observable
@MainActor
final class CallStore {
    var calls: [Call] = []
    var lastError: String?

    private let api: APIClient

    init(api: APIClient = APIClient()) {
        self.api = api
    }

    func refresh() async {
        do {
            calls = try await api.listCalls()
            lastError = nil
        } catch {
            lastError = error.localizedDescription
        }
    }

    /// Returns the call from the cache, fetching it if unknown (e.g. arriving
    /// via a push deep link before the list has loaded).
    func call(id: Int) async -> Call? {
        if let cached = calls.first(where: { $0.id == id }) {
            return cached
        }
        do {
            let call = try await api.getCall(id: id)
            upsert(call)
            return call
        } catch {
            lastError = error.localizedDescription
            return nil
        }
    }

    /// Optimistically marks a call resolved; rolls back if the request fails.
    func resolve(_ call: Call) async -> Bool {
        guard let index = calls.firstIndex(where: { $0.id == call.id }) else { return false }
        let original = calls[index]
        calls[index].resolved = true
        do {
            let updated = try await api.resolveCall(id: call.id)
            upsert(updated)
            return true
        } catch {
            calls[index] = original
            lastError = error.localizedDescription
            return false
        }
    }

    private func upsert(_ call: Call) {
        if let index = calls.firstIndex(where: { $0.id == call.id }) {
            calls[index] = call
        } else {
            calls.append(call)
        }
    }

    // MARK: - Derived collections

    private func sorted(_ subset: [Call]) -> [Call] {
        subset.sorted {
            if $0.severity.sortRank != $1.severity.sortRank {
                return $0.severity.sortRank < $1.severity.sortRank
            }
            return $0.receivedAt > $1.receivedAt
        }
    }

    var unresolved: [Call] { sorted(calls.filter { !$0.resolved }) }
    var resolved: [Call] { sorted(calls.filter(\.resolved)) }
}
