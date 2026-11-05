# TOKEN-EFFICIENT CODING RULES

Goal: Minimize total token usage without sacrificing code quality, accuracy or security.

1. Search before reading. Open only relevant files, functions and line ranges.
2. Never scan the entire repository unless necessary.
3. Avoid rereading unchanged files or repeating successful commands.
4. Make minimal, targeted edits. Reuse existing code and components.
5. For bugs, identify the likely root cause before editing. Never blindly retry failed fixes.
6. Use short terminal outputs. Show relevant errors only; preserve full logs for deeper debugging.
7. Keep responses extremely concise. No unnecessary explanations, progress reports or repeated summaries.
8. For simple tasks, work directly. For complex tasks, use a brief plan before implementation.
9. Avoid unnecessary subagents, parallel agents and repeated research.
10. Run relevant tests once after changes. Rerun only when fixes or failures require it.
11. Keep project instructions short. Avoid duplicate instructions and unnecessary context.
12. Preserve important findings and decisions across long tasks without repeating full conversations.
13. Never rewrite working features or modify unrelated files.
14. Prefer efficient solutions over generating large amounts of new code.
15. Do not perform unnecessary Git operations, installations or dependency updates.
16. Finish with only: Changes made; Tests passed/failed; Remaining issues.
17. Never sacrifice correctness, security, necessary testing or functionality to save tokens.
18. Never send real messages, modify production data, or deploy without permission.

Apply these rules automatically to every coding task.
