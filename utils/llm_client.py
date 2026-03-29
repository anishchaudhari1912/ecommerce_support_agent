import os
from dotenv import load_dotenv
from groq import Groq
import time
load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def call_llm(
    system: str,
    user: str,
    model: str = "llama-3.1-8b-instant",
    temperature: float = 0.1,
    max_tokens: int = 500,
    retries: int = 3,
):
    
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )

            return response.choices[0].message.content  # ✅ correct indent

        except Exception as e:
            print(f"[Retry {attempt+1}] Error: {e}")
            time.sleep(2)

    raise RuntimeError("Failed after retries")