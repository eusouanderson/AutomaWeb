Using "Fetch Web Page"

Fetched 3 resources

Resumo do uso da Groq API (Python):

1) Crie a chave: https://console.groq.com/keys  
2) Defina a variável de ambiente: `GROQ_API_KEY`  
3) Instale o SDK: `pip install groq`  
4) Exemplo mínimo:

```python
import os
from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

resp = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": "Olá!"}],
)

print(resp.choices[0].message.content)
```

Endpoint compatível OpenAI: `https://api.groq.com/openai/v1/chat/completions`

