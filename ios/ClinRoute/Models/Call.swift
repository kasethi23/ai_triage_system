import SwiftUI

/// Severity tiers, mirroring `frontend/src/types.ts::Severity` and the classifier
/// schema. The raw values are the wire format: `critical | urgent | routine | fyi`.
enum Severity: String, Codable, CaseIterable {
    case critical
    case urgent
    case routine
    case fyi

    /// Unknown/legacy severity strings decode as `.fyi` rather than failing the
    /// whole payload.
    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = Severity(rawValue: raw) ?? .fyi
    }

    /// Sort order for the call list: most severe first.
    var sortRank: Int {
        switch self {
        case .critical: 0
        case .urgent: 1
        case .routine: 2
        case .fyi: 3
        }
    }

    var displayName: String {
        switch self {
        case .critical: "Critical"
        case .urgent: "Urgent"
        case .routine: "Routine"
        case .fyi: "FYI"
        }
    }

    var color: Color {
        switch self {
        case .critical: .red
        case .urgent: .orange
        case .routine: .blue
        case .fyi: .gray
        }
    }
}

/// Mirrors `frontend/src/types.ts::Call` exactly (snake_case JSON handled by
/// the decoder's `.convertFromSnakeCase` strategy in APIClient).
struct Call: Codable, Identifiable, Equatable {
    let id: Int
    let callSid: String
    let fromNumber: String
    let receivedAt: String
    let audioPath: String
    let transcript: String
    let urgency: String
    let requestType: String
    let confidence: Double
    let summary: String
    let suggestedAction: String
    let rawClassificationJson: String
    let severity: Severity
    let patientName: String
    let room: String
    let callerName: String
    let callerRole: String
    var resolved: Bool
}

extension Call {
    /// `received_at` is a Python `datetime.isoformat()` string; parse with a
    /// fractional-seconds ISO8601 formatter, falling back to whole seconds.
    private static let isoFractional: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    private static let isoWhole = ISO8601DateFormatter()

    var receivedDate: Date? {
        // Python emits microseconds (6 digits); trim to milliseconds for ISO8601DateFormatter.
        var value = receivedAt
        if let dotIndex = value.firstIndex(of: ".") {
            let afterDot = value.index(after: dotIndex)
            let fractionEnd = value[afterDot...].firstIndex { !$0.isNumber } ?? value.endIndex
            let fraction = value[afterDot..<fractionEnd]
            if fraction.count > 3 {
                value.replaceSubrange(afterDot..<fractionEnd, with: fraction.prefix(3))
            }
        }
        // The DB stores naive UTC timestamps; append Z when no offset is present.
        let timePart = value.split(separator: "T").last.map(String.init) ?? value
        if !timePart.contains("Z"), !timePart.contains("+"), !timePart.contains("-") {
            value += "Z"
        }
        return Self.isoFractional.date(from: value) ?? Self.isoWhole.date(from: value)
    }

    var relativeReceivedTime: String {
        guard let date = receivedDate else { return receivedAt }
        return date.formatted(.relative(presentation: .named))
    }

    /// "9:35" — the inbox time-column value.
    var arrivalClock: String {
        guard let date = receivedDate else { return "—" }
        return date.formatted(.dateTime.hour(.defaultDigits(amPM: .omitted)).minute())
    }

    /// "AM" / "PM" — the time-column unit line.
    var arrivalMeridiem: String {
        guard let date = receivedDate else { return "" }
        return date.formatted(.dateTime.hour(.defaultDigits(amPM: .wide))).filter(\.isLetter)
    }

    /// "6 min" / "3 h" / "12 d" — elapsed since arrival, for "waiting {elapsed}".
    var elapsedSinceArrival: String {
        guard let date = receivedDate else { return "" }
        let minutes = max(0, Int(Date.now.timeIntervalSince(date) / 60))
        if minutes < 60 { return "\(minutes) min" }
        let hours = minutes / 60
        if hours < 24 { return "\(hours) h" }
        return "\(hours / 24) d"
    }
}
