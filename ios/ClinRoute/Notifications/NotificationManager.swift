import OSLog
import SwiftUI
import UserNotifications

/// Navigation state for push deep links: tapping a notification pushes the
/// call's detail view onto this path.
@Observable
@MainActor
final class Router {
    var path: [Int] = []

    func showCall(id: Int) {
        path = [id]
    }
}

@MainActor
final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    let router = Router()
    let store = CallStore()

    private let logger = Logger(subsystem: "com.clinroute.console", category: "push")

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        Task { await requestPushAuthorization() }
        return true
    }

    /// Ask for notification authorization and register with APNs. Runs on
    /// every launch — APNs tokens rotate, and registration re-delivers the
    /// current token to didRegisterForRemoteNotifications below.
    ///
    /// Note: time-sensitive delivery is granted by the app's Time Sensitive
    /// Notifications entitlement plus the payload's `interruption-level`;
    /// it is not a UNAuthorizationOptions flag.
    private func requestPushAuthorization() async {
        let center = UNUserNotificationCenter.current()
        do {
            let granted = try await center.requestAuthorization(options: [.alert, .sound, .badge])
            guard granted else {
                logger.info("Notification authorization denied")
                return
            }
            UIApplication.shared.registerForRemoteNotifications()
        } catch {
            logger.error("Notification authorization failed: \(error.localizedDescription)")
        }
    }

    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        Task {
            do {
                try await APIClient().registerDevice(token: token)
                logger.info("Device token registered with backend")
            } catch {
                logger.error("Device registration failed: \(error.localizedDescription)")
            }
        }
    }

    func application(
        _ application: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        logger.error("APNs registration failed: \(error.localizedDescription)")
    }

    // MARK: - UNUserNotificationCenterDelegate

    /// Foreground delivery: refresh the list and still show a banner.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        await store.refresh()
        return [.banner, .sound, .badge]
    }

    /// Notification tap: deep-link to the call in the payload's `call_id`.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse
    ) async {
        let userInfo = response.notification.request.content.userInfo
        if let callID = userInfo["call_id"] as? Int {
            router.showCall(id: callID)
        } else if let raw = userInfo["call_id"] as? String, let callID = Int(raw) {
            router.showCall(id: callID)
        }
    }
}
