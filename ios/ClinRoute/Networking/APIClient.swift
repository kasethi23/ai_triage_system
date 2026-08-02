import Foundation

enum APIError: Error, LocalizedError {
    case invalidResponse
    case httpStatus(Int)
    case decoding(Error)
    case network(Error)

    var errorDescription: String? {
        switch self {
        case .invalidResponse: "Invalid response from server."
        case .httpStatus(let code): "Server returned HTTP \(code)."
        case .decoding: "Could not decode the server response."
        case .network(let error): error.localizedDescription
        }
    }
}

/// Async/await client for the ClinRoute backend. Base URL and bearer token
/// are injected (default: Config constants).
struct APIClient {
    let baseURL: URL
    let bearerToken: String
    let session: URLSession

    init(baseURL: URL = Config.baseURL,
         bearerToken: String = Config.bearerToken,
         session: URLSession = .shared) {
        self.baseURL = baseURL
        self.bearerToken = bearerToken
        self.session = session
    }

    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()

    // MARK: - Endpoints

    func listCalls(limit: Int = 100) async throws -> [Call] {
        try await get("calls", query: [URLQueryItem(name: "limit", value: String(limit))])
    }

    func getCall(id: Int) async throws -> Call {
        try await get("calls/\(id)")
    }

    func resolveCall(id: Int) async throws -> Call {
        try await send("calls/\(id)/resolve", method: "PATCH")
    }

    @discardableResult
    func registerDevice(token: String) async throws -> [String: String?] {
        struct Registration: Encodable {
            let token: String
            let platform: String
        }
        var request = makeRequest(path: "devices", method: "POST")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(Registration(token: token, platform: "ios"))
        let data = try await perform(request)
        return (try? JSONSerialization.jsonObject(with: data) as? [String: String?]) ?? [:]
    }

    /// URL of a call's audio endpoint.
    func audioURL(for callID: Int) -> URL {
        baseURL.appending(path: "calls/\(callID)/audio")
    }

    /// Downloads a call's voicemail audio (bearer-authenticated). Recordings
    /// are small WAVs, so download-then-play beats streaming — the backend
    /// doesn't support the range requests AVPlayer streaming needs.
    func audioData(for callID: Int) async throws -> Data {
        try await perform(makeRequest(path: "calls/\(callID)/audio", method: "GET"))
    }

    var authHeaders: [String: String] {
        bearerToken.isEmpty ? [:] : ["Authorization": "Bearer \(bearerToken)"]
    }

    // MARK: - Plumbing

    private func makeRequest(path: String, method: String, query: [URLQueryItem] = []) -> URLRequest {
        var url = baseURL.appending(path: path)
        if !query.isEmpty {
            url.append(queryItems: query)
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        if !bearerToken.isEmpty {
            request.setValue("Bearer \(bearerToken)", forHTTPHeaderField: "Authorization")
        }
        return request
    }

    private func get<T: Decodable>(_ path: String, query: [URLQueryItem] = []) async throws -> T {
        let data = try await perform(makeRequest(path: path, method: "GET", query: query))
        return try decode(data)
    }

    private func send<T: Decodable>(_ path: String, method: String) async throws -> T {
        let data = try await perform(makeRequest(path: path, method: method))
        return try decode(data)
    }

    private func perform(_ request: URLRequest) async throws -> Data {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.network(error)
        }
        guard let http = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        guard (200..<300).contains(http.statusCode) else {
            throw APIError.httpStatus(http.statusCode)
        }
        return data
    }

    private func decode<T: Decodable>(_ data: Data) throws -> T {
        do {
            return try Self.decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decoding(error)
        }
    }
}
