---
name: review-pr
description: Auditar alterações e pull requests do BuscaInsta, conferir CI, contratos de CSV, privacidade, segurança e regressões antes de aceitar um merge.
---

# Revisão de PR e auditoria de segurança

1. Confirmar SHA da `main`, HEAD da feature, lista de arquivos e issues abertas antes de qualquer alteração.
2. Verificar impacto de cada diff em privacidade, determinismo, idempotência, limites de 100 registros e logs agregados.
3. Rodar `python -m pytest -q`; executar `scripts/setup-windows.ps1` duas vezes no Windows; examinar logs GitHub Actions sem segredos.
4. Conferir `.gitignore` e `git ls-files`: nunca deixar dados reais, CSVs, bancos, tokens ou logs pessoais no repositório público.
5. Registrar observações como P0/P1/P2 com arquivo, reprodução, impacto e sugestão de patch mínimo. Não refatorar módulos sem necessidade.
6. Atualizar PR apenas com resultados comprovados; não marcar pronto nem fazer merge sem gates humanos.

**GO** apenas para fase offline após testes em ambiente real, CI verde e revisão de segurança. **NO-GO** para sincronização privada de agenda, scraping de terceiros, adivinhação de perfis, coleta sem autorização e mudanças no CRM real.
