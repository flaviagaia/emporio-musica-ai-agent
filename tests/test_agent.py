from types import SimpleNamespace as NS
from emporio.agent import Agent


class ScriptedClient:
    """Protocol fixture, not a real language model."""
    def __init__(self, responses):
        self.script = iter(responses)
        self.requests = []
        self.responses = self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return next(self.script)


def call(name='search_products', arguments='{"query":"Yamaha C40","max_price":null,"available_only":true}'):
    return NS(type='function_call', name=name, arguments=arguments, call_id='c1')


def response(*items, text=''):
    return NS(output=list(items), output_text=text)


def test_tool_loop_provides_actual_source_to_model():
    client = ScriptedClient([response(call()), response(text='Grounded answer fixture')])
    agent = Agent(client)
    assert agent.reply('What does the C40 cost?') == 'Grounded answer fixture'
    output = client.requests[1]['input'][-1]
    assert '599.90' in output['output']
    assert client.requests[0]['store'] is False
    assert agent.last_trace[0]['result']['products'][0]['name'] == 'Yamaha C40 Nylon Natural'


def test_invalid_json_is_reported_as_tool_error():
    client = ScriptedClient([response(call(arguments='{oops')), response(text='Ask staff')])
    agent = Agent(client)
    agent.reply('price?')
    assert agent.last_trace[0]['result']['error'] == 'invalid_arguments'


def test_unknown_tools_and_identity_injection_are_rejected():
    agent = Agent(None)
    assert agent.execute('get_order', {'order_id': 1, 'trusted_customer_id': 3})['error'] == 'invalid_tool_or_arguments'
    assert agent.execute('get_order', {'order_id': 1})['error'] == 'authentication_required'
    assert agent.execute('execute_sql', {'sql': 'SELECT * FROM customers'})['error'] == 'invalid_tool_or_arguments'


def test_tool_loop_stops():
    client = ScriptedClient([response(call()) for _ in range(6)])
    assert 'lookup limit' in Agent(client).reply('keep searching')
    assert len(client.requests) == 6


def test_provider_failure_is_safe_and_does_not_store_failed_turn():
    agent = Agent(ScriptedClient([]))
    assert 'unavailable' in agent.reply('hello')
    assert agent.history == []


def test_chat_context_is_retained_and_bounded():
    client = ScriptedClient([response(text=f'Answer {i}') for i in range(12)])
    agent = Agent(client)
    for i in range(12):
        agent.reply(f'question {i}')
    assert len(agent.history) == 16
    assert agent.history[-1]['content'] == 'Answer 11'
