import Foundation
import Observation
import UserNotifications

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
            await syncBadge()
        } catch {
            lastError = error.localizedDescription
        }
    }

    /// Badge = unresolved critical+urgent count. The server sends the same
    /// number in push payloads; this keeps it current after local changes.
    private func syncBadge() async {
        let count = calls.filter {
            !$0.resolved && ($0.severity == .critical || $0.severity == .urgent)
        }.count
        try? await UNUserNotificationCenter.current().setBadgeCount(count)
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
            await syncBadge()
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

    // Inbox groups (design: oldest arrival first, consistently, in all groups).
    private func oldestFirst(_ severities: Set<Severity>) -> [Call] {
        calls.filter { !$0.resolved && severities.contains($0.severity) }
            .sorted { $0.receivedAt < $1.receivedAt }
    }

    var criticalGroup: [Call] { oldestFirst([.critical]) }
    var urgentGroup: [Call] { oldestFirst([.urgent]) }
    /// Routine and FYI merged — membership in the group is the signal.
    var laterGroup: [Call] { oldestFirst([.routine, .fyi]) }

    /// Badge = calls with a callback clock (critical + urgent), not total.
    var alertingCount: Int { criticalGroup.count + urgentGroup.count }
}
