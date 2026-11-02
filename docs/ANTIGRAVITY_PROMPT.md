# Antigravity — Fase Dashboard BuscaInsta

Repositório: hypeneural/buscainsta; branch: feat/windows-offline-poc-bootstrap; PR #1 Draft; issue #4.

1. Verifique git status -sb, git log -3 --oneline. Atualize por git fetch origin + git pull --ff-only somente se árvore limpa. Não descartar trabalho local nem force-push.
2. Leia apenas AGENTS.md, docs/DASHBOARD.md, src/buscainsta/dashboard.py, dashboard_store.py, instagram_actions.py e tests/test_dashboard.py. Se matching precisar ser depurado, ler live_sync.py e tests/test_live_sync.py.
3. Rodar .\.venv\Scripts\python.exe -m pytest -q tests/test_dashboard.py tests/test_live_sync.py e depois pytest -q completo. Verificar CI da SHA FINAL em Windows/Ubuntu Python 3.11 e 3.12.
4. No Windows iniciar painel OFFLINE, com CSV privado: .\.venv\Scripts\python.exe -m buscainsta.dashboard --db "C:\BuscaInstaPrivado\buscainsta.db" --contacts "C:\BuscaInstaPrivado\contatos.csv" --account estudio_teste. Abrir http://127.0.0.1:8765/.
5. Validar busca/paginação, editar @, foto ausente, status de seguidores unknown, marcação manual É o cliente e permissão Direct; capturar somente evidência com nomes fictícios.
6. Validar matching com dois clientes de mesmo nome: não pode selecionar arbitrariamente o primeiro. Validar que --limit-search realmente é aplicado e que follow não é invertido.
7. Para consulta real APENAS quando operador autorizar, configurar credenciais da conta de teste via variáveis privadas, ativar --enable-instagram e clicar em Consultar para 1 @ próprio ou voluntário. O Chrome logado não substitui a sessão Python.
8. Para Direct, testar primeiro somente FakeClient: confirmação/opt-in/candidato/consulta, botão individual e horário de tentativa e aceite. NÃO disparar mensagens reais no teste automático. O modo real necessita --enable-dm --enable-instagram e --message-file com texto fixo local, e autorização individual. Mensagem pode cair em solicitações ou falhar; status desconhecido sem retry.
9. Para várias contas, NÃO compartilhar o mesmo DB mudando --account: usar um DB por conta enquanto não existir schema multi-conta.
10. Corrigir somente falhas reproduzidas, novos testes de regressão, reportar SHA, CI, Windows/Python, logs sanitizados e P0/P1/P2. Não anexar PII/cookies/senhas/CSV à PR. Manter Draft e não fazer merge.

Objetivo: painel utilizável com foto e seguidores por perfil, checkbox de conferência manual e botão de mensagem fixa com data/hora verificável, sem envios em massa.