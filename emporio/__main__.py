import argparse
from .agent import Agent
from .backend import LiteLLMBackend, ConfigurationError
from .paths import CONFIG_DIR


def main():
    parser = argparse.ArgumentParser(description='Mel - Empório da Música')
    parser.add_argument('--mode', choices=['mock', 'groq'], default='mock', help='Default: offline mock; Groq is opt-in')
    parser.add_argument('--demo-customer-id', type=int, help='Local evaluator fixture ONLY; not real authentication')
    parser.add_argument('--trace', action='store_true', help='Print tool names only; no customer data')
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(CONFIG_DIR / '.env', override=False)
    try:
        backend = LiteLLMBackend(mode=args.mode)
    except ConfigurationError as error:
        parser.error(str(error))
    agent = Agent(backend, trusted_customer_id=args.demo_customer_id)
    label = 'OFFLINE MOCK - scripted simulator, no API calls' if args.mode == 'mock' else 'GROQ - uses your API quota; verify your account is on Free plan'
    print(f'[{label}]')
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
            agent.last_trace.clear()
            agent.last_error = None
            print('Mel: Session cleared.')
            continue
        print('Mel:', agent.reply(message))
        if args.trace:
            print('[tools]', ', '.join(t['tool'] for t in agent.last_trace))


if __name__ == '__main__':
    main()
