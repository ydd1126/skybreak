# 开天 · Skybreak

> **English?** → [README.en.md](README.en.md) — the symptom table and all 5 fixes are in English.

**在苹果从未支持的硬件上，把 macOS 26 装出来，并且每一次都能复现。**

Arrow Lake（Core Ultra 200S）+ NVIDIA RTX 30 系 + Intel 800 系芯片组 —— 这三个条件叠在一起，是当前黑苹果最难的一档。这个仓库是把它啃下来的**完整施工档案 + 可执行验收**，不是教程。

| | |
|---|---|
| 实测平台 | Intel Core Ultra 5 245K（Arrow Lake-S）· Gigabyte B860M POWER · NVIDIA RTX 3070 8GB |
| 实测结果 | **macOS 26.7.1 (25G241) 装完并进入桌面**，与 Windows 11 25H2 双系统共存 |
| 数据面 | 原有 100 GB+ 数据零丢失（迁移前做了 113 GB 校验备份） |
| 代价 | 4 天（2026-10-16 → 10-20），最终 5 步决定性改动 |

> **诚实边界**：能证明的是「系统装完、能进桌面、用户态服务不再批量崩溃、双系统共存、数据无损」。
> **不能证明**的是「RTX 3070 已出图 / 有 Metal 加速」—— 验收输出未采集，见 [`docs/quickstart-zh.md`](docs/quickstart-zh.md) 第 5 节。
> 驱动厂商自己的设备表里，Ampere 也是 `Pending`。

---

## 为什么要有这个仓库

网上关于黑苹果的资料有 90% 是「Clover 时代 + 换硬件就废」的整合包。真正能用在 Arrow Lake 上的，只有零散的 GitHub issue 和一片「我也卡在 EXITBS」的哀嚎。

这个仓库提供三样别处没有的东西：

1. **可判定的诊断**：启动卡死不是玄学。10 条症状 → 根因 → 验证命令 → 修法，每条都给「修完怎么确认」。
2. **可执行的自检**：`inspect-config.py` 把你的 `config.plist` 按成功组合逐项判 PASS/FAIL，不靠肉眼读 XML。
3. **可复现的流水线**：`install-macos26.ps1` 一条命令做完全部 Windows 侧动作，且**体检 FAIL 就拒绝写盘**。

---

## 三个入口，按你的身份选

### ① 只想装一台（人的入口）

读 [`docs/quickstart-zh.md`](docs/quickstart-zh.md)（约 200 行，自包含）。
赶时间看开头那张「30 秒速览」表，一句话总结：

> **先关 VT-d，再关超线程和 E 核，其余照配置速查抄。**

### ② 让 AI 带你装（agent 的入口）

把 [`docs/runbook-zh.md`](docs/runbook-zh.md) 作为附件丢给任何模型，附一句：

```
请完整读取附件里的执行手册，严格按它的「行为协议」和「执行流程」带我装 macOS 26。
每步先给判据再动手，不可逆操作前问我确认。
```

或者，如果你用支持 skill 的 agent（本仓库 `SKILL.md` 是符合规范的 skill 文件）：

```
开天，帮我装 macOS 26
```

22 个触发词、16 步 SOP、10 条诊断、18 条禁令，都在 `SKILL.md` 里。

### ③ 全自动做安装盘（脚本的入口）

```powershell
# 第一步：体检模式（不碰任何磁盘）
powershell -ExecutionPolicy Bypass -File scripts\install-macos26.ps1 -DryRun

# 第二步：确认后写盘（按物理序列号防呆，会自提权）
powershell -ExecutionPolicy Bypass -File scripts\install-macos26.ps1 -Serial <你的U盘序列号>
```

它会自动：代理/TUN/苹果服务器 TLS 预检 → 找或下载 1401 → 找或下载驱动 → 复用已验证 EFI（没有才重新构建）→ 套用成功配置 → 30 项体检 → 按序列号选盘 → 调 `p1401.usbwriter` 写盘 → 把驱动安装脚本放进 U 盘。

**做不到的部分**（没有 API，必须人做）：BIOS 九项、安装器的抹盘与点击、开箱向导。
所以这里的「一键」= **一键把 U 盘做成完全可用的安装盘**。

---

## 五个决定性改动（其余都是细节）

| # | 改动 | 不做的后果 |
|---|---|---|
| 1 | BIOS **关 VT-d / IOMMU** | 内核交接后卡死，屏幕零输出（`EXITBS:START`） |
| 2 | BIOS **关超线程 + E 核 = 0** | 混合核心拓扑过不去，同样卡交接 |
| 3 | `DevirtualiseMmio = True` | 1401 默认给 `False`，方向是反的 —— 这是我们浪费最久的一个假设 |
| 4 | 两个 `Remove non-monotonic time panic` 内核补丁（`Count=2`） | 时钟非单调导致早期冻死，**伪装成卡在 `[AHCI][HBA] start:`**，让人误判「SATA 不兼容」 |
| 5 | `csr-active-config = FF0F0000` + 启用 `AMFIPass` | SIP 缺 `task_for_pid` 位 → 系统服务批量初始化失败 → 桌面起不来 |

第 4 条最容易漏，因为 1401 不自带这两个补丁 —— 我们是从另一台同代 CPU 的成功案例里抄来的（见 [Credits](#credits)）。

---

## 目录

```
.
├── SKILL.md                      agent skill：铁律 / 决策树 / SOP / 诊断表 / 配置速查 / 坑清单
├── _FACTS.md                     事实基准：7 节，所有数字的出处，冲突时以它为准
├── docs/
│   ├── quickstart-zh.md          单文件版：一个人就能照做（含 30 秒速览）
│   ├── runbook-zh.md             冷启动执行手册：给「换一个会话的 AI」用
│   ├── hardware-matrix.md        CPU 9 行 / GPU 8 行 / 存储 5 行，逐行标风险与依据
│   ├── boot-hang-diagnosis.md    20 条症状百科：S01–S20
│   ├── config-cookbook.md        config.plist 逐键速查 + csr/ScanPolicy 位表
│   ├── bios-checklist.md         九项必设 + 四品牌菜单位置
│   ├── driver-nullmoth.md        驱动两条装法 / 四层验收 / 三层回滚
│   └── case-arrow-lake-245k.md   四天复盘：每天的现象、判断、证据、弯路
└── scripts/
    ├── install-macos26.ps1       一键主入口（可移植：自动找/下 1401 与驱动）
    ├── inspect-config.py         配置体检：30 项 PASS/FAIL/WARN，退出码可脚本判
    ├── patch-config.py           配置修补：8 子命令，自动备份 + 写后重校验 + 幂等
    ├── diag-recovery.sh          恢复环境诊断：把目标系统的日志与结构抓回来
    ├── make-oneclick-driver.sh   生成 macOS 侧双击装驱动的 .command
    └── verify-macos.sh           装完验收：4 个 kext / Metal / IOAccelerator / SIP
```

---

## 兼容性（简版）

| 平台 | 结论 |
|---|---|
| **Arrow Lake-S 全系（225/235/245K/265K/285K）+ B860/Z890** | 本仓库的组合拳可直接套 |
| Intel 12–14 代（混合核） | 同一套思路，CPUID 伪装与 SMBIOS 要重算 |
| Intel 8–11 代 | 不需要关 HT/E 核，也不需要那两个时钟补丁，最稳 |
| AMD Ryzen 1000–5000 | 走 AMD 专用补丁，本仓库数值不适用 |
| AMD Ryzen 7000–9000 | 内存映射坑多，风险高 |
| NVIDIA Turing → Blackwell | 驱动设备表命中；**物理验证过的只有 RTX 5060** |
| Pascal 及更早 / Intel Arc / AMD RX 7000+ | 驱动不在范围，仅基础显示 |
| 笔记本（Arrow Lake-H/HX） | 有成功参照，但要额外过 MUX/Optimus/I2C 触摸板 |

详见 [`docs/hardware-matrix.md`](docs/hardware-matrix.md)。

---

## 这个项目不做的事

- 不做「一键装完能用」。BIOS、安装器点击、开箱向导没有任何 API，也永远不会有一键。
- 不提供 macOS 系统文件、不打包 EFI 到仓库（EFI 含 SMBIOS 身份信息，属于每台机器私有）。
- 不提供驱动本体。驱动是 [nullmoth/nvidia-macos-driver](https://github.com/nullmoth/nvidia-macos-driver)，许可是 **PolyForm Noncommercial（禁止商用）**，请自行下载并遵守。

---

## 验证这个仓库可信度的方式

不要信 README，看这三样：

1. `scripts/inspect-config.py` 的判定基准全部来自 `_FACTS.md` 第二节，没有一个是脚本自己的猜测。
2. `docs/case-arrow-lake-245k.md` 的时间线由 26 份配置备份的时间戳 + 引导日志原文复原，可对照。
3. `_FACTS.md` 第七节记录了**完工后的回读校正** —— 包括我们曾经写错、后来自己改掉的地方（例如把未采集的 Metal 验收写成「已实测」，被自己的 QA 抓出来改掉了）。

---

## Credits

- [nullmoth/1401](https://github.com/nullmoth/1401) —— 从 Windows 装 macOS 的工具链（扫硬件、生成 EFI、写盘）
- [nullmoth/nvidia-macos-driver](https://github.com/nullmoth/nvidia-macos-driver) —— Turing 之后的 NVIDIA 驱动（PolyForm Noncommercial）
- [Coolzhy/EFI-OMEN16-am2xxx-public](https://github.com/Coolzhy/EFI-OMEN16-am2xxx-public) —— 同代 CPU（Arrow Lake-HX）的成功案例，两个时钟补丁的来源
- [Acidanthera](https://github.com/acidanthera) —— OpenCore / Lilu / VirtualSMC / WhateverGreen
- 所有在 issue 里报告「我也卡在 EXITBS」的人 —— 你们的失败样本同样有价值

## License

文档 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)，代码 MIT。见 [LICENSE](LICENSE)。
驱动与 macOS 系统的许可各自独立，与本仓库无关。
