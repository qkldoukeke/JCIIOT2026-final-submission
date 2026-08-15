# JCIIOT 2026 最终提交：CI Lab

本仓库是 CI Lab（参赛 ID：`doukeke`）的 JCIIOT 2026 工业具身智能挑战赛最终提交。

- 代码仓库：<https://github.com/qkldoukeke/JCIIOT2026-final-submission>
- 排行榜提交：<https://github.com/JCIIOT2026/JCIIOT2026/issues/13>
- 机器可读提交清单：`JCIIOT/team_submission/submission_manifest.json`
- 当前五题复测证据索引：`JCIIOT/team_submission/evidence_retest_20260815/EVIDENCE_INDEX.json`
- 历史五题证据索引：`JCIIOT/team_submission/evidence/EVIDENCE_INDEX.json`

## 最终结果

以下结果由本地官方 App 评分流程生成，正式成绩仍以主办方复现为准。

| Level | Score | Time | Environment |
|---|---:|---:|---|
| L1 | 10/10 | 40.163 s | `FactorySorting1_3FO3ERFHISEM` |
| L2 | 15/15 | 38.976 s | `FactorySorting3_3FO3ERRPH7X9` |
| L3 | 20/20 | 39.762 s | `FactorySorting5_3FO3ERTPXEUT` |
| L4 | 25/25 | 46.651 s | `FactorySorting7_3FO3ERFKY9RN` |
| L5 | 30/30 | 102.583 s | `FactorySorting9_3FO3ERT2C5FP` |
| Total | **100/100** | **268.135 s** | L1–L5 |

当前重构后复测的 `score.json`、`result.json` 和 `trajectory.json` 保存在 `JCIIOT/team_submission/evidence_retest_20260815/`，并使用 SHA-256 固定；2026-08-11 的历史满分证据继续保留在 `JCIIOT/team_submission/evidence/`，未被覆盖。

## 获取代码与模型

不要使用 GitHub 网页的 **Download ZIP** 取得运行代码，因为 GitHub 源码 ZIP 只包含 Git LFS 指针，不能直接加载模型。请使用：

```powershell
git lfs install
git clone https://github.com/qkldoukeke/JCIIOT2026-final-submission.git
Set-Location .\JCIIOT2026-final-submission
git lfs pull
```

然后按 [复现指南](./复现指南.md) 配置环境并进入 `JCIIOT/` 启动官方 `app.py`。

## 技术材料

- [技术报告](./技术报告.md)
- [复现指南](./复现指南.md)
- [新颖性声明](./新颖性声明.md)
- [提交合规说明](./提交合规说明.md)
- [实验开发日志](./实验开发日志.md)
- [最终提交清单](./最终提交清单.md)

## 固定官方基准

- 主办方仓库：<https://github.com/JCIIOT2026/JCIIOT2026>
- 固定提交：`80d8f9216b0716c6c7a20c19582b532ff1c9cdf2`
- 官方归档 SHA-256：`d5245cb57b0c9c99253f397950a30a4255e98af78390cc2d0850784cb84bda2a`
- 边界审计：4,966 个普通文件逐字节一致，6 个官方 LFS 对象正确实体化，修改 0、缺失 0、违规 0。

## 合规边界声明

主办方禁止修改的源码已通过上述固定基准审计。当前 `skills/` 只依赖团队声明的 `CompetitionEnvBackend` 能力协议，不再直接读取 MuJoCo、具体 backend 私有字段或主办方环境实现；物理抓取所需的仿真访问统一封装在允许修改的 `workflows/SemanticBackendAdapter` 后端边界内。该自定义后端扩展是否符合主办方最终接口解释，仍以主办方复现和审查结论为准。

训练配置已经改为从 `JCIIOT/` 根目录解析的相对路径，但训练 HDF5 未随 GitHub 提交。最终推理可复现；从头训练只有在另行取得训练数据清单中的 HDF5 后才可复现。
