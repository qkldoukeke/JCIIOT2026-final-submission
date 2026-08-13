# 竞赛提交合规清单

## 结论

依据主办方《直播分享 (1).pptx》12 页培训内容、原始 GitHub ZIP 和当前工作树审计，当前方案的源码修改范围符合 PPT 给出的选手主战场。主办方维护文件无源码修改；五题均有正式满分记录；五份 SOP 均为团队从对应 Word 生成，并已实现 Execute 按环境自动激活。

五题均采用程序化物理抓取作为主路径，并由该题团队 BC checkpoint 承担恢复。`pick_up.py` 根据当前官方环境名自动选择五个已验证权重，不需要人工替换配置。2026-08-11 使用相同最终 skill 实现并逐题加载对应参数与模型，五题记录合计 100/100；提交版自动路由已完成五环境单元验证，仍需在主办方环境最终复现。

## PPT 要求逐项核对

| 主办方要求 | 当前状态 | 证据 |
|---|---|---|
| 完整链路为 move → pick_up → move → place_down | 通过 | 五题正式 result 均按该链路执行；L5 重复三次 |
| 评分依据执行轨迹 JSON | 通过 | `JCIIOT/team_submission/evidence/` 中保留五题最终 score/result/trajectory |
| 不修改 robosuite、机器人/物体、控制器 | 通过 | 4,972 个受保护文件哈希审计，违规 0 |
| 不修改 generated_maps | 通过 | 包含在受保护目录逐文件审计中 |
| 不修改 environments/base.py、robosuite_backend.py | 通过 | 与参考 ZIP 逐字节一致 |
| 不修改 core/types.py | 通过 | 与参考 ZIP 逐字节一致；接口字段未改 |
| 不修改 app.py、task_config.json | 通过 | 与参考 ZIP 逐字节一致 |
| 优化 skills/*.py | 通过 | 导航、抓取、放置、SOP、任务映射均位于 skills |
| knowledge/ 与 robot_params.json 可优化 | 通过 | 执行参数在 robot_params；主办方 SOP 已恢复参考内容 |
| 可自训练 robomimic 并替换 checkpoint | 通过 | L1–L5 均有团队训练 checkpoint，并按环境自动路由 |
| LLM 输出已注册技能和精确 object_name | 通过 | 团队 SOP + 锁定任务映射 + skill 层运行时纠正 |
| Execute 使用独立 MuJoCo 子进程 | 未改动 | app、task_subprocess_runner 与主办方源码保持原逻辑 |
| SkillResult / ExecutionContext 结构不可改 | 通过 | `core/types.py` 逐字节一致；新增信息仅放 payload |

## 受保护边界审计

- 参考：官方 GitHub commit `01032e8dc97fcd376502b71327ad8cbea6b6589b`
- 受保护参考文件：4,972
- 逐字节一致：4,971
- Git LFS 正确实体化：1
- 修改：0
- 缺失：0
- 违规新增源码：0

唯一非逐字节项是 `robosuite/robosuite/model_epoch_150.pth`。参考 ZIP 内为 Git LFS 指针；当前实际文件大小 139,543,773 字节，SHA-256 为 `ef5910f6a9f6309b5ced617762dffeb1169a8b0cfcea892d158e6b483252169f`，与指针声明完全一致，属于官方资产正确下载。

本地受保护目录中的 Python 缓存、采集示范文件和安装元数据均由 Git 忽略，不进入 GitHub 提交。

## 当前允许范围内的源码变化

修改的 skill：

- `move.py`：携物安全余量、受验证离站、A* 降级和路径审计 payload；
- `pick_up.py`：动态抓取优先、BC 恢复、在线初始化与物理成功验证；
- `place_down.py`：安全区预转向、语义目标适配、多物体槽位；
- `read_document.py`：Word → 任务目录 → 语义地图 → 团队 SOP；
- `library.py`：按实时环境自动激活对应团队 SOP。

新增的 skill：

- `grasp_alignment.py`；
- `grasp_fallback.py`；
- `task_station_mapping.py`。

参数变化位于允许的 `JCIIOT/knowledge/robot_params.json`。最终模型、证据和审计工具位于 `JCIIOT/team_submission/`；原始训练数据与历史回退包仅保留在本地，不上传。

## 团队 SOP 使用状态

- `generated_sop_l1.md` 至 `generated_sop_l5.md`：5/5 通过来源与绑定校验；
- 每份记录 Word、语义地图、生成 Markdown 的 SHA-256；
- 当前激活文件为 L1，且与 L1 生成归档逐字节一致；
- Execute 时 `skills/library.py` 依据 backend 环境和锁定任务配置自动切换对应生成 SOP；
- 主办方 `knowledge/sop1～sop5.md` 没有被团队生成器覆盖。

需要准确表述：规划器仍会读取主办方 `knowledge/`，这是官方 planner 的既有行为；团队生成 SOP 随后从 `team_submission/knowledge/` 注入，并通过环境自动选择和 authority rules 对当前任务生效。因此不是“完全不读取主办方知识”，而是“当前任务执行使用团队生成 SOP 作为任务级约束，同时保留平台基础知识”。

## 正式客观成绩

| 关卡 | 得分 | 正式时间 | 当前结论 |
|---|---:|---:|---|
| L1 | 10/10 | 39.584 s | 最终五题联测记录 |
| L2 | 15/15 | 39.549 s | 最终五题联测记录 |
| L3 | 20/20 | 40.750 s | 最终五题联测记录 |
| L4 | 25/25 | 49.415 s | 最终五题联测记录 |
| L5 | 30/30 | 98.462 s | 最终五题联测记录 |

现有正式得分合计 100/100。主观创新分不会因客观满分自动获得；必须同时提交 `NOVELTY_STATEMENT.md`，把贡献、消融、边界和局限讲清楚。

## 打包前必须执行

1. 再跑一次 `verify_official_boundary.py`，要求违规项为 0。
2. 再跑一次 `verify_generated_sops.py`，要求 5/5 通过。
3. 排除所有 `__pycache__`、`.pyc`、`demonstrations_private`、`*.egg-info`、临时日志、渲染中间文件和 `recordings/*_RUNNING.json`。
4. 排除 `JCIIOT/team_submission/.local/`；其中包含本机 API 配置，已经由 `.gitignore` 忽略。
5. 不提交明文 API Key；由评测环境变量或现场侧边栏提供。
6. 验证最终 checkpoint 路径存在，并与要运行的题目/统一模型策略一致。
7. 在 `JCIIOT/` 目录运行 `python team_submission/audits/verify_final_submission.py`，确认五模型哈希、五题证据与路由均通过。
8. 按仓库根目录 `REPRODUCTION_GUIDE.md` 使用官方入口启动。本地密钥文件不提交，由侧边栏或环境变量提供。
