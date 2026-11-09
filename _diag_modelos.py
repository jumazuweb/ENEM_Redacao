"""Lista modelos disponiveis para a chave do .env sem expor o segredo."""
import os

from dotenv import load_dotenv

load_dotenv(override=True)

chave = (os.environ.get("GEMINI_API_KEY") or "").strip()
if not chave:
    print("CHAVE_VAZIA: GEMINI_API_KEY nao encontrada no .env")
    raise SystemExit(1)

print(f"chave carregada: {len(chave)} caracteres, prefixo='{chave[:3]}', sufixo='...{chave[-2:]}'")

from google import genai

client = genai.Client(api_key=chave)

try:
    modelos = list(client.models.list())
except Exception as erro:
    print(f"ERRO_AO_LISTAR: {type(erro).__name__}: {erro}")
    raise SystemExit(2)

print(f"total de modelos: {len(modelos)}")
print("--- modelos com 'flash' no nome ---")
for m in modelos:
    nome = getattr(m, "name", "")
    if "flash" in nome.lower():
        metodos = getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", "")
        print(f"  {nome}   {metodos}")
