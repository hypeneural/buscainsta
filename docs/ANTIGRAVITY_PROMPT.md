# Prompt operacional — Antigravity /real-pilot (31/10/2026)

Repositório `hypeneural/buscainsta`, branch `feat/windows-offline-poc-bootstrap`, PR #1 em Draft.

**Contexto:** O Windows 11 físico já homologou SHA `76345c6`, pytest 57 PASS e 100/100 sintéticos. **Não refazer a mesma fase sem motivo**. Agora preciso avançar para uma MVP REAL, inicialmente manual e auditável, com até 100 contatos especificamente autorizados.

1. Confirme `git status -sb`, branch e HEAD. Se houver mudanças locais, preserve-as. `git fetch origin` e somente com árvore limpa use `git pull --ff-only`.
2. Leia `AGENTS.md` e ative `/real-pilot`; leia `docs/REAL_MVP.md` e `src/buscainsta/pilot.py`, **não** toda documentação histórica. Aplique o princípio de progressive disclosure e não crie workflows legados.
3. Rode `.\.venv\Scripts\python.exe -m pytest -q tests/test_pilot.py`, depois a suíte completa. Confirme o CI na SHA atual; corrija erros pequenos na branch com regressão, sem alterações em CRM produção.
4. Preparar piloto local real: a fonte de dados do CRM deve ser mapeada **somente no Windows**, em pasta privada fora do GitHub; confirmar autorização específica por contato. O modelo é `contact_id,full_name,phone,email,instagram,consent,consent_date,consent_source`.
5. Use `python -m buscainsta.pilot prepare` para gerar a planilha de revisão privada. Teste pesquisa nominal, sugestões nativas do Instagram (somente com autorização de compartilhar contatos) e respostas voluntárias dos clientes; registre candidatos separadamente de confirmados.
6. Use `python -m buscainsta.pilot summarize` para métricas sem dados pessoais. Teste primeiro voluntários com @ conhecido para aferir precisão. Não alegue que sugestões por contato identificam uma pessoa inequivocamente.
7. Investigue as funções `address_book_link` e `address_book_unlink` do `instagrapi` **como referência**, listando dependências, retornos, incertezas e termos de plataforma. Não fazer login nem upload via API privada no piloto padrão. Se houver um método oficial adequado, proponha em PR separado e com autorização.
8. Entregue relatório: SHA, Python/Windows, testes, total de registros autorizados, quantos revisados, candidatos e confirmados, falso positivo conhecido, bloqueios, próximos ajustes; não inclua nomes, emails, números, usernames, screenshots de clientes ou CSVs no GitHub.
9. Deixe PR em Draft; não refatore o CLI homologado sem falha reproduzível, não force-push, não faça merge automático.

**Objetivo de saída:** prova operacional com contatos reais autorizados e resultado de revisão, não mais uma re-homologação sintética. **Limitação:** o projeto ainda não tem API que devolva @ diretamente de telefone/e-mail.
