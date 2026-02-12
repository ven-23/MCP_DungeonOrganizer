# 🧭 Dungeon Organizer: File Management MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-Protocol-orange.svg)](https://modelcontextprotocol.io)

![DungeonOrganizer UI](dashboard_preview.png)

---

## 🌟 Key Features

### 🏗️ Intelligent Organization ("Rooms")
Automatically categorizes files based on their type and content:
- **🖼️ Images Room**: All visual assets (PNG, JPG, WebP, etc.).
- **📚 Docs Library**: Documents and spreadsheets (PDF, DOCX, XLSX, etc.).
- **💻 Code Cave**: Development files (PY, JS, TS, JSON, etc.).
- **🎵 Media Hall**: Audio and video files (MP4, MKV, MP3, etc.).
- **🧰 Archives Vault**: Compressed files (ZIP, RAR, 7Z, etc.).

### 🐲 Monster & Treasure Detection
- **👾 Monster Hunting**: Automatically identifies "Behemoths" (large files >200MB) and redundant "Duplicates" using SHA-256 hashing.
- **💎 Treasure Finding**: Detects high-value files like invoices, resumes, and contracts using keyword analysis.

### 📜 Interactive Quests
- **Dry-Run Safety**: Preview reorganization changes before applying them.
- **Undo Scripts**: Generates PowerShell (`undo.ps1`) scripts for every major operation.
- **XP & Ranks**: Track your organization progress through a gamified scoring system.

### 📊 Premium Game-Themed Dashboard
Generates a stunning, pixel-art inspired HTML dashboard (`index.html`) to visualize your dungeon stats and browse files.

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10 or higher
- [uv](https://github.com/astral-sh/uv) (recommended) or `pip`

### Installation

#### Using `uv` (Fastest)

```bash
# Clone the repository
git clone https://github.com/your-username/dungeon-server.git
cd dungeon-server

# Run the server
uv run dungeon_server.py
```

#### Using `pip`

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
python dungeon_server.py
```

---

## 🛠️ Configuration for MCP Clients

To integrate **Dungeon Organizer** with Claude Desktop or other MCP-compatible tools, update your `mcpConfig.json` or `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "dungeon-organizer": {
      "command": "python",
      "args": ["C:/absolute/path/to/dungeon_server.py"],
      "cwd": "C:/absolute/path/to/Dungeon Server"
    }
  }
}
```

---

## 🧪 Tool Documentation

| Tool | Description | Key Arguments |
| :--- | :--- | :--- |
| `scan_dungeon` | Performs a deep scan of the directory and generates stats. | `path`, `include_subfolders` |
| `plan_reorganize` | Generates a preview of the reorganization plan. | `path`, `include_subfolders` |
| `reorganize` | Moves files into their assigned rooms (supports `dry_run` and `apply`). | `path`, `mode`, `include_subfolders` |
| `generate_index` | Builds the gamified HTML dashboard. | `output_dir` |
| `trash_loot` | Safely moves unwanted files to the system Recycle Bin. | `path` |
| `move_loot` | Moves specific files to a target directory. | `src`, `dest_dir` |
| `rename_loot` | Renames files in-place with duplicate name protection. | `src`, `new_name` |

---

## 📜 Development & Rules

### Dungeon Room Rules
The server follows a predefined logic for organizing files. You can modify the `ROOM_RULES` dictionary in `dungeon_server.py` to customize file destinations.

### Treasure Keywords
Identifies important files containing keywords like: `invoice`, `resume`, `cv`, `thesis`, `contract`, `grade`, `requirements`, `certificate`, `budget`.

---

## 🛡️ License

Distributed under the MIT License. See `LICENSE` for more information.

---
