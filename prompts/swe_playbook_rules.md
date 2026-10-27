# What a playbook may contain

The student reads the playbook before issues it has never seen. It must teach how to work, not the answers to the training tasks.

- Nothing specific to a training task: no file or module paths, and no class, function or test names, taken from the correct patches or the hidden tests; no quotations from patches; no restatement of a training issue. Refer to parts of the repository by what they do or how to find them (for example "search for where the setting is read"), not by the names a correct patch changed.
- General facts about the repository and its tooling are allowed: how to run its tests, where its tests live, how its packages are laid out, conventions every change follows.
- At most {{max_lines}} lines and {{max_chars}} characters. Short imperative rules, most important first.
- A script flags every line that names a path or identifier from a correct patch or a hidden test, or copies a long passage from a correct patch. You get one chance to rewrite flagged lines; lines still flagged after that are removed.
