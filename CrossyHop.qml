import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons

Item {
  id: root

  property var shell: null
  property var manifest: null
  property bool opened: false
  property bool muted: false
  property int hopCount: 0
  property int bootId: 0

  // Crash diagnostics — every 2nd hop appends a line here (and console.warn).
  readonly property string homeDir: Quickshell.env("HOME") || ""
  readonly property string stateHome: Quickshell.env("XDG_STATE_HOME") || (homeDir + "/.local/state")
  readonly property string debugDir: stateHome + "/crossy-hop"
  readonly property string debugLogPath: debugDir + "/hop-debug.log"

  // Grid / iso — Crossy dimetric defaults (not true iso): pitch 40°, yaw -26° (user-matched).
  // `rows` is the sliding window height: only ~9 rows of the infinite world exist at a time.
  readonly property int cols: 9
  readonly property int rows: 9
  property real isoAngleDeg: 40
  property real tileW: 96
  property real tileH: tileW * Math.tan(isoAngleDeg * Math.PI / 180)
  readonly property int playW: 900
  readonly property int playH: 480

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
  readonly property color water: Qt.tint(night, Qt.rgba(0.20, 0.45, 0.88, 0.60))
  readonly property color waterMark: Qt.lighter(water, 1.5)
  readonly property color railBed: Qt.tint(night, Qt.rgba(0.60, 0.56, 0.50, 0.45))
  readonly property color railMetal: Qt.lighter(railBed, 1.9)
  readonly property color logBrown: "#6b4a2a"
  readonly property color logEdge: "#4a2f18"
  readonly property color treeGreen: "#2f7a3a"
  readonly property color treeDark: "#1f5227"
  readonly property color trunkBrown: "#5a3c22"
  readonly property color rockGray: "#7d8088"
  readonly property color rockDark: "#4b4e56"

  // ---------------------------------------------------------------------------
  // World model
  //
  // Absolute row `ar` grows as the chick advances (forward = up-screen = away).
  //   screenRow(ar) = rows - (ar - winAnchor)
  // `winAnchor` is the absolute row pinned to the bottom screen row. It is a
  // real number so a forward hop can animate the whole world downward.
  // `winAnchorTarget` is the integer it settles on; all game logic uses that.
  // ---------------------------------------------------------------------------
  property int winAnchorTarget: 0
  property real winAnchor: 0
  property var laneMap: ({})
  property int nextAr: 0
  property string genLastType: "grass"
  property int genRun: 0

  // Flat render lists (rebuilt by refreshView / rebuildTraffic).
  property var flatProps: []
  property var flatTraffic: []
  property var flatLogs: []

  readonly property int startAr: 2          // safe grass rows live at ar <= 2
  readonly property int minChickScreenRow: rows - 3

  // Chick (col is fractional: logs carry the chick)
  property real chickColF: 5
  property int chickAr: 2
  property real visCol: 5
  property real visAr: 2
  property real hopZ: 0
  property real chickSquash: 1
  property string chickFacing: "ne"

  // Run state
  property int score: 0
  property int best: 0
  property bool dying: false
  property bool gameOver: false
  property real deathClock: 0
  property real overClock: 0
  property string deathCause: ""
  readonly property real deathFreeze: 0.5   // traffic freeze before the overlay

  property real lastTick: 0
  property real clock: 0
  property real paintAcc: 0
  property int frame: 0

  readonly property string pluginId: "io.github.tomfaulkner.crossy-hop"

  // ---------------------------------------------------------------------------
  // Iso projection (ROT baked in; center + fit keeps the upright card filled)
  // ---------------------------------------------------------------------------
  function isoLocal(col, row) {
    return {
      x: (col - row) * tileW / 2,
      y: (col + row) * tileH / 2
    }
  }

  function gridCentroidLocal() {
    return isoLocal((1 + cols) / 2, (1 + rows) / 2)
  }

  // Uniform fit factor: AABB of every cell center after ROT, padded by the tile
  // half-extent, scaled into the play card. Pure function of the camera props,
  // so QML re-evaluates the binding whenever ANGLE/ROT/size changes.
  function computeFitScale() {
    var mid = gridCentroidLocal()
    var r = viewRotationDeg * Math.PI / 180
    var c = Math.cos(r), s = Math.sin(r)
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
    var pad = Math.max(tileW, tileH) * 0.75
    var bw = (maxX - minX) + pad * 2
    var bh = (maxY - minY) + pad * 2
    return Math.min((playW * 0.92) / bw, (playH * 0.88) / bh)
  }

  readonly property real fitScale: root.computeFitScale()

  function projDelta(lx, ly) {
    var r = viewRotationDeg * Math.PI / 180
    var c = Math.cos(r), s = Math.sin(r)
    return {
      x: (lx * c - ly * s) * fitScale,
      y: (lx * s + ly * c) * fitScale
    }
  }

  // Screen-space delta for one step along the road (col) and across it (row).
  readonly property var colVec: projDelta(tileW / 2, tileH / 2)
  readonly property var rowVec: projDelta(-tileW / 2, tileH / 2)
  readonly property real unit: Math.sqrt(colVec.x * colVec.x + colVec.y * colVec.y)
  readonly property real carH: unit * 1.80
  readonly property real carW: carH * 1.15
  // Bacon train bake is ~101x96 (near-square AABB of a diagonal long sprite).
  // Size so the diagonal ≈ lane length (~len*0.95 units).
  // Bacon train bake is ~101x96 (near-square AABB of a diagonal long sprite).
  readonly property real trainH: unit * 2.85
  readonly property real trainW: trainH * 1.05
  readonly property real chickH: unit * 1.85
  readonly property real chickW: chickH * 0.63
  readonly property real propW: unit * 1.00
  readonly property real propH: unit * 1.70
  // Lane bands / grass tiles run well past the grid so ROT never shows card edges.
  readonly property int bandC0: -4
  readonly property int bandC1: cols + 5
  readonly property int tileC0: -2
  readonly property int tileC1: cols + 3

  function projectLocal(lx, ly) {
    var mid = gridCentroidLocal()
    var x = lx - mid.x
    var y = ly - mid.y
    var r = viewRotationDeg * Math.PI / 180
    var c = Math.cos(r), s = Math.sin(r)
    return {
      x: (x * c - y * s) * fitScale + playW / 2,
      y: (x * s + y * c) * fitScale + playH / 2
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

  // Fractional screen row of an absolute row (uses the animated anchor).
  function screenRowF(ar) { return rows - (ar - winAnchor) }
  // Gameplay screen row (uses the settled integer anchor).
  function screenRowOf(ar) { return rows - (ar - winAnchorTarget) }

  // Screen-degrees of travel along +col on a lane (rails/roads/rivers).
  // Use this to align procedural trains/logs — NOT baked car sprites.
  function laneTravelDeg(ar) {
    var sr = screenRowF(ar)
    var x0 = centerX(0, sr), y0 = centerY(0, sr)
    var x1 = centerX(1, sr), y1 = centerY(1, sr)
    return Math.atan2(y1 - y0, x1 - x0) * 180 / Math.PI
  }

  function zFor(ar, bias) {
    return 3 + screenRowF(ar) * 0.1 + (bias || 0)
  }

  // ---------------------------------------------------------------------------
  // Lane generation
  // ---------------------------------------------------------------------------
  function makeLane(ar, type) {
    return {
      ar: ar,
      type: type,          // grass | road | river | rail
      dir: 1,
      speed: 1,
      interval: 2,
      spawnT: 0,
      warn: 0,
      obstacles: [],       // [{col, kind}] — grass blockers
      vehicles: []         // cars | trains | logs
    }
  }

  function pick(list) {
    return list[Math.floor(Math.random() * list.length)]
  }

  function maxRoadRun(ar) {
    return ar < 12 ? 2 : (ar < 30 ? 3 : 4)
  }

  // Hazards are always separated by at least one safe grass row.
  function nextType(ar) {
    if (genLastType === "rail") return "grass"
    if (genLastType === "river")
      return (genRun < 3 && Math.random() < 0.72) ? "river" : "grass"
    if (genLastType === "road")
      return (genRun < maxRoadRun(ar) && Math.random() < 0.45) ? "road" : "grass"
    var r = Math.random()
    var railChance = ar < 6 ? 0.0 : 0.10
    var riverChance = ar < 5 ? 0.0 : 0.18
    var roadChance = 0.32
    if (r < railChance) return "rail"
    if (r < railChance + riverChance) return "river"
    if (r < railChance + riverChance + roadChance) return "road"
    return "grass"
  }

  function difficulty(ar) {
    return 1 + Math.min(ar, 80) / 90
  }

  function generateLane(ar) {
    var type = (ar <= startAr) ? "grass" : nextType(ar)
    var lane = makeLane(ar, type)
    var diff = difficulty(ar)

    if (type === "road") {
      lane.dir = Math.random() < 0.5 ? 1 : -1
      lane.speed = (1.1 + Math.random() * 1.2) * diff
      lane.interval = Math.max(0.75, (2.3 + Math.random() * 1.7) / diff)
      lane.spawnT = lane.interval * Math.random()
      spawnVehicle(lane, Math.random() * (cols + 2) - 1)
      if (Math.random() < 0.55) spawnVehicle(lane, null)
    } else if (type === "river") {
      lane.dir = Math.random() < 0.5 ? 1 : -1
      lane.speed = (0.7 + Math.random() * 0.7) * diff
      lane.interval = Math.max(1.1, (2.8 + Math.random() * 1.8) / diff)
      lane.spawnT = lane.interval * Math.random()
      spawnLog(lane, Math.random() * (cols + 2) - 1)
      if (Math.random() < 0.5) spawnLog(lane, null)
    } else if (type === "rail") {
      lane.dir = Math.random() < 0.5 ? 1 : -1
      lane.speed = 7 + Math.random() * 3
      lane.interval = 4 + Math.random() * 4
      lane.spawnT = 0
    } else if (ar > startAr) {
      // Trees / boulders block hops onto their cell.
      var density = 0.16 + Math.min(0.12, ar / 400)
      for (var c = 1; c <= cols; c++) {
        if (Math.random() < density)
          lane.obstacles.push({ col: c, kind: Math.random() < 0.72 ? "tree" : "boulder" })
      }
      // Never wall off a whole row.
      if (lane.obstacles.length > cols - 3)
        lane.obstacles.length = Math.max(1, cols - 3)
    }

    if (lane.type === genLastType) genRun++
    else { genLastType = lane.type; genRun = 1 }
    return lane
  }

  function ensureLanes(maxAr) {
    while (nextAr <= maxAr) {
      laneMap[nextAr] = generateLane(nextAr)
      nextAr++
    }
  }

  function pruneLanes() {
    var lo = winAnchorTarget - 2
    var hi = winAnchorTarget + rows + 2
    var keys = Object.keys(laneMap)
    for (var i = 0; i < keys.length; i++) {
      var ar = parseInt(keys[i], 10)
      if (ar < lo || ar > hi) delete laneMap[ar]
    }
  }

  function isBlocked(lane, col) {
    for (var i = 0; i < lane.obstacles.length; i++) {
      if (lane.obstacles[i].col === col) return true
    }
    return false
  }

  // ---------------------------------------------------------------------------
  // Traffic
  // ---------------------------------------------------------------------------
  function laneClear(lane, t, len) {
    for (var i = 0; i < lane.vehicles.length; i++) {
      var v = lane.vehicles[i]
      if (Math.abs(v.t - t) < (len + v.len) * 0.5 + 0.9) return false
    }
    return true
  }

  function spawnVehicle(lane, t) {
    var len = 1.6 + Math.random() * 0.5
    if (t === null || t === undefined)
      t = lane.dir === 1 ? -len - 1 : cols + len + 1
    if (!laneClear(lane, t, len)) return null
    var veh = {
      kind: "car",
      t: t,
      ar: lane.ar,
      len: len,
      dir: lane.dir,
      speed: lane.speed * (0.85 + Math.random() * 0.35),
      image: "assets/baked/bacon/" + pick(["orange", "blue", "green"]) + "-" + (lane.dir === 1 ? "e" : "w") + ".png"
    }
    lane.vehicles.push(veh)
    return veh
  }

  function spawnLog(lane, t) {
    var len = 2 + Math.floor(Math.random() * 2)   // 2 or 3 tiles
    if (t === null || t === undefined)
      t = lane.dir === 1 ? -len - 1 : cols + len + 1
    if (!laneClear(lane, t, len)) return null
    var log = {
      kind: "log",
      t: t,
      ar: lane.ar,
      len: len,
      dir: lane.dir,
      speed: lane.speed
    }
    lane.vehicles.push(log)
    return log
  }

  function spawnTrain(lane) {
    var len = 4.2
    var t = lane.dir === 1 ? -len - 1 : cols + len + 1
    lane.vehicles.push({
      kind: "train",
      t: t,
      ar: lane.ar,
      len: len,
      dir: lane.dir,
      speed: lane.speed,
      image: "assets/baked/bacon/train-" + (lane.dir === 1 ? "e" : "w") + ".png"
    })
  }

  function hitHalf(v) {
    // Half-extent along the lane (col axis). Trains were using len*0.3+0.4 ≈ 2+
    // tiles and felt like they hit far off the rail visually when mis-oriented.
    if (v.kind === "train") return Math.max(0.55, v.len * 0.42)
    if (v.kind === "log") return Math.max(0.55, v.len * 0.42)
    return 0.32 + v.len * 0.20
  }

  // ---------------------------------------------------------------------------
  // Flattened render lists
  // ---------------------------------------------------------------------------
  function rebuildTraffic() {
    var keys = Object.keys(laneMap)
    var cars = []
    var logs = []
    for (var i = 0; i < keys.length; i++) {
      var lane = laneMap[keys[i]]
      for (var j = 0; j < lane.vehicles.length; j++) {
        var v = lane.vehicles[j]
        if (v.kind === "log") logs.push(v)
        else cars.push(v)
      }
    }
    flatTraffic = cars
    flatLogs = logs
  }

  function refreshView() {
    var lo = winAnchorTarget - 2
    var hi = winAnchorTarget + rows
    var props = []
    for (var ar = lo; ar <= hi; ar++) {
      var lane = laneMap[ar]
      if (!lane) continue
      for (var i = 0; i < lane.obstacles.length; i++)
        props.push({ ar: ar, col: lane.obstacles[i].col, kind: lane.obstacles[i].kind })
    }
    flatProps = props
    rebuildTraffic()
  }

  // ---------------------------------------------------------------------------
  // Simulation
  // ---------------------------------------------------------------------------
  // Returns true when the traffic roster changed (spawn/despawn). Callers must
  // NOT rebuild flat lists every frame — that thrashes Repeaters and crashes QS.
  function updateWorld(dt) {
    var keys = Object.keys(laneMap)
    var rosterDirty = false
    var paintDirty = false
    for (var i = 0; i < keys.length; i++) {
      var lane = laneMap[keys[i]]
      lane.spawnT += dt

      if (lane.type === "road") {
        if (lane.spawnT >= lane.interval) {
          lane.spawnT = 0
          if (lane.vehicles.length < 4 && spawnVehicle(lane, null)) rosterDirty = true
        }
      } else if (lane.type === "river") {
        if (lane.spawnT >= lane.interval) {
          lane.spawnT = 0
          if (lane.vehicles.length < 3 && spawnLog(lane, null)) rosterDirty = true
        }
      } else if (lane.type === "rail") {
        if (lane.vehicles.length === 0 && lane.spawnT >= lane.interval) {
          lane.spawnT = 0
          spawnTrain(lane)
          lane.interval = 4 + Math.random() * 4
          rosterDirty = true
        }
        var warn = (lane.vehicles.length > 0 || lane.spawnT > lane.interval - 1.9) ? 1 : 0
        if (warn !== lane.warn) { lane.warn = warn; paintDirty = true }
      }

      var alive = []
      var before = lane.vehicles.length
      for (var j = 0; j < lane.vehicles.length; j++) {
        var v = lane.vehicles[j]
        v.t += v.dir * v.speed * dt
        var margin = v.len + 2
        if (v.t > -margin && v.t < cols + margin) alive.push(v)
      }
      if (alive.length !== before) rosterDirty = true
      lane.vehicles = alive
    }
    if (rosterDirty) rebuildTraffic()
    return paintDirty || rosterDirty
  }

  function checkChick(dt) {
    var lane = laneMap[chickAr]
    if (!lane) return
    var i, v

    if (lane.type === "road") {
      for (i = 0; i < lane.vehicles.length; i++) {
        v = lane.vehicles[i]
        if (Math.abs(v.t - chickColF) < hitHalf(v)) { die("car"); return }
      }
      return
    }

    if (lane.type === "rail") {
      for (i = 0; i < lane.vehicles.length; i++) {
        v = lane.vehicles[i]
        if (Math.abs(v.t - chickColF) < hitHalf(v)) { die("train"); return }
      }
      return
    }

    if (lane.type === "river") {
      var raft = null
      for (i = 0; i < lane.vehicles.length; i++) {
        v = lane.vehicles[i]
        if (Math.abs(v.t - chickColF) < v.len * 0.5 + 0.30) { raft = v; break }
      }
      if (!raft) { die("water"); return }
      chickColF += raft.dir * raft.speed * dt
      if (!hopAnim.running) visCol = chickColF
      if (chickColF < 0.6 || chickColF > cols + 0.4) die("water")
    }
  }

  function die(cause) {
    if (dying || gameOver) return
    dying = true
    deathCause = cause
    deathClock = 0
    squashAnim.start()
    debugHopSnapshot("die:" + cause)
  }

  function step(dt) {
    try {

    clock += dt
    var needPaint = false
    if (dying) {
      deathClock += dt
      if (deathClock >= deathFreeze) {
        dying = false
        gameOver = true
        overClock = 0
        if (score > best) best = score
        needPaint = true
      }
    } else if (gameOver) {
      overClock += dt
    } else {
      if (updateWorld(dt)) needPaint = true
      checkChick(dt)
      if (dying) needPaint = true
    }
    // Traffic/logs/props are Canvas-only (no per-item frame bindings).
    frame++
    paintAcc += dt
    // Canvas-only scene can take ~30fps now; idle paints stay cheaper.
    var moving = flatTraffic.length > 0 || flatLogs.length > 0
    var paintHz = moving ? 0.033 : 0.12
    if (needPaint || paintAcc >= paintHz || hopAnim.running || scrollAnim.running) {
      paintAcc = 0
      playfield.requestPaint()
    }
  
    } catch (error) {
      console.warn("[crossy-hop] step failed", error)
      try { debugHopSnapshot("step-error") } catch (e2) { console.warn("[crossy-hop] log failed", e2) }
    }
  }


  function trafficCounts() {
    var keys = Object.keys(laneMap)
    var vehN = 0
    for (var i = 0; i < keys.length; i++) {
      var lane = laneMap[keys[i]]
      if (lane && lane.vehicles) vehN += lane.vehicles.length
    }
    return { lanes: keys.length, vehs: vehN }
  }

  function debugHopSnapshot(tag) {
    var counts = trafficCounts()
    var lane = laneMap[chickAr]
    var line = [
      (new Date()).toISOString(),
      tag || "hop",
      "n=" + hopCount,
      "score=" + score,
      "ar=" + chickAr,
      "col=" + Number(chickColF).toFixed(2),
      "lane=" + (lane ? lane.type : "null"),
      "lanes=" + counts.lanes,
      "vehs=" + counts.vehs,
      "flatT=" + flatTraffic.length,
      "flatL=" + flatLogs.length,
      "flatP=" + flatProps.length,
      "anchor=" + winAnchorTarget,
      "frame=" + frame,
      "boot=" + bootId,
      "dying=" + (dying ? 1 : 0),
      "over=" + (gameOver ? 1 : 0)
    ].join(" ")
    console.warn("[crossy-hop]", line)
    // Never pile Process restarts — overlapping shells have crashed QS before.
    if (hopLogProc.running)
      return
    hopLogProc.command = [
      "sh", "-c",
      "mkdir -p \"$1\" && printf '%s\n' \"$2\" >> \"$3\"",
      "sh",
      debugDir,
      line,
      debugLogPath
    ]
    hopLogProc.running = true
  }

  // ---------------------------------------------------------------------------
  // Chick
  // ---------------------------------------------------------------------------
  function moveChick(dc, dAr) {
    if (gameOver) {
      if (overClock > 0.4) resetGame()
      return
    }
    if (dying) return

    var newAr = chickAr + dAr
    var newCol = Math.round(chickColF) + dc
    var sr = screenRowOf(newAr)
    if (sr < 1 || sr > rows) return
    if (newCol < 1 || newCol > cols) return

    ensureLanes(newAr)
    var lane = laneMap[newAr]
    if (lane && isBlocked(lane, newCol)) {
      bumpAnim.start()
      return
    }

    chickAr = newAr
    chickColF = newCol
    if (dAr > 0) {
      chickFacing = "ne"
      if (chickAr - startAr > score) score = chickAr - startAr
    } else if (dAr < 0) {
      chickFacing = "sw"
    }

    hopCol.from = visCol
    hopCol.to = newCol
    hopRow.from = visAr
    hopRow.to = newAr
    hopAnim.restart()

    hopCount++
    if (hopCount % 2 === 0)
      debugHopSnapshot("hop")

    // Scroll the world so the chick stays in the bottom third.
    var target = winAnchorTarget
    var s = rows - (chickAr - target)
    while (s < minChickScreenRow) { target++; s++ }
    if (target !== winAnchorTarget) {
      winAnchorTarget = target
      ensureLanes(winAnchorTarget + rows + 1)
      pruneLanes()
      refreshView()
      scrollAnim.to = winAnchorTarget
      scrollAnim.restart()
    }
  }

  function resetGame() {
    hopCount = 0
    score = 0
    winAnchorTarget = 0
    winAnchor = 0
    laneMap = ({})
    nextAr = 0
    genLastType = "grass"
    genRun = 0
    chickColF = Math.round((cols + 1) / 2)
    chickAr = startAr
    visCol = chickColF
    visAr = chickAr
    hopZ = 0
    chickSquash = 1
    chickFacing = "ne"
    dying = false
    gameOver = false
    deathCause = ""
    deathClock = 0
    overClock = 0
    paintAcc = 0
    ensureLanes(rows + 2)
    refreshView()
    playfield.requestPaint()
    debugHopSnapshot("reset")
  }

  // ---------------------------------------------------------------------------
  // Shell plumbing
  // ---------------------------------------------------------------------------
  function open(payloadJson) {
    opened = true
    bootId++
    resetGame()
    lastTick = Date.now()
    debugHopSnapshot("open")
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

  Component.onCompleted: {
    // Build a world up-front so the card is never empty (even before first open).
    resetGame()
  }

  Timer {
    interval: 16
    repeat: true
    running: root.opened
    onTriggered: {
      var now = Date.now()
      var dt = (now - root.lastTick) / 1000
      root.lastTick = now
      if (dt > 0.25) dt = 0.25
      root.step(dt)
    }
  }

  Process {
    id: hopLogProc
    running: false
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

        // Quad along a lane: from column c0 to c1 on (possibly fractional) row.
        function laneQuad(ctx, rowF, c0, c1, half) {
          var ax = root.centerX(c0, rowF), ay = root.centerY(c0, rowF)
          var bx = root.centerX(c1, rowF), by = root.centerY(c1, rowF)
          var dx = bx - ax, dy = by - ay
          var len = Math.sqrt(dx * dx + dy * dy) || 1
          var nx = -dy / len, ny = dx / len
          ctx.beginPath()
          ctx.moveTo(ax + nx * half, ay + ny * half)
          ctx.lineTo(bx + nx * half, by + ny * half)
          ctx.lineTo(bx - nx * half, by - ny * half)
          ctx.lineTo(ax - nx * half, ay - ny * half)
          ctx.closePath()
        }

        function drawBand(ctx, lane, fill) {
          var sr = root.screenRowF(lane.ar)
          if (sr < -2 || sr > root.rows + 2) return
          var half = Math.sqrt(root.rowVec.x * root.rowVec.x + root.rowVec.y * root.rowVec.y) * 0.5 + 1
          ctx.save()
          laneQuad(ctx, sr, root.bandC0, root.bandC1, half)
          ctx.fillStyle = fill
          ctx.fill()
          ctx.restore()
        }

        // One projected tile diamond (col/row may be fractional).
        function drawCell(ctx, colF, rowF, sx, sy, fill, stroke) {
          var cx = root.centerX(colF, rowF)
          var cy = root.centerY(colF, rowF)
          var ax = root.colVec.x * sx * 0.5, ay = root.colVec.y * sx * 0.5
          var bx = root.rowVec.x * sy * 0.5, by = root.rowVec.y * sy * 0.5
          ctx.save()
          ctx.beginPath()
          ctx.moveTo(cx + ax, cy + ay)
          ctx.lineTo(cx + bx, cy + by)
          ctx.lineTo(cx - ax, cy - ay)
          ctx.lineTo(cx - bx, cy - by)
          ctx.closePath()
          if (fill) { ctx.fillStyle = fill; ctx.fill() }
          if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = 1; ctx.stroke() }
          ctx.restore()
        }

        function drawLane(ctx, lane) {
          var sr = root.screenRowF(lane.ar)
          if (sr < -2 || sr > root.rows + 2) return

          if (lane.type === "grass") {
            var alt = (Math.abs(lane.ar) % 2 === 0) ? root.grass : Qt.darker(root.grass, 1.10)
            drawBand(ctx, lane, alt)
            return
          }

          if (lane.type === "road") {
            drawBand(ctx, lane, root.road)
            // dashed centre line along the lane direction
            ctx.save()
            ctx.strokeStyle = root.roadMark
            ctx.lineWidth = Math.max(1.5, root.unit * 0.08)
            ctx.setLineDash([root.unit * 0.55, root.unit * 0.45])
            ctx.beginPath()
            ctx.moveTo(root.centerX(root.bandC0, sr), root.centerY(root.bandC0, sr))
            ctx.lineTo(root.centerX(root.bandC1, sr), root.centerY(root.bandC1, sr))
            ctx.stroke()
            ctx.setLineDash([])
            ctx.restore()
            return
          }

          if (lane.type === "river") {
            drawBand(ctx, lane, root.water)
            var rowLen = Math.sqrt(root.rowVec.x * root.rowVec.x + root.rowVec.y * root.rowVec.y)
            ctx.save()
            ctx.strokeStyle = root.waterMark
            ctx.lineWidth = Math.max(1, root.unit * 0.05)
            ctx.setLineDash([root.unit * 0.9, root.unit * 0.7])
            for (var w = -1; w <= 1; w++) {
              var off = w * rowLen * 0.28
              var a = [root.centerX(root.bandC0, sr + off / rowLen), root.centerY(root.bandC0, sr + off / rowLen)]
              var b = [root.centerX(root.bandC1, sr + off / rowLen), root.centerY(root.bandC1, sr + off / rowLen)]
              ctx.beginPath()
              ctx.moveTo(a[0], a[1])
              ctx.lineTo(b[0], b[1])
              ctx.stroke()
            }
            ctx.setLineDash([])
            ctx.restore()
            return
          }

          if (lane.type === "rail") {
            drawBand(ctx, lane, root.railBed)
            // sleepers
            ctx.save()
            ctx.strokeStyle = Qt.darker(root.railBed, 1.35)
            ctx.lineWidth = Math.max(1, root.unit * 0.10)
            for (var s = -2; s < root.cols + 3; s += 1.0) {
              var sx = root.colVec.x * 0.18, sy = root.colVec.y * 0.18
              var px = root.centerX(s, sr), py = root.centerY(s, sr)
              ctx.beginPath()
              ctx.moveTo(px - sx, py - sy)
              ctx.lineTo(px + sx, py + sy)
              ctx.stroke()
            }
            // two rails
            ctx.strokeStyle = root.railMetal
            ctx.lineWidth = Math.max(1, root.unit * 0.06)
            for (var k = -1; k <= 1; k += 2) {
              var ox = root.rowVec.x * 0.20 * k, oy = root.rowVec.y * 0.20 * k
              ctx.beginPath()
              ctx.moveTo(root.centerX(root.bandC0, sr) + ox, root.centerY(root.bandC0, sr) + oy)
              ctx.lineTo(root.centerX(root.bandC1, sr) + ox, root.centerY(root.bandC1, sr) + oy)
              ctx.stroke()
            }
            ctx.restore()
            // crossing lights (blink while a train is pending / running)
            if (lane.warn) {
              var lit = (Math.floor(root.clock * 5) % 2) === 0
              ctx.save()
              ctx.fillStyle = lit ? "#ff5f56" : "#5c2020"
              for (var e = 0; e < 2; e++) {
                var ec = e === 0 ? 0.1 : root.cols + 0.9
                var lx = root.centerX(ec, sr), ly = root.centerY(ec, sr)
                ctx.beginPath()
                ctx.arc(lx, ly - root.unit * 0.45, root.unit * 0.20, 0, Math.PI * 2)
                ctx.fill()
              }
              ctx.restore()
            }
            return
          }
        }

        function drawTreeAt(ctx, cx, cy) {
          var w = root.propW, h = root.propH
          var x = cx - w / 2, y = cy - h * 0.78
          ctx.fillStyle = root.trunkBrown
          ctx.fillRect(x + w * 0.42, y + h * 0.58, w * 0.16, h * 0.42)
          ctx.fillStyle = root.treeDark
          ctx.beginPath()
          ctx.moveTo(x + w * 0.5, y + h * 0.24)
          ctx.lineTo(x + w * 0.96, y + h * 0.80)
          ctx.lineTo(x + w * 0.04, y + h * 0.80)
          ctx.closePath()
          ctx.fill()
          ctx.fillStyle = root.treeGreen
          ctx.beginPath()
          ctx.moveTo(x + w * 0.5, y + h * 0.02)
          ctx.lineTo(x + w * 0.86, y + h * 0.52)
          ctx.lineTo(x + w * 0.14, y + h * 0.52)
          ctx.closePath()
          ctx.fill()
        }

        function drawBoulderAt(ctx, cx, cy) {
          var w = root.propW * 0.85, h = root.propH * 0.45
          ctx.save()
          ctx.translate(cx, cy - h * 0.15)
          ctx.scale(1, Math.max(0.35, h / Math.max(w, 1)))
          ctx.beginPath()
          ctx.arc(0, 0, w / 2, 0, Math.PI * 2)
          ctx.fillStyle = root.rockGray
          ctx.fill()
          ctx.strokeStyle = root.rockDark
          ctx.lineWidth = 2
          ctx.stroke()
          ctx.restore()
        }

        function spriteFor(path) {
          if (!path) return null
          if (path.indexOf("train-e") >= 0) return sprTrainE
          if (path.indexOf("train-w") >= 0) return sprTrainW
          if (path.indexOf("orange-e") >= 0) return sprOrangeE
          if (path.indexOf("orange-w") >= 0) return sprOrangeW
          if (path.indexOf("blue-e") >= 0) return sprBlueE
          if (path.indexOf("blue-w") >= 0) return sprBlueW
          if (path.indexOf("green-e") >= 0) return sprGreenE
          if (path.indexOf("green-w") >= 0) return sprGreenW
          return null
        }

        function drawSprite(ctx, img, cx, cy, w, h, deg, yAnchor) {
          if (!img || img.status !== Image.Ready) return
          ctx.save()
          ctx.translate(cx, cy)
          ctx.rotate(deg * Math.PI / 180)
          ctx.drawImage(img, -w / 2, -h * yAnchor, w, h)
          ctx.restore()
        }

        function drawLogAt(ctx, log) {
          var sr = root.screenRowF(log.ar)
          if (sr < -2 || sr > root.rows + 2) return
          var cx = root.centerX(log.t, sr)
          var cy = root.centerY(log.t, sr)
          var w = root.unit * log.len * 0.95
          var h = root.unit * 0.50
          var deg = root.laneTravelDeg(log.ar) * Math.PI / 180
          ctx.save()
          ctx.translate(cx, cy)
          ctx.rotate(deg)
          var r = h / 2
          ctx.beginPath()
          // rounded capsule
          ctx.moveTo(-w / 2 + r, -h / 2)
          ctx.lineTo(w / 2 - r, -h / 2)
          ctx.arc(w / 2 - r, 0, r, -Math.PI / 2, Math.PI / 2)
          ctx.lineTo(-w / 2 + r, h / 2)
          ctx.arc(-w / 2 + r, 0, r, Math.PI / 2, -Math.PI / 2)
          ctx.closePath()
          ctx.fillStyle = root.logBrown
          ctx.fill()
          ctx.strokeStyle = root.logEdge
          ctx.lineWidth = 2
          ctx.stroke()
          ctx.restore()
        }

        function drawVehAt(ctx, veh) {
          var sr = root.screenRowF(veh.ar)
          if (sr < -2 || sr > root.rows + 2) return
          var cx = root.centerX(veh.t, sr)
          var cy = root.centerY(veh.t, sr)
          var w = veh.kind === "train" ? root.trainW : root.carW
          var h = veh.kind === "train" ? root.trainH : root.carH
          drawSprite(ctx, spriteFor(veh.image), cx, cy, w, h, root.viewRotationDeg, 0.70)
        }

        onPaint: {
          var ctx = getContext("2d")
          ctx.reset()
          ctx.imageSmoothingEnabled = false

          ctx.fillStyle = grass
          ctx.fillRect(0, 0, playW, playH)

          var keys = Object.keys(root.laneMap)
          var lanes = []
          for (var i = 0; i < keys.length; i++) lanes.push(root.laneMap[keys[i]])
          lanes.sort(function(a, b) { return b.ar - a.ar })
          for (var j = 0; j < lanes.length; j++) drawLane(ctx, lanes[j])

          // Props / logs / cars / trains — all Canvas (no Repeater thrash).
          var props = root.flatProps
          for (var pi = 0; pi < props.length; pi++) {
            var prop = props[pi]
            var psr = root.screenRowF(prop.ar)
            var pcx = root.centerX(prop.col, psr)
            var pcy = root.centerY(prop.col, psr)
            if (prop.kind === "boulder") drawBoulderAt(ctx, pcx, pcy)
            else drawTreeAt(ctx, pcx, pcy)
          }

          var logs = root.flatLogs
          for (var li = 0; li < logs.length; li++)
            drawLogAt(ctx, logs[li])

          var cars = root.flatTraffic
          for (var vi = 0; vi < cars.length; vi++)
            drawVehAt(ctx, cars[vi])
        }
      }

      // Hidden sprite atlas for Canvas.drawImage (cars + trains).
      Item {
        id: spriteBank
        visible: false
        width: 1
        height: 1
        Image { id: sprOrangeE; source: Qt.resolvedUrl("assets/baked/bacon/orange-e.png"); asynchronous: true; cache: true; smooth: false }
        Image { id: sprOrangeW; source: Qt.resolvedUrl("assets/baked/bacon/orange-w.png"); asynchronous: true; cache: true; smooth: false }
        Image { id: sprBlueE; source: Qt.resolvedUrl("assets/baked/bacon/blue-e.png"); asynchronous: true; cache: true; smooth: false }
        Image { id: sprBlueW; source: Qt.resolvedUrl("assets/baked/bacon/blue-w.png"); asynchronous: true; cache: true; smooth: false }
        Image { id: sprGreenE; source: Qt.resolvedUrl("assets/baked/bacon/green-e.png"); asynchronous: true; cache: true; smooth: false }
        Image { id: sprGreenW; source: Qt.resolvedUrl("assets/baked/bacon/green-w.png"); asynchronous: true; cache: true; smooth: false }
        Image { id: sprTrainE; source: Qt.resolvedUrl("assets/baked/bacon/train-e.png"); asynchronous: true; cache: true; smooth: false }
        Image { id: sprTrainW; source: Qt.resolvedUrl("assets/baked/bacon/train-w.png"); asynchronous: true; cache: true; smooth: false }
      }

      Image {
        id: chick
        x: root.centerX(root.visCol, root.screenRowF(root.visAr)) - width / 2
        y: root.centerY(root.visCol, root.screenRowF(root.visAr)) - height * 0.70 - root.hopZ
        width: root.chickW
        height: root.chickH
        source: Qt.resolvedUrl("assets/baked/bacon/chicken-" + root.chickFacing + ".png")
        smooth: false
        scale: root.chickSquash
        transformOrigin: Item.Bottom
        z: root.zFor(root.visAr, 0.05)
        rotation: root.viewRotationDeg
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
          font.pixelSize: 20
          font.bold: true
          font.family: "monospace"
        }
        Text {
          text: "ROT    " + root.rotationLabel()
          color: accent
          font.pixelSize: 20
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

      Column {
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 14
        spacing: 2
        z: 20
        Text {
          anchors.right: parent.right
          text: "SCORE  " + root.score
          color: ink
          font.pixelSize: 30
          font.bold: true
          font.family: "monospace"
        }
        Text {
          anchors.right: parent.right
          text: "BEST   " + root.best
          color: hush
          font.pixelSize: 16
          font.bold: true
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

      // Game over
      Rectangle {
        anchors.centerIn: parent
        width: 340
        height: 168
        radius: 6
        z: 60
        visible: root.gameOver
        color: Qt.rgba(root.night.r, root.night.g, root.night.b, 0.90)
        border.color: root.accent
        border.width: 2

        Column {
          anchors.centerIn: parent
          spacing: 8
          Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "GAME OVER"
            color: root.ink
            font.pixelSize: 34
            font.bold: true
            font.family: "monospace"
          }
          Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.deathCause === "water" ? "GLUB GLUB"
                : root.deathCause === "train" ? "SPLAT"
                : "SQUISH"
            color: root.accent
            font.pixelSize: 16
            font.family: "monospace"
          }
          Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "SCORE " + root.score + "   BEST " + root.best
            color: root.ink
            font.pixelSize: 18
            font.bold: true
            font.family: "monospace"
          }
          Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "SPACE / ENTER / R  RESTART"
            color: root.hush
            font.pixelSize: 14
            font.family: "monospace"
          }
        }
      }

      ParallelAnimation {
        id: hopAnim
        NumberAnimation {
          id: hopCol
          target: root
          property: "visCol"
          duration: 165
          easing.type: Easing.OutQuad
        }
        NumberAnimation {
          id: hopRow
          target: root
          property: "visAr"
          duration: 165
          easing.type: Easing.OutQuad
        }
        SequentialAnimation {
          NumberAnimation { target: root; property: "hopZ"; to: 20; duration: 85; easing.type: Easing.OutQuad }
          NumberAnimation { target: root; property: "hopZ"; to: 0; duration: 85; easing.type: Easing.InQuad }
        }
      }

      SequentialAnimation {
        id: bumpAnim
        NumberAnimation { target: root; property: "hopZ"; to: 5; duration: 70; easing.type: Easing.OutQuad }
        NumberAnimation { target: root; property: "hopZ"; to: 0; duration: 70; easing.type: Easing.InQuad }
      }

      NumberAnimation {
        id: scrollAnim
        target: root
        property: "winAnchor"
        duration: 165
        easing.type: Easing.OutQuad
      }

      NumberAnimation {
        id: squashAnim
        target: root
        property: "chickSquash"
        to: 0.45
        duration: 120
        easing.type: Easing.OutQuad
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
          else if (event.key === Qt.Key_Space || event.key === Qt.Key_Enter || event.key === Qt.Key_Return) {
            if (root.gameOver && root.overClock > 0.4) root.resetGame()
            else return
          }
          else if (event.key === Qt.Key_R) {
            if (root.gameOver && root.overClock > 0.4) root.resetGame()
            else return
          }
          else if (event.key === Qt.Key_Left || event.key === Qt.Key_A) root.moveChick(-1, 0)
          else if (event.key === Qt.Key_Right || event.key === Qt.Key_D) root.moveChick(1, 0)
          else if (event.key === Qt.Key_Up || event.key === Qt.Key_W) root.moveChick(0, 1)
          else if (event.key === Qt.Key_Down || event.key === Qt.Key_S) root.moveChick(0, -1)
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
