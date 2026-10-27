# 投放方案 —— 让需要的人真的看到这个仓库

> 2026-10-24 首版。仓库 `ydd1126/skybreak`。
> 现状：0 star / 0 fork / 0 watch。**原因不是内容，是零曝光。**

---

## 0. 先接受一个现实

黑苹果圈现在的流量池很小，而且 **NVIDIA 在这个圈子里是长期"劝退项"**。
大多数人已经换成 AMD 或 Intel 核显。所以「RTX 3070 也能跑 macOS 26」这件事，
第一反应不是「我要装」，而是「真的假的」。

**这意味着两件事：**
1. 泛流量渠道（HN / V2EX 首页）效率低，而且容易被质疑。
2. **精准流量渠道**效果最好 —— 就是当初和你一样卡住、正在搜「EXITBS」「[AHCI] HBA start」的那些人。

所以投放优先级不是「越多人看越好」，而是「让卡住的那个人搜到」。

---

## 1. 受众排序（按「真的会点开」的概率）

| 优先级 | 人群 | 在哪 | 为什么最可能点 |
|---|---|---|---|
| **P0** | 1401 / nvidia-macos-driver 的 issue 里报过「我也卡在 EXITBS」的人 | GitHub issues | 他们正在受苦，且已经在这个仓库的生态里 |
| **P0** | 搜「Arrow Lake hackintosh」「Core Ultra 200S macOS」的人 | Google / 论坛搜索 | 需求明确、样本极少、你的页面是少数几个真答案 |
| **P1** | r/hackintosh 的 NVIDIA/DDR5/新平台讨论 | Reddit | 英文区最大的黑苹果聚集地 |
| **P1** | InsanelyMac、TonyMacX86、Hackintosh-Forum | 论坛 | 老牌、搜索权重高 |
| **P2** | 中文圈：V2EX、远景论坛、黑苹果吧、知乎、B站 | — | 人多但转化低，且 NVIDIA 劝退情绪重 |
| **P3** | Hacker News / Lobsters | — | 偶尔爆，但「黑苹果」已过话题期 |

---

## 2. 立刻可做的三件事（不需要写新内容）

### 2.1 回帖到相关 issue（P0，最有效）

去这些地方，不要发广告，用「补充一个成功数据点」的口吻：

- `nullmoth/1401` **#10**（Core Ultra 7 265KF / B860M / 卡 EXITBS）
- `nullmoth/1401` **#11**（Core Ultra 5 245KF / RTX 5060 Ti / 静默卡 EXITBS）
- `nullmoth/1401` **#44**、**#49**（275HX / Arrow Lake-HX）
- `nullmoth/nvidia-macos-driver` **#252**（Arrow Lake-HX 卡 EXITBS）

**回帖模板（英文，直接改后缀）：**

```
Adding a second data point: Core Ultra 5 245K (Arrow Lake-S) + Gigabyte B860M POWER
+ RTX 3070 now boots macOS 26.7.1 (25G241) to the desktop.

What made the difference in my case, in order:

1. VT-d / IOMMU disabled in BIOS (was already reported in this thread).
2. Hyper-Threading = Disabled and Active E-Cores = 0. Resulting 6C/6T is expected.
3. Booter -> Quirks -> DevirtualiseMmio = TRUE. Your default is False for this
   platform; with False the handoff stopped at EB|LOG:EXITBS:START.
4. Two "Remove non-monotonic time panic" kernel patches, Count = 2
   (MinKernel 21.0.0 / MaxKernel 25.3.99 and 25.4.0 / 25.99.99).
   Without them the freeze *looks* like a hang at "[AHCI][HBA] start:".
   I initially misdiagnosed that as a SATA problem; B860 SATA is fine.
5. csr-active-config = FF0F0000 (0x0FFF) + AMFIPass enabled. With 0x0A43 I got
   "setuid/task_for_pid: Operation not permitted" and "code signature page shift: 14",
   and userspace services failed in bulk.

Caveat: I have not yet collected the kmutil/system_profiler verification output,
so I can only confirm the OS installs and reaches the desktop — not that the GPU
is accelerating. 1401 build was 2.3.3, driver 2.3.x.

Full notes and the config table: https://github.com/ydd1126/skybreak
```

**为什么这样写**：给的是 issue 作者真正需要的信息（可复现的差异点），链接只作为「细节在这」。纯链接帖会被当 spam 删掉。

### 2.2 Reddit r/hackintosh（P1）

标题（二选一，都要带硬件）：
```
[Success] Arrow Lake (Core Ultra 5 245K) + RTX 3070 + macOS 26.7.1 — the 5 changes that mattered
```

正文框架（Reddit 要求给细节，否则被删）：
1. Hardware 列表
2. 五个改动 + 每个的「不做的后果」
3. 一个症状表（EXITBS / AHCI / task_for_pid / ScanPolicy / 快速启动）
4. 诚实边界（GPU 未验证）
5. 链接

### 2.3 中文渠道（P2）

V2EX / 知乎 标题（挑一个）：
```
我在苹果没支持过的 CPU 上装上了 macOS 26，记下这 5 步
```

B 站/抖音标题：
```
苹果从没支持过这代 CPU，我们花了四天把它装上了 macOS 26
```

---

## 3. 还缺的「信任物料」（影响转化率，不影响曝光）

| 缺什么 | 为什么重要 | 怎么补 |
|---|---|---|
| **`kmutil` / `system_profiler` 的截图** | 现在最缺一块证据，所有人都会问「真的出图了吗」 | 进 macOS 跑两条命令，截图贴进 README |
| **一段 30 秒开机视频** | 比一百行文字有说服力 | 手机拍：按电源 → OpenCore 菜单 → 进桌面 → 拖窗口 |
| **`inspect-config.py` 的真实输出截图** | 证明「可执行验收」不是嘴上说说 | 终端跑一次截图 |
| **Release 里的 zip 附件** | 有人想整包下载 | 打一个 `skybreak-v1.0.0.zip` 挂上去 |

---

## 4. 追踪：怎么看有没有效果

仓库 → Insights → Traffic（只有 owner 能看）：

```
Views / Unique visitors        ← 曝光量
Referring sites                ← 哪个渠道真的带来了人
Clones                         ← 有人实际拉了代码（比 star 更能说明价值）
Popular content                ← 大家最先点开哪个文件
```

**判断标准**：如果 7 天内 `Referring sites` 出现 `reddit.com` 或 `github.com/nullmoth/...`，说明投放命中了；如果只有 `github.com` 自己，说明没人转。

---

## 5. 禁忌（会直接毁掉可信度）

1. 不要在 issue 里只贴链接 —— 会被当广告删，且显得心虚。
2. 不要写「完美支持」「100% 可用」—— 驱动状态是 Pending，一验就穿。
3. 不要同时发 5 个论坛 —— 同一作者短时间刷屏会被判定为推广。
4. 不要把中文 README 直接发到英文区 —— 用 `README.en.md`。
5. 不要买 star / 刷 star —— GitHub 会标记，且社区一眼看出。

---

## 6. 一句话结论

**内容已经够了，缺的是「把链接放到正在搜索这个问题的那个页面旁边」。**
最高性价比的动作不是发新文章，而是回到 `1401` 和 `nvidia-macos-driver` 的那几个 issue 下面，
用「补充一个成功数据点」的方式把 5 步差异写出来。
