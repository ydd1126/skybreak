# 验收记录（Verification Log）

> 最后更新：2026-10-24

## 已确认（实机）

| 项 | 结论 | 依据 |
|---|---|---|
| macOS 26.7.1 (25G241) 安装 | ✅ 完成 | 真机安装 + 首次启动 |
| 启动到桌面 | ✅ 完成 | 真机 |
| 用户态服务 | ✅ 不再批量崩溃 | 引导日志（`task_for_pid` / `page shift` 类报错消失） |
| 双系统共存 | ✅ Windows 11 25H2 + macOS 26 双启动 | 真机 |
| 数据安全 | ✅ 100 GB+ 零丢失 | 迁移前 113 GB 校验备份 |
| **显卡出图** | ✅ **RTX 3070 已出图** | **2026-10-24 实机确认** |
| **Metal 加速** | ✅ **可用** | **2026-10-24 实机确认** |

## 存档缺口（不影响结论，影响可引用性）

以下是**已确认但没有留下原始命令输出**的项。引用具体字段时请现场重跑，不要凭记忆复述：

```bash
kmutil showloaded --list-only | grep nullmoth      # 期望 4 行：NVRM / NVAccel / NVRMFB / NVRMAGDC
system_profiler SPDisplaysDataType | head -20      # 期望 Chipset Model: NVIDIA GeForce RTX 3070 / Metal: Supported
sw_vers                                            # 26.7.1 / 25G241
nvram boot-args
csrutil status
```

## 仍未覆盖（真正的未知项）

| 项 | 状态 | 说明 |
|---|---|---|
| 音频 ALC897 | 未验证 | 本 skill 不含 AppleALC 方案（`layout-id` 需按机型试） |
| 蓝牙 | 未验证 | 未加任何蓝牙 kext |
| 睡眠 / 唤醒 | 未验证 | 未做长时挂机测试 |
| 显示器热插拔 / 高刷 DSC | 未验证 | 驱动已知问题，见 `references/boot-hang-diagnosis.md` S15/S16 |
| Turing / Ada 卡 | 未验证 | 厂商表里 `Pending`；本机只有 Ampere 数据点 |
| 其他主板 / CPU 代际 | 未验证 | 需按 `SKILL.md` 第二节重新判档、重新验证 |

## 更新规则

1. 新增一条「已确认」必须能指出**证据类型**（真机观察 / 命令输出 / 日志原文）。
2. 命令输出没留档的，标注「实机确认，输出未存档」，不得伪造输出。
3. 每次 macOS 或驱动升级后，重新跑上面 5 条命令并更新本文件。
