# v58 服务器依赖准备修订（待批准）

用户已授权执行 v58，并于本轮明确端口为 `root@183.147.142.40:31348`。连接及只读环境核验成功；当前阻塞是依赖版本不符合冻结运行门，不是模型或控制实验失败。原提案明确不安装/升级依赖，因此此次新增环境准备须单独确认，原 v58 执行授权保留。

## 现场证据与修复选择

| 包 | 已有 isaaclab 环境 | v58 要求 |
|---|---|---|
| NumPy | 1.26.0 | 1.26.4 |
| Numba | 0.59.1 | 0.61.2 |
| llvmlite | 0.42.0 | 0.44.0 |

Python 为 3.11.13，GPU 为 RTX 4090；IsaacLab commit 和工作区补丁哈希与合同一致。发行包元数据中的 `isaaclab=0.45.9` 不作为运行时 Lab 版本结论，真正的 runtime provenance 仍由 collector 核验。已检查常规 conda/venv 位置以及 `/root`、`/root/gpufree-data`、`/tmp` 顶层的编译依赖目录名称，未发现可直接复用的匹配环境；没有扫描整盘。原始读回见[环境记录](evidence/phase9/server-preflight-v58-20260920/environment-31348.json)。

建议新建 `/root/EASYkoopman-phase9-runtime-env-v58`，以已有 Isaac Python 创建 `--system-site-packages --without-pip` 的独立 venv。仅在新 venv 的 site-packages 安装上述三个固定版本，继承原环境的 Torch/Isaac；原环境及旧实验目录保持原样。进程使用新 venv 的 Python，使其子进程自然继承同一解释器，不依赖会被监督器覆盖的 PYTHONPATH，也不把 Windows 编译包复制到 Linux。

## 具体变更与资源范围

- 新增一次环境准备与针对性验收，墙钟上限 15 分钟；只下载 Linux/Python 3.11 二进制 wheel，不从源码编译、不递归更新依赖。任一失败停止，无自动重试或改版本。
- 新环境及其临时下载/日志合计最多 512 MiB。创建前检查目标不存在；下载临时目录放在该新环境内，不向用户已有 pip 缓存写入。安装过程中监测目录大小，达到 480 MiB 停止并保留余量；停止后清点实际占用。轮询不等于操作系统硬配额。
- 将本次两端新增总量上限由 512 MiB 增至 1 GiB：服务器原研究包仍为 256 MiB，加新环境最多 512 MiB；本地研究包仍为 256 MiB。原 v58 运行目录的 192 MiB 停止线和 256 MiB 上限不变，新环境不能用作转存结果的目录。
- 原 v58 仿真阶段仍为最多 30 分钟、每构型采集/验收/回读合计 180 秒、8 构型各 32 区间、零拟合、base 先行、失败即停。此次修订不批准额外 episode 或训练，不改变 100 ms 求解和 16.67 ms 完整周期门。

## 安装和验收入口

批准后，在时间/空间监督下执行以下固定操作。命令中的新目录必须排他创建；目标已存在则先检查其来源，不覆盖或删除。

```bash
/opt/conda/envs/isaaclab/bin/python -B -m venv --system-site-packages --without-pip /root/EASYkoopman-phase9-runtime-env-v58
# TMPDIR 指向上述新目录内的专用临时目录；不使用共享 pip 缓存。
/opt/conda/envs/isaaclab/bin/python -B -m pip install --no-deps --only-binary=:all: --no-cache-dir \
  --target /root/EASYkoopman-phase9-runtime-env-v58/lib/python3.11/site-packages \
  numpy==1.26.4 numba==0.61.2 llvmlite==0.44.0
```

先用新解释器检查三个包的实际导入路径/版本、Numba 小型编译、Torch 导入及 CUDA 可用性；核对已有三个包目录和 IsaacLab 补丁未变化。确认新 venv 的子进程仍使用相同包后，使用未改动的 release 执行 `--check-only` 与真实 Linux 清理探针。通过后按原用户授权继续 v58，无需重复请求同一短预检授权；失败则保存环境诊断并停下。安装/验证时间、文件清单和环境身份单独记录，不能当作 MPC 通过证据。

修订仅允许准备这一隔离环境并增加对应的资源额度。v58 发布 SHA `8a08093a6f07d1630691d4aa5d9871137e1dd9bab116cdbba49404628bf4a7a3`、模型、控制算法和原验收门保持不变。原提案/运行说明中的 30852 是历史端点，已被用户最新确认的 31348 取代；不为修改端口而重打包冻结源码。
