# POC KB 目录规范

POC 阶段负责决定知识库目录 schema，kb-builder 只按 schema 执行目录创建、QA 归类和上传。

## 优先级

1. 用户当前消息明确指定的目录层级。
2. 客户已有知识库目录或上传文件中的目录字段。
3. POC 标准目录模板。

用户或上游已经提供目录 schema 时，必须把该 schema 传给 kb-builder，并要求 kb-builder 严格按输入结构执行。schema 定义了根节点和层级时，不得在其外额外增加 POC 标准目录，也不得擅自重排层级。

## POC 标准目录模板

仅当用户没有指定目录 schema、也没有已有目录可复用时，才使用：

- Product Introduction
- Brand Policy
- Help Center（仅发现帮助中心/FAQ/文档站时创建）
- Pending Assignment

使用标准模板时，这 4 个一级目录是稳定路径标识，保持英文；其下业务目录使用目标业务语言，品牌名、型号和其他专有名词保留原文。
