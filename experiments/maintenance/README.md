# 当前化验证

`tests.xml`：最终当前tests 221通过。`tests-first.xml`：首次220通过、一个过期v1源码断言失败，保留迁移过程。

`validation-replay.json` / `test-replay.json`：对原v88的24条独立轨迹重新验收、冻结预测，无重新训练。`verification.json`：与原全部窗口、门限、源哈希比较以及独立源码包加载结果。`source-manifest.json`：实际验证的76文件哈希。

`cleanup.json`：精确旧文件清单、语义模块映射、原始归档位置与恢复提交。旧版数值基准在 `tests/fixtures/`。

当前源码包在本地 `results/current-release/`。`verify.py` 是此次一次性复核脚本，要求新输出文件和新的解包目录，不覆盖已有记录。这里的通过是整理正确性证据，不是新Isaac或闭环成功证明。
