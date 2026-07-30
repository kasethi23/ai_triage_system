import AVFoundation
import SwiftUI

struct CallDetailView: View {
    let callID: Int

    @Environment(CallStore.self) private var store
    @State private var call: Call?
    @State private var player: AVPlayer?
    @State private var isPlaying = false
    @State private var isResolving = false

    private let api = APIClient()

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
            player?.pause()
        }
    }

    @ViewBuilder
    private func content(for call: Call) -> some View {
        List {
            Section {
                HStack {
                    SeverityBadge(severity: call.severity)
                    Spacer()
                    Text(call.relativeReceivedTime)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                LabeledContent("Patient", value: call.patientName)
                if !call.room.isEmpty {
                    LabeledContent("Room", value: call.room)
                }
                if !call.callerName.isEmpty {
                    LabeledContent("Caller", value: callerDescription(call))
                }
                LabeledContent("Confidence", value: call.confidence.formatted(.percent.precision(.fractionLength(0))))
            }

            Section("Summary") {
                Text(call.summary)
            }

            if !call.suggestedAction.isEmpty {
                Section("Suggested action") {
                    Text(call.suggestedAction)
                }
            }

            Section("Recording") {
                Button {
                    togglePlayback(for: call)
                } label: {
                    Label(isPlaying ? "Pause" : "Play voicemail",
                          systemImage: isPlaying ? "pause.circle.fill" : "play.circle.fill")
                }
            }

            Section("Transcript") {
                Text(call.transcript.isEmpty ? "No transcript available." : call.transcript)
                    .font(.callout)
                    .foregroundStyle(call.transcript.isEmpty ? .secondary : .primary)
            }

            Section {
                if !call.resolved {
                    Button {
                        Task {
                            isResolving = true
                            _ = await store.resolve(call)
                            isResolving = false
                        }
                    } label: {
                        if isResolving {
                            ProgressView()
                                .frame(maxWidth: .infinity)
                        } else {
                            Label("Resolve", systemImage: "checkmark.circle.fill")
                                .frame(maxWidth: .infinity)
                        }
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
            .listRowBackground(Color.clear)
        }
    }

    private func callerDescription(_ call: Call) -> String {
        call.callerRole.isEmpty ? call.callerName : "\(call.callerName) (\(call.callerRole))"
    }

    private func togglePlayback(for call: Call) {
        if let player, isPlaying {
            player.pause()
            isPlaying = false
            return
        }
        if player == nil {
            // Attach the bearer header at the asset layer — AVPlayer streams
            // the protected audio endpoint directly.
            let asset = AVURLAsset(
                url: api.audioURL(for: call.id),
                options: ["AVURLAssetHTTPHeaderFieldsKey": api.authHeaders]
            )
            player = AVPlayer(playerItem: AVPlayerItem(asset: asset))
        }
        player?.play()
        isPlaying = true
    }
}
