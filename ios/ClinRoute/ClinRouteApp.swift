import SwiftUI

@main
struct ClinRouteApp: App {
    @State private var store = CallStore()

    var body: some Scene {
        WindowGroup {
            NavigationStack {
                CallListView()
            }
            .environment(store)
        }
    }
}
