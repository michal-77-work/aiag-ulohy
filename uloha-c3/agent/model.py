"""How the agent reaches an LLM.

Uses OpenAI directly (gpt-5-nano), consistent with uloha-c1 / uloha-c2. The key
comes from OPENAI_API_KEY in the environment / .env.
"""

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-nano")


def get_model(model: str = DEFAULT_MODEL, **kwargs) -> ChatOpenAI:
    """A chat model. temperature is left at the model default (gpt-5-nano only
    supports the default), so we don't pass it."""
    return ChatOpenAI(
        model=model,
        api_key=os.environ["OPENAI_API_KEY"],
        **kwargs,
    )
