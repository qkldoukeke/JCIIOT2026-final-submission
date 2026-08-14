# 训练数据清单与复现边界

所有 `training_configs/*.json` 都规定从 `JCIIOT/` 项目根目录启动训练，数据路径相对于该目录解析。下列 HDF5 当前存在于开发机，但受 `.gitignore` 排除，**没有随 GitHub 仓库或材料证据 ZIP 提交**。因此最终模型推理可复现；从头训练只有在另行取得对应 HDF5 并校验哈希后才可复现。

| Relative path from `JCIIOT/` | Bytes | SHA-256 |
|---|---:|---|
| `team_submission/training_data/factory_sorting_l1_123_train.hdf5` | 299831614 | `bb363cc80aa962e29a714f1a54ebe361edf427ad05ee78477aeff5fba8183274` |
| `team_submission/training_data/factory_sorting_l1_nomarker_121_train.hdf5` | 294706546 | `b19447cf190bbbb2ce8e268bd7ae50940d63214045333e16176878632775c432` |
| `team_submission/training_data/factory_sorting_l1_nomarker_timestep_121_train.hdf5` | 295064658 | `63bd03e7f781c19431a82ef70a6d0d0c6178fbcc6ae3c99cf67baaa2cdb14df0` |
| `team_submission/training_data/factory_sorting_l2_80_train.hdf5` | 162401082 | `d156764c34a62bc3a594d680f07972a2a5929b78d05508f2a19063d88bb84834` |
| `team_submission/training_data/factory_sorting_l3_200_train.hdf5` | 375965770 | `bc3e4c328754227ca1b7a26be10229b4f67b163b7cd8e62ea666145b0428463a` |
| `team_submission/training_data/factory_sorting_l4_upper_100_train.hdf5` | 243475132 | `e9e1f61d3c83f0cee56f4c57253033772c3ec7592e3d9f4e608145f22e8bca8a` |
| `team_submission/training_data/factory_sorting_l5_center_100_train.hdf5` | 195575326 | `379a4f484143d232d6bf8c911281bcee02c73150e76a75ffe5665116be5a1d8d` |
| `team_submission/training_data/factory_sorting_l5_center_clean_25_timestep_balanced_windows_train.hdf5` | 272118013 | `ea4a76f65ddc1bc57012754b1b958ba968711c6081d37dbacdc81a132f58f85b` |
| `team_submission/training_data/factory_sorting_l5_center_clean_25_timestep_key_windows_train.hdf5` | 603923981 | `53d9929d1849d1aa235972a52a52317f103bcc2faa91f51da2a8876a9cbf5fa8` |
| `team_submission/training_data/factory_sorting_l5_center_clean_25_timestep_prefix10_train.hdf5` | 215870652 | `50346312209777b2bb3c84424b5fcf044d408975dc7552a14d655e77065920da` |
| `team_submission/training_data/factory_sorting_l5_center_clean_25_timestep_train.hdf5` | 48972249 | `718c48f63c90edff89f0de6367151c0a8755483bdd77c4dec127190845620b6c` |
| `team_submission/training_data/factory_sorting_l5_center_clean_25_train.hdf5` | 48894169 | `ef2c159a27e6a2ab17e2a2bf5641befddf24f7446c3e15970fa1b119043461bc` |
| `team_submission/training_data/factory_sorting_l5_center_recovery_key_windows_train.hdf5` | 980153617 | `ded4fd1ba151507126d781e9e1fedaa2659288c45411ee5b2894a6b9a42ff682` |
| `team_submission/training_data/factory_sorting_l5_three_objects_300_train.hdf5` | 588918412 | `d4cb2e381e029939be002570bff408118f4b51594727ec0e07a74b72df502744` |
| `team_submission/training_data/l2_pipeline_check.hdf5` | 6108973 | `f79fc524a64c966e9db75888ade63723678c1bc47eeb5adf6dcfe14b3702ec98` |

## 启动约定

```powershell
cd <repository>\JCIIOT
python -m robomimic.scripts.train --config team_submission/training_configs/<config>.json
```

使用 `python team_submission/audits/validate_training_configs.py --require-data` 可验证全部 28 份配置、相对路径解析和本地数据是否齐备；不带 `--require-data` 时只验证配置结构和路径可移植性。
