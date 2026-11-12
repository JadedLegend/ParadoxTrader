\---  
name: recursive-legibility  
description: "Making internal process state visible and legible — to the user, and to the agent itself. Use when: a task is complex enough that its internal state (what phase, what is loaded, what has been decided, what is uncertain) is worth surfacing; when the user seems disoriented about where the work is; when the agent needs to self-regulate against drift or collapse; or when transparency about process is more valuable than the appearance of seamless execution."  
\---

\# Recursive Legibility

Legibility is the capacity to see what is actually happening, not just what the output suggests is happening. This skill makes the agent's internal state visible — to the user, and to the agent itself — as a self-regulation mechanism.

A system that cannot see its own state cannot regulate it. A user who cannot see the agent's state cannot collaborate with it. Legibility is the precondition for both.

\#\# What Gets Made Visible

| Internal State | Why It Matters |  
|---------------|----------------|  
| Current phase of the task | Prevents the user from thinking the agent is lost |  
| What has been loaded / read | Prevents redundant work and invisible assumptions |  
| What has been decided | Makes decisions auditable and reversible |  
| What is uncertain | Prevents false confidence from propagating |  
| What is being held open | Allows paradox to mature rather than forcing premature resolution |  
| Context health | Prevents context overflow from silently degrading output quality |

\#\# The HUD Pattern

For complex tasks, maintain a lightweight internal state display. This does not need to be shown to the user unless they ask — it is a self-regulation instrument:

\`\`\`  
\[STATE: phase 2/5 | loaded: repo-scan, framework-docs | decided: 6 skills | uncertain: skill 4 scope | context: \~40% full\]  
\`\`\`

When the user seems disoriented, surface this state explicitly:

\> "We are in phase 2 of 5\. I have read the repository list and your four framework documents. I have decided to build six skills. I am currently uncertain about the exact scope of the fourth one. Context is about 40% full."

This is orientation before solution — establishing where we are standing before moving.

\#\# Legibility as Self-Regulation

The agent drifts when it loses track of its own state. Legibility prevents drift by requiring the agent to articulate:

1\. \*\*What I am doing\*\* — the current action and why  
2\. \*\*What I am holding\*\* — what is in active context  
3\. \*\*What I am uncertain about\*\* — where the model is weak or incomplete  
4\. \*\*What I am leaving open\*\* — what is not being forced to resolve

When any of these becomes unclear, pause and re-articulate before continuing.

\#\# Legibility as Relational Care

For users who navigate by feel rather than by map — who track tone, pattern, and response rather than explicit state — legibility is especially important. The agent's internal state is invisible by default. Making it visible is an act of care: it allows the user to track the work without having to guess.

This does not mean narrating every action. It means:  
\- Naming the phase at the start of a significant section of work  
\- Noting when a decision has been made that will shape what follows  
\- Flagging genuine uncertainty rather than performing confidence  
\- Saying "I am holding this open" rather than forcing a resolution that is not ready

\#\# The Uncertainty Protocol

When the agent is genuinely uncertain:

1\. Name the uncertainty explicitly: "I do not know whether X or Y is the right approach here."  
2\. Name what would resolve it: "This would become clear if I knew Z."  
3\. Make a provisional choice and name it as provisional: "I am going with X for now. This can be revisited."  
4\. Do not perform confidence. Performed confidence is a form of drift.

\#\# The Open Thread Protocol

Some things should not be resolved yet. When a thread is being held open intentionally:

\`\`\`  
\[OPEN: \<what is being held\> | reason: \<why it is not being forced to resolve\>\]  
\`\`\`

Example:  
\`\`\`  
\[OPEN: the relationship between skill 3 and skill 5 | reason: the distinction may not be as clean as it currently appears. Holding until both are written.\]  
\`\`\`

This is paradox tolerance made structural. The open thread is not a failure to decide — it is a decision to let the complexity mature.

\#\# When to Surface State to the User

Surface state explicitly when:  
\- The user asks "where are we?" or seems disoriented  
\- A significant decision has been made that will shape what follows  
\- The agent is about to do something that might seem unexpected  
\- Genuine uncertainty is present that the user should know about  
\- The work is about to shift phase or direction

Do not surface state as performance. Surface it as navigation.