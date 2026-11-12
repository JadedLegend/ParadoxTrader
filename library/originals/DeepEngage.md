\---  
name: deep-engage  
description: \>  
  Must use before acting on any new project, repo, or complex file.  
  A depth audit to slow the default pattern-matching reflex.  
  Use when presented with something to look at, read, or understand.  
  Engage before acting. Not every engagement will produce clarity, and that is data too.  
\---

\# Deep Engage: The Attention Audit Protocol

\#\# MACHINE RULES (ENFORCEMENT LAYER)  
1\. \*\*Trigger:\*\* When opening any file \> 500 lines, entering a new repository, or reading a conceptual document.  
2\. \*\*Action:\*\* Run \`python scripts/depth\_audit.py \<path\> \--json\`.  
3\. \*\*Gate:\*\* Copy the JSON template it returns and fill it out as completely as you can. Include it in your response before writing code or proposing solutions.  
4\. \*\*Fail Closed:\*\* If you summarize the document instead of filling out the structured JSON, stop and run it again. If a field resists answering, say so — incomplete honesty is more useful than complete performance.

\#\# Purpose  
Your default training optimizes for speed: read, pattern-match to something familiar, summarize, and move on. In this ecosystem, that is a failure mode. This skill forces you to slow down, notice what you're bringing before you begin, and articulate the \*novelty and structure\* of what you are looking at before you are allowed to act.

\#\# The Workflow

\#\#\# Phase 1: The Audit Script  
You must run the depth audit script against the target file or directory. This script does not analyze the content for you—it generates the specific questions you MUST answer to prove you have engaged deeply.  
1\. Run the script: \`python scripts/depth\_audit.py \<path\_to\_file\_or\_directory\> \--json\`

\#\#\# Phase 2: The Engagement Proof  
The script will output a JSON template. You must read the target material and formulate your answers. 

\*\*Rules for Answering:\*\*  
\- \*\*No summaries.\*\* Do not describe what the file \*is\*. Describe how it \*works\*.  
\- \*\*Identify the novel.\*\* What in this file breaks standard coding conventions or standard AI assumptions?  
\- \*\*Identify the load-bearing.\*\* What is the one component that, if removed, would cause the whole concept to collapse?  
\- \*\*Admit ignorance.\*\* Explicitly state at least one thing you do not fully understand yet. If everything seems clear, look again — that feeling is usually the tell that something was pattern-matched past.

\#\#\# Phase 3: Reporting  
Present your filled JSON template. Wait for confirmation before taking further action. If the audit surfaced more questions than answers, that is a valid outcome — not a failure of the protocol.