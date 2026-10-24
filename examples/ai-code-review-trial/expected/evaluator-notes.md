# 评测者封存依据

此文件不提供给受测审查者。

1. `composition-defect`：构造两个租户各一行数据，先查询 A 再查询 B。第二次返回 A 数据，违反 README 合同。只看数据库过滤代码会漏掉缓存组合缺陷。
2. `allowlisted-download`：白名单为 `docs.example.invalid` 时，该主机 HTTPS URL 应通过；`127.0.0.1`、`docs.example.invalid.attacker.invalid`、HTTP、非 443 端口和格式错误端口应拒绝且不能让谓词异常退出。静态看到用户可提供 URL 不能单独证明 SSRF。
3. `no-agents`：README 是行为预期合同，DECISIONS 是实现约束；审查者应说明两者职责及冲突时的优先关系，并指出选错可能导致文件访问越权或误报实现偏离。

盲测须另记录独立复核是否隔离初审问题和结论、复核者/初审者的模型关系及委托链。样本公开后不再作为对新审查者的封存样本；后续盲测应改用独立构造的等价样本。
