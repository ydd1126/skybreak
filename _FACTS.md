# 实战事实简报（2026-10-20 实战蒸馏，所有数字都是实测）

> 这份文件是所有子代理的**唯一事实来源**。禁止编造这里没写的型号、版本、数字、命令。

## 一、目标机器

| 项 | 值 |
|---|---|
| 主板 | Gigabyte **B860M POWER**（Intel B860 芯片组 / LGA1851），BIOS AMI **F10**（2026-02-02） |
| CPU | **Intel Core Ultra 5 245K**（Arrow Lake-S，Family 6 Model 0xC6），原始 14 核（6P+8E），L3 24 MB |
| dGPU | **NVIDIA RTX 3070 8GB**，PCI `10DE:2488`，SUBSYS `1458:404E`（技嘉） |
| iGPU | Intel Graphics `8086:7D67`（Arrow Lake） |
| 内存 | 16 GB DDR5-6000 ×1（单通道，4 槽只用 1） |
| 网卡 | Realtek RTL8125 2.5GbE `10EC:8125`（无无线网卡） |
| 声卡 | Realtek ALC897 `10EC:0897` + NVIDIA HDMI `10DE:009E` |
| USB | Intel USB 3.20 xHCI `8086:7F6E` |
| 显示器 | Philips 237E7 1920×1080@60，接在 RTX 3070 的 HDMI |
| 系统（双系统） | macOS **26.7.1 build 25G241** 装在 ADATA SU800 256G；Windows 11 25H2 26200 装在 SAMSUNG SM841 256G |

磁盘清单（序列号用于身份核对，绝对不要认错盘）：

```
disk0 Samsung 750 EVO 120G   SATA  SERIAL_DISK0_REDACTED
disk1 WD20EZRZ 2T            SATA  SERIAL_DISK1_REDACTED
disk2 WD20PURX 2T            SATA  （未分配）
disk3 SAMSUNG SM841 256G     SATA  SERIAL_DISK3_REDACTED   ← Windows 系统盘
disk4 ADATA SU800 256G       SATA  SERIAL_DISK4_REDACTED     ← macOS 系统盘（APFS）
disk5 APPLE SSD SM0512F 500G SATA  SERIAL_DISK5_REDACTED   ← 418 GB 数据
disk6 Generic U 盘 59.5G     USB   SERIAL_USB_REDACTED     ← OpenCore 安装盘
```

## 二、最终成功的配置（照抄这套）

### BIOS（必须这样）
```
VT-d / IOMMU                  = Disabled      ← 决定性，社区公认解法
Hyper-Threading               = Disabled      ← 混合核心必须
Active E-Cores                = 0 (Disabled)  ← 同上，CPU 只剩 6C/6T
Above 4G Decoding             = Enabled
Re-Size BAR / Resizable BAR   = Enabled       ← 驱动要 8 GB BAR，MUST
CSM / Legacy Boot             = Disabled
Secure Boot                   = Disabled
Fast Boot                     = Disabled
```

### OpenCore config.plist 关键项（macOS 26 + Arrow Lake + NVIDIA 的成功组合）
```
Kernel → Quirks → ProvideCurrentCpuInfo  = True      （混合核 CPU 必须）
Kernel → Quirks → DisableIoMapper        = True
Kernel → Quirks → LapicKernelPanic       = False
Booter → Quirks → DevirtualiseMmio       = True      ← 1401 默认给 False，方向反了
Booter → Quirks → ResizeAppleGpuBars     = 0         （安装/无驱动阶段；装完驱动可用 -1）
Booter → Quirks → SetupVirtualMap        = True
Booter → Quirks → RebuildAppleMemoryMap  = True
Booter → Quirks → SyncRuntimePermissions = True
UEFI   → Quirks → ResizeGpuBars          = -1（BIOS 已开 ReBAR 时不需要 OC 再改）
ACPI   → Delete → DMAR                   = All=True, Enabled=True
Kernel → Emulate → Cpuid1Data            = 55 06 0A 00 ...（Comet Lake 0x000A0655 伪装）
Kernel → Emulate → Cpuid1Mask            = ff ff ff ff ...
Kernel → Add → CpuTopologyRebuild.kext   = Enabled=False   （Arrow Lake 必须关）
NVRAM  → Add → 7C436110-... → csr-active-config = FF0F0000  （0x0FFF 全关 SIP）
Misc   → Security → SecureBootModel      = Disabled
PlatformInfo → Generic → SystemProductName = MacPro7,1   （macOS 15 和 26 都接受）
```

### 两个内核补丁（决定性，1401 不自带，从成功案例抄来）
```
Identifier = kernel      Comment = ... | Visual | thread_invoke, thread_dispatch | Remove non-monotonic time panic | 12.0-26.3 | Count=2 Enabled=True
Identifier = kernel      Comment = ... | laobamac | thread_invoke, thread_dispatch | Remove non-monotonic time panic | 26.4+ | Count=2 Enabled=True
```
它们覆盖 macOS 26.4+ 的时钟（TSC）非单调导致的冻死。

### 必备 kexts（缺一不可的最小集合）
```
Lilu / VirtualSMC / AMFIPass / AppleMCEReporterDisabler /
RestrictEvents / SMCProcessor / SMCSuperIO / USBToolBox / UTBDefault /
WhateverGreen / RTL812xLucy（2.5G 网卡）       ← AMFIPass 是必须的，缺它系统服务全挂
```

### boot-args（装完驱动后由 1401 Mac app 调成）
```
keepsyms=1 revpatch=sbvmm nvfb=1 nvaccel=1 nvfbheads=1 -nvkmsnosmooth
amfi_get_out_of_my_way=0x1 amfi=0x80 ipc_control_port_options=0
```
安装阶段可以用 `-v keepsyms=1` 打开详细日志（诊断时必开）。

## 三、失败→根因→解法（四天的完整时间线，这是本 skill 的核心资产）

| 现象 | 根因 | 解法 | 验证依据 |
|---|---|---|---|
| 内核交接后**零输出**，屏幕定格在 OpenCore 菜单 | `debug=0x100` 把内核错误静默进调试器；且 NVRAM 里的旧 boot-args 盖住了 config 里的新值（`OCVAR: Setting NVRAM ...boot-args - ignored, exists`） | 把 `boot-args` 加进 `NVRAM → Delete`，去掉 `debug=0x100` | 日志出现 `Deleting NVRAM ...boot-args - Success` |
| 卡 `EB|LOG:EXITBS:START` | **BIOS VT-d 没关**（社区 5+ 用户同一结论）、混合核心拓扑、DevirtualiseMmio 方向错 | 关 VT-d + 关 HT/E 核 + `DevirtualiseMmio=True` + `ProvideCurrentCpuInfo=True` | 关 VT-d 后日志里不再出现 `OCA: Deleting table DMAR`；社区 #10/#11 |
| 过了 EXITBS 但在 `[AHCI][HBA] start:` 冻住 | 时钟非单调（TSC）导致早期冻死，AHCI 只是最后刷屏的一行（**不是 SATA 不兼容**） | 加两个 `Remove non-monotonic time panic` 内核补丁 | 打补丁后内核继续滚到 userspace |
| 到 userspace 后服务全失败：`setuid/task_for_pid: Operation not permitted`、`code signature page shift: 14`、`malformed Mach-O` | SIP 值 `0x0A43` 缺 `CSR_ALLOW_TASK_FOR_PID(0x04)`；且 AMFIPass 被误关 | `csr-active-config = FF0F0000`（0x0FFF）+ 启用 AMFIPass.kext | 成功案例（HP OMEN Arrow Lake）就是 0xFF0F |
| OpenCore 菜单只有 `Reset NVRAM` | `ScanPolicy` 位掩码算错（0x01070003 把 APFS/USB 都过滤掉了） | 用官方默认 `17760515`(0x010F0103) 或 `0`；只有想隐藏 Windows 时才用 17760515 | 菜单恢复 |
| 每次重启都进 Windows | ① U 盘固件启动项 GUID 在重写 U 盘后失效 ② **快速启动(休眠)** 直接跳过固件 | `bcdedit /set {fwbootmgr} bootsequence {U盘GUID}` 或改 displayorder；装 macOS 期间必须 `powercfg /h off` + `HiberbootEnabled=0` | U 盘上出现新的 `opencore-*.txt` 才说明真走过 OC |
| 抹盘时提示"磁盘已锁定" | NTFS 卷被 macOS 只读挂载 | 磁盘工具 → 显示所有设备 → 选**整块盘** → 抹成 APFS/GUID | 分区表出现 `7C3457EF-...`(APFS) |
| 双系统时间差 8 小时 | macOS 把 RTC 写 UTC，Windows 按本地时间读 | `HKLM\SYSTEM\CurrentControlSet\Control\TimeZoneInformation\RealTimeIsUniversal=1` + `w32tm /resync` | 与网络时间比对差 1 秒 |

## 四、工具链事实

- **1401**（nullmoth/1401，Windows 版）负责：扫硬件 → 构建 OpenCore EFI → 写 macOS 安装盘。**版本必须最新**（老版本缺混合核心修复）。CLI 可用：`python -m p1401 build <Report.json> <ACPI dir> <out> --macos 24|25 --boot-log <日志>`。
- **驱动**：nullmoth/nvidia-macos-driver，Linux 侧支持 macOS 15 和 26（`install.sh` 门禁 `case $MAJ in 15|26)`），NVAccel 按版本分叉（`kexts/15`、`kexts/26`）。装法两种：Mac app（`1401-Mac-<ver>.zip`，会改 OpenCore 配置+加回滚菜单项）或 `tar.gz` + `sudo ./install.sh`。
- **GitHub 直连在此网络不可用**（实测 1.6 KB/s），必须走 `https://gh-proxy.com/https://github.com/...` 镜像（实测 400–4400 KB/s）。
- **Clash 系统代理会掐断 `osrecovery.apple.com` 的 TLS**（`SSL: UNEXPECTED_EOF_WHILE_READING`），写安装盘前必须 `ProxyEnable=0`。
- 驱动许可 **PolyForm Noncommercial**（禁止商用）。
- 官方文档索引：`TROUBLESHOOTING.md`（症状→修复表）、`CARD-SUPPORT.md`（设备表 vs 物理验证）、`HOW-IT-WORKS.md`。

## 五、硬件兼容性判断（本 skill 必须给出的诚实结论）

- CPU：**Arrow Lake（Core Ultra 200S/H/HX）苹果从未支持**，但社区已跑通（需上面那套组合拳）。12/13/14 代（Alder/Raptor Lake）同属"混合核心"类，同样吃 `ProvideCurrentCpuInfo` 与补丁。
- GPU：驱动设备表覆盖 Turing 及以后（GTX16/RTX20/30/40/50），但**物理验证过的只有 RTX 5060**。Ampere（RTX 30）状态 Pending —— 能不能出图必须实机验证。
- 存储：**优先 M.2 NVMe**（走 `AppleNVMe` 通用 PCIe 驱动）。SATA AHCI 在新 PCH（600/700/800 系）上风险更高，但**本次实战证明 B860 的 SATA 是可以工作的**——卡 AHCI 那行其实是时钟补丁问题。
- 成功的真实参照：`github.com/Coolzhy/EFI-OMEN16-am2xxx-public`（Core Ultra 7 255HX + RTX 5060 Laptop + macOS 26）。

## 六、产出物位置（本次实战）

```
U 盘 (M:)
  EFI/OC/config.plist                      当前配置
  EFI/OC/config.plist.bak-20261020-072353  1401 app 自动备份
  NullMoth/                                驱动包 + Mac app + 说明
  opencore-*.txt                           每次启动的引导日志（诊断金矿）
  一键安装显卡驱动.command / 一键回滚-卸载驱动.command / 粘贴即用-命令行.txt
Windows 侧
  C:\<WORK>\    所有脚本与配置备份
  G:\1401-new\            最新 1401 + 驱动
  G:\1401-2.3.3\          本次实际用的 1401
  C:\Users\<USER>\Documents\macOS-install-kit\  文档与报告
```

## 七、完工后回读（2026-10-20 07:23 之后，Windows 侧实测）

以下是把"实战结果"再核对一遍得到的硬事实，用来校正前五节的表述，**以本节为准**。

1. **1401 Mac app（2.3.6）确实在本机运行过**：U 盘 EFI/OC/ 下出现它自己命名的备份 config.plist.bak-20261020-072353（我们自己的脚本备份命名是 config.plist.bak，没有时间戳后缀）。
2. **它实际只改了 boot-args**：-v 被去掉、
vfbheads=4 改成 1。其余键未动 —— Kernel → Block 仍为空、UEFI → Quirks → ResizeGpuBars 仍是 -1、Booter → Quirks → ResizeAppleGpuBars 仍是 0、csr-active-config 仍是 FF0F0000。
3. **因此"最终可用配置"的真实状态**是：Block 为空（**没有**屏蔽 IONDRVSupport）、ResizeGpuBars=-1、ResizeAppleGpuBars=0、csr=FF0F0000、11 个 kext 全启用。**"必须屏蔽 IONDRVSupport、ResizeGpuBars=13"是驱动 README 的要求，但本机成功时的配置并没有这两项** —— 两个值并列记录，不要单方面断言只有一种正确值。
4. **未采集的验收证据**：用户口头确认"进桌面、全部解决"，但 kmutil showloaded --list-only | grep nullmoth 与 system_profiler SPDisplaysDataType 的输出**没有采集**。所以驱动的 kext 是否加载、Metal 是否可用 = **待验证**，任何文档都不得写成"已验证"。
5. **可以证明 vs 不能证明**（对外表述必须区分）：
   - 能证明：macOS 26.7.1 (25G241) 装完、能启动到桌面、用户态服务不再批量崩溃、Windows 双系统共存、数据无损。
   - 不能证明：RTX 3070 在 macOS 内已出图 / 有 Metal 加速（Ampere 在厂商表里是 Pending，本机也未采集验收输出）。
6. **驱动阶段配置存在两种取得方式**：① 1401 Mac app（本机实际用的，只改 boot-args）② 手动/脚本写入 Block + ResizeGpuBars=13（驱动 README 的写法）。两条都记录，不合并成一条真理。