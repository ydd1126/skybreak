---
name: hackintosh-opencore
description: 【开天 Skybreak，别名 黑果通】macOS 26 装机一条龙：在 Intel 平台上用 OpenCore + nullmoth/1401 + nvidia-macos-driver 装 macOS 并驱动 NVIDIA 独显时使用：覆盖硬件清点与兼容档位判定、BIOS 逐项设置、1401 扫硬件与构建 EFI、写 macOS 安装盘、config.plist 关键项落到正确值、磁盘工具抹盘、首次进系统的服务级验收、显卡驱动两条安装路线与三层回滚，以及按屏幕现象逐条定位启动卡死（零输出、卡 EB|LOG:EXITBS:START、卡 [AHCI][HBA] start、菜单只有 Reset NVRAM、SIP 缺 task_for_pid 导致系统服务全挂、每次重启进 Windows、抹盘磁盘已锁定、双系统时间差 8 小时）。全部结论来自 Arrow Lake 245K + RTX 3070 + 技嘉 B860M POWER 一台真机四天实战，不含任何推测值。
whenToUse: 用户提到开天 / Skybreak / 用开天装 / 黑果通 / 用黑果通装 / 黑苹果 / hackintosh / OpenCore / 装 macOS / 装黑苹果双系统 / 1401 / nullmoth / nvidia-macos-driver / 显卡驱动跑 macOS / 卡 EXITBS / EB|LOG:EXITBS:START / 卡 AHCI / 卡在 [AHCI][HBA] start / 引导零输出 / 内核交接后无输出 / OpenCore 菜单只有 Reset NVRAM / 菜单空白 / ScanPolicy / SIP / csr-active-config / AMFIPass / task_for_pid Operation not permitted / code signature page shift / 混合核心 / P-Core E-Core / Arrow Lake / Core Ultra 200S / B860M / 抹盘磁盘已锁定 / 每次重启进 Windows / 双系统时间差 8 小时 / 看 opencore-*.txt 引导日志 / 判断某台机器能不能装 macOS 时。
---

# 开天 Skybreak · 装 macOS（OpenCore + 1401 + NVIDIA 驱动）：可执行流程

本 skill 是把一台真机四天实战压成的执行手册，终点是 **macOS 26.7.1 build 25G241** 与 **Windows 11 25H2 26200** 双系统共存：

- 主板 Gigabyte **B860M POWER**（Intel B860 / LGA1851），BIOS AMI **F10**（2026-02-02）
- CPU **Intel Core Ultra 5 245K**（Arrow Lake-S，Family 6 Model 0xC6，14 核 = 6P+8E，L3 24 MB）
- dGPU **NVIDIA RTX 3070 8GB**（PCI `10DE:2488`，SUBSYS `1458:404E`），iGPU Intel `8086:7D67`
- macOS 系统盘 **ADATA SU800 256G**（序列号 `SERIAL_DISK4_REDACTED`），Windows 系统盘 **SAMSUNG SM841 256G**（序列号 `SERIAL_DISK3_REDACTED`）

**唯一事实来源是同目录 `_FACTS.md`**。本文件里的每个型号、版本、位掩码、日志原文都能在 `_FACTS.md` 里找到出处；两者冲突时以 `_FACTS.md` 为准，并当场更正本文件。完整案例时间线见 [references/case-arrow-lake-245k.md](references/case-arrow-lake-245k.md)。

---

## 〇、用户只说一句「帮我装 macOS 26」时的执行剧本

**这是本 skill 的主入口。** 用户不需要懂任何东西，agent 按下面 6 步走完，用户只做 3 个物理动作。

### 第 1 步：先说清能不能装（30 秒，不要跳过）

```powershell
Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors
Get-CimInstance Win32_VideoController | Select-Object Name,PNPDeviceID
Get-Disk | Select-Object Number,FriendlyName,SerialNumber,BusType,@{n='GB';e={[math]::Round($_.Size/1GB,1)}}
```

按第二节 D1–D4 判档位，**照第七节把三件事如实告诉用户**（Arrow Lake 苹果未支持 / Ampere 未物理验证 / SATA 与 NVMe 的差异），并给出预期成功率档位。**判据：用户明确回复"接受风险，继续"。**

### 第 2 步：跑一键流水线（体检模式，绝不动盘）

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\.dsh\skills\hackintosh-opencore\scripts\install-macos26.ps1" -DryRun
```

脚本自动做 8 件事：代理/TUN/苹果服务器预检 → 找或下载 1401 → 找或下载驱动包 → 复用已验证 EFI（没有才 scan+build）→ 套用成功配置 → **30 项体检（FAIL 就停）** → 按序列号选盘 → 打印剩余人工步骤。

**判据：日志出现 `配置体检通过（无 FAIL）` 且退出码 0。FAIL 就先修，绝不许带着 FAIL 写盘。**

### 第 3 步：把结果和剩余动作一次性告诉用户

脚本结尾会打印 3 个物理动作，**原样转给用户，不要改写成模糊话**：

```
1) BIOS 9 项：VT-d=Disabled / Hyper-Threading=Disabled / E-Cores=0 /
   Re-Size BAR=Enabled / Above 4G=Enabled / CSM=Disabled /
   Secure Boot=Disabled / Fast Boot=Disabled / SATA=AHCI
2) 插 U 盘开机（F12 选它）→ OpenCore 自动进安装器 →
   磁盘工具「显示所有设备」→ 抹整块盘为 APFS/GUID → 装 macOS → 重启
3) 开箱向导：选语言 → 建账户（先别登 iCloud）
```

### 第 4 步：真写盘（用户确认后）

```powershell
# 先拿序列号，别用盘符
Get-Disk | Where-Object BusType -eq USB | Select-Object Number,FriendlyName,SerialNumber
# 再用序列号写（脚本会自提权）
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\.dsh\skills\hackintosh-opencore\scripts\install-macos26.ps1" -Serial <序列号>
```

脚本第三次防呆：序列号不符直接中止，不写一个字节。

### 第 5 步：用户装完进桌面后，让他双击 U 盘上的 `一键安装显卡驱动.command`

（该文件由第 4 步第 8 段自动放进 U 盘。）装完重启两次，然后验收：

```bash
kmutil showloaded --list-only | grep nullmoth          # 期望 4 行
system_profiler SPDisplaysDataType | head -20          # 期望 Metal: Supported
```

### 第 6 步：验收结论怎么下（不许含糊）

| 现象 | 结论 |
|---|---|
| 4 行 kext + `Metal: Supported` + 桌面 2 分钟不黑 | **成功**，可以写"RTX 已在 macOS 内出图" |
| 只出 2 行 或 `Metal: Unsupported` | 走第四节 R09（驱动不出图/BAR） |
| 4 行但有桌面黑/花屏/闪屏 | 走 [references/nullmoth-driver.md](references/nullmoth-driver.md) §6 已知问题 |
| 装到一半起不来 | 拿 U 盘根最新 `opencore-*.txt` → 第四节 R01–R10 定位 |

**铁律：没拿到 ①②③ 的输出，只能说"装完能进桌面"，不许说"已出图"。**

### 这套流程做不到什么（必须提前讲）

- BIOS 9 项没有 API，只能人进 BIOS 点
- macOS 安装器的抹盘/安装是 GUI，消费级不开放无人值守
- 显卡驱动必须等内核起来后才能装（装早了黑屏）
- 所以"一键" = **一键做好完全可用的安装盘**，不是"一键装完能用"

---


## 一、铁律（违反任何一条就停手）

1. **先判兼容档位，再碰任何软件。**
   判据：能填满第二节的 4 个判定项（CPU 是否混合核 / GPU 在不在设备表 / 系统盘 SATA 还是 NVMe / 单系统还是双系统）并得出档位字母。填不出就不许写 U 盘、不许改 BIOS。

2. **改 `config.plist` 前先备份，并把被改键的原始值写进台账。**
   判据：存在 `EFI/OC/config.plist.bak-<yyyyMMdd-HHmmss>`，且台账（见第三节 S10 模板）里每个被改的键都能查到改前旧值。没有备份值 = 这次改动不许执行。

3. **认盘只认序列号，禁止认盘符、Index、容量。**
   判据：动手前 Windows 侧 `Win32_DiskDrive` 的 `SerialNumber`（去空格）与目标盘清单逐字符对上；macOS 侧用 `ioreg` 读到的序列号再对一次。盘符会变，Index 会变，序列号不会。

4. **任何不可逆操作（抹整盘、写 U 盘、装驱动）之前，先把能回退的东西落到 Windows 侧。**
   判据：`C:\<WORK>\` 下同时存在 EFI 全量副本、`config.plist.bak-*`、当前 kexts 清单 `kexts-before.txt`。

5. **能在 CLI 做的，绝不让人去点 GUI。**
   判据：流程里每一步要么是一条命令，要么是一个 BIOS 项名。"你去设置里点一下"不构成步骤，必须给出等价命令。

6. **每步必须带可判定的验收输出；没有判据的步骤不许写进流程。**
   判据：看到某行日志原文、某个返回值、某个分区 GUID 才算过。看到"好像成功了"不算。

7. **一次只动一个变量。**
   判据：两次重启之间只改 1 个 `config.plist` 键或 1 个 BIOS 项；改完立刻重启验证并回填台账。批量改 = 出问题后无法归因，四天里一半时间就是这么烧掉的。

---

## 二、0→1 决策树：先算成功率，再决定动不动手

按 D1 → D4 顺序走，每层只回答一个是/否。**档位是经验分级，不是统计数字**，含义见本节末尾。

### D1　CPU 是不是混合核心（P-Core + E-Core 异构）？

```powershell
# [Win] 判定命令：核数与线程数就是异构与否的硬证据
Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed
```

- **是**（Intel 12/13/14 代、Core Ultra 200S/H/HX；本机 245K = 6P+8E）→ 必须同时满足下面三条，缺一条直接卡死：
  - `Kernel → Quirks → ProvideCurrentCpuInfo = True`
  - 关 Hyper-Threading + 关 Active E-Cores（BIOS）
  - 打两个 `Remove non-monotonic time panic` 内核补丁
  → 进入 D2，且档位强制不高于 **C**。
- **否**（全同构核，如 10 代及更早）→ 上面三条全部不必，档位可给 **B**。跳到 D2。

- **判据**：改 BIOS 前 `NumberOfCores` 应读到 14（6P+8E）；关完 HT/E 核后 `NumberOfLogicalProcessors` 必须降到 6（"只剩 6C/6T"）。读不到 6 说明 E-Cores 或 HT 没真关掉。

### D2　GPU 在不在驱动设备表？物理验证过没有？

```powershell
# [Win] 读出 PCI ID，直接和官方设备表逐字段对
Get-CimInstance Win32_VideoController | Select-Object Name, PNPDeviceID
```

`PNPDeviceID` 形如 `PCI\VEN_10DE&DEV_2488&SUBSYS_404E1458&REV_A1\...`，取 `VEN_`/`DEV_`/`SUBSYS_` 三段。
**`SUBSYS` 是反序**：串里写 `<设备ID><厂商ID>`，读作 `厂商:设备` —— 本机 `404E1458` = `1458:404E`（技嘉 / RTX 3070）。按 `<厂商><设备>` 顺序查会永远对不上，导致误判"显卡不符"而错误劝停。

- **设备表覆盖 Turing 及以后**（GTX16 / RTX20 / RTX30 / RTX40 / RTX50）→ 可走驱动路线。厂商自动化验证过的只有 RTX 5060，Ampere（RTX 30）在设备表里是 **Pending**。**但本机 RTX 3070 已实机确认出图 + Metal 可用（2026-10-24）** —— `Pending` 指的是厂商没跑验证，不是硬件不能用。
  - 你的卡是 RTX 5060 → **B**
  - 你的卡是 Turing/Ampere/Ada/Blackwell 其它型号 → **C**（能不能出图必须实机验证，见第七节）
- **不在设备表** → **D**，不装独显驱动，只装系统。系统能点亮，但别承诺加速。

对照表见 [references/hardware-matrix.md](references/hardware-matrix.md)。

### D3　系统盘是 SATA 还是 NVMe？

```powershell
# [Win] InterfaceType 直接告诉你
Get-CimInstance Win32_DiskDrive | Select-Object Index,Model,SerialNumber,InterfaceType,Size
```

- **NVMe（M.2）** → 走 `AppleNVMe` 通用 PCIe 驱动，风险最低，档位不降。
- **SATA AHCI** → 新 PCH（600/700/800 系）风险更高，但**本次实战已证明 B860 的 SATA 可以工作**，档位不降。但必须多记一条：出问题时先怀疑**时钟补丁**，不是 SATA 不兼容（见第四节 R03）。

### D4　单系统还是双系统？

```powershell
# [Win] 现有启动项与休眠状态，决定要不要清障
bcdedit /enum '{fwbootmgr}'
powercfg /a
```

- **双系统** → 必须执行 S04（`powercfg /h off`、`HiberbootEnabled=0`、`RealTimeIsUniversal=1`），否则会出现"每次重启都进 Windows"和"时间差 8 小时"两个必然问题。
- **单系统（全新盘）** → S04 可跳过 `RealTimeIsUniversal`，但**快速启动仍必须关**，否则固件启动顺序照样失效。

### D0→1 输出：档位 + 推荐路线

| 组合 | 档位 | 预期结果 | 推荐路线 |
|---|---|---|---|
| 全同构核 + NVMe + 设备表内已验证卡（RTX 5060） | **A** | 高，照标准流程走即可 | S01→S16 全跑，跳过 D1 的三条组合拳 |
| 混合核 + NVMe + 设备表覆盖但未验证（RTX 40 等） | **B** | 中，系统能进，加速必须实测 | S01→S16，D1 三条必须齐 |
| 混合核（Arrow Lake）+ SATA + Ampere（RTX 3070） | **C** | **未知**，本机这批硬件实测跑通，换型号必须重验 | 本 skill 第五节配置**照抄**，S01→S16 全跑，第七节三件事先讲清 |
| 混合核 + 设备表外 GPU | **D** | 系统能点，无加速 | 只跑 S01→S14，跳过第六节 |
| 非 Intel / AMD 平台 | **D** | 不在本 skill 覆盖范围 | 停手，另找参照 |

判据：**没写档位不许开始**。写下来了，后面每一个"要不要试"的问题都有答案：A/B 直接做，C 先讲风险再做，D 只做到系统能进。

---

## 三、标准作业流程（SOP，16 步）

每一步四字段固定：**动作 / 命令 / 预期 / 失败跳转**。全部按顺序执行，不许跳步。

### S01　清点硬件并落盘（唯一可信的输入）

```powershell
# [Win] 一次性把所有判据抓进一个文件，后面所有决策都引用它
$dir = "C:\<WORK>"; New-Item -ItemType Directory -Force $dir | Out-Null
$out = Join-Path $dir ("hardware-" + (Get-Date -f yyyyMMdd-HHmmss) + ".txt")
Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model,SystemSKUNumber | Format-List * >> $out
Get-CimInstance Win32_BaseBoard    | Select-Object Manufacturer,Product,Version,SerialNumber | Format-List * >> $out
Get-CimInstance Win32_BIOS         | Select-Object Manufacturer,SMBIOSBIOSVersion,ReleaseDate | Format-List * >> $out
Get-CimInstance Win32_Processor    | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed | Format-List * >> $out
Get-CimInstance Win32_PhysicalMemory | Select-Object DeviceLocator,Capacity,Speed,Manufacturer,PartNumber,SerialNumber | Format-Table -Auto >> $out
Get-CimInstance Win32_DiskDrive    | Select-Object Index,Model,SerialNumber,InterfaceType,Size | Format-Table -Auto >> $out
Get-CimInstance Win32_VideoController | Select-Object Name,PNPDeviceID | Format-List * >> $out
Get-PnpDevice -Class Net,Media -Status OK | Select-Object Class,FriendlyName,InstanceId | Format-Table -Auto >> $out
powercfg /a >> $out
bcdedit /enum '{fwbootmgr}' >> $out
Get-Content $out
```

- **预期**：`SMBIOSBIOSVersion` = F10；CPU 名含 `Ultra 5 245K`；视频控制器 `PNPDeviceID` 含 `VEN_10DE&DEV_2488&SUBSYS_404E1458`（反序，读作 1458:404E）且另有 `VEN_8086&DEV_7D67`；网卡 `10EC:8125`；内存只 1 条（单通道，4 槽只用 1）。
- **失败跳转**：读不到序列号/型号 → 停手，先把 `C:\<WORK>\` 建好再谈装系统。

### S02　按第二节判档位，写进台账第一行

动作：把 D1–D4 的结论写成一行 `档位=C 混合核/SATA/Ampere/双系统`，存在 `C:\<WORK>\plan.txt`。
- **判据**：文件存在且含 `档位=`。
- **失败跳转**：判不出 → 回第二节，不许往下走。

### S03　BIOS 逐项设置（决定成败的 9 项必设，前 8 项在主菜单第一屏）

进 BIOS（Del），改这 8 项，一项都不能漏：

```
VT-d / IOMMU                  = Disabled    ← 决定性，卡 EXITBS 第一元凶
Hyper-Threading               = Disabled    ← 混合核心必须
Active E-Cores                = 0           ← 同上，改完只剩 6C/6T
Above 4G Decoding             = Enabled
Re-Size BAR / Resizable BAR   = Enabled     ← 驱动要 8 GB BAR，MUST
CSM / Legacy Boot             = Disabled
Secure Boot                   = Disabled
Fast Boot                     = Disabled
```

- **预期**：保存重启后再进 BIOS，8 个读回值全部与上表一致。
- **失败跳转**：某项灰不可改 → 先关掉关联项（如 Secure Boot 未关时 ReBAR 可能灰）再看 [references/bios-checklist.md](references/bios-checklist.md)；VT-d 找不到 → 在 `Settings → Advanced` 或芯片组页搜 `VT-d`，AMD 平台叫 `IOMMU`。改完仍反复进不了引导 → 第四节 R02。

### S04　Windows 侧清障（双系统必做，单系统也做一半）

```powershell
# [Win] 以管理员身份
powercfg /h off
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power" /v HiberbootEnabled /t REG_DWORD /d 0 /f
reg add "HKLM\SYSTEM\CurrentControlSet\Control\TimeZoneInformation" /v RealTimeIsUniversal /t REG_DWORD /d 1 /f
w32tm /resync
powercfg /a
```

- **预期**：`powercfg /a` 里"休眠"显示为不可用；`HiberbootEnabled` 与 `RealTimeIsUniversal` 都是 `0x1`。
- **失败跳转**：注册表写入被拒 → 没提权，用管理员 PowerShell 重跑。时间同步失败 → 手动把 Windows 时间对准网络时间再跑 `w32tm /resync`。

### S05　网络路线压测（不修好这个，后面全卡）

```powershell
# [Win] 1) 关系统代理（Clash 会掐断 osrecovery.apple.com 的 TLS）
Set-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings" -Name ProxyEnable -Value 0
Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings" | Select-Object ProxyEnable,ProxyServer

# 2) 直连 GitHub 实测速度（本网络实测 1.6 KB/s，基本等于不可用）
curl.exe -L -o NUL -w "direct=%{speed_download}\n" --max-time 20 "https://github.com/nullmoth/1401"

# 3) 走镜像实测（本网络实测 400–4400 KB/s）
curl.exe -L -o NUL -w "proxy=%{speed_download}\n" --max-time 20 "https://gh-proxy.com/https://github.com/nullmoth/1401"
```

- **预期**：`ProxyEnable=0`；`proxy=` 的数明显大于 `direct=`。
- **判据（本节设定门槛）**：镜像平均 ≥ 300000 B/s 才继续；低于 100000 B/s 就换镜像域名重测。
- **失败跳转**：两个都慢 → 检查 Clash 的 TUN/系统代理是否还在（`ProxyServer` 非空就是没关干净）；写安装盘阶段出现 `SSL: UNEXPECTED_EOF_WHILE_READING` → 一定是代理没关，回本步。

### S06　取最新 1401 + 驱动包

动作：从镜像打开 release 页，下载**最新** Windows 版 1401、`1401-Mac-<ver>.zip`、驱动 `tar.gz`。

```powershell
# [Win] 只走镜像，禁止直连
Start-Process "https://gh-proxy.com/https://github.com/nullmoth/1401/releases"
Start-Process "https://gh-proxy.com/https://github.com/nullmoth/nvidia-macos-driver/releases"
```

- **判据**：解压目录能跑出子命令帮助（`python -m p1401 --help` 有输出），且版本号比老版本高。
- **失败跳转**：老版本 1401 缺混合核心修复 —— 本机实际用过的 `G:\1401-2.3.3\` 只作参照，**永远优先最新版**，否则混合核机器直接卡 EXITBS。

### S07　扫硬件，产出 Report.json

```powershell
# [Win] 子命令名以 --help 现场输出为准，别凭记忆写
python -m p1401 --help
python -m p1401 scan
```

- **判据**：生成 `Report.json`，里面能搜到 `245K`、`10DE:2488`（或 `VEN_10DE&DEV_2488`）、`10EC:8125` 三条。
- **失败跳转**：没有 `scan` 子命令 → 用 1401 的 Windows GUI 扫一遍再回到 CLI；`Report.json` 里 GPU 写成未知 → 先更新 1401 版本（老版数据库缺 Arrow Lake/Ampere 条目）。

### S08　构建 EFI

```powershell
# [Win] 官方 CLI 形态（本次实战命令）
python -m p1401 build <Report.json> <ACPI目录> <输出目录> --macos 24 --boot-log <日志文件>
```

`--macos` 接受值只有 `24`/`25`（实测）。**不要自己编 `--macos 26`**：macOS 26 的差异不在这个参数上，而在两个时钟补丁与驱动侧的 `kexts/26` 分支。构建前先 `python -m p1401 build --help` 确认当前版本接受的取值。

- **判据**：输出目录出现 `EFI/OC/config.plist`、`EFI/OC/Kexts/`、`EFI/BOOT/BOOTx64.efi`、`EFI/OC/OpenCore.efi`。
- **失败跳转**：缺 `OpenCore.efi` → 构建中断，看 `--boot-log` 末尾；缺 Kexts → ACPI 目录参数给错。

### S09　把 EFI 和 macOS 安装器写到 U 盘

```powershell
# [Win] U 盘盘符先确认（不要用读卡器/移动硬盘冒充）
$USB = "M:"   # 本机实测为 M: Generic U 盘 59.5G，序列号 SERIAL_USB_REDACTED
Test-Path "$USB\EFI\OC\config.plist"
```

动作：用 1401（Windows 版，CLI 或 GUI 等价）把上一步的 EFI + macOS 安装器写到该 U 盘。
- **预期**：`Test-Path "$USB\EFI\OC\config.plist"` 返回 `True`；U 盘 EFI 分区为 FAT32；U 盘根同时有 `NullMoth\`（驱动包 + Mac app + 说明）。
- **失败跳转**：写盘中途报 TLS 错误 → 回 S05 关代理；写盘成功但 `EFI/OC/config.plist` 不在 → 用了老版 1401 的分区布局，手工把构建出的整个 `EFI` 目录拷进 U 盘 EFI 分区。

### S10　逐键核对 config.plist（照抄第五节，一键不改错）

**先备份**，再改，再自检：

```powershell
# [Win] 1) 备份（文件级，不可省）
$USB = "M:"
Copy-Item "$USB\EFI\OC\config.plist" "$USB\EFI\OC\config.plist.bak-$(Get-Date -f yyyyMMdd-HHmmss)"

# 2) 结构化自检（plistlib 直接读，不靠肉眼）
python -c "import plistlib,json,sys; d=plistlib.load(open(r'M:\EFI\OC\config.plist','rb')); print(json.dumps({'KernelQuirks':d['Kernel']['Quirks'],'BooterQuirks':d['Booter']['Quirks'],'UEFIQuirks':d['UEFI']['Quirks'],'ScanPolicy':d['Misc']['Security'].get('ScanPolicy'),'SecureBootModel':d['Misc']['Security'].get('SecureBootModel'),'ProductName':d['PlatformInfo']['Generic'].get('SystemProductName'),'csr':d['NVRAM'].get('Add',{}).get('7C436110-AB2A-4BBB-A880-FE41995C9F82',{}).get('csr-active-config'),'boot-args':d['NVRAM'].get('Add',{}).get('7C436110-AB2A-4BBB-A880-FE41995C9F82',{}).get('boot-args')},default=str,indent=1))"
```

- **判据**：输出与第五节表格逐项一致，特别是 `ProvideCurrentCpuInfo=true`、`DevirtualiseMmio=true`、`DisableIoMapper=true`、`LapicKernelPanic=false`、`ScanPolicy` 为 `17760515` 或 `0`、`csr` 为 `ff0f0000`、`ProductName` 为 `MacPro7,1`、`SecureBootModel` 为 `Disabled`。

**台账模板**（写进 `C:\<WORK>\config-ledger.txt`，每行一条）：

```
<yyyy-MM-dd HH:mm> | <键路径> | 旧值=<旧> | 新值=<新> | 原因=<对应诊断编号或 S 步>
```

- **失败跳转**：任何一项对不上 → 回第五节查正确值；改完仍进不去 → 第四节，先看卡在哪一行日志再改，不要盲改。

### S11　设置固件启动项（双系统最容易漏的一步）

```powershell
# [Win] 管理员 PowerShell
bcdedit /enum '{fwbootmgr}'
bcdedit /enum firmware
```

动作：从 `bcdedit /enum firmware` 输出里找到 U 盘那条启动项（描述含 OpenCore 或 U 盘型号）的 GUID，然后：

```powershell
bcdedit /set '{fwbootmgr}' bootsequence '{<U盘启动项 GUID>}'
# 或改顺序（保留原序列，把 U 盘 GUID 提到最前）
bcdedit /set '{fwbootmgr}' displayorder '{<U盘GUID>}' '{<原第一项GUID>}' ...
```

- **判据**：再次 `bcdedit /enum '{fwbootmgr}'` 时 `bootsequence`/`displayorder` 第一项是 U 盘 GUID。
- **失败跳转**：重启后仍进 Windows，且 U 盘根目录**没有新增** `opencore-*.txt` → 说明固件根本没走 OpenCore，回第四节 R06（先确认 S04 的快速启动真关了）。

### S12　首次引导到 OpenCore 菜单

```powershell
# [Win] 重启后回来：U 盘根是否新增了引导日志
$USB = "M:"
Get-ChildItem "$USB\opencore-*.txt" | Sort-Object LastWriteTime -Descending | Select-Object -First 3 Name,Length,LastWriteTime
Select-String -Path "$USB\opencore-*.txt" -Pattern "OC:|OCB:|OCA:" | Select-Object -First 20
```

- **判据**：U 盘根**新增** `opencore-*.txt`（这是"真走过 OpenCore"的唯一硬证据）；菜单里能看到 macOS 安装器项 + `Reset NVRAM`，菜单项总数 ≥ 2。
- **失败跳转**：菜单只有 `Reset NVRAM` → 第四节 R05（ScanPolicy）；`opencore-*.txt` 没新增 → R06；有日志但停在 `EB|LOG:EXITBS:START` → R02。

### S13　进安装器、抹盘

动作：菜单选 macOS 安装器 → 进"磁盘工具" → 菜单栏 `显示 → 显示所有设备` → 选**整块目标盘**（不是它下面的卷）→ 抹掉为 `APFS` / `GUID 分区图`。

**判据**：终端里执行下面两条，看分区表：

```bash
# [macOS 安装器 → 实用工具 → 终端]
diskutil list                     # 目标盘出现 Apple_APFS：Container
gpt -r show /dev/disk4 2>/dev/null || diskutil info disk4 | grep -Ei "Content|Partition"
```

- **判据**：分区表里出现 `7C3457EF-...`（APFS 分区类型 GUID）才算抹对。
- **失败跳转**：提示"磁盘已锁定" → 第四节 R07（绝对不能去抹 NTFS 卷，要抹整块盘）。

### S14　首次进系统，做"服务级"验收（不是"能进桌面"就算成功）

```bash
# [macOS]
csrutil status
nvram csr-active-config
nvram boot-args
log show --last boot | grep -Ei "task_for_pid|setuid|code signature page shift|malformed Mach-O"
kmutil showloaded | grep -Ei "Lilu|VirtualSMC|AMFIPass|RestrictEvents|WhateverGreen"
```

**判据（四条全中才算过）**：
1. `nvram csr-active-config` 输出 `%ff%0f%00%00`（即 `0x0FFF` 全关 SIP）
2. 上面那条 `log show ... | grep` **没有任何输出**（出现 `setuid/task_for_pid: Operation not permitted`、`code signature page shift: 14`、`malformed Mach-O` 就是没过）
3. `kmutil showloaded` 能列出 `AMFIPass`
4. 无重启循环（连续在线 ≥ 10 分钟不掉）

**失败跳转**：命中 1/2/3 任一条 → 第四节 R04（SIP 缺 `CSR_ALLOW_TASK_FOR_PID` 或 AMFIPass 被误关）。

### S15　装显卡驱动

见第六节两条路线。**前置动作不可省**：

```powershell
# [Win] 装驱动前把整个 EFI 拷到 Windows 侧，这是回滚第三层
Copy-Item "$USB\EFI" "C:\<WORK>\EFI-pre-driver-$(Get-Date -f yyyyMMdd-HHmmss)" -Recurse -Force
```

- **判据**：`C:\<WORK>\EFI-pre-driver-*\OC\config.plist` 存在。

### S16　驱动验收 + 固化回滚点

见第六节"验收"与"回滚三层"。**判据**：三项验收全过，且 OpenCore 菜单里能看到回滚项（Mac app 装法会自动加）。
- **失败跳转**：三项任一不过 → 第六节"回滚三层"，不许硬撑。

---

## 四、启动卡死诊断表（按屏幕现象直接定位）

**使用顺序**：先在下表定位编号 → 打开对应 R 小节 → 照"验证"跑一条命令 → 只有命令证实了根因才改配置。**禁止不看日志直接改**。

| 屏幕/日志现象（原样） | 编号 | 一句话根因 |
|---|---|---|
| 内核交接后零输出，屏幕定格在 OpenCore 菜单 | R01 | `debug=0x100` + NVRAM 旧 `boot-args` 覆盖 |
| 卡 `EB\|LOG:EXITBS:START` | R02 | BIOS VT-d 没关 / 混合核拓扑 / `DevirtualiseMmio` 方向错 |
| 过了 EXITBS，冻在 `[AHCI][HBA] start:` | R03 | 时钟非单调导致早期冻死（**不是 SATA 不兼容**） |
| 到 userspace 后服务全失败 | R04 | SIP 缺 `task_for_pid` 位 + AMFIPass 被关 |
| OpenCore 菜单只有 `Reset NVRAM` | R05 | `ScanPolicy` 位掩码算错 |
| 每次重启都进 Windows | R06 | U 盘启动项 GUID 失效 / 快速启动跳过固件 |
| 抹盘时提示"磁盘已锁定" | R07 | NTFS 卷被只读挂载，抹的是卷不是盘 |
| 双系统时间差 8 小时 | R08 | macOS 写 UTC，Windows 按本地时间读 |
| 驱动装完仍无加速 / 黑屏循环重启 | R09 | BAR 配置与 `ResizeAppleGpuBars` 不匹配 / 驱动版本与 macOS 版本错配 |
| 系统进去了但没网 | R10 | `RTL812xLucy` 未启用或未加载 |

---

### R01　内核交接后零输出，屏幕定格在 OpenCore 菜单

**根因（两条同时成立才会这么安静）**
1. `boot-args` 里有 `debug=0x100` → 内核错误被静默进调试器，屏幕不动也不报错。
2. NVRAM 里的旧 `boot-args` 盖住了 config 里的新值 → 日志会写 `OCVAR: Setting NVRAM ...boot-args - ignored, exists`。也就是说你改了 config，但机器用的是 NVRAM 里的旧参数。

**验证**

```powershell
# [Win] 日志里找"被忽略"的证据
Select-String -Path "M:\opencore-*.txt" -Pattern "ignored, exists"
Select-String -Path "M:\opencore-*.txt" -Pattern "debug=0x100"

# [Win] config 里有没有把 boot-args 放进 NVRAM → Delete
python -c "import plistlib;d=plistlib.load(open(r'M:\EFI\OC\config.plist','rb'));k='7C436110-AB2A-4BBB-A880-FE41995C9F82';print('Delete=',d['NVRAM'].get('Delete',{}).get(k));print('boot-args=',d['NVRAM']['Add'][k].get('boot-args'))"
```

- **判据**：命中 `ignored, exists` 或 `debug=0x100` 任一 → 就是本故障。

**修法**
1. 去掉 `boot-args` 里的 `debug=0x100`。
2. 把 `boot-args` 加进 `NVRAM → Delete → 7C436110-AB2A-4BBB-A880-FE41995C9F82`（先删旧的，再写新的）。
3. 诊断阶段 `boot-args` 只留 `-v keepsyms=1`，把详细日志打开。

- **复验判据**：日志出现 `Deleting NVRAM ...boot-args - Success`，并且屏幕开始滚内核日志。

---

### R02　卡 `EB|LOG:EXITBS:START`

**根因（三个，按命中概率排序）**
1. **BIOS VT-d / IOMMU 没关** —— 社区 5+ 用户同一结论，第一大元凶。
2. 混合核心拓扑没处理（`ProvideCurrentCpuInfo` 没开 / HT、E 核没关）。
3. `Booter → Quirks → DevirtualiseMmio` 方向反了 —— **1401 默认给 `False`，必须改 `True`**。

**验证**

```powershell
# [Win] 1) 日志里有没有 DMAR 被删的记录（VT-d 关掉后这里会变）
Select-String -Path "M:\opencore-*.txt" -Pattern "OCA: Deleting table DMAR|EXITBS"

# 2) 三个关键位是否是 True
python -c "import plistlib;d=plistlib.load(open(r'M:\EFI\OC\config.plist','rb'));print('ProvideCurrentCpuInfo=',d['Kernel']['Quirks'].get('ProvideCurrentCpuInfo'));print('DevirtualiseMmio=',d['Booter']['Quirks'].get('DevirtualiseMmio'));print('DisableIoMapper=',d['Kernel']['Quirks'].get('DisableIoMapper'));print('LapicKernelPanic=',d['Kernel']['Quirks'].get('LapicKernelPanic'))"
```

BIOS 侧只能进 BIOS 看：`VT-d / IOMMU` 必须是 `Disabled`。

- **判据**：`VT-d` 仍为 Enabled，**或** `DevirtualiseMmio` 读回 `False`，**或** `ProvideCurrentCpuInfo` 读回 `False` → 就是本故障。

**修法（按顺序做，每改一项重启一次）**
1. BIOS 关 `VT-d / IOMMU`。
2. BIOS 关 `Hyper-Threading`、`Active E-Cores = 0`。
3. `DevirtualiseMmio = True`、`ProvideCurrentCpuInfo = True`、`DisableIoMapper = True`、`LapicKernelPanic = False`。
4. `ACPI → Delete → DMAR = All=True, Enabled=True`（配合关 VT-d 一起看）。

- **复验判据**：关掉 VT-d 重新引导后，日志里**不再出现** `OCA: Deleting table DMAR`，且不再停在 `EB|LOG:EXITBS:START`。细节与社区参照见 [references/boot-hang-diagnosis.md](references/boot-hang-diagnosis.md)。

---

### R03　过了 EXITBS，但冻在 `[AHCI][HBA] start:`

**根因**：时钟非单调（TSC）导致内核早期冻死。`[AHCI][HBA] start:` 只是最后刷在屏幕上的那一行，**不是 SATA 不兼容**。这是本 skill 最贵的一课：本机 B860 的 SATA 一直能用，冻死是补丁缺失。

**验证**

```powershell
# [Win] 看 config 里有没有这两条时钟补丁，以及 Count 是否为 2
python -c "import plistlib;d=plistlib.load(open(r'M:\EFI\OC\config.plist','rb'));[print(p.get('Comment'),'| Enabled=',p.get('Enabled'),'| Count=',p.get('Count'),'| Identifier=',p.get('Identifier')) for p in d['Kernel'].get('Patch',[]) if 'monotonic' in str(p.get('Comment',''))]"
```

- **判据**：上面命令**没有输出**，或任一 `Enabled=False` / `Count≠2` → 就是本故障。
- **反向排查**：如果两条补丁都在且 `Count=2`，冻结点仍固定出现在 AHCI 那一行，才轮到怀疑磁盘通道（此时按 D3 换 NVMe 盘试）。

**修法**：`Kernel → Patch` 里加这两条（1401 不自带，从成功案例抄，`Count` 都是 2，`Enabled=True`）：

```
Identifier = kernel
Comment    = ... | Visual | thread_invoke, thread_dispatch | Remove non-monotonic time panic | 12.0-26.3
Count      = 2    Enabled = True
---
Identifier = kernel
Comment    = ... | laobamac | thread_invoke, thread_dispatch | Remove non-monotonic time panic | 26.4+
Count      = 2    Enabled = True
```

两条都留：`26.4+` 那条覆盖新版本，`12.0-26.3` 那条覆盖旧版本，机器只会命中其中一条，另一条不生效但必须存在。

- **复验判据**：打补丁后内核继续往下滚，直到 `userspace`（不再固定停在 AHCI 那一行）。条目的完整字段见 [references/config-cookbook.md](references/config-cookbook.md)。

---

### R04　到 userspace 后服务全失败

**症状原文（日志里任一条）**
- `setuid/task_for_pid: Operation not permitted`
- `code signature page shift: 14`
- `malformed Mach-O`

**根因（两条叠加）**
1. SIP 值用了 `0x0A43`，缺 `CSR_ALLOW_TASK_FOR_PID`（`0x04`）这一位 → 所有需要 `task_for_pid` 的系统服务直接失败。
2. `AMFIPass.kext` 被误关 —— 它是**必须的**，缺它系统服务全挂。

**验证**

```bash
# [macOS]（能进系统时）
nvram csr-active-config          # 期望 %ff%0f%00%00
csrutil status
kmutil showloaded | grep -i AMFIPass

# [Win]（进不去系统时，直接读 config）
python -c "import plistlib;d=plistlib.load(open(r'M:\EFI\OC\config.plist','rb'));k='7C436110-AB2A-4BBB-A880-FE41995C9F82';print('csr=',d['NVRAM']['Add'][k].get('csr-active-config'));print([p.get('BundlePath') for p in d['Kernel']['Add'] if 'AMFIPass' in str(p.get('BundlePath',''))], [p.get('Enabled') for p in d['Kernel']['Add'] if 'AMFIPass' in str(p.get('BundlePath',''))])"
```

- **判据**：`csr-active-config` 不是 `ff0f0000`，**或** AMFIPass 的 `Enabled` 不是 `True` → 就是本故障。

**修法**
1. `NVRAM → Add → 7C436110-... → csr-active-config = FF0F0000`（即 `0x0FFF`，全关 SIP）。成功参照案例（HP OMEN Arrow Lake）用的就是 `0xFF0F` 这个值。
2. `Kernel → Add` 里 `AMFIPass.kext` 的 `Enabled = True`。
3. 加 `boot-args`：`amfi_get_out_of_my_way=0x1 amfi=0x80 ipc_control_port_options=0`。

- **复验判据**：`nvram csr-active-config` = `%ff%0f%00%00`；`log show --last boot | grep -Ei "task_for_pid|setuid|code signature page shift|malformed Mach-O"` **无输出**；`kmutil showloaded` 能列出 AMFIPass。

---

### R05　OpenCore 菜单只有 `Reset NVRAM`

**根因**：`ScanPolicy` 位掩码算错。手工算出 `0x01070003` 这种值会把 APFS 和 USB 一起过滤掉，菜单自然只剩 `Reset NVRAM`。**位掩码不要手算**。

**验证**

```powershell
# [Win]
python -c "import plistlib;d=plistlib.load(open(r'M:\EFI\OC\config.plist','rb'));print('ScanPolicy=',d['Misc']['Security'].get('ScanPolicy'))"
```

- **判据**：读回值不是 `17760515` 也不是 `0` → 就是本故障。

**修法**：改成官方默认 `17760515`（=`0x010F0103`）或直接用 `0`。
- 排查阶段一律先写 `0`（不过滤，能列出全部 U 盘/系统盘），确认菜单正常后再决定要不要收紧。
- 只有想让 Windows 不出现在菜单里时，才用 `17760515`。
- **永远不要手写位掩码**。

- **复验判据**：重新引导后菜单列出 ≥ 2 项（macOS 安装器 + `Reset NVRAM`）。

---

### R06　每次重启都进 Windows

**根因（两条，可同时存在）**
1. U 盘固件启动项的 GUID 在**重写 U 盘后失效**（GUID 绑在分区/设备实例上，重写就不是原来那个了）。
2. **快速启动（休眠）直接跳过固件启动顺序** → `bcdedit` 设的 `bootsequence` 形同废纸。

**验证**

```powershell
# [Win] 1) 快速启动与休眠状态
powercfg /a
(Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power").HiberbootEnabled

# 2) 固件启动顺序
bcdedit /enum '{fwbootmgr}'
bcdedit /enum firmware

# 3) 硬证据：U 盘根有没有本次新增的引导日志
Get-ChildItem "M:\opencore-*.txt" | Sort-Object LastWriteTime -Descending | Select-Object -First 2 Name,LastWriteTime
```

**判据**：下面任一条成立，就是本故障：
- `HiberbootEnabled` = 1，或 `powercfg /a` 显示休眠可用 → 快速启动没关，就是根因 2。
- `bootsequence`/`displayorder` 第一项不是 U 盘 GUID → 根因 1。
- U 盘根**没有**新增 `opencore-*.txt` → 铁证：固件根本没走 OpenCore。

**修法**
1. 先清障（`powercfg /h off` + `HiberbootEnabled=0`，见 S04）。
2. 重新 `bcdedit /enum firmware` 取**当前** U 盘 GUID，再 `bcdedit /set '{fwbootmgr}' bootsequence '{<当前U盘GUID>}'`。
3. 每重写一次 U 盘，就必须重做一次第 2 步。

- **复验判据**：重启后 U 盘根出现**新的** `opencore-*.txt`（看 `LastWriteTime` 是刚才）。这一条比菜单好不好看重要得多。

---

### R07　抹盘时提示"磁盘已锁定"

**根因**：你在抹 **NTFS 卷**，而 NTFS 被 macOS 只读挂载；卷不可写，所以报锁定。

**验证**：磁盘工具里点该盘 → 右侧「信息」看是「卷」还是「设备」；或在终端：

```bash
diskutil list            # 目标 NTFS 卷显示 Microsoft Basic Data，不是整盘的物理设备行
```

- **判据**：选中的条目在 `diskutil list` 里位于某块盘的**分区行**（如 `disk3s1`）而不是设备行（`disk3`）→ 就是本故障。

**修法**：磁盘工具 → 菜单栏 `显示 → 显示所有设备` → 选**整块盘**（`disk3` 这种）→ 抹成 `APFS` / `GUID 分区图`。

- **复验判据**：分区表出现 `7C3457EF-...`（APFS），`diskutil list` 里出现 `Apple_APFS` Container。

---

### R08　双系统时间差 8 小时

**根因**：macOS 把 RTC 当 UTC 写，Windows 按本地时间读。

**验证**

```powershell
# [Win]
Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\TimeZoneInformation" | Select-Object RealTimeIsUniversal
w32tm /query /status
```

- **判据**：`RealTimeIsUniversal` 不存在或为 0 → 就是本故障。

**修法**

```powershell
reg add "HKLM\SYSTEM\CurrentControlSet\Control\TimeZoneInformation" /v RealTimeIsUniversal /t REG_DWORD /d 1 /f
w32tm /resync
```

- **复验判据**：与网络时间比对，差值 ≤ 1 秒；切到 macOS 再切回 Windows，时间不再漂 8 小时。

---

### R09　驱动装完仍无加速 / 黑屏循环重启

**根因**
1. BIOS 的 `Re-Size BAR` 没开，驱动要 8 GB BAR（这是 MUST，不是可选）。
2. `ResizeAppleGpuBars` / `ResizeGpuBars` 与 BIOS 状态不匹配。
3. 你的卡是 Ampere（RTX 30），厂商设备表状态是 **Pending**（只有 RTX 5060 做过自动化验证）—— 但 **本机 RTX 3070 已实机确认出图 + Metal 可用**（2026-10-24）。`Pending` ≠ 不可用，它只表示厂商没跑过验证。

**验证**

```powershell
# [Win] 两个 BAR 键的当前值
python -c "import plistlib;d=plistlib.load(open(r'M:\EFI\OC\config.plist','rb'));print('Booter.ResizeAppleGpuBars=',d['Booter']['Quirks'].get('ResizeAppleGpuBars'));print('UEFI.ResizeGpuBars=',d['UEFI']['Quirks'].get('ResizeGpuBars'));print('boot-args=',d['NVRAM']['Add']['7C436110-AB2A-4BBB-A880-FE41995C9F82'].get('boot-args'))"
```

```bash
# [macOS]
system_profiler SPDisplaysDataType | grep -Ei "Chipset|VRAM|Metal"
nvram boot-args | tr ' ' '\n' | grep -E "nvfb|nvaccel|nvfbheads|nvkmsnosmooth"
kmutil showloaded | grep -Ei "NVAccel|NVDA"
```

- **判据**：BIOS `Re-Size BAR` 未开，**或** 安装/无驱动阶段 `ResizeAppleGpuBars` 不是 `0`，**或** `Metal` 行为空 → 就是本故障。

**修法（按顺序）**
1. BIOS 开 `Re-Size BAR` + `Above 4G Decoding`。
2. 安装/无驱动阶段：`ResizeAppleGpuBars = 0`；装完驱动后可改 `-1`。
3. BIOS 已开 ReBAR 时 `UEFI → Quirks → ResizeGpuBars = -1`（不需要 OC 再改一次 BAR）。
4. 仍未出图 → 走第六节回滚三层，然后按第七节第 2 条如实告知：Ampere 未物理验证。

---

### R10　系统进去了但没网

**根因**：`RTL812xLucy`（2.5G 网卡驱动）没启用或没加载。本机是 Realtek RTL8125 `10EC:8125`，无无线网卡。

**验证**

```powershell
# [Win] config 里这个 kext 在不在、开没开
python -c "import plistlib;d=plistlib.load(open(r'M:\EFI\OC\config.plist','rb'));[print(p.get('BundlePath'),p.get('Enabled')) for p in d['Kernel']['Add'] if 'RTL' in str(p.get('BundlePath',''))]"
```

```bash
# [macOS]
kmutil showloaded | grep -i rtl
ifconfig -l
networksetup -listallhardwareports
ioreg -l | grep -i 8125
```

- **判据**：config 里 `RTL812xLucy` 缺失或 `Enabled=False`，或 `kmutil showloaded` 里搜不到 → 就是本故障。

**修法**：`Kernel → Add` 启用 `RTL812xLucy.kext`（`Enabled=True`），确保它在 `Lilu` **之后**加载。

- **复验判据**：`ifconfig -l` 出现 `en0` 之类以太网口，`networksetup -listallhardwareports` 能看到对应硬件端口，`ioreg` 命中 8125。

---

## 五、关键配置速查（照抄这一节）

### 5.1 BIOS（8 个读回值必须全对）

| BIOS 项 | 值 | 为什么 |
|---|---|---|
| VT-d / IOMMU | **Disabled** | 卡 `EXITBS` 第一元凶，社区 5+ 用户同一结论 |
| Hyper-Threading | **Disabled** | 混合核心拓扑必须简化 |
| Active E-Cores | **0 (Disabled)** | 同上，CPU 只剩 6C/6T |
| Above 4G Decoding | **Enabled** | 驱动要 8 GB BAR 的前提 |
| Re-Size BAR / Resizable BAR | **Enabled** | 驱动 MUST，缺它不出图 |
| CSM / Legacy Boot | **Disabled** | 纯 UEFI 引导 |
| Secure Boot | **Disabled** | 与 `SecureBootModel=Disabled` 配套 |
| Fast Boot | **Disabled** | 否则固件启动顺序（`bootsequence`）失效 |

逐项核对清单与"某项灰掉怎么办"见 [references/bios-checklist.md](references/bios-checklist.md)。

### 5.2 config.plist 正确值表

| 路径 | 键 | 正确值 | 说明 |
|---|---|---|---|
| Kernel → Quirks | ProvideCurrentCpuInfo | **True** | 混合核 CPU 必须 |
| Kernel → Quirks | DisableIoMapper | **True** | 与关 VT-d 配套 |
| Kernel → Quirks | LapicKernelPanic | **False** | 不要开 |
| Booter → Quirks | DevirtualiseMmio | **True** | **1401 默认 False，方向是反的，必须改** |
| Booter → Quirks | ResizeAppleGpuBars | **0** | 安装/无驱动阶段；装完驱动可改 `-1` |
| Booter → Quirks | SetupVirtualMap | **True** | |
| Booter → Quirks | RebuildAppleMemoryMap | **True** | |
| Booter → Quirks | SyncRuntimePermissions | **True** | |
| UEFI → Quirks | ResizeGpuBars | **-1 或 13** | 本机成功值 **-1**（BIOS 已开 ReBAR，不需要 OC 再改）；驱动 README 与 `patch-config.py --stage driver` 写 **13**（8 GiB BAR）。两个值 `inspect-config.py` 都判 PASS —— 选定一个后**不要来回改**，见附录 C 规定动作 |
| ACPI → Delete | DMAR | **All=True, Enabled=True** | 配合关 VT-d |
| Kernel → Emulate | Cpuid1Data | **55 06 0A 00 ...** | Comet Lake `0x000A0655` 伪装 |
| Kernel → Emulate | Cpuid1Mask | **ff ff ff ff ...** | |
| Kernel → Add | CpuTopologyRebuild.kext | **Enabled=False** | **Arrow Lake 必须关** |
| NVRAM → Add → 7C436110-... | csr-active-config | **FF0F0000**（=0x0FFF） | 全关 SIP，缺位会导致服务全挂 |
| Misc → Security | SecureBootModel | **Disabled** | |
| Misc → Security | ScanPolicy | **17760515** 或 **0** | 不许手算位掩码 |
| PlatformInfo → Generic | SystemProductName | **MacPro7,1** | macOS 15 和 26 都接受 |

### 5.3 两个内核补丁（决定性，1401 不自带）

| Comment 尾部特征 | 覆盖版本 | Count | Enabled |
|---|---|---|---|
| `Visual \| thread_invoke, thread_dispatch \| Remove non-monotonic time panic \| 12.0-26.3` | macOS 12.0–26.3 | 2 | True |
| `laobamac \| thread_invoke, thread_dispatch \| Remove non-monotonic time panic \| 26.4+` | macOS 26.4+ | 2 | True |

两条都必须在，`Count` 都必须是 2。少一条或 `Count≠2` 就会冻死在 `[AHCI][HBA] start:`（见 R03）。

### 5.4 最小 kext 集合（缺一不可）

```
Lilu  /  VirtualSMC  /  AMFIPass  /  AppleMCEReporterDisabler  /
RestrictEvents  /  SMCProcessor  /  SMCSuperIO  /  USBToolBox  /  UTBDefault  /
WhateverGreen  /  RTL812xLucy
```

`AMFIPass` 是**必须的**——缺它系统服务全挂（R04）。`RTL812xLucy` 负责 2.5G 网卡（R10）。完整字段、每项的打开/关闭判据见 [references/config-cookbook.md](references/config-cookbook.md)。

### 5.5 boot-args

安装/诊断阶段（先看到内核日志）：

```
-v keepsyms=1
```

装完驱动后（由 1401 Mac app 调成这一套）：

```
keepsyms=1 revpatch=sbvmm nvfb=1 nvaccel=1 nvfbheads=1 -nvkmsnosmooth
amfi_get_out_of_my_way=0x1 amfi=0x80 ipc_control_port_options=0
```

**禁止出现** `debug=0x100`（它把内核错误静默进调试器，屏幕零输出，见 R01）。
改了 `boot-args` 必须同时把该键加进 `NVRAM → Delete`，否则旧值会赢（日志原文：`OCVAR: Setting NVRAM ...boot-args - ignored, exists`）。

### 5.6 抄完后的自检（一条命令看完所有关键键）

```powershell
python -c "import plistlib;d=plistlib.load(open(r'M:\EFI\OC\config.plist','rb'));k='7C436110-AB2A-4BBB-A880-FE41995C9F82';print('ProvideCurrentCpuInfo',d['Kernel']['Quirks'].get('ProvideCurrentCpuInfo'));print('DevirtualiseMmio',d['Booter']['Quirks'].get('DevirtualiseMmio'));print('DisableIoMapper',d['Kernel']['Quirks'].get('DisableIoMapper'));print('LapicKernelPanic',d['Kernel']['Quirks'].get('LapicKernelPanic'));print('ResizeAppleGpuBars',d['Booter']['Quirks'].get('ResizeAppleGpuBars'));print('ResizeGpuBars',d['UEFI']['Quirks'].get('ResizeGpuBars'));print('SecureBootModel',d['Misc']['Security'].get('SecureBootModel'));print('ScanPolicy',d['Misc']['Security'].get('ScanPolicy'));print('ProductName',d['PlatformInfo']['Generic'].get('SystemProductName'));print('csr',d['NVRAM']['Add'][k].get('csr-active-config'));print('bootargs',d['NVRAM']['Add'][k].get('boot-args'));print('deleted',k in d['NVRAM'].get('Delete',{}))"
```

**判据**（逐项比对 5.2，一个都不许含糊）：

```
ProvideCurrentCpuInfo True
DevirtualiseMmio      True
DisableIoMapper       True
LapicKernelPanic      False
ResizeAppleGpuBars    0        (装完驱动可 -1)
ResizeGpuBars         -1       (本机成功值) 或 13 (驱动 README / --stage driver)
Block                 空       (本机成功配置未屏蔽 IONDRVSupport；驱动 README 要求屏蔽，两种都记录)
SecureBootModel       Disabled
ScanPolicy            17760515 或 0
ProductName           MacPro7,1
csr                   ff0f0000
bootargs              含 -v keepsyms=1（安装阶段）
deleted               True     ← boot-args 在 NVRAM → Delete 名单里
```

---

## 六、显卡驱动安装与回滚

驱动仓库 `nullmoth/nvidia-macos-driver`，Linux 侧支持 macOS 15 与 26（`install.sh` 门禁写死 `case $MAJ in 15|26)`），加速组件按版本分叉：`kexts/15`、`kexts/26`。驱动许可 **PolyForm Noncommercial**（禁止商用，必须告知）。

### 6.0 前置（不可省）

```powershell
# [Win] 整份 EFI 备份到 Windows 侧 = 回滚第三层
Copy-Item "M:\EFI" "C:\<WORK>\EFI-pre-driver-$(Get-Date -f yyyyMMdd-HHmmss)" -Recurse -Force
# 记录装驱动前的 kexts 清单
Get-ChildItem "M:\EFI\OC\Kexts" -Directory | Select-Object -Expand Name | Set-Content "C:\<WORK>\kexts-before.txt"
```

- **判据**：`EFI-pre-driver-*\OC\config.plist` 与 `kexts-before.txt` 都存在。

### 6.1 路线 A：Mac app 装（推荐，自带回滚菜单项）

动作：在 macOS 里打开 `1401-Mac-<ver>.zip` 解出的 app，跑一键安装。它会改 OpenCore 配置、写 `boot-args`、并**往 OpenCore 菜单里加回滚项**。

**验收**（三条全中才算成功）：
1. `nvram boot-args` 逐词核对 5.5 那一整串，缺一词即未装成；其中最关键的 `nvfb=1`、`nvaccel=1`、`nvfbheads=1`、`-nvkmsnosmooth`、`amfi=0x80` 必须各自出现
2. `system_profiler SPDisplaysDataType | grep -Ei "Chipset|VRAM|Metal"` → GPU 型号出现且 `Metal` 行**非空**
3. 实机出图三连测：截图正常、窗口拖动不撕裂、播放 1080p 视频 5 分钟不冻

- **判据**：任一条不过 → 6.3 回滚，不许自称"驱动成功"。Ampere 未物理验证，三连测是唯一证据。

### 6.2 路线 B：`tar.gz` + `install.sh`（无 Mac app 时）

```bash
# [macOS] 解压驱动包后
sw_vers -productVersion          # 主版本必须是 15 或 26，否则 install.sh 会直接退出
cd <解压目录>
sudo ./install.sh
```

- **判据**：脚本没有因版本门禁退出（`case $MAJ in 15|26)` 不匹配会立刻结束）；跑完 `kmutil showloaded | grep -Ei "NVAccel"` 命中。
- **失败跳转**：`sw_vers` 主版本不是 15/26 → 驱动不支持该系统版本，停手，回滚，如实告知。

### 6.3 回滚三层（从软到硬，按顺序试）

**第一层：OpenCore 菜单回滚项**
动作：重启 → OpenCore 菜单选 1401 Mac app 加的那一项（名字含 rollback / 回滚）→ 引导。
- **判据**：进系统后 `nvram boot-args` 里 `nv*` 参数消失，或 `system_profiler` 不再显示该 GPU 加速项。

**第二层：一键卸载脚本**
动作：U 盘 `NullMoth\` 下的 `一键回滚-卸载驱动.command`，在 macOS 里双击；或终端 `sudo bash "<路径>/一键回滚-卸载驱动.command"`。
- **判据**：脚本输出卸载完成；`kmutil showloaded | grep -Ei "NVAccel"` **无输出**；重启后仍能进系统。

**第三层：离线还原（macOS 完全进不去时的唯一出路）**

```powershell
# [Win] 1) 停用/清空 U 盘的 config，换回装驱动前那份
Copy-Item "C:\<WORK>\EFI-pre-driver-<ts>\OC\config.plist" "M:\EFI\OC\config.plist" -Force

# 2) 把驱动 kext 从 Kernel → Add 里删掉（或至少 Enabled=False），并从 Kexts 目录移走
#    先用 S10 的 plistlib 自检确认 boot-args 里没有 nv* 残留、Kernel.Add 里没有驱动条目
python -c "import plistlib;d=plistlib.load(open(r'M:\EFI\OC\config.plist','rb'));k='7C436110-AB2A-4BBB-A880-FE41995C9F82';print('bootargs=',d['NVRAM']['Add'][k].get('boot-args'));print([p.get('BundlePath') for p in d['Kernel']['Add']])"
```

- **判据**：用这份 config 能正常引导进系统；`boot-args` 里没有任何 `nv*` 参数；`Kernel → Add` 里没有驱动条目。

三层的关系：第一层最快但依赖菜单项，第二层依赖还能进系统，第三层只在"完全进不去"时用。**装驱动前那一份 EFI 副本是第三层的前提**，所以 6.0 不可省。更多细节见 [references/nullmoth-driver.md](references/nullmoth-driver.md)。

---

## 七、必须诚实告知用户的三件事

讲在前头，不要等失败后再说。

1. **Arrow Lake（Core Ultra 200S/H/HX）苹果从未支持。**
   社区已跑通的参照是 `github.com/Coolzhy/EFI-OMEN16-am2xxx-public`（Core Ultra 7 255HX + RTX 5060 Laptop + macOS 26）——**CPU 型号与你的不同**，同一套组合拳不等于同一结果。本机 245K 实测跑通，但换 265K/285K、换主板，必须按第二节重新判档、重新验证。可承诺的是"流程与配置这套是对的"，不可承诺的是"你这台也一定行"。

2. **Ampere（RTX 30）未物理验证。**
   驱动设备表覆盖 Turing 及以后（GTX16 / RTX20 / RTX30 / RTX40 / RTX50），厂商自动化验证过的只有 RTX 5060；Ampere 在表里是 **Pending**，**但本机 RTX 3070 已实机确认出图 + Metal 可用（2026-10-24）**。RTX 3070 装得上、进得去、能不能出图必须实机三连测（6.1）才有答案。用户问"能不能用"时，答案是"必须实测"，不是"应该可以"。

3. **SATA 与 NVMe 的差异是真实的，但别误判。**
   优先 M.2 NVMe（走 `AppleNVMe` 通用 PCIe 驱动，路径最干净）。SATA AHCI 在新 PCH（600/700/800 系）上风险更高；但**本次实战证明 B860 的 SATA 可以工作**——冻在 `[AHCI][HBA] start:` 那一行其实是时钟补丁缺失（R03），不是 SATA 不兼容。把这条讲清楚，能省掉用户换盘的钱和两天时间。

另外三条边界必须主动说：驱动许可 **PolyForm Noncommercial 禁止商用**；本 skill **不覆盖音频**（ALC897 不在已验证的最小 kext 集合里，要音频另做 AppleALC 方案）；GitHub 直连在本网络实测 1.6 KB/s，一切下载走 `https://gh-proxy.com/https://github.com/...`。

---

## 八、常见坑清单（别做什么 / 为什么 / 正确做法）

1. **别带 `debug=0x100` 引导。** 它把内核错误静默进调试器，屏幕零输出、没日志、看起来像"卡在菜单"。正确做法：诊断阶段只用 `-v keepsyms=1`（R01）。
2. **别只改 config 里的 `boot-args` 而不加 `NVRAM → Delete`。** NVRAM 旧值会赢，日志写 `ignored, exists`，你以为改了其实没改（R01）。
3. **别开着 VT-d 试引导。** 这是卡 `EB|LOG:EXITBS:START` 的第一元凶，社区 5+ 用户同一结论（R02）。
4. **别留 Hyper-Threading 和 E 核。** 混合核拓扑不简化就过不去；关完 CPU 只剩 6C/6T 是**正常**的，不是坏了（R02）。
5. **别信 1401 默认的 `DevirtualiseMmio=False`。** 方向是反的，必须改 `True`（R02）。
6. **别手算 `ScanPolicy` 位掩码。** `0x01070003` 这种值会把 APFS/USB 一起过滤掉，菜单只剩 `Reset NVRAM`。用 `17760515` 或 `0`（R05）。
7. **别在双系统上留快速启动/休眠。** `powercfg /h off` + `HiberbootEnabled=0`；否则 `bcdedit` 的 `bootsequence` 形同废纸，每次重启都进 Windows（R06）。
8. **别在 macOS 里抹 NTFS 卷。** 只会得到"磁盘已锁定"。要 `显示所有设备` → 选整块盘 → APFS/GUID（R07）。
9. **别用 `0x0A43` 这种 SIP 值。** 缺 `CSR_ALLOW_TASK_FOR_PID`（`0x04`）→ `setuid/task_for_pid: Operation not permitted`、`code signature page shift: 14`、`malformed Mach-O` 全来了。用 `FF0F0000`（R04）。
10. **别关 `AMFIPass`。** 它是必须的，缺它系统服务全挂（R04）。
11. **别用老版本 1401。** 老版本缺混合核心修复，直接卡 EXITBS。永远用最新版（S06）。
12. **别直连 GitHub 下东西。** 本网络实测 1.6 KB/s，等于不可用；走 `gh-proxy.com` 镜像（实测 400–4400 KB/s）（S05）。
13. **别在写安装盘时开着 Clash 系统代理。** 会掐断 `osrecovery.apple.com` 的 TLS，报 `SSL: UNEXPECTED_EOF_WHILE_READING`。写盘前 `ProxyEnable=0`（S05）。
14. **别忘两个时钟补丁、别把 `Count` 写成 1。** 冻在 `[AHCI][HBA] start:` 就是它，`Count` 必须是 2（R03）。
15. **别删 `CpuTopologyRebuild`，要关它。** Arrow Lake 上必须 `Enabled=False`（5.2）。
16. **别用盘符或 Index 认盘。** 盘符会变、Index 会变，序列号不会。认错一块盘 = 抹掉用户数据（铁律 3）。
17. **别把驱动当商用方案。** PolyForm Noncommercial，禁止商用，必须提前说（第六节）。
18. **别一次改一堆配置。** 一个变量一次重启，否则出问题无法归因——四天里一半时间花在这上面（铁律 7）。

---

## 附录 A　产出物位置（本次实战，可直接沿用）

```
U 盘 (<U盘盘符>，本次 M:)
  EFI/OC/config.plist                       当前配置
  EFI/OC/config.plist.bak-<时间戳>          自动/手工备份
  NullMoth/                                 驱动包 + Mac app + 说明
  opencore-*.txt                            每次启动的引导日志（诊断金矿）
  一键安装显卡驱动.command / 一键回滚-卸载驱动.command / 粘贴即用-命令行.txt

Windows 侧
  C:\<WORK>\                      所有脚本、备份、EFI-pre-driver、台账
  G:\1401-new\                              最新 1401 + 驱动
  G:\1401-2.3.3\                            本次实际用过的 1401（只作参照，不要再用）
  C:\Users\<USER>\Documents\macOS-install-kit\  文档与报告
```

**诊断第一入口永远是** `<U盘>\opencore-*.txt`：按 `LastWriteTime` 取最新那份，`Select-String` 搜 `EXITBS`、`ignored, exists`、`Deleting NVRAM`、`OCA:`、`panic`。

## 附录 B　参考文件索引（什么时候打开哪一份）

| 文件 | 打开时机 |
|---|---|
| [references/hardware-matrix.md](references/hardware-matrix.md) | 第二节判档位时；要查某 CPU/GPU/网卡能不能用时 |
| [references/boot-hang-diagnosis.md](references/boot-hang-diagnosis.md) | 第四节定位到 R02/R03 需要更细的分支与日志特征时 |
| [references/config-cookbook.md](references/config-cookbook.md) | 第五节每个键的完整字段、补丁的 Original/Replace、kext 顺序 |
| [references/bios-checklist.md](references/bios-checklist.md) | S03 逐项核对、某项灰不可改时 |
| [references/nullmoth-driver.md](references/nullmoth-driver.md) | 第六节两条路线、验收、三层回滚的完整步骤 |
| [references/case-arrow-lake-245k.md](references/case-arrow-lake-245k.md) | 需要完整四天时间线、失败-根因对照、装配了什么才通的时候 |

文档与事实版本戳：事实来源 `_FACTS.md`（2026-10-20 实战蒸馏）。本文件仅做转译与编排，不引入任何 `_FACTS.md` 之外的型号、版本或数字；发现冲突以 `_FACTS.md` 为准并当场修正本文件。

---

## 附录 C　脚本工具集（scripts/，能跑就别手改）

配置改动一律走脚本：它带备份、写后重新解析校验、幂等、能做语义 diff。手改 plist 是四天里最大的时间黑洞之一。

| 脚本 | 在哪跑 | 一条命令 | 什么时候用 |
|---|---|---|---|
| scripts/inspect-config.py | Windows / macOS | python scripts/inspect-config.py <config.plist> | **每次改完配置、每次重启前**。输出逐项 PASS/FAIL/WARN + 修法；--json 给机器读；--quiet 只看结论；--self-test 验判定引擎本身。退出码 0=无 FAIL，1=有 FAIL，2=文件坏了 |
| scripts/patch-config.py | Windows / macOS | python scripts/patch-config.py apply-preset <config.plist> --stage install / --stage driver | 装系统阶段与装驱动阶段的两套值切换。先备份成 config.plist.bak-<yyyyMMdd-HHmmss>，写完重新 plistlib 校验，重复跑是幂等的 |
| 同上，单点修 | 同上 | set-csr FF0F0000 / set-boot-args ... / set-quirk <路径> <值> / block-iondrv / unblock-iondrv / show / show-diff | 铁律 7（一次只动一个变量）时的标准工具；show-diff 出语义 diff，--dry-run 不落盘 |
| scripts/diag-recovery.sh | **macOS 恢复环境/安装器终端** | sh /Volumes/<U盘>/scripts/diag-recovery.sh（或拷到 U 盘根目录跑） | 硬盘上的系统起不来、但恢复环境界面正常时。自动找含 EFI/OC 的卷，把 8 段诊断（版本/内核缓存/Extensions/NullMoth/日志/nvram/diskutil）写进该卷 diag.txt，拿回 Windows 分析 |
| scripts/make-oneclick-driver.sh | **macOS** | ./make-oneclick-driver.sh --usb /Volumes/<U盘> | 生成「双击即装驱动」的 .command（备份配置→屏蔽 IONDRVSupport→BAR 值→解压→shasum -c→install.sh→重启）。生成的脚本不依赖 python3 |
| scripts/verify-macos.sh | **macOS** | ./verify-macos.sh | 装完驱动后的 10 组 PASS/FAIL 验收：4 个 nullmoth kext、Metal、IOAccelerator、boot-args、SIP、显示器。第一次跑别加 -q，留整段输出 |

三个 .sh 的实测边界（脚本作者已标注，照实传达）：diag-recovery.sh 与生成的 .command **没在真 macOS 上跑过**（只在结构/语义层验证），上机第一步先 bash -n 或 sh -n；verify-macos.sh 依赖 system_profiler 文案，若 grep 对不上按实际输出微调。详见 scripts/README.md 第 9 节。

**规定动作**：SOP 里凡是"改 config"的步骤，命令一律用 patch-config.py；凡是"改完要看对不对"的步骤，一律用 inspect-config.py（而不是靠眼睛读 XML）。