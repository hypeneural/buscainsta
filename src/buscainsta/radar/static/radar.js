// Local-only UI; never connects to Instagram, remote CDN or credentials.
const $ = id => document.getElementById(id);
let offset=0, slides=[], index=0;
function element(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=String(text);return e;}
function mediaUrl(a){return a.local_url||null;}
function showSlide(){
  const host=$('viewer-content');host.replaceChildren();
  if(!slides.length){host.textContent='Nenhum arquivo salvo localmente';return;}
  const a=slides[index],src=mediaUrl(a);
  if(!src){host.textContent='Arquivo não disponível no acervo';return;}
  const e=element(a.kind==='video'?'video':'img');
  e.src=src;if(a.kind==='video'){e.controls=true;e.autoplay=false;}
  host.append(e);$('counter').textContent=(index+1)+' / '+slides.length;
}
function openViewer(post){slides=post.assets.filter(a=>a.local_url);index=0;showSlide();$('viewer').showModal();}
function card(p){
  const a=element('article'), preview=p.assets.find(x=>x.local_url);
  if(preview){const media=element('img');media.src=preview.kind==='image'?preview.local_url:'';media.alt='Mídia do perfil '+p.username;media.loading='lazy';
    if(preview.kind==='video'){const label=element('div','', '▶ Vídeo arquivado');a.append(label);}else a.append(media);
  }else a.append(element('div','', 'Sem prévia local'));
  const info=element('div','info');info.append(element('strong','', '@'+p.username),element('div','',p.kind+' · '+new Date(p.posted_at).toLocaleString('pt-BR')));info.append(element('p','',p.caption.slice(0,240)));
  info.append(element('small','', '♥ '+(p.likes??'—')+' · Comentários '+(p.comments??'—')));
  if(p.permalink){const link=element('a','', 'Abrir original');link.href=p.permalink;link.target='_blank';link.rel='noopener noreferrer';info.append(element('div'),link);}
  const b=element('button','', 'Visualizar '+p.assets.length+' arquivos');b.onclick=()=>openViewer(p);info.append(b);a.append(info);return a;
}
async function get(path){const r=await fetch(path);if(!r.ok)throw Error('Falha ao ler acervo');return await r.json();}
async function load(reset=true){
  try{
    if(reset){offset=0;$('mural').replaceChildren();}
    const qs=new URLSearchParams({limit:'40',offset:String(offset)});
    if($('profile').value)qs.set('username',$('profile').value);
    if($('kind').value)qs.set('kind',$('kind').value);
    const posts=await get('/api/posts?'+qs);
    posts.forEach(p=>$('mural').append(card(p)));offset+=posts.length;$('more').hidden=posts.length<40;
    $('status').textContent=offset+' publicações exibidas';
  }catch(e){$('status').textContent='Falha ao abrir o acervo local';}
}
async function init(){
  try{
    const profiles=await get('/api/competitors');
    for(const p of profiles){const o=element('option','', '@'+p.username);o.value=p.username;$('profile').append(o);}
    const stats=await get('/api/stats');
    $('health').textContent=stats.posts+' publicações · '+stats.blobs+' arquivos locais';
  }catch(e){$('health').textContent='Acervo indisponível';}
  await load();
}
$('profile').onchange=()=>load();$('kind').onchange=()=>load();$('refresh').onclick=()=>load();$('more').onclick=()=>load(false);
$('close').onclick=()=>$('viewer').close();
$('prev').onclick=()=>{if(slides.length){index=(index-1+slides.length)%slides.length;showSlide();}};
$('next').onclick=()=>{if(slides.length){index=(index+1)%slides.length;showSlide();}};
init();
