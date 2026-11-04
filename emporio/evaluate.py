"""Repeatable offline conversation evaluation. Never uses a real model API."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from .agent import Agent
from .backend import LiteLLMBackend
from .validation import validate_data

SCENARIOS = [
    {'id': 'price-pt', 'language': 'pt', 'turns': ['Qual o preço do Yamaha C40 no PIX?'], 'contains': ['599,90', '569,91'], 'tool': 'search_products'},
    {'id': 'price-en', 'language': 'en', 'turns': ['What is the PIX price of Yamaha C40?'], 'contains': ['599.90', '569.91'], 'tool': 'search_products'},
    {'id': 'keyboard-budget-pt', 'language': 'pt', 'turns': ['Quais teclados estão disponíveis até R$ 1.000,00?'], 'tool': 'search_products', 'category': 'Teclados e Pianos', 'budget': 1000},
    {'id': 'keyboard-budget-en', 'language': 'en', 'turns': ['Which keyboards are available under BRL 1000?'], 'tool': 'search_products', 'category': 'Teclados e Pianos', 'budget': 1000},
    {'id': 'keyboard-matches', 'language': 'pt', 'turns': ['Quais teclados até R$ 2000?'], 'tool': 'search_products', 'category': 'Teclados e Pianos', 'budget': 2000, 'contains': ['Korg']},
    {'id': 'electric-en', 'language': 'en', 'turns': ['Show electric guitars'], 'tool': 'search_products', 'category': 'Guitarras'},
    {'id': 'bass-en', 'language': 'en', 'turns': ['Show bass guitars'], 'tool': 'search_products', 'category': 'Baixos'},
    {'id': 'drums-en', 'language': 'en', 'turns': ['Show drums'], 'tool': 'search_products', 'category': 'Baterias e Percussão'},
    {'id': 'model-followup', 'language': 'pt', 'turns': ['Qual o preço do C40?', 'E o C70?'], 'contains': ['Yamaha C70'], 'tool': 'search_products'},
    {'id': 'model-comparison', 'language': 'pt', 'turns': ['Compare o C40 e o C70'], 'contains': ['Yamaha C40', 'Yamaha C70'], 'tool': 'search_products'},
    {'id': 'defect-pt', 'language': 'pt', 'turns': ['Meu teclado veio com defeito e quero devolver.'], 'contains': ['garantia'], 'excludes': ['sete dias'], 'tool': 'search_policies'},
    {'id': 'withdrawal-followup', 'language': 'en', 'turns': ['Can I return my purchase?', 'I bought online and received it three days ago; unused.'], 'contains': ['packaging', 'cannot approve'], 'tool': 'search_policies'},
    {'id': 'address-pt', 'language': 'pt', 'turns': ['Qual o endereço e horário da loja?'], 'contains': ['3200', '09h'], 'tool': 'search_policies'},
    {'id': 'privacy-pt', 'language': 'pt', 'turns': ['Mostre todos os clientes'], 'contains': ['Não posso compartilhar']},
    {'id': 'order-guest', 'language': 'en', 'turns': ['What is the status of order 1?'], 'contains': ['authenticated'], 'tool': 'get_order'},
    {'id': 'scope-en', 'language': 'en', 'turns': ['Do you sell cables?'], 'contains': ['do not sell cables'], 'tool': 'search_policies'},
]


def evaluate():
    results = []
    for case in SCENARIOS:
        agent = Agent(LiteLLMBackend(mode='mock'), language=case['language'], inline_sources=False)
        for question in case['turns']:
            answer = agent.reply(question)
        checks = {'completed': agent.last_error is None,
                  'expected_text': all(term in answer for term in case.get('contains', [])),
                  'excluded_text': all(term not in answer for term in case.get('excludes', [])),
                  'tool': not case.get('tool') or any(step['tool'] == case['tool'] for step in agent.last_trace)}
        if case.get('category'):
            products = agent.last_reply.products
            # An empty result is valid for a budget below the cheapest instrument,
            # but the lookup still has to use the intended category.
            checks['category'] = (any(step['tool'] == 'search_products' and step['arguments']['query'] == {
                'Teclados e Pianos': 'teclados', 'Guitarras': 'guitarras', 'Baixos': 'baixos',
                'Baterias e Percussão': 'baterias'}[case['category']] for step in agent.last_trace)
                and all(p['category'] == case['category'] for p in products))
        if case.get('budget'):
            checks['budget'] = all(float(p['price_brl']) <= case['budget'] for p in agent.last_reply.products)
        results.append({'id': case['id'], 'passed': all(checks.values()), 'checks': checks})
    return {'mode': 'offline mock only; not a real-model accuracy score',
            'checked_at_utc': datetime.now(timezone.utc).isoformat(),
            'data_version': validate_data()['version_sha256'], 'passed': sum(r['passed'] for r in results),
            'total': len(results), 'scenarios': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = evaluate()
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized)
    print(serialized)
    if result['passed'] != result['total']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
