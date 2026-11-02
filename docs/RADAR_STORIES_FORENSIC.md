# Auditoria forense — Stories de contas seguidas (02/11/2026)

**Situação:** design/viabilidade, nenhuma automação de visualizações liberada. Repositório `hypeneural/buscainsta`; base PR #5 Draft sobre PR #1.

## Objetivo
No Radar, permitir ao gestor listar Stories ativos de perfis monitorados e outros perfis que a conta dedicada segue, distinguir estado de acesso, abrir no Instagram mediante ação humana, registrar eventos confirmados pelo operador e eventualmente catalogar mídias quando houver fonte e autorização suficientes.

**Duas identidades diferentes:** a conta dedicada de monitoramento e `@estudioevydenciaa` não são intercambiáveis. Quem aparece ao dono do Story é a conta que realmente assistiu na plataforma, jamais uma terceira conta selecionada no painel.

## Código inspecionado diretamente no `subzeroid/instagrapi`, branch master
- `instagrapi/mixins/auth.py:get_reels_tray_feed(reason="pull_to_refresh")`: endpoint privado `feed/reels_tray/`, retorna **dict cru** de bandeja de Stories. O parâmetro page_size é 50; **não é prova de lista exaustiva** nem um provedor oficial. Depende de sessão.
- `instagrapi/mixins/user.py:user_following(user_id, amount=0)` e `user_following_v1_chunk`: lista contas seguidas via `friendships/{user_id}/following/`, com paginação. `amount=0` pode buscar a lista completa; usar limites quando autorizado. `user_friendships_v1(ids)` consulta status com endpoint privado `friendships/show_many/`; `user_friendship_v1` pode capturar `ClientError` e devolver `None`. `None` = **não confirmado**, nunca "não segue".
- `instagrapi/mixins/story.py:users_stories_gql(ids)`: método web não oficial, divide ids em grupos de 50, usa query hash fixo; vulnerável a mudanças. `user_stories(user_id)`: tenta `user_stories_v1` privado se autenticado e faz fallback GQL, ou vice-versa. `user_stories_v1` usa `feed/user/{user_id}/story/`. A falta de resultado não distingue expiração, invisibilidade, conta restrita e erro da fonte.
- `types.py:Story`: `pk,id,code,taken_at,media_type,thumbnail_url,video_url,video_duration,user,mentions,links,stickers,...`. **Não existe `expires_at` nem `viewer_seen` validado no modelo**; prazo de 24 h é apenas estimativa inicial e a plataforma define disponibilidade real.
- `story.py:story_seen(story_pks,skipped_story_pks=[])` delega a `media_seen`. `media.py:media_seen` envia requisição privada `/v2/media/seen/?reel=1&live_vod=0`. A função usa `random.randint(100,3000)` para montar o **intervalo temporal informado no payload**, não para fazer `sleep` nem fornecer rate limit. Retorna bool somente se o endpoint respondeu `status=ok` — isso **não certifica** visualização real/contagem no Instagram.
- `story.py:story_viewers(story_pk)` chama `media/{story_pk}/list_reel_media_viewer/`; é uma lista de visualizadores de mídia do proprietário, não instrumento de confirmação da visibilidade da conta de monitoramento no Story de terceiros. Não consultar listas privadas de terceiros.
- `story.py:story_download` existe, mas não significa autorização para salvar Stories de terceiros.

Referências de código:
https://github.com/subzeroid/instagrapi/blob/master/instagrapi/mixins/auth.py
https://github.com/subzeroid/instagrapi/blob/master/instagrapi/mixins/story.py
https://github.com/subzeroid/instagrapi/blob/master/instagrapi/mixins/media.py
https://github.com/subzeroid/instagrapi/blob/master/instagrapi/mixins/user.py
https://github.com/subzeroid/instagrapi/blob/master/instagrapi/types.py

## Matriz de viabilidade

| Função | Biblioteca | Suporte oficial / observação | Decisão |
|---|---|---|---|
| Mostrar os oito perfis concorrentes | Radar já cadastra | Sem API de Stories | Implementável sem automação |
| Comprovar que segue determinado perfil | `user_friendships_v1` ou `user_following` privado | Não é endpoint autorizado de terceiros na API oficial | Requer autorização/alternativa de export; estado `unknown` por padrão |
| Ver Stories ativos dos seguidos | `get_reels_tray_feed` ou `user_stories` | API privada não oficial; não disponível via Business Discovery | Tecnicamente existe; NÃO colocar em produção como bot |
| Registrar "seen" | `story_seen` -> `media_seen` | Endpoint privado; status ok não prova que dono contou a visualização | Não automatizar |
| Garantir aparecer na lista do dono | Nenhum | Só Instagram e dono do Story podem comprovar | Impossível garantir |
| Selecionar aleatoriamente seguidos para análise | Lista já autorizada/importada | UI local sem ações na conta | Viável como sugestão manual |
| Armazenar Stories de terceiros | `story_download` não oficial | Sujeito a direitos e autorização; Stories efêmeros | Não fazer download padrão |
| Definir aleatoriedade que evite bloqueio | `media_seen` fabrica duração textual no payload | Não limita volume nem concede permissão | Não existe proteção comprovada |

Documentação Meta oficial: https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api
Políticas: https://www.facebook.com/legal/automated_data_collection_terms e https://developers.facebook.com/devpolicy/

## Modelo de dados proposto, isolado do CRM
`radar_following`: `monitor_account_id`, `target_user_id`, `username`, `following_state` enum `confirmed/unknown/not_following`, `confirmation_source`, `confirmed_at`.

`story_catalog`: chave `(monitor_account_id,owner_id,story_pk)`; `taken_at`, `expected_expiry_at` (estimativa, nunca garantia), `last_seen_at`, `source`, `availability` enum `active/expired/restricted/unknown/error`, `preview_authorized`, `provenance`. Não registrar `expired` apenas por falha de consulta.

`story_review_actions`: `story_pk`, `operator_action` enum `opened_in_instagram/marked_watched/skip`, `actor_account_id`, `timestamp`, `confirmation_origin` enum `operator/instagram_verification`, `verification_status` enum `unverified/confirmed`. Abrir link pelo painel não confirma `watched`.

`story_check_runs`: `provider`, `started_at`, `finished_at`, `attempted`, `visible`, `status`, `error_type`, `next_allowed_at`; nunca persistir senhas/tokens ou corpos completos de respostas.

## Tela planejada: "Stories para revisar"
- Cards por perfil com avatar autorizado, último Story conhecido, horário, disponibilidade estimada e link **Abrir no Instagram**; o Instagram fará a reprodução ao usuário.
- Abas: `Concorrentes`, `Outros que seguimos`, `Revisados hoje`, `Indisponíveis`.
- Filtros: `Stories detectados`, `ainda não revisados`, `prioridade`, `última data`, `categoria` e conta de monitoramento.
- Botão `Sugerir outros perfis` apenas sorteia uma amostra de contas efetivamente presentes numa lista validada/importada e ainda não revisadas; **não dispara visualizações**.
- Estados sem ambiguidade: `Story disponível` somente quando verificado recentemente em fonte autorizada, `pode ter expirado`, `não foi possível consultar`, `visto manualmente` e `visualização confirmada pelo proprietário` somente com evidência independente.
- Não misturar marcação local `visto` com confirmação de que o Instagram contabilizou a visualização.

## Tráfego, bloqueios e riscos
Não há limite diário de visualizações nem distribuição de atrasos publicada pela Meta que garanta "não bloquear". `random.randint(100,3000)` no código é informação temporal do evento, **não** um algoritmo de pacing.

Usar somente APIs autorizadas para leitura. Se houver polling permitido: cache, deduplicação, limite de consultas, fila única, `Retry-After` quando fornecido, backoff em 429/5xx, suspensão imediata em checkpoint/login/challenge e logs sem PII. **Nunca** usar jitter, proxies, contas de rotação ou marcação automática de `seen` para disfarçar engajamento artificial.

## Gatilhos mínimos para homologação
1. Conta dedicada identificada, visibilidade real dos oito perfis confirmada manualmente.
2. Comprovação do acesso aos Stories pelo app oficial em dois perfis escolhidos.
3. Verificar se export autorizado/lista manual de seguidos contém IDs suficientes; nenhum `unknown` convertido em `confirmed` por inferência.
4. Diferenciar `nenhum Story` de `consulta falhou` e `acesso negado`.
5. Status de visualização local: teste `abrir link` não vira visualização confirmada.
6. Regressão de migrações, deduplicação por story_pk e separação da conta do estúdio.
7. Auditoria de políticas e permissões antes de qualquer coleta automatizada ou arquivamento.
