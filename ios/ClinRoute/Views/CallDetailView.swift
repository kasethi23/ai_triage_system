import SwiftUI

struct CallDetailView: View {
    let callID: Int

    @Environment(CallStore.self) private var store
    @State private var call: Call?
    @State private var player = VoicemailPlayer()
    @State private var isResolving = false

    var body: some View {
        Group {
            if let call {
                content(for: call)
            } else {
                ProgressView()
            }
        }
        .navigationTitle(call?.patientName ?? "Call")
        .navigationBarTitleDisplayMode(.inline)
        .task(id: callID) {
            call = await store.call(id: callID)
        }
        .onChange(of: store.calls) { _, _ in
            // Keep in sync with the shared store (e.g. after resolve).
            if let updated = store.calls.first(where: { $0.id == callID }) {
                call = updated
            }
        }
        .onDisappear {
            player.stop()
        }
    }

    @ViewBuilder
    private func content(for call: Call) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                card {
                    HStack {
                        SeverityBadge(severity: call.severity)
                        Spacer()
                        Text(call.relativeReceivedTime)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    detailRow("Patient", call.patientName)
                    if !call.room.isEmpty {
                        detailRow("Room", call.room)
                    }
                    if !call.callerName.isEmpty {
                        detailRow("Caller", callerDescription(call))
                    }
                    detailRow("Confidence", call.confidence.formatted(.percent.precision(.fractionLength(0))))
                }

                sectionHeader("Summary")
                card {
                    Text(call.summary)
                }

                if !call.suggestedAction.isEmpty {
                    sectionHeader("Suggested action")
                    card {
                        Text(call.suggestedAction)
                    }
                }

                sectionHeader("Recording")
                card {
                    Button {
                        Task { await player.toggle(callID: call.id) }
                    } label: {
                        if player.isLoading {
                            ProgressView()
                        } else {
                            Label(player.isPlaying ? "Pause" : "Play voicemail",
                                  systemImage: player.isPlaying ? "pause.circle.fill" : "play.circle.fill")
                        }
                    }
                    .disabled(player.isLoading)
                    if let message = player.errorMessage {
                        Text(message)
                            .font(.footnote)
                            .foregroundStyle(.red)
                    }
                }

                sectionHeader("Transcript")
                card {
                    Text(call.transcript.isEmpty ? "No transcript available." : call.transcript)
                        .font(.callout)
                        .foregroundStyle(call.transcript.isEmpty ? .secondary : .primary)
                }

                actionButtons(for: call)
            }
            .padding()
        }
        .background(Color(.systemGroupedBackground))
    }

    @ViewBuilder
    private func actionButtons(for call: Call) -> some View {
        VStack(spacing: 10) {
            if !call.resolved {
                Button {
                    Task {
                        isResolving = true
                        _ = await store.resolve(call)
                        isResolving = false
                    }
                } label: {
                    Group {
                        if isResolving {
                            ProgressView()
                        } else {
                            Label("Resolve", systemImage: "checkmark.circle.fill")
                        }
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .disabled(isResolving)
            } else {
                Label("Resolved", systemImage: "checkmark.circle.fill")
                    .foregroundStyle(.green)
                    .frame(maxWidth: .infinity)
            }

            if !call.fromNumber.isEmpty,
               let telURL = URL(string: "tel:\(call.fromNumber.filter { !$0.isWhitespace })") {
                Link(destination: telURL) {
                    Label("Call back \(call.fromNumber)", systemImage: "phone.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
            }
        }
        .padding(.top, 4)
    }

    // MARK: - Building blocks

    @ViewBuilder
    private func card(@ViewBuilder _ content: () -> some View) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            content()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 12))
    }

    private func sectionHeader(_ title: String) -> some View {
        Text(title)
            .font(.footnote.weight(.semibold))
            .foregroundStyle(.secondary)
            .textCase(.uppercase)
            .padding(.leading, 4)
    }

    private func detailRow(_ label: String, _ value: String) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label)
            Spacer()
            Text(value)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.trailing)
        }
    }

    private func callerDescription(_ call: Call) -> String {
        call.callerRole.isEmpty ? call.callerName : "\(call.callerName) (\(call.callerRole))"
    }
}
