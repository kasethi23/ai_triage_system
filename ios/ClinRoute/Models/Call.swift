import SwiftUI

/// Severity tiers, mirroring `frontend/src/types.ts::Severity` (the raw values
/// are the wire format). Product-facing labels map severe→Critical and
/// emergent→Urgent, matching the push notification titles from the backend.
enum Severity: String, Codable, CaseIterable {
    case severe
    case emergent
    case semiUrgent = "semi-urgent"
    case nonUrgent = "non-urgent"

    /// Unknown/legacy severity strings decode as `.nonUrgent` rather than
    /// failing the whole payload.
    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = Severity(rawValue: raw) ?? .nonUrgent
    }

    /// Sort order for the call list: most severe first.
    var sortRank: Int {
        switch self {
        case .severe: 0
        case .emergent: 1
        case .semiUrgent: 2
        case .nonUrgent: 3
        }
    }

    var displayName: String {
        switch self {
        case .severe: "Critical"
        case .emergent: "Urgent"
        case .semiUrgent: "Routine"
        case .nonUrgent: "FYI"
        }
    }

    var color: Color {
        switch self {
        case .severe: .red
        case .emergent: .orange
        case .semiUrgent: .blue
        case .nonUrgent: .gray
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
}
