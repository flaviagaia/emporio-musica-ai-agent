"""Generate factual tool evidence only: no LLM calls or extra conversation files."""
import json
from pathlib import Path
from .store import Store
from .policies import Policies


def main():
    store, policies = Store(), Policies()
    target = Path(__file__).resolve().parents[1] / 'evidence'
    target.mkdir(exist_ok=True)
    evidence = {
        'catalog': {'budget_search': store.products('violão', 1000),
                    'follow_up': store.products('Yamaha C40')},
        'address': policies.search('store address endereco'),
        'promotion': {'products': [p for p in store.products(promotion_only=True)['products'] if float(p['discount_percent']) > 0],
                      'policy': policies.search('PIX promocao cumulatividade')},
        'returns': policies.search('online return refund devolucao arrependimento'),
        'boundaries': {'anonymous_order': store.order(1), 'wrong_customer': store.order(1, 7),
                       'authorized_fixture': store.order(1, 3),
                       'policy': policies.search('acessorios cabos escopo')},
    }
    for name, result in evidence.items():
        (target / f'{name}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Generated {len(evidence)} local-tool evidence files (no LLM calls).')


if __name__ == '__main__':
    main()
