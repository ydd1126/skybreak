# config.plist 速查（逐节正确值 / 为什么 / 错值会怎样）

> **标注约定**：`[实测]` = 本机成功组合（macOS 26.7.1 25G241，Gigabyte B860M POWER / Ultra 5 245K / RTX 3070）；
> `[厂商]` = NullMoth README / CARD-SUPPORT.md / OpenCore 文档 / Apple xnu 源码；`[社区]` = 社区报告；`未实测` = 判断未验证。
> 位表数字来自 Apple `bsd/sys/csr.h` 与 OpenCore/dortania 的 ScanPolicy 定义，不是凭印象写的。

## 1. ACPI

| 项 | 正确值 | 为什么 | 错值会怎样 |
|---|---|---|---|
| `Delete` 删 `DMAR` | `TableSignature=DMAR`、`All=True`、`Enabled=True` | 把固件 VT-d 表从内核视野摘掉，配合 BIOS 关 VT-d | 不删且 VT-d 没关 → 卡 `EXITBS`（S02） |
| `Add` `SSDT-PLUG-ALT` | 启用 | 本机 DSDT 里 `Processor(` 出现 **0 次**，CPU 是 `Scope(_SB){Device(PR00)…}`（`_HID ACPI0007`），`SSDT-PLUG` 的 `ObjectType==0x0C` 守卫在此静默失效 | 用错 `SSDT-PLUG` → 表加载成功但无任何效果（`plugin-type` 没注入） |
| `SSDT-EC-USBX` | 启用，**路径改成 `\_SB.PC00.LPCB`** | 本机 PCI 根桥叫 `PC00`（`_SB_PC00` 出现 1053 次，`_SB_PCI0` 0 次）；上游预编译版写的是 `PCI0` | 照抄上游 → Scope 不存在，整表加载失败 |
| `SSDT-AWAC-DISABLE` | 启用 | 本机 `AWAC._STA` 与 `RTC._STA` 由 `STAS` 互斥，`STAS=One` 打开传统 RTC（`PNP0B00`，IO 0x70–0x77 + IRQ8） | 不处理 → 拿不到可用 RTC，时间/唤醒异常 |
| `SSDT-RHUB` / `SSDT-H_EC-DISABLE` | **都关**（备着） | RHUB 只对移动 Icelake/华硕 Z490 必要；本机 `H_EC._STA` 本来就 `Return(Zero)` | 乱开 → 端口表被打乱 / 无益 |

## 2. Kernel

| 项 | 正确值 | 为什么 | 错值会怎样 |
|---|---|---|---|
| `Quirks → ProvideCurrentCpuInfo` | `True` | 混合核（P/E）必须，让内核拿到核心布局与计时器 | `False` → 卡 EXITBS 或启动后计时器乱 |
| `Quirks → DisableIoMapper` | `True` | 双保险：BIOS 的 VT-d 没关干净也不让内核用 IOMMU 映射 | `False` 且 VT-d 未关 → 卡 EXITBS |
| `Quirks → LapicKernelPanic` | `False` | 只有 legacy LAPIC 机器需要，新平台开着会制造 panic | 误开 → 启动即 panic |
| `Emulate → Cpuid1Data/Cpuid1Mask` | `55 06 0A 00 …`（Comet Lake `0x000A0655`）/ `ff ff ff ff …` | 把 CPUID 伪装成 macOS 认识的最新型号 | 不伪装 → 内核极早期拒绝 CPU |
| `Add → 最小 kext 集` | Lilu / VirtualSMC / **AMFIPass** / AppleMCEReporterDisabler / RestrictEvents / SMCProcessor / SMCSuperIO / USBToolBox / UTBDefault / RTL812xLucy | **AMFIPass 必须**；WhateverGreen 在本机要关（驱动要求移除 WEG 的 NVIDIA 补丁与 `agdpmod=pikera`） | 关 AMFIPass → `task_for_pid` 拒绝刷屏；开 WEG → 与驱动抢显示路径 |
| `Add → CpuTopologyRebuild` | `Enabled=False` | Arrow Lake 上必须关（按旧拓扑重排 P/E 会出错） | 开着 → 核数/调度错乱 |
| `Block` | `com.apple.iokit.IONDRVSupport`，`Strategy=Exclude`（**仅驱动阶段**） | 否则固件帧缓冲占显示 index 0，NVRMFB 拿不到 | 不 Block → 桌面黑但系统在跑；**安装阶段反而不能 Block** |
| `Patch` 两条时钟补丁 | 都 `Enabled=True`、`Count=2` | 修 macOS 26.4+ 与 12.0–26.3 的 TSC 非单调冻死 | 缺 → 冻在 `[AHCI][HBA] start:`（S03） |

## 3. Booter

| 项 | 正确值 | 为什么 | 错值会怎样 |
|---|---|---|---|
| `DevirtualiseMmio` | **`True`** | 1401 默认给 `False`，方向是反的；混合核 Intel 必须 `True` | `False` → 卡 EXITBS（本机在此绕了两天，见 case 文档） |
| `ResizeAppleGpuBars` | **安装 `0`** / **装完驱动 `-1`** | `0` = macOS 只看到最小 BAR（无驱动时跑固件屏）；`-1` = 用固件给的真实 BAR | 驱动阶段还用 `0` → 8 GB BAR 拿不到，桌面起不来 |
| `SetupVirtualMap` | `True` | 最终生效组合里是 `True` | 与 dortania「Gigabyte 板要关」相反；本机按 `True` 走通，出问题再试 `False` |
| `RebuildAppleMemoryMap` + `SyncRuntimePermissions` | 都 `True` | 新平台需要的内存映射/权限修正；与 `EnableWriteUnprotector=False` 配对 | 关掉 → 映射/权限报错；双开 `EnableWriteUnprotector` → 映射冲突 |

## 4. UEFI

| 项 | 正确值 | 为什么 | 错值会怎样 |
|---|---|---|---|
| `Quirks → ResizeGpuBars` | **`-1`**（本机成功值，BIOS 已开 ReBAR） | BIOS 已给大 BAR，OC 再改只增不确定性 | 与 README 驱动阶段的 `13`（2¹³ MiB = 8 GiB）混用时两边抢 BAR；两个值都要试过才算定论 |
| `Drivers` | `OpenRuntime`（必需）、`HfsPlus`、`OpenCanopy`、`ResetNvramEntry`、`OpenNtfsDxe` | 缺 `OpenRuntime` 直接不启动；`HfsPlus` 不在 OpenCore release zip 里，要取自 `OcBinaryData` | `OpenHfsPlus` 与 `HfsPlus` **只能开一个** |
| `PickerMode` | `External` | 图形选择界面（OpenCanopy）需要 | 留 `Builtin` 就没有图形界面 |
| `Resources/` | 必须有真实文件（Font/Image/Label） | OpenCore 1.0.8 的 release zip 里只有空目录 | 空的 → OpenCanopy 起不来 |

## 5. NVRAM

| 项 | 正确值 | 为什么 | 错值会怎样 |
|---|---|---|---|
| `Add → 7C436110-… → csr-active-config` | `FF0F0000`（= `0x0FFF`） | 全开 SIP 例外，见 §8 | `430A0000`（`0x0A43`）→ 服务全崩（S13） |
| `Add → … → boot-args` | §7 的三段串 | 驱动参数 + 调试参数 | 串写错 → 驱动不加载 / 看不到日志 |
| `Delete → 7C436110-…` | 必须含 **`boot-args`** 与 **`csr-active-config`** | 不删旧的，`Add` 会被 `- ignored, exists` 掉（S01 实测原文） | 只改 Add 不改 Delete → 改了等于没改 |

## 6. Misc / PlatformInfo

| 项 | 正确值 | 为什么 | 错值会怎样 |
|---|---|---|---|
| `Security → SecureBootModel` | `Disabled` | Apple Secure Boot 会拒绝非 Apple 签名的 kext | 开着 → 驱动 kext 全部加载失败 |
| `Security → ScanPolicy` | 调试 `0`，稳态 `17760515` | 见 §9 | 算错 → 菜单只剩 `Reset NVRAM`（S04） |
| `Security → Vault` | `Optional` | 没做 vault 签名的 OC 会拒绝启动 | `Secure` → 直接不启动 |
| `Boot → HideAuxiliary` | 调试期 `False` | 让 `Reset NVRAM`、Recovery、安装盘可见 | `True` → 找不到恢复/安装项 |
| `Generic → SystemProductName` + `Automatic`/`UpdateSMBIOSMode` | **`MacPro7,1`** + `True`/`Create` | macOS 15 与 26 都接受；`iMacPro1,1` 被 26 拒绝 | 旧机型 → `This version of Mac OS X is not supported…`（S08） |
| `Generic → SystemSerialNumber` / `MLB` / `SystemUUID` / `ROM` | 自己生成（`macserial -m MacPro7,1 -n 3 -g`）；`ROM` 是 6 字节 `<data>` | 序列号决定 iMessage/App Store 且必须唯一 | 抄别人的 → 服务被限；`ROM` 类型写错 → 不生效 |

## 7. boot-args 字典（作用 + 适用阶段）

| 参数 | 作用 | 适用阶段 | 来源 |
|---|---|---|---|
| `-v keepsyms=1` | 详细日志 + 保留内核符号（panic 栈才有函数名）；**一切排查的前提** | 安装、诊断、日常 | `[厂商]` |
| `debug=0x100` | 内核调试标志；本机实测表现为「错误被静默、屏幕无输出」 | 不建议常开 | `[实测]` |
| `revpatch=sbvmm` | RestrictEvents（<https://github.com/acidanthera/RestrictEvents>）：按 VMM 机型上报，换取正常更新/无内存报错 | 日常 | `[厂商]` |
| `nvfb=1` | 启用 NVIDIA 帧缓冲（NVRMFB） | 装完驱动 | `[厂商]` |
| `nvaccel=1` | 启用 NVAccel（WindowServer 合成走它） | 装完驱动 | `[厂商]` |
| `nvfbheads=1`（README 示例 `=4`） | 显示头数量；本机成功串用 1 | 装完驱动 | `[厂商]`/`[实测]` |
| `-nvkmsnosmooth` | 关闭驱动的 KMS 平滑处理（1401 默认串里带） | 装完驱动 | `[厂商]` |
| `-nvrmnoflip` | 强制保留 copy 路径，不启用 zero-copy 扫描输出（治「1 分钟后黑屏」） | 驱动排障 | `[厂商]` |
| `-nvrmnogo` | 驱动待命不自启 GPU（要 `nvrmctl go <pass>`） | 驱动排障 | `[厂商]` |
| `-nvrmnobootscreen` | 不截取启动画面快照 | 驱动排障 | `[厂商]` |
| `nvrmsettle=10000` | Turing 等卡固件起来要 10 s，给足等待 | Turing 机器 | `[厂商]` |
| `-nmlogooff` | 关掉驱动加的启动 logo | 观感/排障 | `[厂商]` |
| `amfi_get_out_of_my_way=0x1` + `amfi=0x80` | 放开 AMFI 检查，允许未签名 bundle/kext，并让 WindowServer 加载第三方 GPU bundle | 装完驱动 | `[厂商]` |
| `ipc_control_port_options=0` | 放宽 IPC 控制端口选项（配合未签名进程的 `task_for_pid` 类服务） | 装完驱动 | `[厂商]` |
| `npci=0x2000` / `0x3000` | 老平台 PCI 配置修法；**本机加了没用，已移除** | 老平台 | `[实测]` |
| `cpus=1` | 内核只用 1 核，用于分离「多核拓扑」与「其他」问题 | 诊断 | `[实测]` |
| `-x` | 安全模式（不加载第三方 kext），会挡住开箱向导 | 诊断 | `[厂商]` |
| `nv_disable=1` | 完全禁用 NVIDIA 驱动（回退用） | 驱动排障 | `[厂商]` |
| `agdpmod=pikera` | WhateverGreen 的 board-id 修法；**本驱动要求移除** | 不要用 | `[厂商]` |
| `alcid=NN` | 覆盖 AppleALC 的 `layout-id`（ALC897 可试 11/12/98/66/97） | 声卡排障 | `[厂商]` |

三段固定串（照抄）：

```
安装阶段：  -v keepsyms=1
诊断阶段：  -v keepsyms=1
装完驱动：  keepsyms=1 revpatch=sbvmm nvfb=1 nvaccel=1 nvfbheads=1 -nvkmsnosmooth amfi_get_out_of_my_way=0x1 amfi=0x80 ipc_control_port_options=0
```
> 1401 Mac app 会自动写入驱动阶段那串；手工改时**每次都要确认 `NVRAM → Delete` 挂着同名键**，否则不生效。

## 8. csr-active-config 位表（SIP）

来源：Apple `xnu/bsd/sys/csr.h`（`[厂商]` 原文 `#define CSR_ALLOW_* (1 << n)`，<https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/csr.h>）。
写入 NVRAM 是 little-endian `<data>`，所以 `0x0FFF` 写成 `FF0F0000`，`0x0A43` 写成 `430A0000`。

| 位 | 值 | 名称 | 作用 |
|---|---|---|---|
| 0 | `0x001` | `UNTRUSTED_KEXTS` | 允许未签名 kext |
| 1 | `0x002` | `UNRESTRICTED_FS` | 放开受限文件系统保护 |
| 2 | `0x004` | **`TASK_FOR_PID`** | 允许对任意进程用 `task_for_pid`（服务/调试依赖） |
| 3 | `0x008` | `KERNEL_DEBUGGER` | 允许内核调试器 |
| 4 | `0x010` | `APPLE_INTERNAL` | Apple 内部构建特权 |
| 5 | `0x020` | `UNRESTRICTED_DTRACE` | 无限制 DTrace |
| 6 | `0x040` | `UNRESTRICTED_NVRAM` | 无限制写 NVRAM |
| 7 | `0x080` | `DEVICE_CONFIGURATION` | 固件配置接口（`CSR_ALWAYS_ENFORCED` 之一） |
| 8 | `0x100` | `ANY_RECOVERY_OS` | 允许任意恢复系统（`CSR_ALWAYS_ENFORCED` 之一） |
| 9 | `0x200` | `UNAPPROVED_KEXTS` | 允许未批准 kext |
| 10 | `0x400` | `EXECUTABLE_POLICY_OVERRIDE` | 覆盖可执行策略 |
| 11 | `0x800` | `UNAUTHENTICATED_ROOT` | 允许未认证 root（root patch 必需） |

`0x0A43` vs `0x0FFF` 逐位差异（**差 `0x5BC`**）：

| 位 | 名称 | `0x0A43` | `0x0FFF` | 缺了会怎样（本机实测） |
|---|---|---|---|---|
| 0,1,6,9,11 | `UNTRUSTED_KEXTS`/`UNRESTRICTED_FS`/`UNRESTRICTED_NVRAM`/`UNAPPROVED_KEXTS`/`UNAUTHENTICATED_ROOT` | ✅ | ✅ | — |
| **2 `0x004`** | **`TASK_FOR_PID`** | ❌ | ✅ | **主犯**：`setuid/task_for_pid: Operation not permitted` 刷屏，服务成片失败 |
| 3,4,5 `0x008/0x010/0x020` | `KERNEL_DEBUGGER`/`APPLE_INTERNAL`/`UNRESTRICTED_DTRACE` | ❌ | ✅ | 调试与 DTrace 受限，部分系统组件走内部路径报错 |
| 7,8 `0x080/0x100` | `DEVICE_CONFIGURATION`/`ANY_RECOVERY_OS` | ❌ | ✅ | 本身 always enforced，缺失只影响策略表达 |
| 10 `0x400` | `EXECUTABLE_POLICY_OVERRIDE` | ❌ | ✅ | 签名页校验更严 → `code signature page shift: 14` |

**为什么缺 `0x04` 会让系统服务全挂**：`task_for_pid` 是 launchd/XPC 体系里让一个进程拿到另一个进程任务端口的唯一入口。
缺它时，凡需要跨进程取任务端口的服务（窗口服务、安装器、部分守护进程）都拿到 `Operation not permitted`；
再叠加 AMFIPass 被关（未签名 bundle 过不了签名页校验），就表现为「系统起来了但满屏签名错误、App 一开就崩」。
修法是两条同时做：**`csr-active-config=FF0F0000`** + **`AMFIPass.kext` 启用**（本机验证：服务不再报错，`csrutil status` = disabled）。

> 注意：驱动 README 的「tested value」是 `<430A0000>`（`0x0A43`）。本机按它试过并失败（S13），最终 `0x0FFF` 才通。两个值都留着，服务崩先往位表上想。

## 9. ScanPolicy 位表与组合

位定义（`[厂商]` OpenCore/dortania，<https://dortania.github.io/OpenCore-Post-Install/universal/security/scanpolicy.html>）：

| 值 | 名称 | 含义 |
|---|---|---|
| `0x00000001` | `FILE_SYSTEM_LOCK` | 只扫策略允许的文件系统 |
| `0x00000002` | `DEVICE_LOCK` | 只扫策略允许的设备类型 |
| `0x00000100` | `ALLOW_FS_APFS` | 允许 APFS |
| `0x00000200` | `ALLOW_FS_HFS` | 允许 HFS |
| `0x00000400` | `ALLOW_FS_ESP` | 允许 ESP |
| `0x00010000` | `ALLOW_DEVICE_SATA` | 允许 SATA |
| `0x00020000` | `ALLOW_DEVICE_SASEX` | 允许 SAS / Mac NVMe |
| `0x00040000` | `ALLOW_DEVICE_SCSI` | 允许 SCSI |
| `0x00080000` | `ALLOW_DEVICE_NVME` | 允许 NVMe |
| `0x00100000` | `ALLOW_DEVICE_ATAPI` | 允许光驱 |
| `0x00200000` | `ALLOW_DEVICE_USB` | **允许 USB（U 盘安装盘必需）** |
| `0x01000000` | `ALLOW_DEVICE_PCI` | 允许直连 PCI（如 VIRTIO） |

常用组合：

| 十进制 | 十六进制 | 组成 | 什么时候用 |
|---|---|---|---|
| `0` | `0x0` | 全放行 | **调试/装机期首选**：U 盘安装盘、Recovery、Windows 都出现 |
| `17760515` | `0x010F0103` | locks + APFS + SATA + SASEX + SCSI + NVME + PCI | 稳态：只认 APFS 系统盘，**隐藏 Windows 与 USB**（官方默认） |
| `19857667` | `0x012F0103` | 上者 + `ALLOW_DEVICE_USB` | 稳态下还想看见 U 盘 |

**本机教训（务必记住）**：曾把值算成 `0x01070003`（`17235971`），意图「去掉 NTFS 位和 USB 位以隐藏 Windows」。
它实际 = `locks + SATA(0x10000) + SASEX(0x20000) + SCSI(0x40000) + PCI(0x1000000)`，**连 APFS 位 `0x100` 都没了**——
于是所有 APFS 卷被过滤，菜单只剩 `Reset NVRAM`（S04）。正确做法：**先用 `0` 确认看得见所有东西，再收窄到 `17760515`**，每次改完重启看菜单。

## 10. 改完必跑的三个校验

```bash
# 1) plist 能被解析 + 关键值一眼确认（macOS 的 python3 来自 Command Line Tools）
python3 - <<'PY'
import plistlib
G = '7C436110-AB2A-4BBB-A880-FE41995C9F82'
c = plistlib.load(open('config.plist', 'rb'))
bq, kq, nv = c['Booter']['Quirks'], c['Kernel']['Quirks'], c['NVRAM']
print('DevirtualiseMmio     ', bq.get('DevirtualiseMmio'))
print('ResizeAppleGpuBars   ', bq.get('ResizeAppleGpuBars'))
print('ProvideCurrentCpuInfo', kq.get('ProvideCurrentCpuInfo'))
print('csr-active-config    ', nv['Add'][G]['csr-active-config'].hex())
print('boot-args            ', nv['Add'][G].get('boot-args'))
print('Delete has boot-args ', 'boot-args' in nv['Delete'].get(G, []))
PY

# 2) 引用的文件都真的在
ls EFI/OC/Kexts EFI/OC/ACPI EFI/OC/Drivers
```

Windows 侧（**本机没有 Python**，`python.exe` 只是 Microsoft Store 别名占位）：

```powershell
$xml = [xml](Get-Content -LiteralPath 'M:\EFI\OC\config.plist' -Raw)   # 解析失败即良构性不合格
function PV($k) { $n = $xml.SelectSingleNode("//key[.='$k']/following-sibling::*[1]")
                  if ($n.InnerText) { $n.InnerText } else { $n.Name } }
"DevirtualiseMmio=" + (PV 'DevirtualiseMmio'); "ScanPolicy=" + (PV 'ScanPolicy'); "boot-args=" + (PV 'boot-args')
```

> 校验器参考：本机 `opencore\_work\validate.ps1` 做过 4 层校验（XML 良构 → 独立解析器 → plist 结构 → 语义断言 + 磁盘一致性），
> 结果 `205 passed, 0 failed`；它抓到过三个真问题：`Resources/` 空、`Vault=Secure`、`ScanPolicy` 不含 USB。
