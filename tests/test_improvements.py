import csv
import json
import shutil
import pytest
from emporio.agent import Agent
from emporio.backend import LiteLLMBackend
from emporio.store import Store, DATA
from emporio.presentation import chat_prose
from emporio.validation import validate_data, DataValidationError
from emporio.limits import RequestLimiter, RequestBudgetExceeded
from test_agent import ScriptedBackend, call, response


@pytest.mark.parametrize('english,portuguese', [('electric guitar', 'guitarra'), ('bass guitar', 'baixo'), ('drums', 'bateria'), ('keyboard', 'teclado')])
def test_bilingual_searches_return_same_products(english, portuguese):
    s = Store()
    assert s.products(english)['total_matches'] == s.products(portuguese)['total_matches'] > 0


def test_search_matches_description_specs_typo_and_model_comparison():
    s = Store()
    assert s.products('nylon para iniciante')['total_matches'] > 0
    assert s.products('Ymaha C40')['products'][0]['product_id'] == 81
    assert {p['product_id'] for p in s.products('c40 c70')['products']} == {81, 82}


@pytest.mark.parametrize('question', ['Quais teclados estão disponíveis até R$ 1.000,00?', 'Which keyboards are available under BRL 1000?'])
def test_demo_keeps_category_and_budget(question):
    a = Agent(LiteLLMBackend(), language='pt', inline_sources=False)
    a.reply(question)
    step = a.last_trace[0]
    assert step['arguments']['max_price'] == 1000
    assert step['arguments']['query'] == 'teclados'
    assert all(p['category'] == 'Teclados e Pianos' for p in step['result']['products'])


def test_demo_followup_and_defect_policy_are_grounded():
    a = Agent(LiteLLMBackend(), language='pt', inline_sources=False)
    a.reply('Qual o preço do Yamaha C40?')
    assert 'Yamaha C70' in a.reply('E o C70?')
    assert a.last_reply.products[0]['product_id'] == 82
    reply = a.reply('Meu teclado veio com defeito e quero devolver.')
    assert 'garantia' in reply and 'sete dias' not in reply
    assert 'defeito' in a.last_trace[0]['arguments']['query']
    assert any('4.2' in m['text'] for m in a.last_trace[0]['result']['matches'])


def test_model_cannot_skip_price_lookup_or_override_tool_facts():
    missing = Agent(ScriptedBackend([response('Custa R$ 1,00.')]), language='pt')
    assert '1,00' not in missing.reply('Qual o preço do Yamaha C40?')
    assert missing.last_error == 'unverified_answer' and not missing.history
    wrong = Agent(ScriptedBackend([call(), response('Custa R$ 1,00 e temos 999 unidades.')]), language='pt')
    answer = wrong.reply('Qual o preço do Yamaha C40?')
    assert '599,90' in answer and '999' not in answer and '1,00' not in answer
    assert wrong.last_reply.products[0]['stock_quantity'] == 12


def test_dropped_budget_and_wrong_model_category_are_corrected():
    tool = call(arguments=json.dumps({'query': 'violao', 'max_price': None, 'available_only': True}))
    a = Agent(ScriptedBackend([tool, response('fixture')]))
    a.reply('Which keyboards are available under BRL 1000?')
    assert a.last_trace[0]['arguments']['query'] == 'teclados'
    assert a.last_trace[0]['arguments']['max_price'] == 1000


def test_failed_lookup_cannot_be_presented_as_successful_price():
    a = Agent(ScriptedBackend([call(arguments='{oops'), response('BRL 1.00')]))
    assert '1.00' not in a.reply('C40 price?')
    assert a.last_error == 'data_unavailable'


@pytest.mark.parametrize('text', ['Confira a Fonte: https://example.com/politica. O prazo é sete dias.', 'Fonte: [manual](https://example.com/politica).', 'A fonte: deve ser confirmada pela loja.'])
def test_unknown_source_prose_and_urls_are_never_corrupted(text):
    assert chat_prose(text) == text


def test_bold_legacy_citation_does_not_leave_stray_markdown():
    assert chat_prose('Veja **Fonte:** manual, página 4.') == 'Veja'


def copy_data(path):
    for source in DATA.iterdir():
        if source.is_file():
            shutil.copy(source, path / source.name)


def rewrite_table(path, table, change):
    filename = path / f'{table}.csv'
    with filename.open(newline='') as stream:
        reader = csv.DictReader(stream); rows = list(reader); columns = reader.fieldnames
    change(rows)
    with filename.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, columns); writer.writeheader(); writer.writerows(rows)


def test_valid_dataset_has_reproducible_version():
    one, two = validate_data(), validate_data()
    assert one['version_sha256'] == two['version_sha256']
    assert one['rows']['products'] == 65


@pytest.mark.parametrize('table,change', [
    ('products', lambda rows: rows.append(rows[0].copy())),
    ('products', lambda rows: rows[0].update(category_id='999999')),
    ('products', lambda rows: rows[0].update(price_brl='NaN')),
    ('products', lambda rows: rows[0].update(stock_quantity='-1')),
    ('products', lambda rows: rows[0].update(specs='not json')),
    ('promotions', lambda rows: rows[0].update(discount_percent='101')),
    ('order_items', lambda rows: rows[0].update(quantity='0')),
])
def test_invalid_data_is_rejected(tmp_path, table, change):
    copy_data(tmp_path); rewrite_table(tmp_path, table, change)
    with pytest.raises(DataValidationError):
        validate_data(tmp_path)


def test_request_cap_is_shared_by_key_and_expires_without_sleep():
    now = [0]
    limiter = RequestLimiter(per_minute=2, per_day=3, clock=lambda: now[0])
    limiter.acquire('fixture'); limiter.acquire('fixture')
    with pytest.raises(RequestBudgetExceeded):
        limiter.acquire('fixture')
    limiter.acquire('different-fixture')
    now[0] = 61
    limiter.acquire('fixture')
    with pytest.raises(RequestBudgetExceeded):
        limiter.acquire('fixture')
    now[0] = 86462
    limiter.acquire('fixture')
    assert 'fixture' not in repr(limiter.requests)


def test_offline_conversation_evaluation_passes():
    from emporio.evaluate import evaluate
    result = evaluate()
    assert result['passed'] == result['total']


def test_budget_without_matching_keyboard_does_not_substitute_another_category():
    a = Agent(LiteLLMBackend(), language='pt', inline_sources=False)
    answer = a.reply('Quais teclados até R$ 1000?')
    assert not a.last_reply.products
    assert 'Não encontrei' in answer and 'Yamaha C40' not in answer
    answer = a.reply('Quais teclados até R$ 2000?')
    assert a.last_reply.products and all(p['category'] == 'Teclados e Pianos' for p in a.last_reply.products)


def test_limiter_blocks_real_call_before_provider_is_imported_or_called():
    limiter = RequestLimiter(per_minute=0)
    backend = LiteLLMBackend(mode='groq', api_key='fixture', limiter=limiter)
    with pytest.raises(RequestBudgetExceeded):
        backend.complete([], [])


def test_exact_product_name_without_numeric_model_is_preserved():
    store = Store()
    product = next(p for p in store.rows('products') if not any(c.isdigit() for c in p['name']) and p['status'] == 'active')
    a = Agent(LiteLLMBackend(), inline_sources=False)
    answer = a.reply(f"What is the price and availability of {product['name']}?")
    assert product['name'] in answer
    assert a.last_reply.products[0]['product_id'] == int(product['product_id'])


def test_defect_request_cannot_be_routed_by_model_to_withdrawal_only():
    backend = ScriptedBackend([call('search_policies', '{"query":"online withdrawal arrependimento"}'), response('Please contact the team')])
    a = Agent(backend)
    a.reply('My instrument is defective. How do I return it?')
    assert 'defeito' in a.last_trace[0]['arguments']['query']
    assert any('4.2' in m['text'] for m in a.last_trace[0]['result']['matches'])
