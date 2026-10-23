# 2026-10-23 组合行为验证

## 目的

验证“先写行为合同，再检查组合结果；用故意缺陷和正确实现检验检查方法”能否发现外观完整但组合后错误的 AI 代码。该记录只证明本次三个隔离场景，不证明能发现未知 bug，也不替代真实业务环境验收。

## 被测材料

- 夹具：[`examples/composition-challenge/trial.py`](../../../examples/composition-challenge/trial.py)
- 说明：[`examples/composition-challenge/README.md`](../../../examples/composition-challenge/README.md)
- 运行基线：`537da45e306f82bf7d9f01bcc9b440fd19b7860b`，工作区在运行时包含本次新增夹具和文档改动；未提交变更不能归给该 commit。
- 夹具 SHA-256（最终复跑）：`E39F1BF698F6F8DE01D40080A8BD809C2A5DFE0ADCC0DF7114E52B2C62D4C768`
- 环境：Windows，观察到 `Python 3.12.13`。
- 方法：`contract-first composition challenge`。受测行为由用户可观察合同定义，不以代码实现、局部单元测试或报告自述定义。

## 预先封存的场景和判据

| 场景 | 局部合理之处 | 组合违约条件 | 修正版判据 |
|---|---|---|---|
| `currency-boundary` | 前端发送小数元；支付边界的单元测试接收整数分 | `12.34` 元必须扣 `1234` 分，缺陷实现扣 `12` 分 | 正确实现扣 `1234` 分 |
| `durability-ack` | 队列接收返回成功；正常 worker 能写入 | 数据库提交失败时不能返回 `saved`；若返回 `saved`，随后读取必须得到内容 | 修正版在提交失败时返回 `error` |
| `retry-idempotency` | 网络在扣款前失败时重试一次可以恢复 | 扣款已发生但响应丢失时，同一 key 只能产生一次扣款 | 幂等网关重试返回原扣款，不产生第二笔 |

## 实际命令与输出

```text
python examples/composition-challenge/trial.py
```

```json
{
  "method": "contract-first composition challenge",
  "results": [
    {
      "name": "currency-boundary",
      "local_checks_pass": true,
      "buggy_contract_failed": true,
      "corrected_contract_passed": true,
      "finding": "frontend sends yuan while payment boundary requires cents"
    },
    {
      "name": "durability-ack",
      "local_checks_pass": true,
      "buggy_contract_failed": true,
      "corrected_contract_passed": true,
      "finding": "success is returned before the queued write is durable"
    },
    {
      "name": "retry-idempotency",
      "local_checks_pass": true,
      "buggy_contract_failed": true,
      "corrected_contract_passed": true,
      "finding": "retry repeats a charge after a response-loss timeout"
    }
  ],
  "summary": {
    "local_checks": true,
    "buggy_defects_detected": 3,
    "corrected_false_failures": 0
  }
}
```

## 结论

本轮在三个预先定义且确实触发的组合缺陷上，局部检查为 `3/3`，组合检查发现缺陷 `3/3`，正确实现误报 `0`。因此可以把该方法作为关键代码交付的候选治理步骤，并写入执行合同、治理试验和入口规则。

本轮没有测：真实外部支付、真实队列／数据库、并发竞态、生产配置、未知缺陷发现率、不同模型是否实际采用规则，也没有证明规则能覆盖所有组合错误。后续真实漏检应保存复现条件，再补为回归场景。
