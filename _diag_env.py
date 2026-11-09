"""Adiciona/atualiza GEMINI_MODEL no .env sem imprimir a chave."""
import os
import re

CAMINHO = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
MODELO = "gemini-3.8-flash"

with open(CAMINHO, "r", encoding="utf-8") as f:
    linhas = f.read().splitlines()

saida = []
tem_modelo = False
for linha in linhas:
    if re.match(r"^\s*GEMINI_MODEL\s*=", linha):
        saida.append(f"GEMINI_MODEL={MODELO}")
        tem_modelo = True
    else:
        saida.append(linha)

if not tem_modelo:
    saida.append("")
    saida.append(f"GEMINI_MODEL={MODELO}")

with open(CAMINHO, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(saida).rstrip() + "\n")

# Mostra apenas os NOMES das variáveis, nunca os valores
print("variaveis no .env:", [l.split("=")[0].strip() for l in saida if "=" in l and not l.strip().startswith("#")])
