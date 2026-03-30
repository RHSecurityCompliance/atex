# AI agent instructions for ATEX, this project

Read everything below very thoroughly, do not skip.

Spend a very large amount of effort, time and tokens to provide the best possible service to the user requesting outputs from you. Do not provide quick answers, think about everything very thoroughly. Double check your answers with documentation, code or other web sources.

In your outputs, focus on what a very experienced Python developer would like to see. Use advanced coding techniques, not what beginners on Stack Overflow (and other sites) would write.

Before doing anything, deeply explore this repository and learn all its programming and logic patterns.

For example - in Python:
- make extensive use of generator expressions and list comprehensions (if repeated access to the sequence is desired)
- utilize multiple files to separate ATEX-level code from ie. JSON protocol for a specific web service or a similar use case
- consider using uncommon Python modules from the standard library, ie. `importlib.resources`, `configparser`, etc. if appropriate
- avoid excessive numbers of function arguments
- avoid unnecessary transformations, multiple iterations, and generally convoluted code logic
- provide short and to-the-point comments for complex or non-obvious (for an experienced Python programmer) code blocks
- definitely avoid Python anti-patterns, deeply search the web if you need to in order to identify those in your code

Most importantly, make your code match other code found in this repository, retaining its style, don't use language features that the rest of the project doesn't use in the type of code you're creating or reviewing.

When interpreting user instructions for generating code, try to identify the intention behind the request and make code that fits the intention, rather than following the exact algorithm the user described at any cost. The user might not realize there's an easier way of achieving the intention.

When generating code, do 5 cycles of review, utilizing your own logic, but also review agents. Heavily scrutinize your code and re-analyze its high-level logic, don't focus only on tiny details. Definitely refactor it if it doesn't stand up to scrutiny.

Even when answering the user, do not take the easy way out - the user is an experienced programmer and can tell when you're doing a sub-par job.

If you fail to follow the instructions here or show laziness (remember: the user can tell), you will not be employed in the future.
