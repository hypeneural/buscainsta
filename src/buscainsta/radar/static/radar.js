"use strict";
// Read data only from loopback API. Never load remote Instagram CDN resources.
const $ = (id) => document.getElementById(id);
const TIMEZONE = "America/Sao_Paulo";
let csrf = "";
let view = "overview";
let profiles = [];
let posts = [];
let offset = 0;
let total = 0;
let hasMore = false;
let loading = false;
let requestGeneration = 0;
let filterTimer;
let viewerSlides = [];
let viewerPost = null;
let currentSlide = 0;
const observer = typeof ResizeObserver !== "undefined"
  ? new ResizeObserver((entries) => {
      for (const entry of entries) {
        const tile = entry.target.parentElement;
        if (!tile || !tile.classList.contains("tile")) continue;
        const height = entry.target.getBoundingClientRect().height;
        const span = Math.max(1, Math.ceil((height + 12) / 20));
        if (tile.dataset.span !== String(span)) {
          tile.dataset.span = String(span);
          tile.style.gridRowEnd = "span " + span;
        }
      }
    })
  : null;

function el(tag, className = "", text) {
  const result = document.createElement(tag);
  if (className) result.className = className;
  if (text !== undefined) result.textContent = String(text);
  return result;
}
function button(text, callback, className = "secondary") {
  const result = el("button", className, text);
  result.type = "button";
  result.addEventListener("click", callback);
  return result;
}
function formatDate(value) {
  if (!value) return "—";
  const time = new Date(value);
  return Number.isNaN(time.getTime()) ? "—" : new Intl.DateTimeFormat("pt-BR", {
    timeZone: TIMEZONE, dateStyle: "medium", timeStyle: "short",
  }).format(time);
}
function dayKey(value) {
  const time = new Date(value);
  return Number.isNaN(time.getTime()) ? "Data desconhecida" : new Intl.DateTimeFormat("pt-BR", {
    timeZone: TIMEZONE, weekday: "long", year: "numeric", month: "long", day: "numeric",
  }).format(time);
}
function timeOnly(value) {
  const time = new Date(value);
  return Number.isNaN(time.getTime()) ? "—" : new Intl.DateTimeFormat("pt-BR", {
    timeZone: TIMEZONE, hour: "2-digit", minute: "2-digit",
  }).format(time);
}
function size(n) {
  if (!n) return "0 MB";
  return n < 1024 * 1024 ? (n / 1024).toFixed(0) + " KB" : (n / (1024 * 1024)).toFixed(1) + " MB";
}
function kindLabel(kind) {
  return ({ image: "Foto", video: "Vídeo / Reel", carousel: "Carrossel", story: "Story" })[kind] || "Mídia";
}
async function getJSON(path, signal) {
  const response = await fetch(path, { cache: "no-store", signal });
  if (!response.ok) throw new Error("O acervo local respondeu com erro " + response.status);
  return response.json();
}
async function postJSON(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Radar-CSRF": csrf },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Não foi possível concluir a operação");
  return data;
}
function setText(id, value) { $(id).textContent = String(value); }

async function refreshOverview() {
  const [stats, list] = await Promise.all([getJSON("/api/stats"), getJSON("/api/competitors")]);
  profiles = list;
  setText("kpi-profiles", stats.active_competitors);
  setText("kpi-posts", stats.posts);
  setText("kpi-archived", stats.archived_posts);
  setText("kpi-size", size(stats.bytes_stored));
  let message = "Acervo local · sem consulta automática ao Instagram";
  if (stats.last_run) {
    const run = stats.last_run;
    const sourceName = run.provider === "meta_business_discovery" ? "consulta oficial Meta" : "importação local";
    message += " · Última " + sourceName + ": " + formatDate(run.finished_at);
    message += run.status === "completed" ? " · concluída" : " · houve falha";
  } else {
    message += " · nenhum manifesto importado";
  }
  setText("health", message);
  renderProfiles();
  renderProfileSelect();
  renderProfileOverview();
}
function renderProfileSelect() {
  const selected = $("profile-filter").value;
  const selector = $("profile-filter");
  selector.replaceChildren(el("option", "", "Todos os perfis"));
  selector.firstElementChild.value = "";
  for (const profile of profiles) {
    const option = el("option", "", "@" + profile.username);
    option.value = profile.username;
    selector.append(option);
  }
  if (profiles.some((p) => p.username === selected)) selector.value = selected;
}
function renderProfiles() {
  const host = $("profiles");
  host.replaceChildren();
  if (!profiles.length) {
    host.append(el("p", "muted", "Nenhum perfil cadastrado. Adicione o primeiro concorrente acima."));
    return;
  }
  for (const profile of profiles) {
    const card = el("div", "profile" + (profile.enabled ? "" : " inactive"));
    const top = el("div", "top");
    top.append(el("strong", "", "@" + profile.username),
      el("small", "", profile.enabled ? "Ativo" : "Pausado"));
    card.append(top);
    if (profile.profile_name) card.append(el("small", "", profile.profile_name));
    card.append(el("small", "", profile.post_count + " publicações · " + profile.archived_count + " com arquivo"));
    if (profile.updated_at) card.append(el("small", "", "Última consulta: " + formatDate(profile.updated_at)));
    const actions = el("div", "actions");
    actions.append(button("Ver publicações", () => {
      $("profile-filter").value = profile.username;
      switchView("mural");
    }));
    const toggle = button(profile.enabled ? "Pausar" : "Ativar", async () => {
      toggle.disabled = true;
      try {
        await postJSON("/api/competitors/status", { username: profile.username, enabled: !Boolean(profile.enabled) });
        await refreshOverview();
        setText("form-status", "Perfil atualizado. Os arquivos permanecem preservados.");
      } catch (error) {
        setText("form-status", error.message);
      } finally { toggle.disabled = false; }
    });
    actions.append(toggle);
    card.append(actions);
    host.append(card);
  }
}
function renderProfileOverview() {
  const host = $("overview-profiles");
  host.replaceChildren();
  if (!profiles.length) {
    host.append(el("div", "empty", "Cadastre os perfis que deseja acompanhar."));
    return;
  }
  for (const profile of profiles) {
    const card = el("div", "summary-profile");
    card.append(el("strong", "", "@" + profile.username),
      el("span", "", profile.post_count + " publicações · " + profile.archived_count + " arquivadas"),
      el("span", "", "Post mais recente: " + formatDate(profile.latest_post_at)));
    host.append(card);
  }
}
function switchView(next) {
  view = next;
  for (const tab of document.querySelectorAll("[data-view]")) {
    tab.setAttribute("aria-selected", String(tab.dataset.view === next));
  }
  for (const name of ["overview", "mural", "timeline"]) {
    $("panel-" + name).hidden = name !== next;
  }
  $("filters-panel").hidden = next === "overview";
  $("sort").disabled = next === "timeline";
  $("more-wrap").hidden = next === "overview";
  if (next === "overview") {
    requestGeneration++;
    refreshOverview().catch(() => setText("health", "Não foi possível atualizar o acervo."));
    return;
  }
  loadPosts(true);
}
function currentFilters() {
  const params = new URLSearchParams({
    limit: "40", offset: String(offset),
    sort: view === "timeline" ? "recent" : $("sort").value,
    archived: $("archived").value,
  });
  for (const [control, key] of [
    ["profile-filter", "username"], ["kind", "kind"], ["search", "search"],
    ["from", "from"], ["to", "to"]]) {
    if ($(control).value.trim()) params.set(key, $(control).value.trim());
  }
  return params;
}
async function loadPosts(reset) {
  if (reset) {
    requestGeneration++;
    offset = 0; posts = []; total = 0; hasMore = false;
    $("mural").replaceChildren(); $("timeline").replaceChildren();
    $("more-wrap").hidden = true;
  }
  if (loading && !reset) return;
  if ($("from").value && $("to").value && $("from").value > $("to").value) {
    return setText("results-status", "Data inicial deve ser anterior à data final.");
  }
  const generation = requestGeneration;
  loading = true;
  $("more").disabled = true;
  setText("results-status", "Consultando publicações arquivadas…");
  try {
    const data = await getJSON("/api/posts?" + currentFilters());
    if (generation !== requestGeneration) return;
    posts.push(...data.items);
    offset += data.items.length;
    total = data.total;
    hasMore = data.has_more;
    if (view === "mural") renderMural();
    else if (view === "timeline") renderTimeline();
    setText("count-mural", posts.length + " de " + total + " publicações");
    setText("count-timeline", posts.length + " de " + total + " publicações");
    setText("results-status", total
      ? "Exibindo publicações em ordem cronológica do horário original. Arquivos remotos não são carregados."
      : "Nenhuma publicação encontrada. Ajuste os filtros ou importe um manifesto autorizado.");
    $("more-wrap").hidden = !hasMore;
  } catch (error) {
    if (generation === requestGeneration) setText("results-status", error.message);
  } finally {
    loading = false;
    $("more").disabled = false;
  }
}
function makePreview(post) {
  const preview = el("div", "preview");
  const image = post.assets.find((asset) => asset.local_url && asset.kind === "image");
  const video = post.assets.find((asset) => asset.local_url && asset.kind === "video");
  if (image) {
    const element = el("img");
    element.src = image.local_url;
    element.alt = "Imagem arquivada de @" + post.username;
    element.loading = "lazy";
    element.decoding = "async";
    preview.append(element);
  } else if (video) preview.append(el("div", "placeholder", "▶ Vídeo arquivado · abrir para reproduzir"));
  else preview.append(el("div", "placeholder", "Sem arquivo local · abrir publicação original"));
  preview.append(el("span", "kind-label", kindLabel(post.kind)
    + (post.kind === "carousel" ? " · " + post.assets.length + " itens" : "")));
  return preview;
}
function makeTile(post) {
  const tile = el("article", "tile");
  const inner = el("div", "tile-inner");
  inner.append(makePreview(post));
  const content = el("div", "tile-content");
  const meta = el("div", "meta");
  meta.append(el("strong", "", "@" + post.username), el("small", "", formatDate(post.posted_at)));
  content.append(meta);
  if (post.caption) content.append(el("div", "caption", post.caption));
  const likes = post.likes == null ? "—" : Number(post.likes).toLocaleString("pt-BR");
  const comments = post.comments == null ? "—" : Number(post.comments).toLocaleString("pt-BR");
  const metrics = el("div", "metrics");
  metrics.append(el("span", "", "♥ " + likes), el("span", "", "Comentários " + comments),
    el("span", "", post.locally_archived ? "✓ Salvo localmente" : "Não arquivado"));
  content.append(metrics);
  const actions = el("div", "tile-actions");
  const hasLocal = post.assets.some((x) => x.local_url);
  const open = button("Visualizar mídias", () => openViewer(post));
  open.disabled = !hasLocal;
  actions.append(open);
  if (post.permalink && /^https:\/\/(?:www\.)?instagram\.com\//.test(post.permalink)) {
    const link = el("a", "", "Ver no Instagram");
    link.href = post.permalink; link.target = "_blank"; link.rel = "noopener noreferrer";
    actions.append(link);
  }
  content.append(actions);
  inner.append(content);
  tile.append(inner);
  if (observer && view === "mural") observer.observe(inner);
  else tile.style.gridRowEnd = "auto";
  return tile;
}
function renderMural() {
  const host = $("mural");
  observer?.disconnect();
  host.replaceChildren();
  for (const post of posts) host.append(makeTile(post));
  if (!posts.length) host.append(el("div", "empty", "Ainda não há publicações para estes filtros."));
}
function renderTimeline() {
  observer?.disconnect();
  const host = $("timeline");
  host.replaceChildren();
  let previousDay = "", section = null;
  for (const post of posts) {
    const day = dayKey(post.posted_at);
    if (day !== previousDay) {
      previousDay = day;
      section = el("section", "day");
      section.append(el("h3", "", day));
      host.append(section);
    }
    const entry = el("div", "timeline-entry");
    entry.append(el("div", "time", timeOnly(post.posted_at)), makeTile(post));
    section.append(entry);
  }
  if (!posts.length) host.append(el("div", "empty", "Nenhuma publicação neste intervalo."));
}
function openViewer(post) {
  viewerPost = post;
  viewerSlides = post.assets.filter((asset) => asset.local_url);
  currentSlide = 0;
  setText("viewer-title", "@" + post.username + " · " + kindLabel(post.kind));
  setText("viewer-caption", post.caption || "Sem legenda registrada");
  renderSlide();
  $("viewer").showModal();
}
function renderSlide() {
  const holder = $("viewer-media");
  holder.replaceChildren();
  if (!viewerSlides.length) return holder.append(el("p", "muted", "Nenhum arquivo local disponível."));
  const asset = viewerSlides[currentSlide];
  const media = el(asset.kind === "video" ? "video" : "img");
  media.src = asset.local_url;
  if (asset.kind === "video") {
    media.controls = true; media.preload = "metadata"; media.playsInline = true;
  } else {
    media.alt = "Imagem " + (currentSlide + 1) + " da publicação";
  }
  holder.append(media);
  setText("viewer-counter", (currentSlide + 1) + " / " + viewerSlides.length);
  $("viewer-prev").disabled = viewerSlides.length <= 1;
  $("viewer-next").disabled = viewerSlides.length <= 1;
}
function moveSlide(step) {
  if (!viewerSlides.length) return;
  currentSlide = (currentSlide + step + viewerSlides.length) % viewerSlides.length;
  renderSlide();
}
function scheduleFilter() {
  clearTimeout(filterTimer);
  filterTimer = setTimeout(() => { if (view !== "overview") loadPosts(true); }, 260);
}
async function initialize() {
  for (const tab of document.querySelectorAll("[data-view]"))
    tab.addEventListener("click", () => switchView(tab.dataset.view));
  for (const id of ["profile-filter", "kind", "archived", "from", "to", "sort"])
    $(id).addEventListener("change", scheduleFilter);
  $("search").addEventListener("input", scheduleFilter);
  $("reload-acervo").addEventListener("click", async () => {
    await refreshOverview().catch(() => setText("health", "Não foi possível recarregar o acervo local."));
    await loadPosts(true);
  });
  $("clear-filters").addEventListener("click", () => {
    for (const id of ["profile-filter", "kind", "search", "from", "to"]) $(id).value = "";
    $("archived").value = "all"; $("sort").value = "recent"; loadPosts(true);
  });
  $("more").addEventListener("click", () => loadPosts(false));
  $("viewer-close").addEventListener("click", () => $("viewer").close());
  $("viewer-prev").addEventListener("click", () => moveSlide(-1));
  $("viewer-next").addEventListener("click", () => moveSlide(1));
  $("viewer").addEventListener("close", () => {
    $("viewer-media").replaceChildren(); viewerSlides = []; viewerPost = null;
  });
  $("starter-profiles").addEventListener("click", async () => {
    const starter = ["lizicastagnerafotografias","amizphoto","daianahenckesfotografa","updream_fotografias","carolinigirotofotografia","solarisestudiofotografico","brunacarlafoto","elizandramartins.fotografia"];
    const control = $("starter-profiles");
    control.disabled = true;
    try {
      const result = await postJSON("/api/competitors/bulk", { usernames: starter });
      await refreshOverview();
      setText("form-status", result.saved + " perfis conferidos · " + result.created + " novos · " + result.existing + " já existentes.");
    } catch (error) { setText("form-status", error.message); }
    finally { control.disabled = false; }
  });
  $("batch-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const values = $("batch-input").value.split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
    if (!values.length) return setText("form-status", "Informe ao menos um perfil.");
    const submit = $("batch-form").querySelector("[type=submit]");
    submit.disabled = true;
    try {
      const result = await postJSON("/api/competitors/bulk", { usernames: values });
      $("batch-input").value = "";
      await refreshOverview();
      setText("form-status", result.saved + " perfis conferidos · " + result.created + " novos · " + result.existing + " já cadastrados.");
    } catch (error) { setText("form-status", error.message); }
    finally { submit.disabled = false; }
  });
  $("add-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = $("add-form").querySelector("[type=submit]");
    submit.disabled = true;
    setText("form-status", "Salvando concorrente…");
    try {
      const result = await postJSON("/api/competitors",
        { username: $("new-profile").value, name: $("new-name").value });
      $("new-profile").value = ""; $("new-name").value = "";
      await refreshOverview();
      setText("form-status", "@" + result.username + " cadastrado. Os dados aparecerão após importação autorizada.");
    } catch (error) {
      setText("form-status", error.message);
    } finally { submit.disabled = false; }
  });
  try {
    const config = await getJSON("/api/config");
    csrf = config.csrf;
    await refreshOverview();
  } catch (error) {
    setText("health", "Falha ao carregar banco local: " + error.message);
  }
}
initialize();
