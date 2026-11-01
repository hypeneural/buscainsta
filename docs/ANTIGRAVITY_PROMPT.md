# Prompt Antigravity — revisão forense e re-homologação pós-hardening

Repositório `hypeneural/buscainsta`, branch `feat/windows-offline-poc-bootstrap`, PR #1 Draft. Houve uma homologação do Windows 11 Pro/Python 3.12.10 no commit `cf84f615` com 23 testes PASS. **Aquela evidência vale para o SHA antigo; não utilizar para declarar o novo SHA homologado.**

## Leitura inicial obrigatória
1. `git status -sb`; `git branch --show-current`; `git log -3 --oneline`; confirmar trabalhos locais sem perder alterações.
2. `git fetch origin`; se a árvore estiver limpa: `git pull --ff-only origin feat/windows-offline-poc-bootstrap`; se suja, parar e relatar antes de qualquer mudança.
3. Ler `AGENTS.md`, `docs/AGENT_WORKFLOW.md`, `docs/VALIDATION_CONTRACT.md`, `docs/PLAN.md`, `.agents/skills/windows-poc/SKILL.md`; revisar `src/buscainsta/cli.py` e todos os testes.

## Correções recentemente aplicadas — validar sem reescrever
- Gerador sintético tem **telefone vazio** e e-mails `testNNN@example.invalid`. Não adicionar números aleatórios que possam pertencer a alguém.
- `validate` exige um dos modos `--synthetic` e `--local-consented`; este último nunca é automático.
- Modo sintético exige ID, nome, e-mail e metadados alinhados ao gerador; rejeita telefone, `@instagram` e datas reais.
- Verificação de DDD, números ASCII, e-mail com domínio plausível e data de consentimento.
- `*.egg-info/` no .gitignore para impedir arquivos de instalação editável como untracked.

## Executar no PowerShell
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-windows.ps1
if ($LASTEXITCODE -ne 0) { throw "setup failed" }
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-windows.ps1 -SkipInstall
if ($LASTEXITCODE -ne 0) { throw "repeat failed" }
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-windows.ps1
if ($LASTEXITCODE -ne 0) { throw "verification failed" }
.\.venv\Scripts\python.exe -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "pytest failed" }
git diff --check
git status -sb
```

## Testes adversariais que precisam passar
1. CSV sintético 100/100 e **todos os telefones vazios**.
2. Injetar telefone com formato válido em um registro sintético: deve falhar.
3. Injetar `@username` em registro sintético: deve falhar.
4. Trocar e-mail por outro domínio reservado ou nome por outro: deve falhar.
5. Validar sem selecionar modo: deve falhar; com `--local-consented` e exemplos fictícios explícitos: deve apenas validar estrutura local.
6. Invalidar DDD, Unicode numérico, e-mail com DNS label inválida, CSV malformado, 101 registros, duplicata e UTF-8 inválido.
7. Confirmar saída sem dados pessoais e sem CSVs, cookies, tokens ou `egg-info` versionados.

## Publicar evidências
- SHA novo, sistema, versões, número real de testes e seu resultado, comandos com exit codes, RUN GitHub Actions da SHA final, `git diff --check` e `git status`.
- Achados P0/P1/P2; correções pequenas com regressões e commits na própria PR se necessário.
- Manter PR **Draft**; não fazer force-push, merge ou tocar na `main`.
- Não acessar CRM, não exportar 100 clientes, não autenticar Instagram, não sincronizar contatos nem tentar endpoints não oficiais.
- Distinguir ausência de integração de uma prova instrumental de zero tráfego.
