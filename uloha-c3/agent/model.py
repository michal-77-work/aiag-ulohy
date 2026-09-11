"""How the agent reaches an LLM.

Uses OpenAI directly: gpt-5.6-luna by default, override with OPENAI_MODEL in .env.
The key comes from OPENAI_API_KEY in the environment / .env.
"""

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")


def get_model(model: str = DEFAULT_MODEL, **kwargs) -> ChatOpenAI:
    """A chat model. We don't pass temperature: the GPT-5 models only support the default."""
    return ChatOpenAI(
        model=model,
        api_key=os.environ["OPENAI_API_KEY"],
        # gpt-5.6 models accept tools together with reasoning only on the Responses API.
        use_responses_api=True,
        **kwargs,
    )
