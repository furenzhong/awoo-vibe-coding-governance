# Examples / 示例

These files are fictional shapes, not runnable tasks or evidence of success. Do not move them unchanged into a project's task directory. Replace every placeholder with actual observations; do not fabricate successful checks.

这些文件只展示格式。全零 / 全一 SHA、会话、路径和验收者均为占位，不是有效提交、任务或成功证据。必须替换成实际值，checker 会拒绝不存在的提交。

- [adoption-mapping.json](adoption-mapping.json): reuse a project's existing documents; replace paths before applying.
- [task.example.json](task.example.json): a task starts as planned; add its receipt path when delivery exists.
- [context/](context/README.md): an old delivery arrives while a correction is still pending; separate coordinator/executor checkpoints and honest evidence gaps.
- [receipt.example.json](receipt.example.json): shows delivery and acceptance fields together for reference. The executor supplies checks and result_revision; only a real review supplies verified_by and verification_evidence. Leave these absent until review actually occurs.
- [composition-challenge/](composition-challenge/README.md): three isolated examples where local checks pass but a user-facing composition contract fails; includes a corrected implementation for false-positive control.

See [the harness contract](../docs/02_TECH/HARNESS_CONTRACT.md) for state changes and [the integration guide](../docs/03_DELIVERY/DELIVERY_PROJECT_INSTANTIATION_GUIDE_v1.md) for adoption.
