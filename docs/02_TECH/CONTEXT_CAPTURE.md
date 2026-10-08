# 会话事件记录与恢复

这是 AI 的操作入口。工具包 v1.5 提供可选的本地记录组件；是否启用、哪些事件真实到达，以目标项目的配置和采用证据为准。项目事实仍由 `project-os.json` 的四项来源及相关专题维护。事件文件不是第五份当前事实，也不是任务已经完成或纠偏已经送达的证明。

[共享指令](../00_PROJECT_CONTROL/DOCUMENT_GOVERNANCE_SYSTEM.md)要求 AI 在重要变化仍可查证时主动写回对应来源，即使未启用原生采集也应执行；下一步依赖变化时先保存，不等自动压缩或用户提醒。压缩／恢复后用实际可取得的摘要和相关用户输入检查遗漏，再核对现行决定及现场。记录接口负责保存可观察证据，规则负责推动语义维护；二者与接续验证分别报告。无法取得原生摘要时保存必要接续信息及缺口，不冒称原始摘要或完整恢复。

## 1. 一次采用，随工作维护

普通 `project_os.py apply` 只安装可用工具，不启用 hooks。已获准接入自动记录时，在目标外准备候选：

```text
python <kit>/scripts/project_os_context_hooks.py setup-plan --target <project> --out <outside-project-new-directory> --adapter claude --adapter codex --python <actual-python-executable> --claude-version <observed-version> --codex-version <observed-version>
```

AI 核对 `plan.json` 后，通过现有 `project_os.py upgrade-apply --target <project> --plan <plan.json> --journal <new-outside-journal.json>` 应用。setup 本身不写目标，不改变工具的 hook 信任。保留其他 hook 和已有设置；发现同名适配器命令不同，先查明差异。版本参数是采用声明，不是自动探测结果。旧项目的主检查器需另按升级指南明确升级，setup 不改其版本和 manifest；旧检查器仍可用独立 `project_os_context.py status` 查看记录。

配置文件是 `project-os-context.json`；项目级入口为 `.claude/settings.local.json` / `.codex/hooks.json`。实际工具是否读取、支持事件、要求 `/hooks` 信任或需新会话加载，按安装版本验证。配置生成成功不能算真实接入。命令固定使用采用时的 Python 和项目路径；换机器/路径时重新准备局部配置，不盲用旧绝对路径。

私有记录位于 `.project-os-local/context/`，必须先被 Git 忽略。默认 `redacted`：启发式去除常见凭据，较长正文有界截断并标明；不保证识别所有敏感表达。`metadata_only` 不保存正文；`private_original` 仅在项目明确允许原文留存后选用，仍只留私有证据。任何模式都不解析完整原生日志、不后台扫描、不调用第二个模型。

## 2. 已采用项目中的每次工作

收到 hook 短提示后，使用其中真实 `binding_id` 和 `capture_id`。首次 hook 只建立讨论绑定，不推定业务任务已经启动。按当前问题读取相关来源，无需每轮全文读取所有历史。

```text
python scripts/project_os_context.py status --target . --json
python scripts/project_os_context.py resume --target . --binding <binding-id> --json
```

- 继续本会话时，核对相关待处理输入、当前来源和真实操作。
- 换会话时，先用 `status` 找到与当前专题/任务有关的原绑定；新绑定为空不能证明旧工作没有缺口。读取有关旧绑定的 `resume`，不把所有会话混成一条总水位。
- 发生实质纠偏，在依赖它的写入或派工之前将决定、替代范围、未决项保存到职责文件，再提交核对回执。
- 没有新决定或现场变化，只提交带依据的 `no_change`；可以批量核对同轮若干事件，不重写专题或机械新增检查点。
- 遇到证据无法裁定的冲突，提交 `unresolved`，只暂停依赖该冲突的动作。普通记录不要求用户逐项确认。

输入、输出、压缩和恢复只触发证据记录与必要核对。它们均不启动或提示文档盘点、归类、合并压缩、归档和删除。清理仍只由用户明确唤醒。

### 主动换会话前的交接

用户明确要求“准备换新对话，更新文档治理”时，先检查相关绑定的待处理输入、可获得的原文和当前来源，再把尚未落盘的决定、纠偏、否决原因、验证结果和未完成现场写回原职责文件。无需因换会话新增绑定、任务或派工版本；实际身份／任务改变时才按本指南维护相应记录。未启用事件记录的项目也可以执行同样的交接，只需明确可见范围。

操作信息按需补足：正确环境及入口、连接方式、账号身份、凭据获取位置（不含值）、已成功步骤与验证时点，进入已有部署／操作说明；本次进程／会话／外部操作 ID、查询方法、停点和未知项，进入既有检查点；HANDOFF 只链接到这些来源。判断依据是缺失后是否会重问用户、重复试错、错环境或重复已受理操作，不要求全项目填服务器表。

原生捕获不是完整工具调用日志。只在工具输出出现过的成功命令或错误原因，未必已进入事件或摘要；AI 需从仍可查证的证据提取必要知识。拿不到的细节明确标缺口，不能从完整水位推断没有遗漏。服务器和登录状态可能变化，接手者应先核实环境、身份和原操作，再继续。

回执只需简述：**新会话入口；已保存的变化；核对过的范围与剩余缺口；实际接续已验证或未测**。这四项不是新增存储格式。`reconcile` 的成功仅确认其覆盖的声明与引用，不证明交接语义完整，也不证明新会话已经实际接续。保持相关 `pending/unresolved` 和未知尾部，不能为交接“完成”把它们改成已解决。用户不要求换会话时，不新增自动提醒、退出拦截或每轮总结。

## 3. 关联专题和真实任务

明确会话主题后可创建讨论绑定：

```text
python scripts/project_os_context.py bind --target . --adapter generic --session-id <actual-session-id> --topic docs/topic.md --mode discussion --json
```

`generic` 用于已知具体接口的自控 harness 或模型协助记录；不是“所有模型已自动接入”。没有原生 ID 时，由自控 harness 生成并持续复用自身会话 ID，注明其来源，不冒充另一工具原生 ID。

同一会话从讨论转为已授权执行、切换任务、增补相关专题或改变正文策略时，显式创建新绑定，保留旧历史：

```text
python scripts/project_os_context.py bind --target . --adapter claude --session-id <actual-session-id> --mode execution --task-id <existing-task-id> --topic docs/topic.md --supersedes <current-binding-id> --payload-policy redacted --json
```

执行模式要求任务 JSON 已真实存在；不为记录补造 `running`、派工时间或验收。新绑定有独立来源流并引用旧绑定；旧事件不会自动变成已核对。hook 选同工具、同工作区、同会话的唯一活跃绑定。讨论记录、捕获 ID、检查点版本和派工 `context.current_revision` 独立；单纯压缩不递增派工要求版本。

## 4. 如何提交核对结果

先读取事件正文和相关原始输入，检查当前权威来源及替代关系。`resume.current_refs` 给出当前文件摘要；仅拿到 hash 并不等于读过内容。事件中的 `source_refs` 是捕获当时的字节摘要，未保存源文件全文。

AI 将以下 JSON 写入私有临时文件，例如 `.project-os-local/reconcile-input.json`，填入实际 ID、路径和 SHA-256。不要把示例占位值当成证据。

```json
{
  "event_ids": ["capture-actual-id"],
  "outcome": "no_change",
  "reason": "本次只是查询进展；已核对当前专题与输入，没有新要求或现场变化。",
  "source_refs": [{"path": "docs/topic.md", "sha256": "actual-current-sha256"}],
  "writes": [],
  "checkpoint_ref": null,
  "next_action": "按当前专题中的未完成步骤继续；尚未验收的结果不宣称通过。",
  "unresolved": []
}
```

```text
python scripts/project_os_context.py reconcile --target . --binding <binding-id> --input .project-os-local/reconcile-input.json --json
```

分类要求：

| outcome | 必须保留的含义 |
|---|---|
| `no_change` | 说明为什么没有需持久化的新含义；列实际读取且版本仍匹配的来源；不能同时声明文档写入 |
| `changed` | 指向已保存的专题或该任务已有检查点，说明增量与替代关系；本次写入可用下面的 `writes` 核验 |
| `unresolved` | `unresolved` 数组逐项写明未决原因及受影响动作；保存了冲突不代表冲突解决 |

已发生写入的条目格式：

```json
{"path":"docs/topic.md","before_sha256":"captured-before-sha256","after_sha256":"actual-current-sha256"}
```

`before` 必须在本次所涉事件的来源快照中，`after` 必须与磁盘一致，文件须属于绑定专题、四项来源或关联任务的检查点。若结果已经在现行来源中，由 `changed` 引用它并说明依据，无需再写一次。工具只能验证引用和字节，不能自动证明语义判断正确或模型确实读过原文。

**核对接口不替模型改业务文档。** 写入者先按现有写入归属完成候选审查与安全写入，再保存回执。多人可能改动或需可回退多文件更新时，使用既有 upgrade 候选、写前 hash 检查及 journal；不要用 `reconcile` 冒充文件事务。部分文件已写、其余失败时，保留候选、日志和未完成项，不能提交“全部落实”的回执。恢复后先核对磁盘，不覆盖后来的决定。

`reconcile` 拒绝过期来源、跨绑定事件、缺失写入结果及越界写入声明。来源后来改变会使有关旧回执重新显示待核对。错误的 `no_change` 仍可能通过结构校验，所以恢复不能仅按水位跳过用户原话；`resume` 保留最近相关输入，较早关键约束按任务和来源定位复核。

## 5. 原生事件和覆盖报告

| 原生事件 | 留证行为 | 能证明什么 |
|---|---|---|
| `UserPromptSubmit` | 保存可见用户输入和可用 turn/prompt ID | 该输入已到记录入口，不证明所有历史已覆盖 |
| `PreCompact` | 保存压缩开始的观察 | 不要求模型再执行一轮，不假定来得及补写 |
| `PostCompact` | Claude 提供 `compact_summary` 时保存；Codex 默认只记事件 | 可读正文存在与否分开报告，不从私有日志猜正文 |
| `SessionStart` | 保存恢复观察，注入绑定、指南和恢复命令 | 下一模型能获得指针仍须真实工具试验确认 |
| `Stop` | 保存可用的最后助手消息 | 是工具输出证据，不等于工作完成、验收或消息已被其他 AI 采用 |

原生摘要与元数据放在**同一个不可变 event JSON**，避免“摘要成功、侧车文件失败”的双文件提交问题。核对回执也各自原子落盘；覆盖结果按需从事件和回执推导，没有可失真的独立 `coverage.json`。同原生事件 ID 重试幂等；缺稳定 ID 时保留不同观察，不按相同正文吞掉第二次真实事件。

每次新事件与核对回执会增加历史文件。查询可以复用同次操作的读取和计算，但不会因此删除记录、只保留最近事件，或把尚未核对的旧纠偏隐藏掉。当前没有自动保留期限、轮转或存储容量上限；处理成本的实测范围从项目当前状态链接，不将性能改进称为“历史不再增长”。需要归档、压缩或删除时仍须用户明确发起，记录增长本身不触发清理或询问。

1.6 候选减少同次 `status/resume` 的重复来源读取及事件解析，但 `capture/reconcile` 仍扫描相关会话的完整历史。Windows 合成测试中，5,000 条单流事件的捕获仍可能超过生成 hook 的 10 秒限时；不能据查询提速宣称捕获不会超时。遇到真实超时，先核对原事件是否已保存、写入者／锁是否仍在，以及本次覆盖缺口；使用可核实的原事件 ID 做幂等恢复。缺口保持未知，不靠删除历史、强行解除锁或虚填核对回执宣称完成。

读取检测到文件或集合变化时会拒绝该次观察；核实实际写入者后基于当前历史重试。同一次查询复用的是来源的当次观察，下一次查询重新读取；这不提供跨文件原子快照，接手仍须核对当前来源及实际现场。

`status` 的 `observed_kinds` 仅列已保存记录类型，不验证这些记录是否由真实工具产生。平台能力须由采用记录链接真实运行证据，合成测试不能冒充。`check/snapshot` 的可选 `context_capture` 报告同样不运行模型、不刷新原生日志。

原生 hooks 通常没有完整连续游标，适配器保持 `source_complete=false`，`reconciled_through=null`；明确列已核对 ID、pending、unresolved 和未知尾部。接入前的消息、漏掉的事件和另一执行器的当前状态不能推定已覆盖。自控 harness 只有确有来源连续性证据时才能提交 `source_sequence/sequence_start/source_complete`。

hooks 可能并发。看到 `PreCompact` 或 `SessionStart(source=compact)`、但尚无可关联完成证据时，保留压缩缺口；没有周期 ID 不猜配对。恢复先到、摘要后到时，晚到记录仍保存，下一次查询可见。恢复者可有界重查一次，仍缺失就依赖可见原始输入和当前来源核对，暂停受影响动作；不无限等待，不用 Stop 阻止退出。

## 6. 故障、停用和继续开发

捕获失败返回错误，不宣称保存成功；不要把失败输出误当“没有变化”。检查已有事件、磁盘权限、忽略规则与配置，修复后只能重放确实可访问的输入；拿不到的尾部继续标未知。存储写锁冲突同样留作失败，不重试无界循环，也不停止其他开发进程。

停用新的捕获：将 `project-os-context.json` 的 `enabled` 改为 `false`；单工具可改对应 `adapters.<name>.enabled=false`。这是显式配置修改，记录停用时点。已加载旧 hook 会调用后立即返回，不删除历史；其他 hooks 不受影响。随后可从原生配置中只移除本适配器条目，并按宿主要求重载。不要覆盖整个设置文件，也不要自动清理私有证据。

回退本次采用用目标外 journal；保留后来工作，遵循最近一层先退。配置改变正文策略后，既有绑定需显式 `--supersedes` 才继续捕获，防止沿用旧留存授权。原文材料需随项目私有备份另行保存，Git clone 不携带；跨工作区只传允许共享的最小来源与快照，不能把原机私有绝对路径当交付。

真实采用报告至少写清：工具版本、实际生效项目、按事件的实测结果、手动/自动压缩分别是否验证、正文能力、缺口、停用和恢复位置。不要用“已配置”替代“已经捕获”，也不要宣称跨模型上下文已经无损同步。
