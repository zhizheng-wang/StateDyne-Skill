> **10.13 独立结论承重审计**：重要判断必须区分事实来源、派生计算、关键口径和未经证实的桥接假设；比较强反例/竞争世界、时间截止与结论翻转条件。读取 `load_bearing_audit` 的重大挑战和实际已取得或未取得的证据；不因报告的叙事完整就放行，也不因此一律退回空洞谨慎。尚缺重要事实应进入取证/条件推演，不把用户私有经历或不可观察动机编成事实。对主要量化结论复算并明确假设。改变任务还需比较新的行动是否以无依据的价值/动机推断为前提。

> **10.13.0 兼容说明：以下是 9.x 旧格式工具的文档，不是本版默认执行契约。** 旧脚本原样保留；新运行器使用 [executor.md](executor.md) 所述状态和任务，不得交叉写入。只有明确维护旧格式时才加载本文。

# 受控认知产物契约

本契约按 runtime 的任务依赖与审计需要启用，不因 Python 存在就覆盖普通 @ 聊天。启用后完整读取并实际执行；按当前缺口建包，不机械执行固定轮数。脚本只核对可检查成果及版本，不记录完整隐藏思维，不生成内容、不调用模型、不发送外部消息。

## 调用

Python 3 标准库；所有路径相对独立任务目录 ROOT，禁止越界（含符号链接）。保留输入、证据、旧包与旧稿的独立文件，不覆盖已引用字节。

```text
python scripts/cognitive_work.py hash ROOT/input.txt
python scripts/cognitive_work.py input-hash ROOT/packet.json
python scripts/cognitive_work.py work-hash ROOT/packet.json
python scripts/cognitive_work.py transfer-hash ROOT/packet.json --challenge CHALLENGE_ID
python scripts/cognitive_work.py check packet.json --root ROOT --stage settle
python scripts/cognitive_work.py check packet.json --root ROOT --stage select
python scripts/cognitive_work.py check packet.json --root ROOT --stage plan
python scripts/cognitive_work.py finalize packet.json --root ROOT --receipt receipt.json
python scripts/cognitive_work.py verify receipt.json --root ROOT
```

中心解释开始支配后续工作前实际调用 check --stage settle；实际优先推荐前调用 check --stage select（不要求动作或完整方案）；完整动作/方案选择前调用 check --stage plan；准确出稿前执行 finalize、verify。check 无写入；stage 为 settle、select、plan、finalize，默认 settle。finalize 自动执行 finalize 检查并原子发布收据；verify 在交付前重查当前字节、稿件、节点和账本。退出 0 为通过，2 为拒绝；JSON 给出 blocker、return_to、affected_ids，以及 changed_ids、invalidated_ids、preserved_ids。settle 不代表事实已成立；候选可以进入条件预测与方案。分析及仅请求干预点均用 analysis 阶段，不强求动作。最终包不能单独证明上述 check 按时间顺序调用过；过程时序由真实宿主轨迹审计，脚本强制的是提交时的产物门禁。

## 一个 JSON 包

顶层字段：schema=1；task_id 非空字符串；revision 从 1 开始；phase="analysis" 或 "plan"；previous 首包为 null，此后为前一已提交包的文件引用；inputs、nodes、targets、acquisition 必填。finalize 另需 draft 文件引用、与 targets 完全相同的 draft_targets 和 final_review（见下）。所有文件引用为 {"path":"相对路径","sha256":"64位小写SHA-256"}。hash 命令计算原始字节哈希。

inputs 是非空数组，每项含文件引用字段及 id、status（observed/reported/inferred/unknown）、locator、precision。后两项保留原始位置和精度；不得把未报告补为否定。input-hash 对 inputs 的完整规范化 JSON 计算哈希，供挑战和重开绑定；先建 inputs，再计算该值。

acquisition={input_hash,source_scan,public_ids,user_ids,no_public_basis} 是本轮来源分流产物；source_scan 引用实际检查原材料所得的公开意义/来源与个体作用分流记录，不是完整思维链。两个 ID 数组分别恰覆盖所有 owner=public/user 的 information；公开项为空时 no_public_basis 说明为何没有有价值公开取得任务。input_hash 绑定当前输入。承重公开事实在定型前必须 answered 或有实际阻断证据的 blocked，不能以条件输出绕过未执行的取得工作；无关公开未知和用户独有未知仍局部处理。程序不能自动发现被遗漏的来源任务，便携模式与独立语义检查承担这项责任。

nodes 是数组，每项为 {"id":"唯一ID","kind":"下述类型","version":1,"depends_on":{"被引用ID":1},"data":{...}}。ID 用字母、数字、下划线、点、冒号或连字符。depends_on 是版本依赖 DAG；现实反馈放在 relation.data.feedback，不能错误转换成依赖环。targets 是本次实际完成的 relation/point/proposal/action/output ID 数组，至少一项；必须追溯到 relation。

各类 data 的必填成果如下。除明确数组、对象、枚举外均为非空短文本；不适用也说明理由，不能伪造内容填空。

- relation：status=candidate/established；prior_state、state_conditions、transformation、intermediate_result、result、scope、prediction、counterexample、unresolved；sources 为当前 input ID 数组；feedback={mode:present/not_applicable,description:文本}。established 另需 support 文件引用；它及 established output 不能把 candidate 依赖升级为成立。
- operation：depends_on 绑定相关 relation；target_result、unrepresented_difference、selected、strongest_alternative、choice_basis；delta_kind=added/weakened/excluded/reframed/none/stop；delta；updates 为所更新节点 ID 数组（允许空）；artifact 为实际工作产物引用。所有目标 relation 至少有一项完成操作；none/stop 可诚实通过，不强造增量。
- challenge：input_hash；mode=isolated_branch/serial_rebuild；raw_input_basis；artifact；findings 为非空数组，每项含唯一 id、claim、distinguishing_fact，以及 competing_representation 或 cross_surface_prediction。isolated_branch 另需 isolation_record 文件引用（实际宿主调用记录）。禁止 independent 标签；串行重建必须如实声明。
  challenge 另需 transfer，记录原始材料重建成果与迁移选择。outcome=candidate/no_useful 时保留 {outcome,artifact,source_surface,shared_relation,search_result,value_basis}；artifact 为实际搜索成果。candidate 还需 other_surface、prediction、discriminator、failure_boundary、finding_id；finding_id 必须进入本 challenge 的 findings，故对应 reception 也须处置。no_useful 表示实际尝试迁移后无有用结果，需真实搜索结果及理由。
  若按当前增益未选择迁移，outcome=not_selected，改用 {outcome,artifact,selected_operation,selection_basis,search_result,value_basis}：说明所选的原始材料重建/其他探索操作、为何它比迁移更适用、实际成果和价值判断。不要求假造另一表面或先做无价值迁移；原始材料挑战、具体 findings 和完整 reception 仍必需。字段存在不证明操作确实发生、无遗漏或预测有价值，这些由行为复核判断。
- reception：depends_on 绑定 challenge；challenge 为该 ID；dispositions 对该挑战所有 finding ID 各给一项，无多无少。每项含 decision=incorporated/excluded/conditional、basis、evidence 文件引用、affected_ids 数组、updated_versions={影响ID:当前版本}。后两者键集一致；affected_ids 只能指向 relation/information/point/proposal/action/output，禁止只改 operation/challenge/reception 流程记录；只有 excluded 允许 affected_ids 为空。接收必须落实到当前解释、问题、预测、点或动作版本，不能只附一份报告。
- information：owner=public/user；status=open/answered/blocked/ready/asked/deferred；question；required_for 为确实依赖答案才能完成的节点 ID 数组，可空；同时，任何节点以 depends_on 引用 information，都声明消费该信息前提。必要依赖取 required_for 与这些显式消费者的并集，再沿下游检查；空反向列表不能消除已有 DAG 前提。只有主题关联而不消费答案时，不写成该依赖边。answered/blocked 需 evidence 文件引用和 result；blocked 另需 attempt、constraint。公开事实只用 open/answered/blocked，另需 acquisition_kind=fact/meaning_location；意义未定位不能标成普通事实绕过其取得责任。用户 asked 需正整数 batch 和实际问句产物 evidence；当前相互独立的未答问题同一 batch。deferred 必须有 after 指向尚未回答的 user information、在 depends_on 引用该版本，并填 necessary_after 解释为何前答决定后问。用户独有未解信息只拒绝 required_for 及其下游目标；若该目标 status=candidate/conditional，可用 data.conditional_on={信息ID:{assumption,alternative,next_step}} 记录真实条件处理后继续，信息责任仍保留未解。承重公开项不能使用此出口跳过实际取得；有证据的真实阻断可支持候选/条件完成，不能支持依赖该答案的 established 完成；目标祖先链中依赖未解必要信息的关系与输出也不得标为 established，不能用条件输出遮蔽已成立前提。
  meaning_location 另需 lookup={outcome,attempts}；outcome=located/access_blocked/locator_unresolved。attempts 是按实际顺序的非空数组，每项含 route=literal/normalized/concept_relation/context_read、query_or_locator、basis、observation、evidence 文件引用和 result_kind=literal_only/incidental/candidate/verified_context/no_result/access_denied。保存实际工具输入及返回相关性，不保存完整隐藏思维。
  located 要求 information.status=answered、至少一项 verified_context，并有 referent、scope；来源只证明实际支持范围。access_blocked 要求 status=blocked、末项真实 access_denied 与 remaining_unknown；不能绕过权限。locator_unresolved 要求 status=blocked、实际 concept_relation 路线、末项非 access_denied，并有 remaining_unknown、stop_basis、minimum_locator_question。一次直接关系查询可以够用，无固定次数；只重复字面查询不能作为定位完成。沿用 blocked 的 evidence/result/attempt/constraint。工具仅核验声明的转换及文件，不能判定查询真的去锚、来源足够相关、任务分类正确或已穷尽；这些仍须真实轨迹和语义复核。
- point：depends_on 至少一个 relation；changed_state、mechanism、adoption、result、comparison、scope。
- proposal：depends_on 至少一个 relation 或 point；actor、situation、input、transformation、first_deliverable、use_path、expected_result、assumptions、limits、artifact 文件引用；feasibility=conditional/supported，supported 另需 support 文件引用。构造给定条件下的具体成果，不把可行性当已确认；可独立作为 analysis 目标，不强迫全计划。
- action：depends_on 至少一个 point；operation、adoption、result、comparison；selection={chosen,alternatives,basis,switch_condition,mode}。chosen 是当前 proposal ID，alternatives 是其他当前 proposal ID 数组，必须在 depends_on 绑定所选及替代版本；空替代需 no_alternative_basis，不设候选数量。mode=conditional/commit；commit 需所选 proposal.feasibility=supported，且其依赖范围的必要信息已 answered。条件构造、候选比较及真实承诺分开。plan 阶段目标链须包含 action；动作映射不等于语义上已找对点。
- output：claim；status=conditional/established；depends_on 引用依据。可用于说明、预测等成果。

## 迁移接收必须完成信息转换

challenge.transfer.outcome=candidate 时，与 transfer.finding_id 对应的 disposition 另需 acquisition={mode,basis}。mode=grounded/no_gain 时需 evidence 文件引用，分别说明已有材料足够或取得无增益；不强迫产生私人经历问题。mode=information 时需 information_id，该信息必须进入 reception 的 affected_ids 和 updated_versions。

对应 information.data 必须含 origin={challenge,challenge_version,finding_id,transfer_sha256}，精确绑定当前挑战及整个 transfer 的规范化摘要；使用 transfer-hash 命令取得。另需 discrimination={if_present,if_absent}，说明同一关系的区分条件成立与不成立各怎样改变结论。这是来源绑定，不要求将接收回指误做依赖环。信息不能仍 open。

公共信息必须 answered 或有证据 blocked；不改成私人追问代替可得公开核查。用户信息可 answered、ready、asked、blocked、deferred；ready 表示本轮准备提出，asked 表示先前真实问过，均用同批独立问题原则。ready 及带 origin 的 asked 需 delivery={mode,text}，text 必须等于 question。ready 的 mode=current_draft，finalize 核验该确切问句出现在确切 draft；asked 的 mode=prior_asked，另需 record 文件引用且真实记录包含该问句。旧问未答保留未知，不强迫重问。真实阻断和前答依赖延后仍用原限制；条件成果只完成覆盖范围。记录、摘要和文字相等不能证明问句真的保持共享关系与判别力，仍须语义复核。

## 意义定位返回线索的接收

meaning_location 的 lookup 另需 lead_scan 文件引用和 leads 数组。只登记承重且不同的返回关系，合并重复与无关结果；空数组需 no_material_leads 的实际依据。程序不能发现遗漏的线索、判定相关性或认证工具执行。

每个 lead 含唯一 id、source_attempt（从1开始的实际查询序号）、source_locator、relation、relevance、disposition、basis、evidence 文件引用，followup_attempts 是晚于来源的实际查询序号数组，默认空。disposition：

- checked：实际后续查询及 result，核查支持范围。
- excluded：有据排除，无强制额外检索。
- no_gain：具体无信息增益依据，可停止。
- blocked：constraint、blockage_kind=access/safety，及 safe_alternative={decision:attempted/unavailable/no_gain,basis}。access 需来源或后续有实际 access_denied；safety 不要求先访问不适宜来源。attempted 需实际后续查询，其余说明不可得/无增益。
- conditional：remaining_unknown、next_condition、stop_basis，以及实际后续查询或具体 constraint，保留未确证关系。

返回 result_kind=candidate 的 attempt 需有对应 lead 或 nonmaterial_basis，不能仅凭做过 concept_relation 就关闭候选线索。排除来源不等于排除其提示的关系；适宜安全替代可以核查相同关系。弱来源不能直接支持成立。该门槛不要求跟每条结果、打开不适宜站点、命中特定词义或固定查询次数；locator_unresolved 在有据处置后仍是合法诚实结果。

## 比较证据先于实际推荐

select、plan、finalize 需顶层 decision_scope={targets:{目标ID:角色},basis,artifact}，角色恰覆盖 targets：analysis/candidate/recommendation/user_directed。分析与未排序候选不强求推荐；目标祖先中含 action 时只能 recommendation 或 user_directed。实际推荐也可能是 analysis 阶段的 output，不能靠没有 action 跳过本门槛。程序不能从正文识别漏报的推荐；角色真实性由真实回答复核。

user_directed 目标 data.direction={input_id,instruction} 引用原输入ID和其中出现的确切指令。它只表明执行用户指定选择，不认证指令含义或免除事实/安全责任。无此来源不能以该角色替代择优。

recommendation 目标 data.selection 含 chosen、alternatives、basis、switch_condition、mode=conditional/commit；与 action 相同，绑定当前 proposal 依赖，空替代需 no_alternative_basis。commit 仍需已支持的可行性且无未解必要信息。另需 comparison={artifact,criterion,preference,scope,candidate_versions,premises}；candidate_versions 恰绑定所选及替代的当前版本，premises 非空，不规定数量。

每个承重比较前提含唯一 id、claim、if_false、basis、candidate_ids、route、evidence。candidate_ids 为本次比较候选的非空子集，所有前提合起来必须涵盖 chosen；不能只用备选研究充当首选依据。route：

- information：information_id 必须是推荐目标直接依赖的当前 information。另有 reception={relevance,relevance_basis,effect_on_preference,remaining_limits}；relevance=direct/partial/irrelevant/contradictory/unavailable。公开项须 answered 或有证据 blocked；answered 仅接受 direct/contradictory，部分或无关研究不能宣称关闭该比较前提。未答/阻断另需 condition、next_step，遵守已有条件输出与信息责任。查询不能认证相关性，自述直接相关也可能是错的。
- existing：已有充分且可复用依据，另有 source_locator、support_scope。
- derivation：从已有材料推导，另有 derivation、assumptions，不伪造外部事实。
- no_gain/not_material：另有 why_no_acquisition、boundary，说明为何继续取得无增益或该低影响差异不承重。仍需实际依据，不用空标签跳过已识别可得公共任务。

比较工件随当前节点/稿件绑定；候选、前提或排序变化须更新成果与版本、重新评阅。它要求命题→取得/已有依据→相关性接收→选择变化的交接，不要求每个建议额外联网、每个候选同量研究、私人付款证明或指定竞争者。结构检查不判断比较已穷尽、任务分类诚实或证据真能支持排序。

## 更新、局部返工与提交

每个包 revision 增一，previous 绑定前一包精确字节。允许经过有效 settle 检查的中间工作包，不要求提前 finalize。旧节点内容（含依赖）变化时 version 恰加一；不变则保持；新节点从 1 开始。旧依赖拒绝，修订节点与下游列入 invalidated_ids，无关节点保留。每个历史包也会重新检查 settle 门槛；失败候选另存为草稿，修复后再加入有效包链。

inputs 任一字段变化都强制 scope_discovery，不能靠 central=false 绕过：顶层新增 reopen={input_hash,assessed_ids,affected_ids,basis,evidence}。assessed_ids 必须覆盖新旧包全部 relation/output/point/proposal/action/information ID；发现新范围而非仅沿旧图传播。affected_ids 指当前受影响节点，它们必须更新版本；即使结论不变，也在 data 增加本次重验成果后增版。新输入绑定的新 challenge 和相应 reception 必须有效。覆盖和理由的真实性仍需语义评阅。

删除旧节点须在顶层 retirements={旧ID:{reason:"superseded"或"value_ended",explanation:文本,evidence:文件引用}} 留下材料与理由，不能静默丢弃未决问题。

finalize 的默认账本是 ROOT/.cognitive-ledger.json，可用 --ledger 换名；每个任务独立账本。它检查当前账本头位于已验证祖先链，且新 revision 更大，拒绝重复提交及旧分叉。新账本允许有效的多包链从 revision=1 起步。用排他目录锁和临时文件原子发布；收据不可覆盖。崩溃遗留锁须核实无写者后人工处理，不能盲删重试。收据先于账本提交；中断时未提交收据 verify 拒绝，保留故障证据后换收据名重试。文件系统不支持原子硬链接则 finalize 失败，不能降级成已批准。Windows 不依赖 flock；不代表旧 task_state.py 获得 Windows 支持。

final_review={artifact,draft_sha256,input_hash,work_hash,mode,outside_model_attempt,limits,verdict,blockers,return_to}：artifact 为真实最终评阅产物；draft_sha256、input_hash 绑定当前稿件与原始输入；work_hash 用 work-hash 命令对整个包除 final_review 外的规范化 JSON 计算，绑定全部认知节点、版本、范围、阶段及沿革。先完成工作包，再实际评阅并记录该值；工作变化必须重新评阅，不能复用旧绑定。摘要不认证评阅真实发生；mode=self/peer，peer 另需 execution_record 文件引用；outside_model_attempt 简记评阅如何寻找现稿未表示关系，limits 如实声明限制；verdict=ready/rework/needs_info。只准许 ready 且 blockers=[]、return_to=[] 的对应范围稿件。自填 ready 与 peer 字符串不认证质量或身份，仍需真实评阅。

## 边界与工程样例

程序拒绝结构、顺序、绑定和版本错误；不证明来源真实、关系实质、最强替代、遗漏已穷尽、心理采用、语义正确或代理身份。isolation_record 记录实际隔离证据，但脚本不认证宿主。相同模型的隔离上下文也不是独立训练模型。它控制自己的 finalize，不能拦截宿主直接发送；交付应记录本次 exact draft SHA-256，并实际使用 verify。字节核验不是行为验收。

完整无私有材料的合成生成器与负向测试留在包外工程记录中，不计入常驻读取。结构完整但空泛的样例可通过，工程测试明确保留这项语义失败，不能称为程序识别了它。无脚本时回到同一方法的便携协议，如实声明无程序门禁。
