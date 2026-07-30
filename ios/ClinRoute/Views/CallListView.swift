import SwiftUI

struct CallListView: View {
    @Environment(CallStore.self) private var store
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        List {
            if let error = store.lastError {
                Section {
                    Label(error, systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.secondary)
                        .font(.footnote)
                }
            }
            if !store.unresolved.isEmpty {
                Section("Unresolved") {
                    ForEach(store.unresolved) { call in
                        NavigationLink(value: call.id) {
                            CallRow(call: call)
                        }
                    }
                }
            }
            if !store.resolved.isEmpty {
                Section("Resolved") {
                    ForEach(store.resolved) { call in
                        NavigationLink(value: call.id) {
                            CallRow(call: call)
                        }
                    }
                }
            }
            if store.calls.isEmpty && store.lastError == nil {
                ContentUnavailableView(
                    "No calls yet",
                    systemImage: "phone.badge.waveform",
                    description: Text("New calls appear here as they come in.")
                )
            }
        }
        .navigationTitle("ClinRoute")
        .navigationDestination(for: Int.self) { callID in
            CallDetailView(callID: callID)
        }
        .refreshable { await store.refresh() }
        .task { await store.refresh() }
        .onChange(of: scenePhase) { _, newPhase in
            if newPhase == .active {
                Task { await store.refresh() }
            }
        }
    }
}

struct CallRow: View {
    let call: Call

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                SeverityBadge(severity: call.severity)
                Spacer()
                Text(call.relativeReceivedTime)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Text(call.patientName)
                .font(.headline)
            HStack(spacing: 6) {
                if !call.room.isEmpty {
                    Text(call.room)
                }
                if !call.room.isEmpty && !call.callerRole.isEmpty {
                    Text("·")
                }
                if !call.callerRole.isEmpty {
                    Text(call.callerRole)
                }
            }
            .font(.subheadline)
            .foregroundStyle(.secondary)
        }
        .padding(.vertical, 2)
        .opacity(call.resolved ? 0.6 : 1)
    }
}

struct SeverityBadge: View {
    let severity: Severity

    var body: some View {
        Text(severity.displayName.uppercased())
            .font(.caption2.weight(.bold))
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(severity.color.opacity(0.15), in: Capsule())
            .foregroundStyle(severity.color)
    }
}
