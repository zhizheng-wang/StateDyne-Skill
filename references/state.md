> **10.12.0 兼容说明：以下是 9.x 旧格式工具的文档，不是本版默认执行契约。** 旧脚本原样保留；新运行器使用 [executor.md](executor.md) 所述状态和任务，不得交叉写入。只有明确维护旧格式时才加载本文。

# 可运行的本地任务状态

## 轻量回合接续（Windows、Linux、macOS）

多轮开放任务先按 runtime 保留一份短交接成果：主目标、当前工作、未完成果、插问返回位置、仍重要的候选与未答问题。下面的 `check_work.py checkpoint` 可检查这些**已经登记**的内容是否被静默丢弃，使用 Python 3.8+ 标准库，无需 POSIX 锁。它与下文较重的依赖/动作账本相互独立；普通对话也可以在可用上下文中保留同样的成果，不必为了脚本创建第二份长报告。

每轮使用新的材料文件、状态文件和检查点文件，放在技能包之外。合成示例 `turn-1-state.json`：

```json
{
  "task": {
    "goal": "找出合成系统延迟上升的原因并选择处理办法",
    "current": "比较当前解释并取得会改变选择的信息",
    "unfinished": ["尚需选择实际处理办法"],
    "return_to": null
  },
  "candidates": [
    {"id": "input-pressure", "summary": "输入增长可能超过当前处理能力；需与下游阻塞比较", "status": "open"},
    {"id": "downstream-block", "summary": "下游等待可能使处理能力下降；输入不增长也可能积压", "status": "open"}
  ],
  "questions": [
    {"id": "input-time", "summary": "输入量何时发生变化；与延迟先后关系会改变解释和处置", "status": "open"},
    {"id": "wait-time", "summary": "下游等待何时发生变化；与延迟先后关系会改变解释和处置", "status": "open"}
  ]
}
```

从工作目录运行；将 `SKILL` 替换成技能目录的绝对路径。`turn-1.md` 应含本轮实际材料及确切答复；示例材料为合成记录，不是真实测量。

```text
python SKILL/scripts/check_work.py checkpoint --state turn-1-state.json --input dialogue=turn-1.md --out turn-1-checkpoint.json
python SKILL/scripts/check_work.py checkpoint --state turn-2-state.json --input dialogue=turn-2.md --previous turn-1-checkpoint.json --out turn-2-checkpoint.json
python SKILL/scripts/check_work.py check-checkpoint --checkpoint turn-2-checkpoint.json
```

第二轮继承仍重要的候选、未答问题与真实未完工作。候选状态为 `open/closed`，问题状态为 `open/answered/closed`；未回答继续为 `open`，用户不记得不等于得到答案。每个问题 ID 按 runtime 对应一个可独立回答的缺口；前台分组不合并它们的已答状态。例如只得到输入时间，`input-time` 可以已答，`wait-time` 仍开放。已答项的 `summary` 保留实际答案及材料位置，不以“未提到”代替答案。更新发生在解释综合之前，审核读取更新后的这份记录；新问题在交付时已登记。问题的作用和候选的不同预测直接写在 `summary`，不记录隐藏思维链。`return_to` 为具体返回位置，没有插问则为 `null`。`unfinished` 可为空；`goal/current` 保持实际结果与当前工作，不写固定阶段口号。

已有条目的 `summary/status` 或任务内容变化时，在该条目/任务添加 `change`。新材料支持改变时使用：

```json
{"reason":"新的合成记录回答了时间关系，需重排候选","evidence":[{"input":"dialogue","at":"第 2 轮用户提供的时间记录"}]}
```

`input` 必须指向本轮 `--input` 绑定的实际文件别名，`at` 是可定位位置。至少一项所指材料的 SHA-256 须不同于上一轮所绑定材料；给同一旧文件换别名不算新依据。任务变化也可引用本轮真实工作或答复中已经完成的成果。脚本只核对声明及文件版本，**不检查定位真的存在、内容是否支持结论、是否确实更新了所有重要解释**。

候选或问题随目标改变、已被覆盖等原因失去继续保留的价值时，改为 `closed`，用 `change` 说明原因及价值为何结束：

```json
{"reason":"当前目标已改变，不再据此选择","value_ended":"此差别只影响已取消的交付，对剩余目标没有影响"}
```

`value_ended` 只能用于关闭条目或修订任务，不能代替答案或为仍开放的解释改判提供证据。尚重要的旧 `open` 项必须出现在下一轮；明确关闭或回答后可以在更晚轮省略，历史仍在旧检查点。原样保留的条目可以直接复制，也可去掉其旧 `change`；重开、改写或新登记已关闭/已回答条目仍需相应依据。这里的稳定 ID 是同一条目的标识，不能通过改名、新建初始链或篡改状态绕过实质接续。

每个检查点绑定自己的状态源文件、材料路径/字节数/SHA-256、上一轮检查点字节版本和连续轮次。新检查点拒绝覆盖已有文件；复核会追溯整条链，旧材料或状态被改写则失败。保存失败或中断留下的文件不能当成功记录，另用新文件名并复核；工具不提供跨进程唯一主线、自动备份或宿主持久化。并行分支可共享前轮，负责人综合后明确选择下一轮，不能把两个分支都假定为唯一最新状态。

结果中的 `continuity: registered_items_only` 表示只检查已登记条目；`source_locations: declared_not_verified`、`semantic_quality: not_checked` 表示仍需读取实际对话核对。漏登记的候选、虚假的理由、问题是否集中问出、洞察与创新、真实采用和长期效果均不由脚本认证。没有文件工具时复用 runtime 的短交接成果，如实说明无法提供此版本校验，不冒称自动记忆。

目录：适用边界；最小演练；更正与迟到分支；动作与恢复；字段与检查结果。

## 适用边界

长任务、分支交接、中心更正或恢复执行且宿主可运行脚本时，用 `scripts/task_state.py` 保存实际需要的任务约定、依赖、成果和动作记录。普通短答不为用脚本而建表；不要求每个任务具备全部节点类型，也不新增用户审批。`kind=action` 只是分析中的动作节点；有外部副作用的操作另用动作台账。

运行环境为 Python 3.8+、支持 POSIX `flock` 和同目录原子替换的单机本地文件系统。脚本提供合作进程之间的互斥、预期版本检查、原子 JSON 写入和有限状态核对。它不是持久存储后端、ChatGPT 发送钩子、实际执行器或分布式多写者系统；不支持把网络盘、多台机器或同一文件的硬链接别名当作等价运行环境。绕过脚本改文件的进程不受锁约束。

选择获准位置保存真实任务；只有宿主确已保存到可持续访问的位置，才声称可跨会话恢复。脚本不会上传、备份、设定后台任务或自动恢复外部操作。状态只存可审查材料、简短依据和成果，不存私有思维链。保存失败如实报告；没有宿主脚本能力时按 runtime 保留普通恢复记录，不冒充有硬检查。

runtime 的简洁任务栈可存在普通 task/work 中：主目标、阶段、完成与欠交、下一步、插问影响及返回位置，不必扩充脚本字段。reality 的主解释、保留解释、弱线索、已放下与暂不相关是语义地位，可写在既有节点 body/basis 或成果记录；不是新增 kind，也不等同支持充分。仅在实际需要时声明依赖和更新条件，不把后台转成第二份谨慎文章。结构工具保持原职责，不自动判定解释优先级、下游价值或生成质量。

## 最小演练

以下命令从本技能目录执行；数据全部为合成演练，目录为可删除的临时目录。真实任务替换任务内容和位置。`--state` 及脚本本身先定位为绝对路径；**其他文件参数**（`--data` 和成果 `path`）均按状态文件所在目录解析，或使用绝对路径，改变工作目录不改变其含义。

```bash
STATE_TOOL="$PWD/scripts/task_state.py"
TASK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/statedyne-demo.XXXXXX")"
STATE_FILE="$TASK_DIR/state.json"

python3 "$STATE_TOOL" --state "$STATE_FILE" init <<'JSON'
{"request":"比较缓解队列积压的方案并交付试验建议","goal":"形成可复核的下一步试验","constraints":["合成演练，不执行真实外部动作"]}
JSON

python3 "$STATE_TOOL" --state "$STATE_FILE" put --expect-revision 1 <<'JSON'
{"id":"finding","expected_revision":0,"kind":"fact","body":"合成观察：流量上升时队列增长","basis":["合成演练材料，不是实测证据"]}
JSON

python3 "$STATE_TOOL" --state "$STATE_FILE" put --expect-revision 2 <<'JSON'
{"id":"idea","expected_revision":0,"kind":"candidate","body":"探索改变批大小是否打开另一条路径"}
JSON

python3 "$STATE_TOOL" --state "$STATE_FILE" put --expect-revision 3 <<'JSON'
{"id":"choice","expected_revision":0,"kind":"adopted","body":"演练建议：用短时限流试验区分输入压力的作用","depends_on":{"finding":1,"@task":1}}
JSON

cat > "$TASK_DIR/answer.md" <<'TEXT'
# 建议
合成演练：先做短时限流试验，观察队列变化。此处不是实际任务结论。
TEXT

python3 "$STATE_TOOL" --state "$STATE_FILE" put --expect-revision 4 <<'JSON'
{"id":"delivery","expected_revision":0,"kind":"obligation","body":"交付可复核的试验建议","use":"support","depends_on":{"choice":1},"artifacts":[{"path":"answer.md","visible_at":"建议章节"}]}
JSON

python3 "$STATE_TOOL" --state "$STATE_FILE" check
python3 "$STATE_TOOL" --state "$STATE_FILE" show
```

此时状态总版本为 5，各节点版本为 1。`idea` 没有证据仍被保留；`delivery` 记录实际文件 SHA-256 和声明的可见位置。`check` 的 `ok: true` 仅表示本次有限检查没有发现错误，不能把合成依据变成真实依据，不能证明建议充分，也不表示用户已经收到文件。

`--data node.json` 可替代标准输入；该文件从 `STATE_FILE` 所在目录读取。所有写入（初始化除外）同时需要最新状态 `--expect-revision`；节点和动作还需要 JSON 中的 `expected_revision`，新记录填 0，已有记录填自身当前版本。不要只改版本数字来掩盖没有重读、没有重算的分支。

## 更正、历史与迟到分支

`depends_on` 记录本项判断**作为成立前提采用**的节点及所用版本。节点还可用 `recompute_on` 记录所研究、检验或条件推演的对象：其内容改变需要重算本项，但不据此认定它为真。两者都用 `{"节点ID":所用版本}`，涉及当前任务可引用 `@task`；一般出处和简短理由写入 `basis`。不能把实际采用的前提挪到 `recompute_on` 规避探索保护，也不把所有提及都登记为依赖。脚本不验证这些语义声明。

`put` 完整替换一个节点的当前内容，未提供的依据、两类依赖和成果列表变为空；`central` 默认沿用原标记。旧状态和归档缺少 `recompute_on` 时按空字典处理，无需迁移；原有 `depends_on` 含义和保护继续有效。替换、撤回和递归置为 `stale` 前，旧节点完整记录保留于 `archive.nodes`；当前任务变化前保留于 `archive.task`，`original_task` 始终保留最初请求、目标和约束。归档保留文字、元数据与哈希，**不保存被覆盖的外部文件内容**；需要旧成果文件时另存版本。

两类依赖共同参与版本、新鲜度、环与失效传播检查：前提或对象变化均递归标记已声明下游，连带增加这些节点自身版本；无关节点不动。重算时引用仍有效的当前版本，不能引用较新但仍 `stale` / `invalid` 的节点绕过检查。同一节点同时出现在两类依赖时版本必须一致，且仍受成立前提的保护约束。`invalidate` 以 `id`、`expected_revision`、`reason` 撤回节点；`task` 接收与 `init` 相同的三个字段，更新当前任务、增加任务版本并使 `@task` 的两类已声明下游过时。

下列例子接续初次演练：

```bash
python3 "$STATE_TOOL" --state "$STATE_FILE" put --expect-revision 5 <<'JSON'
{"id":"finding","expected_revision":1,"kind":"fact","central":true,"body":"合成更正：队列主要由下游阻塞造成","basis":["新的合成材料；真实任务应读取真实来源"]}
JSON

# 预期失败（退出码 2）：状态总版本虽对，所用前提版本已旧；不会写入。
python3 "$STATE_TOOL" --state "$STATE_FILE" put --expect-revision 6 <<'JSON'
{"id":"late","expected_revision":0,"kind":"inference","body":"旧分支结论","depends_on":{"finding":1}}
JSON

python3 "$STATE_TOOL" --state "$STATE_FILE" put --expect-revision 6 <<'JSON'
{"id":"choice","expected_revision":2,"kind":"adopted","body":"演练修订：先检查下游阻塞，用恢复试验识别作用","depends_on":{"finding":2,"@task":1}}
JSON

cat > "$TASK_DIR/answer.md" <<'TEXT'
# 建议
合成演练修订：先检查下游阻塞，再用恢复试验观察队列变化。
TEXT

python3 "$STATE_TOOL" --state "$STATE_FILE" put --expect-revision 7 <<'JSON'
{"id":"delivery","expected_revision":2,"kind":"obligation","body":"交付修订后的试验建议","use":"support","depends_on":{"choice":3},"artifacts":[{"path":"answer.md","visible_at":"建议章节"}]}
JSON

python3 "$STATE_TOOL" --state "$STATE_FILE" review-impact --expect-revision 8 <<'JSON'
{"scope":"演练中重新检查目标、边界、其他候选及未登记关系","findings":"演练记录：建议及成果已修订，批大小候选保留探索地位","checked_nodes":{"finding":2,"choice":3,"delivery":3,"idea":1},"unresolved":[]}
JSON

python3 "$STATE_TOOL" --state "$STATE_FILE" check
```

中心节点的新增、更改或撤回，以及当前任务变化，会挂起全局影响检查。脚本无法发现漏画的关系；`review-impact` 只保存人或代理实际检查的范围、发现、检查到的版本与未决项。`unresolved` 非空则继续待审；为空才关闭本次待审标记。该操作不自动清除 `stale`，也不证明扩大检查真正充分。新中心变化会再次挂起；旧状态版本的审查记录不能关闭较新的变化。

状态总版本冲突时先 `show`。如果只是别的分支新增了无关记录，确认自己的依赖与目标节点版本仍有效后，可以用新的总版本提交原计算；不要全盘重算。所声明依赖过时、已失效或形成环时，脚本拒绝写入。**它不能认证调用者真正读过什么；虚报当前 revision、遗漏依赖或谎称重算仍须实质复核。**

## 探索与承重用途

| 记录 | 用途与约束 |
| --- | --- |
| `kind=candidate` | 默认且只能为 `use=exploration`；允许没有证据、依赖或成果文件。 |
| `use=working` | 默认的工作材料，不声称承担最终推荐。 |
| `kind=adopted` | 默认且必须为 `use=support`，明确承担已采用推荐。 |
| `use=support` | 至少声明 `basis` 或 `depends_on`；仅有 `recompute_on` 不提供支持。沿 `depends_on` 的整个前提祖先链不能含 `candidate` 或 `use=exploration`。 |
| `recompute_on` | 节点可选的对象版本依赖，可指向仍未验证的候选；内容变化仍使本项及下游过时，不把候选升级为事实。 |
| `kind=result, use=exploration` | 可汇报尚未验证的候选及其依赖，不把“报告候选”误作“采纳候选”。 |
| `kind=obligation` | 保存应交付成果；可以先没有文件，届时 `check` 会报告尚未链接输出。 |

例如，一项判别试验可以有充分的设计、可行性和信息价值依据，同时把未验证的 `idea` 作为检验对象；下面只是节点示意，实际版本与依据须取自当前任务：

```json
{"id":"trial","expected_revision":0,"kind":"adopted","body":"设计用于区分候选的试验，不预先认定候选成立","basis":["合成示例：试验能区分候选，且具备开展条件；真实任务替换为实际依据"],"recompute_on":{"idea":1}}
```

`idea` 更新后，`trial` 和依赖该试验的下游需重算；候选身份仍保留。条件推演也可这样引用其假定对象，但结论必须保持条件范围。外部动作台账接口不变，可依赖已有充分依据的试验节点；该节点过时后不能按旧依据发起。

获得相应证据后，可把候选更新为有实际依据的其他类型，或为验证结果新建事实节点；保留探索原稿和分歧。不能仅改 `kind`、`use` 或 revision 就声称验证完成。结构检查只识别明确标为探索的成立前提祖先，无法识别假证据、弱证据、伪装成事实的候选或错分的依赖用途。采用地位、依据充分性、条件范围与专业正确性仍由实际取证和 review 判断。

## 动作台账与恢复

动作台账只托管记录；记录 `authorized` 引用**已有授权**，不要求用户再批准。它既不验证授权真假，也不执行动作。幂等键在同一状态文件所有动作（含失败、取消）中唯一且不可改；它防止此台账登记重复键、重复阶段，不保证外部系统幂等，更不能阻止绕过脚本、另换键或另建状态文件的重复执行。

| 状态 | 只在以下真实阶段登记 |
| --- | --- |
| `proposed` | 拟议，尚未记录授权。 |
| `authorized` | 当前动作已有授权，保存来源；可从该阶段直接初始化记录。 |
| `initiated` | 已进入可能发送的区间，实际请求可能尚未发出，也可能已发出；不证明外部已经发生。真实调用前先成功登记，未核实结果前不能猜作成功、失败或未执行。 |
| `tool_confirmed` | 工具已确认其实际返回的阶段；受理回执不等于结果达成。 |
| `observed` | 已观察到外部结果，在 `note` 中记实际观察。 |
| `failed` / `cancelled` | 已查明失败或取消；不用于掩盖外部状态未知。 |

正常转移为拟议→授权→进入发起区间→工具确认→观察；进入发起区间后允许直接记录已观察结果、失败或取消。已观察、失败和取消是终态，不能用同一动作记录自动重试。进入发起区间之前可用 `action` 修订正文、依赖与已有授权；此后只允许 `advance` 登记实际阶段，不覆盖动作定义。依据更正不抹除已经发生的事实：脚本拒绝用过时依据登记授权/发起，但仍允许记录实际回执和结果。

**真实调用顺序是：先成功落盘 `initiated`，再调用外部工具，最后登记实际回执与观察。** `note` 如实区分“准备调用”“工具已返回”和“结果已观察”；写入失败或结果不明时，先重读核对，不能继续发送。若先调用后登记，可能在外部已发生、记录仍为 `authorized` 时中断，恢复将无法发现该窗口。采用先登记的顺序后，即使在真正发送之前中断，也保留不确定状态；恢复时仍先核对外部系统，不能把没有回执当成未发送。本地文件的落盘不代替宿主所需的持久检查点。

下面接续更正演练的状态版本 9，**模拟**“进入可能发送区间后中断”的恢复；所有 `note` 都注明合成情景，未调用任何外部服务。真实任务先完成登记再调用，恢复时先核对外部状态，再填写真实记录。

```bash
python3 "$STATE_TOOL" --state "$STATE_FILE" action --expect-revision 9 <<'JSON'
{"id":"demo_action","expected_revision":0,"idempotency_key":"demo-only-once","body":"合成情景中的外部动作","depends_on":{"choice":3},"status":"authorized","authorization":"仅演练已有授权状态；不授权真实外部操作"}
JSON

python3 "$STATE_TOOL" --state "$STATE_FILE" advance --expect-revision 10 <<'JSON'
{"id":"demo_action","expected_revision":1,"status":"initiated","note":"合成情景：准备调用，先登记可能发送区间；本条不证明已经发送"}
JSON

# 真实流程只在上一步确认写入成功后调用外部工具；本演练不调用。
# 无论在实际发送前，还是发送后、回执前中断，都先恢复核对。
python3 "$STATE_TOOL" --state "$STATE_FILE" recover --expect-revision 11
python3 "$STATE_TOOL" --state "$STATE_FILE" check

# recover不重发请求；外部核对之后才记录结果。此处仍只是合成情景。
python3 "$STATE_TOOL" --state "$STATE_FILE" advance --expect-revision 12 <<'JSON'
{"id":"demo_action","expected_revision":3,"status":"observed","note":"合成情景：已观察结果","reconciliation":"合成核对记录：按幂等键查询，确认只发生一次"}
JSON

python3 "$STATE_TOOL" --state "$STATE_FILE" check
```

`recover` 对 `initiated` / `tool_confirmed` 挂起 `needs_reconciliation`，保留原阶段、增加动作版本并写历史。核对前 `check` 返回未解决项；后续状态登记必须包含非空 `reconciliation`。该字段只是核对记录，脚本不访问或验证外部系统。失败不明时保留待核对，不能靠换键重试来消除不确定性。

## 字段与检查结果

`show` 输出完整状态：总 `revision`、不可覆盖的 `original_task`、当前 `task`、`nodes`、`archive`、`impact` 与 `actions`。节点类型还包括 `source`、`inference`、`calculation`、`action`、`result`、`unknown`、`goal`、`constraint`；类型名称只帮助区分材料，不能代替真实性判断。ID 使用英文字母、数字、`_ . : -`，以字母、数字或 `_` 开头。依赖字典的值为正整数版本，不能用 `true` 冒充 1。

| 退出码/结果 | 实际含义 |
| --- | --- |
| `0`，写入 `ok: true` | 本次状态写入完成，输出最新总版本；不是动作执行成功。 |
| `0`，`check` 的 `ok: true` | 记录结构、声明版本、文件存在/哈希及已填写的可见位置未发现问题。 |
| `1`，`check` 的 `ok: false` | 仍有待审全局影响、承重/成果节点过时、成果缺失或被改写、动作结果待核对等可检测问题。 |
| `2`，错误 JSON | 输入、文件、锁或预期版本错误；查看错误再处理。写入前拒绝不改状态。 |

`check` 始终输出 `semantic_sufficiency: not_checked`、`declared_dependency_truth_or_recomputation: not_checked` 和 `delivery_or_authorization_authenticity: not_checked`。`visible_at` 只检查已填非空定位，**不读取段落来证明语义覆盖，也不核验定位真的对应所需内容或用户已看见**；交付前仍须打开确切文件，按成果约定做实质核对。文件可在检查后改变，哈希仅约束本次读取到的字节；需要稳定版本时自行保存不可混淆的文件版本。

互斥锁文件 `state.json.lock` 会保留，正常退出或进程退出时系统释放锁；不要删除锁文件来“解锁”，否则合作进程可能锁住不同 inode。替换前故障保留旧 JSON；若替换已经发生但目录同步失败，脚本明确报告应重读，不能把错误码当作“肯定没写入”。断电、磁盘或文件系统故障、人工改写、外部文件变化及授权真实性都超出本地记录器能保证的范围。

## 9.8.11 影响审核覆盖

中心节点变化记录该节点及已登记的受影响下游；任务变化记录全部节点与任务版本。review-impact 解除 pending 前必须在 checked_nodes 中覆盖这些对象的当前版本，空审核或漏项被拒绝；旧事件未记录范围时保守要求全部节点与任务。未解决的审核不会遗忘此前事件。此检查防止结构性空放行，不证明语义充分、依赖图完整或实际读过材料。模型外范围重建与认知操作使用 [认知工作契约](cognitive-contract.md)，不能用这里的影响审核替代。
