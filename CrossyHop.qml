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

  // Grid / iso — Crossy-like ~22.6° (atan(40/96)). Was 16° (too flat) / 27° (too steep).
  readonly property int cols: 9
  readonly property int rows: 7
  readonly property int tileW: 96
  readonly property int tileH: 40
  readonly property int playW: 900
  readonly property int playH: 480
  readonly property int roadRow1: 3
  readonly property int roadRow2: 4

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

  function isoX(col, row) {
    return (col - row) * tileW / 2 + playW / 2
  }

  function isoY(col, row) {
    return (col + row) * tileH / 2 + 36
  }

  function centerX(col, row) {
    return isoX(col, row) + tileW / 2
  }

  function centerY(col, row) {
    return isoY(col, row) + tileH / 2
  }

  function spawnCar(lane) {
    var row = lane === 1 ? roadRow1 : roadRow2
    var dir = lane === 1 ? 1 : -1
    // Kenney official preview PNGs (upright). Preview faces SW; flip = SE for dir=+1.
    // Unflipped SW stands in for NW until a real GLB bake is solid.
    var img = (lane === 1)
      ? (dir === 1 ? "assets/sprites/sedan-flip.png" : "assets/sprites/sedan.png")
      : (dir === 1 ? "assets/sprites/race-flip.png" : "assets/sprites/race.png")
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
    // Map input to iso grid movement
    var dc = 0, dr = 0
    if (dx > 0) { dc = 1; dr = -1 }
    else if (dx < 0) { dc = -1; dr = 1 }
    else if (dy > 0) { dc = 1; dr = 1 }
    else if (dy < 0) { dc = -1; dr = -1 }

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
    anchors { top: true; right: true; bottom: true; left: true }
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.namespace: "crossy-hop"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive

    Rectangle {
      anchors.fill: parent
      color: Qt.rgba(night.r, night.g, night.b, 0.72)
    }

    MouseArea {
      anchors.fill: parent
      onClicked: root.dismiss()
    }

    Item {
      id: gameFrame
      width: playW
      height: playH
      anchors.centerIn: parent
      scale: Math.min((panel.width - 32) / width, (panel.height - 32) / height)

      Rectangle {
        anchors.fill: parent
        color: sky
        border.color: Qt.rgba(ink.r, ink.g, ink.b, 0.45)
        border.width: 2
        radius: 4
      }

      Canvas {
        id: playfield
        anchors.fill: parent

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

        // Continuous Crossy-style parallelogram (hex union) for one road lane row.
        function drawRoadBand(ctx, row, fill) {
          var leftC = [root.centerX(1, row), root.centerY(1, row)]
          var rightC = [root.centerX(cols, row), root.centerY(cols, row)]
          ctx.save()
          ctx.beginPath()
          ctx.moveTo(leftC[0] - tileW / 2, leftC[1])
          ctx.lineTo(leftC[0], leftC[1] - tileH / 2)
          ctx.lineTo(rightC[0], rightC[1] - tileH / 2)
          ctx.lineTo(rightC[0] + tileW / 2, rightC[1])
          ctx.lineTo(rightC[0], rightC[1] + tileH / 2)
          ctx.lineTo(leftC[0], leftC[1] + tileH / 2)
          ctx.closePath()
          ctx.fillStyle = fill
          ctx.fill()
          ctx.restore()
        }

        onPaint: {
          var ctx = getContext("2d")
          ctx.reset()
          ctx.imageSmoothingEnabled = false

          var stroke = Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.12)

          // Grass diamonds (skip road rows — those are continuous bands)
          for (var r = 1; r <= rows; r++) {
            if (r === roadRow1 || r === roadRow2)
              continue
            for (var c = 1; c <= cols; c++) {
              var cx = root.isoX(c, r) + tileW / 2
              var cy = root.isoY(c, r) + tileH / 2
              drawDiamond(ctx, cx, cy, tileW, tileH, grass, stroke)
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

          // Instructions
          ctx.save()
          ctx.font = "bold 14px monospace"
          ctx.textAlign = "center"
          ctx.textBaseline = "middle"
          ctx.fillStyle = ink
          ctx.fillText("ARROWS / WASD  HOP    ESC  CLOSE    M  MUTE", playW / 2, playH - 18)
          ctx.restore()
        }
      }

      Repeater {
        model: root.cars.length
        Item {
          required property int index
          property var car: root.cars[index]
          x: { root.frame; return root.carScreenX(car) - car.w / 2 }
          y: { root.frame; return root.carScreenY(car) - car.h / 2 - 6 }
          width: car.w
          height: car.h
          z: { root.frame; return 3 + (car.lane === 2 ? 0.5 : 0) + car.t / 200 }

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
        source: Qt.resolvedUrl("assets/sprites/chick.png")
        smooth: false
        z: 4
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
