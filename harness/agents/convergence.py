"""Persistent-session convergence loop with controller-only boolean evaluation.

The evaluator is called only while Pi is settled. It must evaluate an isolated
snapshot, keep tests/logs outside the agent bundle, honor the remaining timeout,
and return an actual bool. Infrastructure errors must raise, never return False.
"""
import json
from pathlib import Path
import re
import time

from harness.agents.baseline import PROTOCOL, QUESTION_PARSER_VERSION, extract_question
from harness.agents.rpc import RunError, rpc_session
from harness.agents.wasabi_ui import WasabiDialog
from harness.sandbox.docker import container_command
from harness.simulator.user import LIMIT_REPLY
from harness.tasks.schema import Setting

FAILURE_FEEDBACK = (
    "The implementation does not yet meet the requirements. "
    "Please review and revise it. Ask questions if you need more information."
)


def run_rpc(command, task, simulator, log_path, *, evaluate, wasabi_model=None,
            approve=False, timeout=1800, max_submissions=5, coding_question_limit=3,
            detailed_logging=True):
    """evaluate(submission_number, remaining_seconds) -> bool (controller only).

    No evaluation output is passed to the simulator. A single session/workspace
    survives submissions. The total deadline includes evaluation and user replies.
    wasabi_model=None selects baseline mode (the command must disable extensions).
    """
    if max_submissions < 1 or coding_question_limit < 0:
        raise ValueError('Invalid submission or question limit')
    if simulator.max_turns is not None:
        raise ValueError('Use an unlimited simulator; coding replies have a separate budget')
    started = time.monotonic()
    initial_turns = simulator.turns
    submissions, questions, dialogs = [], [], []
    coding_replies = feedback_count = turn = 0
    limit_sent = False
    previous_coding = previous_wasabi = 0
    adapter = WasabiDialog(simulator, approve=approve) if wasabi_model else None
    with rpc_session(command, log_path, timeout) as rpc:
        rpc.detailed_logging = detailed_logging
        def remaining():
            value = rpc.deadline - time.monotonic()
            if value <= 0:
                raise RunError('Convergence run timed out')
            return value

        def send_prompt(text):
            nonlocal turn
            remaining()
            turn += 1
            ident = f'task-{turn}'
            rpc.send(dict(id=ident, type='prompt', message=text))
            return ident

        prompt = PROTOCOL + task.agent_input(Setting.INTERACTION)['problem_statement']
        configured = False
        prompt_id = None
        if wasabi_model:
            rpc.send(dict(id='setup', type='prompt', message='/wasabi-model ' + wasabi_model))
        else:
            prompt_id = send_prompt(prompt)
        accepted = settled = False
        final_text = ''
        while True:
            event = rpc.receive()
            kind = event.get('type')
            if kind == 'extension_ui_request':
                if adapter is None:
                    raise RunError('Unexpected baseline extension dialog')
                if event.get('method') == 'notify' and event.get('message') == 'Wasabi model: ' + wasabi_model:
                    configured = True
                response = adapter.respond(event)
                if response is not None:
                    rpc.send(response)
            elif kind == 'response' and event.get('id') == 'setup':
                if not event.get('success') or not configured or prompt_id is not None:
                    raise RunError('Wasabi model selection failed')
                prompt_id = send_prompt(prompt)
            elif kind == 'response' and prompt_id is not None and event.get('id') == prompt_id:
                if not event.get('success') or event.get('data', {}).get('disposition') != 'started':
                    raise RunError('Prompt did not start coding')
                accepted = True
            elif kind == 'message_end':
                message = event.get('message', {})
                if message.get('role') == 'assistant':
                    if message.get('stopReason') in ('error', 'aborted'):
                        raise RunError('Coding assistant failed')
                    final_text = ''.join(p.get('text', '') for p in message.get('content', [])
                                         if p.get('type') == 'text').strip()
            elif kind == 'agent_settled':
                settled = True
            if not (accepted and settled):
                continue
            if not final_text:
                raise RunError('Assistant settled without final text')
            parsed = extract_question(final_text)
            if parsed is not None:
                if limit_sent:
                    raise RunError('Agent asked again after the reply limit notice')
                question, prefix, suffix = parsed
                rpc.record('question_parse', dict(parser_version=QUESTION_PARSER_VERSION,
                           raw_text=final_text, question=question,
                           ignored_prefix=prefix, ignored_suffix=suffix))
                limit_sent = coding_replies >= coding_question_limit
                answer = LIMIT_REPLY if limit_sent else simulator.reply(question)
                if not limit_sent:
                    coding_replies += 1
                questions.append(dict(question=question, answer=answer, limit_reached=limit_sent)
                                 if detailed_logging else dict(limit_reached=limit_sent))
                rpc.record('coding_interaction', questions[-1])
            else:
                number = len(submissions) + 1
                evaluation_started = time.monotonic()
                passed = evaluate(number, remaining())
                if type(passed) is not bool:
                    raise RunError('Evaluator must return bool; evaluation errors must raise')
                remaining()
                wasabi_replies = simulator.turns - initial_turns - coding_replies
                submissions.append(dict(number=number, passed=passed,
                                        coding_replies=coding_replies - previous_coding,
                                        wasabi_replies=wasabi_replies - previous_wasabi,
                                        cumulative_coding_replies=coding_replies,
                                        cumulative_wasabi_replies=wasabi_replies,
                                        seconds=time.monotonic() - started,
                                        evaluation_seconds=time.monotonic() - evaluation_started))
                previous_coding, previous_wasabi = coding_replies, wasabi_replies
                rpc.record('submission', submissions[-1])
                if passed or number >= max_submissions:
                    break
                answer = FAILURE_FEEDBACK
                feedback_count += 1
            if adapter is not None:
                dialogs.extend(adapter.log)
                adapter = WasabiDialog(simulator, approve=approve)
            accepted = settled = False
            final_text = ''
            prompt_id = send_prompt(answer)
        if adapter is not None:
            dialogs.extend(adapter.log)
        result = dict(status='resolved' if passed else 'submission_limit',
                      submissions=submissions, coding_interactions=questions,
                      coding_simulator_replies=coding_replies,
                      wasabi_simulator_replies=simulator.turns - initial_turns - coding_replies,
                      feedback_count=feedback_count, interactions=dialogs if detailed_logging else [],
                      seconds=time.monotonic() - started,
                      interaction_protocol='convergence-v1',
                      question_parser_version=QUESTION_PARSER_VERSION,
                      max_submissions=max_submissions, coding_question_limit=coding_question_limit,
                      wasabi_model=wasabi_model, timeout=timeout)
        rpc.record('result', result)
        return result


def run_container(bundle, task, simulator, log_path, *, evaluate,
                  agent_provider, agent_model, wasabi_model=None, approve=False,
                  timeout=1800, max_submissions=5, coding_question_limit=3,
                  image='wasabi-pi:1.4.0-wasabi-614a531', network=False,
                  env_names=(), models_file=None, detailed_logging=True):
    """Launch baseline or Wasabi; evaluator artifacts must stay outside bundle."""
    for value in (agent_provider, agent_model, *([wasabi_model] if wasabi_model else [])):
        if not re.fullmatch(r'[A-Za-z0-9_.:/-]+', value) or value.startswith('-'):
            raise ValueError('Invalid model or provider identifier')
    if wasabi_model and '/' not in wasabi_model:
        raise ValueError('Wasabi model must be provider/model')
    bundle = Path(bundle).resolve()
    if json.loads((bundle / 'agent-input.json').read_text()) != task.agent_input(Setting.INTERACTION):
        raise ValueError('Bundle input does not match selected task')
    log = Path(log_path).resolve()
    if log.is_relative_to(bundle):
        raise ValueError('Controller log must not be inside the agent bundle')
    args = ['--provider', agent_provider, '--model', agent_model]
    if not wasabi_model:
        args = ['--mode', 'rpc', '--no-session', '--no-extensions', '--no-skills',
                '--no-prompt-templates', '--no-themes', '--no-context-files', *args]
    if not network:
        args.append('--offline')
    command = container_command(bundle, args, image=image, network=network,
                                env_names=env_names, models_file=models_file)
    command[2:2] = ['-i'] if wasabi_model else ['-i', '--entrypoint', '/opt/runtime/node_modules/.bin/pi']
    return run_rpc(command, task, simulator, log, evaluate=evaluate,
                   wasabi_model=wasabi_model, approve=approve, timeout=timeout,
                   max_submissions=max_submissions, coding_question_limit=coding_question_limit,
                   detailed_logging=detailed_logging)
