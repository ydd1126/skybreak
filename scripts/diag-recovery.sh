#!/bin/sh
# diag-recovery.sh -- macOS 恢复环境 / 安装器终端里的诊断收集器
#
# 用途: 系统起不来、卡内核、装驱动后黑屏时，在「恢复模式终端」里跑一次，
#       把版本号、KernelCollections、Extensions、NullMoth 驱动残留、日志尾巴、
#       nvram、diskutil、OpenCore 配置快照、opencore-*.txt 关键标记
#       全部写进含 EFI/OC 的那个 U 盘的 diag.txt（不需要写死 /Volumes/1401）。
#
# 用法:
#   sh diag-recovery.sh                    # 自动找含 EFI/OC 的卷
#   sh diag-recovery.sh --usb /Volumes/1401
#   sh diag-recovery.sh --out /tmp/diag.txt
#
# 实测范围: 本机（Windows）没有 sh/bash，只做了结构校验与路径逻辑核对，
#           未在真实 macOS 恢复环境执行过（详见 README「实测状态」）。

set -u

OUT=""
TARGET_USB=""

usage() {
    cat <<'USAGE'
diag-recovery.sh -- 收集 macOS 恢复环境里的诊断信息

用法:
  sh diag-recovery.sh [--usb <U盘挂载点>] [--out <输出文件>]

  --usb <路径>   指定含 EFI/OC 的卷（默认自动探测 /Volumes/*）
  --out <文件>   指定 diag.txt 的输出路径（默认写到 U 盘根目录）
  -h, --help     显示本帮助

输出内容:
  环境/磁盘/每个 macOS 卷的版本与关键目录/安装器残留/nvram/SIP/
  OpenCore 配置快照/opencore-*.txt 关键标记/日志尾巴
USAGE
}

while [ $# -gt 0 ]; do
    case "$1" in
        --usb)
            [ $# -ge 2 ] || { echo "错误: --usb 需要一个路径" >&2; exit 2; }
            TARGET_USB="$2"
            shift 2
            ;;
        --out)
            [ $# -ge 2 ] || { echo "错误: --out 需要一个文件路径" >&2; exit 2; }
            OUT="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "错误: 未知参数 $1（用 --help 看用法）" >&2
            exit 2
            ;;
    esac
done

have() {
    command -v "$1" >/dev/null 2>&1
}

# 找含 EFI/OC 的卷；名字带空格/中文也安全（路径扩展不会被再次分词）
find_efi_volume() {
    for vol in /Volumes/*; do
        if [ -d "$vol/EFI/OC" ] && [ -f "$vol/EFI/OC/config.plist" ]; then
            printf '%s\n' "$vol"
            return 0
        fi
    done
    for vol in /Volumes/*; do
        if [ -d "$vol/EFI" ]; then
            printf '%s\n' "$vol"
            return 0
        fi
    done
    return 1
}

if [ -z "$TARGET_USB" ]; then
    TARGET_USB="$(find_efi_volume || true)"
fi

if [ -n "$TARGET_USB" ] && [ -d "$TARGET_USB" ]; then
    if [ -z "$OUT" ]; then
        OUT="$TARGET_USB/diag.txt"
    fi
else
    if [ -z "$OUT" ]; then
        OUT="/tmp/diag.txt"
    fi
fi

# 写不了就退到 /tmp，别让整个脚本白跑
if ! ( : > "$OUT" ) 2>/dev/null; then
    echo "警告: $OUT 不可写，改写到 /tmp/diag.txt" >&2
    OUT="/tmp/diag.txt"
    : > "$OUT" 2>/dev/null || { echo "错误: /tmp 也写不了" >&2; exit 3; }
fi

log() {
    printf '%s\n' "$*" >>"$OUT" 2>/dev/null
}

say() {
    printf '%s\n' "$*"
    log "$*"
}

sec() {
    say ""
    say "===== $* ====="
}

# 跑命令，输出进 diag.txt；退出码非 0/1 时记一笔（1 通常是 grep 没匹配，不感兴趣）
run() {
    log "\$ $*"
    "$@" >>"$OUT" 2>&1
    rc=$?
    if [ "$rc" -ne 0 ] && [ "$rc" -ne 1 ]; then
        log "  (退出码 $rc)"
    fi
    return 0
}

# 需要管道/重定向的 shell 片段
runsh() {
    log "\$ $*"
    sh -c "$*" >>"$OUT" 2>&1
    rc=$?
    if [ "$rc" -ne 0 ] && [ "$rc" -ne 1 ]; then
        log "  (退出码 $rc)"
    fi
    return 0
}

# PlistBuddy 读一个键（读不到就给 "(读不到)"）
pb() {
    if [ -x /usr/libexec/PlistBuddy ] && [ -f "$1" ]; then
        /usr/libexec/PlistBuddy -c "Print $2" "$1" 2>/dev/null || printf '%s\n' "(读不到)"
    else
        printf '%s\n' "(没有 PlistBuddy 或文件不存在)"
    fi
}

say "diag-recovery.sh -- macOS 恢复环境诊断"
say "运行时间   : $(date)"
say "U 盘根目录 : ${TARGET_USB:-(未探测到，写 /tmp)}"
say "输出文件   : $OUT"
say "注意       : 这个文件里有序列号和 NVRAM 内容，贴到公开场合前先脱敏"

sec "1. 环境"
run uname -a
run sw_vers
if have csrutil; then
    run csrutil status
else
    say "csrutil: 不存在（恢复环境里应该有的，注意确认）"
fi
if have system_profiler; then
    runsh "system_profiler SPHardwareDataType 2>/dev/null | head -20"
fi

sec "2. 卷与磁盘"
runsh "ls -1 /Volumes"
run diskutil list

sec "3. 每个 macOS 卷的体检"
for vol in /Volumes/*; do
    [ -d "$vol/System/Library/CoreServices" ] || continue
    say ""
    say "--- 卷: $vol ---"
    sv="$vol/System/Library/CoreServices/SystemVersion.plist"
    say "ProductVersion      = $(pb "$sv" ':ProductVersion')"
    say "ProductBuildVersion = $(pb "$sv" ':ProductBuildVersion')"

    say "--- $vol/Library/KernelCollections ---"
    runsh "ls -l \"$vol/Library/KernelCollections\" 2>/dev/null | head -40"

    say "--- $vol/Library/Extensions（第三方 kext 一眼可见）---"
    runsh "ls -1 \"$vol/Library/Extensions\" 2>/dev/null | head -120"

    say "--- $vol/Library/NullMoth（NVIDIA 驱动是否落地）---"
    runsh "ls -1 \"$vol/Library/NullMoth\" 2>/dev/null"
    runsh "ls -1 \"$vol/Library/NullMoth/kexts\" 2>/dev/null"

    say "--- $vol/Library/GPUBundles ---"
    runsh "ls -1 \"$vol/Library/GPUBundles\" 2>/dev/null"

    say "--- $vol/var/log/system.log 最后 150 行 ---"
    runsh "tail -n 150 \"$vol/var/log/system.log\" 2>/dev/null"

    say "--- $vol/var/log/install.log 最后 150 行 ---"
    runsh "tail -n 150 \"$vol/var/log/install.log\" 2>/dev/null"

    say "--- $vol/var/log 里的关键日志文件 ---"
    runsh "ls -1 \"$vol/var/log\" 2>/dev/null | head -60"
done

sec "4. 安装器残留（安装卡住时看这里）"
for vol in /Volumes/*; do
    [ -d "$vol" ] || continue
    if [ -d "$vol/macOS Install Data" ]; then
        say "存在: $vol/macOS Install Data"
        runsh "ls -1 \"$vol/macOS Install Data\" 2>/dev/null | head -40"
        runsh "ls -1 \"$vol/macOS Install Data/Locked Files\" 2>/dev/null | head -20"
    fi
done
say "(以上没输出就没有残留)"

sec "5. NVRAM 与引导相关变量"
if have nvram; then
    runsh "nvram -p 2>/dev/null | grep -E 'boot-args|csr-active-config|prev-lang|run-efi-updater' | head -20"
    say "--- nvram -p 全量（前 80 行）---"
    runsh "nvram -p 2>/dev/null | head -80"
else
    say "nvram: 命令不存在"
fi

sec "6. OpenCore 配置快照（U 盘上的 config.plist）"
cfg="${TARGET_USB}/EFI/OC/config.plist"
if [ -n "$TARGET_USB" ] && [ -f "$cfg" ]; then
    say "配置: $cfg"
    say "Kernel:Quirks:ProvideCurrentCpuInfo     = $(pb "$cfg" ':Kernel:Quirks:ProvideCurrentCpuInfo')"
    say "Kernel:Quirks:DisableIoMapper           = $(pb "$cfg" ':Kernel:Quirks:DisableIoMapper')"
    say "Kernel:Quirks:LapicKernelPanic          = $(pb "$cfg" ':Kernel:Quirks:LapicKernelPanic')"
    say "Booter:Quirks:DevirtualiseMmio          = $(pb "$cfg" ':Booter:Quirks:DevirtualiseMmio')"
    say "Booter:Quirks:ResizeAppleGpuBars        = $(pb "$cfg" ':Booter:Quirks:ResizeAppleGpuBars')"
    say "UEFI:Quirks:ResizeGpuBars               = $(pb "$cfg" ':UEFI:Quirks:ResizeGpuBars')"
    say "Misc:Security:ScanPolicy                = $(pb "$cfg" ':Misc:Security:ScanPolicy')"
    say "Misc:Security:SecureBootModel           = $(pb "$cfg" ':Misc:Security:SecureBootModel')"
    say "PlatformInfo:Generic:SystemProductName  = $(pb "$cfg" ':PlatformInfo:Generic:SystemProductName')"
    say "boot-args    = $(pb "$cfg" ':NVRAM:Add:7C436110-AB2A-4BBB-A880-FE41995C9F82:boot-args')"
    say "csr-active-config = $(pb "$cfg" ':NVRAM:Add:7C436110-AB2A-4BBB-A880-FE41995C9F82:csr-active-config')"
    say "NVRAM Delete 里有没有 boot-args:"
    runsh "/usr/libexec/PlistBuddy -c 'Print :NVRAM:Delete:7C436110-AB2A-4BBB-A880-FE41995C9F82' \"$cfg\" 2>/dev/null"
    say "Kernel:Block 条数 = $(pb "$cfg" ':Kernel:Block' | grep -c 'Dict {' || true)"
    say "Kernel:Patch 条数 = $(pb "$cfg" ':Kernel:Patch' | grep -c 'Dict {' || true)"
    say "EFI/OC 目录里的备份:"
    runsh "ls -l \"${TARGET_USB}/EFI/OC\" 2>/dev/null | grep -E 'config.plist' | head -20"
else
    say "没找到 $cfg（U 盘没插好？）"
fi

sec "7. opencore-*.txt 引导日志关键标记"
if [ -n "$TARGET_USB" ] && [ -d "$TARGET_USB" ]; then
    runsh "ls -lt \"${TARGET_USB}\" 2>/dev/null | grep 'opencore-' | head -5"
    newest="$(ls -t "${TARGET_USB}"/opencore-*.txt 2>/dev/null | head -1)"
    if [ -n "$newest" ] && [ -f "$newest" ]; then
        say "最新日志: $newest"
        say "--- 关键标记出现次数 ---"
        for pat in 'EB\|LOG:EXITBS:START' 'AHCI.*\[HBA\] start' 'non-monotonic' 'OCA: Deleting table DMAR' 'Deleting NVRAM.*boot-args' 'panic' 'OC: Failed' 'System is shutting down'; do
            count="$(grep -c -E "$pat" "$newest" 2>/dev/null || true)"
            say "  $(printf '%-34s' "$pat") = ${count:-0}"
        done
        say "--- 最新日志最后 120 行 ---"
        runsh "tail -n 120 \"$newest\" 2>/dev/null"
        say "--- 最新日志里所有 OCA/OCB/OC: 错误行（前 60 行）---"
        runsh "grep -E 'OCA:|OCB:|OC: ' \"$newest\" 2>/dev/null | grep -iE 'fail|error|unsupported|invalid' | head -60"
    else
        say "U 盘根目录没有 opencore-*.txt —— 说明这次启动没走 OpenCore，或文件日志没开（Misc->Debug->Target 要有 0x40）"
    fi
else
    say "U 盘根目录未定位，跳过引导日志"
fi

sec "8. 完成"
say "完成时间: $(date)"
say "把 $OUT 复制到 Windows 侧，用 inspect-config.py / 文本编辑器一起看。"
say "提示: 恢复环境里想直接改 U 盘配置，用 /usr/libexec/PlistBuddy，别依赖 python3（恢复环境没有）。"

printf '\n已写入: %s (%s 字节)\n' "$OUT" "$(wc -c <"$OUT" 2>/dev/null | tr -d ' ')"
printf '把 %s 带回 Windows 侧分析。\n' "$OUT"
exit 0
