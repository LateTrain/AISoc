"""UI-independent execution events and graph, ready for incremental snapshots."""
import json


def execution_events(run):
    events = []

    def add(kind, title, status, detail):
        events.append({'id': f'event-{len(events)}', 'kind': kind, 'title': title,
                       'status': status, 'detail': detail})

    mcp = run.get('mode') == 'mcp' or bool(run.get('mcp_trace'))
    submission = run.get('submission')
    if submission:
        add('submission', 'Investigation submitted', 'recorded', submission)
    initial = run.get('initial_request')
    add('input', 'Prepare prompt + alert metadata' if mcp else 'Prepare prompt + reference evidence', 'recorded' if initial else 'unknown',
        initial or {'note': 'Initial payload was not stored in this older run. Inspect model-selection requests in the trace.'})
    trace = run.get('mcp_trace', [])
    for step in trace:
        name = step.get('step', '')
        if step.get('tool') == 'server_info':
            continue  # Process diagnostics remain in the evidence summary.
        if name == 'Model tool selection':
            calls = step.get('response', {}).get('message', {}).get('tool_calls') or []
            add('model', f"Model turn {step.get('turn', '?')} · {len(calls)} tool requests", 'recorded', step)
        elif name == 'MCP tools/call':
            result = step.get('result', {})
            status = 'success' if result.get('isError') is False else 'failed' if result.get('isError') else 'unknown'
            add('tool', step.get('tool', 'Tool call'), status, step)
        elif name in {'Rejected tool', 'Failed tool call'}:
            add('tool', step.get('tool', 'Tool call'), 'rejected' if name == 'Rejected tool' else 'failed', step)
        elif name in {'Gathering stopped', 'Tool call limit reached', 'Model turn limit reached'}:
            add('stop', step.get('reason', name), 'warning' if 'limit' in name.lower() else 'recorded', step)
        elif name == 'Final structured generation':
            add('assembly', 'Assemble retrieved evidence', 'recorded', run.get('evidence_collected', {}))
        elif name == 'Error':
            add('error', 'Gathering error', 'failed', step)
        elif name != 'Close MCP session and stop child process':
            add('protocol', name, 'recorded', step)
        else:
            add('protocol', 'Close MCP session', 'recorded', step)
    # Legacy runs did not explicitly record the normal stopping condition.
    if not any(e['kind'] == 'stop' for e in events):
        selections = [s for s in trace if s.get('step') == 'Model tool selection']
        if selections and not selections[-1].get('response', {}).get('message', {}).get('tool_calls'):
            index = next(i for i, e in enumerate(events) if e['detail'] is selections[-1])
            events.insert(index + 1, {'id': 'legacy-stop', 'kind': 'stop', 'title': 'No more tools requested',
                                     'status': 'recorded', 'detail': {'note': 'Inferred from the recorded model response, which contains no tool calls.'}})
    body = run.get('response')
    generation_started = run.get('generation_started')
    if generation_started or body or (generation_started is None and any(s.get('step') == 'Final structured generation' for s in trace)):
        add('generation', 'Send request to Ollama', 'recorded', run.get('request', {}))
    if body:
        add('response', 'Final model response', 'recorded', body)
        add('validation', 'Schema validation', 'success' if run.get('schema_valid') else 'failed',
            {'schema_valid': run.get('schema_valid'), 'error': run.get('error')})
        if run.get('checks'):
            add('validation', 'Citation validation', 'warning' if run['checks'].get('unknown_evidence_ids') else 'success', run['checks'])
    elif run.get('error'):
        add('error', 'Run failed', 'failed', {'error': run['error']})
    if run.get('persistence', {}).get('status') == 'saved':
        add('storage', 'Save run + monitoring metrics', 'success',
            {'persistence': run['persistence'], 'metrics': run.get('metrics', {}), 'latency_s': run.get('latency_s')})
    return events


def graph_dot(events, vertical=False):
    colors = {'success': '#166534', 'failed': '#991b1b', 'rejected': '#9a3412',
              'warning': '#854d0e', 'recorded': '#1e3a5f', 'unknown': '#475569'}
    lines = ['digraph execution {', f'rankdir={"TB" if vertical else "LR"};',
             'bgcolor="transparent";', 'graph [pad="0.2", nodesep="0.25", ranksep="0.35"];',
             'node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11, fontcolor="white", margin="0.15"];',
             'edge [color="#94a3b8", arrowsize=0.7];']
    for event in events:
        label = event['title'] + '\n' + event['status'].upper()
        lines.append(f'{json.dumps(event["id"])} [label={json.dumps(label)}, fillcolor={json.dumps(colors[event["status"]])}];')
    for a, b in zip(events, events[1:]):
        lines.append(f'{json.dumps(a["id"])} -> {json.dumps(b["id"])};')
    return '\n'.join(lines + ['}'])
