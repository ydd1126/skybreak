# NullMoth NVIDIA 驱动（nullmoth/nvidia-macos-driver）安装 · 验收 · 回滚

> **标注约定**：`[实测]` = 本机（macOS 26.7.1 25G241 / RTX 3070 `10DE:2488` SUBSYS `1458:404E`）上的真实结果；
> `[厂商]` = 驱动包内文档（README / TROUBLESHOOTING.md / CARD-SUPPORT.md / BASELINE-IDENTITY.json / install.sh 原文）；
> `[社区]` = 社区报告；`未实测` = 只读到文件、没在对应版本上跑过。
> 许可：**PolyForm Noncommercial 1.0.0** —— 可以自用/研究/教学/非营利，**不能商用**（`[厂商]` README + LICENSE）。

## 0. 它是什么（一段话）

用 NVIDIA 自家 r610 open kernel modules（GSP 固件 `610.57.04`）在 macOS 上实现 Metal 显示/加速：
`Metal app → NVMTLDriver.bundle → 翻译器(Apple AIR→SPIR-V) → NVK(Mesa Vulkan + NAK) → NVRM/NVAccel/NVRMFB/NVRMAGDC → GPU`（`[厂商]` README）。

| 组件 | 落盘位置 |
|---|---|
| Metal 插件 | `/Library/GPUBundles/NVMTLDriver.bundle` |
| NVK 后端 | `/Library/GPUBundles/nvmtl/` |
| 内核扩展 | `/Library/Extensions/NVRM.kext`、`NVAccel`、`NVRMFB`、`NVRMAGDC` |
| GSP 固件 | `/Users/Shared/nvfw/nvidia/610.57.04` |

**关键设计**：kext 装在 `/Library/Extensions` 并由 **Auxiliary Kernel Collection** 加载，
**绝对不要**再从 `EFI/OC/Kexts` 注入一遍（`[厂商]` README：「do not also inject them from `EFI/OC/Kexts`」）。OpenCore 只负责给 SIP 与 boot-args。

## 1. 两条安装路线

### 路线 A：1401 Mac app（最省事，会改 OpenCore 配置 + 加回滚菜单）

```bash
# 1) 下载（本机实测走镜像更快，见 §9）
curl -L -o 1401-Mac.dmg 'https://gh-proxy.com/https://github.com/nullmoth/1401/releases/latest/download/1401-Mac-<ver>.dmg'
# 2) 校验（对官方 SHA256SUMS 逐字符比对）
shasum -a 256 1401-Mac.dmg
# 3) 打开 dmg，运行 1401，按提示：Check this PC → Build/选 EFI → 安装驱动
open 1401-Mac.dmg
```

它会：找到启动本机的那块 OpenCore 分区 → **先把配置备份**（`config.plist.bak-<时间戳>`）→ 逐项展示要改什么 → 装驱动 → 在 OC 菜单里加
`1401: Remove NVIDIA driver` 与 `1401: Start once without NVIDIA driver`（`[厂商]` README）。
**跑 app 时要插着启动用的 U 盘/磁盘**，因为要改的就是那份 config。

### 路线 B：tar.gz + install.sh（完全手工、最可控）

```bash
tar -xzf nullmoth-nvidia-*.tar.gz && cd pkgroot
shasum -a 256 -c SHA256SUMS          # 每个文件都要 OK
sudo ./install.sh                    # 拷文件 + 重建 Auxiliary Kernel Collection
sudo shutdown -r now                 # 必须重启；注销不够
# 首次加载后 macOS 会要求在「系统设置 → 隐私与安全性」里允许扩展，允许后再重启一次
```

`install.sh` 实际做的事（本机包内 21 KB 脚本原文，`[厂商]`）：

| 步骤 | 原文要点 |
|---|---|
| 版本门禁 | `case $MAJ in 15\|26) ;; *) die "This driver is built for macOS 15 and 26 (this is $v); no changes made"` |
| 硬件确认 | 打印 `macOS $v, x86_64, NVIDIA GPU present` |
| 完整性 | `shasum -a 256 -c SHA256SUMS --quiet`，不一致直接 `die` |
| **先试建** | `kmutil create -n aux --volume-root / --allow-missing-kdk -B BootKernelExtensions.kc -S SystemKernelExtensions.kc --repository $T/repo -A $T/aux.kc -z`，再用 `kmutil inspect` 确认四个 `com.nullmoth.*` 都在 |
| 备份 | 现有 `AuxiliaryKernelExtensions.kc` 备份进 `$BK` |
| 落盘 | 建 `$NEWKC` 并再次 `kmutil inspect` 验证，最后才替换 |
| 提醒 | 检查 boot-args 有没有 `nvfb=1 nvaccel=1`，缺了会提示你去改 `config.plist` |

> ⚠️ 包内自相矛盾的一处：`install.sh` 门禁放行 15 与 26，但同包的 `BASELINE-IDENTITY.json` 把 **macOS 26 列在 `unqualified`** 里
> （原文：`"macOS 26"`），且 `VERSION`=1.14.2 的 runtime 最低要求是 `15.5`。以脚本实际行为为准，风险自担。

## 2. 装前必查（少一条都可能白装）

| 项 | 要求 | 依据 |
|---|---|---|
| BIOS | `Above 4G Decoding=On`、`CSM=Off`、`Re-Size BAR=On` | `[厂商]` README「BIOS」段 |
| SMBIOS 机型 | 能跑 macOS 15/26 的独显机型：`MacPro7,1`（15 与 26 都接受） | `_FACTS` §二 `[实测]` |
| boot-args 里的旧东西 | **移除** `nv_disable=1`、WhateverGreen 的 NVIDIA 补丁、`agdpmod=pikera` | `[厂商]` README |
| DeviceProperties | NVIDIA 卡**不需要**任何 DeviceProperties | `[厂商]` README |
| OC 注入 | 不要从 `EFI/OC/Kexts` 注入 NVRM 系列 | `[厂商]` README |
| SIP | `csr-active-config` 要放行未签名 kext；本机最终用 `FF0F0000`（`0x0FFF`） | `[实测]`，详见 `config-cookbook.md` §8 |

## 3. 装完要改的 OpenCore 配置（路线 B 手工做，路线 A 自动做）

| 位置 | 装驱动阶段的值 | 为什么 |
|---|---|---|
| `NVRAM → Add → 7C436110-… → csr-active-config` | `<FF0F0000>`（`0x0FFF`） | 未签名 kext + root patch 需要；本机若用 README 的 `<430A0000>` 会服务全崩 |
| `NVRAM → Add → … → boot-args` | `keepsyms=1 revpatch=sbvmm nvfb=1 nvaccel=1 nvfbheads=1 -nvkmsnosmooth amfi_get_out_of_my_way=0x1 amfi=0x80 ipc_control_port_options=0` | 帧缓冲+加速+AMFI 放行 |
| `NVRAM → Delete → …` | 必须有 `boot-args`、`csr-active-config` | 否则 `Add` 被 `- ignored, exists` 掉 |
| `UEFI → Quirks → ResizeGpuBars` | 本机成功值 `-1`；README 的驱动阶段值是 `13`（2¹³ MiB = 8 GiB） | BIOS 已开 ReBAR 时两者都指向「用大 BAR」，别混着来回改 |
| `Booter → Quirks → ResizeAppleGpuBars` | `-1` | 让 macOS 看见完整 BAR |
| `Kernel → Block` | `com.apple.iokit.IONDRVSupport`，`Strategy=Exclude` | 否则固件帧缓冲占显示 index 0，NVRMFB 拿不到 |
| `Misc → Security → SecureBootModel` | `Disabled` | Apple Secure Boot 会拒绝非 Apple 签名的 kext |

**安装器阶段必须反过来**（这就是为什么要有两份 config）：`ResizeAppleGpuBars=0`、`ResizeGpuBars=-1`、**不** Block IONDRVSupport、
boot-args 用 `-v keepsyms=1`。安装器没有 NVIDIA 驱动，跑在固件屏幕上（`[厂商]` README）。

## 4. 验收（四层，缺一层都不算装好）

```bash
# ① 文件完整性（在解包目录里）
shasum -a 256 -c SHA256SUMS                       # 期望：每个文件 OK

# ② 四个 kext 真的进了 Auxiliary KC
kmutil showloaded --list-only | grep nullmoth     # 期望：4 行
kmutil inspect -a x86_64 /Library/KernelCollections/AuxiliaryKernelExtensions.kc \
  | grep -oE 'com\.nullmoth\.[A-Za-z0-9]+' | sort -u   # 期望：NVRM / NVAccel / NVRMFB / NVRMAGDC

# ③ 系统是否认了卡与 Metal
system_profiler SPDisplaysDataType | head -20      # 期望：GeForce RTX 3070，Metal: supported

# ④ 桌面稳定性（真正的验收）
#    · 桌面连续显示 >2 分钟不黑（zero-copy 在约 60 秒后才打开，见 §6）
#    · 移动光标 / 拖动窗口不闪（闪 → 加 -nvrmnoflip 复测）
#    · 切一次分辨率与刷新率，回来仍然有画面
log show --last 5m --predicate 'eventMessage CONTAINS "WindowServer"' --style compact | tail -20
```

验收口径（**三条同时满足才算「出图」**）：**② 4 行 kext + ③ Metal: supported + ④ 桌面 2 分钟不黑**。
只满足 ②③ 而桌面黑，属 §6 的第 1/6 条，不算成功。

> **本机未采集 ②③ 的输出**（`kmutil showloaded | grep nullmoth` 与 `system_profiler SPDisplaysDataType` 都没留档）。按 `_FACTS` §7.4/§7.5，本机能证明的只有：**macOS 26.7.1 装完、能启动到桌面、用户态服务不再批量崩溃**；RTX 3070 的 kext 是否加载、Metal 是否可用属 **待验证**，不得写成已验证或"已出图"。要下结论，先在 macOS 里跑上面 ②③ 并把输出留存。

## 5. 回滚三层（从最轻到最彻底）

| 层 | 操作 | 影响面 | 适用 |
|---|---|---|---|
| L1 软回退 | boot-args 加 `-nvrmnogo`（驱动待命不启 GPU）或 `-nvrmnoflip`（不启用 zero-copy） | 只改参数，不动文件 | 刚装完怀疑显示路径 |
| L2 菜单回退 | OC 选择界面选 `1401: Start once without NVIDIA driver`，按 `Y`，再选 macOS/Recovery（**只这一次**不加载驱动，下次正常）；或选 `1401: Remove NVIDIA driver` 按 `Y`（下次启动自动卸干净并重启，**连 OpenCore 配置一起还原**） | 需要 1401 装过一次（它才会往菜单里加这两项） | 驱动导致进不去系统 |
| L3 彻底卸载 | `cd pkgroot && sudo ./uninstall.sh && sudo shutdown -r now`；再恢复 `EFI/OC/config.plist.bak-<时间戳>` | 删 kext、`/Library/GPUBundles` 相关件、`/Library/NullMoth/*`，重建 KC | 手工路线装的后想干净移除 |

`uninstall.sh` 原文要点（`[厂商]`）：`KEXTS="NVRM NVAccel NVRMFB NVRMAGDC NMXGPU NMXAccel NMXNPU"`；
删 `/Library/Extensions/$k.kext`、`NVMTLDriver.bundle / NVIDIAShared.bundle / nvmtl / nvmtl-allow.txt`、
`/Library/NullMoth/{kexts,firmware,gpu-userland,npu,driver-version,update-pending}`、`/Library/LaunchDaemons/com.nullmoth.osupdate.plist`，
用 `kmutil create -n aux … --repository "$RB/repo"` 重建集合并用 `kmutil inspect` 验证，最后发布验证过的备份集合。

> **1.14.0 用户特别注意**（`[厂商]` BODY-v1.14.2.md）：1.14.1/1.14.2 修了「装完起不来」，但**必须先卸掉 1.14.0**：
> 在 OC 菜单选 `1401: Remove NVIDIA driver` 按 Y，屏幕可能黑/冻几分钟是正常的，它卸完会自己重启，再装 1.14.2。

## 6. 已知未解决问题（照抄厂商原文，别期待）

| # | 问题 | 厂商状态 | 影响 |
|---|---|---|---|
| 1 | **HDMI / DisplayPort 音频**（从 NVIDIA 卡出声） | open | 只能用主板声卡（本机 ALC897） |
| 2 | **Chrome 的 WebGL**（Safari 正常）：Chrome 在 NVIDIA 上把 Metal 路径关了 | open | 用 Safari，或等 Chrome 侧改 |
| 3 | **运行时热插拔显示器** | open | 只能拔插线缆让它重新枚举 |
| 4 | **`Start once without NVIDIA driver` 可能黑屏/冻屏** | open（「Being worked on」） | 机器其实是起来的（能网络访问），画面要等下次正常启动 |
| 5 | AMD / Intel GPU 加速未在真卡上跑过；Intel NPU 固件未 ready | `[厂商]` 1.14.0 release notes | 别把 NPU 当可用能力 |
| 6 | 「桌面约 1 分钟后黑屏只剩鼠标」 | 1.14 已修（保持 copy 路径）；旧版用 `-nvrmnoflip` | 老版本必踩 |
| 7 | 双显示器改刷新率后另一块屏可能空白帧 | `BASELINE-IDENTITY.json` known_issue，计划 1.2 修 | 单屏无影响 |
| 8 | RTX 5090 物理验证、DRM、自动内部 EFI 迁移、DTrace 采集 | `unqualified` 清单 | 别指望 |

## 7. 版本演进（1.13 → 2.3.x）

| 版本 | 关键变化 | 来源 |
|---|---|---|
| 1.13 | Turing（GTX 16 / RTX 20）装驱动后 `AppleKeyStore` 循环 → Setup 自动加 `nvrmsettle=10000` | `[厂商]` TROUBLESHOOTING §2 |
| 1.14.0 | 大版本：`-nvrmnoflip` 成为受支持的显示稳定手段、DSC 压缩参数、热插拔/睡眠修一批、WebGL/mediaanalysisd 修复、AMD/Intel GPU 与 NPU 的 test 功能 | `[厂商]` BODY-v1.14.0 |
| 1.14.1 | 修「装完起不来」；改机型时漏改 SMBIOS 段的问题开始处理 | `[厂商]` BODY-v1.14.2「If you are on 1.14.0」 |
| 1.14.2 | ① 2560×1440@180 Hz 登录窗黑屏（1.14.0 把比原生小的分辨率也列出来所致）② 固件下载 HTTP 429/503 → 改为按目录一次下载 ③ RTX 40 上 SecurityAgent/Installer 崩溃 ④ Safari/照片/视频/iOS 模拟器因 GPU 检查退出 ⑤ 把残留的 `iMacPro1,1` 全改掉（含 board-id） | `[厂商]` BODY-v1.14.2.md |
| 2.3.6 / 2.3.7 | 本机已下载到手（`G:\1401-new\`），对应 1401 2.3.6 与驱动 2.3.7；**具体 changelog 本 skill 没有核到官方正文**，改动项 `未实测` | 文件名 + SHA256 |

> macOS 26 黑屏那几条的定性：**1.14 修的是「打包里的 macOS 26 版本加速器过期」**（`[厂商]` TROUBLESHOOTING §3
> 「macOS 26 (Tahoe): black desktop → The macOS 26 version of the accelerator in the package was out of date. Fixed in 1.14.」）；
> 1.14.2 修的是登录窗/高刷/崩溃那批。**装的时候一定用最新包**，老包会把老问题原样带过来。

## 8. 本机实际下载物与哈希（可直接核对）

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `nullmoth-nvidia-1.14.2.tar.gz` | 371,689,122 | `7c7f7ac97dbcdd48786d4384ffcb2d19199b6d3bc0fb013c71f63b766dea6be5` |
| `1401-Windows-1.14.2.zip` | 391,479,363 | `ec311afa095884193ce1fcba76430c902aa9e8c05cd4e89358c76b8108a310e7` |
| `1401-Mac-1.14.2.dmg` | 3,042,457 | `02ac2946c792ea1e038f23b1bbc290630cfcc0c3b38daba393e27fa14d48f64d` |
| `1401-Mac-1.14.2.zip` | — | `3e17c241b297acf5e22efb9e0b44e3b74b3d34b68c9c0d8d983be663970aef02` |
| `nmxnpu-source-1.14.2.tar.gz` | — | `9dd7c229e1e05cb6c574dfc7623cc3d467f84eb9f39ab4913203a36aaf1d4747`（官方清单里的哈希；**本机未下载该文件**，全盘不存在，别照着文件名找） |
| `nullmoth-nvidia-2.3.6.tar.gz` | 269,039,968 | `3855954d9069eca470e4dbc7f645a63bba888040ec099285ef044ece03ad8e4f` |
| `1401-Mac-2.3.6.zip` / `.dmg` | 2,456,733 | `3c3697f825e56bae594474f5431060e269d508e58509f5e176454261b6780482` / `5fe560bc07801d914eb02db8ba7f6bbcef878de3d9ba6dd8ff56e6df8b73a190` |
| `nullmoth-nvidia-2.3.7.tar.gz` | — | `237675011b81d60f8473a4f53ad08407e659e4a9fcf0dc571c5c15de579e39e6` |

包内 `BASELINE-IDENTITY.json`（1.14.2）记录的四个配对 kext 哈希（改一个就整套不匹配）：

```
NVRM     5675646ca340e685500b06696136ee022765fc9ad7d02cd8cf341ae46bdd29ee
NVRMFB   14d2c405514f53006fb2c92751d8d99b3ce44f13705920fec233c0cca7895384
NVAccel  0b13f33be484da039b44e896d2e4a7f8e4721848c5507de7030f5f307942c950
NVRMAGDC 270f9ef9ac9d2482689ed4d63d422e705e439509d0e3b62fc6bc96fdc9e693ed
```

## 9. 网络与镜像（本机实测的坑）

| 现象 | 原因 | 处理 |
|---|---|---|
| GitHub 直连 1.6 KB/s，几乎下不动 | 本机网络到 GitHub 直连被限 | 走 `https://gh-proxy.com/https://github.com/...`，实测 400–4400 KB/s |
| 写安装盘时报 `SSL: UNEXPECTED_EOF_WHILE_READING`（连 `osrecovery.apple.com`） | Clash 系统代理掐断 Apple 恢复服务器的 TLS | 写盘前把系统代理关掉（`ProxyEnable=0`），或代理里给该域名加直连 |
| 下载被「HTTP 429 / 503」挡住 | 固件服务器限流（1.14.2 就是为此改成按目录一次下载） | 升级到 1.14.2+ 或错峰重试 |

## 10. 装不上时先看这张表

| 报错/现象 | 原因 | 处理 |
|---|---|---|
| `This driver is built for macOS 15 and 26 (this is X)` | 系统版本不在 15/26 | 换盘或升级系统；别改脚本门禁硬来 |
| `SHA256SUMS mismatch: re-download the package` | 下载不完整 | 重下（走镜像时尤其容易截断） |
| `kmutil refused com.nullmoth.NVRM` | KC 构建被拒（macOS 26 会静默跳过非 root 拥有的 kext） | 确认以 root 执行、文件属主正确 |
| 装完桌面黑、但机器能 ping 通 | 显示路径没起来（§6 第 1/4 条） | `-nvrmnoflip` 或 `-nvrmnogo` 排查；必要时 L2 回退 |
| `system_profiler` 里没有 GeForce | 驱动没加载（KC 里没有 kext） | 回到 §4 的 ② 检查 |
