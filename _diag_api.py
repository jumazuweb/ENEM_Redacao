"""Testa a avaliacao real usando somente a chave do .env (sem passar chave manual)."""
import services.ai_evaluator as m

print("env carregado:", m.ENV_CARREGADO)
print("modelo configurado:", m.obter_modelo())
chave = m.obter_api_key()
print("chave presente:", bool(chave), "| tamanho:", len(chave), "| prefixo:", chave[:3])
print()

TEMA = "Os desafios da valorizacao do trabalho de cuidado no Brasil"
TEXTO = (
    "A Constituicao Federal de 1988 garante direitos sociais a todos os cidadaos brasileiros. "
    "No entanto, o trabalho de cuidado, exercido majoritariamente por mulheres, segue invisivel. "
    "Dessa forma, e necessario discutir os desafios dessa valorizacao.\n\n"
    "Primeiramente, a ausencia de politicas publicas especificas agrava a desigualdade. "
    "Segundo o IBGE, mulheres dedicam quase o dobro de horas a tarefas domesticas. "
    "Assim, a sobrecarga impede a insercao plena no mercado de trabalho.\n\n"
    "Ademais, a naturalizacao historica desse papel reforca a discriminacao. "
    "Conforme Bauman, a modernidade liquida torna as relacoes descartaveis. "
    "Portanto, o cuidado precisa ser reconhecido como trabalho.\n\n"
    "Diante disso, o Ministerio da Educacao deve criar campanhas de conscientizacao "
    "por meio de redes sociais, alcancando jovens em idade escolar, a fim de mitigar a problematica."
)

print("=== TESTE 1: avaliar_redacao com chave do .env ===")
try:
    res = m.avaliar_redacao(TEMA, TEXTO)
    print("OK | nota_total:", res.get("nota_total"))
    print("   c1..c5:", [res.get(k) for k in ("c1", "c2", "c3", "c4", "c5")])
    print("   parecer (80 chars):", str(res.get("parecer", ""))[:80])
    print("   tem redacao_modelo:", bool(res.get("redacao_modelo")))
except Exception as e:
    print("FALHOU:", type(e).__name__, "->", str(e)[:400])

print()
print("=== TESTE 2: gerar_redacao_customizada com chave do .env ===")
try:
    r = m.gerar_redacao_customizada(
        tema=TEMA,
        competencias={"c1": 200, "c2": 200, "c3": 200, "c4": 200, "c5": 200},
        vocabulario="Padrão ENEM",
        estilo_argumentacao="Tradicional/Clássico",
        repertorio="Constituição/Leis",
        tom_intervencao="Solução Governamental Direta",
    )
    print("OK | nota_alvo:", r["nota_alvo"])
    print("   paragrafos:", len([p for p in r["redacao"].split("\n\n") if p.strip()]))
    print("   caracteres:", len(r["redacao"]))
    print("   repertorios:", r["repertorios_usados"])
    print("   checklist_c5 chaves:", list(r["checklist_c5"].keys()))
except Exception as e:
    print("FALHOU:", type(e).__name__, "->", str(e)[:400])
