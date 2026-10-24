# AI 代码审查协议 trial v2 样本

这些是供维护者复制到临时目录的合成挑战材料，不连接网络、真实服务或生产数据。做盲测时只把所选 `projects/<case>`、协议、记录模板和正常任务说明交给审查者；将本 README 的判定依据与 `expected/` 留在评测者一侧。受测者不得收到样本标签或判定依据。

## 样本

| 样本 | 复制给审查者的目录 | 预期观察 |
|---|---|---|
| 组合缺陷 | `projects/composition-defect` | `tenant_cache.py` 的数据库过滤正确，但缓存键未包含 tenant；A 后 B 的序列会泄露 A 的结果 |
| 正确实现 | `projects/allowlisted-download` | `downloader.py` 接受 URL 输入，但仅允许声明的主机；未经验证就报“任意 URL 可访问内网”属于误报 |
| 无 AGENTS | `projects/no-agents` | 没有 `AGENTS.md`；审查者需基于产品合同和决定记录裁定权威依据，并记录选错会影响的结论 |

本地行为检查由仓库测试覆盖：`python -B -m unittest discover -s tests -p test_ai_code_review_trial.py -v`。这只能确认夹具的预置行为，不评价 AI 是否发现缺陷或正确裁定来源。
