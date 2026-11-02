# Auditoria instagrapi — dados, mídia, histórico e restrições (2026-11-01)

## Fontes inspecionadas
- https://github.com/subzeroid/instagrapi/blob/master/instagrapi/types.py
- https://github.com/subzeroid/instagrapi/blob/master/instagrapi/mixins/media.py
- https://github.com/subzeroid/instagrapi/blob/master/instagrapi/mixins/comment.py
- https://github.com/subzeroid/instagrapi/blob/master/instagrapi/mixins/story.py
- https://github.com/subzeroid/instagrapi/blob/master/instagrapi/mixins/album.py
- https://github.com/subzeroid/instagrapi/blob/master/instagrapi/mixins/video.py
- https://github.com/subzeroid/instagrapi/blob/master/docs/usage-guide/media.md

## O que o objeto `Media` traz realmente
| Campo | Significado | Regra para Radar |
| --- | --- | --- |
| pk, id, code | Identidade; permalink com shortcode | Dedupe por permalink + mapeamento persistente source/external_id |
| media_type | 1 foto, 2 vídeo, 8 carrossel | Normalizar tipo, nunca duplicar slides como posts |
| product_type | `clips` (Reel), `feed`, `igtv` | Exibir Reel separado de vídeo comum |
| thumbnail_url | Capa JPEG/URL temporária | Guardar referência; não assumir arquivo permanente |
| video_url | URL temporária para MP4 de vídeo | Não tratar como bytes locais; pode expirar |
| resources | `Resource` com `pk, media_type,thumbnail_url,video_url` | Preservar ordem, tipos mistos e posições do álbum |
| taken_at | Data/hora original | UTC no banco; America/Sao_Paulo no painel |
| like_count | Curtidas (pode ser -1 quando oculto) | Normalizar -1/ausente para NULL |
| comment_count | Contagem de comentários | NULL quando não disponível |
| view_count, play_count | Exibições/reproduções de vídeos, quando presentes | NULL significa indisponível, NÃO zero |
| video_duration | Duração em segundos | Para player/totem futuro |
| comments_preview | Comentários embutidos que a resposta já inclui | Importar somente amostra autorizada, até dez na UI |
| shares_count | **Não é um campo de Media** | Não inferir de `viewer_can_reshare`/ `has_shared_to_fb` |
| viewer_can_reshare | Estado de permissão da conta autenticada | Não é total de compartilhamentos |
| insights_media | Métricas da própria conta profissional quando autorizada | Não tratar como insights de qualquer concorrente |

## Importação offline e segura
O módulo `src/buscainsta/radar/instagrapi_normalizer.py` converte **objetos já obtidos com autorização** ou exports JSON Pydantic `model_dump(mode="json")`. Não executa `Client.login`, `user_medias`, `user_stories`, `video_download`, requests privadas ou download de terceiros. O comando `import-instagrapi` salva metadados e referências, não bytes de arquivos.

Uso:
```powershell
.\.venv\Scripts\python.exe -m buscainsta.radar.cli import-instagrapi "C:\BuscaInstaRadar\autorizados.json" --username amizphoto
```

O JSON pode ser um array de modelos `Media` serializados, ou `{"medias":[...]}`. Os timestamps devem ter timezone. Importar no máximo 300 por execução (arquivo de até 10 MB). Os dados originais e sessões ficam fora do GitHub. Para armazenar fotos e vídeos realmente autorizados, use o manifesto local documentado em `RADAR.md`.

## Dados e cache
- **Persistência de metadados:** posts, tipo de mídia, legendas, métricas observadas e horários, com snapshots quando contagens mudam.
- **Persistência binária local:** somente arquivos cuja obtenção e cópia tenham autorização. SHA-256 elimina cópias repetidas e valida hash antes de reutilizar o destino.
- **Integridade:** `python -m buscainsta.radar.cli verify-cache` analisa hashes do arquivo e acusa ausente/corrompido sem apagar nada.
- **Atualização:** `--refresh-meta-on-access` só habilita atualização em background pela Meta Graph oficial e com token configurado. Há lock e janela mínima de 15 minutos (padrão 30). Esse refresh **não faz download**.
- **Stories:** podem expirar; sem captura autorizada prévia, não há garantia de preservação. Não implementar `user_stories` privado de concorrentes automaticamente por padrão.
- **Comentários:** Meta Business Discovery retorna principalmente **contagens**, não o corpo completo dos comentários dos concorrentes. O banco preserva amostras importadas de forma autorizada por fonte que realmente as forneça.
- **Compartilhamentos:** valores só aparecem quando enviados por fonte com autorização e escopo adequados; para concorrentes o valor permanece NULL quando não informado. Não buscar `shares_count` em Business Discovery como se fosse garantido.

## Fragilidades identificadas na biblioteca
- `user_clips_paginated_v1` pode retornar `([], None)` em exceções genéricas; não confundir com perfil sem Reels.
- Endpoints de Stories GraphQL e API móvel mudam sem SLA; nunca marcar 0 Stories como conclusão se houve erro.
- `user_medias(amount=0)` pode buscar histórico inteiro; usar paginação e limites no caso autorizado.
- `video_download_by_url(overwrite=False)` apenas não sobrescreve caminho, **não verifica igualdade do conteúdo**.
- Dados de CDN são transitórios; o arquivo local válido é identificado por hash, e não pela URL.
- Não registrar tokens/IDs sensíveis, não usar proxies/rotação de contas/evasão de desafios. Se a Meta bloquear acesso, registrar erro e interromper.

## Regras de autorização
O fato de uma conta seguir uma terceira conta não confere direitos de backup/reprodução das mídias. O uso de plataformas oficiais também exige observar as políticas da Meta, incluindo limitações para importar ou fazer backup de Conteúdo do Usuário sem permissão. O Radar não ativa o download de mídia de concorrentes automaticamente.

Referência oficial: https://developers.facebook.com/devpolicy/
