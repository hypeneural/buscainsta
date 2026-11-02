# Antigravity — unificação do painel BuscaInsta (Windows 11)

Trabalhe na branch `feat/windows-offline-poc-bootstrap`, PR #1 Draft, issue #4. O usuário **já tinha** o painel `C:\BuscaInstaPrivado\painel_conferencia.html`; não crie outra ferramenta sem migrar os dados e a UX.

## Contexto confirmado
- O HTML original contém 2.739 contatos, 289 perfis **candidatos**, score VIP, ranking P0-P4, filtros e paginação.
- A fonte contém 562 repetições de ID CRM entre as linhas. Telefones são distintos; **nunca deduplicar por ID CRM apenas**.
- O repositório agora inclui `legacy_import.py`, `dashboard_store.py`, `dashboard.py` e `static/dashboard.html`.
- O novo dashboard opera em `http://127.0.0.1:8765/` com SQLite privado, preservando o HTML antigo.

## Plano cirúrgico
1. Inspecionar `git status -sb`, branch e SHA. Preservar alterações locais. Atualizar com `git fetch` e `git pull --ff-only` somente se limpo.
2. Ler apenas `AGENTS.md`, `docs/DASHBOARD.md`, `src/buscainsta/legacy_import.py`, `dashboard_store.py`, `dashboard.py`, `static/dashboard.html`, `tests/test_legacy_import.py` e `tests/test_dashboard.py`. Não colar dados do HTML ou segredos no chat.
3. Executar testes focalizados:
   ` .\.venv\Scripts\python.exe -m pytest -q tests/test_legacy_import.py tests/test_dashboard.py tests/test_live_sync.py `
   e depois a suíte completa. Verificar CI 4/4 da SHA final.
4. **Não sobrescrever `painel_conferencia.html`.** Se houver aplicação antiga aberta, encerrá-la antes. Iniciar:
   `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-dashboard-windows.ps1 -Db "C:\BuscaInstaPrivado\buscainsta.db" -LegacyPanel "C:\BuscaInstaPrivado\painel_conferencia.html" -Account "estudio_teste"`.
5. Abrir `http://127.0.0.1:8765/` e verificar: 2.739 linhas esperadas, 289 candidatos, P0 232, P1 56, P2 654, ranking, pesquisa, paginação e estatísticas. Conferir que rodar duas vezes não gera duplicatas e preserva os checks.
6. Testar apenas dados fictícios em capturas de tela: botão Editar @, É o cliente, Permissão Direct, filtros, status desconhecido, histórico de tentativa e aceite. O botão de foto/seguidores consulta o Instagram somente com `--enable-instagram`.
7. Auditoria de produção: verificar `--account` versus conta efetivamente autenticada. Para as quatro contas comerciais, usar um DB privado separado por conta até migração de schema multi-conta.
8. Direct real: somente para cliente autorizado e elegível, após clique individual e prévia, com `--enable-dm --message-file`. **Nunca testar com envio real sem aprovação**. Testes automatizados usam `FakeClient`, sem contatos externos. Horário `accepted_at` não significa lido/entregue.
9. Se falhar, reproduzir, corrigir pontualmente, adicionar teste e publicar nova SHA na PR Draft. Relatar caminhos, commits, regressões, evidências P0/P1/P2, sem PII.

## Resultado esperado
Um só painel operacional de gestor, com todos os dados e filtros legados, foto/seguir/seguindo, conferência manual e botão Direct com mensagem fixa e timestamp. O HTML antigo permanece intacto e privado. Nada é salvo no GitHub além de código e testes sintéticos.
