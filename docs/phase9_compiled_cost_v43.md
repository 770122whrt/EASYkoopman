# Phase 9：固定预测数值核编译 v43

在同一v42批量预测路径内，替换为编译执行的相同模型矩阵和物理更新。八构型K8/H20整批p50为20.92–69.34ms，相对本轮未编译路径提速1.671–3.077倍，中位1.949倍；最大字段差2.78e-16。本地编译可行性GO，60Hz与完整求解/闭环资格仍未通过。

## 实现、依赖与验证

新增[编译预测器](../koopman/compiled_projected_v43.py)，保留41/53维观测量、原完整六速度矩阵读出及原位姿更新。仅把逐行数值循环编译，不改写为另一种D/Q模型，不重新拟合。fastmath关闭，状态/context检查和非有限速度拒绝保留，输入统一为自有布局以避免控制过程中触发新JIT签名。

Numba0.61.2/llvmlite0.44.0安装在独立`.pytest-tmp/phase9-numba-v43`目录，占112.59MiB；原Python3.12.4/NumPy1.26.4与冻结环境未升级。版本依据[官方兼容表](https://numba.readthedocs.io/en/0.61.2/user/installing.html)，关闭fastmath依据[官方浮点性能说明](https://numba.readthedocs.io/en/stable/user/performance-tips.html)。[固定依赖](../scripts/requirements_phase9_compile_v43.txt)与[安装记录](evidence/phase9/compiled-v43-checks-20260920/dependency-install-02.json)已保存。第一次下载因网络沙箱失败，10.110秒/native1原样保留；授权网络重试70.047秒/native0成功，不计成模型失败。

38项针对性先RED后GREEN；覆盖linear/nonlinear、两代表构型、0/1/8/64行单步、256子步正反输入/并行递推、readonly/strided输入、源模型修改隔离、context与非法输入拒绝、v42整批接口。包含新路径的183项相关回归通过（不是全仓测试）。[测试记录](evidence/phase9/compiled-v43-checks-20260920/related.txt)。

## 同轮整批成本对照

[固定协议](evidence/phase9/compiled-v43-pilot-20260920/protocol.json)：仅既有八条fit PRBS、pooled冻结模型、origin128、K8/H20；一次预热、三次交错计时，原rtol=atol=1e-12。比较器和候选均使用相同v42分配/执行器/分支代码；另逐候选与原v39+v30标量模型对照。[结果](evidence/phase9/compiled-v43-pilot-20260920/result.json)39.125秒/native0。

| 构型 | v42整批p50(ms) | v43整批p50(ms) | 加速比 |
|---|---:|---:|---:|
| base | 141.15 | 69.34 | 2.036 |
| long_body | 116.49 | 62.52 | 1.863 |
| heavy_moderate | 108.19 | 50.24 | 2.153 |
| asymmetric | 114.41 | 53.08 | 2.155 |
| uuv6 | 64.37 | 20.92 | 3.077 |
| uuv6_angled | 63.56 | 37.53 | 1.693 |
| uuv4 | 66.46 | 39.77 | 1.671 |
| uuv4_angled | 115.44 | 65.36 | 1.766 |

首次prepare及编译12.415秒，已包含在39.125秒总运行中但不混入热执行时延；后续不同构型prepare约0.5–1.3ms，八构型始终一个JIT签名。模型worker必须在READY之前完成编译，不能把该冷启动移到控制周期。最坏已测热执行约75.41ms，三次重复不能提供可信尾延迟保证。跨轮绝对耗时有明显变化，不把各轮加速比相乘，不将构型次序造成的差异认作动力学复杂度。

## 下一步与边界

已经完成局部执行提速，下一步应构建有界候选搜索与支持域/目标合同，并测整个求解流程，包括基准生成、候选、原始PWM饱和检查、评分、选择和实际fallback成本。[09-03计划](../.planning/phases/09-configuration-aware-koopman-mpc/09-03-PLAN.md)给出具体顺序，完成后补齐09-02调度决定。不能仅看预测时间就承诺10Hz，也不能把可能多次迭代的FeedbackPolicy逆解当作廉价60Hz回退。

v43实际fit只测H20，长递推覆盖为合成模型回归；没有闭环实验、正式test访问或服务器运行。[复核](evidence/phase9/compiled-v43-pilot-20260920/review.json)确认当前/归档源和v38三项冻结绑定保持。

新编译阶段已测232.768/1200秒（失败安装、测试、冷编译均保留），此前阶段保守1650.127秒不重置。依赖和产物在512MiB范围内。两阶段都是本地工程检查，未消费v38关闭预算。Koopman独特增益、实际控制收益和Agentic收益尚无新增证明。
