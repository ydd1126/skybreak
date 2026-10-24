# 硬件兼容性矩阵（Intel 8–14 代 / Arrow Lake / AMD Ryzen × NVIDIA Turing+）

> **标注约定**：`[实测]` = 本机（Gigabyte B860M POWER / Core Ultra 5 245K / RTX 3070 / macOS 26.7.1 25G241）真跑过；
> `[厂商]` = 厂商或上游文档/源码（NullMoth README、CARD-SUPPORT.md、OpenCore、Apple xnu）；
> `[社区]` = 社区报告，本机没复现；`未实测` = 本 skill 只能给判断、没验证过的项。
> 事实来源：本 skill `_FACTS.md` + `C:\Users\<USER>\Documents\macOS-install-kit\` 下的实测日志。

## 0. 风险等级怎么用

| 等级 | 含义 | 你要做的动作 |
|---|---|---|
| 低 | 按 `config-cookbook.md` 照抄就能工作 | 不用额外验证 |
| 中 | 能工作，但要改 config / BIOS，或依赖某个 kext | 做完必须跑「验收命令」 |
| 高 | 官方完全不支持，靠组合拳；可能根本起不来 | 先按 `boot-hang-diagnosis.md` 准备回滚，再动手 |

## 1. CPU

| CPU 世代 | 代表型号 | 结论 | 依据 | 风险 |
|---|---|---|---|---|
| Skylake→Comet Lake（6–10 代） | i5-9400 / i7-10700 | 官方指南覆盖，最稳 | dortania 配置指南止于 Comet Lake `[厂商]` | 低 |
| Alder Lake（12 代，混合核） | i5-12400 / i7-12700K | 可跑，但必须 `ProvideCurrentCpuInfo=True`；E 核/HT 是常见坑 | `_FACTS` §二、§五；同族 245K 实测可推 `[实测]`/`[社区]` | 中 |
| Raptor Lake（13/14 代） | i5-13600K / i9-14900K | 与 12 代同一类，同样吃 `ProvideCurrentCpuInfo` + 时钟补丁 | `_FACTS` §五 `[社区]`；本机未装过 13/14 代 → `未实测` | 中 |
| **Arrow Lake-S（Core Ultra 200S）** | **Ultra 5 245K（本机）** | **苹果从未支持，但组合拳可跑通**：关 VT-d + 关 HT + E 核=0 + `ProvideCurrentCpuInfo` + `DevirtualiseMmio=True` + 两个 non-monotonic 补丁 | `_FACTS` §二/§三，四天实测 `[实测]` | 高 |
| Arrow Lake-H/HX（移动） | Core Ultra 7 255HX | 有成功参照机（OMEN 16 + RTX 5060 + macOS 26） | <https://github.com/Coolzhy/EFI-OMEN16-am2xxx-public> `[社区]` | 高 |
| Meteor Lake（Core Ultra 1xx） | Ultra 7 155H | 混合核同族，但核显无驱动、移动平台输出路由未解；只可能「独显 + 外接屏」路线 | `[厂商]` CARD-SUPPORT 的 Optimus 说明；本项目 `未实测` | 高 |
| Lunar Lake（Core Ultra 200V） | Ultra 7 258V | 同上，且板载 LPDDR 不可换、无 SATA，装机面更窄 | 推断，`未实测` | 高 |
| AMD Ryzen 1000–5000 | R5 3600 / R7 5800X | 走 AMD 专用内核补丁路线，核显无加速 | dortania AMD 章节 `[厂商]`，本项目 `未实测` | 中 |
| AMD Ryzen 7000/9000 | R7 7800X3D / R9 9950X | 固件内存映射特殊：`EB.MM.AKM`、`STOP 0x16`、`Couldn't allocate runtime area` 高发，需最新 1401 的内存设置 | NullMoth `TROUBLESHOOTING.md` §2 `[厂商]` | 高 |

**混合核必读**：本机实测把 HT 关掉、Active E-Cores 设 0 之后只剩 6C/6T，是能进系统的配置之一（`_FACTS` §二）。
不想降核的话，先按 `boot-hang-diagnosis.md` 的 S02/S03 处理，别一上来就关核。

## 2. GPU（NVIDIA，驱动设备表 vs 物理验证）

设备表来自 NVIDIA 610.57.04 的 235 个 display PCI ID（`[厂商]` CARD-SUPPORT.md，仓库 <https://github.com/nullmoth/nvidia-macos-driver>），**设备表命中 ≠ 能出图**。

| 家族 | 设备表 | 物理验证状态（厂商原文） | 我们的判断 | 风险 |
|---|---|---|---|---|
| Turing | GTX 1650/1660、RTX 20、TITAN RTX、Quadro T1000/RTX | `Pending` | 可试；Turing 需 `nvrmsettle=10000` 兜 Display 起来慢 | 中 |
| Ampere（含 **RTX 3070 `10DE:2488` SUBSYS `1458:404E`**） | RTX 30、RTX A 系列 | `Pending` | **本机就是这块卡：能不能出图必须实机验证** `未实测` | 高 |
| Ada | RTX 40、受支持工作站卡 | `Pending` | 可试；RTX 40 曾有 SecurityAgent/Installer 崩溃，1.14.2 已修 | 中 |
| Blackwell | RTX 50、RTX PRO | `RTX 5060 automated`；`RTX 5070/5080 reported working` | 唯一被自动化验证的一代 | 低 |
| Pascal/Maxwell/Kepler 及更早 | GTX 10 及以前 | 不在本驱动范围 | 只能基础显示，无加速（`[厂商]` TROUBLESHOOTING §5） | 高 |
| Intel 核显 `8086:7D67`（Arrow Lake iGPU） | — | 无任何 macOS 驱动 | 只当固件帧缓冲（GOP）用；**别**加 `AAPL,ig-platform-id` | 高 |
| AMD RX 7000/9000、Intel Arc/Iris Xe、Ryzen AI | — | 无加速 | 基础显示可用；AMD/Intel 加速属 1401 的 test 功能，NPU 固件未 ready | 高 |

**本机结论**：RTX 3070 属 Ampere → 装完驱动后**必须**自己确认出图，验收方法见 `nullmoth-driver.md` §4。
Bar 条件是硬要求：BIOS `Re-Size BAR = Enabled` + `Above 4G Decoding = Enabled`，否则 8 GB BAR 拿不到。

## 3. 存储

| 类型 | 结论 | 依据 | 风险 |
|---|---|---|---|
| M.2 NVMe | **首选**，走 macOS 原生 `AppleNVMe`，不需要额外 kext | `_FACTS` §五 `[社区]` | 低 |
| SATA AHCI（Intel 600/700/800 系 PCH） | 能用，但「卡在 `[AHCI][HBA] start:`」常被误判成 SATA 不兼容 | **本机 B860 的 SATA 实测可工作**；那行是时钟补丁问题 `[实测]` | 中 |
| Intel RST / RAID 模式 | 不要用，macOS 看不到盘 | `[厂商]` dortania；本机 BIOS `SATA Mode=AHCI` | 高 |
| USB 安装盘 | 必须 `HfsPlus.efi` + `ScanPolicy` 含 USB 位（`0x00200000`），否则安装盘不出现 | `_FACTS` §三 + dortania ScanPolicy `[厂商]` | 中 |
| APFS 识别 | 抹盘后分区类型应为 `7C3457EF-...`（APFS） | `_FACTS` §三 | 低 |

本机磁盘身份（**装机前用序列号核对，别认错盘**，`_FACTS` §一）：

| 磁盘 | 型号 | 总线 | 序列号 | 用途 |
|---|---|---|---|---|
| disk3 | SAMSUNG SM841 256G | SATA | `SERIAL_DISK3_REDACTED` | **Windows 系统盘，别动** |
| disk4 | ADATA SU800 256G | SATA | `SERIAL_DISK4_REDACTED` | **macOS 系统盘（APFS）** |
| disk6 | Generic U 盘 59.5G | USB | `SERIAL_USB_REDACTED` | OpenCore 安装盘（M:） |
| disk0/1/2/5 | 750 EVO 120G / WD20EZRZ / WD20PURX / APPLE SM0512F 500G | SATA | 见 `_FACTS` | 数据盘，不参与系统 |

## 4. 网卡 / 声卡 / USB

| 设备 | 本机 ID | 用什么 | 依据 | 风险 |
|---|---|---|---|---|
| Realtek RTL8125 2.5GbE | `10EC:8125` | **最终配置：`RTL812xLucy.kext` 1.1.100**（`[实测]`，读自 `M:\EFI\OC\Kexts`）；手工 EFI 阶段曾用 `LucyRTL8125Ethernet.kext` 1.2.300（BUILD-NOTES §8.7，**未采纳**） | `_FACTS` §二 只给 kext 名 `RTL812xLucy`；版本以真配置实读为准 | 低 |
| Realtek RTL8111（1GbE） | — | `RealtekRTL8111.kext`，**不覆盖 8125** | `_FACTS` 未列此卡；BUILD-NOTES 明确二者不同 | 低（本机不用） |
| Intel 有线 | — | `IntelMausi.kext`，本机无 Intel 网卡 | 同上 | 低（本机不用） |
| 无线网卡 | 本机**无** | — | `_FACTS` §一 | — |
| 蓝牙 | 未确认芯片 | 本机未加任何蓝牙 kext，**不要当成可用** | `未实测` | 高 |
| 声卡 ALC897 | `10EC:0897`（HDA 控制器 `8086:7F50`） | `AppleALC` + `layout-id = <0B000000>`（layout 11，"Custom ALC897 by Sergey_Galan for GIGABYTE Z590M"） | BUILD-NOTES §8.6；本机未验证出声 → `未实测` | 中 |
| NVIDIA HDMI 音频 | `10DE:009E` | **驱动不支持** HDMI/DP 音频 | `[厂商]` BODY-v1.14.2.md「Still open」 | 高 |
| USB xHCI | `8086:7F6E` | 先裸跑原生 XHCI，装完再做 `UTBMap`；`XhciPortLimit=false` | `_FACTS` §二；`UTBDefault` 会套通用表导致端口消失 | 中 |

ALC897 备选 layout（`[厂商]` AppleALC 1.9.8 自带注释）：`11` / `12`（GIGABYTE Z590 Gaming X）/ `98`（MSI PRO B760M-P）/ `66` / `97`；
换法是在 boot-args 尾部加 `alcid=12`（会覆盖 `layout-id`），并同步 `NVRAM → Delete`。

## 5. 一眼判断：这台机器值不值得装

| 情况 | 结论 |
|---|---|
| 有 NVIDIA Turing 及以后独显 + Intel 8–15 代 + NVMe | 值得装；按本 skill 的 Arrow Lake 组合拳裁剪即可 |
| 只有核显（Intel Xe / Arrow Lake iGPU / AMD APU） | 能进系统但**没有图形加速**，日常不可用 |
| 笔记本且屏幕走 Optimus mux | 先确认外接屏是否直连独显，否则内屏永远黑（`[厂商]` CARD-SUPPORT.md） |
| 主板只有 Intel RST 且 BIOS 拿不到 AHCI | 不要装 |
| ARM (Apple Silicon) 或 macOS 不支持的 PCH + 无独显 | 不要装 |

## 6. 快速核实命令（装机前跑一遍）

Windows（PowerShell，本机已验证可用）：

```powershell
Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors
Get-CimInstance Win32_VideoController | Select-Object Name,PNPDeviceID,AdapterRAM
Get-CimInstance Win32_PnPEntity | Where-Object InstanceId -like 'PCI\VEN_10DE*' | Select-Object Name,InstanceId
Get-Disk | Select-Object Number,FriendlyName,BusType,SerialNumber,Size
Get-PhysicalDisk | Select-Object DeviceId,MediaType,BusType,HealthStatus
```

macOS（装好之后）：

```bash
system_profiler SPHardwareDataType | head -20
system_profiler SPDisplaysDataType | head -30
ioreg -l | grep -i '"model"' | head -5
kmutil showloaded --list-only | grep -Ei 'lilu|virtualsmc|whatevergreen|luc'
```

1401 CLI（扫硬件 → 出报告，再喂给构建）：

```bash
python -m p1401 build <Report.json> <ACPI dir> <out> --macos 24|25 --boot-log <日志>
```

> 注意：`--macos` 只有 `24|25` 两个值（`_FACTS` §四）。装 macOS 26 的路子是先装 15 再 OTA/新盘，不在 CLI 参数里。
