"""Generate the self-contained, offline ZonitoVisuals catalogue report."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path, PurePosixPath


def _local_path(value: object) -> str | None:
    """Keep image references local to the catalogue directory."""
    if not isinstance(value, str) or not value:
        return None
    value = value.replace("\\", "/")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or ":" in value:
        return None
    return value


def _script_json(value: object) -> str:
    # Escaping '<' prevents user-controlled strings from closing the JSON script.
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace(
        "<", "\\u003c"
    ).replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _clean_records(records: list[dict], collection: str = "textures") -> list[dict]:
    """Keep only display fields and turn collection-local image paths into root paths."""
    clean = []
    for record in records:
        asset_id = str(record.get("asset_id", ""))
        kind = record.get("kind")
        if collection == "textures":
            kind = "flipbook" if kind == "flipbook" else "static"
        else:
            kind = "beam" if collection == "beams" else "mesh"

        def image_path(field):
            relative = _local_path(record.get(field))
            if relative and collection != "textures" and not relative.startswith(collection + "/"):
                relative = collection + "/" + relative
            return relative

        references = []
        for reference in record.get("references") or []:
            if not isinstance(reference, dict):
                continue
            reference_id = str(reference.get("asset_id") or "")
            uri = str(reference.get("uri") or ("rbxassetid://" + reference_id if reference_id else ""))
            if uri:
                references.append({"label": str(reference.get("label") or "Référence"),
                                   "asset_id": reference_id, "uri": uri})
        item = {
            "asset_id": asset_id,
            "uri": str(record.get("uri") or ("rbxassetid://" + asset_id if asset_id else "")),
            "name": str(record.get("name", "")),
            "creator": str(record.get("creator") or ""),
            "tags": [str(t) for t in record.get("tags", [])],
            "kind": kind,
            "kind_source": str(record.get("kind_source") or "inconnu"),
            "kind_source_labels": [str(label) for label in record.get("kind_source_labels", [])],
            "type_collection_ambiguous": bool(record.get("type_collection_ambiguous", False)),
            "grid": record.get("grid") if record.get("grid") in (2, 4, 8) else 0,
            "grid_source": str(record.get("grid_source") or "inconnu"),
            "image_path": image_path("image_path"),
            "preview_path": image_path("preview_path"),
            "image_status": str(record.get("image_status") or "inconnu"),
            "image_source": str(record.get("image_source") or record.get("source") or ""),
            "references": references,
        }
        for key in ("width", "height", "image_width", "image_height", "dimensions"):
            if key in record:
                item[key] = record[key]
        clean.append(item)
    return clean


def _display_stats(records: list[dict]) -> dict:
    return {"statuses": dict(sorted(Counter(r["image_status"] for r in records).items())),
            "with_image": sum(bool(r["preview_path"] or r["image_path"]) for r in records)}


def build_gallery(records: list[dict], output_dir: Path, summary: dict, *,
                  extra_collections: dict | None = None) -> Path:
    """Write one offline catalogue with Textures, Beams and Meshes tabs.

    The positional arguments and payload records/summary remain texture-only for
    compatibility. Optional extra_collections is a mapping with 'beams'/'meshes'
    keys, each containing records and summary. An extra image path can already
    start with 'beams/' or 'meshes/'; a collection-local path such as images/ID.png
    receives that prefix once. No server or remote assets are used by the page.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    clean = _clean_records(records)
    payload = {
        "records": clean,
        "summary": summary,
        **_display_stats(clean),
        "extra_collections": {},
    }
    for collection in ("beams", "meshes"):
        source = (extra_collections or {}).get(collection)
        if source is not None:
            rows = _clean_records(source.get("records") or [], collection)
            payload["extra_collections"][collection] = {
                "records": rows, "summary": source.get("summary") or {}, **_display_stats(rows)}
    destination = output_dir / "catalogue.html"
    destination.write_text(_HTML.replace("__CATALOGUE_DATA__", _script_json(payload)), encoding="utf-8")
    return destination.resolve()


_HTML = r'''<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dataky FX Studio · Bibliothèque VFX</title>
<style>
:root{color-scheme:dark;--bg:#111217;--panel:#1b1d25;--ink:#f0f1f8;--muted:#a9afc2;--line:#353848;--accent:#bbb0ff;--square-a:#242630;--square-b:#2c2f3c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}button,input,select{font:inherit;color:inherit}button,input,select{border:1px solid var(--line);border-radius:9px;background:var(--panel);padding:9px 12px}button{cursor:pointer}button:hover{border-color:var(--accent);color:var(--accent)}button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid var(--accent);outline-offset:2px}button:disabled{opacity:.45;cursor:default}header{padding:32px 4vw 20px;max-width:1800px;margin:auto}h1{margin:0;font-size:clamp(24px,3vw,38px);letter-spacing:-1px}header p{margin:7px 0;color:var(--muted)}.eyebrow{font-size:11px;font-weight:750;letter-spacing:2px;color:var(--accent);margin-bottom:10px}.toolbar{display:flex;gap:10px;flex-wrap:wrap;padding:15px 4vw;background:#111217ed;position:sticky;top:0;z-index:2;border-block:1px solid var(--line);backdrop-filter:blur(12px)}.field{display:flex;gap:5px;flex-direction:column}.field label{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--muted)}.search{flex:1;min-width:240px}.toolbar input{width:100%}.toolbar select{max-width:250px}.background-toggle{align-self:flex-end}main{max-width:1800px;margin:auto;padding:20px 4vw 35px}.results{display:flex;justify-content:space-between;gap:12px;align-items:center;color:var(--muted);padding-bottom:17px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:15px}.card{overflow:hidden;border-radius:12px;border:1px solid var(--line);background:var(--panel);min-width:0}.visual{background-color:var(--square-a);background-image:linear-gradient(45deg,var(--square-b) 25%,transparent 25%),linear-gradient(-45deg,var(--square-b) 25%,transparent 25%),linear-gradient(45deg,transparent 75%,var(--square-b) 75%),linear-gradient(-45deg,transparent 75%,var(--square-b) 75%);background-size:20px 20px;background-position:0 0,0 10px,10px -10px,-10px 0}.light{--square-a:#d9dbe2;--square-b:#f2f3f6}.thumb{width:100%;height:auto;aspect-ratio:1;display:block;object-fit:contain;padding:10px}.open{display:block;padding:0;border:0;width:100%;border-radius:0;position:relative}.missing{min-height:190px;aspect-ratio:1;display:flex;align-items:center;justify-content:center;flex-direction:column;padding:15px;color:var(--muted);font-size:13px}.kind{position:absolute;left:9px;bottom:9px;background:#12131de8;border:1px solid #4e5066;color:#ece8ff;padding:2px 7px;border-radius:5px;font-size:10px;letter-spacing:.4px}.info{padding:13px}.name{font-size:14px;font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin:0}.id{font-family:ui-monospace,Consolas,monospace;color:var(--muted);font-size:12px;margin:5px 0}.tags{display:flex;gap:5px;flex-wrap:wrap;margin-top:10px}.tag{background:#292636;color:#cfc4ff;font-size:10px;padding:2px 7px;border-radius:20px}.actions{display:flex;gap:6px;margin-top:12px}.actions button{font-size:11px;padding:5px 8px;flex:1}.pager{display:flex;align-items:center;justify-content:center;gap:14px;margin:28px 0 0}.empty{text-align:center;padding:80px 10px;color:var(--muted)}footer{border-top:1px solid var(--line);padding:22px 4vw 35px;color:var(--muted);font-size:12px}footer p{margin:5px 0}footer details{margin-top:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}dialog{color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:15px;padding:22px;max-width:850px;width:calc(100% - 30px);max-height:calc(100vh - 30px);overflow:auto}dialog::backdrop{background:#000a;backdrop-filter:blur(5px)}.detail-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.detail-head h2{font-size:20px;margin:0}.detail-body{display:grid;grid-template-columns:minmax(220px,1fr) minmax(180px,.8fr);gap:22px;margin-top:18px}.preview{width:100%;aspect-ratio:1;position:relative;overflow:hidden;border-radius:9px}.preview img{width:100%;height:100%;object-fit:contain;position:absolute;left:0;top:0;max-width:none;transform-origin:top left}.preview.animating img{object-fit:fill}.metadata{font-size:13px;overflow-wrap:anywhere}.metadata strong{display:block;color:var(--muted);font-weight:500;font-size:11px;letter-spacing:.7px;text-transform:uppercase;margin-top:15px}.metadata p{margin:3px 0}.detail-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:18px}.status{color:var(--muted);font-size:12px;margin-top:10px}.toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:#d4caff;color:#201a35;box-shadow:0 6px 30px #0006;border-radius:9px;padding:10px 20px;z-index:20;max-width:calc(100vw - 30px);text-align:center}.visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}@media(max-width:600px){header{padding-top:22px}.toolbar{gap:8px}.toolbar select{max-width:100%}.search{flex-basis:100%}.grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.info{padding:10px}.actions{flex-direction:column}.detail-body{grid-template-columns:1fr}.missing{min-height:120px}.name{font-size:12px}.field{flex:1}.background-toggle{font-size:12px}.results{font-size:12px}}
[hidden]{display:none!important}.collection-tabs{display:flex;gap:9px;flex-wrap:wrap;margin-top:23px}.collection-tabs button{padding:10px 17px;font-weight:650}.collection-tabs button[aria-pressed="true"]{background:#373049;border-color:#9d8ee4;color:#e3d9ff}.collection-note{margin:0 0 17px;color:var(--muted);font-size:12px}.reference-row{border:1px solid var(--line);border-radius:8px;padding:9px;margin-top:8px}.reference-row p{font:11px/1.5 ui-monospace,Consolas,monospace;color:var(--muted)}.reference-row button{font-size:11px;padding:4px 9px;margin-top:6px}
</style></head><body>
<header><div class="eyebrow">DATAKY FX STUDIO · BIBLIOTHÈQUE LOCALE</div><h1>Dataky FX Studio</h1><p>Textures, beams, meshes et références Roblox. Consultation hors ligne, aperçus conservés dans vos fichiers. Pour créer vos effets, lancez <strong>DATAKY_FX_STUDIO.bat</strong>, puis <a href="http://127.0.0.1:48754/" style="color:var(--accent,#9bdfff)">ouvrez l’atelier</a>.</p><nav class="collection-tabs" aria-label="Collections de la bibliothèque"><button id="tab-textures" aria-pressed="true">Textures</button><button id="tab-beams" aria-pressed="false">Beams</button><button id="tab-meshes" aria-pressed="false">Meshes</button></nav></header>
<div class="toolbar" aria-label="Filtres du catalogue"><div class="field search"><label for="search">Recherche</label><input id="search" type="search" placeholder="Nom, ID, tag, créateur…" autocomplete="off"></div><div class="field"><label for="tag">Tag</label><select id="tag"><option value="">Tous les tags</option></select></div><div class="field" id="kind-field"><label for="kind">Type</label><select id="kind"><option value="">Tous les types</option><option value="static">Images fixes</option><option value="flipbook">Flipbooks</option></select></div><button id="background" class="background-toggle" aria-pressed="false">Fond clair</button></div>
<main><p id="collection-note" class="collection-note"></p><div class="results"><span id="count" role="status" aria-live="polite"></span><span>100 entrées par page</span></div><div id="grid" class="grid"></div><div id="empty" class="empty" hidden>Aucune entrée ne correspond à ces filtres.</div><nav class="pager" aria-label="Pagination"><button id="prev">← Précédente</button><span id="page"></span><button id="next">Suivante →</button></nav></main>
<footer><p id="archive-stats"></p><p id="status-stats"></p><p>Les entrées sans aperçu restent référencées par leur ID. La disponibilité dans un jeu dépend des permissions Roblox de chaque asset.</p><details><summary>Rapport de l’extraction de cette collection</summary><pre id="summary"></pre></details></footer>
<dialog id="detail" aria-labelledby="detail-name"><div class="detail-head"><h2 id="detail-name"></h2><button id="close" aria-label="Fermer">✕</button></div><div class="detail-body"><div><div id="preview" class="preview visual"><img id="detail-image" alt=""></div><p id="detail-status" class="status"></p><div class="detail-actions"><button id="animate" hidden>Animer le flipbook</button><label id="fps-label" hidden>FPS <input id="fps" type="number" min="1" max="60" value="16" style="width:76px"></label></div></div><div class="metadata"><strong>ID Roblox principal</strong><p id="detail-id"></p><strong>Référence à utiliser</strong><p id="detail-uri"></p><div id="creator-wrap"><strong>Créateur</strong><p id="detail-creator"></p></div><strong>Type / dimensions de l’aperçu</strong><p id="detail-meta"></p><strong>Tags d’origine</strong><div id="detail-tags" class="tags"></div><div id="references-wrap"><strong>Références du plugin</strong><div id="detail-references"></div></div><div class="detail-actions"><button id="copy-id">Copier l’ID</button><button id="copy-uri">Copier rbxassetid</button><a id="original" target="_blank" rel="noopener" style="color:var(--accent);padding:9px 0">Ouvrir l’image</a></div></div></div></dialog>
<div id="toast" class="toast" role="status" hidden></div>
<script id="catalogue-data" type="application/json">__CATALOGUE_DATA__</script>
<script>
'use strict';
const DATA=JSON.parse(document.getElementById('catalogue-data').textContent);
const $=id=>document.getElementById(id), SIZE=100;
const number=n=>n.toLocaleString('fr-FR');
const collectionLabels={textures:'Textures',beams:'Beams',meshes:'Meshes'};
function searchable(rows){return rows.map(r=>({...r,_search:[r.asset_id,r.uri,r.name,r.creator,...r.tags,...r.references.flatMap(ref=>[ref.label,ref.asset_id,ref.uri])].join(' ').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase()}));}
const collections={textures:{...DATA,records:searchable(DATA.records)}};
for(const id of ['beams','meshes']){const extra=(DATA.extra_collections||{})[id];if(extra)collections[id]={...extra,records:searchable(extra.records)};}
const states={};
let activeId=null,active=null,records=[],tags=[],page=0,filtered=[],selected=null,animation=null,frame=0,toastTimer=null,searchTimer=null;
function el(tag, cls, text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;}
function source(r){return r.preview_path||r.image_path;}
function kindHint(r){if(r.kind==='beam')return 'Référence issue de l’onglet Beams du plugin.';if(r.kind==='mesh')return 'Référence issue de l’onglet Meshes du plugin.';if(r.type_collection_ambiguous)return 'Type ambigu : cette entrée apparaît dans les filtres images fixes et flipbooks. Le classement affiché est déduit du cadrage observé, à vérifier.';if(r.kind_source==='type_collection')return 'Type enregistré depuis le filtre du plugin'+(r.kind_source_labels.length?' : '+r.kind_source_labels.join(', '):'')+'.';return 'Type déduit du cadrage observé dans le plugin, à vérifier.';}
function statusHint(r){return 'État de récupération : '+r.image_status+' · '+kindHint(r)+(r.image_source?' · Aperçu : '+r.image_source:'');}
function inferredGrid(r){return r.grid&&!['plugin','explicit','verified','rect_size'].includes(r.grid_source);}
function gridHint(r){if(!r.grid)return 'Disposition inconnue';if(r.grid_source==='name')return 'Disposition déduite du nom, à vérifier';if(r.grid_source==='inferred_from_1024_sheet')return 'Disposition estimée à partir d’une feuille de 1024 px, à vérifier';return inferredGrid(r)?'Disposition estimée, à vérifier':'Disposition enregistrée dans le plugin';}
function localUrl(path){return path.split('/').map(encodeURIComponent).join('/');}
function notify(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,2200);}
async function copy(text){
  try {if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(text);notify('Copié : '+text);return;}}catch(e){}
  const area=el('textarea');area.value=text;area.style.position='fixed';area.style.top='-1000px';document.body.append(area);area.select();
  let ok=false;try{ok=document.execCommand('copy');}catch(e){}area.remove();
  if(ok)notify('Copié : '+text);else window.prompt('Copiez cette référence :',text);
}
function makeTags(parent,items){parent.replaceChildren();for(const tag of items)parent.append(el('span','tag',tag));if(!items.length)parent.append(el('span','status','Sans tag'));}
function failedImage(img){const box=el('span','missing','Image locale indisponible');img.replaceWith(box);}
function card(r){
 const article=el('article','card');const open=el('button','open visual');open.type='button';open.setAttribute('aria-label','Voir '+(r.name||r.asset_id));
 if(source(r)){const img=el('img','thumb');img.src=localUrl(source(r));img.alt=r.name||('Asset '+r.asset_id);img.loading='lazy';img.decoding='async';img.onerror=()=>failedImage(img);open.append(img);}else open.append(el('span','missing','Aperçu indisponible'));
 if(r.kind==='flipbook')open.append(el('span','kind','FLIPBOOK'+(r.grid?' '+r.grid+' × '+r.grid+(inferredGrid(r)?' estimé':''):'')));
 else if(r.kind==='beam'||r.kind==='mesh')open.append(el('span','kind',r.kind.toUpperCase()));
 open.addEventListener('click',()=>showDetail(r));article.append(open);
 const info=el('div','info');const name=el('h2','name',r.name||'Entrée sans nom');name.title=r.name||r.asset_id;info.append(name,el('div','id',r.asset_id||'ID indisponible'));const t=el('div','tags');makeTags(t,r.tags);info.append(t);
 const actions=el('div','actions');const id=el('button','','Copier l’ID'),uri=el('button','','rbxassetid');id.disabled=!r.asset_id;uri.disabled=!r.uri;id.addEventListener('click',()=>copy(r.asset_id));uri.addEventListener('click',()=>copy(r.uri));actions.append(id,uri);info.append(actions);article.append(info);return article;
}
function render(){
 const pages=Math.max(1,Math.ceil(filtered.length/SIZE));page=Math.max(0,Math.min(page,pages-1));
 const fragment=document.createDocumentFragment();for(const r of filtered.slice(page*SIZE,(page+1)*SIZE))fragment.append(card(r));$('grid').replaceChildren(fragment);
 $('count').textContent=number(filtered.length)+' entrée'+(filtered.length===1?'':'s')+' sur '+number(records.length)+' · '+collectionLabels[activeId];$('page').textContent=(page+1)+' / '+pages;$('prev').disabled=page===0;$('next').disabled=page>=pages-1;$('empty').hidden=filtered.length!==0;
}
function filter(resetPage=true){const terms=$('search').value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim().split(/\s+/).filter(Boolean);filtered=records.filter(r=>(!$('tag').value||r.tags.includes($('tag').value))&&(activeId!=='textures'||!$('kind').value||r.kind===$('kind').value)&&terms.every(t=>r._search.includes(t)));if(resetPage)page=0;render();}
function activateCollection(id){
 if(!collections[id])return;
 clearTimeout(searchTimer);
 if(activeId)states[activeId]={search:$('search').value,tag:$('tag').value,kind:$('kind').value,page};
 if($('detail').open)$('detail').close();
 activeId=id;active=collections[id];records=active.records;tags=[...new Set(records.flatMap(r=>r.tags))].sort((a,b)=>a.localeCompare(b,'fr',{sensitivity:'base'}));
 const state=states[id]||{search:'',tag:'',kind:'',page:0};page=state.page;
 $('search').value=state.search;$('kind').value=id==='textures'?state.kind:'';$('kind-field').hidden=id!=='textures';
 const all=el('option','','Tous les tags');all.value='';$('tag').replaceChildren(all);for(const name of tags){const option=el('option','',name);option.value=name;$('tag').append(option);}$('tag').value=tags.includes(state.tag)?state.tag:'';$('tag').disabled=tags.length===0;
 for(const key of Object.keys(collectionLabels)){const button=$('tab-'+key),dataset=collections[key];button.disabled=!dataset;button.textContent=collectionLabels[key]+(dataset?' · '+number(dataset.records.length):' · à capturer');button.setAttribute('aria-pressed',String(key===id));}
 $('collection-note').textContent=id==='textures'?'Images fixes et flipbooks du plugin, classés par leurs tags d’origine.':id==='beams'?'Textures de beams référencées dans le plugin. Les boutons copient leurs références Roblox.':'Meshes référencés dans le plugin. Les détails conservent les MeshId et les TextureId disponibles.';
 $('archive-stats').textContent=collectionLabels[id]+' · '+number(records.length)+' entrées · '+number(tags.length)+' tags · '+number(active.with_image)+' entrées avec image locale · '+number(records.length-active.with_image)+' sans image locale.';
 $('status-stats').textContent='États enregistrés : '+(Object.entries(active.statuses).map(([status,count])=>status+' : '+number(count)).join(' · ')||'Aucune entrée')+'.';$('summary').textContent=JSON.stringify(active.summary,null,2);
 filter(false);
}
for(const id of Object.keys(collectionLabels))$('tab-'+id).addEventListener('click',()=>activateCollection(id));
$('search').addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>filter(),130);});$('tag').addEventListener('change',()=>filter());$('kind').addEventListener('change',()=>filter());
$('prev').addEventListener('click',()=>{page--;render();window.scrollTo({top:0,behavior:'smooth'});});$('next').addEventListener('click',()=>{page++;render();window.scrollTo({top:0,behavior:'smooth'});});
$('background').addEventListener('click',()=>{const light=document.body.classList.toggle('light');$('background').textContent=light?'Fond sombre':'Fond clair';$('background').setAttribute('aria-pressed',String(light));});
function animationLabel(){return selected&&inferredGrid(selected)?'Animer · disposition estimée':'Animer le flipbook';}
function stopAnimation(){if(animation!==null){clearInterval(animation);animation=null;}frame=0;const img=$('detail-image');img.style.width='100%';img.style.height='100%';img.style.transform='';$('preview').classList.remove('animating');$('animate').textContent=animationLabel();}
function animate(){
 if(animation!==null){stopAnimation();return;}if(!selected||!selected.grid)return;
 const g=selected.grid,img=$('detail-image');$('preview').classList.add('animating');img.style.width=(g*100)+'%';img.style.height=(g*100)+'%';$('animate').textContent='Arrêter l’animation';
 const next=()=>{const x=frame%g,y=Math.floor(frame/g);img.style.transform='translate('+(-x*100/g)+'%,'+(-y*100/g)+'%)';frame=(frame+1)%(g*g);};next();animation=setInterval(next,1000/Math.max(1,Math.min(60,Number($('fps').value)||16)));
}
function showDetail(r){
 stopAnimation();selected=r;$('animate').textContent=animationLabel();$('detail-name').textContent=r.name||('Asset '+r.asset_id);$('detail-id').textContent=r.asset_id||'ID indisponible';$('detail-uri').textContent=r.uri||'Référence indisponible';$('copy-id').disabled=!r.asset_id;$('copy-uri').disabled=!r.uri;$('detail-creator').textContent=r.creator;$('creator-wrap').hidden=!r.creator;
 const w=r.width||r.image_width,h=r.height||r.image_height;let dimensions=w&&h?(w+' × '+h+' px'):(Array.isArray(r.dimensions)?r.dimensions.join(' × '):r.dimensions||'Dimensions non renseignées');
 $('detail-meta').textContent=(r.kind==='flipbook'?'Flipbook'+(r.grid?' · '+r.grid+' × '+r.grid+' ('+(r.grid*r.grid)+' images'+(inferredGrid(r)?', estimé':'')+')':'')+' · '+gridHint(r):r.kind==='beam'?'Beam':r.kind==='mesh'?'Mesh':'Image fixe')+' · Aperçu : '+dimensions;
 $('detail-status').textContent=statusHint(r);
 makeTags($('detail-tags'),r.tags);
 $('detail-references').replaceChildren();$('references-wrap').hidden=r.references.length===0;
 for(const reference of r.references){const row=el('div','reference-row');row.append(el('span','',reference.label),el('p','',reference.uri));const button=el('button','','Copier '+reference.label);button.addEventListener('click',()=>copy(reference.uri));row.append(button);$('detail-references').append(row);}
 const path=r.image_path||r.preview_path,img=$('detail-image');img.hidden=!path;img.alt=r.name||('Asset '+r.asset_id);img.onerror=()=>{$('detail-status').textContent='Image locale indisponible · '+statusHint(r);img.hidden=true;stopAnimation();};
 if(path){img.src=localUrl(path);$('original').href=localUrl(path);$('original').hidden=false;}else{img.removeAttribute('src');$('original').removeAttribute('href');$('original').hidden=true;}
 $('animate').hidden=!(r.kind==='flipbook'&&r.grid&&path);$('fps-label').hidden=$('animate').hidden;
 if(!$('detail').open)$('detail').showModal();
}
$('animate').addEventListener('click',animate);$('fps').addEventListener('change',()=>{if(animation!==null){stopAnimation();animate();}});$('close').addEventListener('click',()=>$('detail').close());$('detail').addEventListener('close',stopAnimation);$('detail').addEventListener('click',e=>{if(e.target===$('detail')){const rect=$('detail').getBoundingClientRect();if(e.clientX<rect.left||e.clientX>rect.right||e.clientY<rect.top||e.clientY>rect.bottom)$('detail').close();}});
$('copy-id').addEventListener('click',()=>{if(selected&&selected.asset_id)copy(selected.asset_id);});$('copy-uri').addEventListener('click',()=>{if(selected&&selected.uri)copy(selected.uri);});
activateCollection('textures');
</script></body></html>'''
