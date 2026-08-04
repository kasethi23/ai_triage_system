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

    /// Fetches the re-identified record (privacy P7 — the access is audited
    /// server-side). Deliberately NOT cached into `calls`: the list stays
    /// redacted; only the requesting view holds the identified copy.
    func identifiedCall(id: Int) async -> Call? {
        do {
            return try await api.getIdentifiedCall(id: id)
        } catch {
            lastError = error.localizedDescription
            return nil
        }
    }

    /// Records a physician severity override (correction feedback loop) and
    /// applies the server's updated record.
    func correct(_ call: Call, severity: Severity) async -> Bool {
        do {
            let updated = try await api.correctCall(id: call.id, label: severity.rawValue)
            upsert(updated)
            await syncBadge()
            return true
        } catch {
            lastError = error.localizedDescription
            return false
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
    // Insufficient-detail calls are excluded here — their severity is a best
    // guess, so they get their own group (`needsReviewGroup`) instead.
    private func oldestFirst(_ severities: Set<Severity>) -> [Call] {
        calls.filter { !$0.resolved && !$0.insufficientDetail && severities.contains($0.severity) }
            .sorted { $0.receivedAt < $1.receivedAt }
    }

    var criticalGroup: [Call] { oldestFirst([.critical]) }
    var urgentGroup: [Call] { oldestFirst([.urgent]) }
    /// Routine and FYI merged — membership in the group is the signal.
    var laterGroup: [Call] { oldestFirst([.routine, .fyi]) }
    /// Calls the classifier could not reliably triage (insufficient_detail):
    /// severity is unknown, so they need a callback to clarify rather than a
    /// place in the severity ranking.
    var needsReviewGroup: [Call] {
        calls.filter { !$0.resolved && $0.insufficientDetail }
            .sorted { $0.receivedAt < $1.receivedAt }
    }

    /// Badge = calls with a callback clock (critical + urgent), not total.
    var alertingCount: Int { criticalGroup.count + urgentGroup.count }
}
