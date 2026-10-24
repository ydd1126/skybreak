# BIOS 设置清单（九项必设 + 四品牌菜单差异 + 找不到选项怎么办）

> **标注约定**：`[实测]` = 本机 Gigabyte **B860M POWER**（AMI BIOS **F10**，2026-02-02）上真实做过；
> `[厂商]` = 主板/上游文档；`[社区]` = 社区通行说法；`未实测` = 没在对应品牌上验证过。
> 结论先行：**Arrow Lake + 混合核这台机器，BIOS 的 VT-d / HT / E 核三项直接决定能不能过 `EXITBS`**，
> 不是「config 调一调就行」的问题（`_FACTS` §二/§三）。

## 1. 九项必设值（照抄这张表）

| # | 项目 | 目标值 | 为什么 | 错了会怎样 | 装完能恢复吗 |
|---|---|---|---|---|---|
| 1 | **VT-d / IOMMU** | `Disabled` | 社区 5+ 用户同一结论；本机不关必卡 `EXITBS` | 卡在 `EB\|LOG:EXITBS:START`（S02） | **不建议**：除非你要在 Windows 里跑 Hyper-V/WSL2 直通 |
| 2 | **Hyper-Threading** | `Disabled` | 混合核拓扑简化，本机实测只剩 6C/6T 才稳定 | 卡 EXITBS 或启动后计时器/调度异常 | 可尝试恢复（先按 §5 验证稳定性） |
| 3 | **Active E-Cores** | `0`（Disabled） | 同上，E 核是另一处拓扑坑 | 同上 | 同上 |
| 4 | **Above 4G Decoding** | `Enabled` | 显卡显存窗口要映射到 4 GB 以上（驱动 README 硬要求：<https://github.com/nullmoth/nvidia-macos-driver>） | 装完驱动黑屏；卡 `PCI configuration`（S07） | **不能**，驱动硬要求 |
| 5 | **Re-Size BAR / Resizable BAR** | `Enabled`（只有 `Auto` 就选 `Auto`） | 驱动要 8 GB BAR，MUST | 拿不到大 BAR → 桌面起不来/黑屏 | **不能** |
| 6 | **CSM / Legacy Boot** | `Disabled` | CSM 会引入传统 VGA 路径，破坏 GOP 帧缓冲 | 黑屏/卡 PCI configuration | 保持关闭 |
| 7 | **Secure Boot** | `Disabled` | Apple Secure Boot / 未签名 kext 全被拦 | 驱动 kext 加载失败 | 保持关闭（除非你重新签名全套） |
| 8 | **Fast Boot** | `Disabled` | 保证 POST 阶段枚举到 U 盘 | U 盘启动项时有时无 | 可以恢复（但会再次遇到枚举问题） |
| 9 | **SATA Mode** | `AHCI` | Intel RST/RAID 下 macOS 看不到盘 | 安装器里没有硬盘 | **不能**（Windows 侧需先切驱动） |

附加两项（不属九项，但会咬人）：

| 项目 | 目标值 | 说明 |
|---|---|---|
| 主显示输出（Primary Display / Initial Display Output） | `PCIe / PEG`（独显）或直接关核显 | 本机核显 `8086:7D67` 无 macOS 驱动，只当固件帧缓冲用 `[实测]` |
| CFG Lock（MSR 0xE2） | 能解锁就解锁 | 解锁后把 `AppleXcpmCfgLock` 改 `false`；不确定就保持 `true`（可用包内 `ControlMsrE2.efi` 查） |

## 2. 四品牌菜单位置差异

> 只有 Gigabyte B860M POWER 那一行是 `[实测]`；其余是同代 AMI BIOS 的通行位置，`[社区]`/`未实测`，只能当路标。

| 品牌 | VT-d / IOMMU | Above 4G + Re-Size BAR | CSM | Secure Boot | Fast Boot | 备注 |
|---|---|---|---|---|---|---|
| **技嘉 Gigabyte**（本机 F10）`[实测]` | `Settings → IO Ports → VT-d`（也可能在 `Miscellaneous`） | `Settings → IO Ports → Above 4G Decoding` / `Re-Size BAR Support` | `Boot → CSM Support` | `Boot → Secure Boot` | `Boot → Fast Boot` | 某些 F 系列 BIOS 里 IOMMU 名字就叫 `IOMMU`，和 VT-d 是同一项 |
| 华硕 ASUS | `Advanced → System Agent (SA) Configuration → VT-d` | `Advanced → PCI Subsystem Settings → Above 4G Decoding` / `Re-Size BAR Support` | `Boot → Launch CSM` | `Security → Secure Boot → OS Type = Other OS` | `Boot → Fast Boot` | 消费级板常把 SA 页藏起来，要先进 `Advanced` 再 `F7` 切高级模式 |
| 微星 MSI | `Advanced → Integrated Graphics / PCI Subsystem → VT-d` | `Settings → Advanced → PCI Subsystem Settings` 里两项同名 | `Settings → Advanced → CSM Configuration` | `Settings → Security → Secure Boot` | `Settings → Boot → Fast Boot` | 老一点的 MSI 板叫 `Above 4G memory/Crypto Currency mining` |
| 华擎 ASRock | `Advanced → Chipset Configuration → VT-d` | `Advanced → Chipset Configuration → Above 4G Decoding` | `Boot → CSM` | `Security → Secure Boot` | `Boot → Fast Boot` | 华擎有些板把 VT-d 放在 `Advanced → North Bridge` 下 |

## 3. 找不到选项怎么办（按代价从低到高）

| 手段 | 做法 | 风险 | 来源 |
|---|---|---|---|
| 换入口层级 | 先把 BIOS 切到「高级模式」（华硕 `F7`、微星 `F7`、技嘉 `F2`），很多项只在高级模式出现 | 无 | `[社区]` |
| 换名字找 | 同一功能不同叫法：`IOMMU`=`VT-d`；`Resizable BAR`=`Re-Size BAR`=`CAM`；`Above 4G`=`4G Decoding`；`CSM`=`Launch CSM` | 无 | `[社区]` |
| 从「超频页」找 | VT-d/IOMMU 常被放在 `Advanced CPU Configuration` / `AI Tweaker` / `OC` 这类页而不是 PCI 页 | 无 | `[社区]` |
| 看厂商手册 | 每块板每年 BIOS 都会挪位置，官网 PDF 比论坛贴靠谱 | 无 | `[厂商]` |
| 用软件侧面确认 | 见 §5：`msinfo32`、`Get-CimInstance`、GPU-Z 都能反推 BIOS 是否生效，不必死盯着菜单 | 无 | `[实测]` |
| 用 1401 的 Check this PC | 它会扫硬件并给出报告，看不出 VT-d 但能告诉你显卡/CPU 有没有被认成「无名设备」 | 无 | `[厂商]` |
| 解隐藏项（AMIBCP / mod BIOS） | 只能改固件文件再刷，刷坏要 SPI 编程器救 | **高**：本 skill 不建议为装 macOS 冒这个险 | `[社区]` |
| `setup_var`（UEFI Shell 改固件变量） | 用 `OpenShell.efi` + `setup_var 0x… 0x0` 直接改变量 | **高**：偏移随 BIOS 版本变，写错=变砖 | `[社区]` `未实测` |

## 4. 改完顺序（别一次全改）

1. 先只改 **VT-d 关** → 重启试一次（这一步就能让日志里 `OCA: Deleting table DMAR` 消失）。
2. 还卡 EXITBS 再加 **HT 关 + E 核 0**。
3. 最后改 **Above 4G / ReBAR / CSM**（这三项是装驱动阶段的事，安装阶段改了也不会好也不会坏）。
4. 每改一次只改一项，并记下 U 盘里新生成的 `opencore-*.txt` 文件名——**这是唯一能证明「改动真的生效」的证据**。

## 5. 侧面验证命令（不用进 BIOS 也能知道设置对不对）

Windows（本机可用）：

```powershell
# 是否还有「快速启动」在生效
powercfg /a
Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' -Name HiberbootEnabled

# 虚拟化/IOMMU 相关状态（VT-d 关了这里会显示未启用基于虚拟化的安全性）
msinfo32
# 或命令行侧写
(Get-CimInstance Win32_ComputerSystem).HypervisorPresent
Get-CimInstance -ClassName Win32_DeviceGuard -Namespace root\Microsoft\Windows\DeviceGuard |
  Select-Object VirtualizationBasedSecurityStatus,SecurityServicesRunning

# 固件启动项（配合 S05）
bcdedit /enum firmware | Select-String -Pattern 'identifier|description|partition'
```

macOS（装好之后）：

```bash
# 显卡是否拿到大 BAR、Metal 是否被识别（驱动验收也用它）
system_profiler SPDisplaysDataType | head -30
# 三块盘是否都看到了（AHCI 生效的反证）
diskutil list
```

## 6. 装完 macOS 后哪些可以恢复

| 项 | 能否恢复 | 恢复前先确认 |
|---|---|---|
| Hyper-Threading / E 核 | 可以试 | 先备份能启动的 `config.plist`；恢复后连开 3 次机都能稳进桌面才算数 |
| VT-d / IOMMU | 谨慎 | 只有你需要 Windows 侧 Hyper-V、WSL2 直通、或虚拟机 PCIe 直通时才值得开；开了要重跑 `config.plist` 里的 `DisableIoMapper` 组合复测 |
| Fast Boot | 可以 | 恢复后 U 盘可能又从菜单里消失（S05） |
| Secure Boot | **不要** | 一旦开回，非 Apple 签名 kext 全部拒绝 |
| Above 4G / Re-Size BAR | **不要** | 驱动需要 8 GB BAR |
| CSM | **不要** | 会破坏 GOP 帧缓冲 |
| SATA Mode | **不要** | 切回去 macOS 直接看不到盘 |

## 7. 三种「设置全丢」的场合（每次都要照表重做）

| 场合 | 后果 | 处理 |
|---|---|---|
| BIOS 更新（如 F10 → 更新版本） | 全部回到默认，VT-d/Secure Boot/CSM 常常自动变回不安全值 | 更新完立刻照 §1 复核九项，再启动 macOS |
| 清 CMOS / 换电池 / 短接跳线 | 同上 | 同上 |
| BIOS 里选了 `Load Optimized Defaults` | 同上 | 同上 |

> 本机的教训：`F10` 版本的默认值里 **Secure Boot 是开的、CSM 也不一定关**，第一次装之所以卡在 EXITBS，
> BIOS 默认值贡献了一半原因（另一半是 `DevirtualiseMmio` 方向错，见 `case-arrow-lake-245k.md`）。
