# 开天 Skybreak · 冷启动执行手册
## 给「换一个会话」的 AI：读完这份就带用户装 macOS 26

> **这份文件是自包含的。** 你不需要读任何历史会话、不需要联网查资料、
> 不需要用户解释背景。按 §1 → §8 顺序执行即可。
>
> 目标机器：**Intel Core Ultra 5 245K（Arrow Lake-S）+ 技嘉 B860M POWER + NVIDIA RTX 3070**
> 目标系统：**macOS 26 Tahoe**，与 Windows 11 双系统共存
> 已验证结果：**macOS 26.7.1 (25G241) 装完并进入桌面**（2026-10-20）

## ⚡ 30 秒速览（赶时间只看这段）

| 步 | 谁做 | 干什么 | 耗时 |
|---|---|---|---|
| 1 | AI | 跑 `install-macos26.ps1 -DryRun` → 复用 M:\EFI + 30 项体检 | 40 秒 |
| 2 | 用户 | BIOS 九项（VT-d 关 / HT 关 / E核0 / ReBAR 开 / CSM 关 / SecureBoot 关） | 5 分钟 |
| 3 | 用户 | F12 选 U 盘 → 抹整块盘 APFS → 装 macOS | 30 分钟 |
| 4 | 用户 | 开箱向导（跳过 Apple ID） | 5 分钟 |
| 5 | 用户 | 双击 U 盘 `一键安装显卡驱动.command` → 允许扩展 → 重启两次 | 15 分钟 |
| 6 | AI | 跑 `kmutil` + `system_profiler` 验收 | 2 分钟 |

**总计约 1 小时。** 如果你只记得一句话：**先关 VT-d，再关超线程和 E 核，其余照 §9 抄。**

---

# 第一部分 · 你的行为协议（先读这 8 条）

1. **先读 §0 环境坐标和 §9 数值速查**，再动手。不要凭记忆猜路径、猜参数。
2. **每一步都要给用户"可判定的判据"**：不是"看起来成功了"，而是"日志出现 X 行 / 命令返回 Y"。
3. **一次只改一个变量**。两次重启之间只动一个 BIOS 项或一个 config 键。批量改 = 出问题无法归因。
4. **不可逆操作前必须让用户确认**：写盘前让用户输入 U 盘序列号；改 config 前先备份。
5. **能跑命令的绝不让人点 GUI**。但 BIOS 9 项、装机 3 击、开箱向导这三件事**必须人做**，你要原样告诉用户，不要含糊。
6. **每步耗时要报给用户**（§8 有时间预算），让他知道还要多久。
7. **失败不要慌**，按 §7 的症状表定位。表里没有的，收集 `opencore-*.txt` 再判断。
8. **绝不能说的话**：
   - 没跑 `kmutil`/`system_profiler` 就说"显卡已驱动/已出图"
   - 体检 FAIL 就让用户写盘
   - "应该可以""大概率没问题"（要么给判据，要么说不知道）

---

# 第二部分 · 环境坐标（这台机器的实测值）

## §0.1 硬件

| 项 | 值 |
|---|---|
| 主板 | Gigabyte **B860M POWER**（Intel B860 / LGA1851），BIOS AMI **F10** |
| CPU | **Intel Core Ultra 5 245K**（Arrow Lake-S，14 核 = 6P+8E，L3 24 MB） |
| 独显 | **NVIDIA RTX 3070 8GB**，PCI `10DE:2488`，SUBSYS `404E1458`（读作 `1458:404E`，PNP 串里是反序） |
| 核显 | Intel `8086:7D67`（Arrow Lake，macOS 无驱动，只当固件帧缓冲） |
| 内存 | 16 GB DDR5-6000 ×1（单通道） |
| 网卡 | Realtek RTL8125 2.5GbE `10EC:8125`（无无线网卡） |
| 声卡 | Realtek ALC897 `10EC:0897`（**本手册不含音频方案**，需另做 AppleALC） |
| 显示器 | Philips 237E7 1920×1080，接 RTX 3070 的 HDMI |

## §0.2 磁盘（**认盘只认序列号，绝不认盘符**）

| 盘号 | 型号 | 接口 | 序列号 | 用途 |
|---|---|---|---|---|
| 3 | SAMSUNG SM841 256G | SATA | `SERIAL_DISK3_REDACTED` | **Windows 系统盘，绝对不动** |
| 4 | ADATA SU800 256G | SATA | `SERIAL_DISK4_REDACTED` | **macOS 系统盘**（APFS） |
| 5 | APPLE SSD SM0512F 500G | SATA | `SERIAL_DISK5_REDACTED` | 418 GB 数据，不动 |
| 6 | U 盘 59.5G | USB | `SERIAL_USB_REDACTED` | **OpenCore 安装盘** |

## §0.3 已就位的工具与文件

| 东西 | 路径 |
|---|---|
| 1401 引擎（可信版本） | `G:\1401-2.3.3\1401\engine`（python 在 `engine\python\python.exe`） |
| 1401 + 驱动最新包 | `G:\1401-new\` |
| 驱动包（2.3.7） | `M:\NullMoth\nullmoth-nvidia-2.3.7.tar.gz`（SHA256 已校验） |
| 驱动 Mac app（2.3.6） | `M:\NullMoth\1401-Mac-2.3.6.zip` |
| **已验证可启动的 EFI** | `M:\EFI`（就是它启动的 macOS，**优先复用它，零下载**） |
| skill（含全部知识库与脚本） | `C:\Users\<USER>\.dsh\skills\hackintosh-opencore\` |
| 一键脚本 | `...\scripts\install-macos26.ps1` |
| 配置体检 | `...\scripts\inspect-config.py` |
| 配置修补 | `...\scripts\patch-config.py` |
| 装机报告与日志 | `C:\Users\<USER>\Documents\macOS-install-kit\` |
| 所有配置备份 | `C:\<WORK>\config-backup-*.plist` |

## §0.4 当前 BIOS 状态（已经为 macOS 调好）

```
VT-d = Disabled        Hyper-Threading = Disabled    Active E-Cores = 0
Re-Size BAR = Enabled  Above 4G = Enabled            CSM = Disabled
Secure Boot = Disabled Fast Boot = Disabled          SATA Mode = AHCI
```

---

# 第三部分 · 执行流程

## §1. 环境预检（1 分钟，5 条命令）

跑完把结果对一遍，缺什么补什么。**任何一条不对，先修再往下。**

```powershell
# 1) 硬件没变？（CPU 名、显卡 PCI ID）
Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors
Get-CimInstance Win32_VideoController | Select-Object Name,PNPDeviceID
#   期望：Ultra 5 245K / 6 核 6 线程（说明 HT+E核已关，正常）
#   期望：10DE&DEV_2488&SUBSYS_404E1458

# 2) EFI 与工具还在？
Test-Path 'M:\EFI\OC\config.plist'
Test-Path 'G:\1401-2.3.3\1401\engine\python\python.exe'
Test-Path 'M:\NullMoth\nullmoth-nvidia-2.3.7.tar.gz'

# 3) 目标 macOS 盘是否还是 APFS？
Get-Partition -DiskNumber 4 | Select-Object PartitionNumber,@{n='GB';e={[math]::Round($_.Size/1GB,2)}},GptType
#   期望：分区 2 的 GptType = {7c3457ef-0000-11aa-aa11-00306543ecac}

# 4) U 盘序列号（写盘要用）
Get-Disk | Where-Object BusType -eq USB | Select-Object Number,FriendlyName,SerialNumber,@{n='GB';e={[math]::Round($_.Size/1GB,1)}}

# 5) 代理状态（Clash 会掐断苹果服务器 TLS）
Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' | Select-Object ProxyEnable,ProxyServer
Get-Process | Where-Object { $_.ProcessName -match 'clash|verge|mihomo|sing-box' } | Select-Object ProcessName
Get-NetAdapter | Where-Object { $_.InterfaceDescription -match 'TAP|TUN|Wintun' } | Select-Object Name,Status
```

**判据**：1–4 全部符合；第 5 项若 `ProxyEnable=1` 或有 TUN 网卡 → 先让用户关掉/切直连。

---

## §2. 做安装盘（最快 5 分钟，最慢 40 分钟）

### 路线 A（**最快，推荐**）：复用它已验证的 EFI，零下载

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  "C:\Users\<USER>\.dsh\skills\hackintosh-opencore\scripts\install-macos26.ps1" -DryRun
```

它会自动：代理/TUN/苹果服务器预检 → 找 1401 → 找驱动包 → **复用 `M:\EFI`** → 30 项配置体检 → 按序列号选盘 → 打印剩余人工步骤。

**判据**：日志出现 `配置体检通过（无 FAIL）`，退出码 0。
实测耗时：**约 40 秒**（因为不下载任何东西）。

### 路线 B（EFI 坏了才用）：重新扫描 + 构建

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  "...\install-macos26.ps1" -DryRun -ForceBuild
```

⚠️ 会从 GitHub 拉 kext。本网络到 GitHub 实测 **1.6 KB/s（等于不可用）**，
脚本会走 `gh-proxy.com` 镜像；若仍卡住 → 让用户挂梯子或用别的网络。
**注意**：`build` 必须**管理员权限**（kext 缓存在 `%LOCALAPPDATA%\NullMoth\1401\OCK_Files`，是管理员建的）。

### 真写盘（用户确认后）

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  "...\install-macos26.ps1" -Serial SERIAL_USB_REDACTED
```

**必须让用户亲口确认**："这会擦除 U 盘（disk 6，59.5 GB）上的全部数据，继续吗？"

**判据**：脚本退出码 0，且 `M:\` 下出现 `EFI\`、`com.apple.recovery.boot\BaseSystem.dmg`（≈900 MB）。

### 如果不用脚本、纯手工（了解原理用）

```powershell
$py = 'G:\1401-2.3.3\1401\engine\python\python.exe'
# 1) 扫描（产出 Report.json + ACPI）
& $py -m p1401.scan C:\<WORK>\oneclick\scan
# 2) 构建 EFI（--macos 25 = Tahoe 26；24 = Sequoia 15）
#    注意：必须 < NUL 重定向，否则会卡在 "Press Enter to continue"
cmd /c "cd /d G:\1401-2.3.3\1401\engine && `"$py`" -m p1401 build C:\...\scan\Report.json C:\...\scan\ACPI C:\...\efi --macos 25 < NUL"
# 3) 写盘（GUI 同一套模块）
cmd /c "cd /d G:\1401-2.3.3\1401\engine && `"$py`" -m p1401.usbwriter write 6 C:\...\efi 25 --profile C:\...\scan\Report.json --driver M:\NullMoth\nullmoth-nvidia-2.3.7.tar.gz"
```

---

## §3. 用户要做的 3 件事（**必须原样转达，不要改写**）

### ① BIOS 九项（5 分钟）

```
开机连点 Del 进 BIOS →
  VT-d / IOMMU              = Disabled      ← 不关必卡 EXITBS
  Hyper-Threading           = Disabled      ← 混合核心必须
  Active E-Cores            = 0
  Re-Size BAR / Resizable   = Enabled       ← 驱动要 8GB BAR
  Above 4G Decoding         = Enabled
  CSM / Legacy Boot         = Disabled
  Secure Boot               = Disabled
  Fast Boot                 = Disabled
  SATA Mode                 = AHCI
F10 保存退出
```

**顺带确认**：Windows 的快速启动必须关掉，否则固件启动顺序会被跳过：

```powershell
powercfg /h off
Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' HiberbootEnabled 0
```

### ② 装机（20–40 分钟）

```
开机按 F12 → 选 U 盘（UEFI: Generic STORAGE DEVICE）
→ OpenCore 菜单 → 选 macOS Installer
→ 磁盘工具 → 菜单「显示所有设备」→ 选**整块盘**（ADATA SU800，序列号 SERIAL_DISK4_REDACTED）
→ 抹掉：名称 macos，格式 APFS，方案 GUID
→ 关掉磁盘工具 → 安装 macOS → 选刚抹的盘
```

**关键提醒**：
- 只抹分区会失败（NTFS 卷在 macOS 下只读 → 提示"磁盘已锁定"）
- 装机过程中会自动重启几次，每次都选 macOS Installer / macOS
- **判断有没有真进 OpenCore**：U 盘根目录有没有**新增** `opencore-*.txt`

### ③ 开箱向导（5 分钟）

```
选语言 → 选地区 → 不迁移数据 → 不登 Apple ID（先跳过）→ 建本地账户 → 进桌面
```

---

## §4. 装显卡驱动（15 分钟）

进 macOS 桌面后，U 盘会自动挂载为 `/Volumes/1401`。

### 路线 A（推荐，图形界面）

```
U 盘 → NullMoth → 解压 1401-Mac-2.3.6.zip → 右键 1401.app → 打开
→ 按提示：它会找 OpenCore 分区、备份 config、装驱动、加「1401: Remove NVIDIA driver」回滚项
```

### 路线 B（最新驱动 2.3.7，命令行）

```bash
cd /Volumes/1401/NullMoth
tar -xzf nullmoth-nvidia-2.3.7.tar.gz -C /tmp
cd /tmp/pkgroot
shasum -a 256 -c SHA256SUMS          # 必须每行 OK
sudo ./install.sh                     # 输入密码时屏幕不显示，正常
```

### 装完必做

```
重启 → 系统设置 → 隐私与安全性 → 拉到底 → 点「允许」系统扩展 → 再重启一次
```

---

## §5. 验收（3 条，缺一不可）

在 macOS 终端里：

```bash
# ① 四个 kext 是否加载
kmutil showloaded --list-only | grep nullmoth
#   期望 4 行：NVRM / NVAccel / NVRMFB / NVRMAGDC

# ② Metal 是否可用（本机已确认 supported，仍建议现场复核）
system_profiler SPDisplaysDataType | head -20
#   期望：Chipset Model: NVIDIA GeForce RTX 3070
#         Metal: Supported

# ③ 目视（让用户做）
#   拖窗口、切一次分辨率/刷新率、放 1080p 视频 2 分钟 → 不黑不花不闪
```

**判据**：①②③ 全中 → 可以说"RTX 3070 已在 macOS 内出图"。
**只中 ①②** → 走 §7 的 D3。
**只出 2 行 kext** → 走 §7 的 D4。

---

# 第四部分 · 出问题怎么办

## §6. 时间预算（报给用户，减少焦虑）

| 阶段 | 耗时 | 最容易卡在哪 |
|---|---|---|
| §1 预检 | 1 分钟 | 忘了关代理/快速启动 |
| §2 做盘 | 40 秒（复用）～ 40 分钟（重建） | GitHub 下载 1.6 KB/s |
| §3① BIOS | 5 分钟 | 找不到 VT-d / CSM 选项 |
| §3② 装机 | 20–40 分钟 | 抹盘提示"磁盘已锁定" |
| §3③ 开箱 | 5 分钟 | 卡在 Apple ID（跳过即可） |
| §4 驱动 | 15 分钟 | 忘记允许系统扩展 |
| §5 验收 | 2 分钟 | — |
| **合计** | **约 1 小时** | （我们两个人当年花了 4 天） |

## §7. 症状速查表

| 编号 | 现象 | 根因 | 修法 |
|---|---|---|---|
| **D1** | 交接内核后**一个字都不输出**，屏幕停在 Picker 菜单 | `debug=0x100` 静默错误；或 NVRAM 旧 `boot-args` 覆盖 config | 去掉 `debug=0x100`；把 `boot-args` 加进 `NVRAM → Delete` |
| **D2** | 卡 `EB|LOG:EXITBS:START` | VT-d 没关 / 混合核 / `DevirtualiseMmio` 反了 | 关 VT-d + 关 HT/E 核 + `DevirtualiseMmio=True` + `ProvideCurrentCpuInfo=True` |
| **D3** | 卡 `[AHCI][HBA] start:` 或进桌面后黑屏只有鼠标 | **不是 SATA 不兼容**；前者缺时钟补丁，后者 BAR 太小 | 加两个 `Remove non-monotonic time panic` 补丁（Count=2）；BIOS 开 Re-Size BAR |
| **D4** | 到用户态后服务全挂：`setuid/task_for_pid: Operation not permitted`、`code signature page shift: 14` | SIP 缺 `0x04` 位；或 AMFIPass 没开 | `csr-active-config = FF0F0000` + 启用 AMFIPass.kext |
| **D5** | OpenCore 菜单只剩 `Reset NVRAM` | `ScanPolicy` 位掩码算错，把 APFS/USB 一起过滤 | 改成官方默认 `17760515` 或 `0` |
### 双系统怎么选（2026-10-22 已配置好）

| 想进 | 怎么做 | 需要键盘吗 |
|---|---|---|
| **macOS** | 插着 U 盘开机，什么都不按 | ❌ 不需要（8 秒自动） |
| **Windows** | **拔掉 U 盘开机** | ❌ 不需要（固件第二项就是 Windows） |
| Windows（插着 U 盘） | 开机后在 OpenCore 菜单按 ↓ 选 `Windows 11` 回车 | ✅ 需要（固件阶段键盘要能用） |

OpenCore 菜单结构：`macOS`（默认，8 秒倒计时）→ `Windows 11`（自定义项）→ `Reset NVRAM`（若未隐藏）。
若菜单里键盘没反应：BIOS → Advanced → IO Ports → USB Configuration →
`Legacy USB Support = Enabled` + `XHCI Hand-off = Enabled`，保存后再试。

| **D6** | 每次重启都进 Windows U 盘固件项失效 / 快速启动跳过固件 | `powercfg /h off` + `bcdedit /set {fwbootmgr} bootsequence {U盘GUID}`；判断标准：U 盘根有没有新增 `opencore-*.txt` |
| **D7** | 抹盘提示"磁盘已锁定" | NTFS 只读 | 抹**整块盘**为 APFS/GUID |
| **D8** | 双系统时间差 8 小时 | macOS 写 UTC，Windows 读本地 | `RealTimeIsUniversal=1` + `w32tm /resync` |
| **D9** | 驱动装完，`kmutil` 只出 2 行 | 扩展未允许，或 kext 加载失败 | 系统设置允许扩展 → 重启两次 → 再看；仍不行看 `log show --last boot \| grep -i nvrm` |
| **D10** | 装驱动后进不了桌面 | 驱动与系统不匹配 | 重启 → OpenCore 菜单选 `1401: Remove NVIDIA driver` → 按 Y |

## §8. 回滚三层（出事按顺序试）

```
第一层（最轻）：OpenCore 菜单 → 1401: Remove NVIDIA driver → 按 Y
第二层：恢复配置  copy M:\EFI\OC\config.plist.bak-* 到 config.plist
第三层：整盘重做  §2 路线 B 重新构建 EFI + §2 写盘
第四层（保命）：F12 → Windows Boot Manager → 回 Windows 处理 U 盘
```

---

# 第五部分 · 数值速查（照抄区）

## §9. config.plist 关键项（这台机器的正确值）

```python
# 用 python plistlib 改，别手改 XML
import plistlib
p = r'M:\EFI\OC\config.plist'
c = plistlib.load(open(p,'rb'))

# --- CPU / 内存映射 ---
c['Kernel']['Quirks']['ProvideCurrentCpuInfo'] = True      # 混合核必须
c['Kernel']['Quirks']['DisableIoMapper']       = True
c['Kernel']['Quirks']['LapicKernelPanic']      = False
c['Booter']['Quirks']['DevirtualiseMmio']      = True      # 1401 默认给 False，方向反了
c['Booter']['Quirks']['SetupVirtualMap']       = True
c['Booter']['Quirks']['RebuildAppleMemoryMap'] = True
c['Booter']['Quirks']['SyncRuntimePermissions']= True
c['Booter']['Quirks']['ResizeAppleGpuBars']    = 0         # 装驱动阶段可 -1
c['UEFI']['Quirks']['ResizeGpuBars']           = -1        # 或 13（BIOS 已开 ReBAR 时 -1 即可）

# --- CPUID 伪装（Comet Lake 0x000A0655）---
c['Kernel']['Emulate']['Cpuid1Data'] = bytes.fromhex('55060A00000000000000000000000000')
c['Kernel']['Emulate']['Cpuid1Mask'] = bytes.fromhex('FFFFFFFF000000000000000000000000')

# --- ACPI：删 DMAR（配合 BIOS 关 VT-d）---
# ACPI → Delete: TableSignature=DMAR, All=True, Enabled=True

# --- SIP 与启动参数 ---
G = '7C436110-AB2A-4BBB-A880-FE41995C9F82'
nv = c['NVRAM']['Add'][G]
nv['csr-active-config'] = bytes.fromhex('FF0F0000')   # 0x0FFF；0x0A43 会缺 task_for_pid 位
nv['boot-args'] = ('-v keepsyms=1 nvfb=1 nvaccel=1 nvfbheads=1 -nvkmsnosmooth '
                   'amfi_get_out_of_my_way=0x1 amfi=0x80 ipc_control_port_options=0')
# 装完驱动后由 1401 Mac app 自动把 -v 去掉、nvfbheads 改 1
dl = c['NVRAM'].setdefault('Delete', {}).setdefault(G, [])
for k in ('boot-args','csr-active-config'):
    if k not in dl: dl.insert(0, k)     # 不加进 Delete，新值会被 NVRAM 旧值覆盖

# --- 其他 ---
c['Misc']['Security']['SecureBootModel'] = 'Disabled'
c['Misc']['Boot']['ScanPolicy'] = 0        # 或 17760515（只扫 APFS）
c['PlatformInfo']['Generic']['SystemProductName'] = 'MacPro7,1'
plistlib.dump(c, open(p,'wb'), fmt=plistlib.FMT_XML, sort_keys=False)
```

## §9.2 两个内核补丁（**最容易漏，漏了就会卡 `[AHCI]`**）

`Kernel → Patch` 里必须有两条，`Comment` 含 `Remove non-monotonic time panic`，
`Identifier = kernel`，**`Count` 必须是 2**，一条 `MinKernel 21.0.0 / MaxKernel 25.3.99`，
一条 `25.4.0 / 25.99.99`。**1401 不自带**，从
<https://github.com/Coolzhy/EFI-OMEN16-am2xxx-public> 的 `EFI/OC/config.plist` 里原样复制。

## §9.3 kext（11 个，顺序不要变）

```
Lilu → VirtualSMC → AMFIPass → AppleMCEReporterDisabler → RestrictEvents
→ SMCProcessor → SMCSuperIO → USBToolBox → UTBDefault → WhateverGreen → RTL812xLucy
```

**`CpuTopologyRebuild.kext` 必须 `Enabled=False`**（Arrow Lake 上必关）。

---

# 第六部分 · 禁止事项（12 条，违反必踩坑）

```
1. 别带 debug=0x100 引导 —— 它静默所有错误，屏幕看起来像"卡在菜单"
2. 别只改 config 的 boot-args 而不加进 NVRAM → Delete —— 旧值会赢
3. 别开着 VT-d 试 —— EXITBS 第一元凶
4. 别留超线程和 E 核 —— 关完只剩 6C/6T 是正常的
5. 别信 1401 默认的 DevirtualiseMmio=False —— 对 Arrow Lake 方向反了
6. 别手算 ScanPolicy —— 算错会把 APFS 一起过滤
7. 双系统别留快速启动/休眠 —— bcdedit 写的启动顺序等于废纸
8. 别在 macOS 里抹 NTFS 卷 —— 只会"磁盘已锁定"，要抹整块盘
9. 别以为卡 [AHCI] 就是 SATA 不兼容 —— B860 的 SATA 实测能工作，真因是时钟补丁
10. 别关 AMFIPass —— 缺它系统服务全挂
11. 别用老版本 1401 —— 老版本缺混合核心修复
12. 别一次改一堆配置 —— 一次一个变量，每步验一次
```

---

# 第七部分 · 收尾清单（装完勾一遍）

```
[ ] macOS 能启动到桌面（不是黑屏+鼠标）
[ ] Windows 能进（F12 → Windows Boot Manager）
[ ] kmutil 出 4 行 nullmoth
[ ] system_profiler 显示 RTX 3070 + Metal: Supported
[ ] 桌面能拖窗口、切分辨率不黑
[ ] 双系统时间一致（差 < 60 秒）
[ ] U 盘里有 config.plist.bak-*（回滚保险）
[ ] 资料盘（F:/G:/H:）数据完好
```

---

**这份手册的内容全部来自 2026-10-16 → 10-20 的真机实战。**
**你按它走，用户大约 1 小时能装完；我们当年花了 4 天，希望你别重走。**
