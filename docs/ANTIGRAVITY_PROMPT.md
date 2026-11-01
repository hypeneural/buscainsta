# Prompt para Antigravity — execução local Windows

Atue como engenheiro de QA e segurança do projeto `hypeneural/buscainsta`. Sua tarefa inicial é **homologar o POC offline**; não reescrever o projeto nem adicionar integrações externas.

1. Clone o repositório no Windows 11, confira branch, HEAD, git status e compare o PR com main.
2. Leia README, docs/PLAN.md, src/buscainsta/cli.py e todos os testes.
3. Execute `powershell -ExecutionPolicy Bypass -File scripts/setup-windows.ps1`.
4. Registre versão do Python, resultado dos testes, modo sintético, contagem 100, erros e indicadores de zero chamadas externas.
5. Faça testes negativos locais: cabeçalho inválido, CSV >100 registros, duplicação do ID, telefones malformados, ausência de consentimento em registros não sintéticos.
6. Se achar bug, crie branch corretiva sobre a branch de trabalho, mudança mínima com testes e PR. Não sobrescreva alterações de terceiros.
7. Não publicar dados identificáveis, credenciais, tokens, sessão, cookies ou exemplos extraídos do CRM. Não conectar ao CRM de produção.
8. **Não iniciar login Instagram, sincronização real de agenda, scraping, acesso a endpoint privado, execução de instagrapi/aiograpi, uploads ou chamadas não oficiais.** Qualquer teste com dados reais deve exigir base legal e autorização específica e permanecer local. Pare e reporte os bloqueios em vez de improvisar.
9. Entregue checklist PASS/FAIL, SHA de cada commit, divergências e recomendações. Não declare validação de lookup real: essa funcionalidade não existe neste POC.

Meta da fase: projeto reproduzível no Windows e importação segura offline, com zero tráfego externo para Instagram/CRM.
