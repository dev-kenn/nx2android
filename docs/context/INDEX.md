# nx2android — Context Index

All files in `docs/context/`. Together they document the project for rapid onboarding and context recovery.

---

| File | Topic | Read First? |
|------|-------|:-----------:|
| [00-overview.md](00-overview.md) | Project overview, goals, tech stack, repo map | **Yes** |
| [01-architecture.md](01-architecture.md) | Component diagram, data flow, what runs where | Yes |
| [02-porter-modules.md](02-porter-modules.md) | Porter Python modules (CLI + pipeline) | Yes |
| [03-nxnative-runtime.md](03-nxnative-runtime.md) | C runtime: Horizon host, Vulkan backend, game profiles | Yes |
| [04-workflows.md](04-workflows.md) | Git conventions, testing, build/release process | |
| [05-game-status.md](05-game-status.md) | Per-game status table, hardware matrix | |
| [06-open-questions.md](06-open-questions.md) | Open issues, TODOs, recent changes to know | |

---

## How to Read These Files

1. **Start with `00-overview.md`** — gives the 30,000-foot view of what nx2android is and does.
2. **Then `01-architecture.md`** — how components connect and where code runs.
3. **Pick the layer you need:**
   - Working on the port pipeline? Read `02-porter-modules.md`.
   - Debugging runtime behavior? Read `03-nxnative-runtime.md`.
4. **Check `05-game-status.md`** for which games are playable and on what hardware.
5. **Scan `06-open-questions.md`** for things worth investigating before making changes.

---

## Cross-References to External Docs

These files link back to the authoritative sources in the repository:

| Context File | Key External Sources |
|-------------|---------------------|
| 00-overview.md | `README.md`, `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT_GUIDE.md` |
| 01-architecture.md | `porter/README.md`, `porter/pipeline.py`, `PORT_CHECKLIST.md` |
| 02-porter-modules.md | All files in `porter/` directory |
| 03-nxnative-runtime.md | `nxnative/dm/android/*`, `nxnative/dm/host/*` |
| 04-workflows.md | `docs/DEVELOPMENT_GUIDE.md`, `porter/README.md` |
| 05-game-status.md | `nxnative/dm/games/*/android.tsv`, `README.md#games` |
| 06-open-questions.md | `README.md`, `ARCHITECTURE.md`, `PORT_CHECKLIST.md` |

---

## Key Files You May Need to Edit

| Purpose | Files to Open |
|---------|---------------|
| Add a new game profile | `nxnative/dm/games/<titleID>/game.tsv` + `android.tsv` |
| Fix port pipeline bug | `porter/pipeline.py`, `porter/*.py` |
| Debug runtime crash | `nxnative/dm/host/hle_*.c`, `nxnative/dm/android/gfx_vk_*.c` |
| Add a new CLI command | `gui/runner.py`, `cli.py` (in nx2android skill) |
| Update port status | README.md, `nxnative/dm/games/*/android.tsv` |

---

*Generated automatically. Not manually maintained.*
