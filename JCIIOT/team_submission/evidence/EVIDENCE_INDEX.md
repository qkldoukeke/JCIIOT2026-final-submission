# 最终证据索引

以下 15 个 JSON 是五题满分运行产生的原始证据。本轮合规修复不得修改其内容；完整性以相邻 `EVIDENCE_INDEX.json` 中的 SHA-256 为准。

| Level | Environment | Score | Time | Grasp router | Checkpoint |
|---|---|---:|---:|---|---|
| L1 | `FactorySorting1_3FO3ERFHISEM` | 10 | 39.584 s | `scripted_first_with_bc_recovery` | `team_submission/models/final/l1/model_epoch_20.pth` |
| L2 | `FactorySorting3_3FO3ERRPH7X9` | 15 | 39.549 s | `scripted_first_with_bc_recovery` | `team_submission/models/final/l2/model_epoch_50.pth` |
| L3 | `FactorySorting5_3FO3ERTPXEUT` | 20 | 40.750 s | `scripted_first_with_bc_recovery` | `team_submission/models/final/l3/model_epoch_100.pth` |
| L4 | `FactorySorting7_3FO3ERFKY9RN` | 25 | 49.415 s | `scripted_first_with_bc_recovery` | `team_submission/models/final/l4/model_epoch_50.pth` |
| L5 | `FactorySorting9_3FO3ERT2C5FP` | 30 | 98.462 s | `scripted_first_with_bc_recovery` | `team_submission/models/final/l5/model_epoch_100.pth` |

每题目录均包含：

- `score.json`：官方 App 评分结果；
- `result.json`：完整任务执行结果；
- `trajectory.json`：用于评分和回放的成功轨迹。

原始 JSON 中出现的 `/Users/cjr/...` 是历史运行时的来源路径，仅作为原始 provenance 保留；复现与定位请使用本索引中的仓库相对路径。
