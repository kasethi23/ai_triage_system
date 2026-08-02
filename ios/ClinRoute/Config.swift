import Foundation

/// Static app configuration.
///
/// TODO: a Settings screen is intentionally out of scope for now — edit these
/// constants to point at your backend before building.
enum Config {
    /// Base URL of the ClinRoute FastAPI backend (no trailing slash).
    /// Local dev: "http://localhost:8000". Railway: "https://<app>.up.railway.app".
    static let baseURL = URL(string: "http://localhost:8000")!

    /// Must match the backend's API_BEARER_TOKEN env var. Empty string works
    /// only against a tokenless local-dev backend.
    static let bearerToken = ""
}
