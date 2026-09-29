# v58 服务器接入与环境核验

**后续已执行：** 下文为安装前的历史环境检查。用户随后批准隔离环境，准备已通过并执行一次真实预检；当前结论见[v58运行结果](phase9_runtime_preflight_v58_results.md)。

2026-09-20。用户已授权在 agentic-AUV 执行 v58，并最新明确端口为 **31348**。已成功以 SSH 密钥登录 `root@183.147.142.40:31348`，无需再次提供密码。原 30852 端口在 SSH 握手前关闭连接；该失败属于旧端点，不能据此判断当前服务器离线。

本地冻结 release 已通过 `workflows.package_runtime_v58 --verify-only` 复核，SHA 仍为 `8a08093a6f07d1630691d4aa5d9871137e1dd9bab116cdbba49404628bf4a7a3`。已创建绑定 release/协议的授权记录；端口更正另存 `PHASE9_APPROVAL_PORT31348.json`，保留早先带 30852 元数据的记录作为历史。

服务器为 RTX 4090，现有解释器为 `/opt/conda/envs/isaaclab/bin/python`。IsaacLab HEAD 和补丁哈希符合冻结合同，但 NumPy、Numba、llvmlite 分别为 **1.26.0、0.59.1、0.42.0**，不满足 v58 固定的 **1.26.4、0.61.2、0.44.0**。常规位置未找到可复用匹配环境。原始[环境记录](evidence/phase9/server-preflight-v58-20260920/environment-31348.json)及[命令退出记录](evidence/phase9/server-preflight-v58-20260920/environment-check-exit.json)已保存。

当前状态为 **环境预检查受阻，仿真尚未开始**：没有上传执行包、安装依赖、创建远端实验目录、启动训练或物理采样；不是控制模型 NO_GO，也不能宣称完整模拟器资格已通过。远端只读查询已结束，本任务未启动待清理的远端实验进程。

原短预检提案明确“不自动安装或升级依赖”，所以停止在此边界。建议使用[隔离环境修订](phase9_runtime_environment_v58_amendment.md)：继承现有 Isaac 环境，新目录安装三个固定版本，追加最多 15 分钟准备及 512 MiB 环境空间；原研究包与全部仿真门保持。修订批准后继续，既有 v58 执行授权不重复请求。
