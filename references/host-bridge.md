> **10.21 首轮执行优先**：`@StateDyne` 触发后，宿主若提供真实且获准的委派就必须实际派发并等待回执；调用入口不是只读取提示词。不能以时间、额度、题目短为由切断多路盲搜索。原生宿主不自动由 YAML 获得新委派权限，不能把待办伪称已运行。

# 原生宿主交接 · 10.13.0

这是**同一 StateDyne Skill 的实际可用宿主交接协议，不是另一档认知能力或必需后端**。这是实际交接协议，不是“在一段回答中扮演几个专家”。原生受控执行依赖宿主支持 Python、读取本地任务以及真正的独立模型上下文；如果已有可用且已授权的委派能力，开放任务应先实际使用，不等待模型凭主观“够简单了”跳过。没有可用独立工作者就按 [统一运行](runtime.md) 完成相同的认知任务，仅如实说明工具边界；不能伪造工作者回执，也不能因此降格为浅层分析。

## 原材料边界

把当前任务及用户允许使用的事实写到技能目录外的 UTF-8 文件。尊重“仅用本轮、不参考其他对话”等范围。不得把候选答案、其他工作者诊断、审计答案或私有推理混入原始材料。素材可分文件登记，独立工作者看到材料目录后自行读取；不能把多个文件偷偷裁成只有首段。

运行 `scripts/run_statedyne.py start --backend native ...`。读取待执行任务的 `request.json`，它包含 `id`、`role`、`instructions`、`inputs`、严格 `schema`、`input_sha256`。任务文件是控制器生成的不可变输入，禁止自行改写。

## 实际派发

每项任务调用宿主真正的独立工作者。使用其中 `instructions` 与 `inputs`，要求返回符合 `schema` 的可观察工作产物。不要复制控制者整段对话历史。初始生成、初始重构、反差桥接、原材料盲挑战尤其不能看到兄弟分支或既有主稿。最终审稿与写作者必须是不同的工作者调用；同模型不同会话可用，但其判断仍可能相关。

若宿主委派工具默认继承父对话、无法关掉继承，则不能把它登记为独立上下文；本版受控放行要求不成立，应使用便携模式。角色命名和两个不同文本文件都不是独立性的证据。

实际宿主引用可能是 worker ID、session ID 或工具调用 ID。必须记录真实值，不可编造 `reviewer-1` 当作回执。本地程序验证声明、不同引用与数据边界，不具有访问宿主内部日志或证明宿主没有继承隐含上下文的能力。

## 工具取得资料

工作者只能按授权读取登记资料。使用控制器工具桥会保存具体可见段落：

```bash
python scripts/run_statedyne.py tool --workdir ../statedyne-run --job J0001 --name list_materials --args '{}'
python scripts/run_statedyne.py tool --workdir ../statedyne-run --job J0001 --name read_material --args '{"source_id":"S2","start":0,"length":12000}'
python scripts/run_statedyne.py tool --workdir ../statedyne-run --job J0001 --name search_materials --args '{"query":"shared"}'
```

`read_material` 的索引是从零开始的字符位置，单次最多 20000 字符；有截断时跟随 `next_start`。`search_materials` 是本地字面匹配，不冒充语义检索或互联网搜索。输出必须确实交给请求它的工作者；原生模式对这一步仍依赖宿主诚实交接。不得让另一个工作者“代读”后伪称本工作者已读取。

宿主另有获授权外部资料工具时，可以取得资料并以真实来源说明登记为新材料，再重新建立包含该材料的任务。不能把网页存在当成已经读过；在授权宿主中实际取得的公网资料可使用 `add-evidence --workdir ... --source-file ... --url https://原始来源 --label "真实标题"` 录入；它不会联网、不会验证URL内容，记录的外部内容必须确实由工作者取得，来源的支持强度仍由语义审核判断。

## 提交与接续

将实际返回的 JSON 保存在工作目录外或对应任务的独立输出文件中。以下大写变量是实际值占位，不是可伪造的记录：

```bash
python scripts/run_statedyne.py submit --workdir ../statedyne-run --job J0001 --output-file actual-worker-output.json --input-sha EXACT_REQUEST_SHA --worker-ref ACTUAL_HOST_CALL_ID --actual-model ACTUAL_HOST_MODEL --independent-context
python scripts/run_statedyne.py advance --workdir ../statedyne-run
```

只有确实隔离才添加 `--independent-context`。控制器会等待所有同批工作，不用主分支裁决是否让另一分支进入；产物不合格则停在可诊断失败，而不是吞掉该分支。后续不断执行真实待办，直到 `done`、`blocked` 或仍等待外部信息。

最终放行受来源、全候选处置、信息义务、确切稿件、审核版本与独立回执约束。原材料盲挑战的发现必须先重新进入调度，不能跳到“审核无问题”。审稿失败按具体事项生成修复任务，新稿重新审核。

## 用户反馈

用户答复问题后使用 `update` 加入其真实原话，保留范围与不确定性。程序重新打开模型空间，并保留前轮产物。声明被替换来源的依赖自动失效，未声明依赖仍由生成与审核发现。用户只是说“下一步”时传入阶段目标，不要删除前轮事实；可用 `--scope points`、`actions`、`plan` 明确只交付所需阶段。

任务版本变化后，不提交旧 pending 任务的结果。失败重试只修正可观察问题；不得把未公开答案或兄弟诊断塞进盲任务的重试理由。若必须使用那些材料，就把它如实改成知情工作，不再计为盲发现。

## 首轮原料账本、盲挑战与独立重审

首次同批创建十份 `request.json`：`frame`、`system_map`、`goal_scout`、`selection_scout`、`relation_scout`、`discovery`、`reframe`、`contrast_probe`、`environment_scout`、`blind_challenge`。每份均应由**真正隔离的工作者**看到未经别的解释裁剪的原始材料。`frame` 使用 `frame` schema，必须提供真实 `source_id` 与原文逐字 `quote`；不存在来源的说法不能成为焦点。

上述十份工件完成后，先运行**独立增量负对照**：重复同一候选而没有具体无增量解释的工作者不算一次有效的模型外发现；该检测只比较可见字符串和后果，不能证明语义深度。负对照失败需明确排查和重试，不以十个回执直接放行。上述十份工件全部接收以后才运行 `entry_review`，但 **blind_challenge 和其余分支已经同批并行完成**，不是额外串行等待。该审核拿到焦点账本和全部候选，对每个 focal ID 回传 `coverage`，含状态、引用的候选 ID、真实桥梁、原料未报告的预测及可取得的判别信息。若审核发现原映射漏掉的重要现象，可新增带原文引用的 `new_foci`，并同轮标为 open/partial 触发补建。

`entry_review` 返回 `reopen` 后，控制器派发 `entry_repair`；补建工件先入池，**必须另开新的独立 `entry_review`**。如果从 partial/open 改称 explained，程序要求引用这次真实修复中新增的 claim，而不是换一段说法继续使用旧 claim。默认最多两次重新补建，可用 `--max-entry-repairs` 调整。仍无证据时可以交 provisional 并明确未知，不能宣称已经找出完整原因。

最终 `compose` 的 `focus_dispositions` 必须对应所有焦点、含实际出现在正文中的处理文字；`audit.examined_focus_ids` 不能遗漏。程序无法验证所有语义是否正确，保留真实审稿和反例检验的责任。

用 `trace --workdir ...` 检查实际角色、worker/session 引用、声称的独立性、时间、模型和输出身份。如果看到的是等待任务或只有模拟替身，就不能把“耗时长”说成完成了独立认知流程。

## 并行探索的实际交接

调度者返回 `search_plan`，可以安排多项互不需要对方新结果的操作。控制器从同一旧版 `current_view` 创建对应 `request.json` 并在允许并发数内执行，**所有实际输出到齐后才合并**；若有一项等待宿主实际 worker，整个批次等待。非独立的改变/采用任务不允许与其它认知任务强行同批派发。系统记录每项真正尝试的 `opportunity_ids`，不能把一项提议或一个空字段说成已开展研究。


## 10.5：真实公网投递的区分

原生宿主允许网络搜索时，应在获得授权的宿主工具中自行查询并读取真实网页；可通过 `add-evidence` 把取得的实际原文与原 URL 导入本地状态。受控 OpenAI API 模式可以明确打开 `--web-search`（依赖模型/账号支持），其搜索行为与引用 URL 自动出现在工作回执和研究线索中，但**不能**因得到 URL 就造出与原文逐字一致的 quote。两项二次扫描只在实际的 `frontier_scout`、`evidence_scout` 回执被合并后视为完成；只有 Markdown 字样而无真实工具/工作者回执的流程仍然是便携模式。


## 10.25 原生跨轮接续
首轮现在同批派发十项独立原料工作，额外 `relation_scout` 基于与其余工作者相同的原文寻找不同生成关系，不能继承兄弟结论。`update --side-question` 用于用户不要求改变主任务/交付阶段、只想澄清的小问题；`continue --scope next` 承接上次正式审核的主阶段，不是支线的表面话题。用户新信息确实推翻了旧机制时必须重开受影响结果，不得为了复用冻结错误结论。控制器保存文字接续协议，宿主是否显示快捷入口由产品决定。
