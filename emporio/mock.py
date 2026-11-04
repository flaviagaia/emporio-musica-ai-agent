"""Offline scripted demonstration using the same request parser and real local tools."""
import json
from .i18n import translate
from .presentation import product_reply
from .routing import interpret, policy_topic, budget_value


def tool_call(name, args):
    return {'role': 'assistant', 'content': None, 'tool_calls': [{
        'id': 'mock_call_1', 'type': 'function',
        'function': {'name': name, 'arguments': json.dumps(args)}}]}


def answer(text):
    return {'role': 'assistant', 'content': text}


def mock_message(messages):
    system = next((m['content'] for m in messages if m['role'] == 'system'), '')
    language = 'pt' if '[OUTPUT_LANGUAGE:pt]' in system else 'en'
    inline_sources = '[CHAT_PRESENTATION]' not in system
    position = max(i for i, m in enumerate(messages) if m['role'] == 'user')
    user = messages[position]['content']
    request = interpret(user, messages[1:position])
    if messages[-1]['role'] == 'tool':
        return answer(mock_summary(user, json.loads(messages[-1]['content']), language,
                                   inline_sources=inline_sources, topic=request.topic))
    if request.kind == 'privacy':
        return answer(translate('I cannot share customer records. I can help with instruments and store policies.', language))
    if request.kind == 'catalog':
        if not request.query and not request.promotion:
            return answer('Qual instrumento ou modelo você procura?' if language == 'pt' else 'Which instrument or model are you looking for?')
        return tool_call('search_products', {'query': request.query, 'max_price': request.budget,
                         'available_only': not request.specific, 'promotion_only': request.promotion})
    if request.kind == 'policy':
        return tool_call('search_policies', {'query': request.query})
    if request.kind == 'order':
        return tool_call('get_order', {'order_id': request.order_id})
    return answer('Posso ajudar com instrumentos, preços e informações da loja. Qual é a sua dúvida?' if language == 'pt' else
                  'I can help with instruments, prices and store information. What would you like to know?')


def mock_summary(query, result, language='en', *, inline_sources=True, topic=None):
    pt = language == 'pt'
    if result.get('error'):
        return translate(result.get('message', 'Unable to retrieve reliable data. Refer to the team.'), language)
    if 'products' in result:
        if not result['products']:
            return 'Não encontrei instrumentos com esses filtros. Quer ajustar a busca?' if pt else 'No instruments match these filters. Would you like to adjust the search?'
        text = product_reply(result['products'], language)
        return text + ('\n\nFonte: catálogo da loja.' if pt else '\n\nSource: store catalog.') if inline_sources else text
    if 'order_id' in result:
        from .presentation import order_reply
        return order_reply(result, language)
    pages = {m['page'] for m in result.get('matches', [])}
    topic = topic or policy_topic(query)
    citation = ''
    if topic == 'hours' and 2 in pages:
        text = ('A loja fica na Rua 14 de Maio, 3200, Centro, Campo Grande - MS, CEP 79202-333.\n\n'
                'Atendemos de segunda a sexta, das 09h às 18h, e sábado, das 09h às 13h. Domingos e feriados: fechado.' if pt else
                'The store is at Rua 14 de Maio, 3200, Centro, Campo Grande - MS, CEP 79202-333.\n\nWeekdays: 09:00–18:00; Saturday: 09:00–13:00; Sundays and holidays: closed.')
        citation = '2'
    elif topic == 'scope' and 6 in pages:
        text = ('Trabalhamos com instrumentos musicais e não vendemos cabos ou amplificadores. Posso ajudar você a encontrar um instrumento.' if pt else
                'We focus on musical instruments and do not sell cables or amplifiers. I can help you find an instrument.')
        citation = '6'
    elif topic == 'payment' and 3 in pages:
        text = ('O manual lista PIX, cartão de débito, cartão de crédito e boleto. O PIX oferece 5% de desconto sobre o preço de tabela, sem acumular com promoções. O cartão permite até 12 parcelas sem juros.\n\n'
                'Os valores mínimos de parcelamento estão conflitantes no manual. Confirme as condições com a equipe.' if pt else
                'The manual lists PIX, debit cards, credit cards and bank slips. PIX gives 5% off the list price without stacking promotions. Credit cards allow up to 12 interest-free installments.\n\nThe manual has conflicting installment minima; please confirm conditions with staff.')
        citation = '3'
    elif topic == 'shipping' and 4 in pages:
        text = ('Na região metropolitana de Campo Grande, o manual informa frete grátis acima de R$ 500,00 e taxa de R$ 35,00 abaixo desse valor, com estimativa de 1 a 3 dias úteis.\n\n'
                'Para exatamente R$ 500,00 e para outras cidades, confirme o frete com a equipe.' if pt else
                'For metropolitan Campo Grande, shipping is free above BRL 500 and costs BRL 35 below that amount, with an estimated 1–3 business days.\n\nExactly BRL 500 is unspecified. Other destinations require a quote from the team.')
        citation = '4–5'
    elif topic in ('defect', 'exchange') and any('4.2' in m['text'] or '4.4' in m['text'] for m in result.get('matches', [])):
        text = ('Sinto muito pelo problema. Para orientar o atendimento por defeito ou troca, preciso saber qual é o instrumento, quando foi recebido e o que aconteceu.\n\n'
                'A equipe deve confirmar a garantia aplicável e organizar a avaliação ou troca. Não posso aprovar uma troca ou um reembolso pelo chat.' if pt else
                'I am sorry about the issue. For a defect or exchange request, which instrument is it, when did you receive it, and what happened?\n\nThe team must confirm the applicable warranty and arrange assessment or exchange. I cannot approve an exchange or refund in chat.')
        citation = '4–5'
    elif topic == 'withdrawal' and 4 in pages:
        from .store import normalize
        normalized = normalize(query)
        if 'online' in normalized and any(t in normalized for t in ('three days', 'tres dias', '3 dias')) and any(t in normalized for t in ('unused', 'sem uso')):
            text = ('O recebimento informado está dentro da janela de sete dias corridos descrita no manual para compras online. Confirme se há personalização e se você tem a embalagem original, os acessórios e os manuais.\n\n'
                    'O manual prevê frete de devolução pago pela loja e reembolso na forma original em até dez dias úteis, mas não define o início desse prazo. A equipe precisa confirmar e organizar a devolução; não posso aprovar ou processar o reembolso.' if pt else
                    'You are within the stated seven-calendar-day online return window. Please confirm customization, original packaging, accessories and manuals.\n\nThe manual states store-paid return shipping and refund through the original payment method within ten business days, but does not specify when that clock starts. Contact the team to arrange the return; I cannot approve or process it.')
        else:
            text = ('A compra foi online ou na loja física? Quando você recebeu o produto e qual é o motivo da devolução?\n\nO manual descreve sete dias corridos após o recebimento para arrependimento em compras online. Preciso confirmar esses dados antes de orientar a devolução.' if pt else
                    'Was the purchase online or in-store? When did you receive it, and why would you like to return it?\n\nThe manual describes a seven-calendar-day withdrawal period after receipt for online purchases. I need these facts before applying it.')
        citation = '4'
    else:
        return 'Não encontrei uma regra clara para essa pergunta. Você pode detalhar a dúvida ou consultar a equipe da loja.' if pt else 'I could not find a clear policy for this question. Please clarify or contact the store team.'
    if inline_sources:
        text += f'\n\nFonte: manual, página {citation}.' if pt else f'\n\nSource: PDF page {citation}.'
    return text


# Retained for callers of the earlier simulator helper.
def parse_budget(value):
    return budget_value('BRL ' + value)
