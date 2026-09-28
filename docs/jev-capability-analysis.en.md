# JEV Playing Plants vs. Zombies: What Worked, and Where It Struggled

> Written September 28, 2026. The live runs used `jev-1.13.0`. This is a look back at the JevPvz system, not a claim about the model's permanent theoretical limit.

At first, the idea seemed simple: read the game state, let JEV choose an action, and send that action back to the game. `State → JEV → Action`. Playing made that picture fall apart. “What should I plant, and where?” is really several questions. I have to think about available sun, which lane is close to failing, where I already have firepower, what the new plant will block later, and whether a sunflower that costs sun now will pay off before the next threat arrives.

The experiment left me with two observations: **JEV really can make a long series of decisions in a live game. But good next moves do not automatically add up to a good long-term plan.**

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

## What TypeSafe actually says about JEV

TypeSafe calls JEV a **System One** model. It receives a State and answers predefined questions with typed choices and probabilities; it does not currently inspect images directly. The emphasis is on fast, focused judgments, not on asking the model to plan an entire game by itself. See [System One](https://docs.typesafe.ai/concepts/system-one). TypeSafe also recommends splitting a complicated judgment into smaller questions, leaving exact calculations to code, and combining the answers in code. See [Primitives](https://docs.typesafe.ai/primitives).

That matches several problems we ran into. TypeSafe's own list of `jev-1.13` weak spots includes counting, numerical precision, multiple steps of indirection, irrelevant context, and conflicting instructions. See [Jev 1.13 jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13). So “give JEV more State” should not mean dumping every game variable into the request. It means computing the relevant facts, asking a clear question, and leaving JEV the uncertain part that is genuinely a judgment.

The low-hallucination claim needs a precise reading, too. **JEV's answer stays inside the types and options we gave it.** It will not invent a plant that is absent from the candidate list. That makes the software interface dependable; it does not guarantee that the model picks the best legal lane or cell. See [Primitives](https://docs.typesafe.ai/primitives). TypeSafe's Doom demo likewise used structured State, and the company explicitly noted that a conventional bot might play better. A real-time game demo does not, by itself, answer PvZ's resource-planning problem. See the [official launch article](https://typesafe.ai/blog/introducing-system-one-models-and-jev).

## Where I think JEV fits in a harness

I now see JEV as **a fast judgment component with a dependable output shape**. Code reads the game, counts and measures things, offers legal actions, and checks what actually happened. JEV can help with decisions that are hard to express as a rigid rule but easy to ask precisely, such as “Which of these legal options fits this situation best?” This does not mean making five JEV requests for five conceptual layers. TypeSafe says independent questions about one State can go in the same request. Another call is needed only when a later question truly depends on an earlier answer. See [Primitives](https://docs.typesafe.ai/primitives).

JEV could change its next choice whenever it received fresh State, so it was not blind to the changing game. But **responding to new facts** is different from **drawing, testing, and saving a new lesson after a game**. A person wrote the ten rules in the current experience file. This system has no automatic post-game review and cross-game learning loop. That is a missing part of this harness, not proof of a permanent defect in the model.

If the project were continued, one possible design would work at different speeds. Code and JEV would handle local changes in the fast loop. At a new wave or a serious failure, the harness could call an LLM or agent to look at the current situation and plan the next stretch of play: a resource target, lane priorities, and sun to hold in reserve. After the game, a review would check which suggestions actually helped before carrying any lesson into the next run. Older plans would need to expire when an immediate threat appeared. **This is a proposal, not something the five games implemented or validated.** If an LLM or agent added planning, that new capability would belong to the complete harness, not to JEV alone.

## What I would take away from the project

The experiment established something real: **with a prepared State, legal candidates, and a reliable action loop, JEV can take part in a live game and help the system clear two levels.** It also exposed the limit of the current integration. Local choices can work while resource investment, lane coverage, and spatial layout still pull against one another.

I would not call five changing game configurations JEV's “theoretical ceiling.” We did not run a fixed rule-based or alternative-model baseline under the same conditions, and we did not isolate the separate contributions of the model, experience text, and harness. A fairer conclusion is: **JEV gave the harness a useful fast decision point. If the system is to get better from game to game, planning, memory, review, and reliable execution still have to be built around it.**

### Evidence for readers who want to check

- [Five-game verification and counting rules](../.sdd/006-jev-runtime-loop/verify.md)
- [JEV questions and experience injection](../jev/questions.py), [current experience file](../configs/plant_experience.txt), and [runtime scheduler](../jev/loop.py)
- [Pi iteration record](../.log/006-plan-03-pi-02.html): useful for the project's history, not an independent measurement of model performance
