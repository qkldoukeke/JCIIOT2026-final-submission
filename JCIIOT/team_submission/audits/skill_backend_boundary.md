# Skill / EnvBackend 边界审计

- 结论：**通过**
- 扫描范围：`src/robot_agent/skills/*.py`
- Python 文件：`15`
- 违规项：`0`
- 规则：skill 不得直接导入 MuJoCo/robosuite，也不得访问具体环境、sim 或 backend 私有物理状态。
- 物理能力边界：`robot_agent.workflows.semantic_backend.CompetitionEnvBackend`。
