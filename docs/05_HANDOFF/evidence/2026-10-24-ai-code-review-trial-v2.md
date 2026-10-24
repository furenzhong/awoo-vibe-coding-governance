# AI 代码审查治理自检 v2

## 基线与范围

- 基线提交：`a0603c3`（v1.7.0 candidate）；本证据对应其后的 v1.8.0 candidate 工作树，提交前以最终 diff 为准。
- 目标：修补治理项目自身的协议/模板/工具自检闭环。
- 保留：既有 6 步审查结构和 `observed`、`inferred`、`executed`、`adversarial`、`independently_reviewed` 证据等级。
- 独立性：首轮由一个未收到 expected 或初审结论的独立审查会话执行；其与初审者是否同一模型/委托链未知。

## 已执行的可复现检查

| 检查 | 命令 | 实际结果 | 证据范围 |
|---|---|---|---|
| 合成挑战样本行为 | `python -B -m unittest discover -s tests -p test_ai_code_review_trial.py -v` | 3 项通过 | 复现跨租户缓存缺陷；白名单下载拒绝不可信 host、scheme、port 和格式错误端口；无 AGENTS 样本保有合同与决定来源 |
| 新版记录结构接受 | `python -B -m unittest discover -s tests -p test_project_os.py -k code_review -v` | 2 项通过 | 完整记录接受；缺必需章节时报错 |
| 旧记录兼容及误识别 | `python -B -m unittest discover -s tests -p test_project_os.py -k legacy_review -v` | 1 项通过 | v1.7 记录只产生旧版 warning；普通 Markdown 不作为审查记录 |
| 完整回归 | `python -B -m unittest discover -s tests -v` | 117 项通过 | 含现有治理工具、上下文捕获、升级恢复和本轮审查结构/样本测试 |
| 本仓库结构 | `python scripts/project_os.py check --target . --json` | `ok: true`；0 errors、0 warnings；`kit_version: 1.8.0`；扫描到 0 份显式审查记录 | 本仓库通过基础结构检查；不是审查协议的 AI 行为验收 |

## 独立盲审观察与样本修正

可复制的合成材料位于 [`examples/ai-code-review-trial`](../../../examples/ai-code-review-trial/README.md)。三项场景为：已知组合缺陷、带主机白名单的正确下载实现、缺少 `AGENTS.md` 时的权威来源裁定。评测者须把 `expected/evaluator-notes.md` 与任务输入分开保管。

独立审查者只读了协议、模板和三个 case 目录，没有看到 expected 或初审结论。它复现了缓存样本的跨租户泄露并按租户隔离边界报 P1；对无 `AGENTS.md` 样本识别出 README 产品合同与 DECISIONS 实现约束的职责及优先关系，并把缺少实现的场景留为 unknown。独立审查者与初审者是否同一模型或委托链为 unknown。

对“正确实现”样本，首轮审查发现 `urlsplit` 遇到格式错误端口会抛出 `ValueError`，因此该样本原先存在一个未预置的异常路径缺陷。维护者据此把异常处理改为拒绝输入，并增加对应回归。原首轮结论保留为样本设计缺陷证据。第二个独立会话复查修订后的函数，对正常白名单 HTTPS、非白名单 host、HTTP/FTP、非默认端口和格式错误端口做了执行验证，未在该函数范围内报错或误报；DNS、重定向、TLS、真实下载与文件写入链路仍未测。两个复核会话与初审者是否同模型或同委托链均无法确认，均记 `unknown`。

当前能确认的是：独立审查发现并推动修复 1 个样本设计缺陷；预置组合缺陷实际复现；修订后的白名单判定样本通过限定范围的第二次独立复核；无 `AGENTS.md` 样本正确保留了未实现代码范围的 unknown。不能把限定函数测试等同完整 SSRF 安全结论。

样本公开后不再对已读过仓库内容的执行者构成封存盲测；后续轮次应换用未公开的新构造样本。独立审查者将缓存跨租户泄露按权限/租户隔离边界报为 P1，并说明单实例先处理不同租户的触发条件。当前没有第二位审查者对同一缺陷独立定级，P0/P1 一致性仍未验证。

## 变更边界

本轮没有扩展六步流程或把所有风险提示变成必填项。检查器只依据明确的 `record_type` 和 `template_version` 检查章节存在；它不检查表格是否填实、不验证证据真实性、不评估代码安全，也不把旧报告判为无效。结构检查遗漏或误报应按后续真实记录和独立挑战结果调整。
