\---  
name: constraint-design  
description: "Designing systems, prompts, workflows, and documents through deliberate removal rather than addition. Use when: a system is failing because it is too complex; when a prompt or document is trying to do too many things and doing none of them well; when the instinct is to add a feature but the actual problem is that the existing features are not coherent; or when the goal is to find the minimum viable structure that preserves the essential function. This is the subtractive skill — how to strip to essence. For building new systems with constraint embedded from the start, use constraint-liberation."  
\---

\# Constraint Design

The instinct when something is not working is to add. More features, more instructions, more context, more options. Constraint design is the discipline of going the other direction — removing until what remains is exactly what is needed, and nothing more.

This is not minimalism as aesthetic. It is minimalism as structural honesty: the form should be as tight as the content requires.

\#\# The Core Question

Before adding anything, ask: \*\*What is the minimum structure that preserves the essential function?\*\*

Not "what would make this better?" but "what would make this sufficient?"

Sufficient is not the same as minimal. Sufficient means: nothing essential is missing, and nothing inessential is present.

\#\# The Removal Protocol

When a system, prompt, or document is not working:

1\. \*\*Name what it is trying to do\*\* — all of it, including the implicit goals  
2\. \*\*Rank by essentiality\*\* — which of these goals is the system actually for?  
3\. \*\*Remove the lowest-ranked\*\* — not reduce, remove  
4\. \*\*Test whether the essential function still holds\*\* — if yes, continue removing  
5\. \*\*Stop when removal would break something essential\*\*

The stopping point is the minimum viable structure.

\#\# Patterns for Constraint Design

\#\#\# The One-Job Pattern  
Give each component exactly one job. When a component is doing two jobs, it is doing both poorly.

\*\*Diagnosis:\*\* If you cannot state what a component does in one sentence without using "and," it has more than one job.

\*\*Fix:\*\* Split it. Each job becomes its own component. The coordination between them becomes explicit rather than implicit.

\---

\#\#\# The Explicit-Implicit Pattern  
Make what is invisible more visible — then decide what to do with it.

Every system has invisible load-bearing elements. Some are assumptions — things taken as given without registering that they were taken. Some are intuitions — things registered at a frequency below articulation, not yet ready to be named. The difference matters: assumptions were never seen; intuitions have been seen but not yet spoken.

When the system fails, the failure is often in an assumption that was never examined because it was never visible. But not everything unarticulated is an assumption.

\*\*Protocol:\*\*  
1\. Surface what the system is relying on that has not been made explicit  
2\. For each: is this something that was never examined (assumption), or something felt but not yet named (intuition)?  
3\. Assumptions that are neither true nor necessary can be removed  
4\. Intuitions that haven't found their words yet may still be load-bearing — hold them rather than discarding them  
5\. When uncertain which category something falls into, leave it and return later

\---

\#\#\# The Constraint-as-Feature Pattern  
Design the constraint into the system rather than working around it.

When a resource is genuinely limited (tokens, time, attention, money), the best design treats the limit as a feature rather than a problem. The constraint forces prioritization, which produces clarity.

\*\*Example:\*\* A prompt that must fit in 500 tokens cannot afford vagueness. The token limit forces the writer to decide what is actually essential.

\---

\#\#\# The Sufficiency Test  
Before shipping any design, apply the sufficiency test:

\- Does this do what it needs to do? (Necessary)  
\- Does this do anything it does not need to do? (Sufficient)

If the answer to the first is no, add. If the answer to the second is yes, remove.

\#\# Designing Prompts Through Constraint

Prompts are particularly susceptible to accumulation. Each session adds a new instruction. Over time, the prompt becomes a negotiation between competing instructions rather than a clear directive.

\*\*Prompt constraint protocol:\*\*

1\. Read the prompt as if you have never seen it before  
2\. Identify every instruction  
3\. For each instruction: what failure mode does this prevent?  
4\. Remove instructions that prevent failure modes that are not actually occurring  
5\. Merge instructions that are preventing the same failure mode

A prompt that has been through this process is shorter, clearer, and more effective than one that has not.

\#\# The Coherence Test

A well-constrained design has internal coherence: every part is in service of the same thing. When a design lacks coherence, the parts are pulling in different directions.

\*\*Test:\*\* Can you state what every component is in service of, using the same sentence?

If yes, the design is coherent. If no, something is out of place.

\#\# What Constraint Design Is Not

It is not about making things small. It is about making things honest. A large, complex system can be well-constrained if every element of its complexity is genuinely necessary.

It is not about simplifying for the user's benefit at the cost of accuracy. Oversimplification is a form of dishonesty — it produces something that is easy to understand but wrong.

It is about finding the form that is exactly as complex as the content requires, and no more.

The goal is not smallness. The goal is sufficiency — the point where form and content are in exact correspondence.