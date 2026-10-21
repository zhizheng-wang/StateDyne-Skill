# API 接口实现依据

接口核对日期：2026-10-18。以下资料只支持接口形态，不证明本技能的认知增益；本次没有真实 API 调用。

- OpenAI Responses API：<https://developers.openai.com/api/reference/responses/overview>
- Structured outputs：<https://developers.openai.com/api/docs/guides/structured-outputs>
- Function calling：<https://developers.openai.com/api/docs/guides/function-calling>
- Reasoning protocol continuation：<https://developers.openai.com/api/docs/guides/reasoning>

采用官方 HTTPS 端点、显式模型、结构化文本 schema、工具调用回执与 `store: false`。工具续接所需的 reasoning 协议项仅在任务内存中保留，不持久收集私有推理。接口随服务可能变化；不兼容时明确失败，不静默替换模型或输出。
