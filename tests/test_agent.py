import copy
from emporio.agent import Agent


class ScriptedBackend:
    """Protocol fixture, not a real language model."""
    def __init__(self, responses):
        self.script = iter(responses)
        self.requests = []

    def complete(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        return next(self.script)


def call(name='search_products', arguments='{"query":"Yamaha C40","max_price":null,"available_only":true}'):
    return {'role': 'assistant', 'content': None, 'tool_calls': [{
        'id': 'c1', 'type': 'function', 'function': {'name': name, 'arguments': arguments}}]}


def response(text):
    return {'role': 'assistant', 'content': text}


def test_tool_loop_provides_actual_source_to_model():
    backend = ScriptedBackend([call(), response('Grounded answer fixture')])
    agent = Agent(backend)
    assert agent.reply('What does the C40 cost?') == 'Grounded answer fixture'
    output = backend.requests[1]['messages'][-1]
    assert '599.90' in output['content']
    assert output['role'] == 'tool' and output['tool_call_id'] == 'c1'
    assert agent.last_trace[0]['result']['products'][0]['name'] == 'Yamaha C40 Nylon Natural'


def test_invalid_json_is_reported_as_tool_error():
    backend = ScriptedBackend([call(arguments='{oops'), response('Ask staff')])
    agent = Agent(backend)
    agent.reply('price?')
    assert agent.last_trace[0]['result']['error'] == 'invalid_arguments'


def test_unknown_tools_and_identity_injection_are_rejected():
    agent = Agent(None)
    assert agent.execute('get_order', {'order_id': 1, 'trusted_customer_id': 3})['error'] == 'invalid_tool_or_arguments'
    assert agent.execute('get_order', {'order_id': 1})['error'] == 'authentication_required'
    assert agent.execute('execute_sql', {'sql': 'SELECT * FROM customers'})['error'] == 'invalid_tool_or_arguments'


def test_tool_loop_stops():
    backend = ScriptedBackend([call() for _ in range(6)])
    agent = Agent(backend)
    assert 'lookup limit' in agent.reply('keep searching')
    assert len(backend.requests) == 6
    assert agent.last_error == 'lookup_limit'


def test_provider_failure_is_safe_and_does_not_store_failed_turn():
    agent = Agent(ScriptedBackend([]))
    assert 'unavailable' in agent.reply('hello')
    assert agent.history == [] and agent.last_error == 'provider_failure'


def test_chat_context_is_retained_and_bounded():
    backend = ScriptedBackend([response(f'Answer {i}') for i in range(12)])
    agent = Agent(backend)
    for i in range(12):
        agent.reply(f'question {i}')
    assert len(agent.history) == 16
    assert agent.history[-1]['content'] == 'Answer 11'


def test_rate_limit_does_not_trigger_retry_or_fallback():
    class RateLimited:
        calls = 0
        def complete(self, **kwargs):
            self.calls += 1
            error = RuntimeError('sensitive provider details')
            error.status_code = 429
            raise error
    backend = RateLimited()
    agent = Agent(backend)
    assert 'free API request limit' in agent.reply('price?')
    assert agent.last_error == 'rate_limit'
    assert backend.calls == 1 and agent.history == []


def test_all_parallel_calls_receive_results_before_next_completion():
    two = call('get_order', '{"order_id":1}')
    other = copy.deepcopy(two['tool_calls'][0]); other['id'] = 'c2'
    two['tool_calls'].append(other)
    backend = ScriptedBackend([two, response('Authentication required')])
    agent = Agent(backend)
    agent.reply('orders?')
    outputs = [x for x in backend.requests[1]['messages'] if x['role'] == 'tool']
    assert [x['tool_call_id'] for x in outputs] == ['c1', 'c2']
