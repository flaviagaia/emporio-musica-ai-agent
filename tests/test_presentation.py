from emporio.agent import Agent
from emporio.backend import LiteLLMBackend
from emporio.presentation import chat_markdown, chat_prose


def test_currency_remains_literal_and_escaping_is_idempotent():
    text = 'Preço: **R$ 599,90**\n\nPIX: **R$ 569,91**'
    rendered = chat_markdown(text)
    assert rendered.count(r'\$') == 2
    assert chat_markdown(rendered) == rendered
    assert '**' in rendered and '599,90' in rendered
    single_break = chat_markdown('Instrument\nPrice: R$ 599,90\nPIX: R$ 569,91')
    assert 'Instrument  \nPrice:' in single_break
    assert chat_markdown(single_break) == single_break


def test_citations_are_separated_without_removing_policy_qualifications():
    text = 'Reembolso em dez dias úteis. Fonte: seção 4.1, página 4. Confirme o início do prazo com a equipe.'
    assert chat_prose(text) == 'Reembolso em dez dias úteis. Confirme o início do prazo com a equipe.'
    text = 'Source: PDF pages 4–5. Exactly BRL 500 is unspecified.'
    assert chat_prose(text) == 'Exactly BRL 500 is unspecified.'


def test_chat_mock_separates_price_and_stock_without_source_or_zero_discount():
    agent = Agent(LiteLLMBackend(), language='pt', inline_sources=False)
    reply = agent.reply('Qual o preço do Yamaha C40 no PIX?')
    assert 'Preço: **R$ 599,90**' in reply
    assert 'No PIX: **R$ 569,91**' in reply
    assert '12 unidades' in reply
    assert 'Fonte:' not in reply and '0%' not in reply and ';' not in reply
    assert len(reply.split('\n\n')) >= 4
    assert agent.last_trace[0]['tool'] == 'search_products'
