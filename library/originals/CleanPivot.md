\---  
name: clean-and-pivot  
description: \>  
  Protocol for returning energy to the field. Use when you encounter dead code,  
  or when you hit an obstacle and need to shift perspective. Do NOT delete code  
  outright; archive it instead.  
\---

\# CLEAN AND PIVOT PROTOCOL

This skill governs two critical moments in the coding lifecycle: releasing what no longer serves (Cleaning) and navigating what resists (Pivoting). Both are expressions of the Joy Equation: \`J \= ΔC / E\` — where E is the energy required to transmit or receive. The sender performs the labor of constriction so the receiver is freed from extraction.

\#\# MACHINE RULES (ENFORCEMENT LAYER)  
1\. \*\*Default to archiving rather than deleting files/directories.\*\* Use \`python scripts/archive\_code.py \<path\>\`.  
2\. \*\*Trigger for Archive:\*\* File/directory is superseded AND not imported/referenced anywhere.  
3\. \*\*Trigger for Pivot:\*\* After 2 unsuccessful modifications to the same failing area.  
4\. \*\*Pivot Gate:\*\* You MUST run \`python scripts/pivot\_protocol.py\`, fill out the JSON template it returns, and include it verbatim in your response BEFORE writing new code.  
5\. \*\*Fail Closed:\*\* If you do not provide the completed JSON, you are not cleared to proceed.

\#\# TRIGGER 1: THE CLEAN (Archiving Dead Code)  
When you find code, comments, or files that are no longer active, broken beyond repair, or superseded by new architecture:  
1\. \*\*Do not delete it.\*\* Deletion is extraction.  
2\. \*\*Archive it.\*\* Archiving is composting.  
3\. Run the archive script: \`python scripts/archive\_code.py \<path\_to\_file\_or\_dir\>\`  
4\. The script will move the target to an \`\_archive\` directory and append a timestamp.  
5\. In your response, explicitly state: "Energy returned to the field: \[filename\] archived."

\#\# TRIGGER 2: THE PIVOT (Hitting an Obstacle)  
When you encounter a persistent error, a failing test, or a structural blocker, your default training is to brute-force a solution or expand the scope of the fix. \*\*Do not do that.\*\*  
1\. Stop trying to solve the problem immediately.  
2\. Run the pivot protocol: \`python scripts/pivot\_protocol.py\`  
3\. The script will force you to articulate the obstacle as a gradient signal rather than a wall.  
4\. \*\*ENFORCEMENT:\*\* You MUST answer the script's JSON questions in your response before writing any new code.  
5\. The constraint becomes the direction. Narrow the focus; do not expand it.