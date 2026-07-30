import SwiftUI

/// The Organic design system tokens, from the ClinRoute design handoff
/// (design_handoff_clinroute_triage/organic.css). Warm paper ground,
/// terracotta accent, olive secondary. Never hard-code these hexes at call
/// sites — add a token here instead.
enum Organic {

    // MARK: - Color

    /// App ground, cards, on-dark foreground.
    static let bg = Color(hex: 0xF5EAD8)
    /// Detail header.
    static let surface = Color(hex: 0xEBDDC5)
    /// Body text.
    static let text = Color(hex: 0x201E1D)
    /// Hairlines, secondary button border.
    static let divider = Color(hex: 0x201E1D).opacity(0.16)

    // Terracotta accent ramp — critical tier, primary actions.
    static let accent100 = Color(hex: 0xFFF2EB)
    static let accent200 = Color(hex: 0xFFE1D0)
    static let accent300 = Color(hex: 0xFFC6A5)
    static let accent400 = Color(hex: 0xF6A06B)
    static let accent = Color(hex: 0xC67139)
    static let accent600 = Color(hex: 0xB2622D)
    static let accent700 = Color(hex: 0x8C491A)
    static let accent800 = Color(hex: 0x643312)
    static let accent900 = Color(hex: 0x402310)

    // Olive secondary ramp — escalation promise, routine tier, avatar.
    static let accent2_100 = Color(hex: 0xF0FAE1)
    static let accent2_200 = Color(hex: 0xE1EECC)
    static let accent2_700 = Color(hex: 0x56633F)
    static let accent2_800 = Color(hex: 0x3D472B)
    static let accent2_900 = Color(hex: 0x272E1B)

    // Neutral ramp — group fill, muted text, inactive tabs.
    static let neutral100 = Color(hex: 0xF9F4ED)
    static let neutral200 = Color(hex: 0xEEE7DB)
    static let neutral300 = Color(hex: 0xDCD3C4)
    static let neutral400 = Color(hex: 0xC0B6A5)
    static let neutral500 = Color(hex: 0xA19786)
    static let neutral600 = Color(hex: 0x82796A)
    static let neutral700 = Color(hex: 0x645C50)
    static let neutral800 = Color(hex: 0x474238)
    static let neutral900 = Color(hex: 0x2E2B25)

    // MARK: - Spacing scale (steps 1, 2, 3, 4, 6, 8)

    static let space1: CGFloat = 4.4
    static let space2: CGFloat = 8.8
    static let space3: CGFloat = 13.2
    static let space4: CGFloat = 17.6
    static let space6: CGFloat = 26.4
    static let space8: CGFloat = 35.2

    // MARK: - Radius

    static let radiusSm: CGFloat = 8
    static let radiusMd: CGFloat = 16
    static let radiusLg: CGFloat = 28
    static let radiusPill: CGFloat = 999

    // MARK: - Type

    /// Headings: Caprasimo 400. Falls back to the system serif if the bundled
    /// font fails to register.
    static func heading(_ size: CGFloat) -> Font {
        .custom("Caprasimo-Regular", size: size)
    }

    /// Body: Figtree.
    static func body(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        weight == .bold || weight == .heavy
            ? .custom("Figtree-Bold", size: size)
            : .custom("Figtree-Regular", size: size)
    }

    /// Kicker style companion values: 11px, uppercase, +0.1em tracking, bold.
    static let kickerTracking: CGFloat = 1.1  // 0.1em of 11px
}

extension Severity {
    /// Organic tier colors: Critical accent-700, Urgent accent-600,
    /// Routine accent-2-700, FYI neutral-600.
    var organicColor: Color {
        switch self {
        case .severe: Organic.accent700
        case .emergent: Organic.accent600
        case .semiUrgent: Organic.accent2_700
        case .nonUrgent: Organic.neutral600
        }
    }
}

extension Color {
    init(hex: UInt32) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255
        )
    }
}
