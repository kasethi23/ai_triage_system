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
    /// Classifier flag: the transcript lacked the information needed to triage
    /// (best-guess severity only — surface for review, don't act blindly).
    let insufficientDetail: Bool
    /// Classifier flag: the caller explicitly said no response/callback is
    /// needed (a loop-closing FYI). Distinct from low severity.
    let noCallback: Bool
    let patientName: String
    let room: String
    let callerName: String
    let callerRole: String
    var resolved: Bool

    /// The default API payload is redacted by construction (backend privacy P4):
    /// `patient_name`, `room`, `caller_name`, and `caller_role` are omitted from
    /// `/calls`. Decode them when present, otherwise fall back to the copies the
    /// classifier left in `raw_classification_json`, then to empty defaults —
    /// never fail the whole payload over a redacted identifier.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(Int.self, forKey: .id)
        callSid = try c.decode(String.self, forKey: .callSid)
        fromNumber = try c.decode(String.self, forKey: .fromNumber)
        receivedAt = try c.decode(String.self, forKey: .receivedAt)
        audioPath = try c.decode(String.self, forKey: .audioPath)
        transcript = try c.decode(String.self, forKey: .transcript)
        urgency = try c.decode(String.self, forKey: .urgency)
        requestType = try c.decode(String.self, forKey: .requestType)
        confidence = try c.decode(Double.self, forKey: .confidence)
        summary = try c.decode(String.self, forKey: .summary)
        suggestedAction = try c.decode(String.self, forKey: .suggestedAction)
        rawClassificationJson = try c.decode(String.self, forKey: .rawClassificationJson)
        severity = try c.decode(Severity.self, forKey: .severity)
        insufficientDetail = try c.decodeIfPresent(Bool.self, forKey: .insufficientDetail) ?? false
        noCallback = try c.decodeIfPresent(Bool.self, forKey: .noCallback) ?? false
        resolved = try c.decode(Bool.self, forKey: .resolved)

        let raw = (try? JSONSerialization.jsonObject(with: Data(rawClassificationJson.utf8)))
            as? [String: Any] ?? [:]
        patientName = try c.decodeIfPresent(String.self, forKey: .patientName)
            ?? raw["patient_name"] as? String ?? "Unknown"
        room = try c.decodeIfPresent(String.self, forKey: .room)
            ?? raw["room"] as? String ?? ""
        callerName = try c.decodeIfPresent(String.self, forKey: .callerName)
            ?? raw["caller_name"] as? String ?? ""
        callerRole = try c.decodeIfPresent(String.self, forKey: .callerRole)
            ?? raw["caller_role"] as? String ?? ""
    }
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
