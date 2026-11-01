# Workflow eficiente — Google Antigravity (31/10/2026)

O Antigravity IDE 2.6.0 (26/10/2026) inclui arquitetura de agente atualizada. Para reduzir custo e alucinações no Flash: **AGENTS.md curto + skills sob demanda + comandos de verificação**, não prompts monolíticos.

Documentação oficial: https://antigravity.google/docs/rules/ ; https://antigravity.google/docs/skills ; https://antigravity.google/docs/migration/workflows-to-skills ; https://antigravity.google/docs/subagents ; https://antigravity.google/changelog

## Despacho por objetivo
1. **Setup/quebra no Windows:** `/windows-poc` — instalar uma vez, verificar.
2. **MVP com contatos consentidos:** `/real-pilot` — usar a base local e registrar candidatos/confirmados.
3. **Auditar código/PR:** `/review-pr` — ler o diff e executar testes, sem reprocessar todo o repo.
4. **Investigação externa de API:** produzir nota técnica separada; código existente não faz reverse lookup.

## Loop mínimo para agente Flash
1. `git status -sb`; confirmar HEAD/PR. Não vasculhar outros projetos sem necessidade.
2. Escolher **um** skill e executar `--help` do script antes de ler sua implementação (orientação oficial de progressive disclosure).
3. Definir resultado observável e 1–3 arquivos impactados. `/plan` se a mudança for extensa; não criar planejamento infinito.
4. Primeiro executar apenas teste focal. Alterar uma causa e adicionar regressão. Depois rodar pytest completo e conferir CI.
5. Registrar **SHA + comandos + exit code + evidência**, com diagnóstico P0/P1/P2. Nunca publicar contatos ou credenciais.
6. Parar após passar o objetivo. Não repetir setup/pip/testes completos por tentativa de ganhar confiança sem mudança de código.

## Gates proporcionais
- Código: testes focal + suíte geral + CI da SHA final.
- MVP de campo: somente contatos com finalidade autorizada, pastas privadas, status candidato x confirmado e métricas agregadas.
- Integrações reais: avaliar individualmente Meta, termos e consentimento; não presumir que uma API privada é permitida.
- Merge/CRM produção: dependem da revisão do mantenedor e não são subprodutos automáticos do teste.

Os workflows legados (`.agents/workflows/`) foram substituídos por skills; não criar arquivos antigos.
