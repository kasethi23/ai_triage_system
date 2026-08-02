import SwiftUI

@main
struct ClinRouteApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        WindowGroup {
            RootView(router: appDelegate.router)
                .environment(appDelegate.store)
        }
    }
}

/// Hosts the NavigationStack bound to the Router path so push-notification
/// taps can deep-link straight to a call's detail view.
private struct RootView: View {
    @Bindable var router: Router

    var body: some View {
        NavigationStack(path: $router.path) {
            CallListView()
        }
    }
}
