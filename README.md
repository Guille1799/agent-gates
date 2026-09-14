# agent-gates

[![CI](https://github.com/Guille1799/agent-gates/actions/workflows/ci.yml/badge.svg)](https://github.com/Guille1799/agent-gates/actions/workflows/ci.yml)

**Gates around an autonomous coding agent.** Four small, self-contained tools that answer the
questions you have to ask *before* an agent is allowed to act and *after* it has acted — and that
nobody asks until something goes wrong.

They were extracted from a private system where four autonomous agents commit code every night.
Every one of them exists because of a specific failure, and the docstring of each says which.

| tool | the question it answers |
|---|---|
| `bin/puede_entrar.py` | **Can the agent even get in?** Exit 0 yes, 1 no — and if it cannot, *the night is not spent*. |
| `bin/el_gate_se_cayo_solo.py` | **Did the gate fail because of the agent's commit, or did it fall on its own?** This is the question that decides whether to revert. |
| `bin/puerta_de_la_cola.py` | **The only legitimate way to write to the shared queue.** Born the night a robot and a human session closed the same task at the same time. |
| `bin/stop_gate_mcp.py` | **Blocks the session from closing** while a retrieval-quality regression is open. |

`576` lines of tool, `~700` lines of test. **Only the Python standard library** — no dependencies.

```
python -m pytest tests/ -q
```

## Two things this repo tells you about itself

**1 · Half of two tests was removed, on purpose, and it is marked in the files.**

In the system they come from, the tests for `puede_entrar` and `el_gate_se_cayo_solo` check two
things: that the tool works, **and that something actually calls it** on the daily round. The second
half cannot travel without bringing a 10,000-line acceptance harness that describes a private
repository, so it was cut. Each file carries a block saying exactly what was removed and why.

That second half is not decoration. It exists because of a failure measured on 2026-09-05: *a piece
that existed, passed its own contract, and nobody called it.* **A mechanism that is written but not
wired reads exactly like one that works.**

**2 · The suite was flaky on the packaging machine, and CI settled why.**

Five consecutive runs of the same command on the machine these were extracted from:
`4 failed · 0 · 4 · 0 · 3`. The failures landed only on the tests that spawn subprocesses, they
failed in `0.25s` where a passing run took `1.33s`, and the error was
`OSError: [WinError 6] The handle is invalid`.

The obvious reading was *“Windows cannot do this”*. **That reading was wrong, and CI is how we
know**: `windows-latest` runs the same suite green, alongside Linux on 3.10, 3.12 and 3.14. The
flakiness belongs to one sandboxed environment, not to the platform.

This is left written down rather than quietly deleted, because it is the same question the repo
is about. **`bin/el_gate_se_cayo_solo.py` exists to answer exactly this**: it re-runs the failing
tests and reports `0` if they pass again (it fell on its own) or `1` if they still fail (revert).
A green reached by retrying is not the same as a green — and telling the two apart is the point.

## Origin

Extracted on 2026-09-14 from a private multi-agent system. Nothing here has been rewritten for
display: the code, the tests and the docstrings are the ones that run in production, minus the two
declared cuts above. Comments and docstrings are in Spanish, which is the language they were
written in.
