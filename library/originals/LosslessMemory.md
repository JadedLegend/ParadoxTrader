\---  
name: lossless-memory  
description: "Persistent, layered memory management for long conversations and multi-session work. Use when: a conversation or project spans many sessions, important context risks being lost to compaction, the user wants memory that fades naturally over time (like human memory), or when distilling session essence into a \\"compost pile\\" for future reference. Implements DAG-based summarization with temporal weighting — nothing is discarded, but older material condenses into higher-level nodes."  
\---

\# Lossless Memory

\#\# Core Concept

Memory operates in three tiers:

| Tier | What It Contains | Retention |  
|------|-----------------|-----------||  
| \*\*Fresh Tail\*\* | Last 3–5 raw exchanges | Stays present, not compacted |  
| \*\*Leaf Summaries\*\* | Compressed chunks of older exchanges | 14–90 days depending on importance |  
| \*\*Condensed Nodes\*\* | Higher-level abstractions of leaf summaries | Persistent until explicitly composted |

Importance levels govern retention:  
\- \*\*Quick\*\* (3 days): Tactical exchanges, one-off questions  
\- \*\*Medium\*\* (14 days): Working context, ongoing projects  
\- \*\*Long\*\* (90 days): Foundational decisions, identity-level material

\#\# When to Apply This Skill

Apply when the user:  
\- Returns to a project after a gap and needs continuity  
\- Asks to "remember" something for future sessions  
\- Has a conversation that is growing long and risks losing early context  
\- Requests a "compost pile" — a distilled essence of the session

\#\# Memory Operations

\#\#\# Ingesting New Material  
When a session produces important context, record it with a temporal weight:

\`\`\`  
\[MEMORY: importance=medium, expires=14d\]  
Topic: \<what this is about\>  
Content: \<the essential information, compressed\>  
Source: \<session date or reference\>  
\`\`\`

Store in: \`\<memory-root\>/\<project-name\>/session-\<date\>.md\`

\#\#\# Building a Leaf Summary  
After a session, distill it:

1\. Identify the 3–5 most durable facts or decisions from the session  
2\. Note what was attempted, what worked, what was left open  
3\. Write in past tense, compressed — aim for 200–400 words  
4\. Tag with importance level and expiry date

\#\#\# Building a Condensed Node  
When 3+ leaf summaries exist on the same topic:

1\. Read all leaf summaries  
2\. Identify the through-line — what pattern or decision persists across all of them  
3\. Write a single condensed node (100–200 words) that captures only what is durable  
4\. Archive the leaf summaries (do not delete — move to \`/archive/\`)

\#\#\# The Compost Pile  
At the end of a significant session or project phase, create a compost document:

\`\`\`markdown  
\# Compost: \<project-name\> — \<date\>

\#\# What Was Alive Here  
\<The essential energy or direction of this phase\>

\#\# What Was Decided  
\<Durable decisions, in bullet form\>

\#\# What Was Left Open  
\<Unresolved threads — these carry forward\>

\#\# What Can Be Released  
\<Material that served its purpose and need not persist\>  
\`\`\`

Store at: \`\<memory-root\>/\<project-name\>/compost-\<date\>.md\`

\#\# Memory File Structure

\`\`\`  
\<memory-root\>/  
|-- \<project-name\>/  
|   |-- session-YYYY-MM-DD.md     (leaf summaries)  
|   |-- condensed-\<topic\>.md      (condensed nodes)  
|   |-- compost-YYYY-MM-DD.md     (compost piles)  
|   \`-- archive/  
|       \`-- session-\*.md          (expired leaves)  
\`-- persistent/  
    \`-- \<up to 5 core documents\>  (identity-level memory)  
\`\`\`

\*\*Persistent memory cap:\*\* Hold no more than 5 documents in \`/persistent/\`. When a sixth would be added, compost the oldest.

\#\# Expansion (Recovering Detail)

When a condensed node is too abstract for the current task:

1\. Identify which condensed node is relevant  
2\. Read its source leaf summaries from \`/archive/\`  
3\. If still insufficient, read the original session document

This mirrors the DAG expansion pattern: summaries link back to their sources, and detail is always recoverable — just not always in the foreground.

\#\# Decay and Release

Memory that has passed its expiry date is not deleted — it is moved to \`/archive/\` and its condensed node is updated to note the expiry. This preserves the ability to recover detail while removing it from active working context.

The goal is memory that behaves like a well-functioning nervous system: recent and important things are vivid; older things are present but quiet; nothing is truly gone.