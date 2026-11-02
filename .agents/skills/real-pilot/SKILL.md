---
name: real-pilot
description: Executa MVP real BuscaInsta no Windows com até 100 contatos autorizados, registro local de candidatos encontrados na pesquisa/sugestões nativas do Instagram, confirmação humana e métricas agregadas. Use quando o operador pedir teste real.
---

# Real pilot — evitar loops de homologação

**Objetivo:** produzir evidência sobre o número de contatos revisados, candidatos e correspondências confirmadas, sem declarar que a API do Instagram faz reverse lookup.

## Decisão rápida
- Ambiente novo? Use primeiro `/windows-poc` **uma vez**.
- Já há Windows homologado e branch atual? Execute somente pytest focal `tests/test_pilot.py`, depois prepare e summarize; CI e teste completo apenas após editar código.
- Quer testar telefone/e-mail -> @? Use pequeno grupo com @ conhecido pelos voluntários, observe sugestões no aplicativo oficial e registre `candidate`. Confirme os perfis diretamente com o cliente antes de marcar `confirmed`. O app não identifica precisamente qual telefone gerou cada sugestão.
- Quer testar a API de sincronização realmente? Audite `live_probe.py` e testes mockados; com conta de teste própria, autorização expressa para compartilhar um contato e revisão de termos, o operador pode executar o probe opcional. Jamais disparar sem confirmação humana, nem escalar para toda a base. Retornos são sugestões, não identidades comprovadas.

## Comandos
- Ver `python -m buscainsta.pilot --help`.
- Validar CSV consentido: `python -m buscainsta.cli validate --input <csv> --local-consented`.
- Preparar: `python -m buscainsta.pilot prepare --input <csv> --output <arquivo-privado-fora-do-repo>`.
- Registrar observações **editando localmente o arquivo de revisão**.
- Sumarizar: `python -m buscainsta.pilot summarize --input <arquivo-privado>`.

NUNCA mostrar o CSV real no chat, GitHub, logs ou exemplos. O output é agregado, não envia contatos.
Antes do piloto, leia apenas `docs/REAL_MVP.md` e `src/buscainsta/pilot.py` (se precisar depurar). Não rodar repetidamente setup/pip sem necessidade.

## Painel local
Para ações de foto/follow/Direct, consultar docs/DASHBOARD.md e executar pytest focal tests/test_dashboard.py tests/test_live_sync.py. Habilitar --enable-instagram só em testes individuais autorizados; --enable-dm apenas para envio individual aprovado, com mensagem fixa e prévia. Teste automático sempre mockado. Não usar UI para disparos em massa.
