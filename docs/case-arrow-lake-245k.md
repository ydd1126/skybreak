# 案例复盘：Arrow Lake（Core Ultra 5 245K）+ B860M + RTX 3070 装 macOS 26 的四天

> **标注约定**：`[实测]` = 本机真实发生、有文件/日志为证；`[厂商]` = 上游文档；`[社区]` = 社区报告；`未实测` = 推断。
> 全部时间戳来自 `C:\<WORK>\` 下文件的 LastWriteTime（脚本名即实验名）与 `oc-panic.txt` 内的引导时间戳。

## 0. 一句话结论

这台机器能跑起来，**不是靠调出一个神奇的 config，而是把四个独立的故障点全部拆掉**：
BIOS 的 VT-d/HT/E 核、NVRAM 盖住 boot-args、`DevirtualiseMmio` 方向反、缺两条 TSC 时钟补丁；
最后再加一条 SIP 值 `0x0A43 → 0x0FFF`（并启用 AMFIPass）才让 userspace 活过来。
**任何一条没拆，现象都是「卡住/黑屏」，看起来一模一样——这是最坑的地方。**

## 1. 机器与目标

| 项 | 值 |
|---|---|
| 主板 | Gigabyte **B860M POWER**（Intel B860 / LGA1851），BIOS AMI **F10**（2026-02-02） |
| CPU | **Intel Core Ultra 5 245K**（Arrow Lake-S，Family 6 Model 0xC6），原始 14 核（6P+8E），L3 24 MB |
| dGPU | **NVIDIA RTX 3070 8GB**，`10DE:2488`，SUBSYS `1458:404E`（技嘉）→ Ampere，厂商验证状态 **Pending** |
| iGPU | Intel Graphics `8086:7D67`（Arrow Lake，macOS 无驱动） |
| 内存 | 16 GB DDR5-6000 ×1（单通道） |
| 网卡/声卡 | RTL8125 2.5GbE `10EC:8125` / ALC897 `10EC:0897` + NVIDIA HDMI `10DE:009E` |
| 显示器 | Philips 237E7 1920×1080@60，接 RTX 3070 的 HDMI |
| 系统 | macOS **26.7.1 build 25G241**（ADATA SU800 256G）+ Windows 11 25H2 26200（SM841 256G） |
| 工具 | 1401 **2.3.3**（本次实际使用）+ 驱动 **1.14.2** |

## 2. 前传：10-12 ~ 10-13（不是装机，但决定了后面所有麻烦）

| 时间 | 事件 | 证据 |
|---|---|---|
| 10-12 19:38 | 三个安装包经 `gh-proxy.com` 镜像下载完，逐个算 SHA-256 记录 | `downloads\HASHES.txt`、`*-SHA256SUMS.txt` |
| 10-13 18:33 | 发现 **E:（ADATA SU800，后来的 macOS 盘）整个卷被清零**：GPT 完好、分区首扇区无 NTFS 签名、抽样 8 个位置全 0 | `logs\E-disk-incident-and-refix.txt`、`probe-e-copy.txt` |
| 10-13 18:36 | `Clear-Disk → Initialize-Disk GPT → New-Partition → Format NTFS` 重建，序列号核对 `SERIAL_DISK4_REDACTED`，回拷 1268 文件 / 2582.1 MiB，三个包哈希逐字符复校 | 同上 |
| 事故根因 | 全套脚本里有 `格式化两块盘.cmd` / `admin-format-disks.ps1`，会对 disk 4 执行 `Clear-Disk` 整盘清零 | 文件原文 + 记录里的「不要再运行」 |

> **教训（提前说）**：这台机器上「清盘」类脚本是真实存在的、一键就能抹掉 256 GB 的。装 macOS 前先确认你要抹的是哪块盘，
> 并用序列号核对（`_FACTS` §一 的磁盘表就是为此存在的）。

## 3. 四天时间线

### 第 1 天 10-16 ~ 10-17：以为「配置不对」，其实是「三处硬件级阻塞」

| 时间 | 现象 | 当时判断 | 动作 | 证据 |
|---|---|---|---|---|
| 10-16 18:36 | 启动 1401（2.3.3），生成第一份 config | 「先让它自己生成，再微调」 | `启动1401.cmd` → `config-orig.plist`（24017 B） | 文件时间戳 |
| 10-17 11:36 | 选完 macOS 条目后**屏幕零输出**，定格在 OC 菜单 | 以为内核没加载/镜像坏了 | 抓 OC 日志 | `oc-panic.txt`：`AAPL: #[EB\|LOG:EXITBS:START] 2026-10-17T11:36:54` |
| 10-17 12:28 | 日志里发现两处硬证据 | ① `OCVAR: Setting NVRAM 7C436110-…:boot-args - ignored, exists`（NVRAM 旧值压住新值）② `OCA: Detected table DMAR … at index 31` + `OCA: Deleting table DMAR …`（VT-d 表还在固件里） | 12:40 备份 → 12:40 `config-backup-before-bootargs.plist`；13:47 `before-nvramdelete`（把 `boot-args` 挂进 `NVRAM → Delete`） | 上述两行原文 + 备份文件名 |
| 10-17 14:48 | 还是卡 EXITBS | **错误判断**：笔记里写着「混合核心 Intel 必须把 `DevirtualiseMmio` 设 `False`」，于是主动改成 `False` | `patch-config.py` → `before-devmmio.plist`；`final-check.py` 至今还打印着那句错误注释 | 脚本注释原文：`[2b'' 混合核心 Intel 修复]`、`(混合核心 Intel 必须 False)` |
| 10-17 15:18 | 安装器进不去，怀疑 ADATA 盘有旧数据 | 清空 ADATA 盘 | `clear-adata.ps1` + 日志 | `clear-adata-log.txt` |
| 10-17 16:32~17:19 | 手工构建 EFI（OpenCore 1.0.8），做 4 层校验 | 「自己搭一份更可控」 | `build-efi-admin.ps1`、`patch-config.py`、`add-cpus1.py`（加 `cpus=1`） | `opencore\BUILD-NOTES.md`：`205 passed, 0 failed`、164 文件 / 11.41 MB |
| 10-17 18:27~22:11 | 仍进不去，开始「减 kext」「砍 boot-args」「去安全模式」式盲试 | 「先最小化再说」 | `hw.py`、`minimize.py`、`strip-kexts.py`（关 AMFIPass/WhateverGreen/AppleALC）、`verify-strip.py` | 一串 `before-minimal/stripkexts` 备份 |
| 10-17 22:15 | 改策略：**目标从 macOS 15 换成 macOS 26（Tahoe）** | 「直接上 26，反正驱动也支持」 | `fix-nvram-tahoe.py` + `config-backup-tahoe-before-bootargs.plist`（config 从 24017 缩到 22726 B，1401 重建了它） | 文件大小变化 |
| 10-17 22:49~22:52 | 清完 NVRAM 后开始处理「每次进 Windows」和「时间差」 | 双系统基础设施问题 | `fix-nvram-tahoe.py`（`boot-args` 进 Delete）、`boot-optimize.ps1`（查休眠/快速启动）、`boot-times.txt` | `boot-times.txt`：10-17 21:37 `total=64.8s`（当天最慢一次） |

**当天结论（错的）**：以为主要矛盾是「kext 太多 / NVRAM 脏 / 安装镜像不合格」。

### 第 2 天 10-18：翻车最密集的一天，主要是自己给自己挖坑

| 时间 | 现象 | 当时判断 | 动作 | 证据 |
|---|---|---|---|---|
| 00:23 | 双系统时间差 8 小时 | RTC 时区问题 | `fix-time.ps1` 设 `RealTimeIsUniversal=1`，`w32tm /resync` **失败**：`服务尚未启动。 (0x80070426)` | `fix-time-log.txt` 原文 |
| 08:24~08:42 | 重启又进 Windows | 固件启动顺序 | `list-fwboot.ps1` → 找到 U 盘项 `{4e108714-c960-11f1-8017-806e6f6e6963}`，`bcdedit /set {fwbootmgr} bootsequence …` | `set-bootseq.txt`（`操作成功完成。 rc=0`） |
| 12:04~12:05 | 想让菜单「干净点、默认进 macOS」 | 以为 `HideAuxiliary`+`ScanPolicy` 组合是正解 | `hideaux.py`（`HideAuxiliary=True`）、`timeout60.py` | 备份 `before-hideaux` / `before-scanpolicy` |
| **12:59** | **菜单只剩 `Reset NVRAM`** | **自己算 `ScanPolicy`**：想「去掉 NTFS 位和 USB 位以隐藏 Windows」，算出 `0x01070003` | `scanpolicy.py` 写入 `0x01070003` | 脚本注释原文：`# 0x01070003 = FILE_SYSTEM_LOCK + DEVICE_LOCK + APFS + HFS + ESP + SATA/SASEX/SCSI/NVME + PCI`（**这段注释本身就是错的**） |
| 13:11~13:27 | 慌了：先恢复全放行 | | `make-usb-first.ps1`、`restore-scan.py`（`ScanPolicy=0`、`HideAuxiliary=False`、`Timeout=60`） | `before-restore.plist` |
| 13:28 | 改用官方默认值 | 「官方默认总没错」 | `official-policy.py`（`17760515` = `0x010F0103`） | `before-officialpolicy.plist` |
| 14:12~17:46 | 还是不行 → 开始大规模盲试 | 怀疑显卡/安全模式/PCI | `nvdisable.py`（加 `nv_disable=1`）、`quiet.py`（去掉 `-v/debug=0x100/keepsyms`）、`safemode.py`（`-x`）、`diagboot.py`、`rebar-on.py`、`verbose2.py`（再加回 `-v keepsyms=1`）、`npci2.py`（`npci=0x2000`） | 每题一份 `config-backup-before-*` |
| 22:40~22:57 | `npci=0x2000` 无用；`DisableIoMapper` 改成 False | 「VT-d 反正关了就不要再禁 IOMMU」 | `npci2.py`、`iomapper.py` | 备份 + 脚本打印 |

**当天结论（半错）**：把「菜单看不见卷」这件小事，用半天时间做成了主战场；
`ScanPolicy` 的十六进制是**自己拼的**，而且拼错了（见 §5 弯路 1）。

### 第 3 天 10-19：找到成功参照机，一次性对齐

| 时间 | 现象 | 当时判断 | 动作 | 证据 |
|---|---|---|---|---|
| 18:45 | 决定「先不管 kext 数量」 | 需要一份确定能工作的基线 | `minkext.py`（只留 Lilu+VirtualSMC 的极端实验） | `before-minkext.plist` |
| **19:56** | **拿到参照机 EFI**（HP OMEN 16 / Core Ultra 7 255HX + RTX 5060 + macOS 26），做 diff | **「不要再自己想，先抄对的」** | `cmp.py` 逐项对比 → `apply-omen.py` 一把改齐：`ProvideCurrentCpuInfo=True`、`DisableIoMapper=True`、`LapicKernelPanic=False`、`DevirtualiseMmio=True`、`ResizeAppleGpuBars=0`，并**抄来两条 `Remove non-monotonic time panic` 内核补丁**；`rm-npci.py` 去掉 `npci=0x2000` | 备份 `before-omen.conf`、`before-kexts-on`；`apply-omen.py` 打印「新增 2 个补丁」 |
| 21:22 | 恢复 kext（只关 `CpuTopologyRebuild`） | 与参照机一致 | `dump-kexts.py`、`kexts-on.py` | `kexts-on.py` 注释：`成功机器唯一关闭的是 CpuTopologyRebuild` |
| **22:16** | 系统能进 userspace 了，但**服务成片失败**：`setuid/task_for_pid: Operation not permitted`、`code signature page shift: 14` | SIP 位不够 + AMFIPass 被自己关了 | `sip.py`：`csr-active-config 430A0000 → FF0F0000`，并把 `csr-active-config`/`boot-args` 都挂进 `NVRAM → Delete` | `before-sip.py.plist`；脚本打印 `(0x0A43 -> 0x0FFF: 加上 task_for_pid / unrestricted_dtrace / device_configuration 等)` |

### 第 4 天 10-20：收尾定版

| 时间 | 事件 | 证据 |
|---|---|---|
| 10-20 07:23 | 1401 Mac app 自动备份 **`config.plist.bak-20261020-072353`**，此后系统稳定进桌面 | 文件存在 + `_FACTS` §六 |
| 之后 | 把「必设值」蒸馏成 `_FACTS.md` §二，把「失败→根因」蒸馏成 §三 | 本 skill 即产物 |

## 4. 最终 5 步决定性改动（每步的证据）

| # | 改动 | 为什么是决定性的 | 日志/文件证据 |
|---|---|---|---|
| 1 | **BIOS**：`VT-d=Disabled`、`Hyper-Threading=Disabled`、`Active E-Cores=0`（配套 `Above 4G=On`、`Re-Size BAR=On`、`CSM=Off`、`Secure Boot=Off`、`Fast Boot=Off`） | VT-d 不关，内核在 `EXITBS` 之前就被 IOMMU 描述符卡死；混合核拓扑是第二重阻塞 | 关之前日志有 `OCA: Detected table DMAR (52414D44) … at index 31`；关之后**不再出现删表动作**，直接越过 EXITBS |
| 2 | **`NVRAM → Delete` 挂 `boot-args` + `csr-active-config`**，同时去掉 `debug=0x100` | 不加 Delete，config 里改的 boot-args 根本不生效（被 NVRAM 旧值压住）；`debug=0x100` 又让错误不出现在屏幕上 | 改前：`OCVAR: Setting NVRAM 7C436110-AB2A-4BBB-A880-FE41995C9F82:boot-args - ignored, exists`；改后：`OC: Deleting NVRAM 7C436110-…:boot-args - Success`，屏幕恢复滚动 |
| 3 | **`DevirtualiseMmio=True`** + `ProvideCurrentCpuInfo=True` + `DisableIoMapper=True` + `LapicKernelPanic=False` | 1401 默认给 `False`，方向是反的；这四项是参照机与原配置差异最大的地方 | `apply-omen.py` 的打印；`cmp.py` 的 `<-- 不同` 行 |
| 4 | **两条 `Remove non-monotonic time panic` 内核补丁**（`Count=2`，`12.0-26.3` 与 `26.4+` 各一条） | 没有它，内核在 TSC 非单调处冻死，画面最后一行的 `[AHCI][HBA] start:` 会骗你以为 SATA 不兼容 | 补丁前日志停在 `[AHCI][HBA] start:` 后再无输出；补丁后越过它进 userspace |
| 5 | **`csr-active-config = FF0F0000`（`0x0FFF`）+ 启用 `AMFIPass.kext`** | `0x0A43` 缺 `CSR_ALLOW_TASK_FOR_PID(0x04)`，服务取不到任务端口；AMFIPass 关闭让未签名 bundle 过不了签名页校验 | 改前：`setuid/task_for_pid: Operation not permitted`、`code signature page shift: 14`、`malformed Mach-O`；改后：这些消失，`csrutil status` = disabled |

**前置条件（不满足连菜单都进不去）**：`ScanPolicy` 必须是 `0` 或 `17760515`（`0x010F0103`），
`SystemProductName` 必须是 `MacPro7,1`（macOS 26 拒绝 `iMacPro1,1`），`Kernel → Add → CpuTopologyRebuild` 必须关。

## 5. 最后悔的三个弯路

### 弯路 1：自己拼 `ScanPolicy`（浪费约 6 小时）

想「隐藏 Windows」于是手算一个 `0x01070003`。它的实际组成是
`FILE_SYSTEM_LOCK(0x1) + DEVICE_LOCK(0x2) + SATA(0x10000) + SASEX(0x20000) + SCSI(0x40000) + PCI(0x1000000)`，
**APFS 位 `0x100` 与 USB 位 `0x00200000` 都不在里面**，于是所有 APFS 卷被过滤 → 菜单只剩 `Reset NVRAM`。
更糟的是脚本注释还替这个错误值写了「包含 APFS/HFS/ESP」的说明，把我自己说服了。
**正确做法**：先 `0` 全放行确认能看见所有卷，再改成 `17760515`；位表手边放一份（见 `config-cookbook.md` §9）。

### 弯路 2：`DevirtualiseMmio` 方向反了，还写进了笔记（浪费约 1.5 天）

10-17 14:48 我把 `DevirtualiseMmio` 从 `True` 改成 `False`，理由写在脚本注释里：
「混合核心 Intel 必须 False」。这句话没有出处，是我从别处记岔的。
1401 生成时本来就给 `False`，**我等于把「厂商默认的错误」又确认了一遍**。
直到 10-19 19:56 抄参照机才改回 `True`。
**正确做法**：任何「混合核必须 X」的结论，先拿一份**已知成功**的 config 做 diff 再写进自己的笔记。

### 弯路 3：屏幕没输出时不肯先修「能看见」（浪费约半天 + 一堆无效实验）

`debug=0x100` 在 boot-args 里时，内核错误被静默，屏幕上什么都不显示。
我不信这一点，转而去试 `cpus=1`、`-x` 安全模式、`nv_disable=1`、`npci=0x2000`、砍 kext、`HideAuxiliary`、`Timeout=60`……
一晚上做了 10 份 `config-backup-before-*`（10-17 19:22 ~ 10-18 17:46 这一段）。
**正确做法**：`-v keepsyms=1` + 确认它的**生效证据**（日志里 `Deleting NVRAM …:boot-args - Success`）是一条前置工序，
不通过就不做任何别的实验。

## 6. 可复用的经验（下次直接照做）

1. **先找参照机，再做 diff。** 本案例里 `cmp.py` 是全部工作里性价比最高的一步：一次性指出 5 个 Quirk 差异 + 2 个缺失补丁。
   参照机：<https://github.com/Coolzhy/EFI-OMEN16-am2xxx-public>（Core Ultra 7 255HX + RTX 5060 + macOS 26）。
2. **一次只改一项，并让文件名当实验记录。** `config-backup-before-<实验名>.plist` 这种命名让四天后还能复原顺序。
3. **区分「硬件级阻塞」和「参数级问题」。** VT-d/HT/E 核属于前者：先关掉再谈细节，否则所有参数实验都是在验证同一个失败。
4. **屏幕无输出时，优先级最高的事是「让屏幕能说话」**（`-v keepsyms=1` + 去掉 `debug=0x100` + NVRAM Delete）。
5. **别信默认值。** 1401 的 `DevirtualiseMmio=False`、OpenCore Sample 的 `Vault=Secure`/`ScanPolicy=17760515`，
   都是「默认但会挡你」的项（后两者本机校验器也抓到过）。
6. **判断驱动出图不要看 Kext 装没装上**，要看：`kmutil showloaded | grep nullmoth` 四行 + `Metal: supported` + 桌面 2 分钟不黑。
7. **镜像、代理、工具版本先对齐再动手。** 直连 GitHub 1.6 KB/s、Clash **会使 `osrecovery.apple.com` 的 TLS 断**（`SSL: UNEXPECTED_EOF_WHILE_READING`），
   写盘前必须关系统代理。
8. **回滚要提前准备好。** 装驱动用 1401 Mac app 会自动留 `config.plist.bak-<时间戳>` 和菜单里的 `Remove NVIDIA driver`，
   手工路线要自己先 `cp config.plist config.plist.bak`。

## 7. 边界：这套复盘证明到哪一步

| 已验证 `[实测]` | 尚未验证 `未实测` |
|---|---|
| macOS 26.7.1 25G241 能装完、能进桌面、服务不再批量崩溃 | **RTX 3070 是否真的出图/有 Metal 加速**（Ampere 在厂商表里仍是 `Pending`） |
| 五步改动的每一条都有对应日志/脚本作为证据 | 声卡 ALC897 是否真的出声（layout 11 只是选型依据） |
| NVRAM Delete / ScanPolicy / SIP 位表的机制 | 蓝牙（本机未确认芯片、未加 kext） |
| 双系统共存、时间同步、固件启动项修正 | 热插拔显示器、HDMI 音频（厂商已列为 open issue） |

## 8. 证据文件索引（都在本机，可复核）

| 路径 | 内容 |
|---|---|
| `C:\<WORK>\oc-panic.txt` | 失败的 OpenCore 引导日志（`EXITBS` 时间戳、`ignored, exists`、`Deleting table DMAR`、`147/256 slide values`） |
| `C:\<WORK>\config-backup-*.plist` | 26 份逐次实验备份，文件名即实验顺序 |
| `C:\<WORK>\{scanpolicy,official-policy,sip.py,iomapper,apply-omen,cmp,npci2,quiet,safemode,nvdisable}.py` | 每一步的真实改动脚本（含当时的错误注释） |
| `C:\<WORK>\{fwboot,set-bootseq,usb-first,fix-time-log,boot-times,verify-boot}.txt` | 固件启动项、时间同步、启动耗时实测 |
| `C:\Users\<USER>\Documents\macOS-install-kit\opencore\BUILD-NOTES.md` | 手工 EFI 的构建依据（DSDT 证据、205 项校验、三处被抓到的真问题） |
| `C:\Users\<USER>\Documents\macOS-install-kit\logs\E-disk-incident-and-refix.txt` | 清盘事故与重建记录 |
| `C:\Users\<USER>\Documents\macOS-install-kit\drivers\` | 驱动包文档（README / TROUBLESHOOTING / CARD-SUPPORT / BASELINE-IDENTITY） |
