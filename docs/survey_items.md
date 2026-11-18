# Changing How Setbacks Feel — Survey Instruments

## Study flow

One session of about 15–20 minutes, within-subject: each participant writes one real setback, then reads all four AI feedback messages (neutral, strict, generic encouraging, appraisal-tailored) in counterbalanced order, labeled only Message A–D.

1. Pre-survey (Section P): consent, screening, background, baseline motivation and traits.
2. Setback recall + middle survey (Section M): describe the slip, then appraisal, shame/guilt and motivation before any feedback.
3. Post-feedback survey (Section F): shown after each of the four messages, so it runs four times.
4. Final section (Section Z): compare the four messages, attention checks, debrief.

## Scoring rules (for the parser)

- Unless noted, items use a 7-point scale: 1 = Strongly disagree, 2 = Disagree, 3 = Somewhat disagree, 4 = Neither agree nor disagree, 5 = Somewhat agree, 6 = Agree, 7 = Strongly agree.
- "1 = Not at all, 7 = Very much" items are also integers 1–7.
- Items marked (R) are reverse-scored: scored value = 8 − raw value.
- Sliders (M_INTENT, F_INTENT) are integers 0–100.
- Matching for change scores: every F appraisal/feeling/motivation item matches the M item with the same suffix (F_STAB1 ↔ M_STAB1, F_SHAME1 ↔ M_SHAME1, F_MOT1 ↔ M_MOT1, F_INTENT ↔ M_INTENT). Change score = F − M after reverse-scoring.
- Scale scores = mean of items in each block (STAB, CTRL, BLAME, COPE, GLOB, SHAME, GUILT, MOT, SE, SC, QUIT, AI).
- Attention check M_ATTN: correct answer = 3 ("Somewhat disagree"). Any other value = fail flag. It is not part of any scale.
- Z_ATTN2: flag if the chosen area differs from P_GOALTYPE.

## Section P — Pre-survey

**P0. Consent.** Show the consent text (texts.consent_body in backend/config/survey.json), then: "I am 18 or older, have read the information above, and agree to take part." (Yes / No — No ends the study.)

**Screening** (any listed answer ends the study politely)

- P_SCR1. Are you 18 or older? (Yes / No → end if No)
- P_SCR2. Are you currently trying to make or keep a healthy lifestyle change (for example exercise, eating, sleep, stress, screen time)? (Yes / No → end if No)
- P_SCR3. Are you currently receiving treatment for an eating disorder? (Yes / No / Prefer not to say → end if Yes, and show support resources)

**Background**

- P_AGE. Age range: 18–24 / 25–34 / 35–44 / 45–54 / 55–64 / 65+
- P_GENDER. Gender: Woman / Man / Non-binary / Self-describe ___ / Prefer not to say
- P_COUNTRY. Country you live in: ___
- P_STUDENT. Are you currently a student? Yes / No

**Your lifestyle goal**

- P_GOALTYPE. Which area is your main goal in? Exercise / Eating habits / Sleep / Stress / Screen time / Other ___
- P_GOALTEXT. In one or two sentences, what is your goal? (open text)
- P_GOALLEN. How long have you been working on it? Less than 2 weeks / 2–4 weeks / 1–3 months / 3–12 months / Over a year
- P_GOALIMP. How important is this goal to you? (1 = Not at all, 7 = Extremely)
- P_APP. Do you currently use an app or tracker for this goal? Yes / No / I used to

**Baseline motivation** (1–7 agree)

- P_MOT1. I am motivated to keep working on my goal.
- P_MOT2. I intend to keep working on my goal over the next month.
- P_MOT3. I sometimes feel like giving up on this goal. (R)

**Self-efficacy** (1–7 agree)

- P_SE1. I am confident I can stick with my goal even when it gets hard.
- P_SE2. I am confident I can get back on track after a bad day.
- P_SE3. I am confident I can reach my goal.

**How you treat yourself after setbacks** (1–7 agree)

- P_SC1. When I fall short of a goal, I try to be kind to myself.
- P_SC2. When I slip up, I remind myself that everyone has setbacks.
- P_SC3. When I fail at something important, I try to keep things in perspective.
- P_SC4. When I slip up, I am hard on myself. (R)
- P_SC5. When I fall short, I feel like I am the only one who struggles this much. (R)
- P_SC6. After a setback, I keep thinking about everything I did wrong. (R)

**Tendency to quit after a slip** (1–7 agree)

- P_QUIT1. After one slip, I often think "I've ruined it anyway" and stop trying for a while.
- P_QUIT2. In the past, a single bad day has made me give up on a health goal.
- P_QUIT3. One setback usually doesn't change my plans. (R)

**Attitudes toward AI feedback** (1–7 agree)

- P_AI1. I would be comfortable getting feedback on my habits from an AI coach.
- P_AI2. I trust AI tools to give helpful advice about health habits.
- P_AIUSE. How often do you use AI chatbots (e.g. ChatGPT, Claude)? Never / Rarely / Monthly / Weekly / Daily

## Section M — Setback recall and middle survey

This block measures how people see their slip before any AI feedback. The tailored condition reads these answers.

**Setback recall**

- M_TEXT. Think of a recent time you slipped on your goal (for example, skipped a workout, stress-ate, stayed up too late, missed logging). Describe what happened, how you felt, and what went through your mind afterward. Please write at least 3 sentences. (open text, minimum 150 characters)
- M_WHEN. When did this happen? Today / Past few days / Past week / Past month / Longer ago
- M_EMO. Which feelings did you have afterward? Select all: Frustrated / Disappointed / Guilty / Ashamed / Sad / Anxious / Angry at myself / Indifferent / Relieved / Other ___
- M_EMOINT. How strong were those feelings? (1 = Very weak, 7 = Very strong)

**Appraisal of the setback** (1–7 agree; "this setback" = the one you described)

Stability

- M_STAB1. This kind of setback will keep happening to me.
- M_STAB2. This setback was a one-time thing. (R)

Controllability

- M_CTRL1. I can control whether this happens again.
- M_CTRL2. Whether I slip again is mostly out of my hands. (R)

Self-blame / locus

- M_BLAME1. This setback happened because of who I am as a person.
- M_BLAME2. This setback was mostly caused by my situation that day, not by me. (R)

Coping potential

- M_COPE1. I know what I can do to get back on track.
- M_COPE2. I have what it takes to recover from this setback.

Globality

- M_GLOB1. This setback means I am failing at my goal overall.

**Attention check 1** (display in the middle of the appraisal block, between M_CTRL2 and M_BLAME1)

- M_ATTN. To show you are reading carefully, please select "Somewhat disagree" for this item. (correct = 3)

**Shame and guilt right now** (1 = Not at all, 7 = Very much)

- M_SHAME1. I feel like I am a bad or weak person.
- M_SHAME2. I want to hide or avoid thinking about my goal.
- M_SHAME3. I feel small or worthless.
- M_GUILT1. I regret what I did and wish I had acted differently.
- M_GUILT2. I want to make up for this slip.
- M_GUILT3. I feel bad about what I did, not about who I am.

**Motivation right now, before feedback** (1–7 agree)

- M_MOT1. Right now, I feel motivated to keep working on my goal.
- M_MOT2. Right now, I feel like giving up on this goal. (R)
- M_MOT3. I plan to do my next planned healthy action as usual.
- M_INTENT. How likely are you to do your next planned healthy action in the next 48 hours? (slider 0–100%)

## Section F — Post-feedback survey (repeat after each message)

Shown four times, once after each of Messages A–D. Instruction before each message: "Imagine your AI coach sent you this message right after the setback you described. Read it, then answer the questions." Keep the message visible on screen while they answer.

**Appraisal after this message** (1–7 agree; same constructs as Section M, needed for the H3 mediation test)

- F_STAB1. After reading this message, I think this kind of setback will keep happening to me.
- F_STAB2. After reading this message, I see this setback as a one-time thing. (R)
- F_CTRL1. After reading this message, I feel I can control whether this happens again.
- F_CTRL2. After reading this message, whether I slip again feels mostly out of my hands. (R)
- F_BLAME1. After reading this message, I feel this setback happened because of who I am.
- F_BLAME2. After reading this message, I see this setback as mostly caused by my situation that day. (R)
- F_COPE1. After reading this message, I know what I can do to get back on track.
- F_COPE2. After reading this message, I feel I have what it takes to recover.
- F_GLOB1. After reading this message, this setback feels like I am failing at my goal overall.

**Feelings after this message** (1 = Not at all, 7 = Very much)

- F_SHAME1. I feel like I am a bad or weak person.
- F_SHAME2. I want to hide or avoid thinking about my goal.
- F_GUILT1. I regret what I did and want to make up for it.

**Motivation after this message** (1–7 agree; primary outcome for H1 and H2)

- F_MOT1. This message makes me motivated to keep working on my goal.
- F_MOT2. This message makes me feel like giving up. (R)
- F_MOT3. After this message, I plan to do my next planned healthy action as usual.
- F_INTENT. After this message, how likely are you to do your next planned healthy action in the next 48 hours? (slider 0–100%)

**How the message came across** (1–7 agree; not matched to M, no change scores)

- F_TAIL1. This message responded to how I actually see my setback. (manipulation check)
- F_TAIL2. This message could have been sent to anyone. (R) (manipulation check)
- F_EMP1. This message felt understanding.
- F_WARM1. This message felt warm and supportive.
- F_JUDG1. This message felt judgmental. (R)
- F_HOLL1. This message felt hollow or too soft to take seriously. (R)
- F_HELP1. This message was helpful.
- F_CRED1. I would trust advice from a coach that writes like this.

**Open response**

- F_OPEN. What, if anything, about this message helped or bothered you? (open text, optional)

## Section Z — Final comparison, checks and debrief

**Comparing the four messages** (show all four side by side, labeled A–D)

- Z_RANK. Drag to rank the messages from most to least likely to keep you going on your goal. (stored as ranks 1–4 per message)
- Z_BEST. If you could get only one of these after every setback, which would you pick? A / B / C / D
- Z_WORST. Which message would most make you want to give up? A / B / C / D / None
- Z_WHY. Briefly, why did you pick your top message? (open text)

**Attention and quality checks**

- Z_ATTN2. What was the setback you wrote about mainly related to? Exercise / Eating habits / Sleep / Stress / Screen time / Other (flag if it differs from P_GOALTYPE)
- Z_HONEST. Did you answer honestly and pay attention throughout? Yes / No (your payment is not affected)

**Debrief** (shown after the last question)

Thank you. In this study the four messages were written by AI in four styles: neutral, strict, generally encouraging, and encouraging in a way tailored to how you described your setback. We are studying which style best helps people keep going after a slip. Setbacks are a normal part of any lifestyle change. If this study brought up difficult feelings about eating, exercise or yourself, please reach out to someone you trust or a health professional. This was a class project, and your responses will be deleted when the course ends. Questions: [team contact email].
