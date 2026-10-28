// usage: notifier <title> <subtitle> <message> [focus-script focus-args...]
import AppKit
import UserNotifications

let args = CommandLine.arguments
func arg(_ i: Int) -> String { args.count > i ? args[i] : "" }

final class Delegate: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate {
    func applicationDidFinishLaunching(_ n: Notification) {
        let center = UNUserNotificationCenter.current()
        center.delegate = self
        if args.count < 4 { return }
        center.requestAuthorization(options: [.alert, .sound]) { granted, _ in
            guard granted else { exit(1) }
            let c = UNMutableNotificationContent()
            c.title = arg(1)
            c.subtitle = arg(2)
            c.body = arg(3)
            c.sound = UNNotificationSound(named: UNNotificationSoundName("Glass"))
            c.userInfo = ["focus": Array(args.dropFirst(4))]
            center.removeAllDeliveredNotifications()
            center.add(UNNotificationRequest(identifier: "latest", content: c, trigger: nil)) { _ in
                DispatchQueue.main.asyncAfter(deadline: .now() + 1) { exit(0) }
            }
        }
    }

    func userNotificationCenter(_ c: UNUserNotificationCenter, willPresent n: UNNotification,
                                withCompletionHandler h: @escaping (UNNotificationPresentationOptions) -> Void) {
        h([.banner, .sound])
    }

    func userNotificationCenter(_ c: UNUserNotificationCenter, didReceive r: UNNotificationResponse,
                                withCompletionHandler h: @escaping () -> Void) {
        if let focus = r.notification.request.content.userInfo["focus"] as? [String], let script = focus.first {
            let p = Process()
            p.executableURL = URL(fileURLWithPath: "/bin/bash")
            p.arguments = [script] + focus.dropFirst()
            try? p.run()
            p.waitUntilExit()
        }
        h()
        exit(0)
    }
}

let app = NSApplication.shared
let delegate = Delegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
DispatchQueue.main.asyncAfter(deadline: .now() + 30) { exit(0) }
app.run()
