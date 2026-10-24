#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inspect-config.py -- OpenCore config.plist 体检工具（Arrow Lake + macOS 26 + NVIDIA 基准）

用法:
    python inspect-config.py <config.plist>            # 人读体检表 + 结论
    python inspect-config.py <config.plist> --json     # 机器可读（全部字段）
    python inspect-config.py --self-test               # 内置自检（不读外部文件）

判定口径: 全部基准值来自 skill 目录 _FACTS.md 第二节「最终成功的配置」，不臆造。
退出码: 0 = 无 FAIL（可以有 WARN）；1 = 存在 FAIL；2 = 文件读不了/不是 plist。

只依赖 Python 标准库（plistlib/argparse/json/pathlib/datetime/unicodedata），
路径含中文/空格均可用（Windows 与 macOS 的 Python 3 都跑）。
"""

import argparse
import json
import os
import plistlib
import sys
import unicodedata
from datetime import datetime

# ---------------------------------------------------------------- 基准常量 --

# _FACTS.md 第二节：Kernel/Booter/UEFI 关键 quirk
BASELINE_QUIRKS = [
    # (分组, 键, 期望值, 说明, FAIL 时的修复提示)
    ("Kernel", "ProvideCurrentCpuInfo", True,
     "混合核心 CPU（Arrow Lake 6P+8E）必须开，否则内核起不来",
     "patch-config.py set-quirk Kernel:Quirks:ProvideCurrentCpuInfo true"),
    ("Kernel", "DisableIoMapper", True,
     "禁用 IOMapper（VT-d 已在 BIOS 关掉，这里必须同步）",
     "patch-config.py set-quirk Kernel:Quirks:DisableIoMapper true"),
    ("Kernel", "LapicKernelPanic", False,
     "关掉 LAPIC 超时内核恐慌",
     "patch-config.py set-quirk Kernel:Quirks:LapicKernelPanic false"),
    ("Booter", "DevirtualiseMmio", True,
     "1401 默认给 False，方向反了；这是过 EB|LOG:EXITBS:START 的决定性项",
     "patch-config.py set-quirk Booter:Quirks:DevirtualiseMmio true"),
    ("Booter", "ResizeAppleGpuBars", None,  # 单独判定（0 / -1 都合法）
     "安装/无驱动阶段=0；装完驱动可用 -1",
     "patch-config.py apply-preset"),
    ("Booter", "SetupVirtualMap", True,
     "固件兼容的内存映射修复，必须开",
     "patch-config.py set-quirk Booter:Quirks:SetupVirtualMap true"),
    ("Booter", "RebuildAppleMemoryMap", True,
     "重建 Apple 内存映射",
     "patch-config.py set-quirk Booter:Quirks:RebuildAppleMemoryMap true"),
    ("Booter", "SyncRuntimePermissions", True,
     "同步运行时内存权限",
     "patch-config.py set-quirk Booter:Quirks:SyncRuntimePermissions true"),
    ("UEFI", "ResizeGpuBars", -1,
     "BIOS 已开 ReBAR 时 OC 不需要再改 BAR（驱动阶段是 13）",
     "patch-config.py set-quirk UEFI:Quirks:ResizeGpuBars -1"),
]

EXPECTED_CPUID = 0x000A0655        # Comet Lake 伪装签名（55 06 0A 00）
EXPECTED_CPUID_DATA = bytes.fromhex("55060a00")
EXPECTED_CSR = 0x0FFF              # csr-active-config = FF0F0000
BAD_CSR = 0x0A43                   # 实战踩过的坑值：缺 CSR_ALLOW_TASK_FOR_PID(0x04)
EXPECTED_SCANPOLICY = 17760515     # 0x010F0103 官方默认
EXPECTED_SMBIOS = "MacPro7,1"
EXPECTED_SECUREBOOTMODEL = "Disabled"

POST_DRIVER_BOOT_ARGS = (
    "keepsyms=1 revpatch=sbvmm nvfb=1 nvaccel=1 nvfbheads=1 -nvkmsnosmooth "
    "amfi_get_out_of_my_way=0x1 amfi=0x80 ipc_control_port_options=0"
)
REQUIRED_BOOT_ARGS = ["keepsyms=1", "amfi_get_out_of_my_way=0x1", "amfi=0x80",
                      "ipc_control_port_options=0"]
DRIVER_BOOT_ARGS = ["nvfb=1", "nvaccel=1", "nvfbheads=1", "-nvkmsnosmooth"]

REQUIRED_KEXTS = [
    "Lilu.kext", "VirtualSMC.kext", "AMFIPass.kext", "AppleMCEReporterDisabler.kext",
    "RestrictEvents.kext", "SMCProcessor.kext", "SMCSuperIO.kext",
    "USBToolBox.kext", "UTBDefault.kext", "WhateverGreen.kext", "RTL812xLucy.kext",
]
# 第二个 Remove non-monotonic time panic 补丁的基准（覆盖 macOS 26.4+）
TIME_PATCH_BASELINE = [
    ("Visual",   "21.0.0", "25.3.99", "12.0-26.3"),
    ("laobamac", "25.4.0", "25.99.99", "26.4+"),
]

CSR_BITS = [
    (0x001, "CSR_ALLOW_UNTRUSTED_KEXTS"),
    (0x002, "CSR_ALLOW_UNRESTRICTED_FS"),
    (0x004, "CSR_ALLOW_TASK_FOR_PID"),
    (0x008, "CSR_ALLOW_KERNEL_DEBUGGER"),
    (0x010, "CSR_ALLOW_APPLE_INTERNAL"),
    (0x020, "CSR_ALLOW_UNRESTRICTED_DTRACE"),
    (0x040, "CSR_ALLOW_UNRESTRICTED_NVRAM"),
    (0x080, "CSR_ALLOW_DEVICE_CONFIGURATION"),
    (0x100, "CSR_ALLOW_ANY_RECOVERY_OS"),
    (0x200, "CSR_ALLOW_UNAPPROVED_KEXTS"),
    (0x400, "CSR_ALLOW_EXECUTABLE_POLICY_OVERRIDE"),
    (0x800, "CSR_ALLOW_UNAUTHENTICATED_ROOT"),
]

SCANPOLICY_BITS = [
    (0x00000001, "OC_SCAN_FILE_SYSTEM_LOCK"),
    (0x00000002, "OC_SCAN_DEVICE_LOCK"),
    (0x00000100, "ALLOW_FS_APFS"),
    (0x00000200, "ALLOW_FS_HFS"),
    (0x00000400, "ALLOW_FS_ESP"),
    (0x00000800, "ALLOW_FS_NTFS"),
    (0x00001000, "ALLOW_FS_EXT"),
    (0x00010000, "ALLOW_DEVICE_SATA"),
    (0x00020000, "ALLOW_DEVICE_SASEX"),
    (0x00040000, "ALLOW_DEVICE_NVME"),
    (0x00080000, "ALLOW_DEVICE_ATAPI"),
    (0x00100000, "ALLOW_DEVICE_USB"),
    (0x00200000, "ALLOW_DEVICE_FIREWIRE"),
    (0x00400000, "ALLOW_DEVICE_SDCARD"),
    (0x00800000, "ALLOW_DEVICE_PCI"),
    (0x01000000, "ALLOW_DEVICE_VIRTUAL"),
]

NVRAM_APPLE_BOOT = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
NVRAM_OC_OWN = "4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102"

PASS, FAIL, WARN, INFO = "PASS", "FAIL", "WARN", "INFO"
MARK = {PASS: "[PASS]", FAIL: "[FAIL]", WARN: "[WARN]", INFO: "[INFO]"}

# ---------------------------------------------------------------- 小工具 ----

CHECKS = []


def add_check(group, name, expected, actual, status, hint="", note=""):
    """登记一条体检项。status 只能是 PASS/FAIL/WARN/INFO。"""
    item = {
        "group": group,
        "name": name,
        "expected": expected,
        "actual": actual,
        "status": status,
        "hint": hint,
        "note": note,
    }
    CHECKS.append(item)
    return item


def getp(root, *path, default=None):
    cur = root
    for key in path:
        if isinstance(cur, dict):
            if key not in cur:
                return default
            cur = cur[key]
        elif isinstance(cur, list):
            try:
                cur = cur[int(key)]
            except (ValueError, IndexError):
                return default
        else:
            return default
    return cur


def disp_width(text):
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def cut(text, width):
    """按显示宽度截断，超长以 .. 结尾。"""
    text = str(text)
    if disp_width(text) <= width:
        return text
    out = ""
    used = 0
    for ch in text:
        w = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if used + w > width - 2:
            break
        out += ch
        used += w
    return out + ".."


def pad(text, width, align="left"):
    text = cut(text, width)
    space = " " * max(0, width - disp_width(text))
    return space + text if align == "right" else text + space


def hexs(value):
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex(" ").upper() if value else "(空)"
    return "非 data 类型: %s" % type(value).__name__


def hexcompact(value):
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex().upper()
    return "(无)"


def truth(value):
    if value is True:
        return "True"
    if value is False:
        return "False"
    if value is None:
        return "(缺失)"
    return str(value)


def as_bool(value):
    if isinstance(value, bool):
        return value
    return None


def csr_int(value):
    if isinstance(value, (bytes, bytearray)):
        return int.from_bytes(bytes(value)[:4].ljust(4, b"\x00"), "little")
    if isinstance(value, int):
        return value & 0xFFFFFFFF
    return None


def csr_flags(value):
    val = csr_int(value)
    if val is None:
        return [], None
    return [(bit, name) for bit, name in CSR_BITS if val & bit], val


def scanpolicy_flags(value):
    if not isinstance(value, int):
        try:
            value = int(value)
        except (TypeError, ValueError):
            return [], None
    return [(bit, name) for bit, name in SCANPOLICY_BITS if value & bit], value


def table(headers, rows, widths, aligns=None):
    """渲染固定宽度文本表（中文按双宽算，Windows 控制台也不会错位）。"""
    aligns = aligns or ["left"] * len(headers)
    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    lines = [sep,
             "| " + " | ".join(pad(h, w, a) for h, w, a in zip(headers, widths, aligns)) + " |",
             sep]
    for row in rows:
        lines.append("| " + " | ".join(pad(c, w, a) for c, w, a in zip(row, widths, aligns)) + " |")
    lines.append(sep)
    return "\n".join(lines)


def hr(title=""):
    if title:
        return "\n== %s %s" % (title, "=" * max(0, 62 - disp_width(title)))
    return "=" * 68


def tune_streams():
    """控制台是 UTF-8(65001) 就把 stdout/stderr 也切到 UTF-8，否则保持本地编码。

    Windows PowerShell 5.1 + 中文环境常见的半个乱码问题就出在这里：控制台是 65001
    而 Python 管道默认用 cp936。argparse 的 help 走的也是这条路径。
    """
    cp = None
    if os.name == "nt":
        try:
            import ctypes
            cp = ctypes.windll.kernel32.GetConsoleOutputCP()
        except Exception:
            cp = None
    try:
        for stream in (sys.stdout, sys.stderr):
            if cp == 65001:
                stream.reconfigure(encoding="utf-8", errors="replace")
            else:
                stream.reconfigure(errors="replace")
    except Exception:
        pass


def emit(text):
    """统一输出：控制台按控制台编码，重定向/管道一律 UTF-8（避免 GBK 半路截断）。

    这样 `inspect-config.py x.plist > out.txt` 在中文 Windows 上得到的就是 UTF-8 文本，
    PowerShell 里 `| Out-String` 也不会变成一堆问号。
    """
    data = text + "\n"
    stream = sys.stdout
    try:
        if stream.isatty():
            stream.write(data)
            stream.flush()
            return
    except Exception:
        pass
    buf = getattr(stream, "buffer", None)
    if buf is not None:
        try:
            buf.write(data.encode("utf-8"))
            buf.flush()
            return
        except Exception:
            pass
    stream.write(data)


def eprint(text):
    emit_to(sys.stderr, text)


def emit_to(stream, text):
    data = text + "\n"
    buf = getattr(stream, "buffer", None)
    try:
        if buf is not None:
            buf.write(data.encode("utf-8"))
            buf.flush()
            return
    except Exception:
        pass
    stream.write(data)


# ---------------------------------------------------------------- 解析部分 --

def load_config(path):
    p = os.path.abspath(path)
    with open(p, "rb") as fh:
        raw = fh.read()
    cfg = plistlib.loads(raw)
    if not isinstance(cfg, dict):
        raise ValueError("plist 根节点不是 dict，不像 OpenCore config.plist")
    return p, raw, cfg


def quirk_value(cfg, group, key):
    if group == "Kernel":
        return getp(cfg, "Kernel", "Quirks", key)
    if group == "Booter":
        return getp(cfg, "Booter", "Quirks", key)
    if group == "UEFI":
        return getp(cfg, "UEFI", "Quirks", key)
    return None


def acpi_delete(cfg):
    out = []
    for item in (getp(cfg, "ACPI", "Delete", default=[]) or []):
        sig = item.get("TableSignature")
        if isinstance(sig, (bytes, bytearray)):
            sig_text = bytes(sig).decode("ascii", "replace").strip("\x00")
        else:
            sig_text = "(非 data)"
        out.append({
            "sig": sig_text,
            "all": item.get("All"),
            "enabled": item.get("Enabled"),
            "oem_table_id": hexcompact(item.get("OemTableId")) if item.get("OemTableId") else "",
            "comment": item.get("Comment", ""),
        })
    return out


def acpi_add(cfg):
    out = []
    for item in (getp(cfg, "ACPI", "Add", default=[]) or []):
        out.append({"path": item.get("Path", ""), "enabled": item.get("Enabled")})
    return out


def kernel_blocks(cfg):
    out = []
    for item in (getp(cfg, "Kernel", "Block", default=[]) or []):
        out.append({
            "identifier": item.get("Identifier", ""),
            "strategy": item.get("Strategy", ""),
            "enabled": item.get("Enabled"),
            "arch": item.get("Arch", ""),
            "comment": item.get("Comment", ""),
        })
    return out


def kernel_patches(cfg):
    out = []
    for index, item in enumerate(getp(cfg, "Kernel", "Patch", default=[]) or []):
        out.append({
            "index": index,
            "comment": item.get("Comment", ""),
            "identifier": item.get("Identifier", ""),
            "enabled": item.get("Enabled"),
            "min_kernel": item.get("MinKernel", ""),
            "max_kernel": item.get("MaxKernel", ""),
            "count": item.get("Count"),
            "arch": item.get("Arch", ""),
            "find": hexcompact(item.get("Find")),
            "mask": hexcompact(item.get("Mask")),
            "replace": hexcompact(item.get("Replace")),
        })
    return out


def kexts(cfg):
    out = []
    for item in (getp(cfg, "Kernel", "Add", default=[]) or []):
        out.append({
            "bundle": item.get("BundlePath", ""),
            "enabled": item.get("Enabled"),
            "min_kernel": item.get("MinKernel", ""),
            "max_kernel": item.get("MaxKernel", ""),
            "executable": item.get("ExecutablePath", ""),
            "comment": item.get("Comment", ""),
        })
    return out


def boot_args(cfg):
    val = getp(cfg, "NVRAM", "Add", NVRAM_APPLE_BOOT, "boot-args")
    return val if isinstance(val, str) else None


def nvram_delete_names(cfg, guid):
    return list(getp(cfg, "NVRAM", "Delete", guid, default=[]) or [])


def collect(cfg):
    """一次性收集所有要展示/判定的字段（--json 直接复用）。"""
    quirks = {}
    for group, key, _exp, _desc, _hint in BASELINE_QUIRKS:
        quirks["%s:Quirks:%s" % (group, key)] = quirk_value(cfg, group, key)

    emu = getp(cfg, "Kernel", "Emulate", default={}) or {}
    cpu_data = emu.get("Cpuid1Data")
    cpu_mask = emu.get("Cpuid1Mask")
    cpuid_sig = None
    if isinstance(cpu_data, (bytes, bytearray)) and len(cpu_data) >= 4:
        cpuid_sig = int.from_bytes(bytes(cpu_data)[:4], "little")

    args = boot_args(cfg)
    tokens = args.split() if isinstance(args, str) else []
    csr_raw = getp(cfg, "NVRAM", "Add", NVRAM_APPLE_BOOT, "csr-active-config")
    csr_flag_list, csr_value = csr_flags(csr_raw)
    scanpolicy_raw = getp(cfg, "Misc", "Security", "ScanPolicy")
    sp_flag_list, sp_value = scanpolicy_flags(scanpolicy_raw)

    return {
        "quirks": quirks,
        "cpuid": {
            "data": hexcompact(cpu_data),
            "mask": hexcompact(cpu_mask),
            "signature": ("0x%08X" % cpuid_sig) if cpuid_sig is not None else None,
            "data_len": len(cpu_data) if isinstance(cpu_data, (bytes, bytearray)) else 0,
        },
        "acpi_delete": acpi_delete(cfg),
        "acpi_add": acpi_add(cfg),
        "kernel_block": kernel_blocks(cfg),
        "kernel_patch": kernel_patches(cfg),
        "kexts": kexts(cfg),
        "smbios": {
            "product": getp(cfg, "PlatformInfo", "Generic", "SystemProductName"),
            "serial": getp(cfg, "PlatformInfo", "Generic", "SystemSerialNumber"),
            "mlb": getp(cfg, "PlatformInfo", "Generic", "MLB"),
            "rom": hexcompact(getp(cfg, "PlatformInfo", "Generic", "ROM")),
            "processor_type": getp(cfg, "PlatformInfo", "Generic", "ProcessorType"),
            "automatic": getp(cfg, "PlatformInfo", "Automatic"),
            "update_smbios_mode": getp(cfg, "PlatformInfo", "UpdateSMBIOSMode"),
        },
        "security": {
            "secure_boot_model": getp(cfg, "Misc", "Security", "SecureBootModel"),
            "scan_policy": sp_value,
            "scan_policy_flags": [n for _b, n in sp_flag_list],
            "vault": getp(cfg, "Misc", "Security", "Vault"),
            "dmg_loading": getp(cfg, "Misc", "Security", "DmgLoading"),
            "blacklist_apple_update": getp(cfg, "Misc", "Security", "BlacklistAppleUpdate"),
        },
        "nvram": {
            "boot_args": args,
            "boot_args_tokens": tokens,
            "csr_raw": hexcompact(csr_raw),
            "csr_value": ("0x%04X" % csr_value) if csr_value is not None else None,
            "csr_flags": [n for _b, n in csr_flag_list],
            "delete_apple_boot": nvram_delete_names(cfg, NVRAM_APPLE_BOOT),
            "delete_oc_own": nvram_delete_names(cfg, NVRAM_OC_OWN),
            "has_boot_args_in_delete": "boot-args" in nvram_delete_names(cfg, NVRAM_APPLE_BOOT),
            "write_flash": getp(cfg, "NVRAM", "WriteFlash"),
        },
        "debug": {
            "target": getp(cfg, "Misc", "Debug", "Target"),
            "apple_debug": getp(cfg, "Misc", "Debug", "AppleDebug"),
            "apple_panic": getp(cfg, "Misc", "Debug", "ApplePanic"),
            "display_level": getp(cfg, "Misc", "Debug", "DisplayLevel"),
            "sys_report": getp(cfg, "Misc", "Debug", "SysReport"),
        },
        "boot": {
            "timeout": getp(cfg, "Misc", "Boot", "Timeout"),
            "hide_auxiliary": getp(cfg, "Misc", "Boot", "HideAuxiliary"),
            "picker_mode": getp(cfg, "Misc", "Boot", "PickerMode"),
        },
    }


# ---------------------------------------------------------------- 判定部分 --

def run_checks(facts, cfg):
    del CHECKS[:]

    # 1-9 quirk 逐项
    for group, key, expected, desc, hint in BASELINE_QUIRKS:
        actual = facts["quirks"]["%s:Quirks:%s" % (group, key)]
        label = "%s->Quirks->%s" % (group, key)
        if (group, key) == ("UEFI", "ResizeGpuBars"):
            # 安装阶段基准 -1（BIOS 已开 ReBAR 时 OC 不用改）；驱动阶段需要 13（8GB BAR）
            if actual == -1:
                add_check("Quirks", label, "-1（安装阶段）或 13（驱动 8GB BAR）", actual, PASS,
                          note="BIOS 已开 Re-Size BAR，OC 不再改 BAR")
            elif actual == 13:
                add_check("Quirks", label, "-1（安装阶段）或 13（驱动 8GB BAR）", actual, PASS,
                          note="驱动阶段的 8GB BAR 取值")
            elif actual is None:
                add_check("Quirks", label, "-1（安装阶段）或 13（驱动 8GB BAR）", "(缺失)", WARN,
                          hint="patch-config.py set-quirk UEFI:Quirks:ResizeGpuBars -1")
            else:
                add_check("Quirks", label, "-1（安装阶段）或 13（驱动 8GB BAR）", repr(actual), WARN,
                          hint="patch-config.py set-quirk UEFI:Quirks:ResizeGpuBars -1",
                          note="不是 -1 也不是 13，确认是否有意为之")
            continue
        if key == "ResizeAppleGpuBars":
            if actual == 0:
                add_check("Quirks", label, "0（安装/无驱动）或 -1（已装驱动）", actual, PASS,
                          note="安装阶段 0；装完 NVIDIA 驱动可改 -1", )
            elif actual == -1:
                add_check("Quirks", label, "0（安装/无驱动）或 -1（已装驱动）", actual, PASS,
                          note="已是驱动阶段取值 -1")
            else:
                add_check("Quirks", label, "0（安装/无驱动）或 -1（已装驱动）", repr(actual), FAIL,
                          hint="patch-config.py apply-preset --stage install")
            continue
        if actual is None:
            add_check("Quirks", label, truth(expected), "(缺失)", FAIL, hint=hint, note=desc)
        elif isinstance(expected, bool) and as_bool(actual) is expected:
            add_check("Quirks", label, truth(expected), truth(actual), PASS, note=desc)
        elif isinstance(expected, int) and not isinstance(expected, bool) \
                and isinstance(actual, int) and not isinstance(actual, bool) and actual == expected:
            add_check("Quirks", label, truth(expected), truth(actual), PASS, note=desc)
        else:
            add_check("Quirks", label, truth(expected), truth(actual), FAIL, hint=hint, note=desc)

    # 10 内核补丁：两条 Remove non-monotonic time panic 必须在且启用
    patches = facts["kernel_patch"]
    for author, min_k, max_k, cover in TIME_PATCH_BASELINE:
        label = "Kernel->Patch[%s][%s]" % (author, cover)
        hit = None
        for item in patches:
            c = (item.get("comment") or "").lower()
            if author.lower() in c and "non-monotonic" in c:
                hit = item
                break
        if hit is None:
            add_check("KernelPatch", label, "Enabled=True，覆盖 %s" % cover, "(未找到)", FAIL,
                      hint="patch-config.py apply-preset（会补齐两条时钟补丁）",
                      note="缺它会在 [AHCI][HBA] start: 附近冻死（时钟非单调，不是 SATA 问题）")
        elif not hit.get("enabled"):
            add_check("KernelPatch", label, "Enabled=True", "Enabled=False", FAIL,
                      hint="patch-config.py apply-preset",
                      note="补丁存在但被关掉了，等于没有")
        elif hit.get("identifier") not in (None, "kernel"):
            add_check("KernelPatch", label, "Identifier=kernel", repr(hit.get("identifier")), FAIL,
                      hint="patch-config.py apply-preset")
        else:
            note = "Cover=%s Count=%s %s..%s" % (hit.get("count"), hit.get("count"),
                                                 hit.get("min_kernel"), hit.get("max_kernel"))
            status = PASS
            note2 = ""
            if hit.get("min_kernel") != min_k and hit.get("max_kernel") != max_k:
                status = WARN
                note2 = "内核区间与基准不同（基准 MinKernel=%s MaxKernel=%s）" % (min_k, max_k)
            add_check("KernelPatch", label, "Enabled=True，覆盖 %s" % cover,
                      "Enabled=True", status, note=note + ("；" + note2 if note2 else ""))

    # 11 ACPI Delete DMAR
    dmar = [d for d in facts["acpi_delete"] if d["sig"] == "DMAR"]
    if not dmar:
        add_check("ACPI", "ACPI->Delete DMAR", "存在且 All=True Enabled=True", "(未找到)", FAIL,
                  hint="patch-config.py apply-preset")
    else:
        bad = [d for d in dmar if not (d["all"] and d["enabled"])]
        if bad:
            add_check("ACPI", "ACPI->Delete DMAR", "All=True Enabled=True",
                      "All=%s Enabled=%s" % (bad[0]["all"], bad[0]["enabled"]), FAIL,
                      hint="patch-config.py apply-preset",
                      note="BIOS 已关 VT-d 时这也应保留，避免 OCA 报 OCA: Deleting table DMAR")
        else:
            add_check("ACPI", "ACPI->Delete DMAR", "All=True Enabled=True", "All=True Enabled=True", PASS)

    # 12 CPU 伪装
    cpuid = facts["cpuid"]
    if cpuid["signature"] == "0x%08X" % EXPECTED_CPUID:
        add_check("CPU", "Kernel->Emulate->Cpuid1Data", "55 06 0A 00（0x000A0655）",
                  cpuid["data"][:11] + "...", PASS, note="Comet Lake 伪装")
    elif cpuid["signature"] is None:
        add_check("CPU", "Kernel->Emulate->Cpuid1Data", "55 06 0A 00（0x000A0655）", "(缺失/非 data)",
                  FAIL, hint="patch-config.py apply-preset")
    else:
        add_check("CPU", "Kernel->Emulate->Cpuid1Data", "55 06 0A 00（0x000A0655）",
                  cpuid["signature"], WARN, hint="patch-config.py apply-preset",
                  note="有伪装但签名不是基准值，确认是否照抄成功案例")
    mask = cpuid["mask"]
    if mask.startswith("FFFFFFFF"):
        add_check("CPU", "Kernel->Emulate->Cpuid1Mask", "FF FF FF FF ...", mask[:11] + "...", PASS)
    elif mask == "(无)":
        add_check("CPU", "Kernel->Emulate->Cpuid1Mask", "FF FF FF FF ...", "(缺失)", FAIL,
                  hint="patch-config.py apply-preset")
    else:
        add_check("CPU", "Kernel->Emulate->Cpuid1Mask", "FF FF FF FF ...", mask[:11] + "...", WARN,
                  note="掩码前 4 字节不是全 FF，伪装可能只部分生效")

    # 13 CpuTopologyRebuild 必须关（Arrow Lake）
    ctr = [k for k in facts["kexts"] if "CpuTopologyRebuild" in k["bundle"]]
    if not ctr:
        add_check("CPU", "CpuTopologyRebuild.kext", "不存在或 Enabled=False", "未加载（条目不存在）", PASS)
    elif ctr[0]["enabled"]:
        add_check("CPU", "CpuTopologyRebuild.kext", "不存在或 Enabled=False", "Enabled=True", FAIL,
                  hint="patch-config.py set-quirk Kernel:Add:<idx>:Enabled false（或用 GUI 关掉）",
                  note="Arrow Lake 混合核心必须关，否则拓扑重建会崩")
    else:
        add_check("CPU", "CpuTopologyRebuild.kext", "不存在或 Enabled=False", "Enabled=False", PASS)

    # 14 csr-active-config
    nv = facts["nvram"]
    if nv["csr_value"] is None:
        add_check("Security", "NVRAM->csr-active-config", "FF0F0000（0x0FFF 全关 SIP）", "(缺失)", FAIL,
                  hint="patch-config.py set-csr 0x0FFF")
    elif nv["csr_value"] == "0x0FFF":
        add_check("Security", "NVRAM->csr-active-config", "FF0F0000（0x0FFF 全关 SIP）",
                  "%s（0x0FFF）" % nv["csr_raw"], PASS, note="12 个 CSR 位全开")
    elif nv["csr_value"] == "0x%04X" % BAD_CSR:
        add_check("Security", "NVRAM->csr-active-config", "FF0F0000（0x0FFF 全关 SIP）",
                  "%s（0x0A43）" % nv["csr_raw"], FAIL, hint="patch-config.py set-csr 0x0FFF",
                  note="0x0A43 缺 CSR_ALLOW_TASK_FOR_PID(0x04)：所有系统服务 setuid/task_for_pid 会 EPERM")
    else:
        add_check("Security", "NVRAM->csr-active-config", "FF0F0000（0x0FFF 全关 SIP）",
                  "%s（%s）" % (nv["csr_raw"], nv["csr_value"]), WARN,
                  hint="patch-config.py set-csr 0x0FFF")

    # 15 SecureBootModel
    sbm = facts["security"]["secure_boot_model"]
    if sbm == EXPECTED_SECUREBOOTMODEL:
        add_check("Security", "Misc->Security->SecureBootModel", EXPECTED_SECUREBOOTMODEL, sbm, PASS)
    else:
        add_check("Security", "Misc->Security->SecureBootModel", EXPECTED_SECUREBOOTMODEL, repr(sbm), FAIL,
                  hint="patch-config.py apply-preset")

    # 16 ScanPolicy
    sp = facts["security"]["scan_policy"]
    device_bits = 0x00FF0000  # SATA..VIRTUAL 全部设备类别位
    if sp == EXPECTED_SCANPOLICY or sp == 0:
        add_check("Security", "Misc->Security->ScanPolicy", "17760515（0x010F0103）或 0",
                  "%d（0x%08X）" % (sp, sp), PASS,
                  note="含 APFS 与 SATA/SASEX/NVMe/ATAPI 的官方默认" if sp else "0 = 不过滤")
    elif sp is None:
        add_check("Security", "Misc->Security->ScanPolicy", "17760515（0x010F0103）或 0",
                  "(缺失)", WARN, hint="patch-config.py apply-preset")
    else:
        note = "已解码: " + (", ".join(facts["security"]["scan_policy_flags"]) or "(无位)")
        if not (sp & device_bits):
            status = FAIL
            note += "；没有任何设备类别位（SATA/NVMe/USB 全被过滤），会只剩 Reset NVRAM"
        elif not (sp & 0x00100000):
            status = WARN
            note += "；没有 ALLOW_DEVICE_USB(0x00100000)：从 U 盘装的阶段可能看不到安装盘"
        elif not (sp & 0x00000100):
            status = FAIL
            note += "；没有 ALLOW_FS_APFS，看不到 macOS 卷"
        else:
            status = WARN
        add_check("Security", "Misc->Security->ScanPolicy", "17760515（0x010F0103）或 0",
                  "%d（0x%08X）" % (sp, sp), status,
                  hint="patch-config.py apply-preset", note=note)

    # 17 SMBIOS
    product = facts["smbios"]["product"]
    if product == EXPECTED_SMBIOS:
        add_check("SMBIOS", "PlatformInfo->Generic->SystemProductName", EXPECTED_SMBIOS, product, PASS)
    elif not product:
        add_check("SMBIOS", "PlatformInfo->Generic->SystemProductName", EXPECTED_SMBIOS, "(缺失)", FAIL,
                  hint="patch-config.py apply-preset")
    else:
        add_check("SMBIOS", "PlatformInfo->Generic->SystemProductName", EXPECTED_SMBIOS, product, WARN,
                  note="不是基准机型；macOS 15 与 26 都接受 MacPro7,1")

    # 18 必备 kexts
    enabled = {}
    present = {}
    for item in facts["kexts"]:
        bundle = item["bundle"]
        present[bundle] = item
        if item["enabled"]:
            enabled[bundle] = item
    missing = [k for k in REQUIRED_KEXTS if k not in present]
    disabled = [k for k in REQUIRED_KEXTS if k in present and not present[k]["enabled"]]
    if not missing and not disabled:
        add_check("Kexts", "必备 kext 清单（%d 个）" % len(REQUIRED_KEXTS), "全部存在且启用",
                  "全部存在且启用", PASS)
    else:
        detail = []
        if missing:
            detail.append("缺失: " + ", ".join(missing))
        if disabled:
            detail.append("被禁用: " + ", ".join(disabled))
        add_check("Kexts", "必备 kext 清单（%d 个）" % len(REQUIRED_KEXTS), "全部存在且启用",
                  "；".join(detail), FAIL,
                  hint="把对应 kext 放进 EFI/OC/Kexts 并 Enabled=True（AMFIPass 缺了系统服务全挂）")
    if present.get("AMFIPass.kext") and present["AMFIPass.kext"]["enabled"]:
        add_check("Kexts", "AMFIPass.kext（缺它系统服务全挂）", "Enabled=True", "Enabled=True", PASS)
    else:
        add_check("Kexts", "AMFIPass.kext（缺它系统服务全挂）", "Enabled=True",
                  "缺失或禁用", FAIL, hint="启用 AMFIPass.kext")

    # 19 boot-args
    tokens = nv["boot_args_tokens"]
    if nv["boot_args"] is None:
        add_check("boot-args", "NVRAM->boot-args", "非空", "(缺失)", WARN,
                  hint="patch-config.py set-boot-args --stage install")
    else:
        if "debug=0x100" in tokens:
            add_check("boot-args", "禁止 debug=0x100", "不含 debug=0x100", "含有",
                      FAIL, hint="patch-config.py set-boot-args --remove debug=0x100",
                      note="它把内核错误静默进调试器，表现为『屏幕定格零输出』")
        else:
            add_check("boot-args", "禁止 debug=0x100", "不含 debug=0x100", "不含", PASS)

        driver_stage = any(t in tokens for t in ("nvfb=1", "nvaccel=1")) or any(
            b.get("identifier") == "com.apple.iokit.IONDRVSupport"
            for b in facts["kernel_block"])
        stage_text = "驱动阶段" if driver_stage else "安装阶段"
        lost = [t for t in REQUIRED_BOOT_ARGS if t not in tokens]
        if not lost:
            add_check("boot-args", "AMFI/keepsyms 相关必需参数", " ".join(REQUIRED_BOOT_ARGS),
                      "齐全", PASS)
        elif driver_stage:
            add_check("boot-args", "AMFI/keepsyms 相关必需参数", " ".join(REQUIRED_BOOT_ARGS),
                      "%s 缺: %s" % (stage_text, " ".join(lost)), FAIL,
                      hint="patch-config.py set-boot-args --stage driver",
                      note="驱动阶段必须关 AMFI，否则系统服务 setuid/task_for_pid 全 EPERM、"
                           "code signature page shift / malformed Mach-O")
        else:
            add_check("boot-args", "AMFI/keepsyms 相关必需参数", " ".join(REQUIRED_BOOT_ARGS),
                      "%s 缺: %s" % (stage_text, " ".join(lost)), WARN,
                      hint="patch-config.py set-boot-args --stage driver",
                      note="安装阶段可以只有 -v keepsyms=1；装驱动后必须补齐 4 个 AMFI 参数")

        lost_nv = [t for t in DRIVER_BOOT_ARGS if t not in tokens]
        if lost_nv:
            add_check("boot-args", "NVIDIA 驱动参数", " ".join(DRIVER_BOOT_ARGS),
                      "缺: " + " ".join(lost_nv), WARN,
                      note="没装驱动前缺这些是正常的；装完驱动由 1401 Mac app 或 patch-config.py 补上")
        else:
            add_check("boot-args", "NVIDIA 驱动参数", " ".join(DRIVER_BOOT_ARGS), "齐全", PASS)

        if "-v" in tokens:
            add_check("boot-args", "详细日志 -v", "安装/诊断阶段建议有", "有 -v", PASS)
        else:
            add_check("boot-args", "详细日志 -v", "安装/诊断阶段建议有", "没有 -v", WARN,
                      hint="patch-config.py set-boot-args --append -v",
                      note="静默画面是黑盒；安装与排错阶段必须开详细日志")

    # 20 NVRAM Delete 必须含 boot-args
    if nv["has_boot_args_in_delete"]:
        add_check("NVRAM", "NVRAM->Delete[7C436110]->boot-args", "包含 boot-args", "包含", PASS,
                  note="否则 NVRAM 旧值会盖住 config 里的新值（日志: Setting NVRAM ... - ignored, exists）")
    else:
        add_check("NVRAM", "NVRAM->Delete[7C436110]->boot-args", "包含 boot-args", "不包含", FAIL,
                  hint="命令行里给 7C436110 的 Delete 数组补 boot-args；或 apply-preset",
                  note="每次改 boot-args 都不生效的头号原因")

    # 21 调试日志（opencore-*.txt 是诊断金矿）
    target = facts["debug"]["target"]
    if isinstance(target, int) and (target & 0x40):
        add_check("Debug", "Misc->Debug->Target 文件日志位(0x40)", "含 0x40，Target=%d" % target,
                  "含 0x40", PASS)
    elif target == 0:
        add_check("Debug", "Misc->Debug->Target 文件日志位(0x40)", "含 0x40", "Target=0（不写日志）", WARN,
                  note="U 盘上就没有 opencore-*.txt，出问题只能盲猜")
    else:
        add_check("Debug", "Misc->Debug->Target 文件日志位(0x40)", "含 0x40",
                  "Target=%r（缺 0x40）" % (target,), WARN,
                  note="打开文件日志才能在 U 盘根目录拿到 opencore-*.txt")

    if facts["debug"]["apple_debug"] is True and facts["debug"]["apple_panic"] is True:
        add_check("Debug", "Misc->Debug->AppleDebug/ApplePanic", "都为 True", "都为 True", PASS)
    else:
        add_check("Debug", "Misc->Debug->AppleDebug/ApplePanic", "都为 True",
                  "AppleDebug=%s ApplePanic=%s" % (facts["debug"]["apple_debug"],
                                                   facts["debug"]["apple_panic"]), WARN,
                  note="内核 panic 日志要留在系统盘上，排错时是第一手证据")

    # 22 Vault
    vault = facts["security"]["vault"]
    if vault in (None, "Optional"):
        add_check("Security", "Misc->Security->Vault", "Optional", truth(vault), PASS)
    else:
        add_check("Security", "Misc->Security->Vault", "Optional", truth(vault), WARN,
                  note="开了 Vault 后每次改 config 都要重新签名，实战阶段别开")


def summarize():
    counts = {PASS: 0, FAIL: 0, WARN: 0, INFO: 0}
    for item in CHECKS:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return counts


# ---------------------------------------------------------------- 渲染部分 --

def render_text(path, raw, cfg, facts):
    out = []
    stamp = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S")
    out.append(hr("OpenCore config.plist 体检"))
    out.append("文件      : %s" % path)
    out.append("大小/时间 : %d 字节 / %s" % (len(raw), stamp))
    out.append("根节点    : %s" % ", ".join(cfg.keys()))
    out.append("判定基准  : _FACTS.md 第二节（Arrow Lake + macOS 26 + NVIDIA 成功组合）")

    # 文件格式合法性
    if raw.startswith(b"bplist"):
        add_check("Format", "文件格式", "XML plist", "binary plist（bplist00）", WARN,
                  hint="OpenCore 也认，但人工编辑/对比都不方便",
                  note="OC 官方示例与 1401 产出的都是 XML，社区排错工具默认按 XML 处理")
    elif b"<plist" in raw[:1024]:
        add_check("Format", "文件格式", "XML plist", "XML plist", PASS)
    else:
        add_check("Format", "文件格式", "XML plist", "无法识别", WARN)

    # --- 关键 quirks 表
    out.append(hr("CPU / GPU 相关 Quirks"))
    rows = []
    for group, key, expected, _desc, _hint in BASELINE_QUIRKS:
        label = "%s:Quirks:%s" % (group, key)
        actual = facts["quirks"][label]
        item = None
        for check in CHECKS:
            if check["name"] == "%s->Quirks->%s" % (group, key):
                item = check
                break
        exp_text = "0 或 -1" if expected is None else truth(expected)
        rows.append([label, exp_text, truth(actual), MARK[item["status"]] if item else "?"])
    out.append(table(["项", "基准", "实际", "判定"], rows, [30, 14, 12, 8],
                     ["left", "left", "left", "left"]))

    # --- CPU 伪装
    out.append(hr("CPU 伪装"))
    cpuid = facts["cpuid"]
    out.append("Cpuid1Data : %s" % cpuid["data"])
    out.append("Cpuid1Mask : %s" % cpuid["mask"])
    if cpuid["signature"]:
        out.append("签名解码   : %s  （基准 0x000A0655 = Comet Lake 伪装）" % cpuid["signature"])
    else:
        out.append("签名解码   : 无（Cpuid1Data 缺失或不是 <data>）")

    # --- ACPI
    out.append(hr("ACPI"))
    if facts["acpi_delete"]:
        rows = [[d["sig"], truth(d["all"]), truth(d["enabled"]),
                 d["oem_table_id"] or "-", cut(d["comment"], 34)] for d in facts["acpi_delete"]]
        out.append("Delete 列表:")
        out.append(table(["签名", "All", "Enabled", "OemTableId", "Comment"],
                         rows, [8, 7, 8, 18, 34]))
    else:
        out.append("Delete 列表: (空)  <- 基准要求有一条 DMAR All=True Enabled=True")
    adds = facts["acpi_add"]
    if adds:
        out.append("Add 列表: " + ", ".join(
            "%s%s" % (a["path"], "" if a["enabled"] else "(禁用)") for a in adds))
    else:
        out.append("Add 列表: (空)")

    # --- Kernel Block / Patch
    out.append(hr("Kernel Block / Patch"))
    if facts["kernel_block"]:
        rows = [[cut(b["identifier"], 34), b["strategy"] or "-", truth(b["enabled"]),
                 b["arch"] or "-", cut(b["comment"], 26)] for b in facts["kernel_block"]]
        out.append(table(["Identifier", "Strategy", "Enabled", "Arch", "Comment"],
                         rows, [34, 8, 8, 7, 26]))
    else:
        out.append("Block: (空)  <- 没屏蔽任何内核扩展；装 NVIDIA 驱动前需要屏蔽 IONDRVSupport")
    if facts["kernel_patch"]:
        rows = []
        for item in facts["kernel_patch"]:
            rows.append([str(item["index"]), truth(item["enabled"]),
                         item["identifier"] or "-",
                         "%s..%s" % (item["min_kernel"] or "-", item["max_kernel"] or "-"),
                         str(item["count"]), cut(item["comment"], 40)])
        out.append(table(["#", "Enabled", "Identifier", "Min..Max", "Count", "Comment"],
                         rows, [2, 8, 10, 16, 6, 40]))
    else:
        out.append("Patch: (空)  <- 基准要求两条 Remove non-monotonic time panic 补丁")

    # --- kexts
    out.append(hr("Kexts"))
    rows = []
    for item in facts["kexts"]:
        flag = "" if item["bundle"] in REQUIRED_KEXTS else " (非基准必需)"
        rows.append([cut(item["bundle"] + flag, 44), truth(item["enabled"]),
                     "%s..%s" % (item["min_kernel"] or "-", item["max_kernel"] or "-")])
    out.append(table(["BundlePath", "Enabled", "Min..Max"], rows, [44, 8, 14]))
    on = [k["bundle"] for k in facts["kexts"] if k["enabled"]]
    out.append("启用 %d / 共 %d；必备清单命中 %d/%d" % (
        len(on), len(facts["kexts"]),
        len([k for k in on if k in REQUIRED_KEXTS]), len(REQUIRED_KEXTS)))

    # --- SMBIOS / Security
    out.append(hr("SMBIOS / Security"))
    sm = facts["smbios"]
    sec = facts["security"]
    rows = [
        ["SystemProductName", EXPECTED_SMBIOS, truth(sm["product"])],
        ["SystemSerialNumber", "(任意但不与他人重复)", truth(sm["serial"])],
        ["MLB", "(板序列号)", truth(sm["mlb"])],
        ["ROM", "(网卡 MAC 6 字节)", sm["rom"]],
        ["ProcessorType", "1537（未指定）", truth(sm["processor_type"])],
        ["SecureBootModel", EXPECTED_SECUREBOOTMODEL, truth(sec["secure_boot_model"])],
        ["ScanPolicy", "17760515 / 0", "%s（0x%08X）" % (sec["scan_policy"], sec["scan_policy"] or 0)],
        ["Vault", "Optional", truth(sec["vault"])],
        ["DmgLoading", "Signed", truth(sec["dmg_loading"])],
    ]
    out.append(table(["项", "基准", "实际"], rows, [22, 26, 30]))
    if sec["scan_policy_flags"]:
        out.append("ScanPolicy 已置位: " + ", ".join(sec["scan_policy_flags"]))

    # --- NVRAM
    out.append(hr("NVRAM"))
    out.append("boot-args   : %s" % (facts["nvram"]["boot_args"] or "(缺失)"))
    out.append("csr-active  : %s  = %s" % (facts["nvram"]["csr_raw"], facts["nvram"]["csr_value"]))
    if facts["nvram"]["csr_flags"]:
        out.append("  SIP 已开位: " + ", ".join(facts["nvram"]["csr_flags"]))
    out.append("Delete[7C436110] : %s" % (", ".join(facts["nvram"]["delete_apple_boot"]) or "(空)"))
    out.append("Delete[4D1FDA02] : %s" % (", ".join(facts["nvram"]["delete_oc_own"]) or "(空)"))
    out.append("含 boot-args     : %s  <- 决定 boot-args 能不能改生效"
               % ("是" if facts["nvram"]["has_boot_args_in_delete"] else "否（会被 NVRAM 旧值盖住）"))

    # --- Debug / Boot
    out.append(hr("Debug / Boot"))
    dbg = facts["debug"]
    boot = facts["boot"]
    out.append("Target=%r（0x40 文件日志=%s） AppleDebug=%s ApplePanic=%s DisplayLevel=%r"
               % (dbg["target"],
                  "有" if isinstance(dbg["target"], int) and dbg["target"] & 0x40 else "无",
                  dbg["apple_debug"], dbg["apple_panic"], dbg["display_level"]))
    out.append("Timeout=%r HideAuxiliary=%s PickerMode=%s"
               % (boot["timeout"], boot["hide_auxiliary"], boot["picker_mode"]))

    # --- 结论
    counts = summarize()
    out.append(hr("体检结论"))
    rows = []
    for item in CHECKS:
        rows.append([MARK[item["status"]], cut(item["group"] + " " + item["name"], 46),
                     cut(item["expected"], 26), cut(item["actual"], 26)])
    out.append(table(["判定", "项", "基准", "实际"], rows, [7, 46, 26, 26]))
    fails = [c for c in CHECKS if c["status"] == FAIL]
    warns = [c for c in CHECKS if c["status"] == WARN]
    if fails:
        out.append("修复建议（按顺序）:")
        for item in fails:
            out.append("  - %s" % item["name"])
            if item["hint"]:
                out.append("      改法: %s" % item["hint"])
            if item["note"]:
                out.append("      原因: %s" % item["note"])
    out.append("")
    out.append("汇总: PASS=%d  FAIL=%d  WARN=%d   （共 %d 项）"
               % (counts[PASS], counts[FAIL], counts[WARN], len(CHECKS)))
    if fails:
        verdict = "不达标：有 %d 项 FAIL，按上面的修复建议改完再重启。" % len(fails)
    elif warns:
        verdict = "基本达标：0 项 FAIL，%d 项 WARN（不阻断启动，但会影响排错/驱动阶段）。" % len(warns)
    else:
        verdict = "完全达标：所有基准项 PASS。"
    out.append("结论: %s" % verdict)
    return "\n".join(out), counts, verdict


def render_json(path, raw, cfg, facts, counts, verdict):
    payload = {
        "tool": "inspect-config.py",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "file": {
            "path": path,
            "size": len(raw),
            "mtime": datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S"),
            "root_keys": list(cfg.keys()),
        },
        "baseline": {
            "source": "_FACTS.md section 2",
            "target": "Arrow Lake (Core Ultra 5 245K) + macOS 26 + NVIDIA RTX 3070",
            "quirks": {"%s:Quirks:%s" % (g, k): (truth(e) if e is not None else "0 或 -1")
                       for g, k, e, _d, _h in BASELINE_QUIRKS},
            "cpuid": "0x%08X" % EXPECTED_CPUID,
            "csr": "FF0F0000",
            "scan_policy": EXPECTED_SCANPOLICY,
            "smbios": EXPECTED_SMBIOS,
            "secure_boot_model": EXPECTED_SECUREBOOTMODEL,
            "boot_args": POST_DRIVER_BOOT_ARGS,
            "required_kexts": REQUIRED_KEXTS,
        },
        "facts": facts,
        "checks": CHECKS,
        "summary": {
            "pass": counts[PASS],
            "fail": counts[FAIL],
            "warn": counts[WARN],
            "total": len(CHECKS),
            "verdict": verdict,
            "exit_code": 1 if counts[FAIL] else 0,
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


# ---------------------------------------------------------------- 自检 ------

SELF_TEST_PLIST = b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>ACPI</key>
  <dict>
    <key>Add</key><array/>
    <key>Delete</key>
    <array>
      <dict>
        <key>All</key><true/>
        <key>Comment</key><string>Drop VT-d DMAR</string>
        <key>Enabled</key><true/>
        <key>OemTableId</key><data>AAAAAAAA</data>
        <key>TableLength</key><integer>0</integer>
        <key>TableSignature</key><data>RE1BUg==</data>
      </dict>
    </array>
  </dict>
  <key>Booter</key>
  <dict>
    <key>Quirks</key>
    <dict>
      <key>DevirtualiseMmio</key><true/>
      <key>RebuildAppleMemoryMap</key><true/>
      <key>ResizeAppleGpuBars</key><integer>0</integer>
      <key>SetupVirtualMap</key><true/>
      <key>SyncRuntimePermissions</key><true/>
    </dict>
  </dict>
  <key>Kernel</key>
  <dict>
    <key>Add</key>
    <array>
      <dict><key>BundlePath</key><string>Lilu.kext</string><key>Enabled</key><true/></dict>
    </array>
    <key>Block</key><array/>
    <key>Emulate</key>
    <dict>
      <key>Cpuid1Data</key><data>VQYKAAAAAAAAAAAAAAAAAA==</data>
      <key>Cpuid1Mask</key><data>/////wAAAAAAAAAAAAAAAA==</data>
    </dict>
    <key>Patch</key><array/>
    <key>Quirks</key>
    <dict>
      <key>DisableIoMapper</key><true/>
      <key>LapicKernelPanic</key><false/>
      <key>ProvideCurrentCpuInfo</key><true/>
    </dict>
  </dict>
  <key>Misc</key>
  <dict>
    <key>Boot</key><dict><key>Timeout</key><integer>5</integer></dict>
    <key>Debug</key><dict><key>AppleDebug</key><true/><key>ApplePanic</key><true/><key>Target</key><integer>67</integer></dict>
    <key>Security</key>
    <dict>
      <key>ScanPolicy</key><integer>17760515</integer>
      <key>SecureBootModel</key><string>Disabled</string>
      <key>Vault</key><string>Optional</string>
    </dict>
  </dict>
  <key>NVRAM</key>
  <dict>
    <key>Add</key>
    <dict>
      <key>7C436110-AB2A-4BBB-A880-FE41995C9F82</key>
      <dict>
        <key>boot-args</key><string>keepsyms=1</string>
        <key>csr-active-config</key><data>/w8AAA==</data>
      </dict>
    </dict>
    <key>Delete</key>
    <dict>
      <key>7C436110-AB2A-4BBB-A880-FE41995C9F82</key>
      <array><string>boot-args</string></array>
    </dict>
  </dict>
  <key>PlatformInfo</key>
  <dict><key>Generic</key>
    <dict>
      <key>SystemProductName</key><string>MacPro7,1</string>
      <key>SystemSerialNumber</key><string>F5KLW0QJP7QM</string>
    </dict>
  </dict>
  <key>UEFI</key>
  <dict><key>Quirks</key><dict><key>ResizeGpuBars</key><integer>-1</integer></dict></dict>
</dict>
</plist>
"""


def self_test():
    """内置最小 plist 自检：不依赖外部文件，用来验证解析/判定链路没坏。"""
    cfg = plistlib.loads(SELF_TEST_PLIST)
    facts = collect(cfg)
    run_checks(facts, cfg)
    counts = summarize()
    ok = 0
    bad = 0
    # 关键事实逐条断言
    expects = [
        (facts["nvram"]["csr_value"] == "0x0FFF", "csr 解析 = 0x0FFF"),
        ('CSR_ALLOW_TASK_FOR_PID' in facts["nvram"]["csr_flags"], "csr 位解码含 TASK_FOR_PID"),
        (facts["cpuid"]["signature"] == "0x%08X" % EXPECTED_CPUID, "Cpuid1Data 解码 = 0x000A0655"),
        (facts["security"]["scan_policy"] == EXPECTED_SCANPOLICY, "ScanPolicy = 17760515"),
        ('ALLOW_DEVICE_SATA' in facts["security"]["scan_policy_flags"], "ScanPolicy 位解码含 SATA"),
        (facts["acpi_delete"][0]["sig"] == "DMAR", "ACPI Delete 签名 = DMAR"),
        (facts["nvram"]["has_boot_args_in_delete"] is True, "NVRAM Delete 命中 boot-args"),
        (facts["quirks"]["Booter:Quirks:ResizeAppleGpuBars"] == 0, "ResizeAppleGpuBars = 0"),
        (len(csr_flags(bytes.fromhex("430a0000"))[0]) == 5, "0x0A43 应解出 5 个置位"),
        (len([f for _b, f in CSR_BITS if 0x0FFF & _b]) == 12, "0x0FFF 应解出 12 个置位"),
    ]
    for good, label in expects:
        emit("  %s %s" % ("[ok]  " if good else "[BAD] ", label))
        ok += 1 if good else 0
        bad += 0 if good else 1
    # 这个最小样本缺补丁/缺 kext，必然有 FAIL —— 判定引擎必须报出来
    if counts[FAIL] > 0:
        emit("  [ok]   判定引擎按预期报出 FAIL=%d（样本确实不达标）" % counts[FAIL])
        ok += 1
    else:
        emit("  [BAD]  判定引擎没有报 FAIL，逻辑有问题")
        bad += 1
    emit("自检: %d 项通过, %d 项失败" % (ok, bad))
    return 0 if bad == 0 else 1


# ---------------------------------------------------------------- main -----

def main(argv=None):
    tune_streams()

    parser = argparse.ArgumentParser(
        prog="inspect-config.py",
        description="OpenCore config.plist 体检（基准: _FACTS.md 第二节，Arrow Lake + macOS 26 + NVIDIA）",
        epilog="退出码: 0=无 FAIL，1=有 FAIL，2=文件读取/解析失败")
    parser.add_argument("config", nargs="?", help="config.plist 路径（可含中文/空格）")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON（含全部判定与原始字段）")
    parser.add_argument("--self-test", action="store_true", help="跑内置自检，不读外部文件")
    parser.add_argument("--quiet", action="store_true", help="只输出结论段")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.config:
        parser.error("缺少 config.plist 路径（或用 --self-test）")

    try:
        path, raw, cfg = load_config(args.config)
    except FileNotFoundError:
        eprint("[FAIL] 找不到文件: %s" % args.config)
        return 2
    except Exception as exc:  # noqa: BLE001 - 解析失败要给出人话
        eprint("[FAIL] 解析失败（不是合法 plist？）: %s -> %s" % (args.config, exc))
        return 2

    facts = collect(cfg)
    run_checks(facts, cfg)
    text, counts, verdict = render_text(path, raw, cfg, facts)

    if args.json:
        emit(render_json(path, raw, cfg, facts, counts, verdict))
    elif args.quiet:
        lines = [hr("体检结论")]
        for item in CHECKS:
            lines.append("%s %-46s %s" % (MARK[item["status"]],
                                          item["group"] + " " + item["name"],
                                          "" if item["status"] == PASS else item["actual"]))
        lines.append("")
        lines.append("汇总: PASS=%d FAIL=%d WARN=%d" % (counts[PASS], counts[FAIL], counts[WARN]))
        lines.append("结论: %s" % verdict)
        emit("\n".join(lines))
    else:
        emit(text)

    return 1 if counts[FAIL] else 0


if __name__ == "__main__":
    sys.exit(main())
