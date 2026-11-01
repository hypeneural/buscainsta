# BuscaInsta — regras permanentes (Antigravity, 2026)

Projeto: MVP Windows 11 para **avaliar** se contatos autorizados podem ser associados com segurança a perfis Instagram. Não confundir validade do CSV, conta sugerida e vínculo confirmado.

## Regras sempre ativas
- Leia somente os arquivos necessários à tarefa. Use os skills `windows-poc`, `real-pilot` ou `review-pr`; evite reler documentação inteira a cada turno.
- Antes de editar: `git status -sb`, branch/HEAD, PR; não sobrescrever trabalhos locais. Patches pequenos, testes direcionados, depois pytest completo e CI da SHA final.
- O GitHub é **público**: nunca versionar CSV real, tokens, sessões Instagram, credenciais, telefone/e-mail de clientes, nem colocar dados pessoais em logs/artefatos.
- **Dados reais não são proibidos no MVP local.** Usar exclusivamente contatos com autorização específica registrada, arquivos fora do repositório, saídas agregadas e revisão humana. Não é necessário repetir o piloto fictício toda vez que o objetivo for um teste real.
- Sugestões por nome/agenda não são correspondência comprovada. Só marcar `confirmed` quando o próprio titular confirmar por mensagem ou interação autorizada.
- Não inventar uma API pública da Meta que converta telefone/e-mail em @. Não contornar bloqueios de plataforma, automatizar scraping não autorizado ou sincronizar a base inteira com APIs privadas.
- Não fazer deploy, merge, push forçado nem alterar o CRM de produção sem aprovação. A PR #1 permanece Draft até revisão.

## Rotas de execução
- **Ambiente e regressão:** `.agents/skills/windows-poc/SKILL.md`
- **Piloto real (local):** `.agents/skills/real-pilot/SKILL.md`
- **Review:** `.agents/skills/review-pr/SKILL.md`
- **Contratos:** `docs/VALIDATION_CONTRACT.md`; **teste real:** `docs/REAL_MVP.md`

`network_calls: 0` é descritivo do app, não uma captura de tráfego.
