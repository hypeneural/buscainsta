# BuscaInsta — instruções permanentes para agentes

Objetivo da fase: **POC local/offline no Windows 11**, importação, normalização e validação de até 100 contatos de teste. **Nenhuma busca real de Instagram foi implementada.**

## Invariantes
- Não acessar o CRM de produção, não autenticar no Instagram, nem transmitir/sincronizar telefones, nomes e e-mails. Investigar APIs privadas somente pela documentação/código público.
- Nunca salvar, commitar ou expor PII, CSVs reais, cookies, tokens e credenciais; o repositório é **público**. Não colocar exemplos reais em issues, CI e comentários.
- Não inferir identidade de um perfil a partir de sugestões, nomes semelhantes ou metadados de agenda; exigir consentimento e confirmação adequada antes de futura associação ao CRM.
- Trabalhar na branch do PR aberto; consultar `git status`, `git branch --show-current` e `git log -3 --oneline` antes de editar. Não reescrever históricos, fazer force-push, merge, deploy ou alterar outros repositórios.
- Mudanças pequenas e testadas; documentar hipótese, alteração e evidência. Revisar diffs para ausência de dados pessoais e segredos.
- Usar Python >=3.11, stdlib no runtime, pytest somente em desenvolvimento; saída de validação deve permanecer agregada e sem dados de contatos.
- Não afirmar que CI ou testes Windows passaram sem link/resultados verificáveis. Em caso de falha, registrar evidência e bloquear merge.

## Onde encontrar instruções operacionais
- `docs/AGENT_WORKFLOW.md`: sequência de trabalho, gates e entrega.
- `.agents/skills/windows-poc/SKILL.md`: executar homologação Windows e testes.
- `.agents/skills/review-pr/SKILL.md`: auditoria de changes/PR/segurança.
- `docs/PLAN.md`: escopo de dados autorizados.

Regra operacional: **antes de qualquer rede para plataformas de terceiros ou uso de contatos reais, PARAR e obter revisão dos termos, base legal e autorização explícita separada**. Instalar dependências para testes do projeto exige rede ao gerenciador de pacotes, mas não envia contatos.

## Contrato recente dos validadores
- Dados gerados para testes **não podem conter telefones discáveis**, usernames ou credenciais. Usar identificadores `TEST-NNN`, nomes fixos e e-mails em `example.invalid`.
- `validate` requer `--synthetic` OU `--local-consented`. Não usar modo consentido sobre base real sem autorização específica. Mesmo no modo local não há lookup real de Instagram.
- Ver `docs/VALIDATION_CONTRACT.md`; evidência dos 23 testes anteriores não substitui a homologação da SHA atual.
