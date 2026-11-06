# nx2android — Porter Modules

All under `porter/`. The CLI entry is `python -m porter` (`__main__.py` → `cli.py`). Subcommands: `doctor`, `profiles`, `inspect <folder>`, `port <folder>`, `install`, `devices`, `config`, `saves`, `tools`.

## Module table

| Module | Purpose | Key Classes / Functions | Inputs | Outputs | Called By |
|---|---|---|---|---|---|
| `__init__.py` | Version and docstring | `__version__ = '0.3.0'` | — | Version string | Everything |
| `__main__.py` | CLI entry point | calls `cli.main()` | sys.argv | Exit code | `python -m porter` |
| `cli.py` | Argument parsing & dispatch | Subcommands for all porter operations | --help, port args, etc. | Pipeline execution | User / GUI runner |
| `config.py` | Player settings persistence | `load()`, `save()`, `set_value()`; KEY dict (keys, ndk, dotnet, adb, out, device, language) | `<user_dir>/config.json` | Dict of current config | GUI Setup tab, CLI |
| `pipeline.py` | The port pipeline core | `Porter.start(options)` → extract/rewrite/shaders/host/apk/data/install; `Options` dataclass | Game folder, keys, options | APK + data pack paths | `cli.py`, `gui/runner.py` |
| `profiles.py` | Game profile registry | `all_entries()`, `by_title(tid)`, `load(gid)` — reads `nxnative/dm/games/<id>/android.tsv` | Profile TSV files | Entry objects with status/tested/package | CLI, GUI Games tab |
| `dumps.py` | Compressed dump decompression | `decompress(src, dst, done)`, `unpack()`, `_ncz()` — NSZ/XCZ → NSP via AES-CTR + zstd | NSZ/XCZ file, output path | NSP file with correct SHA-256 names | `pipeline.py` unpack stage |
| `fetch.py` | Toolchain download | `download(items)` — fetches NDK r27c, .NET SDK 10, platform-tools from Google/Microsoft with checksum verification | Item list | Installed toolchains in `toolchains/` | CLI `tools --download`, GUI Setup |
| `install.py` | APK + data pack install over ADB | `install(apk_path, data_path, adb_exe, ...)` — pushes APK, RomFS (with optional `--romfs-at`), data files; checks manifest | APK, data pack, adb exe | Confirmation on device | `pipeline.py install()`, CLI `install` |
| `saves.py` | Save manager over ADB | `connect()`, `list()`, `export(folder)`, `import(src)` — stops app, writes request file, reads result; supports .zip imports | ADB exe, package name | Save folders on PC / device | GUI Saves tab, CLI `saves` |
| `adb.py` | ADB wrapper with resumable pushes | `Adb.run()`, `push_tree()`, `push_file()`, `push_tars()` — chunks large files, tar archives for many small files, resumable by MD5 | Local paths, remote device paths | Pushed files verified on device | `install.py`, `saves.py` |
| `toolchain.py` | Toolchain discovery & check | `checks(cfg, keys)` → `[Check(...)]`; `require()` → `{ndk, dotnet, adb}`; finds NDK r27c, .NET 10, adb in config/env/standard paths | Config file, keys path | Check results (ok/detail/fix) | CLI `doctor`, GUI Setup tab |
| `fpslocker.py` | FPSLocker config fetch & convert | `fetch(tid, bid)` → raw YAML; `convert(text, image, bid)` → fpslock.tsv + CUTS patches; only reads from masagrator's Warehouse | Game build ID | fpslock.tsv (for host) + rewriter cuts | Called during port pipeline |
| `datapack.py` | Data pack builder | `build(dst, profile, version, ...)` — creates mods/RomFS/aoc links, shaders.dmsv, env.txt, settings.txt, nx2a-data.json manifest; hard-links large trees | Patched modules, RomFS, shaders | `<game>-data/` folder with manifest | `pipeline.py data()` |
| `paths.py` | Path constants | `REPO`, `NXNATIVE`, `DM`, `user_dir()`, `player_tools()`, `signing_key()` | — | Computed paths | All modules |

---

## Entry points

| Entry | Command | What it does |
|---|---|---|
| CLI | `python -m porter port <folder> -k <keys>` | Full port pipeline: extract → rewrite → shaders → host → APK → data pack |
| GUI | `python -m gui` or `nx2android.exe` | PySide6 app with Port/Setup/Games/Saves tabs; runs `porter port --progress json` |
| Bundle | `python packaging/build_bundle.py` | Builds distributable zip (PyInstaller bundle + committed nxnative/) |

---

## Key data flows between modules

```
cli.py ──args──> pipeline.py ──uses──> dumps.py    (NSZ decompression)
                    │                    fpslocker.py (60fps configs from Warehouse)
                    │                    profiles.py  (game registry lookup)
                    │                    toolchain.py  (NDK/.NET/adb checks)
                    │                    fetch.py      (tool download)
                    │                    install.py    (push to device)
                    │                    saves.py      (save import/export)
                    │                    adb.py        (ADB operations)
                    │                    datapack.py   (data pack assembly)
                    │                    paths.py      (path resolution)
                    ▼
              emits JSON events ──> gui/runner.py (consumes for progress UI)
```

---

*Sources: porter/__init__.py, Porter/*.py files.*
