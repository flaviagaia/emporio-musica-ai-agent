"""LiteLLM SDK boundary. Mock is explicit, offline and never falls back to Groq."""
import os
import logging
from .limits import SHARED_LIMITER

DEFAULT_MODEL = 'groq/qwen/qwen3.8-27b'


class IncompleteResponseError(RuntimeError):
    """A cut-off or filtered model response must never be presented as complete."""


class ConfigurationError(ValueError):
    pass


class LiteLLMBackend:
    def __init__(self, mode='mock', model=None, api_key=None, limiter=None):
        if mode not in ('mock', 'groq'):
            raise ConfigurationError('Mode must be mock or groq.')
        self.mode = mode
        self.limiter = limiter if limiter is not None else SHARED_LIMITER
        self.last_usage = {}
        self.model = model or os.getenv('GROQ_MODEL', DEFAULT_MODEL)
        if not self.model.startswith('groq/'):
            raise ConfigurationError('This project only permits groq/ models; paid-provider fallback is disabled.')
        self.api_key = api_key if api_key is not None else os.getenv('GROQ_API_KEY', '')
        if mode == 'groq' and not self.api_key.strip():
            raise ConfigurationError('GROQ_API_KEY is missing. Run python -m emporio.configure locally, or use --mode mock.')

    def complete(self, messages, tools, tool_choice='auto'):
        if self.mode == 'groq':
            self.limiter.acquire(self.api_key)
        # Avoid LiteLLM downloading the model-cost catalog even in mock mode.
        os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
        from litellm import completion
        options = dict(model=self.model, messages=messages, tools=tools,
                       tool_choice=tool_choice, parallel_tool_calls=False,
                       temperature=0, max_tokens=1200, timeout=30, num_retries=0)
        if self.mode == 'mock':
            from .mock import mock_message
            message = mock_message(messages)
            options['mock_response'] = {'choices': [{'index': 0, 'message': message,
                'finish_reason': 'tool_calls' if message.get('tool_calls') else 'stop'}]}
        if self.mode == 'groq':
            options['api_key'] = self.api_key
        # SDK only; no proxy, router, automatic retries, cache or paid fallback.
        result = completion(**options)
        usage = getattr(result, 'usage', None)
        self.last_usage = {key: int(getattr(usage, key, 0) or 0) for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
        logging.getLogger('emporio').info('Model request completed: mode=%s tokens=%s', self.mode, self.last_usage['total_tokens'])
        choice = result.choices[0]
        if choice.finish_reason not in ('stop', 'tool_calls'):
            raise IncompleteResponseError('The model did not complete its response.')
        return choice.message.model_dump(exclude_none=True)
