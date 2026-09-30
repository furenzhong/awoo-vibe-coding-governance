# 操作接续示例

本例展示已经知道“要完成预览”的新会话，怎样找到“在哪个环境、用什么身份、查询哪个操作、接着做什么”。所有身份和操作都是合成数据；服务只读写你指定的本地隔离目录，不联网、不使用账号或凭据，不代表真实服务器或后台已经验证。

## 记录各归其位

- [已有操作说明](operations.md)：环境、连接方式、身份、凭据需求和可行步骤。这类知识不在每次交接中重抄。
- [已有检查点](checkpoint.json)：复用任务上下文的现有字段，保存操作 ID、最后观察、未知项和下一步。它是形状示例，没有独立注册的任务／派工基线，不可直接冒充目标项目任务。
- [交接入口](handoff.md)：链接操作说明和检查点；文件存在不证明当前状态仍与记录相同。
- [离线探针](local_service.py)：提供查询与推进已有操作的实际动作，不实现真实业务服务。

操作状态从 `ready` 变为 `completed`；原操作 ID 保持不变。先查询原操作再决定是否推进，已经完成时无需重做。探针不提供重新提交接口，因此不能用它验证真实服务是否支持重复请求防护。

## 运行

需要 Python 3.10+。从本示例目录执行；`<new-sandbox>` 替换成项目外一个尚不存在、父目录已存在的目录，后续一直使用同一目录。环境和身份值是本地夹具参数，不是权限认证。每个夹具目录只由一个执行者操作，不提供并发写入互斥。

```text
python local_service.py init --sandbox <new-sandbox>
python local_service.py inspect --sandbox <new-sandbox> --environment rehearsal --identity preview-operator --operation preview-041
python local_service.py finish --sandbox <new-sandbox> --environment rehearsal --identity preview-operator --operation preview-041 --expected-state ready
python local_service.py inspect --sandbox <new-sandbox> --environment rehearsal --identity preview-operator --operation preview-041
```

初始化只允许全新目录，不覆盖已有材料。查询只读。推进会原子更新夹具的 `state.json`，返回同一操作的完成状态与完成计数；已完成后再调用返回 `changed: false`，计数不增加。错误环境、身份或操作 ID 会报错；尚未完成时，前置条件不符合实际状态也会报错，均不修改状态。

这是公开教学例子，命令和结果逻辑都可见，不能将照着本页执行称为“新会话盲接通过”。独立试验应另造材料，在项目外封存期望答案，再给没有本轮历史的接手者正常项目入口，见[治理试验](../../docs/03_DELIVERY/GOVERNANCE_TRIAL.md)。

本例不包含真实登录态、真实工具恢复、完整聊天记录或自动清理。示例的历史观察均为合成情境，任何实测结果需由运行者单独留证。
