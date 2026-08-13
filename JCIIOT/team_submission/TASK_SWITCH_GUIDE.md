# L1–L5 切题与换电脑运行说明

## 一、换电脑启动

1. 把完整 `JCIIOT` 项目目录复制到新电脑，不要只复制 `team_submission`。
2. 安装并激活项目环境：

   ```powershell
   conda activate jci_clean
   Set-Location <新电脑上的项目路径>\JCIIOT
   powershell -ExecutionPolicy Bypass -File .\team_submission\start_frontend.ps1
   ```

3. 启动脚本优先使用当前激活的 Conda 环境，不依赖原电脑盘符。如果没有团队本地密钥文件，页面会保留官方侧边栏，由现场手动填写 LLM/VLM 配置。
4. 如果只想使用主办方原始入口，也可以运行：

   ```powershell
   python -m streamlit run app.py
   ```

## 二、如何切换题目

不需要修改代码、`robot_params.json`、模型路径或 SOP，也不需要重启页面。
`pick_up.py` 会根据当前官方环境名，从 `robot_params.json` 的
`grasp_policy.task_checkpoints` 自动选择该题已验证的 BC 恢复模型。

1. 保持侧边栏 **Inject Knowledge Base** 勾选。
2. 在 Task Panel 中找到 L1、L2、L3、L4 或 L5 对应行。
3. `LLM Plan` 只用于预览规划，可不点。
4. 直接点击该题所在行的 **Execute**；等当前任务评分结束后再运行下一题。

页面会把行号作为 `task_index` 传给独立 MuJoCo 子进程，自动选择场景、语义地图、任务物体、源站、目标站和团队生成 SOP：

| 题目 | task_index | 环境 | 源站 | 目标站 | 自动 SOP |
|---|---:|---|---|---|---|
| L1 | 0 | `FactorySorting1_3FO3ERFHISEM` | `input_5` | `output_4` | `generated_sop_l1.md` |
| L2 | 1 | `FactorySorting3_3FO3ERRPH7X9` | `input_6` | `output_4` | `generated_sop_l2.md` |
| L3 | 2 | `FactorySorting5_3FO3ERTPXEUT` | `aux_input_1` | `output_5` | `generated_sop_l3.md` |
| L4 | 3 | `FactorySorting7_3FO3ERFKY9RN` | `input_2` | `output_5` | `generated_sop_l4.md` |
| L5 | 4 | `FactorySorting9_3FO3ERT2C5FP` | `input_1` | `aux_output_1` | `generated_sop_l5.md` |

## 三、不要用这些操作切题

- 侧边栏 **SOP Document** 和 **Test ReadDocumentSkill** 是文档生成/验证工具，不是切题开关。
- 不要手动覆盖 `knowledge/sop1.md`～`sop5.md`。
- 不要修改主办方的 `knowledge/task_config.json`。
- 不要为每道题手动替换当前 checkpoint；当前运行路径会按实时环境完成程序化物理抓取，并自动选择该题团队自训练模型作为 BC 恢复路径。

## 四、快速确认切题正确

执行结果中的第一步和第三步应分别显示本题源站与目标站；环境名应与上表一致。团队 SOP 会在 Execute 构建 Agent 时按环境自动激活，因此 `team_submission/knowledge/current_generated_sop.md` 在任务间发生变化是正常现象。
