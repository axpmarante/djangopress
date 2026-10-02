# ai/utils/llm_config.py
import os
import json
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Literal, Union
from enum import Enum, auto

# Try to use django-environ if available, fallback to os.getenv
try:
    import environ
    from pathlib import Path

    _env = environ.Env()
    # Find the .env file - go up from this file to project root
    env_file = Path(__file__).resolve().parent.parent.parent / '.env'
    if env_file.exists():
        _env.read_env(str(env_file))
    _env_loaded = True
except (ImportError, Exception) as e:
    _env_loaded = False


def get_env(key):
    """Get environment variable, preferring django-environ if available"""
    if _env_loaded:
        return _env(key, default=None)
    return os.getenv(key)


# Import dependencies with graceful fallback
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OpenAI = None
    OPENAI_AVAILABLE = False

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    Anthropic = None
    ANTHROPIC_AVAILABLE = False

try:
    from google import genai
    from google.genai import types
    GOOGLE_AVAILABLE = True
except ImportError:
    genai = None
    types = None
    GOOGLE_AVAILABLE = False


class ModelProvider(str, Enum):
    """Enum for supported model providers"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"


@dataclass
class ModelConfig:
    """Unified model configuration"""
    provider: ModelProvider = ModelProvider.OPENAI
    model_name: str = "gpt-4o-mini"
    # OpenAI/Anthropic use max_tokens, Google uses max_output_tokens
    max_tokens: Optional[int] = None
    max_output_tokens: Optional[int] = None
    temperature: float = 0.3
    response_format: Optional[Dict[str, str]] = None
    # Provider-specific parameters
    provider_params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Set default provider-specific parameters if not provided"""
        if self.provider == ModelProvider.GOOGLE:
            if self.max_tokens is not None and self.max_output_tokens is None:
                self.max_output_tokens = self.max_tokens
                self.max_tokens = None
            # No top_p/top_k defaults: Gemini 3 is tuned for its own sampling defaults.
        elif self.provider == ModelProvider.ANTHROPIC:
            if self.max_tokens is None and self.max_output_tokens is not None:
                self.max_tokens = self.max_output_tokens
                self.max_output_tokens = None
        elif self.provider == ModelProvider.OPENAI:
            if self.max_tokens is None and self.max_output_tokens is not None:
                self.max_tokens = self.max_output_tokens
                self.max_output_tokens = None


@dataclass
class GeneratedImageResponse:
    """Result of an image generation request."""
    success: bool
    image_bytes: Optional[bytes] = None
    mime_type: str = "image/png"
    error: Optional[str] = None
    prompt_used: str = ""
    thinking_text: Optional[str] = None


# Model configurations for different providers
MODEL_CONFIG = {
    # ===== OPENAI MODELS =====
    'gpt-5': ModelConfig(
        provider=ModelProvider.OPENAI,
        model_name="gpt-5.2",
        max_tokens=32000,
        temperature=1.0
    ),
    'gpt-5-mini': ModelConfig(
        provider=ModelProvider.OPENAI,
        model_name="gpt-5-mini-2025-08-07",
        max_tokens=32000,
        temperature=1.0
    ),

    # ===== ANTHROPIC MODELS =====
    'claude': ModelConfig(
        provider=ModelProvider.ANTHROPIC,
        model_name="claude-sonnet-4-5-20250929",
        max_tokens=32000,
        temperature=0.3
    ),

    # ===== GOOGLE MODELS =====
    'gemini-pro': ModelConfig(
        provider=ModelProvider.GOOGLE,
        model_name="gemini-3.1-pro-preview",
        max_output_tokens=32000,
        temperature=0.3,
    ),
    'gemini-flash': ModelConfig(
        provider=ModelProvider.GOOGLE,
        model_name="gemini-3.8-flash",
        max_output_tokens=32000,
        temperature=0.3,
    ),
    'gemini-lite': ModelConfig(
        provider=ModelProvider.GOOGLE,
        model_name="gemini-3.5-flash-lite",
        max_output_tokens=32000,
        temperature=0.3,
    )
}

# Default model assignments per task category
AI_MODEL_DEFAULTS = {
    'generation': 'gemini-flash',
    'refinement_page': 'gemini-flash',
    'refinement_section': 'gemini-flash',
    'refinement_element': 'gemini-flash',
    'header_footer': 'gemini-flash',
    'translation': 'gemini-lite',
    'metadata': 'gemini-lite',
    'image_analysis': 'gemini-flash',
    'assistant_router': 'gemini-lite',
    'refinement_routing': 'gemini-flash',
    'web_search': 'gemini-flash',
    'assistant_executor': 'gemini-flash',
    'consistency': 'gemini-flash',
    'design_guide': 'gemini-flash',
}



class ModelKey(str):
    """A MODEL_CONFIG key that remembers which task asked for it (see get_ai_model),
    so the call can use that task's generation settings."""

    def __new__(cls, value, task=None):
        obj = super().__new__(cls, value)
        obj.task = task
        return obj


# Gemini 3 generation settings per task. Google tunes Gemini 3 for temperature
# 1.0; thinking is where tasks differ (design work thinks hard, routing barely).
_DESIGN = {'temperature': 1.0, 'thinking_level': 'high'}
_LIGHT = {'temperature': 1.0, 'thinking_level': 'low'}
TASK_SETTINGS = {
    'generation': _DESIGN, 'refinement_page': _DESIGN, 'refinement_section': _DESIGN,
    'refinement_element': _DESIGN, 'header_footer': _DESIGN, 'design_guide': _DESIGN,
    'assistant_executor': {'temperature': 1.0, 'thinking_level': 'medium'},
    'assistant_router': _LIGHT, 'refinement_routing': _LIGHT, 'web_search': _LIGHT, 'metadata': _LIGHT, 'translation': _LIGHT,
    'consistency': _LIGHT, 'image_analysis': _LIGHT,
}
TIER_DEFAULT_THINKING = {'gemini-pro': 'high', 'gemini-flash': 'medium', 'gemini-lite': 'low'}
TRANSIENT_ERROR_MARKERS = ('429', '500', '502', '503', '504', 'UNAVAILABLE', 'RESOURCE_EXHAUSTED', 'DEADLINE_EXCEEDED')


def settings_for(tool_name):
    """Generation settings for a model key, using its task when it carries one."""
    task = getattr(tool_name, 'task', None)
    if task in TASK_SETTINGS:
        return dict(TASK_SETTINGS[task])
    return {'temperature': 1.0, 'thinking_level': TIER_DEFAULT_THINKING.get(str(tool_name), 'medium')}


def _gemini_settings(tool_name, config):
    """GenerateContentConfig kwargs (temperature, thinking, max tokens) for a Gemini call."""
    s = settings_for(tool_name)
    params = {'temperature': s['temperature']}
    if s.get('thinking_level'):
        params['thinking_config'] = types.ThinkingConfig(thinking_level=s['thinking_level'].upper())
    if config.max_output_tokens:
        params['max_output_tokens'] = config.max_output_tokens
    if config.provider_params and 'generation_config' in config.provider_params:
        params.update(config.provider_params['generation_config'])
    return params


def _is_transient(error):
    text = str(error)
    return any(marker in text for marker in TRANSIENT_ERROR_MARKERS)


def _finish_reason(response):
    try:
        reason = response.candidates[0].finish_reason
    except (AttributeError, IndexError, TypeError):
        return None
    return getattr(reason, 'name', None) or (str(reason) if reason else None)


def _gemini_usage(response):
    meta = getattr(response, 'usage_metadata', None)
    if not meta:
        return None
    prompt = getattr(meta, 'prompt_token_count', 0) or 0
    completion = (getattr(meta, 'candidates_token_count', 0) or 0) + (getattr(meta, 'thoughts_token_count', 0) or 0)
    return {'prompt_tokens': prompt, 'completion_tokens': completion, 'total_tokens': prompt + completion}

def get_ai_model(task):
    """Get the configured model for a given AI task.

    Reads from SiteSettings.ai_model_config, falls back to AI_MODEL_DEFAULTS.
    Validates that the returned model exists in MODEL_CONFIG.

    Args:
        task: One of the keys in AI_MODEL_DEFAULTS.

    Returns:
        A model key string (e.g. 'gemini-flash').
    """
    default = AI_MODEL_DEFAULTS.get(task, 'gemini-flash')
    try:
        from djangopress.core.models import SiteSettings
        settings = SiteSettings.load()
        config = settings.ai_model_config or {}
        model = config.get(task, default)
        # Backward compat: old 'refinement' key applies to all refinement_* sub-keys
        if model == default and task.startswith('refinement_') and 'refinement' in config:
            model = config['refinement']
        if model not in MODEL_CONFIG:
            return ModelKey(default, task)
        return ModelKey(model, task)
    except Exception:
        return ModelKey(default, task)


class StandardizedLLMResponse:
    """Standardized response format across all providers"""

    def __init__(self, content: str, usage: Dict[str, int] = None, finish_reason: str = None):
        self.finish_reason = finish_reason
        self.choices = [type('Choice', (), {
            'message': type('Message', (), {
                'content': content
            })()
        })()]
        self.usage = type('Usage', (), usage or {})()


class LLMBase:
    """Unified LLM client with multi-provider support - Singleton pattern"""

    _instance = None
    _clients = {}
    _using_vertex_ai = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if ModelProvider.OPENAI not in self._clients and OPENAI_AVAILABLE:
            openai_key = get_env('OPENAI_API_KEY')
            if openai_key:
                self._clients[ModelProvider.OPENAI] = OpenAI(api_key=openai_key)

        if ModelProvider.ANTHROPIC not in self._clients and ANTHROPIC_AVAILABLE:
            anthropic_key = get_env('ANTHROPIC_API_KEY')
            if anthropic_key:
                self._clients[ModelProvider.ANTHROPIC] = Anthropic(api_key=anthropic_key)

        if ModelProvider.GOOGLE not in self._clients and GOOGLE_AVAILABLE:
            vertex_project = get_env('VERTEX_AI_PROJECT')
            vertex_location = get_env('VERTEX_AI_LOCATION')
            if vertex_project:
                self._clients[ModelProvider.GOOGLE] = genai.Client(
                    vertexai=True,
                    project=vertex_project,
                    location=vertex_location or 'global',
                )
                LLMBase._using_vertex_ai = True
            else:
                google_key = get_env('GEMINI_API_KEY')
                if google_key:
                    self._clients[ModelProvider.GOOGLE] = genai.Client(api_key=google_key)

    def _format_messages_for_claude(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Convert chat messages to Claude's format (now uses messages API)"""
        formatted_messages = []
        system_message = ""

        for msg in messages:
            role = msg['role']
            content = msg['content']

            if role == 'system':
                system_message += content + "\n\n"
            elif role == 'user':
                formatted_messages.append({"role": "user", "content": content})
            elif role == 'assistant':
                formatted_messages.append({"role": "assistant", "content": content})

        return formatted_messages, system_message.strip()

    def _format_messages_for_gemini(self, messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Convert chat messages to Gemini's format with improved error handling"""
        gemini_messages = []

        try:
            system_content = ""
            for msg in messages:
                if msg.get('role') == 'system':
                    system_content += msg.get('content', '') + "\n\n"

            for msg in messages:
                role = msg.get('role', '')
                content = msg.get('content', '')

                if not isinstance(content, str):
                    content = str(content)

                if role == 'system':
                    continue
                elif role == 'user':
                    gemini_messages.append({"role": "user", "parts": [content]})
                elif role == 'assistant':
                    gemini_messages.append({"role": "model", "parts": [content]})
                else:
                    print(f"Warning: Unknown message role '{role}', treating as user message")
                    gemini_messages.append({"role": "user", "parts": [content]})

            if system_content and gemini_messages and gemini_messages[0]["role"] == "user":
                gemini_messages[0]["parts"][0] = f"{system_content}\n\n{gemini_messages[0]['parts'][0]}"

            if not gemini_messages:
                gemini_messages.append({"role": "user", "parts": [system_content or "Hello"]})

            return gemini_messages
        except Exception as e:
            print(f"Error formatting messages for Gemini: {str(e)}")
            return [{"role": "user", "parts": ["Hello, can you help me?"]}]

    def get_completion(
            self,
            messages: List[Dict[str, str]],
            tool_name: str = None,
            on_stream=None,
            json_output: bool = False,
            **kwargs
    ) -> StandardizedLLMResponse:
        """Get chat completion with model-specific configs.

        json_output: ask Gemini for a JSON response (response_mime_type)."""
        import time
        start_time = time.time()

        config = MODEL_CONFIG.get(tool_name, ModelConfig())

        print("\n" + "=" * 80)
        print("🤖 LLM API CALL STARTED")
        print("=" * 80)
        print(f"📍 Provider: {config.provider.value.upper()}")
        print(f"🔧 Tool Name: {tool_name or 'default'}")
        print(f"🧠 Model: {config.model_name}")
        print(f"🌡️  Temperature: {config.temperature}")

        if config.provider == ModelProvider.GOOGLE:
            print(f"📊 Max Output Tokens: {config.max_output_tokens}")
        else:
            print(f"📊 Max Tokens: {config.max_tokens}")

        if config.provider_params:
            print(f"⚙️  Provider Params: {json.dumps(config.provider_params, indent=2)}")

        print(f"\n💬 Messages ({len(messages)} total):")
        print("-" * 80)
        for i, msg in enumerate(messages, 1):
            role = msg['role'].upper()
            content = msg['content']
            SHOW_FULL_CONTENT = True
            if SHOW_FULL_CONTENT:
                content_preview = content
            else:
                content_preview = content if len(content) <= 200 else content[:200] + "... (truncated)"
            print(f"\n[{i}] {role}:")
            print(f"{content_preview}")
        print("-" * 80)

        try:
            if config.provider == ModelProvider.OPENAI and not OPENAI_AVAILABLE:
                raise ImportError("OpenAI library not installed. Install with: pip install openai")
            elif config.provider == ModelProvider.ANTHROPIC and not ANTHROPIC_AVAILABLE:
                raise ImportError("Anthropic library not installed. Install with: pip install anthropic")
            elif config.provider == ModelProvider.GOOGLE and not GOOGLE_AVAILABLE:
                raise ImportError(
                    "Google GenAI library not installed. Install with: pip install google-genai")

            if config.provider not in self._clients:
                raise ValueError(f"Provider {config.provider} not initialized. Check API key.")

            if config.provider == ModelProvider.OPENAI:
                client = self._clients[ModelProvider.OPENAI]

                params = {
                    "model": config.model_name,
                    "temperature": config.temperature,
                    "messages": messages,
                    **kwargs
                }

                if config.max_tokens:
                    if any(x in config.model_name.lower() for x in ["gpt-5", "o1", "o3", "o4"]):
                        params["max_completion_tokens"] = config.max_tokens
                    else:
                        params["max_tokens"] = config.max_tokens

                if config.response_format:
                    params["response_format"] = config.response_format

                if config.provider_params:
                    params.update(config.provider_params)

                print("\n⏳ Calling OpenAI API...")
                response = client.chat.completions.create(**params)

                response_content = response.choices[0].message.content
                usage = {
                    "total_tokens": response.usage.total_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "prompt_tokens": response.usage.prompt_tokens
                }

                elapsed_time = time.time() - start_time
                print("\n" + "=" * 80)
                print("✅ LLM API CALL SUCCESSFUL")
                print("=" * 80)
                print(f"⏱️  Time Elapsed: {elapsed_time:.2f}s")
                print(f"📊 Token Usage:")
                print(f"   - Prompt: {usage['prompt_tokens']}")
                print(f"   - Completion: {usage['completion_tokens']}")
                print(f"   - Total: {usage['total_tokens']}")
                print(f"📝 Response Length: {len(response_content)} characters")
                SHOW_FULL_RESPONSE = True
                if SHOW_FULL_RESPONSE:
                    print(f"📄 Full Response:\n{response_content}")
                else:
                    print(f"📄 Response Preview: {response_content[:150]}..." if len(
                        response_content) > 150 else f"📄 Response: {response_content}")
                print("=" * 80 + "\n")

                return StandardizedLLMResponse(
                    content=response_content,
                    usage=usage
                )

            elif config.provider == ModelProvider.ANTHROPIC:
                client = self._clients[ModelProvider.ANTHROPIC]

                formatted_messages, system_message = self._format_messages_for_claude(messages)

                params = {
                    "model": config.model_name,
                    "max_tokens": config.max_tokens,
                    "temperature": config.temperature,
                    "messages": formatted_messages
                }

                if system_message:
                    params["system"] = system_message

                if config.provider_params:
                    params.update(config.provider_params)

                print("\n⏳ Calling Anthropic (Claude) API...")
                response = client.messages.create(**params)

                response_content = ""
                if hasattr(response, 'content') and response.content:
                    for content_block in response.content:
                        if hasattr(content_block, 'type') and content_block.type == 'text':
                            response_content += content_block.text

                usage = {
                    "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "prompt_tokens": response.usage.input_tokens
                }

                elapsed_time = time.time() - start_time
                print("\n" + "=" * 80)
                print("✅ LLM API CALL SUCCESSFUL")
                print("=" * 80)
                print(f"⏱️  Time Elapsed: {elapsed_time:.2f}s")
                print(f"📊 Token Usage:")
                print(f"   - Prompt: {usage['prompt_tokens']}")
                print(f"   - Completion: {usage['completion_tokens']}")
                print(f"   - Total: {usage['total_tokens']}")
                print(f"📝 Response Length: {len(response_content)} characters")
                SHOW_FULL_RESPONSE = True
                if SHOW_FULL_RESPONSE:
                    print(f"📄 Full Response:\n{response_content}")
                else:
                    print(f"📄 Response Preview: {response_content[:150]}..." if len(
                        response_content) > 150 else f"📄 Response: {response_content}")
                print("=" * 80 + "\n")

                return StandardizedLLMResponse(
                    content=response_content,
                    usage=usage
                )

            elif config.provider == ModelProvider.GOOGLE:
                # Google Gemini (google-genai SDK). System messages go to
                # system_instruction; settings come from the task (settings_for).
                client = self._clients[ModelProvider.GOOGLE]
                resolved_model = config.model_name

                system_text = "\n\n".join(m.get('content', '') for m in messages if m.get('role') == 'system').strip()
                contents = []
                for msg in messages:
                    role = msg.get('role', 'user')
                    if role == 'system':
                        continue
                    contents.append(types.Content(
                        role='model' if role == 'assistant' else 'user',
                        parts=[types.Part.from_text(text=str(msg.get('content', '')))],
                    ))
                if not contents:
                    contents.append(types.Content(role='user', parts=[types.Part.from_text(text=system_text or 'Hello')]))
                    system_text = ''

                gen_config_params = _gemini_settings(tool_name, config)
                if system_text:
                    gen_config_params['system_instruction'] = system_text
                if json_output:
                    gen_config_params['response_mime_type'] = 'application/json'
                generation_config = types.GenerateContentConfig(**gen_config_params)

                finish_reason = None
                real_usage = None
                backend = "Vertex AI" if self._using_vertex_ai else "google-genai SDK"
                for attempt in (1, 2):
                    try:
                        print(f"\n⏳ Calling Google Gemini API ({backend}), attempt {attempt}...")
                        print(f"   Model: {resolved_model} · settings: {settings_for(tool_name)}")
                        if on_stream:
                            response_content = ""
                            for chunk in client.models.generate_content_stream(
                                model=resolved_model, contents=contents, config=generation_config
                            ):
                                chunk_text = ""
                                try:
                                    if getattr(chunk, 'text', None):
                                        chunk_text = chunk.text
                                    elif getattr(chunk, 'candidates', None):
                                        for part in chunk.candidates[0].content.parts:
                                            if getattr(part, 'text', None):
                                                chunk_text += part.text
                                except Exception:
                                    pass
                                finish_reason = _finish_reason(chunk) or finish_reason
                                real_usage = _gemini_usage(chunk) or real_usage
                                if chunk_text:
                                    response_content += chunk_text
                                    try:
                                        on_stream(response_content, len(response_content))
                                    except Exception:
                                        pass  # Never let callback errors break generation
                        else:
                            response = client.models.generate_content(
                                model=resolved_model, contents=contents, config=generation_config
                            )
                            response_content = ""
                            if getattr(response, 'text', None):
                                response_content = response.text
                            elif getattr(response, 'candidates', None):
                                candidate = response.candidates[0]
                                for part in getattr(getattr(candidate, 'content', None), 'parts', None) or []:
                                    if getattr(part, 'text', None):
                                        response_content += part.text
                            finish_reason = _finish_reason(response)
                            real_usage = _gemini_usage(response)
                        break
                    except Exception as gemini_error:
                        # No switch to another provider: retry a transient error once, then fail loudly.
                        print(f"❌ Gemini error ({type(gemini_error).__name__}): {gemini_error}")
                        if attempt == 1 and _is_transient(gemini_error):
                            time.sleep(2)
                            continue
                        raise

                if real_usage:
                    usage = real_usage
                else:
                    char_count = sum(len(str(msg.get('content', ''))) for msg in messages) + len(response_content)
                    usage = {
                        "total_tokens": char_count // 4,
                        "completion_tokens": len(response_content) // 4,
                        "prompt_tokens": char_count // 4 - len(response_content) // 4,
                    }

                elapsed_time = time.time() - start_time
                print("\n" + "=" * 80)
                print("✅ LLM API CALL SUCCESSFUL")
                print("=" * 80)
                print(f"⏱️  Time Elapsed: {elapsed_time:.2f}s")
                print(f"📊 Token Usage:")
                print(f"   - Prompt: ~{usage['prompt_tokens']}")
                print(f"   - Completion: ~{usage['completion_tokens']}")
                print(f"   - Total: ~{usage['total_tokens']}")
                print(f"📝 Response Length: {len(response_content)} characters")
                SHOW_FULL_RESPONSE = True
                if SHOW_FULL_RESPONSE:
                    print(f"📄 Full Response:\n{response_content}")
                else:
                    print(f"📄 Response Preview: {response_content[:150]}..." if len(
                        response_content) > 150 else f"📄 Response: {response_content}")
                print("=" * 80 + "\n")

                print(f"🏁 Finish reason: {finish_reason}")
                return StandardizedLLMResponse(
                    content=response_content,
                    usage=usage,
                    finish_reason=finish_reason,
                )

            else:
                raise ValueError(f"Unsupported provider: {config.provider}")

        except Exception as e:
            elapsed_time = time.time() - start_time
            print("\n" + "=" * 80)
            print("❌ LLM API CALL FAILED")
            print("=" * 80)
            print(f"📍 Provider: {config.provider.value.upper()}")
            print(f"🧠 Model: {config.model_name}")
            print(f"⏱️  Time Elapsed: {elapsed_time:.2f}s")
            print(f"❗ Error Type: {type(e).__name__}")
            print(f"❗ Error Message: {str(e)}")
            print("=" * 80 + "\n")
            raise

    def web_search(self, query, tool_name=None):
        """Answer a question with Google Search grounding.

        Returns {'text', 'sources': [{'title', 'url'}], 'queries'}; sources are the
        pages Google used (deduplicated, in order).
        """
        tool_name = tool_name or get_ai_model('web_search')
        config_entry = MODEL_CONFIG.get(tool_name)
        if not config_entry or config_entry.provider != ModelProvider.GOOGLE:
            raise ValueError(f'Web search needs a Google model, got: {tool_name}')
        client = self._clients.get(ModelProvider.GOOGLE)
        if not client:
            raise RuntimeError('Google client not initialized')
        config = types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            **_gemini_settings(tool_name, config_entry),
        )
        response = client.models.generate_content(
            model=config_entry.model_name,
            contents=f'{query}\n\nAnswer with the facts you found, briefly. Say clearly if you found nothing reliable.',
            config=config,
        )
        meta = getattr(response.candidates[0], 'grounding_metadata', None) if getattr(response, 'candidates', None) else None
        sources, seen = [], set()
        for chunk in (getattr(meta, 'grounding_chunks', None) or []):
            web = getattr(chunk, 'web', None)
            url = getattr(web, 'uri', None)
            if url and url not in seen:
                seen.add(url)
                sources.append({'title': getattr(web, 'title', '') or url, 'url': url})
        return {'text': getattr(response, 'text', '') or '', 'sources': sources,
                'queries': list(getattr(meta, 'web_search_queries', None) or [])}

    def get_completion_with_tools(self, contents, system_instruction, tools,
                                  tool_name='gemini-flash'):
        """Call Gemini with native function calling.

        Args:
            contents: List of Gemini Content dicts (conversation history).
            system_instruction: System instruction string.
            tools: List of types.Tool objects with FunctionDeclarations.
            tool_name: Model config key (e.g. 'gemini-flash').

        Returns:
            The raw Gemini GenerateContentResponse.
        """
        config_entry = MODEL_CONFIG.get(tool_name)
        if not config_entry or config_entry.provider != ModelProvider.GOOGLE:
            raise ValueError(f'Native FC only supported for Google models, got: {tool_name}')

        client = self._clients.get(ModelProvider.GOOGLE)
        if not client:
            raise RuntimeError('Google client not initialized')

        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=tools,
            **_gemini_settings(tool_name, config_entry),
        )

        for attempt in (1, 2):
            try:
                return client.models.generate_content(
                    model=config_entry.model_name,
                    contents=contents,
                    config=config,
                )
            except Exception as error:
                if attempt == 1 and _is_transient(error):
                    import time
                    time.sleep(2)
                    continue
                raise

    def get_vision_completion(
            self,
            prompt: str,
            file_path: str = None,
            file_bytes: bytes = None,
            file_mime_type: str = None,
            images: List[Dict[str, Any]] = None,
            tool_name: str = 'gemini-pro',
            **kwargs
    ) -> StandardizedLLMResponse:
        """
        Get vision completion from LLM with file (PDF/image) input.

        Uses Gemini's native PDF/image support - no conversion needed.
        Falls back to GPT-5.2 if Gemini fails.

        Args:
            prompt: The text prompt to send with the file
            file_path: Path to the file (PDF or image)
            file_bytes: Raw bytes of the file (alternative to file_path)
            file_mime_type: MIME type of the file (required if using file_bytes)
            images: List of images, each with 'bytes' and 'mime_type' keys (for multiple images)
            tool_name: The model configuration to use
        """
        import time
        import mimetypes
        start_time = time.time()

        config = MODEL_CONFIG.get(tool_name, MODEL_CONFIG['gemini-pro'])

        print("\n" + "=" * 80)
        print("🖼️ VISION LLM API CALL STARTED")
        print("=" * 80)
        print(f"📍 Provider: {config.provider.value.upper()}")
        print(f"🔧 Tool Name: {tool_name}")
        print(f"🧠 Model: {config.model_name}")

        try:
            if images:
                images_data = images
                total_size = sum(len(img['bytes']) for img in images)
                print(f"📄 Files: {len(images)} images")
                print(f"📏 Total Size: {total_size / 1024:.2f} KB")
            elif file_path:
                with open(file_path, 'rb') as f:
                    file_content = f.read()
                mime_type = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
                print(f"📄 File: {file_path}")
                images_data = [{'bytes': file_content, 'mime_type': mime_type}]
                print(f"📋 MIME Type: {mime_type}")
                print(f"📏 File Size: {len(file_content) / 1024:.2f} KB")
            elif file_bytes and file_mime_type:
                file_content = file_bytes
                mime_type = file_mime_type
                print(f"📄 File: <bytes> ({len(file_bytes)} bytes)")
                images_data = [{'bytes': file_content, 'mime_type': mime_type}]
                print(f"📋 MIME Type: {mime_type}")
                print(f"📏 File Size: {len(file_content) / 1024:.2f} KB")
            else:
                raise ValueError("Either file_path, (file_bytes and file_mime_type), or images must be provided")

            print(f"💬 Prompt length: {len(prompt)} chars")

            if config.provider == ModelProvider.GOOGLE and GOOGLE_AVAILABLE:
                try:
                    response_content = self._gemini_vision_call(images_data, prompt, config, tool_name=tool_name)
                except Exception as gemini_error:
                    print(f"⚠️ Gemini vision failed: {gemini_error}")
                    print("🔄 Falling back to OpenAI...")
                    if ModelProvider.OPENAI in self._clients:
                        response_content = self._openai_vision_call(images_data, prompt, config)
                    else:
                        raise gemini_error
            elif config.provider == ModelProvider.OPENAI and OPENAI_AVAILABLE:
                response_content = self._openai_vision_call(images_data, prompt, config)
            else:
                raise ValueError(f"Vision not supported for provider: {config.provider}")

            char_count = len(prompt) + len(response_content)
            estimated_tokens = char_count // 4

            usage = {
                "total_tokens": estimated_tokens,
                "completion_tokens": len(response_content) // 4,
                "prompt_tokens": estimated_tokens - (len(response_content) // 4)
            }

            elapsed_time = time.time() - start_time
            print("\n" + "=" * 80)
            print("✅ VISION LLM API CALL SUCCESSFUL")
            print("=" * 80)
            print(f"⏱️ Time Elapsed: {elapsed_time:.2f}s")
            print(f"📝 Response Length: {len(response_content)} characters")
            print("=" * 80 + "\n")

            return StandardizedLLMResponse(
                content=response_content,
                usage=usage
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            print("\n" + "=" * 80)
            print("❌ VISION LLM API CALL FAILED")
            print("=" * 80)
            print(f"⏱️ Time Elapsed: {elapsed_time:.2f}s")
            print(f"❗ Error Type: {type(e).__name__}")
            print(f"❗ Error Message: {str(e)}")
            print("=" * 80 + "\n")
            raise

    def _gemini_vision_call(
            self,
            images_data: List[Dict[str, Any]],
            prompt: str,
            config: ModelConfig,
            tool_name=None,
    ) -> str:
        """Make a vision API call using Gemini with native PDF/image support."""
        client = self._clients[ModelProvider.GOOGLE]

        print(f"\n⏳ Calling Gemini Vision API with {len(images_data)} file(s)...")

        if len(images_data) == 1 and images_data[0]['mime_type'] == 'application/pdf':
            import tempfile
            import os

            file_content = images_data[0]['bytes']
            mime_type = images_data[0]['mime_type']

            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                tmp.write(file_content)
                tmp_path = tmp.name

            try:
                print("📤 Uploading PDF to Gemini Files API...")
                uploaded_file = client.files.upload(file=tmp_path)
                print(f"✅ File uploaded: {uploaded_file.name}")

                contents = [
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_uri(
                                file_uri=uploaded_file.uri,
                                mime_type=mime_type
                            ),
                            types.Part.from_text(text=prompt)
                        ]
                    )
                ]
            finally:
                os.unlink(tmp_path)
        else:
            parts = []
            for i, img in enumerate(images_data):
                print(f"   📷 Image {i + 1}: {img['mime_type']} ({len(img['bytes']) / 1024:.1f} KB)")
                parts.append(
                    types.Part.from_bytes(
                        data=img['bytes'],
                        mime_type=img['mime_type']
                    )
                )
            parts.append(types.Part.from_text(text=prompt))

            contents = [
                types.Content(
                    role="user",
                    parts=parts
                )
            ]

        generation_config = types.GenerateContentConfig(**_gemini_settings(tool_name, config))

        resolved_model = config.model_name
        response = client.models.generate_content(
            model=resolved_model,
            contents=contents,
            config=generation_config
        )

        response_content = ""
        if hasattr(response, 'text') and response.text:
            response_content = response.text
        elif hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                for part in candidate.content.parts:
                    if hasattr(part, 'text') and part.text:
                        response_content += part.text

        return response_content

    def _openai_vision_call(
            self,
            images_data: List[Dict[str, Any]],
            prompt: str,
            config: ModelConfig
    ) -> str:
        """Make a vision API call using OpenAI GPT-5.2."""
        import base64

        client = self._clients[ModelProvider.OPENAI]

        print(f"\n⏳ Calling OpenAI Vision API with {len(images_data)} file(s)...")

        if len(images_data) == 1 and images_data[0]['mime_type'] == 'application/pdf':
            import tempfile
            import os

            file_content = images_data[0]['bytes']

            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                tmp.write(file_content)
                tmp_path = tmp.name

            try:
                print("📤 Uploading PDF to OpenAI...")
                with open(tmp_path, 'rb') as f:
                    uploaded_file = client.files.create(
                        file=f,
                        purpose='assistants'
                    )
                print(f"✅ File uploaded: {uploaded_file.id}")

                messages = [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "file",
                                "file": {"file_id": uploaded_file.id}
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            finally:
                os.unlink(tmp_path)
        else:
            content = []
            for i, img in enumerate(images_data):
                encoded_content = base64.b64encode(img['bytes']).decode('utf-8')
                print(f"   📷 Image {i + 1}: {img['mime_type']} ({len(img['bytes']) / 1024:.1f} KB)")
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{img['mime_type']};base64,{encoded_content}",
                        "detail": "high"
                    }
                })
            content.append({
                "type": "text",
                "text": prompt
            })

            messages = [
                {
                    "role": "user",
                    "content": content
                }
            ]

        params = {
            "model": "gpt-5.2",
            "temperature": 1.0,
            "messages": messages,
        }

        if config.max_tokens:
            params["max_completion_tokens"] = config.max_tokens

        response = client.chat.completions.create(**params)

        return response.choices[0].message.content

    def generate_image(
            self,
            prompt: str,
            aspect_ratio: str = "1:1",
            reference_images: List[bytes] = None,
    ) -> GeneratedImageResponse:
        """
        Generate an image. Uses Imagen 4.0 on Vertex AI, Gemini image on public API.

        Args:
            prompt: The text prompt describing the desired image
            aspect_ratio: Image aspect ratio (1:1, 4:3, 3:4, 16:9, 9:16)
            reference_images: Optional list of image bytes to use as style references (up to 6)

        Returns:
            GeneratedImageResponse with the result
        """
        import time
        from io import BytesIO
        from PIL import Image as PILImage

        start_time = time.time()

        if self._using_vertex_ai:
            model_id = "imagen-4.0-fast-generate-001"
        else:
            model_id = "gemini-3-pro-image-preview"

        print("\n" + "=" * 80)
        print("🎨 IMAGE GENERATION API CALL STARTED")
        print("=" * 80)
        backend = "Vertex AI" if self._using_vertex_ai else "Public API"
        print(f"📍 Provider: GOOGLE ({backend})")
        print(f"🧠 Model: {model_id}")
        print(f"📐 Aspect Ratio: {aspect_ratio}")
        if reference_images:
            print(f"🖼️  Reference Images: {len(reference_images)}")
        print(f"💬 Prompt: {prompt[:200]}..." if len(prompt) > 200 else f"💬 Prompt: {prompt}")
        print("-" * 80)

        if not GOOGLE_AVAILABLE:
            error_msg = "Google GenAI library not available. Install with: pip install google-genai"
            print(f"❌ {error_msg}")
            return GeneratedImageResponse(success=False, error=error_msg, prompt_used=prompt)

        if ModelProvider.GOOGLE not in self._clients:
            error_msg = "Google client not initialized. Check GEMINI_API_KEY or VERTEX_AI_PROJECT."
            print(f"❌ {error_msg}")
            return GeneratedImageResponse(success=False, error=error_msg, prompt_used=prompt)

        try:
            client = self._clients[ModelProvider.GOOGLE]

            # Vertex AI: use Imagen 4.0 dedicated image generation API
            if self._using_vertex_ai:
                return self._imagen_generate(client, model_id, prompt, aspect_ratio, start_time)

            # Public API: use Gemini multimodal image generation
            return self._gemini_image_generate(client, model_id, prompt, aspect_ratio, reference_images, start_time)

        except Exception as e:
            elapsed_time = time.time() - start_time
            error_msg = str(e)

            print("\n" + "=" * 80)
            print("❌ IMAGE GENERATION FAILED")
            print("=" * 80)
            print(f"⏱️  Time Elapsed: {elapsed_time:.2f}s")
            print(f"❗ Error Type: {type(e).__name__}")
            print(f"❗ Error Message: {error_msg}")
            print("=" * 80 + "\n")

            return GeneratedImageResponse(
                success=False,
                error=error_msg,
                prompt_used=prompt
            )

    def _imagen_generate(self, client, model_id, prompt, aspect_ratio, start_time):
        """Generate image using Imagen 4.0 on Vertex AI."""
        import time

        print(f"\n⏳ Calling Imagen 4.0 API...")

        response = client.models.generate_images(
            model=model_id,
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio=aspect_ratio,
            )
        )

        elapsed_time = time.time() - start_time

        if response.generated_images:
            image_bytes = response.generated_images[0].image.image_bytes
            print("\n" + "=" * 80)
            print("✅ IMAGE GENERATION SUCCESSFUL")
            print("=" * 80)
            print(f"⏱️  Time Elapsed: {elapsed_time:.2f}s")
            print(f"📏 Image Size: {len(image_bytes) / 1024:.1f} KB")
            print("=" * 80 + "\n")

            return GeneratedImageResponse(
                success=True,
                image_bytes=image_bytes,
                mime_type="image/png",
                prompt_used=prompt,
            )
        else:
            print("\n" + "=" * 80)
            print("❌ IMAGE GENERATION FAILED")
            print("=" * 80)
            print(f"⏱️  Time Elapsed: {elapsed_time:.2f}s")
            print("❗ Error: No image was generated by the model")
            print("=" * 80 + "\n")

            return GeneratedImageResponse(
                success=False,
                error="No image was generated by the model",
                prompt_used=prompt,
            )

    def _gemini_image_generate(self, client, model_id, prompt, aspect_ratio, reference_images, start_time):
        """Generate image using Gemini multimodal on public API."""
        import time
        from io import BytesIO
        from PIL import Image as PILImage

        contents = [prompt]

        if reference_images:
            for i, img_bytes in enumerate(reference_images[:6]):
                try:
                    img = PILImage.open(BytesIO(img_bytes))
                    contents.append(img)
                    print(f"   ✅ Added reference image {i+1} ({len(img_bytes) / 1024:.1f} KB)")
                except Exception as e:
                    print(f"   ⚠️ Failed to load reference image {i+1}: {e}")

        if aspect_ratio != '1:1':
            enhanced_prompt = f"[Image should be {aspect_ratio} aspect ratio] {prompt}"
            contents[0] = enhanced_prompt

        print("\n⏳ Calling Gemini Image Generation API...")

        response = client.models.generate_content(
            model=model_id,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=['TEXT', 'IMAGE'],
            )
        )

        image_bytes = None
        thinking_text = None

        if response.candidates and len(response.candidates) > 0:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content:
                for part in candidate.content.parts:
                    if hasattr(part, 'text') and part.text:
                        thinking_text = part.text
                    elif hasattr(part, 'inline_data') and part.inline_data:
                        image_bytes = part.inline_data.data
                        print(f"   ✅ Got image: {part.inline_data.mime_type}, {len(image_bytes) / 1024:.1f} KB")

        if not image_bytes and hasattr(response, 'parts'):
            for part in response.parts:
                if hasattr(part, 'inline_data') and part.inline_data:
                    image_bytes = part.inline_data.data

        elapsed_time = time.time() - start_time

        if image_bytes:
            print("\n" + "=" * 80)
            print("✅ IMAGE GENERATION SUCCESSFUL")
            print("=" * 80)
            print(f"⏱️  Time Elapsed: {elapsed_time:.2f}s")
            print(f"📏 Image Size: {len(image_bytes) / 1024:.1f} KB")
            print("=" * 80 + "\n")

            return GeneratedImageResponse(
                success=True,
                image_bytes=image_bytes,
                mime_type="image/png",
                prompt_used=prompt,
                thinking_text=thinking_text
            )
        else:
            print("\n" + "=" * 80)
            print("❌ IMAGE GENERATION FAILED")
            print("=" * 80)
            print(f"⏱️  Time Elapsed: {elapsed_time:.2f}s")
            print("❗ Error: No image was generated by the model")
            if thinking_text:
                print(f"💭 Model response: {thinking_text}")
            print("=" * 80 + "\n")

            return GeneratedImageResponse(
                success=False,
                error="No image was generated by the model",
                prompt_used=prompt,
                thinking_text=thinking_text
            )


class LLMConfig:
    """Configuration class for LLM models"""

    def __init__(self):
        self.default_model = 'gemini-flash'

    def get_available_models(self):
        """Return list of (model_id, display_name) tuples for available models"""
        models = []
        for model_id in MODEL_CONFIG.keys():
            config = MODEL_CONFIG[model_id]
            display_name = f"{model_id.upper()} ({config.provider.value})"
            models.append((model_id, display_name))
        return models


def optimize_generated_image(
    image_bytes: bytes,
    max_width: int = 800,
    quality: int = 85,
) -> bytes:
    """
    Optimize a generated image for web use.

    Args:
        image_bytes: Raw image bytes
        max_width: Maximum width in pixels
        quality: JPEG quality (1-100)

    Returns:
        Optimized JPEG image bytes
    """
    from io import BytesIO
    from PIL import Image as PILImage

    img = PILImage.open(BytesIO(image_bytes))

    if img.mode in ('RGBA', 'LA', 'P'):
        background = PILImage.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        if img.mode in ('RGBA', 'LA'):
            background.paste(img, mask=img.split()[-1])
        else:
            background.paste(img)
        img = background
    elif img.mode != 'RGB':
        img = img.convert('RGB')

    if img.width > max_width:
        ratio = max_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((max_width, new_height), PILImage.Resampling.LANCZOS)

    output = BytesIO()
    img.save(output, format='JPEG', quality=quality, optimize=True)
    output.seek(0)

    return output.getvalue()
