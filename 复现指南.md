# 最终版复现说明

**代码仓库：** [https://github.com/qkldoukeke/JCIIOT2026-final-submission](https://github.com/qkldoukeke/JCIIOT2026-final-submission)

克隆后进入仓库的 `JCIIOT/` 目录执行以下安装和测试步骤。

## 1. 环境

- Python 3.11 或 3.12
- 项目依赖以 `requirements.txt`、根目录 `pyproject.toml` 和 `robosuite/pyproject.toml` 为准
- macOS 本地适配未写入提交源码；Linux/Windows 按主办方原始入口运行

## 2. 安装

在 `JCIIOT` 目录执行：

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
python -m pip install -e ./robosuite
python -m pip install -e .
```

确认以下资源存在：

```text
robosuite/robosuite/model_epoch_150.pth
robosuite/robosuite/environments/factory_sorting/generated_maps/
team_submission/models/final/l1/model_epoch_20.pth
team_submission/models/final/l2/model_epoch_50.pth
team_submission/models/final/l3/model_epoch_100.pth
team_submission/models/final/l4/model_epoch_50.pth
team_submission/models/final/l5/model_epoch_100.pth
```

## 3. 启动与测试

```bash
python -m streamlit run app.py
```

浏览器进入 Streamlit 提示的地址，配置可用的 LLM/VLM API，保持 **Inject Knowledge Base** 开启，然后依次点击 L1–L5 行的 **Execute**。无需手工更换模型或 SOP；当前环境会自动路由到对应生成 SOP 和 BC 恢复模型。

## 4. 离线审计

```bash
python team_submission/audits/verify_generated_sops.py
python team_submission/audits/verify_final_submission.py
```

官方边界审计需要指定主办方原始 ZIP：

```bash
python team_submission/audits/verify_official_boundary.py \
  --reference-zip /path/to/official-source.zip
```

## 5. API 密钥

仓库不包含 API Key。请使用平台侧边栏或环境变量配置，不要把本机 `team_submission/.local/api_credentials.json` 上传到 GitHub。

## 6. 上游可选资源说明

主办方仓库中的 `competition description/USD/*/*.zip` 和 robosuite 示例
`dataset/table_setup_from_dishwasher_sample.hdf5` 仅有无法从上游 LFS 获取的指针，
且不被本比赛 App、五个 FactorySorting 场景或最终模型使用，因此未纳入提交仓库。
