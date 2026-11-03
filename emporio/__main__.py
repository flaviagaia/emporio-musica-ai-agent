import argparse
import os
from .agent import Agent


def main():
    parser = argparse.ArgumentParser(description='Mel - Empório da Música (English evaluation mode)')
    parser.add_argument('--demo-customer-id', type=int, help='Local evaluator fixture ONLY; not real authentication')
    parser.add_argument('--trace', action='store_true', help='Print tool names only; no customer data')
    args = parser.parse_args()
    if not os.getenv('OPENAI_API_KEY'):
        parser.error('Set OPENAI_API_KEY in your shell first. See README for offline verification.')
    from openai import OpenAI
    agent = Agent(OpenAI(timeout=30, max_retries=1), model=os.getenv('OPENAI_MODEL', 'gpt-4.1-mini'),
                  trusted_customer_id=args.demo_customer_id)
    print('Mel: Hi! I can help you find an instrument or check store information. Type /exit to finish or /reset to clear this session.')
    while True:
        try:
            message = input('You: ')
        except (EOFError, KeyboardInterrupt):
            break
        if message.strip() == '/exit':
            break
        if message.strip() == '/reset':
            agent.history.clear()
            print('Mel: Session cleared.')
            continue
        print('Mel:', agent.reply(message))
        if args.trace:
            print('[tools]', ', '.join(t['tool'] for t in agent.last_trace))


if __name__ == '__main__':
    main()
