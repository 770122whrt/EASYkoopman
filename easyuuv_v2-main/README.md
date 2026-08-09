# easyuuv_nc — EasyUUV-STDW 去伪存真重构版

> 主仓库 `easyuuv_stdw` 被大量探针污染后的**干净重构子仓库**：干净包名、零 bootstrap
> hack、剔除死变体（DCE）、保留经 byte-level 等价验证的 flip360 主路径。

## 一页速览

- **它是什么**：EasyUUV 水下机器人 STDW 分离式在线自适应的**可交接、可复现**核心。
- **活线成果**：flip360 深度 free-float（so3 -83%）+ 逆动力学动作锚点（R²=0.92）+
  方向门控物理防火墙（拦 ~40% 毒梯度）+ 谱隔离 zeta-only（policy L2=0）。
- **死分支**：D1(DCE) 已删；D2–D6 见 `docs/AGENT_HANDOFF.md` §3，禁止复活。

## 快速开始

```bash
cd <...>/easyuuv_stdw/easyuuv_nc
export PYTHONPATH=$(pwd):$PYTHONPATH

# flip360 免训练复现（主验收，~5 分钟）
bash workflows/tools/run_flip360_repro.sh 6000
# 通过标准：accepted=95/6000，so3≈0.51，fm_bridge_curvature≈0.053（非 NaN）
```

## ⚠️ 两个调用坑（务必遵守）

1. **不要用 `run_with_isaac_env.sh` 直跑相对路径脚本**（`exec python "$@"` 会误解析）。
   正确：`conda run -n isaaclab python -u <脚本>`。
2. **必须加 `-u`**：`conda run` 缓冲 stdout，不加则实时 print 标记捕获不到。

## 文档地图（`docs/`）

| 文件 | 用途 |
| --- | --- |
| `AGENT_HANDOFF.md` | **接手第一读**：结构导览 + 死分支索引 + 下一步 |
| `COMMAND_CONTRACT.md` | 重构后权威命令契约（训练/复现/路径速查） |
| `REFACTOR_GUIDE.md` | 结构原则 + adapt.py 拆分蓝图 + 配置原则 |
| `00_CONSOLIDATION_LEDGER_20260720.md` | 全量结论流水账（Phase 1–8 去伪存真史） |
| `00_CONSOLIDATION_PLAN_20260720.md` | 结论整理规则 |
| `00_POSTER_CONSOLIDATION_20260720.md` | 海报级成果汇总 |

## 已注册 gym task（4 个，无 DCE）

`EasyUUV-Direct-v1` · `EasyUUV-Direct-Parametric-v1` ·
`EasyUUV-Direct-Parametric-SatObs-v1` · `EasyUUV-Direct-Parametric-Wide256-v1`
（entry_point 均为 `easyuuv_nc.env:EasyUUVEnv`，`import easyuuv_nc` 即注册）。

## 状态（20260721）

- ✅ 干净包名 env 骨架 + 训练/复现验收①②通过（flip360 308 列 byte-level 等价）
- ✅ 五类文档 + README 齐备
- ⏭️ adapt.py（~7200 行）拆分为 `adaptation/` + 删 D2–D6（见 REFACTOR_GUIDE §3）
