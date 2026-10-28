// usage: alert <level 2|3> <count> <message> <title> <card-seconds> [focus-script focus-args...]
import AppKit
import QuartzCore
import CoreImage

let args = CommandLine.arguments
let level = args.count > 1 ? Int(args[1]) ?? 2 : 2
let count = max(1, args.count > 2 ? Int(args[2]) ?? 3 : 3)
let message = args.count > 3 ? args[3] : ""
let title = args.count > 4 && !args[4].isEmpty ? args[4] : (level >= 3 ? "需要你立刻处理" : "需要你操作")
let cardSeconds = args.count > 5 ? Double(args[5]) ?? 0 : 0
let focusCmd = Array(args.dropFirst(6))
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
    mask.contents = blurredRing(bounds.size, radius: radius)
    container.mask = mask
    return container
}

// 屏幕边缘一圈白色描边经高斯模糊，得到从边缘向内平滑衰减的遮罩
func blurredRing(_ size: CGSize, radius: CGFloat) -> CGImage? {
    let k: CGFloat = 0.25
    let w = Int(size.width * k), h = Int(size.height * k)
    let boost: CGFloat = urgent ? 1.35 : 1
    func ring(_ line: CGFloat, _ blur: CGFloat, _ alpha: CGFloat) -> CIImage? {
        guard let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                                  space: CGColorSpaceCreateDeviceRGB(),
                                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return nil }
        ctx.setStrokeColor(NSColor(white: 1, alpha: alpha).cgColor)
        ctx.setLineWidth(line * k * boost)
        ctx.addPath(CGPath(roundedRect: CGRect(x: 0, y: 0, width: w, height: h),
                           cornerWidth: radius * k, cornerHeight: radius * k, transform: nil))
        ctx.strokePath()
        guard let img = ctx.makeImage() else { return nil }
        return CIImage(cgImage: img).clampedToExtent()
            .applyingGaussianBlur(sigma: Double(blur * k * boost))
            .cropped(to: CGRect(x: 0, y: 0, width: w, height: h))
    }
    guard let wide = ring(140, 60, 0.75), let mid = ring(40, 16, 0.9), let core = ring(8, 3, 1) else { return nil }
    let out = core.composited(over: mid.composited(over: wide))
    return CIContext().createCGImage(out, from: out.extent)
}

final class ClickView: NSVisualEffectView {
    var onClick: () -> Void = {}
    override func mouseDown(with event: NSEvent) { onClick() }
    override func resetCursorRects() { addCursorRect(bounds, cursor: .pointingHand) }
}

func card(width: CGFloat, height: CGFloat) -> ClickView {
    let fx = ClickView(frame: CGRect(x: 0, y: 0, width: width, height: height))
    fx.material = .popover
    fx.blendingMode = .behindWindow
    fx.state = .active
    // 苹果推荐的圆角方式：maskImage 同时裁剪模糊背景，不会露出方角
    let r: CGFloat = 18
    let mask = NSImage(size: NSSize(width: r * 2 + 1, height: r * 2 + 1), flipped: false) { rect in
        NSColor.black.setFill()
        NSBezierPath(roundedRect: rect, xRadius: r, yRadius: r).fill()
        return true
    }
    mask.capInsets = NSEdgeInsets(top: r, left: r, bottom: r, right: r)
    mask.resizingMode = .stretch
    fx.maskImage = mask

    let icon = NSImageView()
    let symbol = urgent ? "exclamationmark.triangle.fill" : "hand.raised.fill"
    icon.image = NSImage(systemSymbolName: symbol, accessibilityDescription: nil)?
        .withSymbolConfiguration(.init(pointSize: 30, weight: .semibold).applying(.init(paletteColors: [palette[0], palette[1]])))
    fx.addSubview(icon)

    let titleLabel = NSTextField(labelWithString: title)
    titleLabel.font = .systemFont(ofSize: 20, weight: .semibold)
    titleLabel.textColor = .labelColor
    let body = NSTextField(wrappingLabelWithString: message)
    body.font = .systemFont(ofSize: 17, weight: .regular)
    body.textColor = .secondaryLabelColor
    body.maximumNumberOfLines = 2

    // 图标 + 文字作为一组，在卡片内水平、垂直都居中
    let iconSize: CGFloat = 40, gap: CGFloat = 16, lineGap: CGFloat = 4
    let maxText = width - 48 - iconSize - gap
    let tSize = titleLabel.sizeThatFits(NSSize(width: maxText, height: 100))
    body.preferredMaxLayoutWidth = maxText
    let bSize = message.isEmpty ? .zero : body.sizeThatFits(NSSize(width: maxText, height: 200))
    let textW = min(maxText, max(tSize.width, bSize.width))
    let textH = tSize.height + (message.isEmpty ? 0 : lineGap + bSize.height)
    let x0 = (width - (iconSize + gap + textW)) / 2
    let y0 = (height - textH) / 2
    icon.frame = CGRect(x: x0, y: (height - iconSize) / 2, width: iconSize, height: iconSize)
    titleLabel.frame = CGRect(x: x0 + iconSize + gap, y: y0 + textH - tSize.height, width: textW, height: tSize.height)
    if !message.isEmpty {
        body.frame = CGRect(x: x0 + iconSize + gap, y: y0, width: textW, height: bSize.height)
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

    w.orderFrontRegardless()
    windows.append(w)
}

func fadeOut(_ ws: [NSWindow], then: @escaping () -> Void = {}) {
    NSAnimationContext.runAnimationGroup({ c in
        c.duration = 0.4
        ws.forEach { $0.animator().alphaValue = 0 }
    }, completionHandler: { ws.forEach { $0.orderOut(nil) }; then() })
}

// 卡片只放主屏，可点击：点了切回对应终端 tab；独立于闪光，常驻 cardSeconds
if let main = NSScreen.screens.first {
    let width: CGFloat = min(680, main.frame.width - 80)
    let height: CGFloat = message.isEmpty ? 76 : 112
    let rect = CGRect(x: main.frame.midX - width / 2, y: main.visibleFrame.maxY - height - 16, width: width, height: height)
    let panel = NSPanel(contentRect: rect, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
    panel.isOpaque = false
    panel.backgroundColor = .clear
    panel.hasShadow = true
    panel.level = NSWindow.Level(rawValue: NSWindow.Level.screenSaver.rawValue + 1)
    panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
    let view = card(width: width, height: height)
    view.onClick = {
        if let script = focusCmd.first {
            let p = Process()
            p.executableURL = URL(fileURLWithPath: "/bin/bash")
            p.arguments = [script] + focusCmd.dropFirst()
            try? p.run()
        }
        fadeOut(windows + [panel]) { app.terminate(nil) }
    }
    panel.contentView = view
    panel.orderFrontRegardless()
    DispatchQueue.main.asyncAfter(deadline: .now() + max(total, cardSeconds)) {
        fadeOut([panel]) { app.terminate(nil) }
    }
}

DispatchQueue.main.asyncAfter(deadline: .now() + total) { fadeOut(windows) }
app.run()
