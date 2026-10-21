> **11.3.0 独立成果竞争：** 正常 `@StateDyne` 在宿主具有真实多智能体能力时继续使用完整的并行研究，不削减已有角色。新增独立成果竞争工作者，不把多数相似结论当真理；对常规解、重要少数发现、新目标和可行新路径，比较真实生成过程、可证伪预测、环境条件、净价值及实现要求。关键新证据有现实可调查路径时返回研究调度器，而不是直接写一份平均化总结。未证明的创新保持条件身份。工程测试不证明真实模型已经达到世界领先。

# StateDyne

**StateDyne — 理解现实、改变现实的统一元方法**

StateDyne 是一个面向复杂开放问题的开源 AI Skill。用户无需掌握方法论，只要自然描述现实问题、目标和已知信息；它会按实际证据尝试发现关键关系、取得资料、挑战解释、生成尚未报告但可验证的预测，并在需要改变现实时比较值得改变的位置与具体动作。

[GitHub 首页](README.md) · [English README](README.en.md) · [方法正文](references/method.zh-CN.md) · [工程指南](engineering/guide.md) · [更新记录](CHANGELOG.md)

## 能做什么

- 自主研究问题：区分用户报告、外部事实、因果解释、形成史猜测与条件推断；有工具时主动取证。
- 主动发现：从上下游、环境和制度、历史、主体、反馈、跨领域关系寻找尚未报告的机制，并提出有辨别力的后续检验。
- 信息循环：用户新回答、新证据或反例会重新打开受影响的认识与决策，不为完成固定问数或轮数而提前结束。
- 目标与改变：尊重用户珍视的价值；后台互证干预点与动作，前台通常按分析→干预点→动作→方案分轮交付。
- 严格核验：重要数字要检查来源、单位和时间；复合目标必须核实多个必要条件在同一结果上共同成立。
- **长程任务自主接续**：在用户拒绝更多私人资料、补充一个小问题、暂时讨论别的事情之后，仍保留原目标和已审核进度；用户明确暂停/终止时尊重决定。初步方案合理不代表已经最优，独立搜索更高价值的目标表示和不同路径，不强造创新。
- 能力优先：不默认设定问题数量、探索轮次或有价值干预点上限；不以较短用时换取较差的认知质量。

## 安装

本仓库完整目录即 `statedyne/` 技能目录，`SKILL.md` 位于该目录根部。直接上传入口可使用 [Install ZIP](downloads/StateDyne-11.3.0-Install.zip)；要求 ZIP 内只有一个顶层技能文件夹的 OpenAI Skills API 或其他入口可使用 [Agent Skill ZIP](downloads/StateDyne-11.3.0-Agent-Skill.zip)；明确要求插件格式时使用 [Plugin ZIP](downloads/StateDyne-11.3.0-Plugin.zip)。也可以克隆仓库，再按照宿主实际支持的方式安装完整目录。

Codex 使用默认技能目录时可执行：

```bash
mkdir -p ~/.codex/skills
cp -R . ~/.codex/skills/statedyne
```

是否能使用 `@StateDyne`、真实独立智能体、联网检索、状态保存和外部执行，取决于宿主实际开放并授权的工具。仅安装 ZIP 不能自行创建这些能力，也不应把待执行任务冒充已完成的研究。

## 直接使用

直接描述问题即可。例如：

> 我想知道为什么试点改善了指标，但用户没有付费采用。请自主研究遗漏的现实关系，再比较真正值得改变的位置。

> 请研究这项政策能否在五年内产生实际净新增结果，不能用审批、申请或毛交付代替目标成果。

**语言**：默认跟随用户本轮请求的语言；明确指定输出语言时按要求回答。核心方法及部分协议使用中文，不代表只能输出中文。多语言效果仍由实际模型与宿主决定。

## 工程核验与边界

跨轮使用时，可以在上轮已审核发布后提交本轮自然语言（不必手动给题外话贴标签）：

```bash
python scripts/run_statedyne.py update --workdir ../statedyne-run --source-file ../follow-up.txt
python scripts/run_statedyne.py advance --workdir ../statedyne-run
```

该流程需要真实宿主接入并执行后端派发的工作者；不能把只是加载 `SKILL.md` 的聊天宿主等同于完整受控运行器。

Python 3.11+；下面的本地检查**不会执行真实模型调用**：

```bash
python scripts/validate_skill.py --strict-bytes
python scripts/run_test_groups.py
python scripts/run_statedyne.py doctor
```

如使用 `native` 受控后端，创建请求只等于启动了等待真实工作者的队列，不代表十个工作者已执行：

```bash
python scripts/run_statedyne.py start --backend native --task-file examples/task.txt --workdir ../statedyne-run --scope analysis
python scripts/run_statedyne.py status --workdir ../statedyne-run
python scripts/run_statedyne.py trace --workdir ../statedyne-run
```

请将包含私人输入、凭据、运行回执的工作区放在仓库外。工程测试证明协议与软件结构的局部正确，不证明认知性能全球领先、全部模型效果一致或现实干预已成功。

## 发行信息

当前版本为 **11.3.0（独立成果竞争、多智能体新发现保真版）**。直接技能 ZIP、单顶层目录 Agent Skill ZIP、支持插件导入与 `@StateDyne` 的独立插件 ZIP，使用同一份技能认知协议；GitHub 包保留全部工程资料。干预点要求正文讲清生成机制、独立净价值、与强替代的排序理由；组合点和动作的实际联合条件与额外收益不得只留在后台审核字段。插件安装不会自动提供真实多智能体、检索或持久化权限。目标与现状校准、前置高价值目标搜索、不同生成机制竞争、主动取证、跨领域新关系及干预点重新比较贯穿研究，不受线性交付阶段限制。保留 Apache-2.0、署名 **Zhizheng Wang / 王之政**、原方法正文与历史工程规格。详见 [发布核验说明](verification/PUBLICATION_REPORT.md) 与 [历史版本说明](engineering/history/10.28.0/README.legacy.zh-CN.md)。

## 11.1 安装提示

安装入口若要求 ZIP 根目录直接出现 `SKILL.md`，使用独立的 Install ZIP；若要求一个顶层技能文件夹，使用 Agent Skill ZIP。GitHub 发行 ZIP 含单层 `statedyne/` 文件夹，将其**内容**作为仓库根目录，不要把工程历史识别为第二个技能入口。结构与回归验证通过不能证明远程安装服务一定成功，也不能证明真实模型必然产生创新。详见 `RELEASE.md`、`references/breakthrough-engine.md`。

### 11.0.0 生成性循环（候选版）

本版将“已经给出的现象的有用重组”与“真正新关系/新预测”分开，增加竞争解释和防止过早收束审核，并隔离明确独立新任务的旧来源及研究状态。原方法正文未改。通过四组独立进程的确定性回归不等于真实模型已稳定提升；使用 `python scripts/run_test_groups.py` 复现。

完整机制见 [生成性研究循环](references/generative-loop.md) 和 [发行说明](RELEASE.md)。本次把目标优化前移、把未尝试的关系纳入可执行调度、把暂缓未知保留在跨轮状态，并要求真实研究前沿出现在下一步提示中。周数/人数可以作为粗略里程碑，不要伪装成可精确计算的最优值。真实模型质量与安装是否成功仍需要独立验收，参见 [实机验收条件](verification/REAL_MODEL_ACCEPTANCE.md)。

### 11.1 成果价值机制

不再让泛泛的日程、固定人数门槛和重复清单代替真实的价值发现。先比较现实结果怎样生成、用户已经有效的办法能否直接复用以及新路径如何在可实现条件下击败成熟方案。用户明确只想本轮得到一个直接办法、不继续分析时，可自然结束；原有研究位置仍保留，未来用户主动继续能够接回。详见 [成果生成与路径实现](references/result-realization.md)。工程测试不能替代真实模型对照。
