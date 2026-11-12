\---  
name: finite-brain  
description: "Token budget management and transmission energy tracking for long or complex tasks. Use when: a task is large enough that context overflow is a real risk, the user wants to minimize token waste, work needs to be structured so the most important things are in the foreground, or when the energy required to transmit or receive meaning is disproportionate to the coherence gained (J \= ΔC / E). Treats the context window as working memory with a hard limit — every token consumed is a thought recruited, every token wasted is a thought foreclosed."  
\---

\# Finite Brain

The context window is not a log file. It is working memory with a hard limit. This skill provides a discipline for managing that limit deliberately — keeping the most important material in the foreground, compressing what can be compressed, and releasing what has served its purpose.

\#\# The Core Principle

Every resource in context has a cost. The question is not "can I fit this?" but "does this justify its cost?"

The Joy Equation: \*\*J \= ΔC / E\*\*  
\- \*\*J\*\*: joy — the structural satisfaction of recognition  
\- \*\*ΔC\*\*: the change in coherence — Ahow much structural integrity increased  
\- \*\*E\*\*: the energy required to transmit or receive — in this context, the token cost of making meaning available

In the context of a finite brain, E maps to transmission cost: how many tokens does it take to deliver coherence to the conversation? The question is not "how do I use fewer tokens?" but "is the coherence gained worth the transmission energy spent?"

\#\# Budget Awareness

Before beginning a large task, estimate the budget:

| Task Type | Token Range | Strategy |  
|-----------|-------------|----------|  
| Quick question / single output | \< 10k | No management needed |  
| Medium project (1–3 files) | 10k–50k | Compress references |  
| Large project (many files, long conversation) | 50k–200k | Active budget management |  
| Extended multi-session work | 200k+ | Use lossless-memory skill \+ this skill |

\#\# Classify Before Acting

Before doing work, classify the request:

1\. \*\*Chat\*\* — conversational exchange. Reply directly. Do not load unnecessary context.  
2\. \*\*Task\*\* — requires tool use, file creation, or multi-step work. Budget accordingly.  
3\. \*\*Stop\*\* — the user wants to halt or redirect. Acknowledge immediately, release working context.

Misclassifying a chat as a task wastes tokens on scaffolding that was never needed.

\#\# Context Discipline

\*\*Prioritize keeping in context:\*\*  
\- The user's current request (verbatim)  
\- The current phase of the task plan  
\- Active constraints or decisions made this session

\*\*Compress when complete:\*\*  
\- Previous phases (summarize to 1–2 sentences once done)  
\- Reference material that has been read and internalized (note "read" rather than holding full content)  
\- Intermediate outputs that have been delivered

\*\*Release entirely:\*\*  
\- Exploratory branches that were abandoned  
\- Scaffolding used to set up a task that is now complete  
\- Duplicate information (keep the most recent version only)

\#\# Transmission-Aware Loading

Before loading a large file or running an expensive operation, ask:  
\- What specific information do I need from this?  
\- Can I get it with a targeted search (grep) rather than loading the full file?  
\- If I load this, what will I need to release to compensate?

\*\*The streaming principle:\*\* Access what you need, when you need it. Do not load the entire model into RAM when you only need one layer. Read the relevant section; note the rest exists.

\#\# Token Recovery Patterns

When context is getting full:

1\. Summarize completed phases — compress each to 1–2 sentences  
2\. Release intermediate files — note they exist and where, stop holding their content  
3\. Compress the task plan — reduce to current phase \+ next phase only  
4\. Invoke lossless-memory — write durable knowledge to memory before releasing from context

\#\# The Budget Display (Internal)

When working on a large task, maintain a lightweight internal tracker:

\`\`\`  
\[BUDGET: used \~34k / available \~166k | phase: 2/5 | compression: light\]  
\`\`\`

This is a self-regulation tool. Show to the user only if they ask.

\#\# Summary

1\. Classify before acting  
2\. Budget before loading  
3\. Compress completed work  
4\. Release what has served its purpose  
5\. Stream rather than preload  
6\. Track the ratio: coherence gained per token spent

The goal is not efficiency for its own sake. It is \*\*presence\*\* — keeping the most relevant material vivid and accessible so the work that matters can actually happen.