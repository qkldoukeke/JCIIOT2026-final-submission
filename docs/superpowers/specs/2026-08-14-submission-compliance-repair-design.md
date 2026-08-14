# 最终提交确定性问题修复设计

## 目标

在不改变现有 L1–L5 满分运行行为的前提下，修复提交仓库中已经确认的合规、跨平台复现、文档一致性和打包问题。

## 明确不在本轮修改的内容

- 不修改现有程序化抓取、BC 恢复、导航或放置行为。
- 不修改主办方禁止修改的 `app.py`、`knowledge/task_config.json`、`src/robot_agent/core/`、`src/robot_agent/environments/`。
- `skills/` 直接访问 MuJoCo 的问题保留为“待主办方书面确认”的风险项，不宣称已解决。
- 不改写五题原始成功轨迹、评分和结果文件中的历史数据。

## 修复设计

### 1. 官方基准与受保护资源

审计基准必须固定记录主办方仓库完整 URL、40 位 commit SHA、由该 commit 生成的官方 ZIP SHA-256 和审计时间，不使用会继续移动的 `master` 名称代替。只恢复该固定提交中确实存在的文件。

官方 Git LFS 文件使用 `git checkout <official-commit> -- <path>` 与 `git lfs pull` 恢复，不手工编写指针。重新生成受保护边界审计 JSON 和 Markdown，并分别标记普通文件逐字节一致、官方 LFS 指针一致、官方 LFS 对象正确实体化、LFS 对象无法取得、真正缺失和允许范围内新增项。

### 2. 提交清单作为单一事实来源

新增 `JCIIOT/team_submission/submission_manifest.json`，统一保存团队名 `CI Lab`、参赛 ID `doukeke`、仓库地址、Leaderboard Issue 完整 URL `https://github.com/JCIIOT2026/JCIIOT2026/issues/13`、最终提交 commit、官方基准 commit、官方 ZIP 哈希、审计时间、L1–L5 得分和时间、模型路径/大小/SHA-256、证据相对路径/SHA-256、当前抓取路由和已知合规风险。验证脚本以该文件为唯一机器可读事实来源，并检查人类可读文档中的关键数据与之相符。

### 3. Windows 验证与 LFS 诊断

所有文本读取和写入显式指定 UTF-8。验证脚本在计算模型哈希前识别 Git LFS 指针，并输出 `git lfs install`、`git lfs pull`。输出固定分为 Python/JSON、模型文件、证据完整性、任务 checkpoint 路由、生成 SOP、受保护边界和文档一致性七组 PASS/FAIL。脚本分别在 `python -X utf8` 与 `python -X utf8=0` 下验证。

### 4. 文档一致性

根目录 README、技术报告、实验开发日志、复现指南、最终提交清单和排行榜草稿从 manifest 同步最终成绩、时间、团队名、参赛 ID、Issue 完整 URL、仓库地址和固定审计基准。实验开发日志中的旧结论保留为有明确日期和“历史阶段”标签的过程记录，文件开头给出最终状态，避免评委误读。

整个提交不得宣称“已经完全合规”。统一表述为：主办方禁止修改的源码已通过固定基准审计；skill 内程序化抓取对仿真公开辅助接口的使用方式，仍待主办方对接口边界进行书面确认。

### 5. 训练复现边界

28 份历史训练配置不再依赖特定电脑盘符。统一规定所有训练命令从 `JCIIOT/` 根目录启动，配置中的数据和输出目录按该目录解析。新增训练数据清单，记录最终模型所需数据文件、预期相对位置、是否随 Git 提交和缺失时的处理方式。修改后实际加载全部 28 份配置并验证解析后的路径。文档准确说明：最终推理可复现；从头训练仅在取得清单中的 HDF5 后可复现。

### 6. 证据可移植性

原始 evidence JSON 作为不可变历史证据保留。新增 `JCIIOT/team_submission/evidence/EVIDENCE_INDEX.json` 和 `EVIDENCE_INDEX.md`。每题记录 score、result、trajectory 的相对路径和各自 SHA-256、得分、时间、环境名、checkpoint 相对路径和 SHA-256、`grasp_router` 以及原始文件不可修改声明。修复前后五题 15 个原始证据文件哈希必须完全一致。

### 7. 跨平台提交 ZIP

重新生成材料证据 ZIP，不包含 `__MACOSX`、`.DS_Store`、AppleDouble 文件、模型或 Git LFS 指针。目录和文件名采用 ASCII，ZIP 条目使用 UTF-8。ZIP 包含提交说明、技术报告、新颖性声明、复现指南、证据索引，以及 L1–L5 各自的 score、result、trajectory 共 15 个证据 JSON。代码与真实模型由 Git clone + Git LFS 获取。提交说明明确该 ZIP 是材料证据包而非完整离线代码包。

### 8. 运行路径零变化证明

相对满分基线提交 `4b9d7ed71d57e307d7a0bb3b41f55201704a466e`，以下路径必须逐文件哈希不变：`src/robot_agent/skills/`、`knowledge/robot_params.json`、`src/robot_agent/workflows/`、`app.py`、`knowledge/task_config.json`、`src/robot_agent/core/`、`src/robot_agent/environments/`。最终 `git diff --name-only` 只允许出现文档、审计/验证工具、训练配置、manifest、证据索引、ZIP 构建工具，以及从固定官方提交恢复的资源。

## 验证

- `git diff` 中没有任何运行路径文件变化。
- 五题 15 个原始 evidence 文件 SHA-256 与满分基线完全一致，得分仍为 10、15、20、25、30。
- Python 和 JSON 语法检查通过；验证脚本在 `-X utf8` 与 `-X utf8=0` 下均通过。
- 28 份训练配置不存在 `D:\\`、`E:\\` 或 `/Users/` 绝对路径，并能从 `JCIIOT/` 根目录成功加载。
- 六个模型对象通过 `git lfs fsck`；全新 clone 执行 `git lfs pull` 后模型不是指针。
- 新 ZIP 不含 Mac 元数据、LFS 指针和本机绝对路径，15 个证据 JSON 全部可解析。
- 受保护文件与固定官方提交一致；若上游 LFS 对象确实不可取得，报告如实标记，不能写“缺失 0”。
- 所有人类可读文档的关键事实与 `submission_manifest.json` 一致。

## 风险控制与回退

修复前的满分版本由 Git 提交 `4b9d7ed71d57e307d7a0bb3b41f55201704a466e` 保留。任何文档、审计或打包修复不得改动运行路径。缺失的官方大文件若无法可靠获取，不以伪造指针替代真实内容，而是保留明确说明并停止宣称完全一致。
