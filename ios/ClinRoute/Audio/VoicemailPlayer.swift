import AVFoundation
import Foundation
import Observation

/// Downloads a call's voicemail and plays it with AVAudioPlayer.
///
/// Download-then-play (rather than AVPlayer streaming) because the backend's
/// FileResponse doesn't support HTTP range requests, which AVPlayer requires
/// for progressive playback — and the recordings are small (<1 MB).
@Observable
@MainActor
final class VoicemailPlayer: NSObject, AVAudioPlayerDelegate {
    var isPlaying = false
    var isLoading = false
    var errorMessage: String?

    private var player: AVAudioPlayer?
    private var loadedCallID: Int?
    private let api = APIClient()

    func toggle(callID: Int) async {
        if isPlaying {
            player?.pause()
            isPlaying = false
            return
        }
        do {
            if player == nil || loadedCallID != callID {
                isLoading = true
                defer { isLoading = false }
                let data = try await api.audioData(for: callID)
                player = try AVAudioPlayer(data: data)
                player?.delegate = self
                loadedCallID = callID
            }
            // .playback so voicemails are audible even with the ring/silent
            // switch on silent — this is clinical content the user asked for.
            try AVAudioSession.sharedInstance().setCategory(.playback)
            try AVAudioSession.sharedInstance().setActive(true)
            player?.play()
            isPlaying = true
            errorMessage = nil
        } catch {
            errorMessage = "Playback failed: \(error.localizedDescription)"
            isPlaying = false
        }
    }

    func stop() {
        player?.stop()
        isPlaying = false
    }

    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor in
            isPlaying = false
        }
    }
}
