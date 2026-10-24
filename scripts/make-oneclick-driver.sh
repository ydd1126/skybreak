#!/bin/bash
# make-oneclick-driver.sh -- 生成「一键安装 NVIDIA 驱动.command」到 U 盘
#
# 为什么要有这个生成器: 实战里那个 .command 是手写死的 /Volumes/1401，
#   U 盘卷名一变（比如变成 1401-1 或中文名）就找不到了。这个生成器把
#   U 盘路径和驱动版本当成参数，产出仍然是纯 shell、双击即用、不依赖 python3。
#
# 用法（在 macOS 上跑，U 盘插好）:
#   ./make-oneclick-driver.sh                          # 自动探测 U 盘与最新驱动版本
#   ./make-oneclick-driver.sh --usb /Volumes/1401 --version 2.3.7
#   ./make-oneclick-driver.sh --out /Volumes/1401/一键安装显卡驱动.command --force
#   ./make-oneclick-driver.sh --dry-run                # 只打印将要生成的脚本，不写文件
#
# 生成的脚本做的事（与 2026-10-20 实战成功的那份逻辑一致）:
#   备份 config -> 屏蔽 IONDRVSupport -> ResizeGpuBars=13 -> ResizeAppleGpuBars=-1
#   -> 解压驱动包 -> shasum 校验 -> sudo install.sh -> 提示重启
#
# 实测范围: 本机没有 bash/macOS，生成器与产物只做了结构校验与 PlistBuddy 语义模拟，
#           未在真实 macOS 上执行过（详见 README「实测状态」）。

set -u

USB=""
VERSION=""
OUT=""
FORCE=0
DRY=0

usage() {
    cat <<'USAGE'
make-oneclick-driver.sh -- 生成可双击的一键装驱动 .command

用法:
  ./make-oneclick-driver.sh [--usb <U盘挂载点>] [--version <驱动版本>]
                            [--out <输出文件>] [--force] [--dry-run]

  --usb <路径>      U 盘挂载点，例如 /Volumes/1401（默认探测含 EFI/OC 的卷）
  --version <版本>  驱动版本，例如 2.3.7（默认取 NullMoth 里最高的 tar.gz 版本）
  --out <文件>      输出路径（默认 <U盘>/一键安装显卡驱动-<版本>.command）
  --force           覆盖已存在的输出文件
  --dry-run         只把生成的脚本打印到屏幕，不写盘
  -h, --help        显示本帮助

前置条件（U 盘上要有）:
  <U盘>/EFI/OC/config.plist
  <U盘>/NullMoth/nullmoth-nvidia-<版本>.tar.gz
  <U盘>/NullMoth/SHA256SUMS-<版本>.txt        （可选，有就先校验包本身）
USAGE
}

while [ $# -gt 0 ]; do
    case "$1" in
        --usb)     [ $# -ge 2 ] || { echo "错误: --usb 需要路径" >&2; exit 2; }; USB="$2"; shift 2 ;;
        --version) [ $# -ge 2 ] || { echo "错误: --version 需要版本号" >&2; exit 2; }; VERSION="$2"; shift 2 ;;
        --out)     [ $# -ge 2 ] || { echo "错误: --out 需要文件路径" >&2; exit 2; }; OUT="$2"; shift 2 ;;
        --force)   FORCE=1; shift ;;
        --dry-run) DRY=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "错误: 未知参数 $1（用 --help 看用法）" >&2; exit 2 ;;
    esac
done

have() {
    command -v "$1" >/dev/null 2>&1
}

find_usb() {
    for vol in /Volumes/*; do
        if [ -f "$vol/EFI/OC/config.plist" ]; then
            printf '%s\n' "$vol"
            return 0
        fi
    done
    return 1
}

# 取 NullMoth 里版本号最高的 nullmoth-nvidia-<ver>.tar.gz
detect_version() {
    root="$1/NullMoth"
    [ -d "$root" ] || return 1
    ls -1 "$root" 2>/dev/null \
        | sed -n 's/^nullmoth-nvidia-\([0-9][0-9][0-9.]*\)\.tar\.gz$/\1/p' \
        | sort -t. -k1,1n -k2,2n -k3,3n -k4,4n \
        | tail -1
}

if [ -z "$USB" ]; then
    USB="$(find_usb || true)"
    if [ -z "$USB" ]; then
        echo "错误: 没探测到含 EFI/OC/config.plist 的卷，用 --usb /Volumes/xxx 指定" >&2
        exit 3
    fi
fi
if [ ! -f "$USB/EFI/OC/config.plist" ]; then
    echo "错误: $USB/EFI/OC/config.plist 不存在（U 盘路径不对？）" >&2
    exit 3
fi

if [ -z "$VERSION" ]; then
    VERSION="$(detect_version "$USB" || true)"
    if [ -z "$VERSION" ]; then
        echo "错误: $USB/NullMoth 里没有 nullmoth-nvidia-*.tar.gz，用 --version 指定" >&2
        exit 3
    fi
fi
if ! printf '%s' "$VERSION" | grep -Eq '^[0-9]+(\.[0-9]+){1,3}$'; then
    echo "错误: 版本号格式不对: $VERSION（例: 2.3.7）" >&2
    exit 3
fi
if [ ! -f "$USB/NullMoth/nullmoth-nvidia-$VERSION.tar.gz" ]; then
    echo "错误: 找不到 $USB/NullMoth/nullmoth-nvidia-$VERSION.tar.gz" >&2
    echo "      （可选版本: $(ls -1 "$USB/NullMoth" 2>/dev/null | grep -c 'nullmoth-nvidia-' || true) 个 tar.gz）" >&2
    exit 3
fi

if [ -z "$OUT" ]; then
    OUT="$USB/一键安装显卡驱动-$VERSION.command"
fi
if [ -e "$OUT" ] && [ "$FORCE" -eq 0 ] && [ "$DRY" -eq 0 ]; then
    echo "错误: $OUT 已存在（要覆盖加 --force）" >&2
    exit 4
fi

# ------------------------------------------------------------------ 模板 ----
# 用带引号的 heredoc：这里所有 $ / $( ) / 反引号都原样保留给生成出来的脚本。
TPL="$(cat <<'ONECLICK_TEMPLATE'
#!/bin/bash
# 一键：安装 NullMoth NVIDIA 驱动 @@VERSION@@ + 自动改好 OpenCore 配置
#
# 由 make-oneclick-driver.sh 生成。做的事（顺序与源码都不依赖 python3）:
#   1. 备份 EFI/OC/config.plist（带时间戳 + 固定 config.plist.bak）
#   2. PlistBuddy 改驱动阶段配置：屏蔽 IONDRVSupport / ResizeGpuBars=13 /
#      ResizeAppleGpuBars=-1，并回读自检
#   3. 解压 nullmoth-nvidia-@@VERSION@@.tar.gz 到 /tmp/nm，shasum -a 256 -c 校验
#   4. sudo ./install.sh
#   5. 提示重启，10 秒后自动 restart
#
# 用法: 双击本文件；或终端里 bash 本文件
set -u

USB_DEFAULT="@@USB@@"
NV_VERSION="@@VERSION@@"
PB=/usr/libexec/PlistBuddy
TARGZ_NAME="nullmoth-nvidia-${NV_VERSION}.tar.gz"
WORK=/tmp/nm

# 想临时指到别的卷: NM_USB=/Volumes/其他名 bash 本文件
USB="${NM_USB:-$USB_DEFAULT}"

echo "======================================================"
echo "  NullMoth NVIDIA 驱动 ${NV_VERSION} 一键安装"
echo "======================================================"

# --- 0) 定位 U 盘（卷名变了也能自适应）
if [ ! -f "$USB/EFI/OC/config.plist" ]; then
    found=""
    for vol in /Volumes/*; do
        if [ -f "$vol/EFI/OC/config.plist" ]; then
            found="$vol"
            break
        fi
    done
    if [ -n "$found" ]; then
        echo "  自动探测到 U 盘: $found"
        USB="$found"
    fi
fi
CFG="$USB/EFI/OC/config.plist"
TARGZ="$USB/NullMoth/$TARGZ_NAME"

if [ ! -f "$CFG" ]; then
    echo "错误：找不到 $CFG"
    echo "请确认 U 盘已插好（生成时用的路径是 $USB_DEFAULT）"
    echo "也可以手动指定: NM_USB=/Volumes/xxx bash \"$0\""
    read -n1 -r _ 2>/dev/null
    exit 1
fi
if [ ! -x "$PB" ]; then
    echo "错误：找不到 $PB（这不是 macOS 的终端？）"
    read -n1 -r _ 2>/dev/null
    exit 1
fi
if [ ! -f "$TARGZ" ]; then
    echo "错误：找不到驱动包 $TARGZ"
    read -n1 -r _ 2>/dev/null
    exit 1
fi

# --- 1) 备份配置
echo ""
echo "=== 第 1 步：备份 OpenCore 配置 ==="
STAMP="$(date +%Y%m%d-%H%M%S)"
if cp "$CFG" "$CFG.bak-$STAMP"; then
    echo "  已备份 -> EFI/OC/config.plist.bak-$STAMP"
else
    echo "错误：备份失败（U 盘写保护？）"
    read -n1 -r _
    exit 1
fi
# 「一键回滚.command」找的是固定名，顺手也更新一份
cp "$CFG" "$USB/EFI/OC/config.plist.bak" && echo "  同时更新 EFI/OC/config.plist.bak（回滚用）"

# --- 2) 驱动阶段配置
echo ""
echo "=== 第 2 步：写入驱动阶段配置（PlistBuddy，不用 python3） ==="
$PB -c "Print :Kernel:Block" "$CFG" >/dev/null 2>&1 || $PB -c "Add :Kernel:Block array" "$CFG"

has="$($PB -c "Print :Kernel:Block" "$CFG" 2>/dev/null | grep -c "com.apple.iokit.IONDRVSupport")"
if [ "${has:-0}" -eq 0 ]; then
    idx="$($PB -c "Print :Kernel:Block" "$CFG" 2>/dev/null | grep -c "Dict {")"
    $PB -c "Add :Kernel:Block:$idx dict" "$CFG"
    $PB -c "Add :Kernel:Block:$idx:Arch string Any" "$CFG"
    $PB -c "Add :Kernel:Block:$idx:Comment string NullMoth driver owns the display" "$CFG"
    $PB -c "Add :Kernel:Block:$idx:Enabled bool true" "$CFG"
    $PB -c "Add :Kernel:Block:$idx:Identifier string com.apple.iokit.IONDRVSupport" "$CFG"
    $PB -c "Add :Kernel:Block:$idx:Strategy string Exclude" "$CFG"
    echo "  已屏蔽 IONDRVSupport（Kernel->Block 第 $idx 条）"
else
    echo "  IONDRVSupport 已存在，跳过"
fi

$PB -c "Set :Booter:Quirks:ResizeAppleGpuBars -1" "$CFG" && echo "  ResizeAppleGpuBars = -1"
$PB -c "Set :UEFI:Quirks:ResizeGpuBars 13" "$CFG" && echo "  ResizeGpuBars = 13（8GB BAR）"

echo "  回读自检:"
echo "    IONDRVSupport 屏蔽条数 = $($PB -c "Print :Kernel:Block" "$CFG" 2>/dev/null | grep -c "com.apple.iokit.IONDRVSupport")"
echo "    ResizeAppleGpuBars     = $($PB -c "Print :Booter:Quirks:ResizeAppleGpuBars" "$CFG" 2>/dev/null)"
echo "    ResizeGpuBars          = $($PB -c "Print :UEFI:Quirks:ResizeGpuBars" "$CFG" 2>/dev/null)"

# --- 3) 校验并解压驱动包
echo ""
echo "=== 第 3 步：校验并解压驱动包 ==="
SUMFILE="$USB/NullMoth/SHA256SUMS-${NV_VERSION}.txt"
if [ -f "$SUMFILE" ]; then
    echo "  先校验压缩包本身（对着 $(basename "$SUMFILE")）"
    if ( cd "$USB/NullMoth" && shasum -a 256 -c "$(basename "$SUMFILE")" ); then
        echo "  压缩包哈希 OK"
    else
        echo "  警告：压缩包哈希不一致！可能被重新打包过"
        echo "  按 Ctrl+C 中止；或者回车继续（风险自负）"
        read -n1 -r _
    fi
else
    echo "  没有 $(basename "$SUMFILE")，跳过压缩包哈希（下面还有逐文件校验）"
fi

rm -rf "$WORK"
mkdir -p "$WORK" || exit 1
if ! tar -xzf "$TARGZ" -C "$WORK"; then
    echo "错误：解压失败（包坏了？）"
    read -n1 -r _
    exit 1
fi
PKG="$WORK/pkgroot"
if [ ! -d "$PKG" ]; then
    echo "错误：解压后没有 pkgroot/（包结构不对）"
    read -n1 -r _
    exit 1
fi
cd "$PKG" || exit 1
if [ ! -f SHA256SUMS ]; then
    echo "错误：pkgroot 里没有 SHA256SUMS"
    read -n1 -r _
    exit 1
fi
shasum -a 256 -c SHA256SUMS > "$WORK/verify.txt" 2>&1
ok="$(grep -c "OK$" "$WORK/verify.txt")"
bad="$(grep -vc "OK$" "$WORK/verify.txt")"
echo "  逐文件校验：${ok:-0} 个 OK，${bad:-0} 个异常"
if [ "${bad:-0}" -gt 0 ]; then
    echo "  异常文件："
    grep -v "OK$" "$WORK/verify.txt" | head -20
    echo "  已中止 —— 校验不过的驱动不要装"
    read -n1 -r _
    exit 1
fi

# --- 4) 安装
echo ""
echo "=== 第 4 步：安装驱动（需要管理员密码） ==="
echo "  下面会要求输入密码，输入时屏幕不显示，输完回车"
sudo ./install.sh
rc=$?
if [ "$rc" -ne 0 ]; then
    echo ""
    echo "安装脚本退出码 $rc —— 把上面的报错复制出来（或拍照）"
    read -n1 -r _
    exit "$rc"
fi

# --- 5) 重启
echo ""
echo "======================================================"
echo "  安装完成！10 秒后自动重启"
echo "  重启后如果提示「系统扩展被阻止」："
echo "    系统设置 -> 隐私与安全性 -> 拉到底 -> 点「允许」-> 再重启一次"
echo "  验收命令:"
echo "    kmutil showloaded --list-only | grep nullmoth   （应出现 4 行）"
echo "    ./verify-macos.sh                              （U 盘上的验收脚本）"
echo "======================================================"
read -t 10 -n 1 -r _ 2>/dev/null || true
sudo shutdown -r now
ONECLICK_TEMPLATE
)"

# 占位符替换：用 bash 原生替换，避免 sed 对路径里的特殊字符做手脚
TPL="${TPL//@@USB@@/$USB}"
TPL="${TPL//@@VERSION@@/$VERSION}"

if [ "$DRY" -eq 1 ]; then
    printf '%s\n' "$TPL"
    exit 0
fi

if ! printf '%s\n' "$TPL" >"$OUT"; then
    echo "错误: 写不了 $OUT" >&2
    exit 5
fi
chmod +x "$OUT" 2>/dev/null || true

# ------------------------------------------------------------------ 自检 ----
fail=0
first_line="$(head -1 "$OUT" 2>/dev/null)"
case "$first_line" in
    '#!/bin/bash') : ;;
    *) echo "[FAIL] 第一行不是 #!/bin/bash: $first_line" >&2; fail=1 ;;
esac
if LC_ALL=C grep -q "$(printf '\r')" "$OUT" 2>/dev/null; then
    echo "[FAIL] 输出里有 CR 字符（.command 必须纯 LF）" >&2
    fail=1
fi
if head -c 3 "$OUT" 2>/dev/null | od -An -tx1 | grep -q 'ef bb bf'; then
    echo "[FAIL] 输出带 UTF-8 BOM" >&2
    fail=1
fi
if have bash; then
    if bash -n "$OUT" 2>/dev/null; then
        echo "[ok] bash -n 语法检查通过"
    else
        echo "[FAIL] bash -n 语法检查失败:" >&2
        bash -n "$OUT" >&2 2>&1 || true
        fail=1
    fi
else
    echo "[warn] 没有 bash，跳过 bash -n 语法检查"
fi
if [ -f "$OUT" ] && [ ! -x "$OUT" ]; then
    echo "[warn] $OUT 没有可执行位（FAT32/exFAT 上正常；双击不了就用: bash \"$OUT\"）"
fi

if [ "$fail" -ne 0 ]; then
    exit 6
fi

echo ""
echo "生成成功: $OUT"
ls -l "$OUT" 2>/dev/null
echo ""
echo "下一步:"
echo "  1) 拔 U 盘插到目标机，进 macOS 桌面"
echo "  2) 双击 $(basename "$OUT")  （双击不了就: bash \"$OUT\"）"
echo "  3) 装完重启，再跑 verify-macos.sh 验收"
