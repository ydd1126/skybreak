#!/bin/bash
# verify-macos.sh -- 在 macOS 里验收 NullMoth NVIDIA 驱动是否真的装好、是否真的出图
#
# 用途: 装完驱动重启后跑一次，逐项 PASS/FAIL。全部只读，不需要 sudo，
#       不改任何文件，不依赖 python3（用 bash + 系统自带命令）。
#
# 用法:
#   ./verify-macos.sh          # 全量
#   ./verify-macos.sh -q       # 只打印非 PASS 的项和总结
#   ./verify-macos.sh --help
#
# 退出码: 0 = 没有 FAIL；1 = 有 FAIL（把输出整段发出来当证据）
#
# 实测范围: 本机没有 macOS，脚本只做了结构校验（未在真机执行）。

set -u
QUIET=0

usage() {
    cat <<'USAGE'
verify-macos.sh -- NullMoth NVIDIA 驱动验收（macOS 侧）

用法:
  ./verify-macos.sh [-q]

  -q, --quiet   只打印非 PASS 项与总结
  -h, --help    显示本帮助

检查项:
  1. macOS 版本（驱动门禁只认 15 / 26）
  2. 4 个 nullmoth kext 是否在 kmutil 里加载（NVRM/NVAccel/NVRMFB/NVRMAGDC）
  3. /Library/Extensions 里 4 个 kext 是否落地
  4. /Library/NullMoth 版本目录是否与系统版本匹配（15 / 26 分叉）
  5. 驱动版本号与 nvfw 固件文件
  6. system_profiler 里的显卡型号与 Metal 状态
  7. IOAccelerator / ioreg 是否真的挂上加速器
  8. boot-args 是否含 nvfb/nvaccel/amfi 参数、有没有 debug=0x100
  9. SIP（csrutil）状态
 10. 显示器与分辨率
USAGE
}

while [ $# -gt 0 ]; do
    case "$1" in
        -q|--quiet) QUIET=1 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "错误: 未知参数 $1（用 --help 看用法）" >&2; exit 2 ;;
    esac
    shift
done

ok_count=0
fail_count=0
warn_count=0
skip_count=0

check() {
    status="$1"
    name="$2"
    detail="${3:-}"
    case "$status" in
        PASS) ok_count=$((ok_count + 1)) ;;
        FAIL) fail_count=$((fail_count + 1)) ;;
        WARN) warn_count=$((warn_count + 1)) ;;
        *)    skip_count=$((skip_count + 1)) ;;
    esac
    if [ "$QUIET" -eq 1 ] && [ "$status" = "PASS" ]; then
        return 0
    fi
    printf '[%s] %-38s %s\n' "$status" "$name" "$detail"
}

have() {
    command -v "$1" >/dev/null 2>&1
}

printf 'NullMoth NVIDIA 驱动验收（%s）\n' "$(date '+%Y-%m-%d %H:%M:%S')"
printf '主机: %s / macOS %s\n' "$(hostname 2>/dev/null || echo '?')" "$(sw_vers -productVersion 2>/dev/null || echo '?')"
printf '%s\n' "--------------------------------------------------------------------"

# ---------------------------------------------------------------- 1. 系统版本
version="$(sw_vers -productVersion 2>/dev/null || echo '')"
case "$version" in
    26.*) check PASS "macOS 版本（驱动门禁 15/26）" "$version（26 分支）" ;;
    15.*) check WARN "macOS 版本（驱动门禁 15/26）" "$version（15 分支，注意 kexts/15 与 26 不同）" ;;
    "")   check SKIP "macOS 版本（驱动门禁 15/26）" "sw_vers 拿不到" ;;
    *)    check FAIL "macOS 版本（驱动门禁 15/26）" "$version（install.sh 的 case \$MAJ 只放行 15 和 26）" ;;
esac

# ---------------------------------------------------------------- 2. kext 加载
loaded=""
if have kmutil; then
    loaded="$(kmutil showloaded --list-only 2>/dev/null || true)"
elif have kextstat; then
    loaded="$(kextstat 2>/dev/null || true)"
fi

if [ -z "$loaded" ]; then
    check SKIP "kext 加载清单" "kmutil/kextstat 都拿不到（正常 macOS 上不该这样）"
else
    for id in NVRM NVAccel NVRMFB NVRMAGDC; do
        if printf '%s\n' "$loaded" | grep -E "com\.nullmoth\.driver\.${id}([^A-Za-z]|$)" >/dev/null 2>&1; then
            check PASS "kext 已加载: ${id}" "com.nullmoth.driver.${id}"
        else
            check FAIL "kext 已加载: ${id}" "没看到 com.nullmoth.driver.${id}"
        fi
    done
    n_null="$(printf '%s\n' "$loaded" | grep -ci nullmoth 2>/dev/null || true)"
    check PASS "nullmoth 相关加载条数" "${n_null:-0} 条（期望 4）"
fi

# ---------------------------------------------------------------- 3. kext 落地
for kname in NVRM NVRMFB NVAccel NVRMAGDC; do
    kext="/Library/Extensions/${kname}.kext"
    if [ -d "$kext" ]; then
        check PASS "kext 文件存在: ${kname}.kext" "$kext"
    else
        check FAIL "kext 文件存在: ${kname}.kext" "缺 $kext（驱动没装成功）"
    fi
done

# ---------------------------------------------------------------- 4. 版本分叉
if [ -d /Library/NullMoth/kexts/26 ] || [ -d /Library/NullMoth/kexts/15 ]; then
    dirs=""
    [ -d /Library/NullMoth/kexts/26 ] && dirs="kexts/26"
    [ -d /Library/NullMoth/kexts/15 ] && dirs="${dirs:+$dirs }kexts/15"
    case "$version" in
        26.*) if [ -d /Library/NullMoth/kexts/26 ]; then
                  check PASS "驱动版本分叉目录" "$dirs（macOS 26 需要 kexts/26）"
              else
                  check FAIL "驱动版本分叉目录" "只有 15 分支，macOS 26 会挂"
              fi ;;
        15.*) if [ -d /Library/NullMoth/kexts/15 ]; then
                  check PASS "驱动版本分叉目录" "$dirs（macOS 15 需要 kexts/15）"
              else
                  check FAIL "驱动版本分叉目录" "只有 26 分支，macOS 15 会挂"
              fi ;;
        *)    check WARN "驱动版本分叉目录" "$dirs（系统版本未知，无法判断该用哪个）" ;;
    esac
else
    check FAIL "驱动版本分叉目录" "缺 /Library/NullMoth/kexts/{15,26}"
fi

# ---------------------------------------------------------------- 5. 版本与固件
if [ -f /Library/NullMoth/VERSION ]; then
    check PASS "驱动版本号" "$(head -1 /Library/NullMoth/VERSION 2>/dev/null)"
else
    check WARN "驱动版本号" "缺 /Library/NullMoth/VERSION"
fi
if [ -d /Users/Shared/nvfw/nvidia ]; then
    fwdirs="$(ls -1 /Users/Shared/nvfw/nvidia 2>/dev/null | tr '\n' ' ')"
    check PASS "nvfw 固件目录" "$fwdirs"
else
    check FAIL "nvfw 固件目录" "缺 /Users/Shared/nvfw/nvidia（驱动跑不起来）"
fi
for bundle in NVMTLDriver.bundle NVIDIAShared.bundle; do
    if [ -d "/Library/GPUBundles/$bundle" ]; then
        check PASS "GPU bundle: $bundle" "/Library/GPUBundles/$bundle"
    else
        check WARN "GPU bundle: $bundle" "缺 /Library/GPUBundles/$bundle（Metal/视频编解码会缺功能）"
    fi
done

# ---------------------------------------------------------------- 6. 显卡与 Metal
disp="$(system_profiler SPDisplaysDataType 2>/dev/null || true)"
if [ -z "$disp" ]; then
    check SKIP "system_profiler 显卡信息" "拿不到（权限？）"
else
    if printf '%s\n' "$disp" | grep -qi 'RTX 3070'; then
        check PASS "显卡型号" "$(printf '%s\n' "$disp" | grep -i -m1 'RTX 3070' | sed 's/^ *//')"
    else
        chip="$(printf '%s\n' "$disp" | grep -i -m1 'Chipset Model' | sed 's/^ *//')"
        check FAIL "显卡型号" "${chip:-没看到 RTX 3070}（期望 NVIDIA GeForce RTX 3070）"
    fi

    if printf '%s\n' "$disp" | grep -qiE 'Metal(:| Support:).*(Supported|Metal [0-9])'; then
        check PASS "Metal 状态" "$(printf '%s\n' "$disp" | grep -i -m1 'Metal' | sed 's/^ *//')"
    elif printf '%s\n' "$disp" | grep -qi 'Metal'; then
        check WARN "Metal 状态" "$(printf '%s\n' "$disp" | grep -i -m1 'Metal' | sed 's/^ *//')"
    else
        check FAIL "Metal 状态" "system_profiler 里没有 Metal 行（没出图/没挂加速）"
    fi

    if printf '%s\n' "$disp" | grep -qiE 'Resolution|UI Looks like'; then
        check PASS "显示器与分辨率" "$(printf '%s\n' "$disp" | grep -iE 'Resolution|UI Looks like' | head -2 | sed 's/^ *//' | tr '\n' ' ')"
    else
        check WARN "显示器与分辨率" "没读到分辨率行（可能只挂了基本显示）"
    fi
fi

# ---------------------------------------------------------------- 7. IOAccelerator
if have ioreg; then
    accel_lines="$(ioreg -l -w0 -r -c IOAccelerator 2>/dev/null | wc -l | tr -d ' ')"
    if [ "${accel_lines:-0}" -gt 10 ]; then
        check PASS "IOAccelerator 节点" "ioreg 返回 ${accel_lines} 行（加速器已挂）"
    else
        check FAIL "IOAccelerator 节点" "ioreg 只有 ${accel_lines} 行（没挂加速器，等于没驱动）"
    fi
    if ioreg -l 2>/dev/null | grep -qiE 'nullmoth|NVRM|NVAccel'; then
        check PASS "ioreg 里的 nullmoth 痕迹" "找到 NVRM/NVAccel/nullmoth 字样"
    else
        check WARN "ioreg 里的 nullmoth 痕迹" "没找到（图形栈可能还在用基本驱动）"
    fi
else
    check SKIP "IOAccelerator 节点" "没有 ioreg"
fi

# ---------------------------------------------------------------- 8. boot-args
args="$(nvram boot-args 2>/dev/null | sed 's/^boot-args[[:space:]]*//' || true)"
if [ -z "$args" ]; then
    check FAIL "boot-args" "空 / 读不到（驱动需要 nvfb=1 nvaccel=1 amfi=0x80 ...）"
else
    printf '%s\n' "$args" | grep -q 'debug=0x100' \
        && check FAIL "boot-args 里没有 debug=0x100" "含有 debug=0x100（会把内核错误静默进调试器）" \
        || check PASS "boot-args 里没有 debug=0x100" "干净"
    for token in nvfb=1 nvaccel=1 amfi=0x80 amfi_get_out_of_my_way=0x1 ipc_control_port_options=0 keepsyms=1; do
        printf '%s\n' "$args" | grep -q -- "$token" \
            && check PASS "boot-args 含 ${token}" "" \
            || check FAIL "boot-args 含 ${token}" "缺这个参数"
    done
fi

# ---------------------------------------------------------------- 9. SIP
sip="$(csrutil status 2>/dev/null || true)"
case "$sip" in
    *disabled*) check PASS "SIP 状态" "$sip" ;;
    *enabled*)  check WARN "SIP 状态" "$sip（驱动阶段通常需要 0x0FFF 全关）" ;;
    "")         check SKIP "SIP 状态" "csrutil 读不到" ;;
    *)          check WARN "SIP 状态" "$sip" ;;
esac

# ---------------------------------------------------------------- 10. 汇总
printf '%s\n' "--------------------------------------------------------------------"
printf 'PASS=%d  FAIL=%d  WARN=%d  SKIP=%d\n' "$ok_count" "$fail_count" "$warn_count" "$skip_count"
if [ "$fail_count" -gt 0 ]; then
    printf '结论: 有 %d 项 FAIL —— 驱动没装好或没出图，把整段输出发出来当证据。\n' "$fail_count"
    exit 1
fi
if [ "$warn_count" -gt 0 ]; then
    printf '结论: 没有 FAIL，但有 %d 项 WARN，功能可能不完整（Metal/编解码/分辨率）。\n' "$warn_count"
    exit 0
fi
printf '结论: 全部 PASS，驱动工作正常。\n'
exit 0
