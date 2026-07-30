import SwiftUI

/// Triage inbox (design `2a`), physician-facing: unresolved calls grouped by
/// urgency, oldest arrival first inside every group, fixed tab bar.
struct CallListView: View {
    @Environment(CallStore.self) private var store
    @Environment(\.scenePhase) private var scenePhase
    @State private var tab: Tab = .triage

    enum Tab { case triage, resolved }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                header
                if tab == .triage {
                    groupStack
                } else {
                    resolvedList
                }
            }
            .padding(.bottom, 100)  // last row clears the tab bar
        }
        .background(Organic.bg)
        .scrollIndicators(.hidden)
        .safeAreaInset(edge: .bottom, spacing: 0) { tabBar }
        .navigationDestination(for: Int.self) { callID in
            CallDetailView(callID: callID)
        }
        .toolbar(.hidden, for: .navigationBar)
        .refreshable { await store.refresh() }
        .task { await store.refresh() }
        .onChange(of: scenePhase) { _, newPhase in
            if newPhase == .active {
                Task { await store.refresh() }
            }
        }
    }

    // MARK: - Header block

    private var header: some View {
        VStack(alignment: .leading, spacing: Organic.space1) {
            HStack {
                Text("CLINROUTE")
                    .font(Organic.body(11, weight: .bold))
                    .tracking(Organic.kickerTracking)
                    .foregroundStyle(Organic.accent700)
                Spacer()
                Text("MD")
                    .font(Organic.body(13, weight: .bold))
                    .foregroundStyle(Organic.accent2_800)
                    .frame(width: 36, height: 36)
                    .background(Organic.accent2_200, in: Circle())
            }
            Text(tab == .triage ? "Unresolved" : "Resolved")
                .font(Organic.heading(38))
                .foregroundStyle(Organic.text)
            Text(summaryLine)
                .font(Organic.body(14))
                .foregroundStyle(Organic.neutral700)
        }
        .padding(EdgeInsets(top: Organic.space3, leading: Organic.space4,
                            bottom: Organic.space4, trailing: Organic.space4))
    }

    private var summaryLine: String {
        if tab == .resolved {
            return "\(store.resolved.count) resolved"
        }
        let critical = store.criticalGroup.count
        let urgent = store.urgentGroup.count
        let open = critical + urgent + store.laterGroup.count
        let oldest = (store.criticalGroup.first ?? store.urgentGroup.first ?? store.laterGroup.first)?
            .arrivalClock
        var line = "\(critical) critical · \(urgent) urgent · \(open) open"
        if let oldest { line += ", oldest \(oldest)" }
        return line
    }

    // MARK: - Group stack

    private var groupStack: some View {
        VStack(spacing: Organic.space3) {
            if let error = store.lastError {
                Text(error)
                    .font(Organic.body(12.5))
                    .foregroundStyle(Organic.neutral600)
                    .padding(.horizontal, Organic.space3)
            }
            if !store.criticalGroup.isEmpty {
                GroupCard(
                    style: .critical,
                    calls: store.criticalGroup,
                    icon: "exclamationmark.triangle",
                    title: "Critical",
                    note: "call back now"
                )
            }
            if !store.urgentGroup.isEmpty {
                GroupCard(
                    style: .urgent,
                    calls: store.urgentGroup,
                    icon: "clock",
                    title: "Urgent",
                    note: "this shift"
                )
            }
            if !store.laterGroup.isEmpty {
                GroupCard(
                    style: .later,
                    calls: store.laterGroup,
                    icon: "tray",
                    title: "Routine & FYI",
                    note: "\(store.laterGroup.count) waiting"
                )
            }
            if store.alertingCount == 0 && store.laterGroup.isEmpty && store.lastError == nil {
                Text("Nothing unresolved.")
                    .font(Organic.body(14))
                    .foregroundStyle(Organic.neutral600)
                    .frame(maxWidth: .infinity)
                    .padding(.top, Organic.space8)
            }
        }
        .padding(.horizontal, Organic.space3)
    }

    private var resolvedList: some View {
        VStack(spacing: Organic.space3) {
            if store.resolved.isEmpty {
                Text("Nothing resolved yet.")
                    .font(Organic.body(14))
                    .foregroundStyle(Organic.neutral600)
                    .frame(maxWidth: .infinity)
                    .padding(.top, Organic.space8)
            } else {
                GroupCard(
                    style: .later,
                    calls: store.resolved,
                    icon: "checkmark.circle",
                    title: "Resolved",
                    note: "\(store.resolved.count) done"
                )
            }
        }
        .padding(.horizontal, Organic.space3)
    }

    // MARK: - Tab bar

    private var tabBar: some View {
        HStack(spacing: 0) {
            tabItem("Triage", icon: "tray.full", tabValue: .triage, badge: store.alertingCount)
            tabItem("Resolved", icon: "checkmark.circle", tabValue: .resolved, badge: 0)
        }
        .padding(.top, 12)
        .frame(height: 84, alignment: .top)
        .frame(maxWidth: .infinity)
        .background(Organic.bg)
        .overlay(alignment: .top) {
            Rectangle().fill(Organic.divider).frame(height: 1)
        }
    }

    private func tabItem(_ label: String, icon: String, tabValue: Tab, badge: Int) -> some View {
        Button {
            tab = tabValue
        } label: {
            VStack(spacing: 5) {
                Image(systemName: icon)
                    .font(.system(size: 21, weight: .semibold))
                    .overlay(alignment: .topTrailing) {
                        if badge > 0 {
                            Text("\(badge)")
                                .font(Organic.body(10.5, weight: .bold))
                                .foregroundStyle(Organic.bg)
                                .padding(.horizontal, 4)
                                .frame(minWidth: 17, minHeight: 17)
                                .background(Organic.accent700, in: Capsule())
                                .offset(x: 9, y: -5)
                        }
                    }
                Text(label)
                    .font(Organic.body(10.5, weight: tab == tabValue ? .bold : .regular))
            }
            .foregroundStyle(tab == tabValue ? Organic.accent700 : Organic.neutral500)
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Group card

struct GroupCard: View {
    enum Style { case critical, urgent, later }

    let style: Style
    let calls: [Call]
    let icon: String
    let title: String
    let note: String

    var body: some View {
        VStack(spacing: 0) {
            headerStrip
            VStack(spacing: 0) {
                ForEach(Array(calls.enumerated()), id: \.element.id) { index, call in
                    NavigationLink(value: call.id) {
                        if style == .later {
                            CondensedRow(call: call)
                        } else {
                            CallRow(call: call, style: style)
                        }
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("call-row-\(call.id)")
                    .overlay(alignment: .top) {
                        if index > 0 {
                            Rectangle().fill(rowBorder).frame(height: 1)
                        }
                    }
                }
            }
            .padding(.horizontal, Organic.space3)
        }
        .background(cardBackground, in: RoundedRectangle(cornerRadius: Organic.radiusLg))
        .shadow(color: Organic.neutral900.opacity(0.14), radius: 2, y: 1)
    }

    private var cardBackground: Color {
        switch style {
        case .critical: Organic.accent100
        case .urgent: Organic.bg
        case .later: Organic.neutral100
        }
    }

    private var rowBorder: Color {
        style == .critical ? Organic.accent800.opacity(0.18) : Organic.divider
    }

    private var headerStrip: some View {
        HStack {
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .font(.system(size: 13, weight: .bold))
                Text(title.uppercased())
                    .font(Organic.body(11, weight: .bold))
                    .tracking(Organic.kickerTracking)
            }
            Spacer()
            Text(note)
                .font(Organic.body(11))
                .opacity(style == .critical ? 0.8 : 0.6)
        }
        .foregroundStyle(headerForeground)
        .padding(EdgeInsets(top: 13, leading: Organic.space3, bottom: 11, trailing: Organic.space3))
        .background(style == .critical ? Organic.accent700 : .clear)
    }

    private var headerForeground: Color {
        switch style {
        case .critical: Organic.bg
        case .urgent: Organic.accent800
        case .later: Organic.neutral700
        }
    }
}

// MARK: - Rows

/// Full row anatomy for Critical and Urgent groups.
struct CallRow: View {
    let call: Call
    let style: GroupCard.Style

    var body: some View {
        HStack(alignment: .top, spacing: Organic.space3) {
            TimeColumn(call: call, color: timeColor)
            VStack(alignment: .leading, spacing: 3) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(call.patientName)
                        .font(Organic.body(17, weight: .bold))
                        .foregroundStyle(Organic.text)
                    if !call.room.isEmpty {
                        Text("Rm \(call.room)")
                            .font(Organic.body(13))
                            .foregroundStyle(Organic.neutral600)
                    }
                    Spacer()
                }
                Text(call.summary)
                    .font(Organic.body(14.5))
                    .foregroundStyle(Organic.text)
                    .lineSpacing(2)
                    .fixedSize(horizontal: false, vertical: true)
                Text(callerLine)
                    .font(Organic.body(12.5))
                    .foregroundStyle(Organic.neutral600)
            }
        }
        .padding(EdgeInsets(top: 13, leading: 4, bottom: 15, trailing: 4))
        .contentShape(Rectangle())
    }

    private var timeColor: Color {
        style == .critical ? Organic.accent700 : Organic.accent600
    }

    private var callerLine: String {
        let caller = call.callerName.isEmpty ? call.callerRole : call.callerName
        let who = caller.isEmpty ? "Unknown caller" : caller
        return "\(who) · waiting \(call.elapsedSinceArrival)"
    }
}

/// Condensed row anatomy for the merged Routine & FYI group.
struct CondensedRow: View {
    let call: Call

    var body: some View {
        HStack(alignment: .center, spacing: Organic.space3) {
            TimeColumn(call: call, color: Organic.neutral500)
            VStack(alignment: .leading, spacing: 2) {
                Text(call.patientName)
                    .font(Organic.body(15, weight: .bold))
                    .foregroundStyle(Organic.text)
                Text(call.summary)
                    .font(Organic.body(13.5))
                    .foregroundStyle(Organic.neutral700)
                    .lineLimit(2)
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.right")
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(Organic.neutral500)
        }
        .padding(EdgeInsets(top: 11, leading: 4, bottom: 11, trailing: 4))
        .contentShape(Rectangle())
    }
}

/// 56px fixed arrival-time column: time 20/700 over meridiem 9.5 uppercase.
struct TimeColumn: View {
    let call: Call
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(call.arrivalClock)
                .font(Organic.body(20, weight: .bold))
                .foregroundStyle(color)
            Text(call.arrivalMeridiem)
                .font(Organic.body(9.5, weight: .bold))
                .tracking(0.85)
                .foregroundStyle(Organic.neutral600)
        }
        .frame(width: 56, alignment: .leading)
    }
}
