# BuscaInsta — regras permanentes (Antigravity, 2026)

Projeto: MVP Windows 11 para **avaliar** se contatos autorizados podem ser associados com segurança a perfis Instagram. Não confundir validade do CSV, conta sugerida e vínculo confirmado.

## Regras sempre ativas
- Leia somente os arquivos necessários à tarefa. Use os skills `windows-poc`, `real-pilot` ou `review-pr`; evite reler documentação inteira a cada turno.
- Antes de editar: `git status -sb`, branch/HEAD, PR; não sobrescrever trabalhos locais. Patches pequenos, testes direcionados, depois pytest completo e CI da SHA final.
- O GitHub é **público**: nunca versionar CSV real, tokens, sessões Instagram, credenciais, telefone/e-mail de clientes, nem colocar dados pessoais em logs/artefatos.
- **Dados reais não são proibidos no MVP local.** Usar exclusivamente contatos com autorização específica registrada, arquivos fora do repositório, saídas agregadas e revisão humana. Não é necessário repetir o piloto fictício toda vez que o objetivo for um teste real.
- Sugestões por nome/agenda não são correspondência comprovada. Só marcar `confirmed` quando o próprio titular confirmar por mensagem ou interação autorizada.
- Não inventar uma API pública da Meta que converta telefone/e-mail em @. O probe opcional `live_probe.py` só roda um voluntário com consentimento específico e confirmação explícita; pode violar termos da Meta, então requer avaliação/autorização da plataforma. Não automatizar scraping, contornar bloqueios nem sincronizar a base inteira.
- Não fazer deploy, merge, push forçado nem alterar o CRM de produção sem aprovação. A PR #1 permanece Draft até revisão.

## Rotas de execução
- **Ambiente e regressão:** `.agents/skills/windows-poc/SKILL.md`
- **Piloto real (local):** `.agents/skills/real-pilot/SKILL.md`
- **Review:** `.agents/skills/review-pr/SKILL.md`
- **Contratos:** `docs/VALIDATION_CONTRACT.md`; **teste real:** `docs/REAL_MVP.md`

`network_calls: 0` é descritivo do app, não uma captura de tráfego.

## Painel (01/11/2026)
- Para UI/foto/follow/Direct, ler somente docs/DASHBOARD.md e testes/test_dashboard.py.
- SQLite/fotos somente em pasta privada fora do Git.
- Nos segue/seguimos são estados independentes por conta autenticada; unknown não é no.
- Confirmar cliente é decisão manual do operador. Direct só após permissão e clique humano; nenhuma automação de envio em massa.
- Status aceito API não implica entregue/lido; resultado desconhecido impede reenvio automático.
- Usar DB separado para cada conta Instagram até modelagem multi-conta.

## Importação do painel legado (regra adicional)
- `C:\BuscaInstaPrivado\painel_conferencia.html` é a fonte HTML legada de 2.739 linhas, não uma nova aplicação a recriar. Nunca sobrescrever esse HTML.
- Importação em `legacy_import.py` por telefone normalizado; o ID CRM NÃO é único na versão examinada. Não realizar merge por ID do CRM.
- A nova UI deve manter score VIP, indicadores, filtros, ensaios e situação 2026, além dos novos botões.
- Sem registros reais ou scripts geradores com JSON embutido no GitHub. Somente fixtures sintéticas.
