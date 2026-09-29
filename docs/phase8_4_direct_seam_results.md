# 直接控制接口的真实GPU验收

2026-09-12。**三个构型的逐子步重放与原控制路径完全一致，base的日志开关对照也一致。** 这证明该接口在本次范围内保持给定推进器命令的下游执行语义；尚无新预测模型或控制收益。

| 对照 |32个控制边界state11最大差|64个物理子步state11最大差|
|---|---:|---:|
| base原控制 vs直接重放 |0|0|
| uuv4原控制 vs直接重放 |0|0|
| uuv6原控制 vs直接重放 |0|0|
| base直接hold日志on/off |0|off无子步日志，未测|

虚拟控制、PWM和thruster-only wrench在三个重放对照中也逐分量相等。预声明容差1e-6未调整。重放使用源身份绑定的实测预设命令序列，仅用于执行等价检查；它不作为未来输入可知或模型预测的证据。8.3已独立检验默认预设控制器的因果重建。

新`direct_pre_tam_v24`接收有界无量纲4D分配命令，在两个physics ticks保持命令、分别推进执行器；`direct_sequence_replay_v24`只用于逐子步诊断。两者均绕过S-surface/PID及附加depth控制修正，保留mask、原构型分配、clip、非线性速度转换和原艇体力学。原`legacy_action`默认保留。完整N维转速通过已知命令、tau和dt从零初值递推；测量只做误差对照，最大转速误差1.031e-4。

本轮8个进程、256control intervals、448条实测物理子步（日志off没有子步测量）。66文件归档在服务器和本地核对SHA256、精确case集合、源码、实际加载、运行时、原生退出及子步合同；本地重新执行保存的成对验收结果一致。原工作区240tests通过，独立bundle克隆同240tests通过。没有formal collection、model fit、model handoff或原仓库commit/push。

范围：IsaacSim5.0/IsaacLab2.2.1、单环境、固定构型、无DR、已知零执行器初态、32区间。本版直接入口明确拒绝未验证的多环境调用。新的正常hold波形与旧S-surface产生的不同子步序列不同；后续辨识必须采集自己的新数据，不能把执行重放相等理解成所有控制策略相等。

源码快照`71c4cdda16dac2b35c5d158f11f1c3eb084e10b2`。Bundle SHA256`07554130c74beb60b8c043ba176060a5fe0d16b921b5b9b8592506e1361d2807`；证据archive SHA256`56d09ecd97a0c9b58f9334cf96fac244f730708b4e06b307217f67d0998adee7`。

证据：[验收](evidence/phase8_4/server-direct-seam-20260912/acceptance.json)、[逐子步状态补充检查](evidence/phase8_4/server-direct-seam-20260912/substep-state-check.json)、[源码包](evidence/phase8_4/runtime-package-20260912-r6/package.json)。下一入口：[08.4-02](../.planning/phases/08.4-conditional-identification-experiment/08.4-02-PLAN.md)，先冻结一个fresh pilot的模型、样本角色和评价门。
