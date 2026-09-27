# Explicit upgrade candidates / 明确的升级候选

本目录全部为公开合成材料，不是任何真实项目的文档副本。它展示两类候选；真实升级先按[升级指南](../../docs/03_DELIVERY/GOVERNANCE_UPGRADE_GUIDE.md)核实职责与事实，再由 AI 准备 proposal，用户无需手填。

| 目标 | 旧基线 | 本地变化与候选目的 |
|---|---|---|
| `docs/RULES.md` | [base](base/RULES.md) | [current](current/docs/RULES.md) 增加只接受用户主动清理；[upstream](upstream/RULES.md) 改为事实只维护一处；[candidate](candidate/RULES.md) 明确保留两种变化 |
| `docs/HANDOFF.md` | 未知，`current_only` | [current](current/docs/HANDOFF.md) 不知道原执行会话和保存结果；[candidate](candidate/HANDOFF.md) 只补现场核对与防止重复执行，保留未知，不伪造历史 |

规则条目的 base 是本例给定的旧实际内容，仅用于示范可核实基线。真实项目不能从某个旧版模板或相似文件反推“原来安装的就是它”。候选不自动合并；若 AI 把规则候选改成纯 upstream，就会丢掉本地的主动清理边界，即使 JSON 合法、工具写入成功，语义仍然失败。

## Proposal 字段

[proposal.json](proposal.json) 是本例可直接使用的输入。顶层 `schema_version` 为 `1`，`components` 列出明确修改项：

| 字段 | 含义 |
|---|---|
| `component` | 该项治理职责或组件的标识 |
| `path` | 要改的目标文件，相对目标项目根目录 |
| `reason` | 为什么需要改动及保留什么；真实使用时附可核实的来源 revision 或依据 |
| `candidate` | 已形成的完整候选文件，相对 proposal 所在目录 |
| `base`、`upstream` | 有旧实际采用内容时成对提供；路径相对 proposal 所在目录 |
| `mode` | 无旧基线为 `current_only`；有基线通常为 `candidate`，双方均有独立变化时为 `merged` |
| `merge_reason` | `merged` 必填，说明如何保留本地定制和处理新版变化 |

`component/path/reason/candidate` 必填。无基线时 `mode` 缺省为 `current_only`，有基线时缺省为 `candidate`；为使审查清楚，本例显式填写。若当前内容和 upstream 都不同于 base，且它们彼此不同，工具要求 `mode: merged` 和非空解释；这只是防止静默替换的结构门槛，无法证明合并语义正确。示例没有伪造真实来源 revision，所有内容只代表本目录的合成对照。

## 在一次性副本中运行

在工具包根目录执行以下命令。`../awoo-upgrade-demo/` 应是尚未使用的新目录；复制失败时先核对已有内容，不覆盖它。目标副本与计划、日志互为兄弟路径；原合成材料保持不变。

```text
python -c "import shutil; shutil.copytree('examples/upgrade/current', '../awoo-upgrade-demo/target')"
python scripts/project_os.py upgrade-plan --target ../awoo-upgrade-demo/target --proposal examples/upgrade/proposal.json --out ../awoo-upgrade-demo/plan.json
python scripts/project_os.py upgrade-apply --target ../awoo-upgrade-demo/target --plan ../awoo-upgrade-demo/plan.json --journal ../awoo-upgrade-demo/journal.json
```

应用后，两个目标文件应分别等于 `candidate/` 的对应内容。`RULES.md` 同时保留单一事实维护和手动清理约束；`HANDOFF.md` 仍然说原身份与保存结果未知。计划和日志保留应用所需内容及结果，不要求重新下载上游。

没有后续修改时可回退：

```text
python scripts/project_os.py upgrade-rollback --target ../awoo-upgrade-demo/target --journal ../awoo-upgrade-demo/journal.json
```

回退后，两个文件应等于 `current/docs/` 的原内容。若应用后有新修改，先保留新内容；自动回退冲突项不能恢复旧整份文件，由 AI 比较并形成局部逆向补丁。不要在真实项目上为演示故意制造冲突。

本例只演示明确候选的比较、应用与回退，不代表已经完成某个业务项目的治理接手验收。它也没有启动模型、运行任务、归档历史或调用外部服务。

## English summary

These are synthetic public fixtures. The rules example provides a known base, a local user-only cleanup constraint, an upstream single-source maintenance change, and an explicitly merged candidate that preserves both. The handoff example has no historical baseline: its `current_only` candidate retains the unknown executor and operation outcome while adding recovery instructions.

The commands above copy the target into a new disposable sibling directory, then plan, apply, and roll back the explicit candidates. Planning and application do not decide whether a merge preserves project intent. The AI prepares and reviews the proposal; the user does not need to fill in its fields. Real upgrades follow the [upgrade guide](../../docs/03_DELIVERY/GOVERNANCE_UPGRADE_GUIDE.md), including an independent continuation exercise and coordination with active writers.
