# 启动失败症状大全（症状 → 根因 → 验证 → 修法 → 确认）

> **编号约定（先读这条，否则会找错）**：本文件症状编号是 **S01–S20**；`../SKILL.md` **第四节**的诊断编号是 **R01–R10**（同一批问题的手册视角，**按"现象原文"匹配，不要按编号换算**）；`../SKILL.md` **第三节**的 **S01–S16 是 SOP 作业步号**，与本文件的 S 编号完全不同。
> 记忆法：`R` = 手册诊断轮次，本文件 `S` = Symptom（症状），手册 `S` = Step（步骤）。

> **标注约定**：`[实测]` = 本机 Gigabyte B860M POWER / Ultra 5 245K / RTX 3070 / macOS 26.7.1 上真跑过；
> `[厂商]` = NullMoth README / TROUBLESHOOTING.md / CARD-SUPPORT.md / OpenCore / Apple xnu；
> `[社区]` = 社区报告未在本机复现；`未实测` = 只给判断、没验证。
> 日志原文都来自本机真实文件：`C:\<WORK>\oc-panic.txt`（OpenCore 引导日志）、`boot-times.txt`、`fix-time-log.txt`。

## 0. 先定位在哪一阶段（三段式）

| 阶段 | 判断依据 | 该看哪份日志 |
|---|---|---|
| ① 固件/OpenCore | 还在 OC 菜单，或选完条目后屏幕字符停住 | U 盘根的 `opencore-*.txt` |
| ② 内核接管后 | 出现 `AAPL: #[EB\|LOG:EXITBS:START]` 之后 | 同上的 OC 日志 + verbose 屏幕最后一行 |
| ③ userspace | 出现过进度条/登录界面，或系统起来了但服务崩 | `log show`、`/Library/Logs/DiagnosticReports`、`nvram -p` |

**一条铁律**：任何「屏幕没输出」的排查，第一件事是把 `-v keepsyms=1` 加进 boot-args 并确认它真的生效（见 S01），否则你在瞎猜。

## 1. 症状索引

| 编号 | 一句话症状 | 最可能根因 | 来源 |
|---|---|---|---|
| S01 | 内核交接后零输出，屏定格在 OC 菜单 | `debug=0x100` + NVRAM 旧 boot-args 压住新值 | `[实测]` |
| S02 | 卡 `EB\|LOG:EXITBS:START` | VT-d 没关 / 混合核 / DevirtualiseMmio 反了 | `[实测]` |
| S03 | 过了 EXITBS 但冻在 `[AHCI][HBA] start:` | TSC 时钟非单调（不是 SATA 不兼容） | `[实测]` |
| S04 | OC 菜单只剩 `Reset NVRAM` | ScanPolicy 位掩码算错 | `[实测]` |
| S05 | 每次重启直接进 Windows | 固件启动项 GUID 失效 / Windows 快速启动 | `[实测]` |
| S06 | `EB.MM.AKM` / `STOP 0x16` / `Couldn't allocate runtime area` | 固件内存映射不给 boot.efi 留位置 | `[厂商]` |
| S07 | 卡 `PCI configuration` | Above 4G / ReBAR / CSM；装驱动后首次启动停 40–100 s 属正常 | `[厂商]` |
| S08 | `This version of Mac OS X is not supported on this platform!` | SMBIOS 机型被 macOS 26 拒绝 | `[厂商]` |
| S09 | `OCB: LoadImage failed - Unsupported` / `OS.dmg.root_hash … Err(0xE)` | U 盘或恢复镜像损坏 | `[厂商]` |
| S10 | `OCABC: Only 147/256 slide values are usable!` | 内存映射碎片（KASLR 滑窗不足） | `[实测]` |
| S11 | 抹盘时提示「磁盘已锁定」 | NTFS 卷被 macOS 只读挂载 | `[实测]` |
| S12 | 安装器卡在 19 分钟、Caps Lock 无反应 | 写固件变量挂死（Ryzen 7000+） | `[厂商]` `未实测` |
| S13 | 系统起来了但服务全崩：`task_for_pid: Operation not permitted` | SIP 缺 `CSR_ALLOW_TASK_FOR_PID` + AMFIPass 被关 | `[实测]` |
| S14 | 装驱动后约 1 分钟黑屏只剩鼠标 | zero-copy 扫描输出 + 小 BAR/核显帧缓冲 | `[厂商]` |
| S15 | 100–240 Hz 黑屏/闪屏，改分辨率后黑 | DSC 压缩参数没告诉 macOS | `[厂商]` `未实测` |
| S16 | 睡眠后画面冻结 / 切输入回来无画面 / 热插拔显示器不亮 | 驱动显示电源与热插拔路径 | `[厂商]` `未实测` |
| S17 | Turing 卡循环卡在 `AppleKeyStore` | 卡固件需要更久才点亮显示 | `[厂商]` `未实测` |
| S18 | 苹果 logo + 进度条卡住（没开 verbose） | 没日志，无法定位 | `[实测]` |
| S19 | 选完 macOS 几秒黑屏自动重启 | panic 后自动重启 | `[实测]` |
| S20 | 双系统时间差 8 小时 | macOS 写 UTC，Windows 读本地时间 | `[实测]` |

## 2. 逐条处置

**S01 内核交接后零输出，屏幕定格在 OpenCore 菜单** `[实测]`
- 识别：选完条目后无任何新字符；OC 日志里 `OCVAR: Setting NVRAM 7C436110-AB2A-4BBB-A880-FE41995C9F82:boot-args - ignored, exists`，且 boot-args 含 `debug=0x100`。
- 根因：① `debug=0x100` 把内核报错静默给调试器，屏幕上看不到；② NVRAM 里已有 boot-args，config 里的新值被忽略。
- 验证：`grep -n 'ignored, exists' /Volumes/OCUSB/opencore-*.txt`；macOS 里 `nvram boot-args` 看到的是旧串就是它。
- 修法：`NVRAM → Delete` 的 `7C436110-…` 里加入 `boot-args`（和 `csr-active-config`）；去掉 `debug=0x100`，只留 `-v keepsyms=1`。
- 确认：新日志出现 `OC: Deleting NVRAM 7C436110-AB2A-4BBB-A880-FE41995C9F82:boot-args - Success`，随后内核开始刷屏。

**S02 卡在 `EB|LOG:EXITBS:START`** `[实测]`
- 识别：最后一行 `AAPL: #[EB|LOG:EXITBS:START] 2026-10-17T11:36:54`，此后永远无输出；日志前面还能看到 `OCA: Detected table DMAR (52414D44) … at index 31` 与 `OCA: Deleting table DMAR …`。
- 根因：BIOS **VT-d/IOMMU 没关**（社区 5+ 用户同一结论）+ 混合核拓扑 + `DevirtualiseMmio` 方向错。
- 验证：`grep -n 'DMAR' opencore-*.txt`（有这两行说明固件里 DMAR 表还在）；BIOS 里确认 VT-d/IOMMU 状态。
- 修法：BIOS `VT-d=Disabled`、`Hyper-Threading=Disabled`、`Active E-Cores=0`；config 里 `Booter→Quirks→DevirtualiseMmio=True`、`Kernel→Quirks→ProvideCurrentCpuInfo=True`。
- 确认：关 VT-d 后新日志里**不再出现** `OCA: Deleting table DMAR`；越过 EXITBS 后出现内核 verbose 输出。

**S03 过了 EXITBS 却冻在 `[AHCI][HBA] start:`** `[实测]`
- 识别：最后一行是 `[AHCI][HBA] start:`，无 panic、无后续；重启重试仍停同一行。
- 根因：**时钟非单调（TSC）导致的早期冻死**，AHCI 只是最后一个成功打印的驱动——**不是 SATA 不兼容**。
- 验证：`plutil -p config.plist | grep -A3 '"Patch"'` 看有没有两条 `Remove non-monotonic time panic`；`system_profiler SPHardwareDataType` 记录机型备查。
- 修法：`Kernel → Patch` 加两条（都 `Identifier=kernel`、`Count=2`、`Enabled=True`）：`… | Visual | thread_invoke, thread_dispatch | Remove non-monotonic time panic | 12.0-26.3`、`… | laobamac | thread_invoke, thread_dispatch | Remove non-monotonic time panic | 26.4+`。
- 确认：内核继续滚过 AHCI，出现 `BSD root:` / launchd 相关行，最终进 userspace。

**S04 OpenCore 菜单只剩 `Reset NVRAM`** `[实测]`
- 识别：选择界面只有一项 `Reset NVRAM`（那是 `ResetNvramEntry.efi` 提供的工具项），macOS 与 U 盘安装盘全不见。
- 根因：`ScanPolicy` 位掩码算错。本机曾设 `0x01070003`，它只有 `FILE_SYSTEM_LOCK|DEVICE_LOCK|SATA(0x10000)|SASEX(0x20000)|SCSI(0x40000)|PCI(0x1000000)`，**缺 APFS 位 `0x100` 和 USB 位 `0x00200000`**，于是没有任何可引导卷。
- 验证：`python3 -c "import plistlib;c=plistlib.load(open('config.plist','rb'));print(c['Misc']['Security']['ScanPolicy'])"`；再对照 `config-cookbook.md` 的位表逐位核。
- 修法：调试期 `ScanPolicy=0`（全放行）；稳态 `17760515`（`0x010F0103`，锁 APFS + 内置盘，隐藏 Windows 与 USB）。
- 确认：菜单重新出现 macOS 卷；想看到 U 盘必须带 `0x00200000`（即 `0` 或 `19857667`/`0x12F0103`）。

**S05 每次重启都直接进 Windows** `[实测]`
- 识别：重启不经过 OC 菜单；**U 盘根目录里没有新的 `opencore-*.txt`**（说明确实没走 OC，而不是走了没显示）。
- 根因：① U 盘重写后固件启动项 GUID 变了，`displayorder` 里还指着旧的；② Windows「快速启动/休眠」直接跳过固件初始化。
- 验证：`bcdedit /enum firmware | findstr /i "partition=M: description"` 找 U 盘项；`powercfg /a` 里若还列着「快速启动」就是没关。
- 修法：`bcdedit /set {fwbootmgr} bootsequence {U盘GUID}` 或把 U 盘项排到 `displayorder` 第一位；`powercfg /h off` 且 `HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power\HiberbootEnabled=0`。
- 确认：U 盘上出现新的 `opencore-*.txt`，且 `bcdedit /enum {fwbootmgr}` 里 `bootsequence` 指向 U 盘项。

**S06 `EB.MM.AKM` / `STOP 0x16` / `Couldn't allocate runtime area`** `[厂商]`
- 识别：以上三条任一条出现在 OC 阶段，常见于 Ryzen 7000/9000。
- 根因：固件内存映射没给 boot.efi 留出可用的 runtime area。
- 验证：换最新 1401 重做盘后复现与否就是最好的对照实验。
- 修法：用最新 1401 重建 U 盘（它为 Ryzen 7000/9000 生成正确内存设置，一个设置失败会试下一个）；重启旧盘不做任何改变。
- 确认：越过该行进入内核输出。

**S07 卡 `PCI configuration`** `[厂商]`
- 识别：停在 `PCI configuration` 或 `PCI configuration end` 很久；若已装驱动，首次启动停 **最多约一分钟** 属正常（README：`pauses for up to a minute at "PCI configuration end"` 等 GPU 起来）。
- 根因：Above 4G Decoding / Resizable BAR / CSM 设置不对；或驱动在 bring-up GPU。
- 验证：临时加 `-nvrmnogo`（驱动待命不自启）看是否还是停这里——停说明是固件侧。
- 修法：BIOS `Above 4G Decoding=Enabled`、`CSM=Disabled`、`Re-Size BAR=Enabled`；驱动侧确认 `ResizeGpuBars=13`、`ResizeAppleGpuBars=-1`。
- 确认：安装阶段顺利过；驱动阶段允许 40–100 秒的停顿，之后进桌面（见 `nullmoth-driver.md` §6）。

**S08 `This version of Mac OS X is not supported on this platform!`** `[厂商]`
- 识别：安装器直接报这行并给出一个 `Mac-…` 机型码。
- 根因：SMBIOS 机型不是该 macOS 版本认的机型；macOS 26 拒绝 `iMacPro1,1`，旧机型被 macOS 15 拒绝。
- 验证：`plutil -p config.plist | grep -i SystemProductName`。
- 修法：`PlatformInfo → Generic → SystemProductName = MacPro7,1`（15 与 26 都接受）；EFI 里所有写机型的地方一起改（1.14.1 修的就是只改了其中一处、留下 `iMacPro1,1` 的坑）。
- 确认：安装器进到语言选择界面。

**S09 恢复镜像/ U 盘损坏** `[厂商]`
- 识别：`OCB: LoadImage failed - Unsupported`、`Failed to retrieve boot file from DMG`、`OS.dmg.root_hash … Err(0xE)`、`OCB: DMG has been altered`。
- 根因：镜像在写入后被改动/写入不完整（劣质或虚标 U 盘）。
- 验证：重写后校验（1.14 起 1401 会回读校验）。
- 修法：换 U 盘、换主板后置 USB 口、用最新 1401 重做。
- 确认：能进安装器；把 `opencore-*.txt` 留着做对照。

**S10 `OCABC: Only 147/256 slide values are usable!`** `[实测]`
- 识别：OC 日志里这行数字偏小（本机记录是 `147/256`）。
- 根因：固件内存映射碎片化，KASLR 可用滑窗不足；本身不一定致命。
- 验证：看它后面是否紧跟 EXITBS 卡死——是则按 S02 处理，不是则不用管。
- 修法：`DevirtualiseMmio=True`、`ProvideCustomSlide=True`；必要时 `SetupVirtualMap`/`RebuildAppleMemoryMap` 保持 True。
- 确认：能过 EXITBS 进内核即可，不必追求 256/256。

**S11 抹盘提示「磁盘已锁定」** `[实测]`
- 识别：磁盘工具里卷呈灰色、按钮置灰，或抹盘报「磁盘已锁定/只读」。
- 根因：NTFS 卷被 macOS 只读挂载，卷级操作不可写。
- 验证：磁盘工具左上「显示 → 显示所有设备」，看该盘上层是不是还有分区。
- 修法：选**整块物理盘**（不是分区）→ 抹掉 → 方案 `GUID 分区图` → 格式 `APFS`。
- 确认：`diskutil list` 里出现 `7C3457EF-…`（APFS）类型的分区。

**S12 安装器卡在 19 分钟、Caps Lock 无反应** `[厂商]` `未实测`
- 识别：进度条到约 19 分钟彻底不动，键盘灯不响应（整机冻）。
- 根因：这类板子在安装器写固件设置时挂死（Ryzen 7000/8000/9000 报告最多）。
- 验证：无日志可看，只能按机型+版本判断。
- 修法：最新 1401 重做盘（1.14 已修）；自己维护 EFI 时 `Booter → Quirks → DisableVariableWrite = true`。
- 确认：进度条继续走到重启。

**S13 系统起来了但服务全崩** `[实测]`
- 识别：日志/控制台出现 `setuid/task_for_pid: Operation not permitted`、`code signature page shift: 14`、`malformed Mach-O`；App 打开就闪退，登录后桌面残废。
- 根因：SIP 值 `0x0A43` **缺 `CSR_ALLOW_TASK_FOR_PID(0x04)`**（`0x0A43` = bit0/1/6/9/11），且 `AMFIPass.kext` 被误关。
- 验证：macOS 里 `csrutil status`；`plutil -p config.plist | grep -A2 csr-active-config`；检查 `Kernel → Add` 里 AMFIPass 的 `Enabled`。
- 修法：`csr-active-config = FF0F0000`（即 `0x0FFF`）+ 启用 `AMFIPass.kext`；两处都要在 `NVRAM → Delete` 里挂 `csr-active-config`。
- 确认：`csrutil status` 显示 `System Integrity Protection status: disabled`；日志不再出现 `task_for_pid` 拒绝；窗口服务正常。

**S14 装驱动后约 1 分钟黑屏只剩鼠标** `[厂商]`
- 识别：桌面正常约 60 秒后黑屏，鼠标还能动；重启又是先好后黑。
- 根因：1 分钟后 NVRM 打开 zero-copy 扫描输出（`debug.nvaccel_iop_flip`），而当桌面画在核显/小 BAR 上时那块内存是空的。
- 验证：boot-args 临时加 `-nvrmnoflip` 后是否黑屏消失。
- 修法：升级到 1.14+（会在这类机器上保持 copy 路径）；过渡期 `-nvrmnoflip`（每帧多一次 copy）。
- 确认：桌面连续稳定 >2 分钟不黑，且光标移动无闪烁。

**S15 高刷 / 改分辨率后黑屏闪屏** `[厂商]` `未实测`
- 识别：100–240 Hz 模式黑屏或闪；改分辨率/刷新率后黑；1.14.2 修的是 2560×1440@180 Hz 登录窗黑。
- 根因：超过 DisplayPort 1.4 带宽的模式需要 DSC 压缩，而 macOS 没被告知。
- 验证：在低刷新率（60 Hz）下是否正常——正常即高度指向 DSC 路径。
- 修法：升级到 1.14+（已发送压缩参数）；仍复现就按 **Send logs** 抓显示路径。
- 确认：切到高刷后 60 秒内无黑屏、无 fliplatch 超时告警。

**S16 睡眠/切输入/热插拔显示器异常** `[厂商]` `未实测`
- 识别：显示器睡眠后画面定格不熄屏；切到别的输入再切回无画面；系统运行中插新显示器不点亮。
- 根因：驱动的显示电源管理与热插拔检测不完整（1.14 修了「切输入回来无画面」「睡眠不定格」，热插拔仍是 open issue）。
- 验证：换 1.14.2 观察；记录发生时的显示器/接口。
- 修法：临时拔插线缆让驱动重新枚举；不要指望热插拔。
- 确认：反复切输入 5 次画面都回来；热插拔仍算「已知未解决」。

**S17 Turing 卡循环在 `AppleKeyStore`** `[厂商]` `未实测`
- 识别：装完驱动后启动循环停在 `AppleKeyStore`（GTX 16 / RTX 20）。
- 根因：卡固件起来慢，驱动点亮显示太早。
- 验证：看是否只要多等就能过（与循环不同）。
- 修法：1.13 起 Setup 会自动加 `nvrmsettle=10000`；手工在 boot-args 补。
- 确认：能稳定进桌面且不再循环。

**S18 苹果 logo + 进度条卡住** `[实测]`
- 识别：白苹果和进度条停在中段，屏幕上没有日志可读。
- 根因：没开 verbose，任何判断都是猜。
- 验证：这本身就是验证手段缺失。
- 修法：boot-args 加 `-v keepsyms=1`（并确认按 S01 真的生效），重启复现，把最后一行记下来。
- 确认：能读到停在哪个驱动/哪一行，再回到 S01–S03 分类处理。

**S19 选完 macOS 几秒黑屏自动重启** `[实测]`
- 识别：无 panic 文本直接重启，循环。
- 根因：内核 panic 后自动重启，屏幕来不及显示。
- 验证：`nvram -p | grep -i panic` 看是否留下 `AAPL,panic-info`；`Misc → Debug → ApplePanic=true` 可把 panic 信息写进 NVRAM 供下次启动读出。
- 修法：先按 S02/S03 排除 VT-d 与时钟；`-v keepsyms=1` 抓 panic 栈。
- 确认：能连续多次进入桌面、`boot-times.txt` 类记录里出现正常启动时长。

**S20 双系统时间差 8 小时** `[实测]`
- 识别：Windows 里时间比手机慢（或快）正好 8 小时；macOS 正常。
- 根因：macOS 把 RTC 当 UTC 写，Windows 按本地时间读。
- 验证：`Get-ItemProperty HKLM:\SYSTEM\CurrentControlSet\Control\TimeZoneInformation | Select RealTimeIsUniversal`。
- 修法：设 `RealTimeIsUniversal=1`（DWORD），再 `net start w32time` + `w32tm /resync`。**本机实测坑**：直接 `w32tm /resync` 报 `服务尚未启动。(0x80070426)`，必须先起服务或重启一次。
- 确认：重启后与网络时间差 <1 秒；`w32tm /resync` 返回成功。

## 3. 抓证据的四个固定位置

| 位置 | 内容 | 命令 |
|---|---|---|
| U 盘根目录 | 每次启动一份 `opencore-*.txt`（诊断金矿） | Windows 直接读 `M:\opencore-*.txt` |
| NVRAM | panic 信息、当前 boot-args、SIP | `nvram -p \| grep -Ei 'panic\|boot-args\|csr-active-config'` |
| 崩溃报告 | WindowServer / 守护进程 | `ls -lt /Library/Logs/DiagnosticReports \| head` |
| 内核日志 | 本次启动全部内核消息 | `log show --last boot --predicate 'process == "kernel"' --style compact` |

> 打印/贴日志前先脱敏：序列号、MAC、UUID、私钥路径都要抹掉（1401 的 Send logs 会自动脱敏）。
>
> 社区/厂商索引：1401 问题 <https://github.com/nullmoth/1401/issues> · 驱动问题 <https://github.com/nullmoth/nvidia-macos-driver/issues> ·
> 厂商排障表 <https://github.com/nullmoth/nvidia-macos-driver/blob/main/docs/TROUBLESHOOTING.md> · 成功参照机 EFI <https://github.com/Coolzhy/EFI-OMEN16-am2xxx-public>
> （本文件里标 `[社区]` 的模式，都是从这些 issue / 排障表提炼的通用症状，未在本机逐条复现）
