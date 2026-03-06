import os
from loguru import logger
import json

def get_llm(agent_name: str = None, provider: str = None, model: str = None, temperature: float = 0.1):
    """
    Returns a LangChain ChatModel instance.
    Supports dynamic overrides from data/model_overrides.json.
    """
    # ── Try Dynamic Overrides ─────────────────────────────────
    override_file = "/opt/trade_server/data/model_overrides.json"
    if not os.path.exists(override_file):
        # Fallback for local dev
        override_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "model_overrides.json"))

    if agent_name and os.path.exists(override_file):
        try:
            with open(override_file, "r") as f:
                data = json.load(f)
                # Support nested "overrides" key (new format) or flat (legacy)
                overrides = data.get("overrides", data) if isinstance(data, dict) else {}
                
                if agent_name in overrides:
                    config = overrides[agent_name]
                    if isinstance(config, dict):
                        provider = config.get("provider", provider)
                        model = config.get("model", model)
                        logger.info(f"[LLM] Dynamic override for {agent_name}: {provider}/{model}")
        except Exception as e:
            logger.error(f"[LLM] Error reading overrides: {e}")

    # ── Default Fallbacks ─────────────────────────────────────
    env_provider_key = f"{agent_name.upper()}_PROVIDER" if agent_name else "DEFAULT_LLM_PROVIDER"
    env_model_key    = f"{agent_name.upper()}_MODEL"    if agent_name else "DEFAULT_LLM_MODEL"

    provider = provider or os.getenv(env_provider_key) or os.getenv("DEFAULT_LLM_PROVIDER", "deepseek")
    model    = model or os.getenv(env_model_key)    or os.getenv("DEFAULT_LLM_MODEL", "deepseek-chat")

    logger.debug(f"[LLM] Loading {provider}/{model}")

    if provider == "deepseek":
        from langchain_deepseek import ChatDeepSeek
        return ChatDeepSeek(
            model=model,
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            temperature=temperature
        )
    
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model,
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            temperature=temperature
        )
    
    elif provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=temperature
        )
    
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model,
            api_key=os.getenv("OPENAI_API_KEY"),
            temperature=temperature
        )
    
    elif provider == "ollama":
        from langchain_ollama import ChatOllama
        base_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        return ChatOllama(
            model=model,
            base_url=base_url,
            temperature=temperature
        )
    
    elif provider == "xai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model or "grok-beta",
            api_key=os.getenv("XAI_API_KEY"),
            base_url="https://api.x.ai/v1",
            temperature=temperature
        )
    
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
