import SwiftUI

/// Message detail (design `2a` overlay), physician-facing: everything needed
/// for the callback on one screen — summary, suggested action, recording,
/// full uncropped transcript — with a fixed Call back / Resolve action bar.
struct CallDetailView: View {
    let callID: Int

    @Environment(CallStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @State private var call: Call?
    @State private var player = VoicemailPlayer()
    @State private var isResolving = false

    var body: some View {
        Group {
            if let call {
                content(for: call)
            } else {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Organic.bg)
            }
        }
        .toolbar(.hidden, for: .navigationBar)
        .task(id: callID) {
            call = await store.call(id: callID)
        }
        .onChange(of: store.calls) { _, _ in
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
            VStack(alignment: .leading, spacing: 0) {
                header(for: call)
                body(for: call)
            }
        }
        .background(Organic.bg)
        .scrollIndicators(.hidden)
        .safeAreaInset(edge: .bottom, spacing: 0) { actionBar(for: call) }
    }

    // MARK: - Header (surface background)

    private func header(for call: Call) -> some View {
        VStack(alignment: .leading, spacing: Organic.space3) {
            Button {
                dismiss()
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "chevron.left")
                        .font(.system(size: 15, weight: .bold))
                    Text("Unresolved")
                        .font(Organic.body(15, weight: .bold))
                }
                .foregroundStyle(Organic.accent700)
            }
            .buttonStyle(.plain)

            HStack(spacing: Organic.space2) {
                Text(call.severity.displayName.uppercased())
                    .font(Organic.body(10.5, weight: .bold))
                    .tracking(0.84)
                    .foregroundStyle(Organic.bg)
                    .padding(.horizontal, 9)
                    .padding(.vertical, 4)
                    .background(call.severity.organicColor, in: Capsule())
                Text("Received \(call.arrivalClock) \(call.arrivalMeridiem) · \(call.elapsedSinceArrival) ago")
                    .font(Organic.body(13, weight: .bold))
                    .foregroundStyle(call.severity.organicColor)
            }

            Text(call.patientName)
                .font(Organic.heading(34))
                .foregroundStyle(Organic.text)

            Text(contextLine(for: call))
                .font(Organic.body(14))
                .foregroundStyle(Organic.neutral700)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(EdgeInsets(top: 2, leading: Organic.space4,
                            bottom: Organic.space4, trailing: Organic.space4))
        .background(Organic.surface)
    }

    private func contextLine(for call: Call) -> String {
        var parts: [String] = []
        if !call.room.isEmpty { parts.append("Rm \(call.room)") }
        if !call.callerName.isEmpty {
            parts.append(call.callerRole.isEmpty
                         ? call.callerName
                         : "\(call.callerName) (\(call.callerRole))")
        }
        parts.append("confidence \(call.confidence.formatted(.percent.precision(.fractionLength(0))))")
        return parts.joined(separator: " · ")
    }

    // MARK: - Body sections

    private func body(for call: Call) -> some View {
        VStack(alignment: .leading, spacing: Organic.space4) {
            section("Why it's \(call.severity.displayName)") {
                Text(call.summary)
                    .font(Organic.body(15.5))
                    .lineSpacing(3)
            }

            if !call.suggestedAction.isEmpty {
                section("Suggested action") {
                    Text(call.suggestedAction)
                        .font(Organic.body(15.5))
                        .lineSpacing(3)
                }
            }

            section("Recording") {
                VStack(alignment: .leading, spacing: Organic.space2) {
                    Button {
                        Task { await player.toggle(callID: call.id) }
                    } label: {
                        HStack(spacing: 8) {
                            if player.isLoading {
                                ProgressView()
                            } else {
                                Image(systemName: player.isPlaying ? "pause.circle.fill" : "play.circle.fill")
                                    .font(.system(size: 22))
                            }
                            Text(player.isPlaying ? "Pause" : "Play voicemail")
                                .font(Organic.body(15, weight: .bold))
                        }
                        .foregroundStyle(Organic.accent700)
                    }
                    .buttonStyle(.plain)
                    .disabled(player.isLoading)
                    .accessibilityLabel(player.isPlaying ? "Pause" : "Play voicemail")

                    if let message = player.errorMessage {
                        Text(message)
                            .font(Organic.body(12.5))
                            .foregroundStyle(Organic.accent800)
                    }
                }
            }

            // Design rule carried from 1c: the transcript is never cropped.
            section("Transcript") {
                Text(call.transcript.isEmpty ? "No transcript available." : call.transcript)
                    .font(Organic.body(16))
                    .lineSpacing(6)
                    .foregroundStyle(call.transcript.isEmpty ? Organic.neutral600 : Organic.text)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(Organic.space4)
    }

    @ViewBuilder
    private func section(_ kicker: String, @ViewBuilder _ body: () -> some View) -> some View {
        VStack(alignment: .leading, spacing: Organic.space2) {
            Text(kicker.uppercased())
                .font(Organic.body(11, weight: .bold))
                .tracking(Organic.kickerTracking)
                .foregroundStyle(Organic.neutral600)
            body()
                .foregroundStyle(Organic.text)
        }
    }

    // MARK: - Action bar

    private func actionBar(for call: Call) -> some View {
        HStack(spacing: Organic.space2) {
            if let telURL = telURL(for: call) {
                Link(destination: telURL) {
                    HStack(spacing: 8) {
                        Image(systemName: "phone.fill")
                            .font(.system(size: 16, weight: .semibold))
                        Text("Call back")
                            .font(Organic.body(16, weight: .bold))
                    }
                    .foregroundStyle(Organic.bg)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 15)
                    .background(call.severity.organicColor, in: RoundedRectangle(cornerRadius: Organic.radiusMd))
                }
                .frame(maxWidth: .infinity)
                .layoutPriority(2)
            }

            Button {
                Task {
                    isResolving = true
                    let ok = await store.resolve(call)
                    isResolving = false
                    if ok { dismiss() }
                }
            } label: {
                Group {
                    if isResolving {
                        ProgressView()
                    } else {
                        Text(call.resolved ? "Resolved" : "Resolve")
                            .font(Organic.body(16, weight: .bold))
                    }
                }
                .foregroundStyle(call.resolved ? Organic.neutral500 : Organic.text)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 15)
                .overlay(
                    RoundedRectangle(cornerRadius: Organic.radiusMd)
                        .strokeBorder(Organic.divider, lineWidth: 1)
                )
            }
            .buttonStyle(.plain)
            .disabled(isResolving || call.resolved)
            .frame(width: 110)
        }
        .padding(EdgeInsets(top: Organic.space3, leading: Organic.space4,
                            bottom: Organic.space2, trailing: Organic.space4))
        .background(Organic.bg)
        .overlay(alignment: .top) {
            Rectangle().fill(Organic.divider).frame(height: 1)
        }
    }

    private func telURL(for call: Call) -> URL? {
        guard !call.fromNumber.isEmpty else { return nil }
        return URL(string: "tel:\(call.fromNumber.filter { !$0.isWhitespace })")
    }
}
