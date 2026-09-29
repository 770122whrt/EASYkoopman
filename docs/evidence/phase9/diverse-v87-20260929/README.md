# v87执行证据

当前实验范围与冻结规则见[运行说明](../../../phase9_diverse_v87_runbook.md)，最终结论统一写入[结果报告](../../../phase9_diverse_v87_report.md)。这不是已合格模型发布。

从`no-selection/10ed7c7`已有v86工作继续；源码和测试已提交`ac36b1c`，文档与实验结果另行提交。未删除任何旧未跟踪原始材料。

## 本地和服务器验证

- 本地161项定向回归通过；补充协议测试8项通过，有重叠不相加。详见`local/pytest.xml`和`local/protocol-tests.xml`。
- 旧控制接口回归61项通过，包括历史轨迹重放和篡改拒绝；见`local/legacy-control-tests.xml`。
- 服务器160项通过、1项未选择：打包测试需要Git检出，在源码运行包中不执行，本地已通过。不是整个仓库测试全绿声明。
- 源码冻结744文件：`release-r1/manifest.json` SHA256 `a79174de72c5b3c3e5dce1f88c634b78c4bba76108486a3783c848dc708f7285`。
- 源码包SHA256 `9ee09de46994e8ff48545b096a04521b602fea17529d2cb409bee4516a4a59f2`。Git提交后复核工作区对应文件哈希仍一致。
- 主服务器运行目录`/root/shared-nvme/agentic-auv/workspaces/diverse-v87-20260929`；使用既有Isaac/Python3.11/CasADi3.7.2，所有本任务求解与数值库线程设为1。

## 数据状态

24条轨迹全部完成，服务器及本地原始数据独立验收24/24通过。16条训练、16640行只拟合一次；模型SHA256 `5857a0e8d09cd04e33112b457b6a60f8b4147f3819815634edb6149ac95e137e`。测试窗口物理12/16、Koopman4/16、结合16/16通过。四个求解起点三臂各1/4通过，另外三个均因旧支持域拒绝。按用户确认保留原门限，闭环0次。

307个证据文件完整回传并核对逐文件哈希。归档`server-evidence.tar.gz` SHA256 `fcefaeb2ad71625cf2251cc7300b2b7aab8c20dbcd6a46ffbae2d44786be38e1`。本地无拟合复算与服务器一致：验证指标最大差异0，测试4.02e-18以内。见`local/archive-validation.json`与`local/pullback-validation.json`。服务器本任务进程均已退出，GPU恢复1MiB；服务器保持开启。

每次采集保留原始trace、清理记录、外部退出回执与独立acceptance。预测与求解报告保留所有失败；测试期间不训练。源包、完整原始数据及重复归档默认保留本地/服务器原路径，不全部加入Git；选定机器可读结果与逐文件哈希清单用于版本追踪。Git不能自动恢复未提交的大型原始文件，复算应先核对对应运行包和证据归档。
