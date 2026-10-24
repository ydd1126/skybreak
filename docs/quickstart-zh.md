# 开天 Skybreak · 单文件版
### 在 Arrow Lake + NVIDIA 的 PC 上装 macOS 26 并驱动独显

> 这份文件是自包含的：**不需要装任何 skill、不需要读别的文档**，丢给任何 AI 或人照着做就行。
> 数据来源：一台真机（Intel Core Ultra 5 245K + 技嘉 B860M POWER + NVIDIA RTX 3070）四天实战。
> 凡标 `[实测]` 的都是这台机器上真跑出来的；标 `[社区]` 的是别人报告的；标 `[厂商]` 的是文档写的。

---

## 0. 先看这个：你这台能不能装

按顺序回答 4 个问题，得出档位：

| # | 问题 | 怎么查 | 影响 |
|---|---|---|---|
| D1 | CPU 是不是混合核心（P+E 异构）？ | `Get-CimInstance Win32_Processor \| Select Name,NumberOfCores,NumberOfLogicalProcessors`（核数≠线程数=有超线程；12 代以后基本都有 E 核） | 有 → 必须关超线程+E 核，否则卡 `EXITBS:START` |
| D2 | 显卡在不在驱动设备表？ | `Get-CimInstance Win32_VideoController \| Select Name,PNPDeviceID` | NVIDIA Turing(16/20 系) 及以后 → 可走 NullMoth 驱动；但**物理验证过的只有 RTX 5060**，Ampere（30 系）状态 Pending |
| D3 | 系统盘是 SATA 还是 NVMe？ | `Get-PhysicalDisk \| Select FriendlyName,BusType` | 优先 M.2 NVMe（走 `AppleNVMe` 通用 PCIe 驱动）；SATA 在新 PCH 上风险更高（见坑 9） |
| D4 | 单系统还是双系统？ | `Get-Disk \| Select Number,FriendlyName,SerialNumber,BusType` | 双系统要额外处理快速启动/启动顺序/时间差 |

**档位**：A = 独显在表内且不是 Ampere + NVMe + 单系统（最顺）；B = Ampere 或 SATA（本次就是 B）；C = 笔记本 MUX/双显卡（另有一堆坑）；D = 不存在驱动的卡（别装）。

**必须提前接受的三个事实**：
1. Arrow Lake（Core Ultra 200S）**苹果从未支持** —— 能跑通靠的是社区组合拳，不是官方支持。
2. Ampere/Pascal 的驱动**没有物理验证记录**，能不能出图必须实机验。
3. BIOS 9 项、装机 3 击、开箱向导 —— **没有任何工具能自动化**（苹果 EULA 禁止 + BIOS 无 API + 安装器是 GUI）。

---

## 1. BIOS：9 项，一项都不能漏

| 项 | 值 | 为什么 |
|---|---|---|
| VT-d / IOMMU | **Disabled** | 不关必卡 `EXITBS:START` `[实测]`+`[社区]` |
| Hyper-Threading | **Disabled** | 混合核心拓扑过不去 `[实测]` |
| Active E-Cores | **0** | 同上；关完 CPU 只剩 6C/6T 是**正常**的，不是坏了 |
| Re-Size BAR / Resizable BAR | **Enabled** | 驱动要 8 GB BAR；BAR 只有 256 MB 时桌面会黑屏只剩光标 `[厂商]` |
| Above 4G Decoding | **Enabled** | ReBAR 的前提 |
| CSM / Legacy Boot | **Disabled** | macOS 只认 UEFI |
| Secure Boot | **Disabled** | 与 OpenCore 冲突 |
| Fast Boot | **Disabled** | 会把启动顺序改回去 |
| SATA Mode | **AHCI** | 不能 RST/RAID |

装完之后：VT-d 别急着开（会重新卡）；超线程和 E 核可以一项项试回来，每改一项重启验一次。

---

## 2. 做安装盘（Windows 侧，10–40 分钟）

**工具**：[1401](https://github.com/nullmoth/1401)（开源，Windows GUI，"Install macOS on your PC from Windows"）

```
① 关掉系统代理（Clash 等会掐断 osrecovery.apple.com 的 TLS）
   实测报错长这样：SSL: UNEXPECTED_EOF_WHILE_READING
   而且 TUN 模式下关系统代理也没用 —— 要切「直连」或退出客户端
② 插 ≥16 GB U 盘（会被完全擦除）
③ 1401 → 选 U 盘 → 选 macOS 26 Tahoe → Write
   它自己会：扫硬件 → 按硬件生成 OpenCore EFI → 从苹果服务器下恢复镜像 → 写盘
④ GitHub 直连在国内常只有 1.6 KB/s（等于不可用），下载走镜像：
   https://gh-proxy.com/https://github.com/...
```

写完 U 盘根目录会有 `EFI/`、`com.apple.recovery.boot/`、`opencore-*.txt`（每次启动都会新增一个）。

---

## 3. 装机（3 个物理动作）

```
① 插 U 盘 → 开机按 F12 选它（或用 bcdedit 把 U 盘设为第一启动项）
② OpenCore 菜单 → 选 macOS Installer → 抹盘：
   磁盘工具 → 显示所有设备 → 选「整块盘」→ 抹成 APFS / GUID
   （只抹分区会失败：NTFS 卷在 macOS 下是只读的，会提示"磁盘已锁定"）
③ 装 macOS（约 20–40 分钟，会自动重启几次）→ 开箱向导：选语言、建账户（先别登 iCloud）
```

**如果每次重启都进 Windows**：那是 Windows 的快速启动把固件跳过了。管理员执行：
```powershell
powercfg /h off
Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' HiberbootEnabled 0
```
**判断有没有真走过 OpenCore**：看 U 盘根目录有没有**新增** `opencore-*.txt`。没有 = 根本没进 OC。

---

## 4. config.plist 关键项（成败就在这十几行）

用 Python 直接改，别手改 XML（改错一个标签全盘不启动）：

```python
import plistlib
p = r'<U盘>:\EFI\OC\config.plist'
c = plistlib.load(open(p,'rb'))

kq = c['Kernel']['Quirks']; bq = c['Booter']['Quirks']; uq = c['UEFI']['Quirks']
kq['ProvideCurrentCpuInfo'] = True      # 混合核心必须
kq['DisableIoMapper']       = True
kq['LapicKernelPanic']      = False
bq['DevirtualiseMmio']      = True      # 1401 默认给 False，方向是反的 [实测]
bq['SetupVirtualMap']       = True
bq['ResizeAppleGpuBars']    = 0         # 装驱动阶段可 -1
uq['ResizeGpuBars']         = -1        # 或 13（8GB BAR）；BIOS 已开 ReBAR 时 -1 即可

G = '7C436110-AB2A-4BBB-A880-FE41995C9F82'
nv = c['NVRAM']['Add'][G]
nv['csr-active-config'] = bytes.fromhex('FF0F0000')   # 0x0FFF 全关 SIP（0x0A43 会缺 task_for_pid 位）
nv['boot-args'] = ('keepsyms=1 nvfb=1 nvaccel=1 nvfbheads=1 -nvkmsnosmooth '
                   'amfi_get_out_of_my_way=0x1 amfi=0x80 ipc_control_port_options=0')
# 装系统阶段建议加上 -v keepsyms=1，好定位卡在哪
dl = c['NVRAM'].setdefault('Delete', {}).setdefault(G, [])
for x in ('boot-args','csr-active-config'):
    if x not in dl: dl.insert(0,x)      # 不删旧值，config 里的新值会被忽略

c['Misc']['Security']['SecureBootModel'] = 'Disabled'
c['PlatformInfo']['Generic']['SystemProductName'] = 'MacPro7,1'
plistlib.dump(c, open(p,'wb'), fmt=plistlib.FMT_XML, sort_keys=False)
```

**还要两个内核补丁**（治"时钟非单调"冻死，表现是伪装成卡在 `[AHCI][HBA] start:`）。它们是 `Kernel → Patch` 里的两条，`Count` 必须是 **2**，一条覆盖 12.0–26.3，一条覆盖 26.4+，Comment 里都带 `Remove non-monotonic time panic`。**1401 不自带这两条**，要从成功案例的 config 里抄（见文末参考仓库）。

**必备 kext 11 个**：Lilu / VirtualSMC / **AMFIPass**（缺它系统服务全挂）/ AppleMCEReporterDisabler / RestrictEvents / SMCProcessor / SMCSuperIO / USBToolBox / UTBDefault / WhateverGreen / 有线网卡驱动（Realtek 2.5G 用 `RTL812xLucy`）。
**必须关**：`CpuTopologyRebuild`。

---

## 5. 启动卡死：看屏幕现象直接对号

| 现象 | 根因 | 修法 |
|---|---|---|
| 交接内核后**一个字都不输出** | `debug=0x100` 把错误静默了；或 NVRAM 旧 boot-args 盖住新值 | 去掉 `debug=0x100`；把 `boot-args` 加进 `NVRAM → Delete` |
| 卡 `EB|LOG:EXITBS:START` | VT-d 没关 / 混合核心 / `DevirtualiseMmio` 方向错 | 关 VT-d + 关超线程+E 核 + `DevirtualiseMmio=True` + `ProvideCurrentCpuInfo=True` |
| 卡 `[AHCI][HBA] start:` | **不是 SATA 不兼容**，是时钟补丁缺失 | 加那两个 `non-monotonic` 补丁 |
| 到用户态后服务全挂：`setuid/task_for_pid: Operation not permitted`、`code signature page shift: 14` | SIP 缺 `CSR_ALLOW_TASK_FOR_PID(0x04)`；或 AMFIPass 没开 | `csr-active-config = FF0F0000` + 启用 AMFIPass |
| OpenCore 菜单只剩 `Reset NVRAM` | `ScanPolicy` 位掩码算错，把 APFS/USB 一起过滤了 | 用官方默认 `17760515` 或 `0` |
| 每次重启进 Windows | U 盘固件项失效，或快速启动跳过固件 | 重设 `bcdedit /set {fwbootmgr} bootsequence {U盘GUID}`；关快速启动 |
| 抹盘提示"磁盘已锁定" | NTFS 只读 | 抹**整块盘**为 APFS/GUID |
| 双系统时间差 8 小时 | macOS 写 UTC，Windows 读本地 | `RealTimeIsUniversal=1` + `w32tm /resync` |

---

## 6. 装显卡驱动（macOS 内，最后一步）

```
① 进 macOS 桌面 → 打开 U 盘 → NullMoth 文件夹
② GUI 法：双击 1401-Mac-*.zip → 右键 1401.app → 打开（绕过 Gatekeeper）
   它会：备份 config → 装驱动 → 加一条「1401: Remove NVIDIA driver」回滚菜单项
③ 命令行法（最新驱动）：
   cd /Volumes/<U盘>/NullMoth
   tar -xzf nullmoth-nvidia-<版本>.tar.gz -C /tmp
   cd /tmp/pkgroot && shasum -a 256 -c SHA256SUMS && sudo ./install.sh
④ 重启 → 系统设置 → 隐私与安全性 → 允许系统扩展 → 再重启
```

**验收（三条全中才算"出图"）**：
```bash
kmutil showloaded --list-only | grep nullmoth   # 期望 4 行：NVRM / NVAccel / NVRMFB / NVRMAGDC
system_profiler SPDisplaysDataType | head -20   # 期望 GeForce RTX 3070 且 Metal: Supported
# 第三条靠眼睛：拖窗口、切一次分辨率、放 1080p 视频 2 分钟，不黑不花不闪
```

**回滚**：重启 → OpenCore 菜单选 `1401: Remove NVIDIA driver` → 按 Y；或恢复 `config.plist.bak-*` + `sudo ./uninstall.sh`。

---

## 7. 12 个坑（按踩到概率排）

1. 别带 `debug=0x100` 引导 —— 它会让所有错误静默，屏幕看起来像"卡在菜单"。
2. 别只改 config 的 `boot-args` 而不加 `NVRAM → Delete` —— 旧值会赢，你以为改了其实没改。
3. 别开着 VT-d 试 —— 这是 `EXITBS` 的第一元凶。
4. 别留超线程和 E 核 —— 关完只剩 6C/6T 是正常的。
5. 别信 1401 默认的 `DevirtualiseMmio=False` —— 对 Arrow Lake 方向是反的。
6. 别手算 `ScanPolicy` —— 算错会把 APFS 一起过滤，菜单只剩 `Reset NVRAM`。
7. 双系统别留快速启动/休眠 —— 否则 `bcdedit` 写的启动顺序等于废纸。
8. 别在 macOS 里抹 NTFS 卷 —— 只会得到"磁盘已锁定"，要抹整块盘。
9. 别以为卡在 `[AHCI]` 就是 SATA 不兼容 —— 本机实测 B860 的 SATA 能工作，真因是时钟补丁。
10. 别关 `AMFIPass` —— 缺它系统服务全挂。
11. 别用老版本 1401 —— 老版本缺混合核心修复，可能缺 `_readme.txt` 里说的新参数；永远用最新。
12. 别直连 GitHub 下东西（国内实测 1.6 KB/s）—— 走 `gh-proxy.com` 镜像。
13. 别在写盘时开着 Clash 系统代理 —— 会掐断苹果恢复服务器的 TLS；TUN 模式要切直连。
14. 别一次改一堆配置 —— 一次一个变量，每次重启验证并记录。

---

## 8. 参考

- 驱动与 1401（开源，PolyForm Noncommercial 禁止商用）：[nullmoth/1401](https://github.com/nullmoth/1401)、[nullmoth/nvidia-macos-driver](https://github.com/nullmoth/nvidia-macos-driver)
- 同代 CPU 成功案例（Core Ultra 7 255HX + RTX 5060 Laptop + macOS 26，含那两个内核补丁）：[Coolzhy/EFI-OMEN16-am2xxx-public](https://github.com/Coolzhy/EFI-OMEN16-am2xxx-public)
- 官方排错表：[TROUBLESHOOTING.md](https://github.com/nullmoth/nvidia-macos-driver/blob/main/TROUBLESHOOTING.md)、设备表：[CARD-SUPPORT.md](https://github.com/nullmoth/nvidia-macos-driver/blob/main/CARD-SUPPORT.md)

---

## 9. 这份文件的诚实边界

- 已证明：macOS 26.7.1 装完、能进桌面、用户态服务不再批量崩溃、Windows 双系统共存、数据无损。
- **未证明**：RTX 3070 的 kext 加载与 Metal 加速 —— 验收输出当时没采集，属于待验证。
- 你的硬件只要和上面不同（尤其换 CPU 代数、换主板、换 NVMe），**具体值要重新判**，别照抄。

> 最后一句话：这套东西的价值不在"配置值"，在**判断顺序**。先判档位 → 再动 BIOS → 再动 config → 每次只改一个 → 每步都有可判定的证据。四天里一半时间是被"批量改 + 不看日志"烧掉的。
