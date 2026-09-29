# v59 接口修复复测

用户于 2026-09-20 明确要求“修复后再上服务器进行测试效果”，授权本修复版继续测试。当前端点为 `root@183.147.142.40:31348`，复用已经验收的 `/root/EASYkoopman-phase9-runtime-env-v58/bin/python`；不重新安装依赖。

v59 只修复真实 telemetry 中 tau/drag 单环境向量的形状合同，显式设置 `fast_shutdown=False`，并记录 worker、环境、应用三个关闭边界。旧 v57/v58 源码、发布包、原始失败及模型不变。新的 case id、release 和 approval 必须分别绑定，旧 v58 批准文件不能直接通过 v59 准入。

复测范围沿用 8 构型各 32 区间，base 先行、每例验收后再继续，任一失败停止；不自动重试、不训练、不改初态、参考、权重、预测时域、模型、100ms 求解或 16.67ms 完整周期门。整次 source/environment check 与运行合计 30 分钟，每构型采集、验收及回读共享 180 秒。只有所有声明的资源关闭返回成功、原生退出 0、进程组清理和轨迹验收都通过，才能判定单例通过；缺失最终报告不得用关闭前快照补造通过。

两端研究包继续各限 256MiB，共享隔离环境限 512MiB，两端总量限 1GiB；保留 v58 旧包和本次证据的占用也计入累计清点。使用独立目录 `/root/EASYkoopman-phase9-runtime-v59-20260920`，只传新清单中的文件及本次批准记录，不能覆盖旧目录。运行目录内仍保留 192MiB 停止线；外层部署/监督额外检查两份保留研究包的累计量，给收尾预留空间。

先在独立发布目录跑清单的全部 `local_tests`，Windows 的 Linux 进程组测试必须标记 skipped；实际服务器在启动 Isaac 前执行原超时/孤儿进程清理探针。新回归包含冻结的 v58 真实 reset 快照，但仅用于接口回归，不作为新物理证据。

通过来源、环境和批准绑定后，在新发布目录执行：

```bash
/root/EASYkoopman-phase9-runtime-env-v58/bin/python -B -m workflows.run_runtime_v59 --release-root "$PWD" --check-only
bash scripts/phase9_runtime_preflight_v59.sh /root/EASYkoopman-phase9-runtime-env-v58/bin/python "$PWD/PHASE9_APPROVAL.json"
```

远端启动脚本以明确 UTF-8/LF 字节传输；不要用 PowerShell 文本管道引入 CR。保留每例 trace-before-cleanup、六个 cleanup 边界记录、trace、原生退出、验收，以及阶段终态。任一失败不再启动下一构型。拉回前后核对所有新增文件 SHA、冻结源身份和两端字节，检查实验进程已结束后再告知用户可关服务器。

这仍是约 0.533 秒/构型的接口短预检，不是长期跟踪、持续实时性、Koopman 独有收益或跨构型控制泛化的证明。通过后才能按实际表现设计匹配闭环比较。
