# nx2android - Game Status

Per-game profile status and hardware tested. Data from `nxnative/dm/games/*/android.tsv` + README Games table.

## Summary

- **38 profiles** with `android.tsv` (playable / wip / boots / experimental)
- **79 total game profiles** in `nxnative/dm/games/` (including upstream-only ports)
- ~41 games not yet ported on Android (iOS-only profiles exist)
- Primary test hardware: Lenovo Legion Y700 (Snapdragon 8 Elite, Adreno 830, Android 16)

## Playable Games (from `status: playable` in android.tsv)

All render via NVN (Maxwell). BC-compressed textures on Adreno/Xclipse. Tested on Y700 unless noted.

| # | Game | Title ID | FPS | Notes |
|---|------|----------|-----|-------|
| 1 | Super Mario Odyssey | `0100000000010000` | 60 | |
| 2 | Graveyard Keeper 2 | `0100005027A18000` | 60 | |
| 3 | Tales of Eternia Remastered | `010006E0230AC000` | 60 | |
| 4 | Hollow Knight: Silksong | `010013C00E930000` | 60 | |
| 5 | Super Mario Bros. Wonder | `010015100B514000` | 60 | |
| 6 | Pokemon Legends: Arceus | `01001F5010DFA000` | 60 | |
| 7 | Celeste | `01002B30028F6000` | 60 | |
| 8 | Advance Wars 1+2: Re-Boot Camp | `0100300012F2A000` | 60 | 30 in battle |
| 9 | UNDER NIGHT IN-BIRTH Exe:Late | `010038C00EC34000` | 60 | |
| 10 | 13 Sentinels: Aegis Rim | `01003FC01670C000` | 60 | |
| 11 | Blasphemous 2 | `010040801A4C8000` | 60 | |
| 12 | NEO: The World Ends with You | `010043B013C5C000` | 60 | |
| 13 | DARK SOULS: REMASTERED | `01004AB00A260000` | 30 | As on Switch |
| 14 | FINAL FANTASY RESONANCE | `0100606026F12000` | 60 | |
| 15 | Unpacking | `0100701015846000` | 60 | |
| 16 | Untitled Goose Game | `010082400BCC6000` | 60 | |
| 17 | Metroid Dread | `010093801237C000` | 60 | update 2.1.0 |
| 18 | Captain Toad: Treasure Tracker | `01009BF0072D4000` | 60 | |
| 19 | Donkey Kong Country Returns HD | `01009D901BC56000` | 60 | |
| 20 | Hades II | `0100A00019DE0000` | 60 | |
| 21 | Lonely Mountains: Downhill | `0100A0C00E0DE000` | 60 | Retroid P6, Adreno 740 |
| 22 | Paper Mario: Origami King | `0100A3900C3E2000` | 60 | |
| 23 | Mario vs. Donkey Kong | `0100B99019412000` | 60 | |
| 24 | Castlevania: Belmont's Curse | `0100BA4026E94000` | 60 | |
| 25 | UNDER NIGHT IN-BIRTH II Sys:Celes | `0100BD401D18A000` | 60 | |
| 26 | World Ends with You -Final Remix- | `0100C1500B82E000` | 60 | |
| 27 | Football Manager 26 Touch | `0100D4A023450000` | 30 | touch, match view N/A |
| 28 | Pokemon Legends: Z-A | `0100F43008C44000` | 60 | |
| 29 | Viractal | `0100FD501F95A000` | 60 | |

South Park: Stick of Truth (`010043600B6A6000`) on Xiaomi Pad 5 (SD 860). Paper Mario: TYD in android.tsv.

## Work in Progress

| Game | Title ID | Notes |
|------|----------|-------|
| Xenoblade Chronicles 3 | `010074F013262000` | Under development |
| Paper Mario: TYD | `0100ECD018EBE000` | WIP |

## Bootable Only (status boots)

| Game | Title ID | Notes |
|------|----------|-------|
| Unicorn Overlord | `010069401ADB8000` | Boots, not playable |

## Experimental

| Game | Title ID | Notes |
|------|----------|-------|
| Tomodachi Life: Living the Dream | `010051F0207B2000` | Provisional |
| Unicorn Overlord (Asia) | `010054B01AD92000` | SD 8+ Gen 1 |
| Zelda: Tears of the Kingdom | `0100F2C0115B6000` | TOTK provisional |

## Hardware Matrix

| Device | SoC | GPU | Android | Vulkan | Games |
|--------|-----|-----|---------|--------|-------|
| Lenovo Legion Y700 TB322FC | SD 8 Elite | Adreno 830 | 16 | System | ~34 (primary) |
| Retroid Pocket 6 | QCS8550 | Adreno 740 | 13 | PurpleVK-git-62ac2 | Lonely Mountains: Downhill |
| Xiaomi Pad 5 21051182G | SD 860 | Adreno 640 | 13 | System | South Park: SotT |

Device GPU must read BC-compressed textures. Adreno/Xclipse supported; Mali/PowerVR not yet.

## Not Yet Ported (upstream-only, ~41 games)

Profiles in seedds/nxnative (iOS). No Android work started. Key examples:

| Game | Title ID | Upstream Notes |
|------|----------|----------------|
| ASTRAL CHAIN | `01007300020FA000` | 60 fps with 1.0.1 |
| DQ XI S: Echoes | `01006C300E9F0000` | 60 fps with 1.0.4 |
| FE Engage | `0100A6301214E000` | 60 fps with 2.0.0 |
| FE: Three Houses | `010055D009F78000` | 60 fps with 1.2.0 |
| Hyrule Warriors: AOC | `01002B00111A2000` | 60 fps with 1.3.0 |

Full list in docs/PORT_CHECKLIST.md (33 of 99 ported). Upstream profiles serve as reference.

## How to Update This Table

When testing a game:
1. Update `nxnative/dm/games/<titleID>/android.tsv`: set status and update tested.
2. Update README Games table with new screenshot + version info.

---

*Sources: nxnative/dm/games/*/android.tsv, README.md, docs/PORT_CHECKLIST.md.*