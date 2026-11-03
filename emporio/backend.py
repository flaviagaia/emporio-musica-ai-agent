"""LiteLLM SDK boundary. Mock is explicit, offline and never falls back to Groq."""
import os

DEFAULT_MODEL = 'groq/qwen/qwen3.8-27b'


class IncompleteResponseError(RuntimeError):
    """A cut-off or filtered model response must never be presented as complete."""


class ConfigurationError(ValueError):
    pass


class LiteLLMBackend:
    def __init__(self, mode='mock', model=None):
        if mode not in ('mock', 'groq'):
            raise ConfigurationError('Mode must be mock or groq.')
        self.mode = mode
        self.model = model or os.getenv('GROQ_MODEL', DEFAULT_MODEL)
        if not self.model.startswith('groq/'):
            raise ConfigurationError('This project only permits groq/ models; paid-provider fallback is disabled.')
        if mode == 'groq' and not os.getenv('GROQ_API_KEY', '').strip():
            raise ConfigurationError('GROQ_API_KEY is missing. Run python -m emporio.configure locally, or use --mode mock.')

    def complete(self, messages, tools, tool_choice='auto'):
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
        # SDK only; no proxy, router, automatic retries, cache or paid fallback.
        result = completion(**options)
        choice = result.choices[0]
        if choice.finish_reason not in ('stop', 'tool_calls'):
            raise IncompleteResponseError('The model did not complete its response.')
        return choice.message.model_dump(exclude_none=True)
