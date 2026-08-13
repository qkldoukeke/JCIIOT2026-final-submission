# 团队生成 SOP 审计

- 结论：**通过**
- 已生成并验证：`5/5`
- 当前激活：`L1`
- 当前文件与归档一致：`True`
- Execute 按环境自动激活：`True`

| 关卡 | Word | 环境 | 来源 | 目标 | 结果 |
|---|---|---|---|---|---|
| L1 | case 1 | `FactorySorting1_3FO3ERFHISEM` | `input_5` | `output_4` | 通过 |
| L2 | case 3 | `FactorySorting3_3FO3ERRPH7X9` | `input_6` | `output_4` | 通过 |
| L3 | case 5 | `FactorySorting5_3FO3ERTPXEUT` | `aux_input_1` | `output_5` | 通过 |
| L4 | case 7 | `FactorySorting7_3FO3ERFKY9RN` | `input_2` | `output_5` | 通过 |
| L5 | case 9 | `FactorySorting9_3FO3ERT2C5FP` | `input_1` | `aux_output_1` | 通过 |

每份记录均保存 Word、语义地图和生成 Markdown 的 SHA-256。
坐标来源是匹配场景的语义地图；Word 只提供任务语义，不从图片猜测世界坐标。
