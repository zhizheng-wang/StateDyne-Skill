> **10.13.0 兼容说明：以下是 9.x 旧格式工具的文档，不是本版默认执行契约。** 旧脚本原样保留；新运行器使用 [executor.md](executor.md) 所述状态和任务，不得交叉写入。只有明确维护旧格式时才加载本文。

# 当前成果：普通 @ 的实际工作接口

本文件供复杂任务启动时读取。当前成果是供下一项工作使用的简短内容，不是完整内部思维或用户问卷，不用字段数量认证质量。只有同一版成果被实际读取、变化被实际接收，模块才接通。

## 共同内容与宿主选择

自然语言形态可写为一份短文：

- 当前请求、目标和保护价值。
- 来源 F1…：原始位置、实际内容、报告/观察/公共事实身份、范围与精度。旧问 Q1 的哪部分答了、哪部分仍未知。
- 关系 R1…：当前最有根据判断、转化及范围、为何领先；相容或竞争关系、不同预测、缺口及反证。生成过程与支持它的依据分开。
- 改变 P/A…：有独立作用的点及相对排序、条件候选和动作、多对多映射、采用与反馈；未知会怎样改变它们。
- 此轮变化：何种差异触发什么操作，实际成果是什么，接收到哪些对象；解释、行动、本轮交付分别完成到哪。

这不是要求每次五段齐填，未进入改变就没有完整点动作，简单问答无需建包。来源和关键关系用稳定标识即可，文本可以完整展开，不压成标签。读取成果后仍可回原始材料发现模型外关系；它不是限制探索的唯一地图。

跨轮/多分支复杂任务且宿主能写文件：在包外建立任务目录，真实保存原材料与当前成果。能运行 Python 则用下列轻量适配器；只有文件能力时使用 v1、v2 等不可混淆版本、具体增量和下游修订。无文件能力时在上下文实际形成同等短成果，不能宣称跨会话保存、程序门禁或独立上下文；下一轮只能在真实仍可见的内容上接续。

**同版消费**：每项依赖已有成果的生成、取得接收、选点、写作和审核开始前，实际 read 最新成果。独立原材料挑战例外，它只接原请求和原材料，返回后由主工作读取最新成果来接收。多个分支不能直接覆盖同一文件；分别交产物，由接收者串行合并，发生版本冲突就读取新版本重接收。

## 轻量适配器：真实调用

Python 3 标准库，无网络、模型 API 或安装依赖。ROOT 是单一任务目录，不是技能目录。不得覆盖原材料或已引用工件；新增修订另存文件。脚本输出只声明结构/identity/版本，不会判定材料真实性、内容好坏或宿主确实执行了隔离。

```text
python scripts/current_work.py init ROOT --task-id local-task --goal "当前所求"
python scripts/current_work.py hash ROOT raw.txt
python scripts/current_work.py read ROOT --receipt reads/start.json
python scripts/current_work.py apply ROOT --from-read reads/start.json --patch patches/first.json
python scripts/current_work.py read ROOT --receipt reads/write.json
python scripts/current_work.py bind ROOT --from-read reads/write.json --draft draft.txt --review review.json --receipt bindings/answer.json
python scripts/current_work.py verify ROOT --receipt bindings/answer.json
```

init 建立 revision=0；read 输出实际完整当前成果、revision、work_sha256 和快照引用，并可创建不可覆盖的读取凭据。每项实际工作使用读取的版本，记录短结果到独立产物文件；apply 接收修订，不能用未接收的产物继续下游。apply 后写作/审核须重新 read。无内容变化的一次操作可以交实际不变结果，不强造增量。

read 凭据只是绑定，不证明人或模型理解了内容。调用轨迹才能证明读取和更新发生过；任何自行改文件、跳过调用或事后补录均不能称先前受控。工具不能阻止宿主直接发送。

### apply 的输入

patch 是 JSON 对象：expected_revision 和 expected_work_sha256 来自 read；operation 是本次实际操作成果文件引用；selection_basis 是为何选择该工作而非最强替代的短理由；delta 是实际新增/削弱/排除/重构或有据不变结果；upsert 为改动项对象；retire 为确需撤回的旧项及理由，默认为空。原产物接收另须original_results/result_receptions，格式见下文cp10；findings仍保存本次合成发现。不是要求生成全部思考轨迹。

所有文件引用为 {"path":"相对ROOT路径","sha256":"64位SHA256"}，用 hash 取得。路径不得越界，含符号链接；current-work.json、.current-work-next.json 等可变控制文件不可作为工件，回执不能写入控制文件或锁目录。新增来源时 scope_reopen 引用实际范围重建成果，程序仅校验其存在与字节，不判断搜索充分性。

每个 item 必含：kind、version、status、content、sources、depends_on。

- kind 为 source/relation/information/point/proposal/action/output/challenge/reception。
- version 新项为1，已有内容或依赖变动恰加1，不变保持。
- content 是实际成果的自然语言，关系要讲转化/范围/依据/不同后果，问题要保留确切未答范围，点和动作要真正有作用内容；不是填“已完成”。
- status 可为 reported/observed/public/candidate/inferred/supported/unknown/ready/asked/answered/blocked/conditional/stale。supported 不能直接消费仍未知、候选或条件前提；推断不要求变成 supported 才能有力使用。
- sources 引用 source 项ID。depends_on={"ID":版本} 登记实际消费的依据或成果，主题相近不自动成为必要前提；现实反馈写在 content 中，不能当版本依赖环。
- source 另有 artifact、locator、scope、precision；status 仅 reported/observed/public。原始来源不可覆盖或撤回；纠正新建来源，旧主张撤回/修订保留历史。
- point 显式依赖 relation，action 显式依赖 point；一个动作多个点合法。reception 显式依赖 challenge，其 content 逐项交接收决定、依据及实际更新对象，不能只写已读。其他项可带 artifact 引用具体产物。

改动时已登记下游必须修改或明确 stale，不能默默保留旧结果。stale 表示待返工，不能成为交付目标或未过期消费者的前提。retire 只能用于真正替代或失去价值的旧项，写明理由；撤回ID保留历史身份，之后不得以版本1复用。未解信息不可因不方便而撤回。程序不识别遗漏的依赖和伪造的撤回理由。

completion 是三个短文本：explanation、action、request，说明各自实际覆盖及剩余。未求行动可明确不适用，不把能行动写成解释已定。新信息影响完成判断时一并修订。

### bind 的输入与出稿

先形成确切 draft.txt，再对照原材料、同版当前成果做真实语义审核。review.json 包含：work_sha256；draft 文件引用；targets（本次实际交付的唯一ID列表）；argument_review（实际承重论证/强替代检查的简要结果）；artifact（完整审核与修订结果文件引用）；open_findings（未处理问题列表，绑定要求为空）；limits（限制）。不设置自填 PASS/评分作为质量证明。

review.challenge_dispositions 须精确覆盖当前成果中全部未退休的 challenge ID（包括待返工的 stale 挑战）；没有 challenge 时可省略或用空对象。每项含 version（该 challenge 当前版本）和 decision：

- received：reception_id、reception_version 指向当前非 stale 的 reception；该 reception 的 depends_on 必须消费此 challenge 的当前版本。不能拿另一挑战的接收或旧版本顶替。
- deferred 或 excluded：basis 说明延期/排除依据；artifact 引用真实处置产物；target_effects 的键恰为本次 targets，每项说明该处置对该交付目标的影响；delivery_basis 说明为何本次仍可交付。上述文本不能为空，产物字节会在 bind 和 verify 核验。延期不把未知改成已解决，排除也不证明理由正确。

这是全部已登记挑战的机械处置覆盖，不认证挑战内容、独立性、每个发现接收充分性或延期/排除理由的真实性。承重发现仍由 runtime 逐项实际接收，语义审核仍检查本次交付是否确可继续。未登记的遗漏挑战程序无法发现。

出现承重缺口先回生成/取证/选择并 apply，再重写、重读、重审、bind。表达修改也改变确切 draft 身份，要绑定新稿。bind/verify 只证明稿件、审核文件、当前成果尚是同一字节与版本；空泛内容和错误语义仍可能通过，必须由真实论证审核发现。结构通过不能对用户宣称内容正确、已发现全部未知或心理改变已发生。

## 与既有工具的责任迁移

current_work.py 是普通复杂 @ 的轻量文件接口，不取代已有高级包或外部动作授权。任务本来用 task_state.py 管理外部状态时保留其幂等、权限、回执与恢复；需要 cognitive_work.py 的详细来源分流、挑战接收、比较和精确稿件转换时按原契约调用。两种记录都引用同一原材料和成果；任何副本更新必须同步受影响版本，不能让一个通过的旧包给新稿背书。

当前成果/语义审核负责发现新关系和真实依赖，程序只核验已经登记的结构。先有真实工作，再有记录；不得把自填内容、结构门禁和实际语义质量合成一个“通过”。

## 已登记信息影响与比较的实际接收

information 项增加 affects={"被影响ID":"未知/答案会怎样改变该结果"}。被指向的非 stale 项必须在 depends_on 消费该 information 当前版本；不能一边登记“会改变选择”一边让选择只消费原始来源。确无当前影响时用 affects={} 并写 no_current_effect 的具体依据，不以空对象默认为无关。信息变化走已有版本更新和下游失效规则；影响声明不能代替真实关系搜索，遗漏的影响程序看不出来。旧任务的信息项须依据原材料补影响并在新副本/修订中迁移，不能给每项批量填“无影响”只求过门。旧冻结历史不原地改写。

比较成果直接进入已有 relation/proposal 的 content 或 artifact：比较的是哪些实际对象、各自要达成什么、最低成立条件、决定差异和证据范围；仍未知的差异在相容取值下怎样改变诊断或排序。对象定义缺失时回取证或构造候选定义，不能用一个熟悉大类替代用户尚未说明的具体对象后把它淘汰。先交跨相容情况都成立的可做部分，不等全部信息齐全才构造路线。

同一成果内把三种责任说清：现实诊断需要解释现状及其竞争解释；信息价值排序说明先取得什么会最大改变选择；可逆默认行动说明在当前不确定下何事仍值得先做。后两种选择不反向证明主因已经确定。前台自然解释结论、根据、条件和下一步，不倾倒后台标签。

review.information_dispositions 必须精确覆盖本次 targets 及其传递依赖中的未解 information；answered/supported/observed/reported/public 以外的信息状态均视为未解。无此信息可省略/空。每项含当前 version，以及 target_effects；后者键精确覆盖交付依赖范围内受该信息影响的实质成果节点，详见cp11范围。每个效果含：

- decision 为 conditional、robust 或 not_used。
- basis 为为何可作此处置；effect 为实际怎样改变该目标的诊断、排序、行动或范围；artifact 为实际比较/处置成果文件引用。
- conditional 展开相容情况如何改变路线；robust 说明为什么同一当前行动在相容情况中仍值得及其边界，不能据此确诊；not_used 另含 withdrawn_judgment，明确本次撤回的依赖判断和保留内容的依据。记录仍保留这项依赖，便于审核撤回是否落实。

bind 和 verify 核对覆盖、版本、非空结果和工件字节；不解释自然语言，也不判断理由、相容情况或撤回充分性。只在结尾提问、声称“已有考虑”或产物为空泛故事都不能完成语义责任，即使程序结构通过。审核先用原材料、未知清单和上述比较反查真实依赖，再核确切稿件是否兑现；工具可用性/隔离发生需真实轨迹，自述失败不构成认证。

## 原子发现接收：复用受控契约的普通接口

本接口沿用 cognitive_work 的 finding ID 与 incorporated/conditional/excluded 接收责任，不要求普通任务建立高级受控包。复杂任务的每次 apply 显式给 findings 对象、finding_dispositions 对象；findings 每个短ID对应 {claim, artifact}，分别保存具体承重发现与真实原工件引用。没有承重发现时 findings={}、finding_dispositions={}，并以 no_findings_basis 写实际依据。不能把产物已提出的目标差异、对象缺口、采用边界、替代路线或信息需求漏列为“无发现”；程序不解析 prose 来发现这一遗漏。

finding_dispositions 键精确覆盖 findings。每项为 {decision, basis, artifact, updated_versions}：decision 为 incorporated、conditional 或 excluded；basis 交实际接收依据，artifact 引用具体接收/比较工件，updated_versions={"成果ID":当前版本} 指向 relation/information/point/proposal/action/output，不能指向 source/challenge/reception 或 stale 项。incorporated/conditional 至少映射一个实际成果；excluded 可为空，但须有依据和工件。目标/价值写入既有 relation，比较对象写入 relation/proposal，未解信息继续用 affects 影响下游。可映射已有但经本次实际核对仍适用的成果，不为接收强造增版；若内容或依赖确实改变则按既有规则增版。

challenge 项也必须有 findings；空清单需 no_findings_basis。非 stale reception 的 finding_dispositions 按所依赖 challenge ID 分组，每组精确覆盖该 challenge 的全部 finding ID，处置形态同上。challenge 的当前版本由 reception.depends_on 绑定；接收指向的成果更新/撤回，会要求 reception 重接收增版或 stale。无需把成果版本引用再放入 depends_on 制造反馈环。原始发现和接收工件字节持续核验。

review.challenge_dispositions 的 received 仍绑定当前 reception；现在整体 received 已不能略过其原子覆盖。deferred/excluded 也须以自身 finding_dispositions 逐项覆盖该挑战已列发现；延期发现可条件接入当前信息/候选，排除须具体依据。不能把整体延期当作丢掉承重发现的出口。review.information_dispositions 继续独立履行 cp4 的未解影响处置。

apply 把本次普通操作发现及处置保存进同一当前快照，历史保留原稿；挑战的原子接收留在既有 reception。代码核验声明覆盖、当前成果种类/版本及实际工件，不认证映射内容真的吸收了发现、排除理由正确、空清单诚实或所有重要发现都已找到。纯对话使用同等短成果和逐项接收，不宣称机械门禁。旧快照/夹具缺少这些字段时须保留原件并依据真实产物迁移，不能默认批量标空来取得通过。

## 原文锚点与真实旧命题

证据区分操作和语义审核实际回读原始材料；来源摘要不是原始证据的替代品。文本 source 可声明 quotes=[{start,end,text}]，start/end 为其 artifact 的 UTF-8 字节范围，end 不包含；程序核验范围、精确文字及原文件身份。锚点选择须覆盖承重限定及邻近语境，程序不判断选段是否充分或摘要是否忠实。多模态/二进制来源继续用原 artifact、locator、scope、precision，不强制伪造文本；提取文本作为另存衍生产物并保留出处。既有 source 不可原地改，纠正另建来源。

纠错前实际调用 python scripts/current_work.py diff ROOT --before 旧revision --item 真实ID。返回该任务历史链中的旧/当前 item 完整内容、版本和各自快照引用，不由作者自己改述旧主张。finding 可用 prior_claims=[{snapshot,item_id,version,content}] 引用真实旧命题；程序要求 snapshot 属于当前任务的实际历史链、版本和 content 逐字相符。操作对具体旧命题纠错时实际使用它；未涉及旧命题的小操作无需此项。

将原始锚点、diff结果、相容的非该机制生成过程及其预测差异放入本次已有操作 artifact，findings/finding_dispositions 接收新命题和受影响结果；信息缺口继续经 affects 传递。已有摘要含因果洗入时也纠正其来源身份。无需增加因果认证字段：引用真实不等于因果解释正确、原文蕴涵成立或纠错充分。缺引用可作为语义审核退回理由，脚本不会自行发现全部应有引用。


## 已声明条件规则的比较接续

能独立改变行动的条件规则写入已有 relation/proposal/action/output 等实质成果项的 decision_rules={"规则ID":{trigger,judgment,action}}，三个值为确切非空文本。它们与所属item一起增版，适用已发生或未来条件、反事实及停止/升级门槛；简单任务没有此类规则不造空流程。机制未识别但动作按独立约束成立，也明确表达，不编造机制判断。

实际比较交到原有操作artifact/findings，finding_dispositions.updated_versions指回处理后的规则所属成果；会改变规则的信息以affects指向它。写作消费处理后同版规则，实质新增或修改仍须回接收。

bind/verify 的 review.rule_dispositions 精确覆盖 targets 及传递依赖内有非空decision_rules的item。每项含 version 和 rules；rules逐规则ID覆盖，其处置含 rule_sha256（canonical JSON的trigger/judgment/action摘要，工具实现的digest算法）、judgment_basis、action_basis、effect、artifact，以及 alternative={kind,basis,consequence}。kind为compatible_process或none_found；前者给具体非该机制生成过程和后果，后者给实际比较依据及适用范围，不填“没有其他解释”自证。作用强度与动作依据分开，effect说明规则实际保持、收窄或改变了什么。无相关声明规则可省略/空。

门禁拒绝漏项、旧版本、错误规则内容摘要、缺少两类依据/反例比较结构或不存在/变化的工件；只填PASS无法替代。非空文字仍可能空泛或错误，程序不会解析语义来判真假。不能据此认证全部自然语言规则已登记或反例搜索充分；独立审核仍须对照确切稿件逐条查遗漏。


## 完整独立产物与接收差异（cp8）

challenge 必须带 original_result={path,sha256}，指向生产端原始 JSON 返回：{artifact,findings,no_findings_basis?}。artifact 指完整返回工件（文本/多模态均可），findings 沿用 {ID:{claim,artifact,...}}；空发现仍须真实依据。challenge.findings 必须与该原返回清单完全相等，空清单依据也相等。原返回保留，不把接收者删减的摘要当生产端原件；新增遗漏通过另存补充操作发现接收。

每个非 stale reception 还带 coverage_reviews，键精确覆盖其 challenge 依赖：{challengeID:{original_result,artifact}}。original_result 必须等于对应当前 challenge 的原返回引用，artifact 为实际“完整原工件—当前主成果”语义差异检查报告。报告具体定位正向候选、纠错、目标分支的保留/条件化/排除结果及未列发现，不填全覆盖自证。原有逐项 finding_dispositions 不变。

实际调用 python scripts/current_work.py reconcile ROOT --challenge ID，返回当前快照、challenge版本、原返回引用及完整声明、当前非 stale 接收的逐项处置、目标完整内容/版本与差异检查工件。它自动带出真实两端，语义工作须再打开原 artifact 全文，核对清单以外遗漏与映射是否真的吸收。无 reception 时返回空集合而不认证完成。旧稿或目标改版沿原依赖及接收目标门禁失效。

主要路线比较成果可声明 choice_scope=personal_lead|conditional_choice|robust_default，内容给实际比较与回答分支。对覆盖范围内已声明 choice_scope 的实质成果，information_dispositions 的每项 target_effect 另写 choice_basis=comparison|default_only；bind/verify 拒绝 default_only 支撑 personal_lead。跨相容答案有据保持领先的比较仍可用 comparison 与 robust；个人领先仍可据充分比较成立，但需实际条件/依据，不以共同默认偷换。未声明自然语言排序、未列发现、原返回是否真来自独立工具、语义取舍与信息价值正确性仍不能被程序认证。简单无挑战任务不造challenge对象；实际使用普通operation适配器时，仍按cp10接收其原产物。


cp9仅补 coverage_reviews 的报告内容存在性：每个 coverage artifact 至少一个字节。扩展名明确为文本（txt/md/json/jsonl/csv/tsv/yaml/yml/xml/html/htm），或该 coverage entry 的可选 media_type 声明 text/*、application/json/xml、+json/+xml 时，报告用 UTF-8（可带BOM），且解码后不能全为空白。多模态/二进制报告保持原artifact及可选媒体类型，不强制UTF-8；通用artifact及其他原材料未增加文本限制。非空、有效图片字节或一段PASS均不证明差异审核有意义，语义责任完全保留。


## 普通operation与challenge共用原产物接收（cp10）

每次apply增加original_results={"产物ID":{path,sha256}}及result_receptions，后者精确覆盖前者。每个引用指生产端JSON原返回，格式沿用{artifact,findings,no_findings_basis?}；artifact为完整产物，findings是该原产物自己的完整声明，不以接收端摘要替换。每份接收为{finding_dispositions,coverage_review}：原发现逐项映射当前结果或有据排除；coverage_review={original_result,artifact,media_type?}绑定该原返回和实际全文差异报告，沿cp9内容存在性要求。程序要求本轮operation、每个finding直接引用的artifact，以及本轮改动的relation/information/point/proposal/action/output实质项所带artifact，都在原返回集合中获得覆盖；同一集合可额外接收没有在合成findings中重复的原审阅/构造产物。原事实source仍保持原接口，不伪造分析生产者。

这两项随普通operation保存到当前快照，下一轮历史保留。challenge/reception使用同一original_result/receive_original校验；challenge延期/排除的既有处置artifact也承担完整原件的差异审核，按当前challenge版本绑定原返回并检查非空报告，不另造一套语义规则。调用reconcile ROOT（无--challenge）导出本轮每份原返回、处置和当前实质成果；指定--challenge仍保留原功能。该包只能展示真实声明两端，执行者仍须实际打开原artifact全文找清单外遗漏、完成差异报告，再将变化接回。只给原工件起新名字、故意隐藏消费入口或填虚假原清单仍属语义/执行问题，不被程序认证。

## 选择绑定实际构造对象（cp10）

真正承担方案比较的已有relation/proposal/action/output等选择成果声明candidate_versions={"proposalID":版本}，非空，且每项须在depends_on引用同一当前版本。被引用项必须为非stale proposal，带真实非空构造artifact；明确文本沿cp9拒纯空白，二进制/多模态保留。proposal可以是candidate/conditional，构造不等于事实已证；supported选择仍受既有未解祖先门禁。候选或依赖改版使选择及其下游按既有规则失效。简单解释任务无需此声明。

代码只能检查已有候选声明的对象、当前版本、工件存在性与依赖，不判断首个采用链是否连通，也不自动发现所有自然语言方案选择。方向标题放进非空文件仍可能通过结构，须由原文与确切稿件审核退回；字段数、标为ready或“已构造”均不是能力证据。


## 未解前提的全部实质下游处置（cp11）

information_dispositions仍按information ID和当前version绑定，target_effects的范围扩大为：先取review.targets及其全部依赖，再对其中每个relation/point/proposal/action/output查其未解information祖先，逐节点处置。若information本身是明确交付target，也保留其原有处置要求；不为仅作为输入的information自身、source或challenge/reception过程节点造额外结论。范围内真正受影响的中间目标、排序、预期与终端动作都必须有独立effect；范围外节点或没有该未知祖先的独立目标不纳入。

既有decision/basis/effect/artifact、choice_basis及not_used的withdrawn_judgment要求不变。动作robust可与解释/目标conditional共存，ready不被机械降级；supported的未解祖先限制继续生效。程序拒绝漏中间节点、额外无关节点、旧information版本及错工件；仍无法从prose发现所有应登记未知、拆出混合命题，或判断全填robust的理由是否真实。实际下游重算和原文审核承担这些责任。

旧review只覆盖最终targets时须保留原件，并依据真实重算为中间节点另作处置后重新绑定，不自动复制末端robust。合成工程fixture可以显式补对应中间处置来测试协议，但这不构成真实迁移或语义通过。

## 聚焦接续：强候选与当前缺口

首轮原始反差和后轮新对象共用runtime循环。已有operation原工件保存实际竞争关系、判别需求及新旧缺口取舍；findings映射relation和information/affects，取得操作读取接收后的版本并更新相关比较。candidate/conditional允许参与比较和取证选择；supported不得消费未解前提。点的content或artifact保存实际作用位置、传导、杠杆理由与边界，不以目标标题替代。未新增字段、模型调用或审核层；结构合格不保证候选质量、来源摘要忠实、问题已穷尽或宿主实际遵循流程。

## 原请求范围的反向接收

把原source支持的重要待解释差异/异常/目标差距写入已有operation原工件与findings，接到解释其实际范围的relation、仍开放的information，或有具体价值依据的条件保留/排除。信息选择同时读取候选判别需求与尚无候选承接的重要差异。收窄/完成反查原请求的这些单位，不以只解释中心现象自称全部交齐。无需新增schema；程序仍只验证已声明findings的精确处置及版本/工件，不能证明原请求已穷尽、延后理由正确或解释充分。

## 接收前产物与压缩顺序

本次operation的原工件先保存承重原材料的条件/已做处理/未明条件/支持范围及完整返回待处置对象，再将findings接到source、relation、information和实际受影响成果。完整原返回通过original_results/result_receptions或challenge原接口保留；原返回有遗漏声明时另加带出处finding，不覆盖原件。随后取得选择和成稿消费已接收版本，审核回读前置产物而非仅最终摘要。无schema变化；声明外遗漏、虚假支持范围和不充分的取义理由仍不能机械认证。

## 材料接收的前置版本

复杂首次/实质更新先执行material-intake。source与全部已识别解释需求先在一次operation接收；尚无候选的需求可affects指向明确为开放待解释范围的conditional relation。下一主生成实际read该版本再修订关系，登记源/信息依赖；不得倒过来用主模型筛选前置需求。无新增schema，现有read/apply及声明覆盖只提供结构证据，不认证语义或宿主调度。

## 独立待知义务：required_facts（cp16）

材料接收生产端在finding内声明required_facts对象：稳定ID映射到 {required_fact: 确切待知事实, anchor: {artifact: 原材料path/sha256引用, locator: 定位, quotes: 可选精确UTF8字节引用}}。只拆相互独立可回答且承重的未知，不机械拆每个词、不把required_fact改成推荐问句。二进制/多模态来源可用artifact与locator，无需强转UTF8。

该finding的处置增加required_fact_targets，精确覆盖全部required_facts ID，值为information ID，且该信息项当前版本必须在updated_versions。每个information可保存多个obligations，键为原required_fact稳定ID；值含original_result（不可变生产JSON引用）、finding_id、原required_fact、原anchor、state、basis及必要evidence。required_fact和anchor逐字/结构相等，原返回hash精确相等；不能以同主题内容替代。ID在同份current-work全局唯一。原生产返回和来源纠正时使用新ID/新引用，旧义务有据退休，历史不覆盖。

state可为pending、asked、deferred、obtained、retired。pending为待取得，不阻断有据主答；asked绑定实际成稿/已发送问句artifact及quotes精确字节范围，不能仅交“已问”报告。多模态问句可用audio/image/video media_type及实际工件定位。obtained绑定真实答复artifact、locator和非空scope；deferred/retired有具体basis及理由工件定位。代码检查这些存在/身份，不判断答复真能支持、问句问得对或理由成立。未来要问仍是pending，不冒充asked；asked也不等于用户已回答。

已有未解义务不得跨版本删掉或改身份；信息项不能在pending/asked/deferred仍存在时标answered/supported等已完成状态。先实际记录retired及依据，再在后续版本移除其信息项；已退休ID不得复用。已有回答需要纠正时保留同一事实需求重开，来源变成另一对象则保留旧退休身份并新建义务。义务状态和其依赖变化沿已有增版传播。

旧未声明required_facts的原工件保持兼容，不倒改旧记录或从主摘要伪造生产清单；新材料接收执行此协议。机械保证仅适用于已声明独立义务，源任务漏识别、把多项需求写进一个required_fact以及错误语义处置仍可能通过。成稿审核比较每项原required_fact与实际问句/答复支持范围，不能从后台出现过就声称取得。
