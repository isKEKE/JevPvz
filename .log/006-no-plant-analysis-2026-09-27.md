# 新开局没有种植：只读分析

证据：当前 `.log/test.jsonl`，run `78993a850b2843b29503b31d726d3baa`，2026-09-27 12:42:33.865–12:43:05.232 UTC，约31.4秒。78个事件；本轮未运行游戏/API，未改实现或SDD状态。

## 确认的执行原因

- collect共享请求17次，construction_intent全部选择cancel（概率0.55–0.78，均值约0.694）；next_construction_type选择sunflower13次、peashooter4次。所有请求current_intent=null，source_intent_version始终0。
- Runtime按cancel清空意图；独立类型答案只有operation=replace时才建立意图，因此本次没有任何建设意图发布。类型分布不能当作行动授权，不能忽略cancel直接种植。
- PlantBranch确实发出6次请求。5次Noul为0.19、0.18、0.26、0.25、0.24，均低于实际0.3门槛，返回model_wait/noul_gate_below_threshold。
- 唯一通过者job-000002：Noul=0.32，选择sunflower@r0c0，但job_end=superseded，未成为执行动作。该请求源有9个僵尸，紧接的输入变为0，种植前提发生变化。
- 共5个action_result，全为collect_item success；没有plant action_result/proposal_discarded/Boundary拒绝。8次收集selected不等于8次已经完成点击，文件结束前只有5次成功结果。

## 提问设计问题与证据限度

当前经营编辑问题是“keep/replace/cancel your current next construction intent”，初始current_intent却为空。没有明确“无意图时建立新意图”的语义；实际17次都cancel，这是值得优先修的冷启动问题。它与独立“下一建设类型”答案经常强烈偏向向日葵并存：job-000003中cancel=0.72、sunflower=0.97；job-000005中cancel=0.66、sunflower=0.98。二者独立回答，不能说模型已经授权种向日葵。

局部种植门槛在 `jev/client.py::_plant_absolute_questions` 内直接构造，文本是“Should the next construction intent be acted on now…”，而实际输入current_intent仍为null。这会让fallback继续询问一个尚不存在的意图是否该执行。低分是事实；将低分归因为该措辞还需要冻结状态对照，不可保证单改措辞后模型一定种植。

这个实际使用的Noul没有集中在questions.py，questions.py内保留的economy_question是历史问题。只审阅questions.py不能看到所有现行问题，是实现的审阅入口缺口。350个确定性测试证明模拟typed输出的编排/执行边界，没有证明真实模型在无意图开局会创建建设意图。

## 附加输入异常

开局首样本wave=0却有9个僵尸（均row0、distance8），随后约0.93秒归0；约18秒后才出现wave1的单个僵尸。可能是关卡初始化/残留/待出场实体；没有原始All State/实体状态证据，不能定案为采集bug。它影响了唯一选中种植的来源，但不能解释之后所有空场景仍cancel。

## 建议修订方向

1. 意图为空时询问“下一建设类型或不建设”，或者提供明确的建立新意图选项；避免让编辑不存在的意图成为冷启动前提。由模型弃选决定等待，不由代码固定种向日葵。
2. 常规有意图路径和无意图fallback的问题分开：fallback基于实际合法候选询问当前是否种植，不引用不存在的next intent。
3. 将实际使用的问题/门槛集中到questions.py；增加current_intent=null的真实冻结状态提问对照，以及对应typed编排测试。先验证问题语义，不直接降低门槛或绕过模型cancel。
4. 单独检查开局9→0僵尸的来源与可行动实体定义。

这是研究分析，不是Verify结论或新的Plan批准。
