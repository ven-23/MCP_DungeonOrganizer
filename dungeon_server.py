import json
import hashlib
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple

from mcp.server.fastmcp import FastMCP
from send2trash import send2trash

mcp = FastMCP("DungeonOrganizer")

# ----------------------------
# Dungeon Rules (Rooms)
# ----------------------------
ROOM_RULES: Dict[str, List[str]] = {
    "🖼️ Images Room": [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"],
    "📚 Docs Library": [".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".txt", ".md", ".csv"],
    "💻 Code Cave": [".py", ".js", ".ts", ".java", ".cs", ".cpp", ".c", ".html", ".css", ".json", ".sql", ".yml", ".yaml"],
    "🎵 Media Hall": [".mp4", ".mov", ".mkv", ".mp3", ".wav", ".avi", ".flac", ".m4a"],
    "🧰 Archives Vault": [".zip", ".rar", ".7z", ".tar", ".gz", ".iso"],
}
TREASURE_KEYWORDS = ["invoice", "resume", "cv", "thesis", "contract", "grade", "requirements", "certificate", "budget"]

DEFAULT_EXCLUDE_DIRS = {"_Sorted", "_DungeonOutput"}
LAST_OUTPUT_DIR: Optional[Path] = None


# ----------------------------
# Helpers
# ----------------------------
def _resolve_output_dir(base: Path, output_dir: str) -> Path:
    """
    Default output_dir "dungeon_output" writes beside scanned folder:
      <base>/_DungeonOutput
    """
    if output_dir == "dungeon_output":
        out = base / "_DungeonOutput"
    else:
        out = Path(output_dir).expanduser()
        if not out.is_absolute():
            out = base / out
    return out.resolve()


def _room_for(ext: str) -> str:
    ext = (ext or "").lower()
    for room, exts in ROOM_RULES.items():
        if ext in exts:
            return room
    return "🕳️ Unknown Swamp"


def _is_treasure(name: str, ext: str) -> bool:
    low = (name or "").lower()
    return any(k in low for k in TREASURE_KEYWORDS) or (ext or "").lower() in [".pdf", ".docx", ".pptx", ".xlsx"]


def _sha256_file(p: Path, max_mb: int = 50) -> Optional[str]:
    try:
        if not p.exists():
            return None
        if p.stat().st_size > max_mb * 1024 * 1024:
            return None
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _iter_files(base: Path, include_subfolders: bool, exclude_dirs: set) -> List[Path]:
    files: List[Path] = []
    if include_subfolders:
        for p in base.rglob("*"):
            if p.is_file():
                if any(part in exclude_dirs for part in p.parts):
                    continue
                files.append(p)
    else:
        for p in base.glob("*"):
            if p.is_file():
                files.append(p)
    return files


def _safe_dest(dest_dir: Path, filename: str) -> Path:
    dest = dest_dir / filename
    i = 1
    while dest.exists():
        stem = Path(filename).stem
        suf = Path(filename).suffix
        dest = dest_dir / f"{stem}_dup{i}{suf}"
        i += 1
    return dest


def _format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024**2:
        return f"{n/1024:.1f} KB"
    if n < 1024**3:
        return f"{n/1024**2:.1f} MB"
    return f"{n/1024**3:.2f} GB"


def _quest_progress(files: List[dict], base: Path) -> dict:
    sorted_root = base / "_Sorted"
    total = len(files)

    def in_sorted(fp: str) -> bool:
        p = Path(fp)
        try:
            return p.is_relative_to(sorted_root)  # py3.9+
        except Exception:
            return str(sorted_root) in str(p)

    sorted_count = sum(1 for f in files if in_sorted(f["path"]))
    progress = 100 if total == 0 else int((sorted_count / total) * 100)

    rank = "S" if progress >= 95 else "A" if progress >= 80 else "B" if progress >= 60 else "C" if progress >= 30 else "D"

    return {
        "id": "restore_order",
        "title": "Quest: Restore Order",
        "desc": "Reorganize loot into dungeon rooms under _Sorted to reduce chaos.",
        "xp": 250,
        "icon": "🗡️",
        "progress": progress,
        "rank": rank,
        "hint": "Run reorganize(mode='dry_run') then reorganize(mode='apply') to complete the quest.",
        "sorted_count": sorted_count,
        "total": total,
    }


def _detect_monsters(files: List[dict]) -> List[dict]:
    monsters: List[dict] = []
    seen: Dict[Tuple[int, str], str] = {}

    for f in files:
        if f["size"] > 200 * 1024 * 1024:
            monsters.append({"type": "behemoth", "path": f["path"], "size": f["size"]})

        key = (f["size"], f["name"].lower())
        if key in seen:
            a = Path(seen[key])
            b = Path(f["path"])
            ha = _sha256_file(a)
            hb = _sha256_file(b)
            if ha and hb and ha == hb:
                monsters.append({"type": "duplicate", "a": str(a), "b": str(b), "size": f["size"]})
        else:
            seen[key] = f["path"]

    return monsters


def _build_scan(base: Path, include_subfolders: bool, exclude_dirs: set) -> dict:
    now = datetime.now().timestamp()
    file_paths = _iter_files(base, include_subfolders, exclude_dirs)

    files: List[dict] = []
    rooms: Dict[str, dict] = {}
    total_size = 0
    treasure_count = 0
    relic_count = 0

    for p in file_paths:
        try:
            st = p.stat()
            total_size += st.st_size
            age_days = int((now - st.st_mtime) / 86400)
            room = _room_for(p.suffix)
            treasure = _is_treasure(p.name, p.suffix)
            relic = age_days > 730  # 2 years

            if treasure:
                treasure_count += 1
            if relic:
                relic_count += 1

            meta = {
                "path": str(p),
                "name": p.name,
                "ext": p.suffix.lower(),
                "size": st.st_size,
                "mtime": st.st_mtime,
                "age_days": age_days,
                "room": room,
                "treasure": treasure,
                "relic": relic,
            }
            files.append(meta)

            if room not in rooms:
                rooms[room] = {"count": 0, "size": 0, "treasure": 0, "relic": 0}
            rooms[room]["count"] += 1
            rooms[room]["size"] += st.st_size
            if treasure:
                rooms[room]["treasure"] += 1
            if relic:
                rooms[room]["relic"] += 1

        except Exception:
            continue

    monsters = _detect_monsters(files)
    quest = _quest_progress(files, base)

    return {
        "base": str(base),
        "scan_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_size": total_size,
        "files": files,
        "rooms": rooms,
        "monsters": monsters,
        "quest": quest,
        "treasures": treasure_count,
        "relics": relic_count,
    }


def _plan_reorganize(base: Path, include_subfolders: bool, exclude_dirs: set) -> List[dict]:
    sorted_root = base / "_Sorted"
    sorted_root.mkdir(parents=True, exist_ok=True)

    candidates = _iter_files(base, include_subfolders, exclude_dirs)

    def already_sorted(p: Path) -> bool:
        try:
            return p.is_relative_to(sorted_root)
        except Exception:
            return str(sorted_root) in str(p)

    changes: List[dict] = []
    for src in candidates:
        if already_sorted(src):
            continue
        room = _room_for(src.suffix.lower())
        dest_dir = sorted_root / room
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = _safe_dest(dest_dir, src.name)
        changes.append({"from": str(src), "to": str(dest), "room": room})

    return changes


def _write_undo_ps1(out: Path, changes: List[dict]) -> Path:
    lines = ["# Undo script (DungeonOrganizer)", "$ErrorActionPreference = 'Stop'"]
    for c in reversed(changes):
        lines.append(f"Move-Item -LiteralPath '{c['to']}' -Destination '{c['from']}'")
    p = out / "undo.ps1"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


# ----------------------------
# MCP Tools
# ----------------------------
@mcp.tool()
def scan_dungeon(path: str, include_subfolders: bool = True, output_dir: str = "dungeon_output") -> dict:
    """
    Scans folder and produces dungeon_data.json in <base>/_DungeonOutput by default.
    """
    global LAST_OUTPUT_DIR
    base = Path(path).expanduser().resolve()
    if not base.exists() or not base.is_dir():
        return {"status": "error", "message": "Dungeon entrance not found (invalid folder path)."}

    out = _resolve_output_dir(base, output_dir)
    out.mkdir(parents=True, exist_ok=True)
    LAST_OUTPUT_DIR = out

    data = _build_scan(base, include_subfolders, DEFAULT_EXCLUDE_DIRS)
    data["output_dir"] = str(out)

    (out / "dungeon_data.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    return {
        "status": "ok",
        "base": str(base),
        "output_dir": str(out),
        "file_count": len(data["files"]),
        "room_count": len(data["rooms"]),
        "monster_count": len(data["monsters"]),
        "treasures": data["treasures"],
        "relics": data["relics"],
        "quest_progress": data["quest"]["progress"],
        "data_file": str(out / "dungeon_data.json"),
    }


@mcp.tool()
def plan_reorganize(path: str, include_subfolders: bool = False, output_dir: str = "dungeon_output") -> dict:
    """
    Previews moves without applying them.
    Writes plan_changes.json + undo.ps1 into output_dir.
    """
    base = Path(path).expanduser().resolve()
    if not base.exists() or not base.is_dir():
        return {"status": "error", "message": "Dungeon entrance not found (invalid folder path)."}

    out = _resolve_output_dir(base, output_dir)
    out.mkdir(parents=True, exist_ok=True)

    changes = _plan_reorganize(base, include_subfolders, DEFAULT_EXCLUDE_DIRS)
    (out / "plan_changes.json").write_text(json.dumps(changes, indent=2), encoding="utf-8")
    undo = _write_undo_ps1(out, changes)

    rooms_breakdown: Dict[str, int] = {}
    for c in changes:
        rooms_breakdown[c["room"]] = rooms_breakdown.get(c["room"], 0) + 1

    return {
        "status": "ok",
        "mode": "dry_run",
        "moves": len(changes),
        "output_dir": str(out),
        "plan_changes_json": str(out / "plan_changes.json"),
        "undo_ps1": str(undo),
        "rooms_breakdown": rooms_breakdown,
    }


@mcp.tool()
def reorganize(path: str, include_subfolders: bool = False, mode: str = "dry_run", output_dir: str = "dungeon_output") -> dict:
    """
    Reorganizes files into:
      <base>/_Sorted/<Room Name>/
    mode: dry_run | apply

    Always writes:
      changes.json + undo.ps1 into output_dir
    """
    base = Path(path).expanduser().resolve()
    if not base.exists() or not base.is_dir():
        return {"status": "error", "message": "Dungeon entrance not found (invalid folder path)."}

    if mode not in ("dry_run", "apply"):
        return {"status": "error", "message": "Invalid mode. Use 'dry_run' or 'apply'."}

    out = _resolve_output_dir(base, output_dir)
    out.mkdir(parents=True, exist_ok=True)

    changes = _plan_reorganize(base, include_subfolders, DEFAULT_EXCLUDE_DIRS)

    applied = 0
    failed: List[dict] = []

    if mode == "apply":
        for c in changes:
            try:
                src = Path(c["from"])
                dst = Path(c["to"])
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                applied += 1
            except Exception as e:
                failed.append({"from": c["from"], "to": c["to"], "error": str(e)})

    (out / "changes.json").write_text(json.dumps(changes, indent=2), encoding="utf-8")
    undo = _write_undo_ps1(out, changes)

    return {
        "status": "ok",
        "mode": mode,
        "planned_moves": len(changes),
        "applied_moves": applied if mode == "apply" else 0,
        "failed_moves": len(failed),
        "failed": failed[:30],
        "sorted_root": str((base / "_Sorted").resolve()),
        "output_dir": str(out),
        "changes_json": str(out / "changes.json"),
        "undo_ps1": str(undo),
    }


@mcp.tool()
def trash_loot(path: str) -> dict:
    """
    Sends a file to Recycle Bin.
    """
    p = Path(path).expanduser().resolve()
    if not p.exists() or not p.is_file():
        return {"status": "error", "message": "File not found."}
    send2trash(str(p))
    return {"status": "ok", "action": "trashed", "path": str(p)}


@mcp.tool()
def generate_index(output_dir: str = "dungeon_output") -> dict:
    """
    Generates a premium game-themed dashboard: index.html
    Must run scan_dungeon first (or pass output_dir that contains dungeon_data.json).
    """
    global LAST_OUTPUT_DIR

    if output_dir == "dungeon_output":
        out = LAST_OUTPUT_DIR or Path("dungeon_output").resolve()
    else:
        out = Path(output_dir).expanduser().resolve()

    data_path = out / "dungeon_data.json"
    if not data_path.exists():
        return {"status": "error", "message": "dungeon_data.json not found. Run scan_dungeon first."}

    data = json.loads(data_path.read_text(encoding="utf-8"))

    total_size_label = _format_bytes(int(data.get("total_size", 0)))
    files = data.get("files", [])
    monsters = data.get("monsters", [])
    quest = data.get("quest", {})
    rooms = data.get("rooms", {})  # ✅ define rooms properly
    rooms_count = len(rooms)

    embedded = json.dumps(data)
    progress = int(quest.get("progress", 0))
    scan_date = str(data.get("scan_date", ""))
    base_path = str(data.get("base", ""))

    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>DungeonOrganizer — File Dungeon</title>
  <link href="https://fonts.googleapis.com/css2?family=Press+Start+2P&family=VT323&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg0:#07060a;
      --bg1:#0d0b12;
      --panel:#151326;
      --panel2:#0f0e1a;
      --stroke:#2a2741;
      --stroke2:#3a3658;
      --gold:#facd13;
      --accent:#00d2ff;
      --violet:#7d5fff;
      --danger:#ff4757;
      --ghost:#a29bfe;
      --muted:#a9afc3;
      --px:4px;
      --radius: 14px;
    }

    * { box-sizing:border-box; }
    body {
      margin:0;
      color:#eef0ff;
      font-family:'VT323', monospace;
      font-size: 20px;
      background:
        radial-gradient(1200px 700px at 20% -10%, rgba(125,95,255,.25), transparent 60%),
        radial-gradient(900px 500px at 100% 0%, rgba(0,210,255,.18), transparent 55%),
        linear-gradient(180deg, var(--bg0), var(--bg1));
      overflow-x:hidden;
    }
    body:before {
      content:"";
      position:fixed; inset:0;
      background: linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px);
      background-size: 100% 4px;
      pointer-events:none;
      opacity:.25;
      z-index: 5;
    }

    .wrap {
      width: min(1600px, calc(100vw - 32px));
      margin: 26px auto;
      padding: 0 16px 40px;
      position: relative;
      z-index: 10;
    }

    .topbar {
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap: 16px;
      margin-bottom: 14px;
    }
    .brand { display:flex; align-items:center; gap: 12px; }
    .brand .logo {
      width: 42px; height: 42px;
      border: 2px solid var(--stroke2);
      border-radius: 12px;
      background: linear-gradient(135deg, rgba(125,95,255,.35), rgba(0,210,255,.18));
      box-shadow: 0 10px 30px rgba(0,0,0,.35);
      display:grid; place-items:center;
      font-size: 20px;
    }
    .brand h1 {
      margin:0;
      font-family:'Press Start 2P';
      font-size: 14px;
      color: var(--gold);
      text-shadow: 4px 4px 0 rgba(0,0,0,.35);
      line-height:1.2;
    }
    .brand .sub { color: var(--muted); font-size: 16px; margin-top: 2px; }

    .pill {
      display:inline-flex;
      align-items:center;
      gap: 10px;
      padding: 10px 12px;
      background: rgba(0,0,0,.28);
      border: 2px solid var(--stroke);
      border-radius: 999px;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,.06);
      color: var(--muted);
      font-size: 16px;
      white-space:nowrap;
    }
    .pill b { color: #fff; font-weight: 700; }
    .pill .dot {
      width: 8px; height: 8px; border-radius: 999px;
      background: var(--accent);
      box-shadow: 0 0 0 4px rgba(0,210,255,.15);
    }

    .grid {
      display:grid;
      grid-template-columns: minmax(340px, 420px) 1fr;
      gap: 14px;
    }
    @media (max-width: 980px) { .grid { grid-template-columns: 1fr; } }

    .panel {
      min-height: calc(100vh - 110px);
      background: linear-gradient(180deg, rgba(21,19,38,.95), rgba(15,14,26,.95));
      border: 2px solid var(--stroke);
      border-radius: var(--radius);
      box-shadow: 0 18px 60px rgba(0,0,0,.40);
      position: relative;
      overflow:hidden;
    }
    @media (max-width: 980px){ .panel{ min-height: auto; } }

    .panel:before {
      content:"";
      position:absolute; inset:0;
      background: radial-gradient(800px 260px at 10% 0%, rgba(250,205,19,.09), transparent 60%),
                  radial-gradient(700px 240px at 90% 0%, rgba(0,210,255,.08), transparent 58%);
      pointer-events:none;
      opacity: .9;
    }
    .panel > .inner { position: relative; padding: 14px; }

    .hud { display:grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
    .stat { background: rgba(0,0,0,.25); border: 2px solid var(--stroke); border-radius: 12px; padding: 12px; }
    .stat .k { color: var(--muted); font-family:'Press Start 2P'; font-size: 9px; margin-bottom: 8px; }
    .stat .v { font-size: 26px; display:flex; align-items:baseline; gap: 8px; }
    .gold { color: var(--gold); }
    .danger { color: var(--danger); }
    .ghost { color: var(--ghost); }

    .sectionTitle { font-family:'Press Start 2P'; font-size: 10px; color: var(--gold); margin: 6px 0 10px; }

    .questCard { background: rgba(0,0,0,.22); border: 2px dashed rgba(250,205,19,.65); border-radius: 14px; padding: 12px; }
    .questTop { display:flex; align-items:flex-start; justify-content:space-between; gap: 10px; }
    .questTop .name { font-family:'Press Start 2P'; font-size: 11px; margin: 0; }
    .questTop .xp { color: var(--accent); font-family:'Press Start 2P'; font-size: 9px; white-space: nowrap; }
    .questDesc { margin-top: 10px; color: var(--muted); font-size: 18px; }

    .bar { margin-top: 12px; height: 12px; border-radius: 999px; background: rgba(0,0,0,.35); border: 1px solid rgba(255,255,255,.10); overflow:hidden; }
    .fill { height:100%; width: __QUEST_PROGRESS__%; background: linear-gradient(90deg, var(--violet), var(--accent)); box-shadow: 0 0 22px rgba(0,210,255,.25); }

    .questMeta { display:flex; justify-content:space-between; gap: 10px; margin-top: 8px; color: var(--muted); font-size: 16px; }

    .actions { display:flex; flex-wrap:wrap; gap: 6px; margin-top: 10px; }
    .btn {
      cursor:pointer;
      user-select:none;
      padding: 9px 10px;
      border-radius: 12px;
      border: 2px solid var(--stroke2);
      background: rgba(0,0,0,.25);
      color: #fff;
      font-family:'Press Start 2P';
      font-size: 9px;
      transition: .15s;
      display:inline-flex;
      align-items:center;
      gap: 10px;
    }
    .btn:hover { transform: translateY(-1px); border-color: rgba(0,210,255,.55); box-shadow: 0 12px 25px rgba(0,0,0,.35); }
    .btn .tag { font-family:'VT323'; font-size: 16px; color: var(--muted); }

    .mainHeader { display:flex; align-items:center; justify-content:space-between; gap: 12px; margin-bottom: 8px; }
    .tabs { display:flex; gap: 8px; flex-wrap:wrap; }
    .tab { cursor:pointer; padding: 10px 12px; border-radius: 12px; border: 2px solid var(--stroke); background: rgba(0,0,0,.18); color: var(--muted); font-family:'Press Start 2P'; font-size: 9px; transition:.15s; }
    .tab.active { color:#fff; border-color: rgba(250,205,19,.55); background: rgba(250,205,19,.08); }

    .search { width: 100%; padding: 12px 12px; border-radius: 12px; border: 2px solid var(--stroke); background: rgba(0,0,0,.22); color: #fff; font-family:'VT323'; font-size: 18px; outline: none; }

    .roomGrid { display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px; margin-top: 10px; }
    .room { cursor:pointer; background: rgba(0,0,0,.20); border: 2px solid var(--stroke); border-radius: 14px; padding: 12px; transition: .15s; }
    .room:hover { transform: translateY(-1px); border-color: rgba(0,210,255,.55); }
    .room .name { font-family:'Press Start 2P'; font-size: 10px; color: var(--accent); margin-bottom: 10px; }
    .room .nums { display:flex; gap: 12px; flex-wrap:wrap; font-size: 22px; margin-bottom: 8px; }
    .room .nums span { color: #fff; }
    .room .nums .t { color: var(--gold); }
    .room .nums .r { color: var(--ghost); }
    .room .nums .m { color: var(--danger); }
    .room .small { color: var(--muted); font-size: 16px; display:flex; justify-content:space-between; }

    .list { margin-top: 10px; border: 2px solid var(--stroke); border-radius: 14px; overflow:hidden; background: rgba(0,0,0,.20); }
    .rowItem { display:flex; justify-content:space-between; gap: 12px; padding: 10px 12px; border-bottom: 1px solid rgba(255,255,255,.06); }
    .rowItem:last-child { border-bottom:none; }
    .rowItem .left { display:flex; align-items:center; gap: 10px; min-width: 0; }

    .badge { font-family:'Press Start 2P'; font-size: 8px; padding: 6px 8px; border-radius: 999px; border: 1px solid rgba(255,255,255,.12); color: #fff; background: rgba(255,255,255,.06); white-space:nowrap; }
    .badge.treasure { border-color: rgba(250,205,19,.4); color: var(--gold); }
    .badge.relic { border-color: rgba(162,155,254,.45); color: var(--ghost); }
    .badge.monster { border-color: rgba(255,71,87,.45); color: var(--danger); }

    .fname { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width: 620px; }
    .muted { color: var(--muted); }

    .toast {
      position: fixed;
      bottom: 16px;
      left: 50%;
      transform: translateX(-50%);
      background: rgba(0,0,0,.7);
      border: 2px solid rgba(0,210,255,.35);
      border-radius: 12px;
      padding: 10px 12px;
      color:#fff;
      font-size: 16px;
      display:none;
      z-index: 999;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div class="brand">
        <div class="logo">🧭</div>
        <div>
          <h1>DUNGEON ORGANIZER</h1>
          <div class="sub">File Organizer MCP • Dungeon Theme UI</div>
        </div>
      </div>
      <div class="pill"><span class="dot"></span> Scan: <b>__SCAN_DATE__</b> • Base: <b>__BASE_PATH__</b></div>
    </div>

    <div class="grid">
      <div class="panel">
        <div class="inner">
          <div class="sectionTitle">🏰 DUNGEON HUD</div>
          <div class="hud">
            <div class="stat"><div class="k">FILES</div><div class="v"><span class="gold">__FILES_COUNT__</span></div></div>
            <div class="stat"><div class="k">ROOMS</div><div class="v"><span class="gold">__ROOMS_COUNT__</span></div></div>
            <div class="stat"><div class="k">MONSTERS</div><div class="v"><span class="danger">__MONSTERS_COUNT__</span></div></div>
            <div class="stat"><div class="k">STORAGE</div><div class="v"><span class="gold">__TOTAL_SIZE__</span></div></div>
            <div class="stat"><div class="k">TREASURES</div><div class="v"><span class="gold">__TREASURES__</span></div></div>
            <div class="stat"><div class="k">ANCIENT</div><div class="v"><span class="ghost">__RELICS__</span></div></div>
          </div>

          <div style="height:12px"></div>

          <div class="sectionTitle">📜 MAIN QUEST</div>
          <div class="questCard">
            <div class="questTop">
              <div><div class="name">__QUEST_ICON__ __QUEST_TITLE__</div></div>
              <div class="xp">+__QUEST_XP__ XP</div>
            </div>
            <div class="questDesc">__QUEST_DESC__</div>
            <div class="bar"><div class="fill"></div></div>
            <div class="questMeta">
              <span>Progress: <b class="gold">__QUEST_PROGRESS__%</b></span>
              <span>Rank: <b class="gold">__QUEST_RANK__</b></span>
            </div>
            <div class="muted" style="margin-top:8px;">Hint: __QUEST_HINT__</div>

            <div class="actions">
              <div class="btn" onclick="copyCmd('plan_reorganize')">🧾 <span>PLAN</span> <span class="tag">dry_run</span></div>
              <div class="btn" onclick="copyCmd('reorganize')">⚔️ <span>APPLY</span> <span class="tag">apply</span></div>
              <div class="btn" onclick="copyCmd('scan_dungeon')">🔎 <span>RESCAN</span> <span class="tag">refresh</span></div>

              <div class="btn" onclick="copyCmd('move_loot')">📦 <span>MOVE</span> <span class="tag">optional</span></div>
              <div class="btn" onclick="copyCmd('rename_loot')">🏷️ <span>RENAME</span> <span class="tag">optional</span></div>
              <div class="btn" onclick="copyCmd('trash_loot')">🗑️ <span>TRASH</span> <span class="tag">optional</span></div>
            </div>

            <div class="muted" style="margin-top:10px; font-size:16px;">
              Copied prompts are meant to be pasted into Claude to run tools.
            </div>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="inner">
          <div class="mainHeader">
            <div class="sectionTitle">🗺️ DUNGEON MAP</div>
            <div class="tabs">
              <div class="tab active" data-tab="rooms" onclick="setTab('rooms')">ROOMS</div>
              <div class="tab" data-tab="files" onclick="setTab('files')">FILES</div>
              <div class="tab" data-tab="monsters" onclick="setTab('monsters')">MONSTERS</div>
            </div>
          </div>

          <input class="search" id="q" placeholder="Search loot by name or extension... (e.g., thesis, .pdf, photo)" oninput="render()"/>

          <div id="roomsTab"><div class="roomGrid" id="roomGrid"></div></div>
          <div id="filesTab" style="display:none;"><div class="list" id="fileList"></div></div>
          <div id="monstersTab" style="display:none;"><div class="list" id="monsterList"></div></div>

          <div class="muted" style="margin-top:10px; font-size:16px;">
            Tip: Click a room to filter files to that room.
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="toast" id="toast">Copied!</div>

<script>
  const DATA = __EMBEDDED_JSON__;
  let currentTab = "rooms";
  let roomFilter = null;

  const monsterPaths = new Set();
  (DATA.monsters || []).forEach(m => {
    if (m.type === "behemoth" && m.path) monsterPaths.add(m.path);
    if (m.type === "duplicate") {
      if (m.a) monsterPaths.add(m.a);
      if (m.b) monsterPaths.add(m.b);
    }
  });

  function setTab(tab) {
    currentTab = tab;
    document.querySelectorAll(".tab").forEach(t => {
      t.classList.toggle("active", t.dataset.tab === tab);
    });
    document.getElementById("roomsTab").style.display = (tab === "rooms") ? "block" : "none";
    document.getElementById("filesTab").style.display = (tab === "files") ? "block" : "none";
    document.getElementById("monstersTab").style.display = (tab === "monsters") ? "block" : "none";
    render();
  }

  function toast(msg) {
    const t = document.getElementById("toast");
    t.textContent = msg;
    t.style.display = "block";
    clearTimeout(window.__toastTimer);
    window.__toastTimer = setTimeout(() => t.style.display = "none", 1100);
  }

  function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => toast("Copied prompt to clipboard"));
  }

  function copyCmd(kind) {
    const base = DATA.base;
    if (!base) { toast("Missing base path in data"); return; }

    if (kind === "scan_dungeon") { copyToClipboard(`scan_dungeon on "${base}" include_subfolders=true`); return; }
    if (kind === "plan_reorganize") { copyToClipboard(`plan_reorganize on "${base}" include_subfolders=false`); return; }
    if (kind === "reorganize") { copyToClipboard(`reorganize on "${base}" include_subfolders=false mode="apply"`); return; }
    if (kind === "move_loot") { copyToClipboard(`move_loot with src="<paste a file path from scan>" dest_dir="${base}\\_MovedLoot"`); return; }
    if (kind === "rename_loot") { copyToClipboard(`rename_loot with src="<paste a file path from scan>" new_name="renamed_loot.ext"`); return; }
    if (kind === "trash_loot") { copyToClipboard(`trash_loot with path="<paste a file path from scan>"`); return; }
  }

  function fmtBytes(n) {
    if (n < 1024) return `${n} B`;
    if (n < 1024*1024) return `${(n/1024).toFixed(1)} KB`;
    if (n < 1024*1024*1024) return `${(n/1024/1024).toFixed(1)} MB`;
    return `${(n/1024/1024/1024).toFixed(2)} GB`;
  }

  function setRoomFilter(roomName) { roomFilter = roomName; setTab("files"); }
  function clearRoomFilter() { roomFilter = null; render(); }
  function getQuery() { return (document.getElementById("q").value || "").trim().toLowerCase(); }

  function renderRooms() {
    const grid = document.getElementById("roomGrid");
    grid.innerHTML = "";
    const rooms = DATA.rooms || {};
    const list = Object.keys(rooms).map(k => ({
      name: k,
      count: rooms[k].count || 0,
      size: rooms[k].size || 0,
      treasure: rooms[k].treasure || 0,
      relic: rooms[k].relic || 0
    })).sort((a,b) => b.size - a.size);

    list.forEach(r => {
      const div = document.createElement("div");
      div.className = "room";
      div.onclick = () => setRoomFilter(r.name);

      const monsterCount = (DATA.files || []).filter(f => f.room === r.name && monsterPaths.has(f.path)).length;

      div.innerHTML = `
        <div class="name">${r.name}</div>
        <div class="nums">
          <span>📦 <b>${r.count}</b></span>
          <span class="m">👾 <b>${monsterCount}</b></span>
          <span class="t">💎 <b>${r.treasure}</b></span>
          <span class="r">👻 <b>${r.relic}</b></span>
        </div>
        <div class="small"><span>Size</span><span>${fmtBytes(r.size)}</span></div>
      `;
      grid.appendChild(div);
    });
  }

  function renderFiles() {
    const q = getQuery();
    const listEl = document.getElementById("fileList");
    listEl.innerHTML = "";

    let files = (DATA.files || []);
    if (roomFilter) {
      files = files.filter(f => f.room === roomFilter);
      const head = document.createElement("div");
      head.className = "rowItem";
      head.innerHTML = `
        <div class="left">
          <span class="badge">FILTER</span>
          <span class="fname">Room: <b>${roomFilter}</b></span>
        </div>
        <div class="muted" style="cursor:pointer;" onclick="clearRoomFilter()">Clear</div>
      `;
      listEl.appendChild(head);
    }

    if (q) {
      files = files.filter(f => {
        const n = (f.name || "").toLowerCase();
        const e = (f.ext || "").toLowerCase();
        return n.includes(q) || e.includes(q);
      });
    }

    files = files.slice().sort((a,b) => (b.mtime||0) - (a.mtime||0)).slice(0, 140);

    files.forEach(f => {
      const badges = [];
      if (f.treasure) badges.push('<span class="badge treasure">TREASURE</span>');
      if (f.relic) badges.push('<span class="badge relic">ANCIENT</span>');
      if (monsterPaths.has(f.path)) badges.push('<span class="badge monster">MONSTER</span>');

      const row = document.createElement("div");
      row.className = "rowItem";
      row.innerHTML = `
        <div class="left">
          ${badges.join("")}
          <span class="fname" title="${f.path}">${f.name}</span>
          <span class="muted">${f.ext}</span>
        </div>
        <div class="muted">${fmtBytes(f.size || 0)}</div>
      `;
      listEl.appendChild(row);
    });

    if (!files.length) {
      const empty = document.createElement("div");
      empty.className = "rowItem";
      empty.innerHTML = `<div class="muted">No loot found for this filter/search.</div><div></div>`;
      listEl.appendChild(empty);
    }
  }

  function renderMonsters() {
    const q = getQuery();
    const listEl = document.getElementById("monsterList");
    listEl.innerHTML = "";

    let mons = (DATA.monsters || []);
    if (q) {
      mons = mons.filter(m => JSON.stringify(m).toLowerCase().includes(q));
    }

    mons = mons.slice(0, 140);

    mons.forEach(m => {
      const row = document.createElement("div");
      row.className = "rowItem";

      if (m.type === "behemoth") {
        row.innerHTML = `
          <div class="left">
            <span class="badge monster">BEHEMOTH</span>
            <span class="fname" title="${m.path}">${m.path}</span>
          </div>
          <div class="muted">${fmtBytes(m.size || 0)}</div>
        `;
        listEl.appendChild(row);
      } else {
        row.innerHTML = `
          <div class="left">
            <span class="badge monster">DUPLICATE</span>
            <span class="fname" title="${m.a}">${m.a}</span>
          </div>
          <div class="muted">↔</div>
        `;
        listEl.appendChild(row);

        const row2 = document.createElement("div");
        row2.className = "rowItem";
        row2.innerHTML = `
          <div class="left">
            <span class="badge monster">DUPLICATE</span>
            <span class="fname" title="${m.b}">${m.b}</span>
          </div>
          <div class="muted">${fmtBytes(m.size || 0)}</div>
        `;
        listEl.appendChild(row2);
      }
    });

    if (!mons.length) {
      const empty = document.createElement("div");
      empty.className = "rowItem";
      empty.innerHTML = `<div class="muted">No monsters detected.</div><div></div>`;
      listEl.appendChild(empty);
    }
  }

  function render() {
    if (currentTab === "rooms") renderRooms();
    if (currentTab === "files") renderFiles();
    if (currentTab === "monsters") renderMonsters();
  }

  render();
</script>
</body>
</html>
"""

    html = (
        html.replace("__EMBEDDED_JSON__", embedded)
            .replace("__QUEST_PROGRESS__", str(progress))
            .replace("__SCAN_DATE__", scan_date)
            .replace("__BASE_PATH__", base_path)
            .replace("__FILES_COUNT__", str(len(files)))
            .replace("__ROOMS_COUNT__", str(rooms_count))
            .replace("__MONSTERS_COUNT__", str(len(monsters)))
            .replace("__TOTAL_SIZE__", total_size_label)
            .replace("__TREASURES__", str(int(data.get("treasures", 0))))
            .replace("__RELICS__", str(int(data.get("relics", 0))))
            .replace("__QUEST_ICON__", str(quest.get("icon", "🗡️")))
            .replace("__QUEST_TITLE__", str(quest.get("title", "Quest")))
            .replace("__QUEST_XP__", str(int(quest.get("xp", 0))))
            .replace("__QUEST_DESC__", str(quest.get("desc", "")))
            .replace("__QUEST_RANK__", str(quest.get("rank", "D")))
            .replace("__QUEST_HINT__", str(quest.get("hint", "")))
    )

    index_path = out / "index.html"
    index_path.write_text(html, encoding="utf-8")
    return {"status": "ok", "output_dir": str(out), "index": str(index_path)}



@mcp.tool()
def move_loot(src: str, dest_dir: str) -> dict:
    """
    Moves a file to a destination folder.
    """
    s = Path(src).expanduser().resolve()
    d = Path(dest_dir).expanduser().resolve()
    if not s.exists() or not s.is_file():
        return {"status": "error", "message": "Source file not found."}
    d.mkdir(parents=True, exist_ok=True)
    dest = _safe_dest(d, s.name)
    shutil.move(str(s), str(dest))
    return {"status": "ok", "from": str(s), "to": str(dest)}


@mcp.tool()
def rename_loot(src: str, new_name: str) -> dict:
    """
    Renames a file in place.
    """
    s = Path(src).expanduser().resolve()
    if not s.exists() or not s.is_file():
        return {"status": "error", "message": "File not found."}
    if any(x in new_name for x in ['\\', '/', '|', ':', '*', '?', '"', '<', '>']):
        return {"status": "error", "message": "Invalid characters in name."}
    dest = s.parent / new_name
    i = 1
    while dest.exists():
        dest = s.parent / f"{Path(new_name).stem}_{i}{Path(new_name).suffix}"
        i += 1
    s.rename(dest)
    return {"status": "ok", "from": str(s), "to": str(dest)}


if __name__ == "__main__":
    print("DungeonOrganizer Online...")
    mcp.run(transport="stdio")
