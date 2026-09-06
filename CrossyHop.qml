import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.Commons

Item {
  id: root

  property var shell: null
  property var manifest: null
  property bool opened: false
  property bool muted: false

  // Grid / iso — Crossy dimetric defaults (not true iso): pitch 40°, yaw -26° (user-matched).
  readonly property int cols: 9
  readonly property int rows: 7
  property real isoAngleDeg: 40
  property real tileW: 96
  property real tileH: tileW * Math.tan(isoAngleDeg * Math.PI / 180)
  readonly property int playW: 900
  readonly property int playH: 480
  readonly property int roadRow1: 3
  readonly property int roadRow2: 4
  // View chrome: scale = window size; ROT is baked into isoX/isoY (card stays full + upright).
  // [ ] angle (road steepness)   ; ' rotation   - = size
  property real viewScale: 0.62
  property real viewRotationDeg: -26
  property int winW: Math.round(playW * viewScale + 32)
  property int winH: Math.round(playH * viewScale + 56)

  // Theme colors
  readonly property color ink: Color.foreground || "#d8dee9"
  readonly property color night: Color.background || "#1e1e2e"
  readonly property color accent: Color.accent || "#89b4fa"
  readonly property color hush: Color.muted || "#6c7086"
  readonly property color sky: Qt.tint(night, Qt.rgba(accent.r, accent.g, accent.b, 0.18))
  readonly property color grass: Qt.tint(night, Qt.rgba(0.35, 0.78, 0.40, 0.55))
  readonly property color road: Qt.tint(night, Qt.rgba(ink.r, ink.g, ink.b, 0.45))
  readonly property color roadMark: Qt.lighter(road, 1.6)

  // Game state
  property int chickCol: 5
  property int chickRow: 6
  property real hopZ: 0
  property var cars: []
  property real spawnTimer1: 0
  property real spawnTimer2: 0
  property real lastTick: 0
  property int frame: 0

  readonly property string pluginId: "io.github.tomfaulkner.crossy-hop"

  function open(payloadJson) {
    opened = true
    chickCol = 5
    chickRow = 6
    hopZ = 0
    cars = []
    spawnTimer1 = 0
    spawnTimer2 = 0
    lastTick = Date.now()
    // Pre-warm traffic so lanes are busy immediately.
    spawnCar(1)
    cars[cars.length - 1].t = cols * 0.25
    spawnCar(2)
    cars[cars.length - 1].t = cols * 0.75
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
    playfield.requestPaint()
  }

  function close() {
    opened = false
  }

  function dismiss() {
    close()
    if (shell && typeof shell.hide === "function") shell.hide(pluginId)
  }

  function toggle() {
    if (opened) dismiss()
    else open("{}")
  }

  function toggleMute() {
    muted = !muted
  }

  function nudgeAngle(delta) {
    isoAngleDeg = Math.round((Math.max(8, Math.min(50, isoAngleDeg + delta))) * 10) / 10
    frame++
    playfield.requestPaint()
  }

  function nudgeView(delta) {
    viewScale = Math.round((Math.max(0.35, Math.min(0.95, viewScale + delta))) * 100) / 100
  }

  function nudgeRotation(delta) {
    viewRotationDeg = Math.round((Math.max(-45, Math.min(45, viewRotationDeg + delta))) * 10) / 10
    frame++
    playfield.requestPaint()
  }

  function angleLabel() {
    return isoAngleDeg.toFixed(1) + "°"
  }

  function rotationLabel() {
    return viewRotationDeg.toFixed(1) + "°"
  }

  // Iso cell centers in local space, then ROT around the grid centroid and
  // uniform fit so the whole board stays inside the upright play card.
  function isoLocal(col, row) {
    return {
      x: (col - row) * tileW / 2,
      y: (col + row) * tileH / 2
    }
  }

  function gridCentroidLocal() {
    return isoLocal((1 + cols) / 2, (1 + rows) / 2)
  }

  // Screen-space transform for a local iso point (rotate about centroid, fit, center).
  function projectLocal(lx, ly) {
    var mid = gridCentroidLocal()
    var x = lx - mid.x
    var y = ly - mid.y
    var r = viewRotationDeg * Math.PI / 180
    var c = Math.cos(r), s = Math.sin(r)
    var xr = x * c - y * s
    var yr = x * s + y * c

    // AABB of all cell centers after rotation → fit inside play area with padding.
    var minX = 1e9, maxX = -1e9, minY = 1e9, maxY = -1e9
    for (var row = 1; row <= rows; row++) {
      for (var col = 1; col <= cols; col++) {
        var p = isoLocal(col, row)
        var px = (p.x - mid.x) * c - (p.y - mid.y) * s
        var py = (p.x - mid.x) * s + (p.y - mid.y) * c
        if (px < minX) minX = px
        if (px > maxX) maxX = px
        if (py < minY) minY = py
        if (py > maxY) maxY = py
      }
    }
    // Include diamond half-extents so tiles aren't clipped at edges.
    var pad = Math.max(tileW, tileH) * 0.75
    var bw = (maxX - minX) + pad * 2
    var bh = (maxY - minY) + pad * 2
    var fit = Math.min((playW * 0.92) / bw, (playH * 0.88) / bh)
    return {
      x: xr * fit + playW / 2,
      y: yr * fit + playH / 2
    }
  }

  function centerX(col, row) {
    var p = isoLocal(col, row)
    return projectLocal(p.x, p.y).x
  }

  function centerY(col, row) {
    var p = isoLocal(col, row)
    return projectLocal(p.x, p.y).y
  }

  // Kept for any leftover callers; same as cell center (diamonds draw from center).
  function isoX(col, row) { return centerX(col, row) }
  function isoY(col, row) { return centerY(col, row) }

  function spawnCar(lane) {
    var row = lane === 1 ? roadRow1 : roadRow2
    var dir = lane === 1 ? 1 : -1
    // Bacon MagicaVoxel SE/NW facings (tools/bake_bacon_blender.py). No xScale flip.
    // Variety: orange / blue / green; facing by travel dir (e = SE, w = NW).
    var palette = ["orange", "blue", "green"]
    var color = palette[Math.floor(Math.random() * palette.length)]
    var facing = (dir === 1) ? "e" : "w"
    var img = "assets/baked/bacon/" + color + "-" + facing + ".png"
    var t = dir === 1 ? -1 : cols + 2
    var speed = 1.2 + Math.random() * 1.0
    if (lane === 2) speed += 0.6
    var car = {
      t: t,
      row: row,
      w: 88,
      h: 88,
      dir: dir,
      speed: speed,
      image: img,
      lane: lane,
      mirror: false
    }
    cars.push(car)
  }

  function carScreenX(car) {
    return centerX(car.t, car.row)
  }

  function carScreenY(car) {
    return centerY(car.t, car.row)
  }

  function moveChick(dx, dy) {
    // Crossy controls relative to the road:
    // up/down = perpendicular (change row); left/right = parallel (change col).
    var dc = dx
    var dr = dy
    var nc = chickCol + dc
    var nr = chickRow + dr
    if (nc >= 1 && nc <= cols && nr >= 1 && nr <= rows) {
      chickCol = nc
      chickRow = nr
      hopAnim.restart()
    }
  }

  function step(dt) {
    // Spawn cars
    spawnTimer1 += dt
    spawnTimer2 += dt
    if (spawnTimer1 > 1.6 + Math.random() * 1.2) {
      spawnCar(1)
      spawnTimer1 = 0
    }
    if (spawnTimer2 > 1.0 + Math.random() * 0.9) {
      spawnCar(2)
      spawnTimer2 = 0
    }

    // Move cars along their lane
    var alive = []
    for (var i = 0; i < cars.length; i++) {
      var c = cars[i]
      c.t += c.dir * c.speed * dt
      if (c.t > -2 && c.t < cols + 3) alive.push(c)
    }
    cars = alive
    frame++
    playfield.requestPaint()
  }

  Component.onCompleted: {
    // Pre-warm a couple of cars so the road isn't empty on first open.
    spawnCar(1)
    cars[0].t = cols * 0.30
    spawnCar(2)
    cars[1].t = cols * 0.70
  }

  Timer {
    interval: 16
    repeat: true
    running: root.opened
    onTriggered: {
      var now = Date.now()
      var dt = (now - root.lastTick) / 1000
      root.lastTick = now
      root.step(dt)
    }
  }

  PanelWindow {
    id: panel
    visible: root.opened
    // Fullscreen layer, fully clear — only the scaled game card occludes the desktop.
    anchors { top: true; right: true; bottom: true; left: true }
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.namespace: "crossy-hop"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive

    MouseArea {
      anchors.fill: parent
      onClicked: root.dismiss()
    }

    Item {
      id: gameFrame
      width: playW
      height: playH
      anchors.centerIn: parent
      scale: root.viewScale
      transformOrigin: Item.Center
      clip: true

      // Block dismiss when interacting with the game card.
      MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
        onClicked: keyCatcher.forceActiveFocus()
      }

      Rectangle {
        anchors.fill: parent
        color: sky
        border.color: Qt.rgba(ink.r, ink.g, ink.b, 0.45)
        border.width: 2
        radius: 4
        z: 0
      }

      Canvas {
        id: playfield
        anchors.fill: parent
        z: 1

        function drawDiamond(ctx, cx, cy, w, h, fill, stroke) {
          ctx.save()
          ctx.beginPath()
          ctx.moveTo(cx, cy - h / 2)
          ctx.lineTo(cx + w / 2, cy)
          ctx.lineTo(cx, cy + h / 2)
          ctx.lineTo(cx - w / 2, cy)
          ctx.closePath()
          ctx.fillStyle = fill
          ctx.fill()
          if (stroke) {
            ctx.strokeStyle = stroke
            ctx.lineWidth = 1
            ctx.stroke()
          }
          ctx.restore()
        }

        // Road band as a thick strip along the lane row (uses projected cell centers).
        function drawRoadBand(ctx, row, fill) {
          var leftC = [root.centerX(1, row), root.centerY(1, row)]
          var rightC = [root.centerX(cols, row), root.centerY(cols, row)]
          var dx = rightC[0] - leftC[0]
          var dy = rightC[1] - leftC[1]
          var len = Math.sqrt(dx * dx + dy * dy) || 1
          var nx = -dy / len
          var ny = dx / len
          var half = Math.max(18, Math.min(tileH, tileW) * 0.28)
          var extend = half * 1.2
          var x0 = leftC[0] - (dx / len) * extend
          var y0 = leftC[1] - (dy / len) * extend
          var x1 = rightC[0] + (dx / len) * extend
          var y1 = rightC[1] + (dy / len) * extend
          ctx.save()
          ctx.beginPath()
          ctx.moveTo(x0 + nx * half, y0 + ny * half)
          ctx.lineTo(x1 + nx * half, y1 + ny * half)
          ctx.lineTo(x1 - nx * half, y1 - ny * half)
          ctx.lineTo(x0 - nx * half, y0 - ny * half)
          ctx.closePath()
          ctx.fillStyle = fill
          ctx.fill()
          ctx.restore()
        }

        onPaint: {
          var ctx = getContext("2d")
          ctx.reset()
          ctx.imageSmoothingEnabled = false

          // Full-card ground so ROT never leaves empty sky holes around the grid.
          ctx.fillStyle = grass
          ctx.fillRect(0, 0, playW, playH)

          var stroke = Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.12)

          // Grass diamonds (skip road rows — those are continuous bands)
          for (var r = 1; r <= rows; r++) {
            if (r === roadRow1 || r === roadRow2)
              continue
            for (var c = 1; c <= cols; c++) {
              var cx = root.centerX(c, r)
              var cy = root.centerY(c, r)
              // Diamond size scales with fit roughly via tileW/H; keep readable.
              drawDiamond(ctx, cx, cy, tileW * 0.55, tileH * 0.55, grass, stroke)
            }
          }

          // Two-lane road as continuous parallelogram strips (Crossy-like)
          drawRoadBand(ctx, roadRow1, road)
          drawRoadBand(ctx, roadRow2, road)

          // Subtle seam between the two road rows
          ctx.save()
          ctx.strokeStyle = Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.18)
          ctx.lineWidth = 1
          ctx.beginPath()
          var seamRow = (roadRow1 + roadRow2) / 2
          ctx.moveTo(root.centerX(0.2, seamRow), root.centerY(0.2, seamRow))
          ctx.lineTo(root.centerX(cols + 0.8, seamRow), root.centerY(cols + 0.8, seamRow))
          ctx.stroke()
          ctx.restore()

          // Road center dashed line along the isometric road diagonal
          // (between roadRow1 / roadRow2, left → right of the lane strip)
          ctx.save()
          ctx.strokeStyle = roadMark
          ctx.lineWidth = 2
          ctx.setLineDash([14, 12])
          ctx.beginPath()
          var midRow = (roadRow1 + roadRow2) / 2
          ctx.moveTo(root.centerX(0.0, midRow), root.centerY(0.0, midRow))
          ctx.lineTo(root.centerX(cols + 1.0, midRow), root.centerY(cols + 1.0, midRow))
          ctx.stroke()
          ctx.setLineDash([])
          ctx.restore()

          // (ANGLE/ROT HUD is drawn upright on gameFrame, not in the rotated world)
        }
      }

      Repeater {
        model: root.cars.length
        Item {
          required property int index
          property var car: root.cars[index]
          // Sprites are baked for ROT 0°; spin them with viewRotationDeg so noses
          // stay aligned with the road when ROT is nonzero (e.g. -26°).
          x: { root.frame; return root.carScreenX(car) - car.w / 2 }
          y: { root.frame; return root.carScreenY(car) - car.h / 2 - 6 }
          width: car.w
          height: car.h
          z: { root.frame; return 3 + (car.lane === 2 ? 0.5 : 0) + car.t / 200 }
          rotation: root.viewRotationDeg
          transformOrigin: Item.Center

          Image {
            anchors.fill: parent
            source: Qt.resolvedUrl(car.image)
            smooth: false
            fillMode: Image.PreserveAspectFit
          }
        }
      }

      Image {
        id: chick
        x: root.centerX(chickCol, chickRow) - 40
        y: root.centerY(chickCol, chickRow) - 56 - hopZ
        width: 80
        height: 80
        source: Qt.resolvedUrl("assets/baked/bacon/chicken-ne.png")
        smooth: false
        z: 4
        rotation: root.viewRotationDeg
        transformOrigin: Item.Center
      }

      // Upright HUD (does not spin with ROT)
      Column {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.margins: 14
        spacing: 4
        z: 20
        Text {
          text: "ANGLE  " + root.angleLabel()
          color: accent
          font.pixelSize: 22
          font.bold: true
          font.family: "monospace"
        }
        Text {
          text: "ROT    " + root.rotationLabel()
          color: accent
          font.pixelSize: 22
          font.bold: true
          font.family: "monospace"
        }
        Text {
          text: "[ ] angle  ; ' rot  - = size  ESC close"
          color: ink
          font.pixelSize: 12
          font.family: "monospace"
        }
      }

      Text {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 12
        z: 20
        text: "ARROWS / WASD  HOP    M  MUTE"
        color: ink
        font.pixelSize: 14
        font.bold: true
        font.family: "monospace"
      }

      NumberAnimation {
        id: hopAnim
        target: root
        property: "hopZ"
        from: 0
        to: 16
        duration: 120
        easing.type: Easing.OutQuad
        onFinished: reverseAnim.start()
      }
      NumberAnimation {
        id: reverseAnim
        target: root
        property: "hopZ"
        from: 16
        to: 0
        duration: 120
        easing.type: Easing.InQuad
      }

      Item {
        id: keyCatcher
        anchors.fill: parent
        focus: true

        Keys.priority: Keys.BeforeItem
        Keys.onPressed: function(event) {
          if (event.key === Qt.Key_Escape) root.dismiss()
          else if (event.key === Qt.Key_M) root.toggleMute()
          else if (event.key === Qt.Key_BracketLeft) root.nudgeAngle(-0.5)
          else if (event.key === Qt.Key_BracketRight) root.nudgeAngle(0.5)
          else if (event.key === Qt.Key_Semicolon) root.nudgeRotation(-1)
          else if (event.key === Qt.Key_Apostrophe) root.nudgeRotation(1)
          else if (event.key === Qt.Key_Minus || event.key === Qt.Key_Underscore) root.nudgeView(-0.05)
          else if (event.key === Qt.Key_Equal || event.key === Qt.Key_Plus) root.nudgeView(0.05)
          else if (event.key === Qt.Key_Left || event.key === Qt.Key_A) root.moveChick(-1, 0)
          else if (event.key === Qt.Key_Right || event.key === Qt.Key_D) root.moveChick(1, 0)
          else if (event.key === Qt.Key_Up || event.key === Qt.Key_W) root.moveChick(0, -1)
          else if (event.key === Qt.Key_Down || event.key === Qt.Key_S) root.moveChick(0, 1)
          else return
          event.accepted = true
        }

        onActiveFocusChanged: {
          if (!activeFocus && root.opened) Qt.callLater(function() { if (root.opened) keyCatcher.forceActiveFocus() })
        }
      }
    }
  }
}
