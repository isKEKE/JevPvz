# What Plants vs. Zombies Taught Me About JEV's Place in a Harness

> First written September 28, 2026; updated October 4. The five live games used `jev-1.13.0`. This is a look back at the JevPvz system, not a claim about the model's permanent theoretical limit.

At first, the idea seemed simple: read the game state, let JEV choose an action, and send that action back to the game. `State → JEV → Action`. Playing made that picture fall apart. “What should I plant, and where?” is really several questions. I have to think about available sun, which lane is close to failing, where I already have firepower, what the new plant will block later, and whether a sunflower that costs sun now will pay off before the next threat arrives.

The experiment left me with two observations: **JEV really can make a long series of decisions in a live game. But good next moves do not automatically add up to a good long-term plan.** Later testing made something else clearer: the whole system also depends on how the harness handles State, goals, candidates, actions, and feedback.

## What happened in the five games

A person ran these games and labeled the outcomes. The logs record JEV's requests, choices, actions, and stop states. The full accounting is in the [006 verification record](../.sdd/006-jev-runtime-loop/verify.md).

| Log | What had changed | Result |
| --- | --- | --- |
| [01](../.log/test_01.jsonl) | No experience rules | Reached wave 14; no evidence of a 1-1 clear |
| [02](../.log/test_02.jsonl) | Experience rules newly added | Reached wave 10; no evidence of a 1-1 clear |
| [03](../.log/test_03.jsonl) | Experience revised | Human confirmed a 1-1 clear |
| [04](../.log/test_04.jsonl) | Attempted 1-2 | Human confirmed a loss |
| [05](../.log/test_05.jsonl) | Latest changes applied | Human confirmed a 1-2 clear; Trace ended in the next level's `level_intro` phase |

Clearing 1-1 and 1-2 was not a paper exercise. JEV made choices, and the system planted, collected, and advanced in the real game. But it was **JEV plus the whole harness** that cleared those levels. The memory reader, plant catalog, legal-action candidates, experience text, action checks, scheduler, and result confirmation all played a part.

## Why the strategy still felt shaky after those clears

One early example is [game 01, `event_sequence=312–320`](../.log/test_01.jsonl). Lane 0 already had five resource plants; the other lanes had none. JEV chose `sunflower@r0c6`, and the plant was placed successfully. The move was legal. That does not mean putting yet more resources in that lane was good for the lawn as a whole.

Later, we gave JEV lane-threat labels, plant roles, and layout guidance. The problem did not disappear. In [game 05, `event_sequence=568–571`](../.log/test_05.jsonl), lanes 2, 3, and 4 had zombies but no attackers, so all three were marked `undefended`. Lane 0 had no zombie. JEV still chose and successfully planted a peashooter in lane 0. Preparing ranged fire ahead of time can make sense. In this situation, though, it won out over three lanes with an immediate defense gap. That is the kind of cross-lane priority decision that one more label cannot reliably settle on its own.

Guidance is not a hard rule, either. In [game 05, `event_sequence=2636–2651`](../.log/test_05.jsonl), lane 4 already had two resource plants, and JEV planted another sunflower in column 4. The [experience file](../configs/plant_experience.txt) recommends columns 0 and 1 for resource plants. I cannot prove this one sunflower made the game worse. It does show that telling the model a placement preference is different from enforcing it on every move.

It would also be wrong to say that JEV “never stops planting.” In game 05, the plant branch selected a placement 92 times and returned `model_wait` 140 times. It had a `none_of_the_above` option. The difficult question is subtler: when does a lane already have enough firepower, and when is another plant worth less than supporting a different lane or saving the sun?

There is another distinction that mattered throughout the project: **a poor choice** is different from **a good choice that the harness failed to carry out**. In games 01 and 02, 109 and 188 records involved collectable sun falling outside a wrongly configured clickable area. That count was zero in games 03–05 after the area was fixed. Game 04 also had 753 collection batches superseded by newer batches; the count fell to zero in game 05 after the queue changed. The [verification record](../.sdd/006-jev-runtime-loop/verify.md) explains the counting rules. These were observation and execution problems in the harness, not failures of JEV's plant-placement strategy.

## The hard part is turning next moves into a strategy

Seeing the offered options, the model's choice, and the actual action together clarified JEV's role for me. It can quickly answer “Which of these options should I pick?” and return something software can use directly. Yet a legal choice can still strengthen an already strong lane while leaving another without firepower. **A bounded output tells the program how to consume a judgment; allocating resources across the lawn needs a longer view.** That fits TypeSafe's emphasis on focused judgments composed in code. See the [official documentation](https://docs.typesafe.ai/primitives).

Saving sun makes the distinction easy to see. Building an expensive plant means passing up a cheaper purchase now, perhaps for several turns. The later system keeps a construction goal and uses code to calculate its shortfall, what surplus can be spent, and which threats should interrupt saving. That gives the system a way to preserve resources for later moves. **The continuity comes from the harness retaining a goal and enforcing rules; JEV still makes the current local choice.** In this project, JEV did not build and continually revise a long-term economy plan on its own.

There is another easy misunderstanding: what JEV can choose depends on what the system offers. When a construction goal became a candidate filter, other plants could disappear from view. Changing that restriction made those choices possible again. So when JEV keeps picking cheap plants, I need to inspect both the judgment and whether alternatives were available at all. That is part of the harness's job: turn the situation into a useful question, give the model room to judge, and keep spending and actions aligned with the system's goals. See the [candidate rules and economy facts](../jev/strategy.py).

Planting and removal work the same way. JEV can judge two clear questions separately, but the system still has to coordinate which action happens first and whether clearing a cell serves the next step. Putting the questions in one request does not automatically create a coherent upgrade plan. Later tests reinforced my view: **JEV fits as a fast, bounded judgment component inside a harness. Turning its choices into a strategy over time requires goals, memory, planning, and feedback working together.** That matches TypeSafe's division between model judgments and code composition. See [Primitives](https://docs.typesafe.ai/primitives).

## What TypeSafe actually says about JEV

TypeSafe calls JEV a **System One** model. It receives a State and answers predefined questions with typed choices and probabilities; it does not currently inspect images directly. The emphasis is on fast, focused judgments, not on asking the model to plan an entire game by itself. See [System One](https://docs.typesafe.ai/concepts/system-one). TypeSafe also recommends splitting a complicated judgment into smaller questions, leaving exact calculations to code, and combining the answers in code. See [Primitives](https://docs.typesafe.ai/primitives).

That matches several problems we ran into. TypeSafe's own list of `jev-1.13` weak spots includes counting, numerical precision, multiple steps of indirection, irrelevant context, and conflicting instructions. See [Jev 1.13 jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13). So “give JEV more State” should not mean dumping every game variable into the request. It means computing the relevant facts, asking a clear question, and leaving JEV the uncertain part that is genuinely a judgment.

The low-hallucination claim needs a precise reading, too. **JEV's answer stays inside the types and options we gave it.** It will not invent a plant that is absent from the candidate list. That makes the software interface dependable; it does not guarantee that the model picks the best legal lane or cell. See [Primitives](https://docs.typesafe.ai/primitives). TypeSafe's Doom demo likewise used structured State, and the company explicitly noted that a conventional bot might play better. A real-time game demo does not, by itself, answer PvZ's resource-planning problem. See the [official launch article](https://typesafe.ai/blog/introducing-system-one-models-and-jev).

## JEV, LLMs, agents, and the harness

I now give each a different job. **JEV** makes a bounded judgment: “Which of these legal options fits the current situation?” It can choose again when the State changes. An **LLM** can write out an explanation, propose a plan for the next wave, or look across several games for a recurring mistake. An **agent** is the ongoing process that pursues a goal by observing, using tools, checking results, and updating its plan; it is not a particular model. The **harness** decides when those capabilities are used, what facts they receive, which options and actions are permitted, when an old decision expires, and how results are recorded. These are responsibilities, not a fixed chain of command.

JevPvz currently has a frequent decision loop made of code and JEV: the system prepares State, retains a construction goal, offers candidates, and turns selections into confirmed actions. **The project has not yet connected an LLM or agent to plan automatically, review finished games, and update experience across games.** TypeSafe also positions JEV as a focused judgment within a larger workflow. See [System One](https://docs.typesafe.ai/concepts/system-one).

If an LLM or agent is later connected, I imagine two cadences. As the game changes quickly, code updates exact facts and JEV judges a bounded current choice. At a new wave, a major failure, or the end of a game, an LLM or agent could consider resource goals and lane plans, check them against the actual outcome, and keep only useful lessons. Older plans would need versions and expiry conditions so a new threat can take precedence. **That is a possible next architecture; it has not yet been implemented in the game.** Independent JEV questions about one State need not become separate sequential calls: TypeSafe allows them to be asked together and composed in code. See [Primitives](https://docs.typesafe.ai/primitives).

## What I would take away from the project

The experiment established something real: **with a prepared State, legal candidates, and a reliable action loop, JEV can take part in a live game and help the system clear two levels.** Later testing strengthened my view that JEV fits the frequent local judgments inside a harness. What to build over time, when to stop investing, and how to reshape the formation cannot be expected to emerge automatically from those next-move choices.

I would not call five changing game configurations JEV's “theoretical ceiling.” We did not run a fixed rule-based or alternative-model baseline under the same conditions, and we did not isolate the separate contributions of the model, experience text, and harness. A fairer conclusion is: **JEV gives the harness a useful fast decision point. The harness decides what that point can see and do, and whether its result can be trusted. Planning, review, and experience updates across games are still missing.**

### Evidence for readers who want to check

- [Five-game verification and counting rules](../.sdd/006-jev-runtime-loop/verify.md)
- [JEV questions and experience injection](../jev/questions.py), [hand-edited experience file](../configs/plant_experience.txt), and [runtime scheduler](../jev/loop.py)
- [Pi iteration record](../.log/006-plan-03-pi-02.html): useful for the project's history, not an independent measurement of model performance
