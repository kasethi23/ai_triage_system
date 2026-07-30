import XCTest

/// Drives real gestures against the app (needs the local backend running on
/// localhost:8000 with seeded calls).
final class CallDetailScrollTests: XCTestCase {

    @MainActor
    func testDetailViewOpensAndScrolls() throws {
        let app = XCUIApplication()
        app.launch()

        // Open the first call row in the inbox.
        let row = app.descendants(matching: .any)
            .matching(NSPredicate(format: "identifier BEGINSWITH 'call-row-'"))
            .firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 10), "No call rows appeared")
        row.tap()

        // The action bar is fixed: Resolve must be visible without scrolling.
        let resolve = app.buttons["Resolve"]
        XCTAssertTrue(resolve.waitForExistence(timeout: 5), "Detail did not open (no Resolve bar)")
        XCTAssertTrue(resolve.isHittable, "Resolve is not hittable on open")

        // The transcript kicker sits below the fold; scrolling must reach it.
        let transcript = app.staticTexts["TRANSCRIPT"]
        var swipes = 0
        while !(transcript.exists && transcript.isHittable), swipes < 6 {
            app.swipeUp()
            swipes += 1
        }
        XCTAssertTrue(transcript.exists && transcript.isHittable,
                      "Could not scroll down to the transcript")

        // And back up: the tier tag row's Received line is at the very top.
        var backSwipes = 0
        let back = app.buttons["Unresolved"]
        while !(back.exists && back.isHittable), backSwipes < 6 {
            app.swipeDown()
            backSwipes += 1
        }
        XCTAssertTrue(back.exists && back.isHittable, "Could not scroll back to the top")

        // Back returns to the inbox.
        back.tap()
        XCTAssertTrue(row.waitForExistence(timeout: 5), "Did not return to the inbox")
    }
}
