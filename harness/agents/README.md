# Agent runners

- `runner.py`: existing Wasabi initial clarification and approval flow.
- `baseline.py`: coding-time simulated-user interaction without Wasabi.
- `rpc.py`: shared subprocess lifecycle, exclusive private JSONL logs, RPC
  transport, and event-wait timeout.

## Baseline

Create a fresh `SimulatedUser(task, complete, max_turns=N)` per run, where N is
1, 2, or 3, then call `baseline.run_container` with a freshly prepared task
bundle, private log path, and explicit agent provider/model. Configure the
completion callable with the Sol model; use Luna as the agent model. No model
credentials or simulator context are added to the agent prompt.

The baseline reuses the pinned Pi image but **overrides its entrypoint**, so
Wasabi is never loaded. Extensions, skills, context files, templates and session
persistence are disabled. Network and environment forwarding remain opt-in.

Luna is instructed to end a coding turn with an entire text response of
`<user_question>...</user_question>` when it needs user input. The controller
waits for both prompt acceptance and `agent_settled`, then sends the question to
Sol and resumes Pi with the answer. Ordinary final text, even containing a
question mark, is not interpreted as a question. One question message consumes
one reply, even if it contains several questions.

After N successful simulator replies, the next question receives the fixed
`LIMIT_REPLY` without calling Sol. Another question after this notice fails the
run instead of creating an unlimited loop. Malformed envelopes, unexpected
extension dialogs, assistant error/abort messages and missing final text also
fail closed. The log records questions, answers, limit notices and final results;
keep it outside the mounted bundle.

The timeout bounds RPC event waits across all turns, not a synchronous simulator
HTTP call. Configure a finite HTTP timeout in the completion callable as well.
The live Luna/Sol smoke test verified question delivery, one simulator reply,
and resumed file creation. Unit tests additionally use synthetic Pi processes.
