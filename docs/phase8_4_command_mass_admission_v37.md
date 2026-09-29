# v37：实际质量读回的限定验收修复

2026-09-13。v36真实fit接口核查已停止，native1：base/long_body/heavy/asymmetric四个构型全部逐子步差0，第五个uuv6被严格质量相等检查拒绝。源合同42测试通过仍不足以覆盖这个真实读回细节。保持[原v36合同](phase8_4_causal_command_contract_v36.md)、失败输出及已完成四例不变。

| 构型 | authored float32质量 kg | 实际读回质量 kg |
|---|---:|---:|
| uuv6 | 29.700000762939453 | 29.69999885559082 |
| uuv6_angled | 31.68000030517578 | 31.680002212524414 |

两个实际数值都严格等于 `float32(1 / float32(1 / authored_float32_mass))`。NVIDIA公开PhysX代码setMass存inverseMass、getMass取倒数，与这个机制一致；公开main源码并不证明部署二进制完全同版本。[NpRigidBodyTemplate.h的setMass/getMass](https://raw.githubusercontent.com/NVIDIA-Omniverse/PhysX/main/physx/source/physx/src/NpRigidBodyTemplate.h)。原真实数据验收已允许质量绝对差1e-5，本次无需改旧数据验收或物理参数。

只修新接口的质量准入：接受名义float32值或上述严格倒数往返值，不接受任意“足够接近”的质量；其余context检查保持。传给模型及用于wrench/mass的仍是调用者提供的实际读回context，绝不替换成名义值或base。冻结前核对v37与v36的整个forecast函数AST一致，仅validate_context的质量规则改变。

先测试两个实值通过且确实用于每个子步，邻近但不符合规则的数值与错误配置仍拒绝；然后按同八构型/起点128/4区间、两组±.01depth分支、原1e-12/精确相同门核查。原v36已完成四例与修复后对应四例还须逐数组一致。

v37与v36共享原300秒source诊断额度。承接v36测试保守60秒和失败核查10.578秒；本次原因调查保守30秒、新RED/相关测试45秒，余下154.422秒供八例核查与独立审核，不能借版本变化重置预算。零新拟合、零服务器、零validation/test访问及model handoff。
