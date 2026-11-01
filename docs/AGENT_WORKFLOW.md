# Workflow canônico Antigravity (31/10/2026)

## Por que esta estrutura
O Google Antigravity passou a priorizar **Rules** em `AGENTS.md`, **Agent Skills** em `.agents/skills/<name>/SKILL.md` (carregamento sob demanda), e agentes especializados em `.agents/agents/`. Os antigos arquivos `.agents/workflows/*.md` deixam de funcionar a partir de 19/10/2026; não criar novos workflows legados.

Referências oficiais:
- https://antigravity.google/docs/rules/
- https://antigravity.google/docs/skills
- https://antigravity.google/docs/migration/workflows-to-skills
- https://antigravity.google/docs/customization-discovery
- https://antigravity.google/docs/subagents
- https://antigravity.google/docs/changelog

## Rotina enxuta para um agente econômico (Flash)

1. **Descobrir:** leia `AGENTS.md`; `git status -sb`, `git log -3 --oneline`; leia a PR/issue e o arquivo alvo. Não varra o CRM nem outros repositórios.
2. **Planejar:** escrever problema, escopo, hipóteses, arquivos impactados, reprodução e critérios de aceite; usar `/plan` quando disponível e revisar antes de codificar.
3. **Executar:** patch cirúrgico, uma responsabilidade por alteração, sem reestruturação especulativa. Não sobrescrever alterações alheias.
4. **Validar:** pytest, script de Windows 2x, casos negativos, `git diff --check`, `git status --short`, inspeção sem PII, CI por SHA.
5. **Revisar:** acionar skill `/review-pr` e opcionalmente o agente `offline-reviewer` (se a instalação suporta custom agents). Use evidência de execução, não suposições.
6. **Publicar:** commits pequenos, PR em Draft; descrever arquivos, resultados, riscos, links de CI/issue. Nada de merge automático.

## Gates
- **G0 Repositório:** branch correta, worktree íntegra, nenhum arquivo pessoal rastreado.
- **G1 Qualidade:** pytest e entrada sintética 100/100; testes negativos; repetibilidade Windows.
- **G2 Segurança:** zero credenciais, PII, scraping, integrações externas ou persistência indevida.
- **G3 Revisão:** CI real verde na SHA final; revisão do PR e autorização do mantenedor.
- **G4 Futuro — não autorizado:** qualquer CRM real, Meta/Instagram, consentimento externo, upload, identificação de pessoas. Exige aprovação separada e análise legal/termos. Não inferir que G3 habilita G4.

## Relatório de evidências
Use markdown (sem dados pessoais): branch, HEAD SHA, versões do Windows/Python, comandos e exit codes, pytest pass/fail, testes negativos, links para runs, `git status`, problemas P0/P1/P2, recomendação GO/NO-GO restrita a G0–G3. **Não publicar dumps ou screenshots que contenham nomes, e-mails, telefones.**
