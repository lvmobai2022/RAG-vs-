"""DeepSeek（OpenAI 兼容接口）客户端封装。"""

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

_client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def chat_completion(system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
    """调用 DeepSeek 对话接口，返回纯文本回答。"""
    response = _client.chat.completions.create(
        model=settings.deepseek_model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content or ""
