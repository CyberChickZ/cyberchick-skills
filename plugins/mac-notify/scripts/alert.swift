// usage: alert <level 2|3> <count> [message] [title]
import AppKit
import QuartzCore

let args = CommandLine.arguments
let level = args.count > 1 ? Int(args[1]) ?? 2 : 2
let count = max(1, args.count > 2 ? Int(args[2]) ?? 3 : 3)
let message = args.count > 3 ? args[3] : ""
let title = args.count > 4 && !args[4].isEmpty ? args[4] : (level >= 3 ? "需要你立刻处理" : "需要你操作")
let urgent = level >= 3
let period = urgent ? 0.9 : 1.6
let total = period * Double(count)

let palette: [NSColor] = urgent
    ? [.init(srgbRed: 1, green: 0.23, blue: 0.19, alpha: 1), .init(srgbRed: 1, green: 0.55, blue: 0.1, alpha: 1),
       .init(srgbRed: 1, green: 0.18, blue: 0.45, alpha: 1), .init(srgbRed: 1, green: 0.23, blue: 0.19, alpha: 1)]
    : [.init(srgbRed: 0.35, green: 0.55, blue: 1, alpha: 1), .init(srgbRed: 0.75, green: 0.4, blue: 1, alpha: 1),
       .init(srgbRed: 1, green: 0.45, blue: 0.6, alpha: 1), .init(srgbRed: 1, green: 0.7, blue: 0.3, alpha: 1),
       .init(srgbRed: 0.35, green: 0.55, blue: 1, alpha: 1)]

let app = NSApplication.shared
app.setActivationPolicy(.accessory)

func snapshot(_ index: Int) -> CGImage? {
    let path = NSTemporaryDirectory() + "mac-notify-\(getpid())-\(index).png"
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
    p.arguments = ["-x", "-D", "\(index + 1)", path]
    try? p.run()
    p.waitUntilExit()
    defer { try? FileManager.default.removeItem(atPath: path) }
    return NSImage(contentsOfFile: path)?.cgImage(forProposedRect: nil, context: nil, hints: nil)
}

func breathe(from: Double, to: Double) -> CABasicAnimation {
    let a = CABasicAnimation(keyPath: "opacity")
    a.fromValue = from
    a.toValue = to
    a.duration = period / 2
    a.autoreverses = true
    a.repeatCount = Float(count)
    a.timingFunction = CAMediaTimingFunction(controlPoints: 0.45, 0, 0.55, 1)
    a.fillMode = .forwards
    a.isRemovedOnCompletion = false
    return a
}

func edgeGlow(_ bounds: CGRect, radius: CGFloat) -> CALayer {
    let container = CALayer()
    container.frame = bounds
    let diag = hypot(bounds.width, bounds.height)
    let grad = CAGradientLayer()
    grad.type = .conic
    grad.colors = palette.map(\.cgColor)
    grad.startPoint = CGPoint(x: 0.5, y: 0.5)
    grad.endPoint = CGPoint(x: 0.5, y: 0)
    grad.bounds = CGRect(x: 0, y: 0, width: diag, height: diag)
    grad.position = CGPoint(x: bounds.midX, y: bounds.midY)
    let spin = CABasicAnimation(keyPath: "transform.rotation.z")
    spin.fromValue = 0
    spin.toValue = -2 * Double.pi
    spin.duration = urgent ? 2.5 : 6
    spin.repeatCount = .infinity
    grad.add(spin, forKey: "spin")
    container.addSublayer(grad)

    let mask = CALayer()
    mask.frame = bounds
    let path = CGPath(roundedRect: bounds, cornerWidth: radius, cornerHeight: radius, transform: nil)
    for (width, alpha) in [(160.0, 0.07), (100.0, 0.14), (60.0, 0.26), (32.0, 0.5), (14.0, 0.85), (6.0, 1.0)] {
        let s = CAShapeLayer()
        s.path = path
        s.fillColor = nil
        s.strokeColor = NSColor(white: 1, alpha: alpha).cgColor
        s.lineWidth = width * (urgent ? 1.3 : 1)
        mask.addSublayer(s)
    }
    container.mask = mask
    return container
}

func card(in frame: CGRect, scale: CGFloat) -> NSView {
    let width: CGFloat = min(560, frame.width - 80)
    let height: CGFloat = message.isEmpty ? 64 : 92
    let fx = NSVisualEffectView(frame: CGRect(x: (frame.width - width) / 2, y: frame.height - height - 64, width: width, height: height))
    fx.material = .hudWindow
    fx.blendingMode = .withinWindow
    fx.state = .active
    fx.appearance = NSAppearance(named: .vibrantDark)
    fx.wantsLayer = true
    fx.layer?.cornerRadius = 22
    fx.layer?.cornerCurve = .continuous
    fx.layer?.masksToBounds = true
    fx.layer?.borderWidth = 0.5
    fx.layer?.borderColor = NSColor(white: 1, alpha: 0.18).cgColor

    let icon = NSImageView(frame: CGRect(x: 20, y: (height - 34) / 2, width: 34, height: 34))
    let symbol = urgent ? "exclamationmark.triangle.fill" : "hand.raised.fill"
    icon.image = NSImage(systemSymbolName: symbol, accessibilityDescription: nil)?
        .withSymbolConfiguration(.init(pointSize: 26, weight: .semibold).applying(.init(paletteColors: [palette[0], palette[1]])))
    fx.addSubview(icon)

    let textX: CGFloat = 70
    let titleLabel = NSTextField(labelWithString: title)
    titleLabel.font = .systemFont(ofSize: 17, weight: .semibold)
    titleLabel.textColor = .white
    let body = NSTextField(wrappingLabelWithString: message)
    body.font = .systemFont(ofSize: 14, weight: .regular)
    body.textColor = NSColor(white: 1, alpha: 0.78)
    body.maximumNumberOfLines = 2
    if message.isEmpty {
        titleLabel.frame = CGRect(x: textX, y: (height - 22) / 2, width: width - textX - 20, height: 22)
    } else {
        titleLabel.frame = CGRect(x: textX, y: height - 40, width: width - textX - 20, height: 22)
        body.frame = CGRect(x: textX, y: 14, width: width - textX - 20, height: 40)
        fx.addSubview(body)
    }
    fx.addSubview(titleLabel)

    return fx
}

var windows: [NSWindow] = []
for (i, screen) in NSScreen.screens.enumerated() {
    let shot = urgent ? snapshot(i) : nil
    let frame = screen.frame
    let w = NSWindow(contentRect: frame, styleMask: .borderless, backing: .buffered, defer: false)
    w.isOpaque = false
    w.backgroundColor = .clear
    w.level = .screenSaver
    w.ignoresMouseEvents = true
    w.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
    w.hasShadow = false

    let bounds = CGRect(origin: .zero, size: frame.size)
    let view = NSView(frame: bounds)
    view.wantsLayer = true
    let root = view.layer!
    w.contentView = view

    if let shot {
        let img = CALayer()
        img.frame = bounds
        img.contents = shot
        root.addSublayer(img)
        let shake = CAKeyframeAnimation(keyPath: "transform.translation.x")
        shake.values = [0, -28, 24, -18, 12, -6, 3, 0]
        shake.keyTimes = [0, 0.1, 0.22, 0.36, 0.5, 0.66, 0.82, 1]
        shake.duration = period * 0.7
        let group = CAAnimationGroup()
        group.animations = [shake]
        group.duration = period
        group.repeatCount = Float(count)
        img.add(group, forKey: "shake")

        let flash = CALayer()
        flash.frame = bounds
        flash.backgroundColor = NSColor.white.cgColor
        flash.opacity = 0
        root.addSublayer(flash)
        let blink = CAKeyframeAnimation(keyPath: "opacity")
        blink.values = [0, 0.45, 0, 0]
        blink.keyTimes = [0, 0.08, 0.4, 1]
        blink.duration = period
        blink.repeatCount = Float(count)
        flash.add(blink, forKey: "flash")
    }

    let glow = edgeGlow(bounds, radius: 14)
    glow.opacity = 0
    root.addSublayer(glow)
    glow.add(breathe(from: 0.45, to: 1), forKey: "breathe")

    view.addSubview(card(in: frame, scale: screen.backingScaleFactor))
    w.orderFrontRegardless()
    windows.append(w)
}

DispatchQueue.main.asyncAfter(deadline: .now() + total) {
    NSAnimationContext.runAnimationGroup({ c in
        c.duration = 0.4
        windows.forEach { $0.animator().alphaValue = 0 }
    }, completionHandler: { app.terminate(nil) })
}
app.run()
