# 当前运行说明

本地使用项目 `.venv/Scripts/python.exe`；Linux/服务器使用对应环境的 `python`。先运行 `python -m pytest -q tests`。Isaac由服务器环境提供，不能用本地mock测试代替真实仿真验收。

| 工作 | 模块入口 |
|---|---|
| 冻结当前源码、协议和资产 | `python -m workflows.prepare_disturbance --output results/new-release` |
| 采集三档新轨迹 | `python -m workflows.collect_disturbance_data --help` |
| 原始数据验收 | `workflows.disturbance_data.load_episode` |
| v87训练数据离线拟合 | `python -m workflows.fit_disturbance --help` |
| v88冻结预测评估 | `python -m workflows.evaluate_disturbance --help` |
| 训练数据确定共同范围 | `python -m workflows.freeze_support --help` |
| 共同离线求解验证 | `python -m workflows.solve_disturbance --help` |

工作流输出要求新路径，拒绝覆盖已有证据。参数/角色/门限以 [v88协议](../experiments/phase9/v88/protocol.md) 和其JSON为准。训练只读取训练角色；v88评估不训练。原三模型预测与求解全部通过的闭环准入仍有效，目前未准入。

## 复算已有v88轨迹

以下PowerShell在仓库根运行，输出目录须为新建目录。

```powershell
$evidence = 'results/history/docs/evidence/phase9/matrix-v88-20260929'
New-Item -ItemType Directory -Path results/replay
.venv/Scripts/python.exe -m workflows.evaluate_disturbance --data "$evidence/server/data" --manifest "$evidence/release-r1/manifest.json" --source-archive "$evidence/release-r1/source.tar.gz" --model experiments/artifacts/model.json --role test --output results/replay/test.json
```

原始采集的历史manifest必须配原源码压缩包；新manifest必须匹配当前执行文件。两者的哈希身份分别记录，不能用重构后的代码伪装历史源码。验证和测试应分别复算，全部窗口纳入。

离线求解还需要原已批准的运行资产根目录（`--assets`）。它包含冻结支持域来源、物理拟合缓存和授权记录；当前 `runtime_assets` 从固定handoff哈希出发验证这些字节。历史相对路径属于工件身份，不能为了目录简洁改写。使用外部冻结资产目录或本地归档根，缺失或哈希不符即停止。

未来新Isaac运行须先建立当前源码包、验证资产与数据角色，记录原生退出、环境关闭和独立验收。不以本轮源码整理的测试结果声称新Isaac运行成功。
