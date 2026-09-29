# Phase 7: Cross-Configuration Koopman Data and Control Contract - Pattern Map

**Mapped:** 2026-08-11  
**Scope:** schema v2、Koopman Bridge、v2 dataset、显式 v1 compatibility、三拓扑真实服务器证据链  
**Upstream read:** `07-SPEC.md`、`07-CONTEXT.md`、Phase 6 `06-VERIFICATION.md` / `06-SERVER-EVIDENCE.md` / `06-04-SUMMARY.md` 与 qualification runbook  
**Constraint:** 本文只映射现有实现模式；不扩展到 Phase 8 模型识别或 Phase 9 MPC 迁移。

## 结论先行

Phase 7 没有一个可以整文件复制的现成模块。最接近的实现分成四组：

1. `koopman_data.py` / `koopman/dataset.py` 提供 v1 的 JSONL、数组和 fixture 组织方式，但它们的 `U=PWM_8` 是必须冻结的历史语义，不能原地修改。
2. `easyuuv_nc/embodiments.py`、`easyuuv_nc/thrust_allocation.py` 和 `easyuuv_nc/env/easyuuv_env.py` 是构型、通道、TAM 与真实执行器 telemetry 的唯一运行时事实源；Phase 7 应从这里派生，不再维护第二份构型表。
3. Phase 6 qualification 的 strict JSON、稳定 reason code、受限输出路径、原子写入、CLI exit code 和 mutation tests 可以直接复用结构，但 Phase 7 必须补上“额外字段拒绝、episode 连续性、oracle/estimated 隔离、语义交换拒绝”。
4. Phase 6 bundle/bootstrap/server/pullback 是服务器证据链的最近模式；Phase 7 复用 fail-closed 顺序和 provenance 绑定，但只运行 `base`、`uuv6`、`uuv4` 三个拓扑代表，不能重复八构型资格测试，也不能预生成成功证据。

## File Classification

以下名称是最小、无歧义的推荐落点；若 planner 合并小文件，仍必须保留相同职责边界和公开入口。

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `koopman_data_v2.py` | utility / schema model | transform + JSONL file-I/O | `koopman_data.py`; `workflows/easyuuv_v2_qualification_artifact.py` | role-match，语义必须重写 |
| `koopman/dataset_v2.py` | immutable model-facing dataset | batch transform | `koopman/dataset.py` | exact role，control width 不同 |
| `workflows/koopman_bridge_v2.py` | service / runtime adapter | event-driven step → transition | `workflows/koopman_logging.py`; `workflows/qualify_easyuuv_v2.py` | role-match |
| `easyuuv_nc/env/easyuuv_env.py` | runtime telemetry provider | event-driven physics tick | 同文件 `_pid_control` / `_compute_dynamics` | exact insertion seam |
| `workflows/validate_koopman_v2.py` | validator CLI | file-I/O request-response | `workflows/validate_easyuuv_v2_qualification.py` | exact role |
| `workflows/qualify_koopman_v2.py` | real Isaac runner | streaming/event-driven → file-I/O | `workflows/qualify_easyuuv_v2.py` | exact role，transition 内容不同 |
| `workflows/merge_koopman_v2_evidence.py` | evidence manifest merger | batch file-I/O | `workflows/merge_easyuuv_v2_qualification.py` | exact role，expected set=3 |
| `scripts/phase7_prepare_bundle.ps1` | transfer config/script | batch file-I/O | `scripts/phase6_prepare_bundle.ps1` | exact role |
| `scripts/phase7_server_bootstrap.sh` | server bootstrap | batch/process | `scripts/phase6_server_bootstrap.sh` | exact role |
| `scripts/phase7_server_smoke.sh` | server orchestrator | batch/process + streaming logs | `scripts/phase6_server_qualification.sh` | exact role，matrix 不同 |
| `scripts/phase7_pullback.ps1` | evidence promotion | batch file-I/O | `scripts/phase6_pullback.ps1` | exact role |
| `tests/test_koopman_data_v2.py` | contract test | transform/file-I/O | `tests/test_koopman_data.py`; `tests/test_easyuuv_v2_qualification.py` | role-match |
| `tests/test_koopman_dataset_v2.py` | dataset fixture test | batch transform | `tests/test_koopman_dataset.py` | exact role |
| `tests/test_koopman_bridge_v2.py` | runtime seam test | event-driven | `tests/test_easyuuv_v2_qualification_runner.py` | role-match |
| `tests/test_phase7_server_evidence.py` | evidence-chain test | process/file-I/O | `tests/test_easyuuv_v2_qualification_runner.py` | exact role |
| `docs/phase7_koopman_v2_runbook.md` | runbook | operational sequence | `docs/phase6_easyuuv_v2_qualification_runbook.md` | exact role |

## Pattern Assignments

### 1. `koopman_data_v2.py`：小型、Isaac-free、严格版本化 schema 核心

**Closest analogs:** `koopman_data.py:9-23,44-114,135-186` 与 `workflows/easyuuv_v2_qualification_artifact.py:13-45,86-130,133-162,223-260`。

v1 的可复用模式是“常量维度 + builder 归一化 + 单条验证 + 序列验证 + JSONL logger/loader”：

```python
# koopman_data.py:44-66
def build_koopman_sample(...):
    sample = {...}
    validate_koopman_sample(sample)
    return sample

# koopman_data.py:101-114
def validate_koopman_sequence(samples):
    previous_t = None
    for index, sample in enumerate(samples):
        validate_koopman_sample(sample)
        if previous_t is not None and sample["t"] <= previous_t:
            raise ValueError(...)
```

Phase 6 提供更严格的 bounded UTF-8 JSON 和稳定 reason code：

```python
# workflows/easyuuv_v2_qualification_artifact.py:86-116
def _fail(reason: str, detail: str | None = None) -> None:
    message = reason if not detail else f"{reason}:{detail}"
    raise ValueError(message)

payload = json.loads(text, parse_constant=_reject_json_constant)
if not isinstance(payload, dict):
    _fail("root_not_object")
```

**Copy/reuse:**

- 保持纯 stdlib schema/validator；导入该模块不得触发 Isaac、Gym、Torch。
- 固定一个精确 `SCHEMA_VERSION` 常量；`schema_version` 只能 exact equality。
- builder 在返回前调用 validator；loader 对每条 JSONL 先拒绝 `NaN/Infinity`，再做字段/shape/finite/range 验证。
- 将 per-transition 和 per-episode validation 分开：前者验证单条语义，后者验证 episode invariant、`step_index`/`simulation_time` 单调、相邻 `next_state_11 == state_11`（容差必须明示）及不缺步/不跨 episode 漂移。
- logger 每写一行后 flush；最终 server manifest 使用原子 writer 和哈希绑定。

**Do not copy:**

- 不得沿用字段名 `state/reference/action_4d/pwm_8d/next_state`；v2 使用 SPEC 锁定的完整字段名。
- 不得复制 `reconstruct_training_tuples()` 的 `sample["pwm_8d"]`（`koopman_data.py:172-184`）。
- Phase 6 `_require_fields()` 只检查 missing；Phase 7 要求 missing **和 extra** 都 fail closed，因此 transition/context/provenance 对象均应比较精确 field set，并返回不同 reason code。
- 不得让 validator 修改输入 dict 来“规范化成功”；严格 validator 应返回新 normalized object 或只读检查，避免验证产生证据漂移。

### 2. `koopman/dataset_v2.py`：命名清晰的 `U=virtual_control_4` 只读视图

**Analog:** `koopman/dataset.py:12-60,82-143`。

```python
# koopman/dataset.py:12-22,38-47
@dataclass(frozen=True)
class KoopmanDataset:
    X: np.ndarray
    U: np.ndarray
    R: np.ndarray
    Y: np.ndarray
    ...

for name, width in expected.items():
    if array.ndim != 2 or array.shape[1] != width:
        raise ValueError(f"{name} must have shape (n, {width})")
```

**Copy/reuse:** frozen dataclass、`np.asarray(..., dtype=float)`、相同行数校验、非空数据集、source paths 与 `dt` metadata。

**Required divergence:**

- 新类名必须显式带 v2（例如 `KoopmanDatasetV2`）；`U.shape == (n, 4)` 且只从 `virtual_control_4` 构建。
- 建议命名字段而不是匿名 positional tuple，并将 PWM/mask 放在独立 `diagnostics` view；默认构造函数没有 `use_pwm_as_u` 开关。
- `platform_context`、两个 environment context 和 provenance 必须随样本可审计；不可为了得到 NumPy 数组而丢弃配置/episode identity。
- `koopman/dataset.py`、`KoopmanDataset` 和其 `U.shape==(n,8)` 测试保持不变；Phase 7 不做 model/MPC consumer migration。

### 3. `workflows/koopman_bridge_v2.py`：原子 step 边界和真实 telemetry

**Analogs:** `workflows/koopman_logging.py:24-68` 与 `workflows/qualify_easyuuv_v2.py:496-575`。

v1 logging seam 已展示 state/reference/env telemetry 的拆分，但它依赖旧 `_last_pwm_8d`：

```python
# workflows/koopman_logging.py:52-68
pwm_8d = getattr(env, "_last_pwm_8d", None)
if pwm_8d is None:
    raise AttributeError(...)
sample = build_koopman_sample(...)
logger.write(sample)
```

Phase 6 runner 展示“真实 step 后读取、缺失即失败”：

```python
# workflows/qualify_easyuuv_v2.py:534-554
action = torch.tensor(action_values, ...).repeat(args.num_envs, 1)
env.step(action)
summary = summarize_actual_telemetry(
    pid_value=getattr(env.unwrapped, "_last_pid_value", None),
    motor_values=getattr(env.unwrapped, "_last_motor_values_clipped", None),
    expected_motor_length=topology["thruster_count"],
)
```

**Phase 7 atomic order:**

1. 在调用 `env.step()` 前捕获 `state_11`、`reference_5`、调用方传入且验证后的 `raw_action_4`、episode invariant。
2. 执行一次 `env.step(raw_action)`。
3. 从同一 env index 读取 post-mask/pre-TAM `_last_pid_value`、actual clipped N motor、thruster mask、actual thruster-only wrench、platform/oracle context。
4. 读取 post-step `next_state_11`，组装一条 transition，严格验证成功后才落盘。
5. 任一 telemetry 缺失、batch/shape 不一致或 non-finite 时写明确失败证据并返回非零状态；不得用 raw action、desired wrench、catalog default 或零向量补位。

**Important non-copy:** Phase 6 `deterministic_excitation()` 会预先把 `uuv4` yaw 置零（`workflows/qualify_easyuuv_v2.py:77-88`），它无法证明 D-05。Phase 7 本地/服务器语义测试必须显式输入非零 raw yaw，并证明记录的 `virtual_control_4[2] == 0`。

### 4. `easyuuv_nc/env/easyuuv_env.py`：只增加只读 telemetry，不重写动力学

**Exact seams:**

- `_pid_control` 在 `easyuuv_nc/env/easyuuv_env.py:2149-2176` 先形成 4D `PID_value`，再走 TAM/legacy mixing，并缓存 `_last_pid_value`、raw/clipped motor。
- `_compute_dynamics` 在 `easyuuv_nc/env/easyuuv_env.py:2263-2318` 依次应用 PWM 映射、thruster first-order dynamics、conversion、efficiency/fault/ventilation。
- 真正 thruster-only force/torque 在 `easyuuv_nc/env/easyuuv_env.py:2320-2330` 求和；hydrodynamic/buoyancy/boundary 从 `2332` 之后才相加，最终 total wrench 是 `2360-2385`。

```python
# easyuuv_nc/env/easyuuv_env.py:2167-2175
motor_raw = motorValue.clone()
motorValue = torch.clip(motorValue, -1, 1).to(self.device)
self._last_pid_value = PID_value.detach().clone()
self._last_motor_values_raw = motor_raw.detach().clone()
self._last_motor_values_clipped = motorValue.detach().clone()

# easyuuv_nc/env/easyuuv_env.py:2326-2330
thruster_torques = torch.cross(self.thruster_com_offsets, thruster_forces, dim=-1)
thruster_forces = torch.sum(thruster_forces, dim=-2)
thruster_torques = torch.sum(thruster_torques, dim=-2)
```

**Copy/reuse:** 现有 `detach().clone()` telemetry 风格；在 thruster sum 后、hydrodynamics 前缓存 `_last_thruster_force_b` / `_last_thruster_torque_b` 或等价 6D buffer；reset 时显式归零，getter 返回 clone。

**Required correction:** 当前 WLS 通过 `_alloc_weight` 忽略不可控 yaw，但 `_last_pid_value` 本身未见显式 control-mask 乘法。Phase 7 必须让 `uuv4*` 的 control mask 在 TAM 前生效，并让 telemetry 缓存的是 mask 后值；不能只在 runner 中把 yaw excitation 清零。

**Do not copy/reconstruct:**

- 不得用 `_alloc_B @ clipped_pwm` 重建 `applied_wrench_6`，因为这会漏掉 PWM 非线性、thruster lag、efficiency、fault 和 ventilation。
- 不得把 `forces/torques` 最终和（`2360-2385`）记录为 applied actuator wrench；它含 buoyancy、drag、boundary 与 torque pulse。
- `platform_context` 应使用 active identity 加 runtime buffers（mass、inertia、COM/COB、volume、per-env drag、thruster dynamics tau），不是只抄静态 catalog；`environment_context_oracle` 的流速使用 `get_current_fluid_velocity()`，并携带 body/world frame 与单位。

### 5. 构型 catalog、TAM、mask：单一事实源

**Analogs:** `easyuuv_nc/embodiments.py:8-36,40-153,157-188`；`easyuuv_nc/thrust_allocation.py:13-15,60-110,126-161`。

```python
# easyuuv_nc/embodiments.py:157-188
config = EMBODIMENT_CONFIGS[name]
...
return {
    "configuration": str(name),
    "thruster_count": int(thruster_count),
    "allocation_mode": allocation_mode,
    "control_channels": tuple(CONTROL_CHANNELS),
    "control_mask": tuple(control_mask),
    "declared_control_rank": DECLARED_CONTROL_RANKS[name],
}

# easyuuv_nc/thrust_allocation.py:104-110
def control_channels_to_wrench(cmd):
    wrench = torch.zeros(cmd.shape[:-1] + (6,), ...)
    for channel_index, name in enumerate(CONTROL_CHANNEL_NAMES):
        wrench[..., _CHANNEL_TO_WRENCH_ROW[name]] = cmd[..., channel_index]
    return wrench
```

**Copy/reuse:** exact `SUPPORTED_EMBODIMENTS` 顺序、`qualification_record()` 的 fresh/immutable-by-reference 返回模式、`CONTROL_CHANNEL_NAMES` 固定顺序、`declared_control_rank()` 与 `ThrusterLayout/build_wrench_matrix` 的几何验证。

**Do not copy:** schema 或 tests 中不要再硬编码一套八构型参数。测试可固定期望 exact set 用于防漂移，但实现必须 lazy import catalog；`heavy_duty` 不能进入 public positive fixtures。`qualification_record()` 只有 topology 字段，不能单独充当完整 `platform_context`。

### 6. strict validator、CLI、deterministic/atomic writer

**Analogs:**

- core：`workflows/easyuuv_v2_qualification_artifact.py:86-116,133-162,223-293,296-452`
- CLI：`workflows/validate_easyuuv_v2_qualification.py:18-127`
- writer：`workflows/merge_easyuuv_v2_qualification.py:43-63,131-180`
- confined output：`workflows/qualify_easyuuv_v2.py:91-125,350-376`

```python
# workflows/merge_easyuuv_v2_qualification.py:43-63
with tempfile.NamedTemporaryFile(..., dir=path.parent, delete=False) as stream:
    json.dump(payload, stream, allow_nan=False, indent=2, sort_keys=True)
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
os.replace(temporary_path, path)
```

**Copy/reuse:** `argparse` parser、`main(argv)->int`、只捕获预期 `OSError/ValueError`、stderr `ERROR: <stable_reason>`、成功 JSON `sort_keys=True`、失败 return 1；原子 tempfile/fsync/replace；写边界重复校验 result-root 与 symlink component。

**Phase 7 additions:**

- reason code 至少覆盖 SPEC 的 missing/extra/version/type/shape/nonfinite/range/padding/mask/topology/wrench/context/provenance/continuity；reason code 与 detail 用 `reason:detail` 分离。
- `motor_pwm_padded_8[i] == 0` 当 `thruster_mask_8[i] == 0`；mask 只允许 catalog 派生的 8/6/4 形式。
- oracle 与 estimated 必须是不同对象/namespace；estimated `available=false` 合法，`available=true` 必须有 method/version/source signals；禁止把 oracle source 标为 deployable estimate。
- raw v1 record 与 compatibility view 都必须被 strict v2 validator 拒绝。
- deterministic serialization 与反向输入顺序无关，失败 merge 不覆盖旧输出；参照 `tests/test_easyuuv_v2_qualification_runner.py:1575-1597`。

### 7. v1 compatibility adapter：只读报告，不是 v2 builder

**Closest analog:** `load_koopman_samples()`（`koopman_data.py:158-169`）和 v1 fixture `tests/fixtures/koopman_step_small.jsonl`。

**Recommended pattern:** adapter 先调用现有 v1 loader，返回显式命名的 compatibility result：

- `source_schema="v1"`
- `eligible_for_v2_cross_configuration_training=False`
- `unavailable_fields=("virtual_control_4", "applied_wrench_6", "platform_context", ...)`
- 原始 v1 samples 或只读 view

**No analog / do not infer:** 仓库没有合法的 v1→v2 promotion 模式。adapter 不得调用 v2 builder，不得把 `action_4d` 改名为 `virtual_control_4`，不得从 `pwm_8d` 逆算 control/wrench，不得猜 configuration。canonical v1 fixture 只能证明“可读且不 eligible”。

### 8. Phase 7 真实服务器 runner、bundle、bootstrap 与 pullback

**Runner analog:** `workflows/qualify_easyuuv_v2.py:42-125,128-197,335-376,379-480,496-632`。

可复用的核心行为：

- parser/help 在本地不导入 Isaac；`AppLauncher` 必须先于 Gym/Torch/task import（`496-515`）。
- `_repository_commit()` 拒绝 tracked dirty source（`335-347`）。
- 缺 actual telemetry 立即失败；failure row 使用稳定 reason code 且 `eligible_for_merge=false`（`379-425`）。
- 在 `SimulationApp.close()` 前原子写入并 flush（`455-467`）。
- 输出路径只能落在显式 result root 内，并在真正写入前再次检查。

**Server scripts analog:** `scripts/phase6_prepare_bundle.ps1`、`phase6_server_bootstrap.sh`、`phase6_server_qualification.sh`、`phase6_pullback.ps1`。

```bash
# scripts/phase6_server_qualification.sh:91-137
any_failed=0
run_one() {
    set +e
    "$ISAACLAB_PY" -p -u "$RUNNER" ... 2>&1 | tee "$RESULT_ROOT/logs/$configuration.log"
    pipeline_status=("${PIPESTATUS[@]}")
    set -e
    ...
}
[[ "$any_failed" -eq 0 ]] || exit 1
```

```powershell
# scripts/phase6_pullback.ps1:110-179
$localHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $qualificationPath).Hash.ToLowerInvariant()
if ($localHash -ne $serverHash) { throw "sha256_mismatch:..." }
...
if ($validatorExitCode -ne 0) { throw "validator_failed:..." }
Move-Item -LiteralPath $stagedEvidence -Destination $canonicalEvidence
```

**Copy/reuse exactly in spirit:** clean tested HEAD → Git bundle + commit sidecar → isolated server clone → source/runtime preflight → per-configuration native/tee/semantic gates → strict merge/validate/hash → never-reused local staging → independent hash + validator → atomic promotion。

**Required Phase 7 divergence:**

- 新隔离目录与 artifact root（例如 `/root/EASYkoopman-phase7-v2`、`source/results/koopman_phase7`）；不得覆盖 Phase 6 或历史 `/root/EASYkoopman`。
- 只运行 `base`、`uuv6`、`uuv4`，每个至少 8 条连续 transition；expected set 是精确三构型，不是八构型。
- `uuv4` runner 必须包含非零 raw yaw case，不能复用 Phase 6 mask 后 excitation。
- server semantic gate 要检查 JSONL 行数/连续性、schema v2 strict pass、真实 topology、source/runtime sidecars 与 manifest SHA-256；进程 exit 0 本身不算通过。
- 本地 contract fixture 只能标为 `local_contract`；任何 mock/手写 JSON 不能写 `server_isaac_smoke`。
- planning 提交中不创建成功 `source/results/koopman_phase7`；只有真实回传且 validator/hash 通过后独立 evidence commit。

## Test Patterns

### Fixture builder + mutation matrix

`tests/test_easyuuv_v2_qualification.py:51-126` 的 `_valid_row()` / `valid_server_payload()` 是 v2 positive fixture 的最近模式；`251-310` 展示 missing/extra/duplicate/topology/yaw 欠驱动 mutation，`470-525` 展示 strict JSON 和 CLI。

```python
@pytest.mark.parametrize(("field", "value", "reason"), (...))
def test_wrong_topology_field_is_rejected(field, value, reason):
    payload = valid_server_payload()
    _row(payload, "base")[field] = value
    with pytest.raises(ValueError, match=reason):
        validate_qualification_payload(payload, ...)
```

Phase 7 应建立一个 canonical v2 transition fixture factory，并通过 deepcopy 单点 mutation 覆盖所有 reason code。除类型/shape 外，必须加入语义交换反例：raw action 冒充 virtual control、desired wrench 冒充 actual wrench、oracle copy 冒充 estimated、padding 非零、PWM 被默认 dataset 当作 `U`。

### Dataset fixture and frozen v1 regression

`tests/test_koopman_dataset.py:9-31` 使用 committed 小型 JSONL fixture 检查 shape、dt、metadata 与 `X[1]==Y[0]`。Phase 7 新 fixture 应至少含 8/6/4 三拓扑、同一 4D `U` 和 episode continuity；同时保留原测试断言 `v1 U.shape == (4,8)`，作为 D-01 回归锁。

### Actual telemetry and atomic failure evidence

`tests/test_easyuuv_v2_qualification_runner.py:299-408` 覆盖 result-root escape/symlink、原子 writer 重校验、missing telemetry、shape mismatch、nonfinite failure row 可重读。Bridge tests 应复用同样结构，并使用 fake env 的 before/after state 验证一条 `env.step()` 只产生一条原子 transition。

### Evidence-chain ordering tests

`tests/test_easyuuv_v2_qualification_runner.py:603-824` 通过读取脚本文本和临时 Git repo 锁定 bundle/sidecar、AppLauncher 顺序、`PIPESTATUS`、merge 前 fail gate；`1394-1424` 锁定 pullback 的 hash/commit/validator 全部先于 `Move-Item`。Phase 7 应复制这些测试意图并改为三拓扑 expected set、新路径和新 validator；不要只做“文件包含某字符串”的弱测试，关键 preflight/pullback 至少保留一个真实临时 repo/process failure case。

### TDD execution order

每个实现计划先提交 RED contract，再提交最小 GREEN 实现：

1. schema/validator negative fixtures；
2. dataset `U=4` 与 v1 `U=8` 双锁；
3. env telemetry 和 Bridge atomic-step fake tests；
4. server runner/script/pullback fail-closed tests。

## Shared Patterns

### Error handling

- 内核统一 `ValueError("reason:detail")`；runtime 缺失可用 `RuntimeError`，到 CLI 边界转换成 stderr + exit 1。
- 不捕获 `BaseException`；只在 Isaac runner 的环境执行边界捕获 `Exception` 以写 failure evidence，然后仍返回非零。
- failure artifact 不伪装成功 schema/evidence level，且显式 `eligible_for_merge=false`。

### Determinism and file safety

- JSON 使用 `allow_nan=False, sort_keys=True`；JSONL 每行 canonical encoding 规则必须固定。
- 原子 tempfile 必须与目标同目录，flush + `os.fsync` 后 `os.replace`。
- output root 做 lexical + resolved containment 和 symlink component 检查，并在真正写入时二次验证。
- merge 先完整严格验证内存对象，成功后才 replace；失败必须保留原输出字节。

### Provenance

- source commit、task、configuration、seed、dt、episode id、step index、simulation time、controller mode、runtime versions 和 evidence level 均进入 manifest/record。
- episode invariant 单独验证；不能只验证每行 individually。
- server hash、sidecar、runner/log/semantic gate 和 pullback validator 缺一不可；planning、implementation、server evidence 保持独立提交。

### No authentication pattern

该阶段没有 HTTP/controller/auth 数据流；不要引入 web middleware、数据库或新 runtime dependency。

## No Close Analog Found

| File/Concern | Why no exact analog exists | Planner action |
|---|---|---|
| oracle/estimated typed context | 现有环境有 ground truth，但没有可部署 estimator object | 按 SPEC 定义两个独立对象；estimated 默认 unavailable，不实现 estimator |
| actual thruster-only wrench telemetry | 当前只计算局部变量并最终混入总外力 | 在 thruster sum 后缓存真实 6D 值；禁止 TAM/PWM 重建 |
| explicit v1 compatibility view | 现有 loader 直接返回 v1 samples | 新建只读、不可 promotion 的 compatibility result |
| episode manifest/continuity validator | v1 只检查 timestamp，Phase 6 只检查 row set | 新增 episode-level validator 与 stable reason codes |
| semantic-swap negative fixtures | 现有测试主要是字段/type/topology mutation | 为 raw/virtual、desired/applied、oracle/estimated 专门加反例 |

## Reuse / Do-Not-Copy Matrix

| Area | Reuse | Do not copy |
|---|---|---|
| v1 data | builder/logger/JSONL/fixture组织 | 字段名、`PWM_DIM=8`、`reconstruct_training_tuples(U=pwm)` |
| v1 dataset | frozen dataclass、shape/count/dt checks | 修改现有类、让 v2 默认 U 指向 PWM |
| catalog/TAM | exact catalog、channel order、rank/mask、runtime buffers | 第二份构型表、把 topology record 当完整 platform context |
| env telemetry | `detach().clone()`、真实执行链插点 | desired TAM wrench、最终含流体外力的 total wrench |
| Phase 6 validator | bounded JSON、reason codes、deterministic CLI | missing-only 字段检查、Phase 6 固定 schema/8-config set |
| Phase 6 server | bundle/sidecar、isolated clone、pipeline gates、staging/hash/promotion | 八构型重跑、旧目录/旧 artifact root、成功证据预生成 |

## Recommended Plan Boundaries

### 07-01 — Pure schema v2、strict validator、v2 dataset 与 v1 compatibility

- 只改/新建 Isaac-free Python 和 tests。
- 先锁字段、reason code、episode continuity、`U=virtual_control_4`、v1 non-eligibility。
- 完成 `CONT-01`、`CONT-03`、`CONT-04`、`CONT-05` 的本地核心，但不声称真实 telemetry 已接通。

### 07-02 — EasyUUV runtime telemetry 与 Koopman Bridge

- 修改 `easyuuv_nc/env/easyuuv_env.py` 的最小只读 telemetry seam；新建 Bridge。
- exact-eight catalog/TAM/mask 本地合同；明确 `uuv4*` 非零 raw yaw → zero virtual yaw。
- 完成 actual applied wrench/context 的真实来源与 atomic transition tests；不训练模型、不改 MPC。

### 07-03 — Runner、manifest、CLI 与离线证据链

- 新建三拓扑 runner/merger/validator CLI、四个 phase7 transfer/server/pullback scripts 和 runbook。
- 用临时目录/Git repo/fake process 做 fail-closed TDD；不创建 canonical server success artifact。
- local preflight 必须包含 v1 regression、full Isaac-free suite、compileall、script parse 与 protected-path diff gate。

### 07-04 — Real server checkpoint、pullback 与 phase closure

- 仅在 07-01..03 全绿且 clean tested commit 后请求/使用服务器。
- `base`、`uuv6`、`uuv4` 各至少 8 条连续真实 v2 transition；strict validator/hash/pullback 全通过。
- server evidence 独立提交，随后写 SUMMARY/VERIFICATION 映射 `CONT-01..05`；任一 topology/sidecar/hash/validator 缺失则 Phase 7 保持 incomplete。

这四个边界保持 Phase 7 只证明“跨构型数据与控制合同接通”，不会越界声称 Koopman 跨构型预测有效（Phase 8）或 MPC 已改用 4D virtual control（Phase 9）。

## Metadata

**Analog search scope:** root Koopman data/dataset、`workflows/`、`easyuuv_nc/`、Phase 6 scripts/runbook/artifacts、`tests/`  
**Primary analog groups:** 8  
**Files classified:** 16  
**Exact/strong role matches:** 13  
**No exact analog concerns:** 5  
**Project-local AGENTS/skills:** repository root 未发现 `AGENTS.md`、`.codex/skills/` 或 `.agents/skills/`，因此以 locked Phase 7 contract 和现有代码约定为准。
