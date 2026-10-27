# Skybreak (开天) — macOS 26 on hardware Apple never supported

**Arrow Lake + Ampere, dual-boot with Windows 11, and every step is reproducible.**

> 中文版：[README.md](README.md) · 中文执行手册：[docs/quickstart-zh.md](docs/quickstart-zh.md)

| | |
|---|---|
| **Platform** | Intel Core Ultra 5 245K (Arrow Lake-S) · Gigabyte B860M POWER · NVIDIA RTX 3070 8GB |
| **Result** | **macOS 26.7.1 (25G241)** installed, boots to desktop, **RTX 3070 renders with Metal acceleration**, dual-boots with Windows 11 25H2 |
| **Data** | 100 GB+ preserved (verified backup before touching any disk) |
| **Cost** | 4 days of debugging, distilled into 5 decisive changes |

This is not a tutorial. It is the after-action file of one machine: what broke, what the log actually said, what fixed it, and how to confirm the fix — plus scripts that **refuse to write an installation stick that fails its own 30-point check**.

---

## The 5 changes that actually matter

Everything else is detail. Skip any one of these and you stop somewhere else.

| # | Change | What happens without it |
|---|---|---|
| 1 | BIOS **VT-d / IOMMU = Disabled** | Kernel handoff dies silently → screen shows `EB|LOG:EXITBS:START` and nothing else |
| 2 | BIOS **Hyper-Threading = Disabled**, **Active E-Cores = 0** | Hybrid-core topology never passes the handoff |
| 3 | `Booter → Quirks → **DevirtualiseMmio = True**` | 1401 ships `False` for this platform — **the direction is inverted**. This single assumption cost us the most time |
| 4 | Two **`Remove non-monotonic time panic`** kernel patches, **`Count = 2`** | Non-monotonic TSC freezes early boot and **disguises itself as a hang at `[AHCI][HBA] start:`** — which makes everyone think SATA is incompatible. It is not: B860 SATA works fine once the patches are in |
| 5 | `csr-active-config = **FF0F0000**` + enable **AMFIPass** | SIP missing `CSR_ALLOW_TASK_FOR_PID (0x04)` → `setuid/task_for_pid: Operation not permitted`, `code signature page shift: 14`, system services fail in bulk, desktop never appears |

Patch 4 is the one nobody documents. 1401 does not ship it; we took it from another Arrow Lake-HX success case (see [Credits](#credits)).

---

## Symptom → cause → fix

If you are here because your boot hangs, find your line:

| What you see | Real cause | Fix |
|---|---|---|
| Nothing at all after kernel handoff | `debug=0x100` swallows errors, or stale NVRAM `boot-args` overrides your config | Drop `debug=0x100`; add `boot-args` to `NVRAM → Delete` |
| Hang at `EB|LOG:EXITBS:START` | VT-d on / hybrid cores / `DevirtualiseMmio` wrong direction | Changes 1, 2, 3 above |
| Hang at `[AHCI][HBA] start:` | **Not** SATA incompatibility — missing clock patches | Change 4 above |
| Boots to userspace, then `task_for_pid: Operation not permitted` / `code signature page shift: 14` | SIP too strict; AMFIPass disabled | Change 5 above |
| OpenCore menu shows only `Reset NVRAM` | `ScanPolicy` bitmask wrong — it filtered APFS too | `ScanPolicy = 17760515` or `0` |
| Always boots Windows instead of OpenCore | Fast Startup bypasses firmware boot order | `powercfg /h off` + `HiberbootEnabled=0`, then re-set `bcdedit /set {fwbootmgr} bootsequence {USB-GUID}` |
| Installer says "the disk is locked" | You selected a partition, not the whole disk; NTFS is read-only in macOS | Disk Utility → Show All Devices → select the **whole disk** → erase as APFS / GUID |
| Clock off by hours in dual boot | macOS writes RTC as UTC, Windows reads local time | `RealTimeIsUniversal=1` + `w32tm /resync` |

Full 20-symptom encyclopedia: [`docs/boot-hang-diagnosis.md`](docs/boot-hang-diagnosis.md) (Chinese, tables are readable without it).

---

## Quick start

### Path A — let an agent drive (skill-aware assistants)

```
开天，帮我装 macOS 26
```

`SKILL.md` is a spec-compliant skill: 22 trigger phrases, 16-step SOP, 10 diagnostics with verification commands, 18 prohibitions. Or hand [`docs/runbook-zh.md`](docs/runbook-zh.md) to any model as an attachment — it is a self-contained cold-start manual.

### Path B — one command builds the installer (Windows)

```powershell
# dry run first: scan, generate EFI, apply proven config, 30-point check. Touches no disk.
powershell -ExecutionPolicy Bypass -File scripts\install-macos26.ps1 -DryRun

# then write, guarded by the stick's physical serial number
powershell -ExecutionPolicy Bypass -File scripts\install-macos26.ps1 -Serial <YOUR_USB_SERIAL>
```

It handles: proxy/TUN/Apple-TLS preflight → locate or download 1401 → locate or download the NVIDIA driver → reuse a previously verified EFI (or build one) → apply the proven config → 30-point check (**aborts on any FAIL**) → pick the disk by serial → call `p1401.usbwriter` → drop the one-click driver installer on the stick.

**What no tool can do** (no API exists): the 9 BIOS settings, the installer's erase/click sequence, and the first-boot wizard. So "one command" here means *one command to a fully usable installation stick* — not "one command to a working desktop".

> **Verification status (2026-10-24)**: OS install, desktop boot, service stability, dual-boot and **GPU rendering with Metal** are confirmed on the reference machine. Audio (ALC897), Bluetooth, sleep/wake and hot-plug are still unverified — see [`_VERIFICATION-LOG.md`](_VERIFICATION-LOG.md).

### macOS side

```bash
# inside macOS, from the stick
cd /Volumes/<STICK>/NullMoth
tar -xzf nullmoth-nvidia-<ver>.tar.gz -C /tmp && cd /tmp/pkgroot
shasum -a 256 -c SHA256SUMS && sudo ./install.sh
# reboot, allow the system extension, reboot again, then verify:
kmutil showloaded --list-only | grep nullmoth      # expect 4 lines
system_profiler SPDisplaysDataType | head -20      # expect Metal: Supported
```

---

## What this repo will not do

- **It will not hand you a "supported" badge.** The vendor's own device table still lists Ampere as `Pending` — they ran no automated validation. This build was confirmed on real hardware on 2026-10-24: macOS reaches the desktop and the RTX 3070 renders with Metal acceleration. Raw command output is not archived, so re-run the two commands under *macOS side* before quoting specific fields.
- **It will not ship an EFI.** EFI carries SMBIOS identity — per-machine, private. Generate your own with 1401.
- **It will not ship the driver.** That lives at [nullmoth/nvidia-macos-driver](https://github.com/nullmoth/nvidia-macos-driver) under **PolyForm Noncommercial 1.0.0** (commercial use not permitted).

---

## Compatibility, briefly

| Platform | Status |
|---|---|
| Arrow Lake-S (225/235/245K/265K/285K) + B860/Z890 | This exact playbook applies |
| Intel 12–14th gen (hybrid) | Same approach; CPUID spoof and SMBIOS must be recomputed |
| Intel 8–11th gen | Do **not** disable HT/E-cores; clock patches unneeded — the easy tier |
| AMD Ryzen 1000–5000 / 7000–9000 | Different patch set; values here do not transfer |
| NVIDIA Turing → Blackwell | In the driver's device table; **only RTX 5060 is physically validated** |
| Pascal and older / Intel Arc / AMD RX 7000+ | Out of driver scope; basic display only |
| Laptops (Arrow Lake-H/HX) | A success case exists, but expect MUX/Optimus/I2C-touchpad work |

Detail: [`docs/hardware-matrix.md`](docs/hardware-matrix.md) — every row carries `[measured] / [vendor] / [community]` and a risk grade.

---

## Why trust this

Read the three artifacts, not the README:

1. Every check in `scripts/inspect-config.py` derives from `_FACTS.md` §2 — no values invented inside the script.
2. `docs/case-arrow-lake-245k.md` rebuilds the timeline from 26 config backups' timestamps and raw boot-log text.
3. `_FACTS.md` §7 is a **post-completion audit that corrects our own earlier claims** — including one where we wrote "Metal verified" before collecting the output, and our own QA caught it.

---

## Credits

- [nullmoth/1401](https://github.com/nullmoth/1401) — Windows→macOS installer toolchain (hardware scan, EFI generation, USB writing)
- [nullmoth/nvidia-macos-driver](https://github.com/nullmoth/nvidia-macos-driver) — NVIDIA driver for Turing and later (PolyForm Noncommercial)
- [Coolzhy/EFI-OMEN16-am2xxx-public](https://github.com/Coolzhy/EFI-OMEN16-am2xxx-public) — same-generation CPU success case; source of the two clock patches
- [Acidanthera](https://github.com/acidanthera) — OpenCore, Lilu, VirtualSMC, WhateverGreen
- Everyone who filed "same hang at EXITBS" issues — your failure reports were data too

## License

Docs CC BY 4.0, code MIT. See [LICENSE](LICENSE). Driver and macOS licensing are separate.
