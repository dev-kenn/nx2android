# nx2android — Development Workflow

This documents the development process: git conventions, branch strategy, testing, and release building.

---

## Repository layout at a glance

```
nx2android/
├── porter/          # Python pipeline (CLI): extract → rewrite → shaders → host → APK → data pack
├── gui/             # PySide6 desktop app: Port / Setup / Games / Saves tabs
├── nxnative/        # Our fork: C runtime for Horizon OS emulation + NVN-on-Vulkan replay
├── packaging/       # PyInstaller bundle builder (produces distributable zip)
├── devtools/        # Device bring-up scripts (push, record, soak test)
├── tests/           # Unit tests (architecture rules, porter CLI, ADB, Vulkan memory)
├── probes/          # First on-device feasibility probes (C code)
├── docs/            # Project documentation (ARCHITECTURE.md, etc.)
└── .claude/skills/  # Agent skills for game porting workflows
```

---

## Git conventions

### Branch strategy

| Pattern | Purpose | Example |
|---|---|---|
| `feat/*` | New features / capabilities | `feat/android-external-display` |
| `fix/*` | Bug fixes | `fix/crash-vulkan-init` |
| `docs/*` | Documentation changes | `docs/update-port-status` |
| `dev/beta*` | Beta branches | `dev/beta v0.3.0` |
| `v*.*.*` | Release tags | `v0.4.0` |

### Commit message format

Use **imperative mood, no AI attribution**:

```
<scope>: <description>

Examples:
port: add --external-display option
porter: fix ADB push checksum for 50+ files
nxnative: zero-copy memory pools for Adreno Vulkan
docs: update port status with 12 playable games
tests: add architecture rule for Porter class
```

**No commit messages contain AI attribution lines or model names.**

### Review workflow

1. Branch off `main` (or a beta branch)
2. Write code + tests
3. Commit locally (no push to remote)
4. Pull up any relevant vault notes before continuing
5. If the work spans multiple commits, squash on merge

---

## Testing

### Unit tests

Located in `tests/`. Run with:

```bash
python -m pytest tests/
```

Covers:
- Porter architecture rules (module boundaries)
- ADB push functionality
- Vulkan memory allocation patterns
- Shader format validation
- Game profile parsing

### Per-game testing

Each game port requires manual verification on hardware:

1. Port the game from its folder
2. Install to device via adb
3. Play through key scenes (5+ minutes recommended)
4. Check logs for crash indicators or performance warnings
5. Record results in `nxnative/dm/games/<titleID>/android.tsv`:
   - `status`: playable / wip / boots / experimental
   - `tested`: device name, SoC, Vulkan driver version
   - `env`: any special environment switches used

### Soak testing

For stable games, run extended tests (20+ minutes) and record:
- Frame drops observed
- Memory usage (footprint in GB)
- CPU/GPU per-frame timing
- Any underruns or red log lines

---

## Release building

### From the repository

```bash
cd packaging/
python build_bundle.py [version]
```

Produces a zip archive with:
- The porter CLI (Python scripts + dependencies)
- A committed copy of `nxnative/` source
- `build.gradle` for the Android project
- README with instructions

### Release process

1. Pull up the vault: check for any active notes on this release
2. Ensure all tested games have updated profiles in `nxnative/dm/games/`
3. Update `porter/__init__.py` version number
4. Run full test suite: `python -m pytest tests/`
5. Build bundle: `python packaging/build_bundle.py vX.Y.Z`
6. Review output zip contents
7. Distribute to beta testers

### Beta branches

Named `dev/beta vX.Y.Z`. These accumulate features for the next release. When ready:

```bash
git branch -m dev/beta-v0.4.0 v0.4.0
git tag v0.4.0
# ... distribute and announce
```

---

## Key commands cheat sheet

| Task | Command |
|---|---|
| Port a game | `python -m porter port <folder> -k <keys>` |
| Check device connection | `python -m porter devices` |
| View profile status | `python -m porter profiles` |
| Inspect game folder | `python -m porter inspect <folder>` |
| Install APK + data | `python -m porter port ... --install` |
| Manage saves (GUI) | `python -m gui` → Saves tab |
| Doctor check | `python -m porter doctor` |
| Download tools | `python -m porter tools --download` |
| Run tests | `python -m pytest tests/` |
| Build release bundle | `python packaging/build_bundle.py` |

---

## CI / Automation

Not currently set up. All testing is local on hardware before releases. A PR should include:
- Updated unit tests (where applicable)
- Verified game profiles (TSV files updated)
- Release bundle built locally

---

*Sources: DEVELOPMENT_GUIDE.md, Porter/README.md.*
