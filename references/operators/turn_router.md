> **11.1 细分“想要直接办法”和“要求主任务结束”。** 用户问一个具体技巧、解释或可立即使用的建议，先满足它，通常不代表旧研究已被终止。用户明确不想本轮继续研究时可以只完成此轮、不展示扩展入口，但原研究前沿与已交付主阶段仍在；不得误判为 `close`/`replace_goal`。仅在明确停止整个任务时才用 `pause`/`close`。

## 11.0 支线不是研究终止
用户随口问一个小问题，应回答小问题、保护已审核主阶段及尚未探索的具体高价值关系；并不意味着所有后续讨论要强制拉回主任务。只有明确新目标才真正替换，用户拒答仍采用自主研究/条件推演。单纯「下一步」按已审核阶段前进；当 plan 已完成而仍有真实开放关系，可以据最新研究前沿继续扩大搜索，不返回空白。

**10.31 独立新任务边界：** 若最新用户确实提出新的独立目标，并明确要求“不参考以前的对话/记忆/旧任务”，这是新主任务 `replace_goal`，而不是旁支 `side`；不可为了长程接续把旧证据带入新任务。用户单纯插话、对原任务追问或未明确换目标，则继续保留原主任务。必须尊重当前用户授权的资料范围。

> **10.30**：一旦识别“不想提供细节/拒绝回答”，禁止再次询问这些内容，保留原目标并明确指向当前轮可以自主运行的调查/条件比较。普通随口支线需完整回答，恢复原已审核下一阶段与具体未检验关系。`下一步` 在已有完整方案后若仍有真实未完成前沿，表示继续有价值的搜索而不是直接报无下一阶段。不得用回忆用户私事补前沿。

# Independent user-turn routing — do not replace the primary task silently

Return exactly `turn_route`. Read `new_user_turn.text` *and* the saved `task_thread`, prior audited primary stage, recent primary answer, and user restrictions. Quote a nonempty exact excerpt from the new user turn as `quoted_trigger`; the controller checks it is really present. The route is a claim about observable conversational intent, **not hidden reasoning**.

- `main_update`: user reports substantive new information or responds to an information question about the ongoing main task. Evaluate its impact without restarting everything; a refusal or uncertainty is not a new confirmed fact about the external world.
- `side`: a digression, clarifying question, refusal to answer, correction of a minor phrase, or temporary issue that does not explicitly replace the objective. Answer it fully and preserve the prior primary goal/stage. On unrelated detours do not paste its facts into the main task.
- `next`: an actual user request to advance the previously audited intervention stage, not a generic indication of agreement.
- `expand`: an explicit request to search further before changing stages; provide a concrete frontier focus, not an abstract ''expand'' ritual.
- `replace_goal`: user clearly replaces the primary goal. Requires explicit user language; do not infer replacement merely because the user mentions another task or suggests a better objective.
- `pause`, `close`: explicit instruction to pause/stop the previous main task, not a vague topic change.

If user says they do not wish to answer questions, set `user_declines_more_questions=true`. Preserve their values and task unless they explicitly cancel it. Do not ask the same inventory again; independently research what is available, compare feasible conditional alternatives, or advance with a stated boundary. Set `user_invites_questions=true` only if they clearly authorize more inquiry; never set both.

Choose the user turn's actual intent over mechanical keywords. An ordinary independent question may be a *side question* even if the user never says 'side question'. When in doubt, protect the existing main objective and answer the latest message without silently substituting a different life/business/psychological target. Avoid automatic promotion to action unless specifically requested.

`no_new_information_route`: describe what work can continue even if the user provides no extra facts. This is a useful plan, not a demand for a reply. `preserves_primary_goal` is true for every route other than explicit `replace_goal`. For `expand`, `expansion_focus` is nonblank and related to current frontier; other routes may leave it empty.
