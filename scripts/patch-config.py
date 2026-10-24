#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch-config.py -- 按 _FACTS.md 第二节的成功组合批量改 OpenCore config.plist

子命令（首个参数是子命令，第二个是 config.plist 路径）:
    apply-preset    应用「Arrow Lake + macOS 26 + NVIDIA」成功配置（含两条时钟补丁）
    set-boot-args   设置/追加/删除 boot-args（自动把 boot-args 塞进 NVRAM->Delete）
    set-csr         设置 csr-active-config（SIP），支持 0x0FFF / FF0F0000 两种写法
    set-quirk       改任意 quirk / 键：set-quirk CFG Kernel:Quirks:ProvideCurrentCpuInfo true
    block-iondrv    往 Kernel->Block 加 com.apple.iokit.IONDRVSupport 屏蔽项
    unblock-iondrv  删掉上面的屏蔽项
    show            打印本工具关心的当前值
    show-diff       和备份做差异对比（语义差异，另有 --unified 文本 diff）

安全约束（所有写操作都遵守）:
  1. 写之前先备份到 <config>.bak-<YYYYmmdd-HHMMSS>（同秒重复自动加序号）；
  2. 先写临时文件并重新 plistlib 解析校验，合法才 os.replace 覆盖；
  3. 校验失败立刻回滚成备份，退出码非 0；
  4. --dry-run 只打印计划，不落盘、不备份。

只用标准库；路径含中文/空格可用。
"""

import argparse
import difflib
import os
import plistlib
import re
import shutil
import sys
import unicodedata
from datetime import datetime

# ---------------------------------------------------------------- 常量 ------

APPLE_BOOT_GUID = "7C436110-AB2A-4BBB-A880-FE41995C9F82"

# _FACTS.md 第二节
BOOT_ARGS_DRIVER = (
    "keepsyms=1 revpatch=sbvmm nvfb=1 nvaccel=1 nvfbheads=1 -nvkmsnosmooth "
    "amfi_get_out_of_my_way=0x1 amfi=0x80 ipc_control_port_options=0"
)
BOOT_ARGS_INSTALL = "-v keepsyms=1"

CPUID1_DATA = bytes.fromhex("55060A00") + b"\x00" * 12   # 0x000A0655 Comet Lake
CPUID1_MASK = b"\xff\xff\xff\xff" + b"\x00" * 12
CSR_OFF = b"\xff\x0f\x00\x00"                            # 0x0FFF 全关 SIP

DMAR_DELETE = {
    "All": True,
    "Comment": "Drop VT-d DMAR (Core Ultra hangs at the kernel hand-off with it)",
    "Enabled": True,
    "OemTableId": b"\x00" * 8,
    "TableLength": 0,
    "TableSignature": b"DMAR",
}

# 两条 Remove non-monotonic time panic 补丁（字节与内核区间照抄 M:\EFI\OC\config.plist 实测值）
TIME_PATCHES = [
    {
        "Arch": "x86_64",
        "Base": "",
        "Comment": "Visual | thread_invoke, thread_dispatch | Remove non-monotonic time panic | 12.0-26.3",
        "Count": 2,
        "Enabled": True,
        "Find": bytes.fromhex("480000800400000f0000000000"),
        "Identifier": "kernel",
        "Limit": 0,
        "Mask": bytes.fromhex("480000f0ffffffff0000000000"),
        "MaxKernel": "25.3.99",
        "MinKernel": "21.0.0",
        "Replace": bytes.fromhex("00000000000000669066906690"),
        "ReplaceMask": bytes.fromhex("00000000000000ffffffffffff"),
        "Skip": 0,
    },
    {
        "Arch": "x86_64",
        "Base": "",
        "Comment": "laobamac | thread_invoke, thread_dispatch | Remove non-monotonic time panic | 26.4+",
        "Count": 2,
        "Enabled": True,
        "Find": bytes.fromhex("480000900400000f0000000000"),
        "Identifier": "kernel",
        "Limit": 0,
        "Mask": bytes.fromhex("480000f0ffffffff0000000000"),
        "MaxKernel": "25.99.99",
        "MinKernel": "25.4.0",
        "Replace": bytes.fromhex("00000000000000669066906690"),
        "ReplaceMask": bytes.fromhex("00000000000000ffffffffffff"),
        "Skip": 0,
    },
]
TIME_PATCH_AUTHORS = ["Visual", "laobamac"]

REQUIRED_KEXTS = [
    "Lilu.kext", "VirtualSMC.kext", "AMFIPass.kext", "AppleMCEReporterDisabler.kext",
    "RestrictEvents.kext", "SMCProcessor.kext", "SMCSuperIO.kext",
    "USBToolBox.kext", "UTBDefault.kext", "WhateverGreen.kext", "RTL812xLucy.kext",
]

IONDRV_IDENTIFIER = "com.apple.iokit.IONDRVSupport"

MISSING = object()
CHANGES = []   # [(path, old, new)]，用于打印计划
WARNINGS = []


# ---------------------------------------------------------------- 输出 ------

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
    data = text + "\n"
    buf = getattr(sys.stderr, "buffer", None)
    try:
        if buf is not None:
            buf.write(data.encode("utf-8"))
            buf.flush()
            return
    except Exception:
        pass
    sys.stderr.write(data)


def disp_width(text):
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in str(text))


def pad(text, width, align="left"):
    text = str(text)
    if disp_width(text) > width:
        clipped = ""
        used = 0
        for ch in text:
            w = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
            if used + w > width - 2:
                break
            clipped += ch
            used += w
        text = clipped + ".."
    space = " " * max(0, width - disp_width(text))
    return space + text if align == "right" else text + space


def fmt_value(value):
    if value is MISSING:
        return "(不存在)"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (bytes, bytearray)):
        return "<data %s>" % bytes(value).hex().upper() if value else "<data 空>"
    if isinstance(value, list):
        return "[%d 项]" % len(value)
    if isinstance(value, dict):
        return "{%d 键}" % len(value)
    if value is None:
        return "(空值)"
    text = str(value)
    return text if len(text) <= 72 else text[:69] + "..."


# ---------------------------------------------------------------- 读写 ------

def load_config(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    cfg = plistlib.loads(raw)
    if not isinstance(cfg, dict):
        raise ValueError("根节点不是 dict，不像 OpenCore config.plist")
    return cfg


def free_backup_name(path):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = "%s.bak-%s" % (path, stamp)
    seq = 2
    while os.path.exists(candidate):
        candidate = "%s.bak-%s-%d" % (path, stamp, seq)
        seq += 1
    return candidate


def commit(cfg, path, dry_run=False, backup=True):
    """备份 -> 写临时文件 -> 重新解析校验 -> 原子替换。返回 (备份路径, 校验信息)。"""
    if dry_run:
        return None, "dry-run：不写盘"
    bak = None
    if backup:
        bak = free_backup_name(path)
        shutil.copy2(path, bak)
    tmp = path + ".tmp-patchpy"
    try:
        with open(tmp, "wb") as fh:
            plistlib.dump(cfg, fh, fmt=plistlib.FMT_XML, sort_keys=False)
        # 1) 重新解析校验
        with open(tmp, "rb") as fh:
            reparsed = plistlib.load(fh)
        if not isinstance(reparsed, dict):
            raise ValueError("写出的文件解析后不是 dict")
        # 2) 关键结构兜底校验（防止把 OpenCore 必需的段写没了）
        for key in ("ACPI", "Booter", "Kernel", "Misc", "NVRAM", "PlatformInfo", "UEFI"):
            if key not in reparsed:
                raise ValueError("写出的文件缺少必需的段: %s" % key)
        if not reparsed.get("Kernel", {}).get("Add") and cfg.get("Kernel", {}).get("Add"):
            raise ValueError("Kernel->Add 写没了")
        shutil.copymode(path, tmp)   # 保留原文件权限位（时间戳要更新，别复刻 mtime）
        os.replace(tmp, path)
    except Exception as exc:  # noqa: BLE001
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        if bak and os.path.exists(bak):
            shutil.copy2(bak, path)
            raise RuntimeError("写入/校验失败，已从 %s 回滚: %s" % (os.path.basename(bak), exc))
        raise RuntimeError("写入/校验失败（没有备份可回滚）: %s" % exc)

    # 3) 落盘后再读一次，确认磁盘上的就是合法的
    with open(path, "rb") as fh:
        final = plistlib.load(fh)
    if not isinstance(final, dict) or "Kernel" not in final:
        raise RuntimeError("落盘后复读异常，请用备份还原")
    return bak, "已重新解析校验通过"


# ---------------------------------------------------------------- 改值 ------

def record(change_path, old, new):
    CHANGES.append((change_path, old, new))


def walk(cfg, keys, create=False):
    """按 ['ACPI','Delete'] 走 dict，返回末级容器。"""
    cur = cfg
    for key in keys:
        if isinstance(cur, dict):
            if key not in cur:
                if not create:
                    return None
                cur[key] = {}
            cur = cur[key]
        else:
            return None
    return cur


def set_key(cfg, dotted, value, label=None):
    """设置 dict 里的一个键（不存在就建）。dotted 支持 Kernel:Quirks:X / Kernel.Quirks.X。"""
    keys = split_path(dotted)
    parent = walk(cfg, keys[:-1], create=True)
    if parent is None or not isinstance(parent, dict):
        raise ValueError("路径 %s 的父级不是 dict: %s" % (dotted, keys[:-1]))
    key = keys[-1]
    old = parent[key] if key in parent else MISSING
    same = (type(old) is type(value)) and old == value
    if not same:
        parent[key] = value
        record(label or "/".join(keys), old, value)
    return not same


def split_path(text):
    parts = re.split(r"[:./]+|->", text)
    return [p for p in parts if p != ""]


def as_list(cfg, dotted):
    keys = split_path(dotted)
    parent = walk(cfg, keys[:-1], create=True)
    key = keys[-1]
    if key not in parent or not isinstance(parent[key], list):
        old = parent.get(key, MISSING)
        parent[key] = []
        record("/".join(keys), old, [])
    return parent[key]


def as_dict(cfg, dotted):
    keys = split_path(dotted)
    parent = walk(cfg, keys[:-1], create=True)
    key = keys[-1]
    if key not in parent or not isinstance(parent[key], dict):
        old = parent.get(key, MISSING)
        parent[key] = {}
        record("/".join(keys), old, {})
    return parent[key]


# ---------------------------------------------------------------- 解析值 ----

def parse_scalar(text, force_type=None):
    low = str(text).strip().lower()
    if force_type == "str":
        return str(text)
    if force_type == "bool" or low in ("true", "false", "yes", "no", "on", "off"):
        if low in ("true", "yes", "on", "1"):
            return True
        if low in ("false", "no", "off", "0"):
            return False
        if force_type == "bool":
            raise ValueError("--type bool 只接受 true/false")
    if force_type == "int" or re.fullmatch(r"[+-]?\d+", low):
        try:
            return int(low)
        except ValueError:
            raise ValueError("这一项是整数，%r 不是数字（用 0 / 1 / -1 这种）" % text)
    return str(text)


def parse_csr(text):
    """返回 (4 字节 little-endian data, 数值)。接受 0x0FFF / 0FFF / FF0F0000 / disabled。"""
    raw = str(text).strip()
    low = raw.lower()
    if low in ("off", "disabled", "sip-off", "none"):
        return b"\x00\x00\x00\x00", 0x0000
    if low.startswith("0x"):
        value = int(low, 16)
        if value > 0xFFFFFFFF:
            raise ValueError("csr 值超出 32 位: %s" % text)
        return value.to_bytes(4, "little"), value
    digits = low.replace(" ", "")
    if re.fullmatch(r"[0-9a-f]{8}", digits):
        data = bytes.fromhex(digits)
        return data, int.from_bytes(data, "little")
    if re.fullmatch(r"[0-9a-f]{1,4}", digits):
        value = int(digits, 16)
        return value.to_bytes(4, "little"), value
    raise ValueError("看不懂的 csr 值: %s（用 0x0FFF 或 FF0F0000）" % text)


# ---------------------------------------------------------------- 子命令 ----

def cmd_apply_preset(cfg, path, args):
    stage = args.stage
    boot_args = BOOT_ARGS_INSTALL if stage == "install" else BOOT_ARGS_DRIVER
    bar_apple, bar_oc = (0, -1) if stage == "install" else (-1, 13)

    # 1) Kernel quirks
    for key, value in (("ProvideCurrentCpuInfo", True), ("DisableIoMapper", True),
                       ("LapicKernelPanic", False)):
        set_key(cfg, "Kernel:Quirks:%s" % key, value)
    # 2) Booter quirks
    for key, value in (("DevirtualiseMmio", True), ("SetupVirtualMap", True),
                       ("RebuildAppleMemoryMap", True), ("SyncRuntimePermissions", True),
                       ("ResizeAppleGpuBars", bar_apple)):
        set_key(cfg, "Booter:Quirks:%s" % key, value)
    # 3) UEFI quirks
    set_key(cfg, "UEFI:Quirks:ResizeGpuBars", bar_oc)
    # 4) ACPI Delete DMAR
    deletes = as_list(cfg, "ACPI:Delete")
    hit = None
    for item in deletes:
        sig = item.get("TableSignature")
        if isinstance(sig, (bytes, bytearray)) and bytes(sig).decode("ascii", "replace") == "DMAR":
            hit = item
            break
    if hit is None:
        deletes.append(dict(DMAR_DELETE))
        record("ACPI/Delete (+DMAR)", MISSING, DMAR_DELETE)
    else:
        for key, value in DMAR_DELETE.items():
            if hit.get(key) != value:
                record("ACPI/Delete[DMAR]/%s" % key, hit.get(key, MISSING), value)
                hit[key] = value
    # 5) CPUID 伪装
    set_key(cfg, "Kernel:Emulate:Cpuid1Data", CPUID1_DATA)
    set_key(cfg, "Kernel:Emulate:Cpuid1Mask", CPUID1_MASK)
    # 6) CpuTopologyRebuild 必须关 + 必备 kext 全开
    kext_adds = cfg.setdefault("Kernel", {}).setdefault("Add", [])
    for item in kext_adds:
        bundle = item.get("BundlePath") or ""
        if "CpuTopologyRebuild" in bundle and item.get("Enabled") is not False:
            record("Kernel/Add[%s]/Enabled" % bundle, item.get("Enabled"), False)
            item["Enabled"] = False
    present = set()
    for item in kext_adds:
        bundle = item.get("BundlePath") or ""
        present.add(bundle)
        if bundle in REQUIRED_KEXTS and item.get("Enabled") is not True:
            record("Kernel/Add[%s]/Enabled" % bundle, item.get("Enabled"), True)
            item["Enabled"] = True
    for bundle in REQUIRED_KEXTS:
        if bundle not in present:
            WARNINGS.append("必备 kext 不在配置里（本工具不造文件）: %s —— 请把 kext 放进 EFI/OC/Kexts 再加进 Kernel->Add" % bundle)
    # 7) 两条时钟补丁
    patches = as_list(cfg, "Kernel:Patch")
    for spec in TIME_PATCHES:
        author = spec["Comment"].split(" | ")[0]
        hit = None
        for item in patches:
            comment = (item.get("Comment") or "").lower()
            if author.lower() in comment and "non-monotonic" in comment:
                hit = item
                break
        if hit is None:
            patches.append(dict(spec))
            record("Kernel/Patch (+%s 时钟补丁)" % author, MISSING, spec["Comment"])
        else:
            for key, value in spec.items():
                if hit.get(key) != value:
                    record("Kernel/Patch[%s]/%s" % (author, key), hit.get(key, MISSING), value)
                    hit[key] = value
    # 8) NVRAM：csr + boot-args + Delete
    nv_add = as_dict(cfg, "NVRAM:Add:%s" % APPLE_BOOT_GUID)
    if args.keep_boot_args:
        pass
    else:
        set_key(nv_add, "boot-args", boot_args, label="NVRAM/Add/boot-args")
    set_key(nv_add, "csr-active-config", CSR_OFF, label="NVRAM/Add/csr-active-config")
    nv_delete = as_dict(cfg, "NVRAM:Delete")
    delete_list = nv_delete.setdefault(APPLE_BOOT_GUID, [])
    if not isinstance(delete_list, list):
        delete_list = []
        nv_delete[APPLE_BOOT_GUID] = delete_list
    for token in ("boot-args", "csr-active-config"):
        if token not in delete_list:
            delete_list.append(token)
            record("NVRAM/Delete[7C436110] (+%s)" % token, MISSING, token)
    # 9) 安全 / 机型
    set_key(cfg, "Misc:Security:SecureBootModel", "Disabled")
    set_key(cfg, "Misc:Security:ScanPolicy", 17760515)
    set_key(cfg, "Misc:Security:Vault", "Optional")
    set_key(cfg, "PlatformInfo:Generic:SystemProductName", "MacPro7,1")
    if stage == "driver":
        note_stage = "驱动阶段：ResizeAppleGpuBars=-1、ResizeGpuBars=13、boot-args 用驱动全套"
    else:
        note_stage = "安装阶段：ResizeAppleGpuBars=0、ResizeGpuBars=-1、boot-args=-v keepsyms=1"
    emit("apply-preset --stage %s  （%s）" % (stage, note_stage))
    return True


def cmd_set_boot_args(cfg, path, args):
    nv_add = as_dict(cfg, "NVRAM:Add:%s" % APPLE_BOOT_GUID)
    current = nv_add.get("boot-args")
    current_text = current if isinstance(current, str) else ""
    tokens = current_text.split()

    if args.show and not (args.value or args.stage or args.append or args.remove):
        emit("当前 boot-args: %s" % (current_text or "(空)"))
        return False

    if args.stage:
        new_text = BOOT_ARGS_INSTALL if args.stage == "install" else BOOT_ARGS_DRIVER
        tokens = new_text.split()
    if args.value is not None:
        tokens = args.value.split()
    if args.append:
        for token in args.append:
            for piece in token.split():
                if piece not in tokens:
                    tokens.append(piece)
    if args.remove:
        for token in args.remove:
            for piece in token.split():
                while piece in tokens:
                    tokens.remove(piece)
    new_text = " ".join(tokens)
    set_key(nv_add, "boot-args", new_text, label="NVRAM/Add/boot-args")
    if not args.no_nvram_delete:
        delete_list = as_dict(cfg, "NVRAM:Delete").setdefault(APPLE_BOOT_GUID, [])
        if not isinstance(delete_list, list):
            delete_list = []
            as_dict(cfg, "NVRAM:Delete")[APPLE_BOOT_GUID] = delete_list
        if "boot-args" not in delete_list:
            delete_list.append("boot-args")
            record("NVRAM/Delete[7C436110] (+boot-args)", MISSING, "boot-args")
            emit("提示: 已同时把 boot-args 加进 NVRAM->Delete —— 否则 NVRAM 旧值会盖住这次修改"
                 "（启动日志会写 Setting NVRAM ... - ignored, exists）")
    if args.show:
        emit("新 boot-args    : %s" % new_text)
    return True


def cmd_set_csr(cfg, path, args):
    data, value = parse_csr(args.value)
    nv_add = as_dict(cfg, "NVRAM:Add:%s" % APPLE_BOOT_GUID)
    set_key(nv_add, "csr-active-config", data, label="NVRAM/Add/csr-active-config")
    delete_list = as_dict(cfg, "NVRAM:Delete").setdefault(APPLE_BOOT_GUID, [])
    if isinstance(delete_list, list) and "csr-active-config" not in delete_list:
        delete_list.append("csr-active-config")
        record("NVRAM/Delete[7C436110] (+csr-active-config)", MISSING, "csr-active-config")
    enabled = [name for bit, name in (
        (0x001, "UNTRUSTED_KEXTS"), (0x002, "UNRESTRICTED_FS"), (0x004, "TASK_FOR_PID"),
        (0x008, "KERNEL_DEBUGGER"), (0x010, "APPLE_INTERNAL"), (0x020, "UNRESTRICTED_DTRACE"),
        (0x040, "UNRESTRICTED_NVRAM"), (0x080, "DEVICE_CONFIGURATION"),
        (0x100, "ANY_RECOVERY_OS"), (0x200, "UNAPPROVED_KEXTS"),
        (0x400, "EXECUTABLE_POLICY_OVERRIDE"), (0x800, "UNAUTHENTICATED_ROOT"),
    ) if value & bit]
    emit("csr-active-config = %s（0x%04X），置位 %d 个: %s"
         % (data.hex().upper(), value, len(enabled), ", ".join(enabled) or "(无)"))
    if value != 0x0FFF and value != 0:
        emit("提醒: 实战成功值是 0x0FFF（FF0F0000）。缺 CSR_ALLOW_TASK_FOR_PID(0x04) 会让所有"
             "系统服务 setuid/task_for_pid 报 Operation not permitted。")
    return True


def cmd_set_quirk(cfg, path, args):
    keys = split_path(args.key)
    if len(keys) < 2:
        raise ValueError("路径至少两段，例如 Kernel:Quirks:ProvideCurrentCpuInfo")
    parent = walk(cfg, keys[:-1])
    key = keys[-1]
    if parent is None or not isinstance(parent, dict):
        raise ValueError("父级不存在: %s（先用 GUI 或 apply-preset 建立）" % ":".join(keys[:-1]))
    old = parent.get(key, MISSING)
    force = args.type
    if force == "auto" and old is not MISSING:
        if isinstance(old, bool):
            force = "bool"
        elif isinstance(old, int) and not isinstance(old, bool):
            force = "int"
        elif isinstance(old, str):
            force = "str"
    value = parse_scalar(args.value, force)
    if isinstance(old, bool) and not isinstance(value, bool):
        raise ValueError("该项是布尔值，只接受 true/false（收到 %r）" % args.value)
    if isinstance(old, int) and not isinstance(old, bool) and not isinstance(value, int):
        raise ValueError("该项是整数（当前 %r），只接受数字（收到 %r）" % (old, args.value))
    set_key(cfg, args.key, value, label="/".join(keys))
    emit("%-46s : %s -> %s" % (":".join(keys), fmt_value(old), fmt_value(value)))
    return True


def cmd_block_iondrv(cfg, path, args):
    ident = args.identifier
    blocks = as_list(cfg, "Kernel:Block")
    hit = [b for b in blocks if b.get("Identifier") == ident]
    if hit:
        for item in hit:
            if item.get("Enabled") is not True:
                record("Kernel/Block[%s]/Enabled" % ident, item.get("Enabled"), True)
                item["Enabled"] = True
        emit("已存在屏蔽项 %s，置 Enabled=True（共 %d 条）" % (ident, len(hit)))
    else:
        entry = {
            "Arch": "Any",
            "Comment": "NullMoth driver owns the display",
            "Enabled": True,
            "Identifier": ident,
            "Strategy": "Exclude",
        }
        blocks.append(entry)
        record("Kernel/Block (+%s)" % ident, MISSING, entry)
        emit("已加入屏蔽项: Identifier=%s Strategy=Exclude Enabled=True（索引 %d）"
             % (ident, len(blocks) - 1))
    return True


def cmd_unblock_iondrv(cfg, path, args):
    ident = args.identifier
    blocks = as_list(cfg, "Kernel:Block")
    keep = []
    removed = 0
    for item in blocks:
        if item.get("Identifier") == ident:
            removed += 1
            continue
        keep.append(item)
    if removed:
        blocks[:] = keep
        record("Kernel/Block (-%s x%d)" % (ident, removed), "%d 条" % removed, "已移除")
        emit("已移除 %d 条 %s 屏蔽项；当前 Kernel->Block 共 %d 条" % (removed, ident, len(blocks)))
    else:
        emit("没有找到 %s 屏蔽项，不需要改" % ident)
    return False


def cmd_show(cfg, path, args):
    def val(dotted):
        keys = split_path(dotted)
        parent = walk(cfg, keys[:-1])
        if parent is None or not isinstance(parent, dict):
            return "(缺失)"
        return fmt_value(parent.get(keys[-1], MISSING))

    rows = [
        ("内核/CPU", "Kernel:Quirks:ProvideCurrentCpuInfo"),
        ("内核/CPU", "Kernel:Quirks:DisableIoMapper"),
        ("内核/CPU", "Kernel:Quirks:LapicKernelPanic"),
        ("内存映射", "Booter:Quirks:DevirtualiseMmio"),
        ("内存映射", "Booter:Quirks:ResizeAppleGpuBars"),
        ("内存映射", "Booter:Quirks:SetupVirtualMap"),
        ("内存映射", "Booter:Quirks:RebuildAppleMemoryMap"),
        ("内存映射", "Booter:Quirks:SyncRuntimePermissions"),
        ("BAR", "UEFI:Quirks:ResizeGpuBars"),
        ("CPU 伪装", "Kernel:Emulate:Cpuid1Data"),
        ("SIP", "NVRAM:Add:%s:csr-active-config" % APPLE_BOOT_GUID),
        ("启动参数", "NVRAM:Add:%s:boot-args" % APPLE_BOOT_GUID),
        ("安全", "Misc:Security:SecureBootModel"),
        ("安全", "Misc:Security:ScanPolicy"),
        ("机型", "PlatformInfo:Generic:SystemProductName"),
    ]
    emit("%s %s %s" % (pad("分组", 10), pad("键", 54), "当前值"))
    emit("-" * 104)
    for group, dotted in rows:
        emit("%s %s %s" % (pad(group, 10), pad(dotted, 54), val(dotted)))
    emit("")
    def signature_text(item):
        sig = item.get("TableSignature")
        if isinstance(sig, (bytes, bytearray)):
            return bytes(sig).decode("ascii", "replace").strip("\x00") or fmt_value(sig)
        return fmt_value(sig)

    emits = [("ACPI/Delete", [signature_text(x) for x in
                              (walk(cfg, ["ACPI", "Delete"]) or [])]),
             ("Kernel/Block", ["%s(%s)" % (x.get("Identifier"), x.get("Enabled"))
                               for x in (walk(cfg, ["Kernel", "Block"]) or [])]),
             ("Kernel/Patch", [fmt_value(x.get("Comment")) for x in
                               (walk(cfg, ["Kernel", "Patch"]) or [])]),
             ("NVRAM/Delete", [", ".join(x) if isinstance(x, list) else fmt_value(x)
                               for x in [walk(cfg, ["NVRAM", "Delete", APPLE_BOOT_GUID])] if x])]
    for name, values in emits:
        emit("%s: %s" % (name, " | ".join(str(v) for v in values) or "(空)"))
    return False


def cmd_show_diff(cfg, path, args):
    target = args.against
    if not target:
        candidates = sorted(
            [name for name in os.listdir(os.path.dirname(path) or ".")
             if name.startswith(os.path.basename(path) + ".bak-")],
        )
        if not candidates:
            raise ValueError("目录里没有 %s.bak-* 备份；用 --against <旧文件> 指定对比对象"
                             % os.path.basename(path))
        target = os.path.join(os.path.dirname(path) or ".", candidates[-1])
        emit("对比对象（默认取最新备份）: %s" % target)
    else:
        emit("对比对象（--against）: %s" % target)

    old_cfg = load_config(target)
    diffs = diff_plists(old_cfg, cfg)

    emit("")
    if args.unified:
        emit("=== 文本 diff: %s -> %s ===" % (os.path.basename(target), os.path.basename(path)))
        with open(target, "r", encoding="utf-8", errors="replace") as fh:
            old_lines = fh.readlines()
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            new_lines = fh.readlines()
        text = "".join(difflib.unified_diff(old_lines, new_lines,
                                            fromfile=os.path.basename(target),
                                            tofile=os.path.basename(path), n=2))
        emit(text or "(无差异)")
        return False

    emit("=== 语义 diff（%d 处）: 旧 -> 新 ===" % len(diffs))
    if not diffs:
        emit("(无差异：当前 config 与对比对象完全一致)")
        return False
    for change_path, old, new in diffs:
        emit("  %-58s %s -> %s" % (change_path, fmt_value(old), fmt_value(new)))
    return False


def diff_plists(a, b, prefix=""):
    out = []
    if type(a) is not type(b) and not (isinstance(a, (bytes, bytearray))
                                       and isinstance(b, (bytes, bytearray))):
        out.append((prefix or "/", a, b))
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for key in a:
            if key not in b:
                out.append((prefix + "/" + key, a[key], "<已删除>"))
            else:
                out.extend(diff_plists(a[key], b[key], prefix + "/" + key))
        for key in b:
            if key not in a:
                out.append((prefix + "/" + key, "<原本没有>", b[key]))
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append((prefix + "[长度]", len(a), len(b)))
        for index in range(min(len(a), len(b))):
            out.extend(diff_plists(a[index], b[index], "%s[%d]" % (prefix, index)))
        return out
    if isinstance(a, (bytes, bytearray)) and isinstance(b, (bytes, bytearray)):
        if bytes(a) != bytes(b):
            out.append((prefix, a, b))
        return out
    if a != b:
        out.append((prefix or "/", a, b))
    return out


# ---------------------------------------------------------------- 主流程 ----

COMMANDS = {
    "apply-preset": cmd_apply_preset,
    "set-boot-args": cmd_set_boot_args,
    "set-csr": cmd_set_csr,
    "set-quirk": cmd_set_quirk,
    "block-iondrv": cmd_block_iondrv,
    "unblock-iondrv": cmd_unblock_iondrv,
    "show": cmd_show,
    "show-diff": cmd_show_diff,
}

WRITE_COMMANDS = {"apply-preset", "set-boot-args", "set-csr", "set-quirk",
                  "block-iondrv", "unblock-iondrv"}


def add_common(parser):
    parser.add_argument("config", help="config.plist 路径（可含中文/空格）")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要改的内容，不写盘、不备份")
    parser.add_argument("--no-backup", action="store_true", help="不生成 .bak-时间戳（不建议）")
    parser.add_argument("--quiet", action="store_true", help="少打印")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="patch-config.py",
        description="按 _FACTS.md 第二节的成功组合修补 OpenCore config.plist（所有写操作先备份再校验）",
        epilog="示例: patch-config.py apply-preset D:\\config.plist --stage install --dry-run")
    sub = parser.add_subparsers(dest="command", metavar="<子命令>")

    p = sub.add_parser("apply-preset", help="应用成功配置（quirks/DMAR/CPUID/补丁/csr/boot-args/SMBIOS）")
    add_common(p)
    p.add_argument("--stage", choices=["install", "driver"], default="install",
                   help="install=安装阶段(BAR 0/-1, boot-args=-v keepsyms=1)；"
                        "driver=驱动阶段(BAR -1/13, boot-args 驱动全套)")
    p.add_argument("--keep-boot-args", action="store_true", help="不动 boot-args")

    p = sub.add_parser("set-boot-args", help="设置/追加/删除 boot-args")
    add_common(p)
    p.add_argument("value", nargs="?", help="整串 boot-args（带引号）")
    p.add_argument("--stage", choices=["install", "driver"], help="用预设串")
    p.add_argument("--append", action="append", metavar="TOKEN",
                   help="追加 token，可重复给（支持 --append -v 这种以 - 开头的写法）")
    p.add_argument("--remove", action="append", metavar="TOKEN",
                   help="删除 token，可重复给")
    p.add_argument("--show", action="store_true", help="打印当前/修改后的值")
    p.add_argument("--no-nvram-delete", action="store_true",
                   help="不要自动把 boot-args 加进 NVRAM->Delete")

    p = sub.add_parser("set-csr", help="设置 csr-active-config（0x0FFF / FF0F0000 / disabled）")
    add_common(p)
    p.add_argument("value", help="0x0FFF 或 FF0F0000 或 0A43 或 disabled")

    p = sub.add_parser("set-quirk", help="改任意键：set-quirk CFG Kernel:Quirks:ProvideCurrentCpuInfo true")
    add_common(p)
    p.add_argument("key", help="键路径，支持 : . / -> 分隔")
    p.add_argument("value", help="true/false/整数/字符串")
    p.add_argument("--type", choices=["auto", "bool", "int", "str"], default="auto",
                   help="强制值类型（默认按现有值类型推断）")

    for name, help_text in (("block-iondrv", "往 Kernel->Block 加 IONDRVSupport 屏蔽项"),
                            ("unblock-iondrv", "移除 IONDRVSupport 屏蔽项")):
        p = sub.add_parser(name, help=help_text)
        add_common(p)
        p.add_argument("--identifier", default=IONDRV_IDENTIFIER, help="要屏蔽的 kext 标识")

    p = sub.add_parser("show", help="打印本工具关心的当前值")
    add_common(p)

    p = sub.add_parser("show-diff", help="和备份/指定文件做差异对比")
    add_common(p)
    p.add_argument("--against", help="对比对象（默认取同目录最新 .bak-* 备份）")
    p.add_argument("--unified", action="store_true", help="输出文本 unified diff")
    return parser


VALUE_FLAGS = ("--append", "--remove")


def preprocess_argv(argv):
    """把 `--append -v nvfb=1` 改写成 `--append=-v --append=nvfb=1`。

    argparse 会把以 - 开头的 token 当成选项，直接报 "expected at least one argument"，
    而 boot-args 里恰恰全是 -v / -nvkmsnosmooth 这种 token。
    """
    out = []
    index = 0
    while index < len(argv):
        current = argv[index]
        if current in VALUE_FLAGS:
            values = []
            cursor = index + 1
            while cursor < len(argv) and not argv[cursor].startswith("--"):
                values.append(argv[cursor])
                cursor += 1
            if values:
                for value in values:
                    out.append("%s=%s" % (current, value))
                index = cursor
                continue
            out.append(current)
            index += 1
            continue
        out.append(current)
        index += 1
    return out


def main(argv=None):
    argv = preprocess_argv(list(sys.argv[1:] if argv is None else argv))
    tune_streams()

    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1

    path = os.path.abspath(args.config)
    if not os.path.exists(path):
        eprint("[FAIL] 找不到文件: %s" % path)
        return 2
    try:
        cfg = load_config(path)
    except Exception as exc:  # noqa: BLE001
        eprint("[FAIL] 解析失败（不是合法 plist？）: %s -> %s" % (path, exc))
        return 2

    is_write = args.command in WRITE_COMMANDS
    try:
        changed = COMMANDS[args.command](cfg, path, args)
    except (ValueError, RuntimeError) as exc:
        eprint("[FAIL] %s" % exc)
        return 2

    if not is_write:
        for warning in WARNINGS:
            emit("[WARN] %s" % warning)
        return 0

    if not CHANGES:
        emit("没有需要改的内容（已经是目标状态）。")
    elif not args.quiet:
        emit("")
        emit("=== 变更清单（%d 处）===" % len(CHANGES))
        for change_path, old, new in CHANGES:
            emit("  %-58s %s -> %s" % (change_path, fmt_value(old), fmt_value(new)))
    for warning in WARNINGS:
        emit("[WARN] %s" % warning)

    if not CHANGES:
        return 0

    try:
        bak, verify = commit(cfg, path, dry_run=args.dry_run, backup=not args.no_backup)
    except RuntimeError as exc:
        eprint("[FAIL] %s" % exc)
        return 3

    if args.dry_run:
        emit("")
        emit("dry-run: 以上 %d 处变更未写入（去掉 --dry-run 才会真正改 %s）" % (len(CHANGES), path))
        return 0
    emit("")
    emit("备份: %s" % (os.path.basename(bak) if bak else "(未备份)"))
    emit("写入: %s" % path)
    emit("校验: %s" % verify)
    return 0


if __name__ == "__main__":
    sys.exit(main())
