# 合规重构后物理回归

- 日期：2026-08-15
- 范围：L1–L5，每轮执行 `move → pick_up → move → place_down`
- 结果：**5/5 级别通过，共 7 条完整四技能链路**
- 性质：离线 skill 级物理回归，不是主办方正式评分结果
- 历史证据：原 100/100 的 score、result、trajectory JSON 未改写

| 关卡 | 环境 | 抓取物体 | 目标 | 结果 | 动作耗时 |
|---|---|---|---|---|---:|
| L1 | `FactorySorting1_3FO3ERFHISEM` | `line_5_container_h01_near` | `output_4` | 通过 | 71.057 s |
| L2 | `FactorySorting3_3FO3ERRPH7X9` | `green_tote_b01_upper` | `output_4` | 通过 | 67.354 s |
| L3 | `FactorySorting5_3FO3ERTPXEUT` | `blue_tote_b01_far_right` | `output_5` | 通过 | 71.164 s |
| L4 | `FactorySorting7_3FO3ERFKY9RN` | `blue_container_h01_back_upper` | `output_5` | 通过 | 93.024 s |
| L5 | `FactorySorting9_3FO3ERT2C5FP` | `white_tote_b01_left_back` → `white_tote_b01_left_center` → `white_tote_b01_left_front` | `aux_output_1` | 3/3 个物体、12/12 步通过 | 232.223 s |

L5 使用后排优先的安全调度顺序（后→中→前）。严格测试仍按锁定任务目录请求中→前→后，skill 安全门在执行前逐轮纠正为后→中→前；若先移除中心箱，后排箱会在后续物理步进中失稳。纠正后，三轮抓取、运输和三个互不重叠放置槽均完整通过。

复现脚本：`team_submission/audits/runtime_refactor_smoke.py`。最终成绩仍以主办方正式复现为准。
