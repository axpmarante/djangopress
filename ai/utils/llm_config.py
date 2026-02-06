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
    import google.generativeai as genai
    GOOGLE_AVAILABLE = True
except ImportError:
    genai = None
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
        # Set provider-specific defaults based on the provider
        if self.provider == ModelProvider.GOOGLE:
            # For Google, ensure we use max_output_tokens instead of max_tokens
            if self.max_tokens is not None and self.max_output_tokens is None:
                self.max_output_tokens = self.max_tokens
                self.max_tokens = None

            # Set Gemini-specific defaults if not provided
            if "generation_config" not in self.provider_params:
                self.provider_params["generation_config"] = {
                    "top_p": 0.95,
                    "top_k": 40
                }

        elif self.provider == ModelProvider.ANTHROPIC:
            # Anthropic uses max_tokens, ensure it's set
            if self.max_tokens is None and self.max_output_tokens is not None:
                self.max_tokens = self.max_output_tokens
                self.max_output_tokens = None

        elif self.provider == ModelProvider.OPENAI:
            # OpenAI uses max_tokens (or max_completion_tokens in newer versions)
            if self.max_tokens is None and self.max_output_tokens is not None:
                self.max_tokens = self.max_output_tokens
                self.max_output_tokens = None


# Model configurations for different providers
MODEL_CONFIG = {
    # ===== OPENAI MODELS =====
    'gpt-5': ModelConfig(
        provider=ModelProvider.OPENAI,
        model_name="gpt-5-2025-08-07",
        max_tokens=8192,
        temperature=1.0  # GPT-5 only supports temperature=1
    ),
    'gpt-5-mini': ModelConfig(
        provider=ModelProvider.OPENAI,
        model_name="gpt-5-mini-2025-08-07",
        max_tokens=8192,
        temperature=1.0  # GPT-5 only supports temperature=1
    ),

    # ===== ANTHROPIC MODELS =====
    'claude': ModelConfig(
        provider=ModelProvider.ANTHROPIC,
        model_name="claude-sonnet-4-5-20250929",  # Latest Sonnet 4.5
        max_tokens=8192,
        temperature=0.3
    ),

    # ===== GOOGLE MODELS =====
    'gemini-pro': ModelConfig(
        provider=ModelProvider.GOOGLE,
        model_name="gemini-2.5-pro",
        max_output_tokens=15000,
        temperature=0.3,
        provider_params={
            "generation_config": {
                "top_p": 0.95,
                "top_k": 40
            }
        }
    ),
    'gemini-flash': ModelConfig(
        provider=ModelProvider.GOOGLE,
        model_name="gemini-2.5-flash",
        max_output_tokens=15000,
        temperature=0.3,
        provider_params={
            "generation_config": {
                "top_p": 0.95,
                "top_k": 40
            }
        }
    ),
    'gemini-lite': ModelConfig(
        provider=ModelProvider.GOOGLE,
        model_name="gemini-2.5-flash-lite",
        max_output_tokens=8192,
        temperature=0.3,
        provider_params={
            "generation_config": {
                "top_p": 0.95,
                "top_k": 40
            }
        }
    )
}



class StandardizedLLMResponse:
    """Standardized response format across all providers"""

    def __init__(self, content: str, usage: Dict[str, int] = None):
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

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Initialize OpenAI client if not already done
        if ModelProvider.OPENAI not in self._clients and OPENAI_AVAILABLE:
            openai_key = get_env('OPENAI_API_KEY')
            if openai_key:
                self._clients[ModelProvider.OPENAI] = OpenAI(api_key=openai_key)

        # Initialize Anthropic client if not already done
        if ModelProvider.ANTHROPIC not in self._clients and ANTHROPIC_AVAILABLE:
            anthropic_key = get_env('ANTHROPIC_API_KEY')
            if anthropic_key:
                self._clients[ModelProvider.ANTHROPIC] = Anthropic(api_key=anthropic_key)

        # Initialize Google client if not already done
        if ModelProvider.GOOGLE not in self._clients and GOOGLE_AVAILABLE:
            google_key = get_env('GEMINI_API_KEY')
            if google_key:
                genai.configure(api_key=google_key)
                self._clients[ModelProvider.GOOGLE] = genai

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
            # Extract system message if present
            system_content = ""
            for msg in messages:
                if msg.get('role') == 'system':
                    system_content += msg.get('content', '') + "\n\n"

            # Format the rest of the messages
            for msg in messages:
                role = msg.get('role', '')
                content = msg.get('content', '')

                # Ensure content is a string
                if not isinstance(content, str):
                    content = str(content)

                if role == 'system':
                    # Skip system messages as they're handled separately
                    continue
                elif role == 'user':
                    gemini_messages.append({"role": "user", "parts": [content]})
                elif role == 'assistant':
                    gemini_messages.append({"role": "model", "parts": [content]})
                else:
                    # Default to user for unknown roles
                    print(f"Warning: Unknown message role '{role}', treating as user message")
                    gemini_messages.append({"role": "user", "parts": [content]})

            # If there was a system message, prepend it to the first user message
            if system_content and gemini_messages and gemini_messages[0]["role"] == "user":
                gemini_messages[0]["parts"][0] = f"{system_content}\n\n{gemini_messages[0]['parts'][0]}"

            # If no messages were created, create a default one with just the system content
            if not gemini_messages:
                gemini_messages.append({"role": "user", "parts": [system_content or "Hello"]})

            return gemini_messages
        except Exception as e:
            print(f"Error formatting messages for Gemini: {str(e)}")
            # Return a simple default message if formatting fails
            return [{"role": "user", "parts": ["Hello, can you help me?"]}]


    def get_completion(
            self,
            messages: List[Dict[str, str]],
            tool_name: str = None,
            **kwargs
    ) -> StandardizedLLMResponse:
        """Get chat completion with model-specific configs"""
        import time
        start_time = time.time()

        config = MODEL_CONFIG.get(tool_name, ModelConfig())

        # Print API call details
        print("\n" + "="*80)
        print("🤖 LLM API CALL STARTED")
        print("="*80)
        print(f"📍 Provider: {config.provider.value.upper()}")
        print(f"🔧 Tool Name: {tool_name or 'default'}")
        print(f"🧠 Model: {config.model_name}")
        print(f"🌡️  Temperature: {config.temperature}")

        # Print correct token parameter based on provider
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
            # Show full content for debugging (can be configured)
            SHOW_FULL_CONTENT = True  # Set to False to truncate
            if SHOW_FULL_CONTENT:
                content_preview = content
            else:
                content_preview = content if len(content) <= 200 else content[:200] + "... (truncated)"
            print(f"\n[{i}] {role}:")
            print(f"{content_preview}")
        print("-" * 80)

        try:
            # Check if the requested provider is available
            if config.provider == ModelProvider.OPENAI and not OPENAI_AVAILABLE:
                raise ImportError("OpenAI library not installed. Install with: pip install openai")
            elif config.provider == ModelProvider.ANTHROPIC and not ANTHROPIC_AVAILABLE:
                raise ImportError("Anthropic library not installed. Install with: pip install anthropic")
            elif config.provider == ModelProvider.GOOGLE and not GOOGLE_AVAILABLE:
                raise ImportError("Google Generative AI library not installed. Install with: pip install google-generativeai")
            
            # Check if we have the client for the requested provider
            if config.provider not in self._clients:
                raise ValueError(f"Provider {config.provider} not initialized. Check API key.")

            if config.provider == ModelProvider.OPENAI:
                # OpenAI implementation
                client = self._clients[ModelProvider.OPENAI]

                params = {
                    "model": config.model_name,
                    "temperature": config.temperature,
                    "messages": messages,
                    **kwargs
                }

                # Add max_tokens if specified (use max_completion_tokens for newer models)
                if config.max_tokens:
                    # Check if this is a newer model that requires max_completion_tokens
                    if "gpt-5" in config.model_name.lower():
                        params["max_completion_tokens"] = config.max_tokens
                    else:
                        params["max_tokens"] = config.max_tokens

                if config.response_format:
                    params["response_format"] = config.response_format

                # Add any provider-specific parameters
                if config.provider_params:
                    params.update(config.provider_params)

                print("\n⏳ Calling OpenAI API...")
                response = client.chat.completions.create(**params)

                # Extract and format response
                response_content = response.choices[0].message.content
                usage = {
                    "total_tokens": response.usage.total_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "prompt_tokens": response.usage.prompt_tokens
                }

                # Print success info
                elapsed_time = time.time() - start_time
                print("\n" + "="*80)
                print("✅ LLM API CALL SUCCESSFUL")
                print("="*80)
                print(f"⏱️  Time Elapsed: {elapsed_time:.2f}s")
                print(f"📊 Token Usage:")
                print(f"   - Prompt: {usage['prompt_tokens']}")
                print(f"   - Completion: {usage['completion_tokens']}")
                print(f"   - Total: {usage['total_tokens']}")
                print(f"📝 Response Length: {len(response_content)} characters")
                # Show full response
                SHOW_FULL_RESPONSE = True  # Set to False to truncate
                if SHOW_FULL_RESPONSE:
                    print(f"📄 Full Response:\n{response_content}")
                else:
                    print(f"📄 Response Preview: {response_content[:150]}..." if len(response_content) > 150 else f"📄 Response: {response_content}")
                print("="*80 + "\n")

                return StandardizedLLMResponse(
                    content=response_content,
                    usage=usage
                )

            elif config.provider == ModelProvider.ANTHROPIC:
                # Anthropic implementation
                client = self._clients[ModelProvider.ANTHROPIC]

                formatted_messages, system_message = self._format_messages_for_claude(messages)

                params = {
                    "model": config.model_name,
                    "max_tokens": config.max_tokens,
                    "temperature": config.temperature,
                    "messages": formatted_messages
                }

                # Add system message if present
                if system_message:
                    params["system"] = system_message

                # Add any provider-specific parameters
                if config.provider_params:
                    params.update(config.provider_params)

                print("\n⏳ Calling Anthropic (Claude) API...")
                response = client.messages.create(**params)

                # Extract and format response
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

                # Print success info
                elapsed_time = time.time() - start_time
                print("\n" + "="*80)
                print("✅ LLM API CALL SUCCESSFUL")
                print("="*80)
                print(f"⏱️  Time Elapsed: {elapsed_time:.2f}s")
                print(f"📊 Token Usage:")
                print(f"   - Prompt: {usage['prompt_tokens']}")
                print(f"   - Completion: {usage['completion_tokens']}")
                print(f"   - Total: {usage['total_tokens']}")
                print(f"📝 Response Length: {len(response_content)} characters")
                # Show full response
                SHOW_FULL_RESPONSE = True  # Set to False to truncate
                if SHOW_FULL_RESPONSE:
                    print(f"📄 Full Response:\n{response_content}")
                else:
                    print(f"📄 Response Preview: {response_content[:150]}..." if len(response_content) > 150 else f"📄 Response: {response_content}")
                print("="*80 + "\n")

                return StandardizedLLMResponse(
                    content=response_content,
                    usage=usage
                )

            elif config.provider == ModelProvider.GOOGLE:
                # Google Gemini implementation
                client = self._clients[ModelProvider.GOOGLE]

                # Convert message format for Gemini
                gemini_messages = self._format_messages_for_gemini(messages)

                # Configure generation parameters
                generation_config = {
                    "temperature": config.temperature,
                    "top_p": 0.95,
                    "top_k": 40,
                }

                # Add max_output_tokens if specified
                if config.max_output_tokens:
                    generation_config["max_output_tokens"] = config.max_output_tokens

                # Update with any provider-specific parameters
                if config.provider_params and 'generation_config' in config.provider_params:
                    generation_config.update(config.provider_params['generation_config'])

                # Get the model
                model = client.GenerativeModel(
                    model_name=config.model_name,
                    generation_config=generation_config
                )

                try:
                    print("\n⏳ Calling Google Gemini API...")

                    # If it's a chat, use the chat method
                    if len(gemini_messages) > 1:
                        print(f"   Using chat mode with {len(gemini_messages)} messages")
                        chat = model.start_chat(history=gemini_messages[:-1])
                        response = chat.send_message(gemini_messages[-1]["parts"][0])
                    else:
                        print(f"   Using single message mode")
                        # For a single message, use the generate_content method
                        response = model.generate_content(gemini_messages[0]["parts"][0])

                    # Extract response content
                    response_content = ""
                    try:
                        if hasattr(response, 'text') and response.text:
                            response_content = response.text
                        elif hasattr(response, 'candidates') and response.candidates:
                            # Try to extract text from candidates
                            candidate = response.candidates[0]
                            if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                                for part in candidate.content.parts:
                                    if hasattr(part, 'text') and part.text:
                                        response_content += part.text

                    except Exception as content_error:
                        print(f"  ⚠️ Error extracting content: {content_error}")
                        response_content = "I apologize, but I'm having trouble processing your request."

                except Exception as gemini_error:
                    print("\n" + "="*80)
                    print("❌ GEMINI API ERROR")
                    print("="*80)
                    print(f"⚠️  Error Type: {type(gemini_error).__name__}")
                    print(f"⚠️  Error Message: {str(gemini_error)}")
                    print("🔄 Attempting fallback to OpenAI...")
                    print("="*80)

                    # Fall back to OpenAI if Gemini fails
                    if ModelProvider.OPENAI in self._clients:
                        fallback_client = self._clients[ModelProvider.OPENAI]
                        fallback_params = {
                            "model": "gpt-4o-mini",  # Use a reliable model as fallback
                            "temperature": config.temperature,
                            "max_tokens": 10000,
                            "messages": messages
                        }

                        print("⏳ Calling OpenAI as fallback...")
                        fallback_response = fallback_client.chat.completions.create(**fallback_params)

                        response_content = fallback_response.choices[0].message.content
                        print("✅ Successfully used OpenAI fallback.")
                    else:
                        # If OpenAI is not available, re-raise the original error
                        print("❌ OpenAI fallback not available. Re-raising error.")
                        raise gemini_error

                # Gemini doesn't provide token usage directly in the same way as OpenAI
                # Approximate based on character count
                char_count = sum(len(msg.get('content', '')) for msg in messages) + len(response_content)
                estimated_tokens = char_count // 4  # Rough estimate

                usage = {
                    "total_tokens": estimated_tokens,
                    "completion_tokens": len(response_content) // 4,
                    "prompt_tokens": estimated_tokens - (len(response_content) // 4)
                }

                # Print success info
                elapsed_time = time.time() - start_time
                print("\n" + "="*80)
                print("✅ LLM API CALL SUCCESSFUL")
                print("="*80)
                print(f"⏱️  Time Elapsed: {elapsed_time:.2f}s")
                print(f"📊 Token Usage (estimated):")
                print(f"   - Prompt: ~{usage['prompt_tokens']}")
                print(f"   - Completion: ~{usage['completion_tokens']}")
                print(f"   - Total: ~{usage['total_tokens']}")
                print(f"📝 Response Length: {len(response_content)} characters")
                # Show full response
                SHOW_FULL_RESPONSE = True  # Set to False to truncate
                if SHOW_FULL_RESPONSE:
                    print(f"📄 Full Response:\n{response_content}")
                else:
                    print(f"📄 Response Preview: {response_content[:150]}..." if len(response_content) > 150 else f"📄 Response: {response_content}")
                print("="*80 + "\n")

                return StandardizedLLMResponse(
                    content=response_content,
                    usage=usage
                )

            else:
                raise ValueError(f"Unsupported provider: {config.provider}")

        except Exception as e:
            elapsed_time = time.time() - start_time
            print("\n" + "="*80)
            print("❌ LLM API CALL FAILED")
            print("="*80)
            print(f"📍 Provider: {config.provider.value.upper()}")
            print(f"🧠 Model: {config.model_name}")
            print(f"⏱️  Time Elapsed: {elapsed_time:.2f}s")
            print(f"❗ Error Type: {type(e).__name__}")
            print(f"❗ Error Message: {str(e)}")
            print("="*80 + "\n")
            raise

class LLMConfig:
    """Configuration class for LLM models"""

    def __init__(self):
        self.default_model = 'gemini-pro'  # Default model
        
    def get_available_models(self):
        """Return list of (model_id, display_name) tuples for available models"""
        models = []
        
        # Add available models from MODEL_CONFIG
        for model_id in MODEL_CONFIG.keys():
            config = MODEL_CONFIG[model_id]
            # Create a friendly display name
            display_name = f"{model_id.upper()} ({config.provider.value})"
            models.append((model_id, display_name))
        
        return models
