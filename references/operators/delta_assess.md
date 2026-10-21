> **10.17 提问回报逐组清算**：读取 `recent_turns[-1].draft.output.question_groups`（只看确实向用户提出的那一批问题）。必须在 `question_results` 中逐组给出 `group_id`、结果性质（支持第一种解释/第二种/混合/未知/真正新增关系）、这次答复提供的实际证据，以及它改变或没有改变的判断；即使用户记不清也要按 `unknown` 如实登记，不能把没答到的事当作否定。并非所有新内容都是在回答旧问题；新关系也可以独立触发重构。不要为了让提问显得值得而编出新增深度。若原来没有问用户，则 `question_results=[]`。

# 增量新证据影响评估（不直接改写旧历史）

输入包含本轮真实新增来源、旧的目标限定系统图、竞争解释、预测、未知和已经交付的结果。输出严格 `delta_assessment`。

判断新增信息是否只修改少量现有关系（`local`），还是目标、系统边界或主要问题表示被推翻而需要真实全局重建（`rebuild`）。不得只因有新内容就重启所有智能体；更不得把纠正根本前提当作局部修补。`affected_claim_ids` 逐条指向确实受影响的结论，`affected_unknown_ids` 指向需重新核对的未知；未受影响的老解释仍然有效。`new_foci` 从新来源逐字引用关键新反差，避免无据创造历史。`newly_relevant_difference` 具体描述它改变什么预测、目标、上下游、环境或改变路径，不能填泛泛的“有新资料”。

这是决策接口，不是语义真值证明。若无法可靠判断是否局部，选择 `rebuild` 并说明理由。公开市场/科研资料应按来源强度处理，不等于所有披露都是充分证据。


## 10.29 task re-entry rule
A routed refusal, digression, correction or no-new-information message must NOT turn the user’s silence into evidence against the main hypothesis or erase previously verified goals. Look at `task_thread.user_input_policy`: if the user declined personal questions, complete analysis via available records, autonomous research, rival conditional futures and low-regret decisions, not repeated demands. If `task_thread.last_route` was `replace_goal`, the former goal is no longer the active objective: return a full rebuild, not a local patch.
