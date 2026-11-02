const API = "http://localhost:8001/api";
const API_ORIGIN = "http://localhost:8001";
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
let token = localStorage.getItem("clothed.token") || "";
let currentUser = null;
let state = {items:[], outfits:[], wears:[], analytics:null};
let activeFilter = "All", selected = new Set(), monthCursor = new Date(), pendingImage = null, aiNotes = "", aiConfidence = null;
let authMode = "login";
let activeAIConfig = null;

function esc(s=""){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
function apiImage(url){return url ? (url.startsWith("http") ? url : API_ORIGIN + url) : ""}
function img(item,cls=""){return item.image_url?`<img class="${cls}" src="${esc(apiImage(item.image_url))}" alt="${esc(item.name)}">`:`<div class="${cls||"photo-placeholder"}">cloth(ed)</div>`}
function itemPriceMeta(item){
 if(item.purchase_price==null)return "";
 const stat=state.analytics?.item_stats?.find(x=>x.item_id===item.id);
 return `<small>₹${Number(item.purchase_price).toFixed(0)} · ${stat?.cost_per_wear!=null?`₹${Number(stat.cost_per_wear).toFixed(0)} / wear`:"not worn yet"}</small>`;
}
function toast(msg){const t=$("#toast");t.textContent=msg;t.classList.add("show");setTimeout(()=>t.classList.remove("show"),2300)}
async function request(path, options={}){
 const headers = {...(options.headers||{})};
 if(token) headers.Authorization = `Bearer ${token}`;
 if(options.body && !(options.body instanceof FormData)) headers["Content-Type"]="application/json";
 const res=await fetch(API+path,{...options,headers});
 if(res.status===401){signOut(false);throw new Error("Your session expired. Please sign in again.")}
 if(!res.ok){let message=`Request failed (${res.status})`;try{const data=await res.json();message=data.detail||message}catch{}throw new Error(message)}
 if(res.status===204)return null;
 return res.json();
}
async function loadState(){
 const [items,outfits,wears,analytics]=await Promise.all([request("/items"),request("/outfits"),request("/wears"),request("/analytics")]);
 state.items=items;state.outfits=outfits;state.wears=wears;state.analytics=analytics;
 renderAll();
}
function showAuth(mode="login"){
 authMode=mode;$("#auth-title").textContent=mode==="login"?"Welcome back.":"Make room for your style.";
 $("#auth-copy").textContent=mode==="login"?"Sign in to step back into your wardrobe.":"Create an account to start building your digital closet.";
 $("#auth-submit").textContent=mode==="login"?"Sign in ↗":"Create my account ↗";
 $("#auth-switch").textContent=mode==="login"?"New here? Create an account":"Already have an account? Sign in";
 $("#auth-error").textContent="";$("#auth-dialog").showModal();
}
function signOut(show=true){token="";currentUser=null;localStorage.removeItem("clothed.token");state={items:[],outfits:[],wears:[]};$("#account-email").textContent="";if(show)toast("Signed out");showAuth("login")}
$("#auth-switch").addEventListener("click",()=>showAuth(authMode==="login"?"register":"login"));
$("#auth-form").addEventListener("submit",async e=>{
 e.preventDefault();const email=$("#auth-email").value.trim(),password=$("#auth-password").value;
 const path=authMode==="login"?"/auth/login":"/auth/register";
 $("#auth-submit").disabled=true;$("#auth-error").textContent="";
 try{
  const data=await fetch(API+path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,password})});
  const result=await data.json();if(!data.ok)throw new Error(result.detail||"Unable to authenticate.");
  token=result.access_token;localStorage.setItem("clothed.token",token);currentUser=result.user;
  $("#auth-dialog").close();await boot();
 }catch(err){$("#auth-error").textContent=err.message}
 finally{$("#auth-submit").disabled=false}
});
$("#logout-button").addEventListener("click",()=>signOut());

function go(view){$$(".view").forEach(v=>v.classList.toggle("active",v.id===`view-${view}`));$$(".nav-link").forEach(n=>n.classList.toggle("active",n.dataset.view===view));$("#crumb").textContent=view.toUpperCase();if(view==="calendar")renderCalendar();if(view==="outfits")renderStudio();window.scrollTo({top:0,behavior:"smooth"})}
$$(".nav-link").forEach(b=>b.addEventListener("click",()=>go(b.dataset.view)));
$$("[data-go]").forEach(b=>b.addEventListener("click",()=>go(b.dataset.go)));
$("#today-label").textContent=new Intl.DateTimeFormat("en",{weekday:"short",day:"numeric",month:"short"}).format(new Date()).toUpperCase();

function renderAll(){renderHome();renderWardrobe();renderStudio();renderCalendar()}
function renderHome(){
 $("#nav-count").textContent=state.items.length;$("#stat-items").textContent=state.items.length;$("#stat-outfits").textContent=state.outfits.length;$("#stat-wears").textContent=state.wears.length;
 const wornIds=new Set(state.wears.flatMap(w=>w.outfit?.items?.map(i=>String(i.id))||[]));
 $("#stat-unworn").textContent=state.items.filter(i=>!wornIds.has(String(i.id))).length;
 const recent=state.items.slice(0,4);$("#recent-items").innerHTML=recent.length?recent.map(i=>`<div class="mini-item">${img(i)}<span>${esc(i.name)}</span></div>`).join(""):'<div class="empty-inline">Your next favourite piece belongs here.</div>';
 const a=state.analytics||{};
 $("#insight-favourites").textContent=a.favorite_item_count??"—";
 $("#insight-repeats").textContent=a.repeated_outfits?.length??"—";
 $("#insight-cpw").textContent=a.average_cost_per_wear==null?"—":`₹${Number(a.average_cost_per_wear).toFixed(0)}`;
 const least=a.least_worn||[];
 $("#least-worn-list").innerHTML=least.length?least.slice(0,5).map(i=>`<div class="insight-row"><span>${esc(i.name)}</span><strong>${i.wear_count} wears</strong></div>`).join(""):'<div class="empty-inline">Log outfits to discover underused pieces.</div>';
 const repeated=a.repeated_outfits||[];
 $("#repeated-outfits-list").innerHTML=repeated.length?repeated.slice(0,5).map(o=>`<div class="insight-row"><span>${esc(o.name)}</span><strong>${o.wear_count} wears</strong></div>`).join(""):'<div class="empty-inline">No repeated outfits yet.</div>';
}
function fillAttributeFilters(){
 const configs=[["filter-colour","colour","Any colour"],["filter-style","style","Any style"],["filter-subcategory","subcategory","Any type"],["filter-occasion","occasion","Any occasion"]];
 configs.forEach(([id,key,label])=>{
   const el=$("#"+id),current=el.value;
   const values=[...new Set(state.items.map(i=>i[key]).filter(Boolean).map(v=>String(v).trim()))].sort((a,b)=>a.localeCompare(b));
   el.innerHTML=`<option value="">${label}</option>`+values.map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join("");
   el.value=values.includes(current)?current:"";
 });
}
function renderWardrobe(){
 fillAttributeFilters();
 const q=$("#search").value.toLowerCase();
 const colour=$("#filter-colour").value,style=$("#filter-style").value,sub=$("#filter-subcategory").value,occasion=$("#filter-occasion").value;
 const list=state.items.filter(i=>(activeFilter==="All"||(activeFilter==="Favorites"?i.is_favorite:i.category===activeFilter))
   &&[i.name,i.brand,i.colour,i.style,i.subcategory,i.pattern].join(" ").toLowerCase().includes(q)
   &&(!colour||i.colour===colour)&&(!style||i.style===style)&&(!sub||i.subcategory===sub)&&(!occasion||i.occasion===occasion));
 $("#all-count").textContent=state.items.length;
 $("#item-grid").innerHTML=list.length?list.map(i=>`<article class="item-card" data-item-detail="${i.id}" tabindex="0" role="button" aria-label="View ${esc(i.name)} details"><div class="item-photo">${img(i)}<button class="item-favorite ${i.is_favorite?"active":""}" data-fav-item="${i.id}" title="Toggle favourite" aria-label="Toggle favourite">${i.is_favorite?"♥":"♡"}</button><button class="item-delete" data-delete="${i.id}" title="Remove item">×</button><span class="item-view-hint">VIEW DETAILS ↗</span></div><div class="item-meta"><strong>${esc(i.name)}</strong><small>${esc([i.category,i.subcategory,i.colour,i.pattern,i.brand].filter(Boolean).join(" · "))}</small>${itemPriceMeta(i)}</div></article>`).join(""):`<div class="empty-state"><h3>${state.items.length?"Nothing matches these filters.":"A closet full of possibility."}</h3><p>${state.items.length?"Try clearing a filter or changing your search.":"Add your first piece to start building your digital wardrobe."}</p><button class="button dark" id="empty-add">＋ Add your first piece</button></div>`;
 $("#empty-add")?.addEventListener("click",openAdd);
 $$("[data-item-detail]").forEach(card=>{
   card.addEventListener("click",e=>{if(e.target.closest("[data-delete]"))return;openItemDetail(Number(card.dataset.itemDetail))});
   card.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();openItemDetail(Number(card.dataset.itemDetail))}});
 });
 $$("[data-fav-item]").forEach(b=>b.addEventListener("click",async e=>{e.stopPropagation();try{const item=state.items.find(i=>i.id===Number(b.dataset.favItem));await request(`/items/${item.id}`,{method:"PATCH",body:JSON.stringify({is_favorite:!item.is_favorite})});await loadState()}catch(err){toast(err.message)}}));
 $$("[data-delete]").forEach(b=>b.addEventListener("click",async e=>{e.stopPropagation();if(!confirm("Remove this piece from your wardrobe?"))return;try{await request(`/items/${b.dataset.delete}`,{method:"DELETE"});selected.delete(String(b.dataset.delete));await loadState();toast("Piece removed")}catch(err){toast(err.message)}}));
}

$("#filters").addEventListener("click",e=>{const b=e.target.closest("[data-filter]");if(!b)return;activeFilter=b.dataset.filter;$$(".filter").forEach(x=>x.classList.toggle("active",x===b));renderWardrobe()});
$("#search").addEventListener("input",renderWardrobe);
["filter-colour","filter-style","filter-subcategory","filter-occasion"].forEach(id=>$("#"+id).addEventListener("change",renderWardrobe));
$("#clear-filters").addEventListener("click",()=>{$("#search").value="";["filter-colour","filter-style","filter-subcategory","filter-occasion"].forEach(id=>$("#"+id).value="");activeFilter="All";$$(".filter").forEach(x=>x.classList.toggle("active",x.dataset.filter==="All"));renderWardrobe()});


const addDialog=$("#add-dialog");
let extractedGarments=[], extractedImageUrl=null;
function openAdd(){pendingImage=null;aiNotes="";aiConfidence=null;extractedGarments=[];extractedImageUrl=null;$("#add-form").reset();$("#image-preview").src="";$(".upload-zone").classList.remove("has-image");$("#analyze-item").disabled=true;$("#extract-outfit").disabled=true;$("#extracted-garments").hidden=true;$("#extracted-garments").innerHTML="";$("#ai-status").textContent="Add a photo to enable AI identification.";addDialog.showModal()}
$("#open-add").addEventListener("click",openAdd);
$$("[data-close]").forEach(b=>b.addEventListener("click",()=>b.closest("dialog").close()));
$("#item-image").addEventListener("change",e=>{
 const f=e.target.files[0];if(!f)return;
 if(f.size>10*1024*1024){toast("Choose an image under 10 MB");e.target.value="";return}
 if(!["image/jpeg","image/png","image/webp"].includes(f.type)){toast("Use a JPG, PNG or WEBP image");e.target.value="";return}
 pendingImage=f;aiNotes="";aiConfidence=null;extractedGarments=[];extractedImageUrl=null;$("#analyze-item").disabled=false;$("#extract-outfit").disabled=false;$("#extracted-garments").hidden=true;$("#ai-status").textContent="Photo ready. Identify one piece, or extract every garment from an outfit photo.";
 const r=new FileReader();r.onload=()=>{$("#image-preview").src=r.result;$(".upload-zone").classList.add("has-image")};r.readAsDataURL(f);
});
function fillExtractedGarment(garment){
 const result=garment.analysis;extractedImageUrl=garment.image_url;
 $("#item-name").value=result.name||"";$("#item-category").value=result.category||"Other";$("#item-subcategory").value=result.subcategory||"";$("#item-colour").value=result.colour||"";$("#item-secondary-colour").value=result.secondary_colour||"";$("#item-pattern").value=result.pattern||"";$("#item-material").value=result.material||"";$("#item-occasion").value=result.occasion||"";aiNotes=result.description||result.notes||"";aiConfidence=typeof result.confidence==="number"?result.confidence:null;
 $("#ai-status").textContent=`Using extracted ${result.subcategory||result.category}. Review, then add it to your closet.`;
}
async function addExtractedGarments(){
 if(!extractedGarments.length)return;const button=$("#add-all-extracted");if(button)button.disabled=true;
 try{for(const garment of extractedGarments){const a=garment.analysis;await request("/items",{method:"POST",body:JSON.stringify({name:a.name||a.subcategory||a.category,category:a.category||"Other",subcategory:a.subcategory||null,colour:a.colour||null,secondary_colour:a.secondary_colour||null,pattern:a.pattern||null,material:a.material||null,occasion:a.occasion||null,style:a.style||null,ai_confidence:typeof a.confidence==="number"?a.confidence:null,notes:a.description||a.notes||null,image_url:garment.image_url})})}addDialog.close();await loadState();go("wardrobe");toast(`${extractedGarments.length} clothing pieces added`)}catch(err){toast(err.message)}finally{if(button)button.disabled=false}
}
$("#extract-outfit").addEventListener("click",async()=>{
 if(!pendingImage)return;const btn=$("#extract-outfit");btn.disabled=true;$("#analyze-item").disabled=true;$("#ai-status").textContent="Finding and separating the clothes…";
 try{const fd=new FormData();fd.append("file",pendingImage);const result=await request("/ai/extract-outfit",{method:"POST",body:fd});extractedGarments=result.garments;const host=$("#extracted-garments");host.innerHTML=`<div class="extracted-head"><strong>${result.garments.length} clothing pieces found</strong><button class="button dark" type="button" id="add-all-extracted">Add all</button></div>${result.garments.map((g,i)=>`<button type="button" class="extracted-garment" data-extracted="${i}"><img src="${esc(apiImage(g.image_url))}" alt="${esc(g.analysis.name||g.analysis.category)}"><span>${esc(g.analysis.name||g.analysis.subcategory||g.analysis.category)}</span><small>${esc(g.analysis.category)}</small></button>`).join("")}`;host.hidden=false;$$('[data-extracted]').forEach(b=>b.addEventListener("click",()=>fillExtractedGarment(extractedGarments[Number(b.dataset.extracted)])));$("#add-all-extracted").addEventListener("click",addExtractedGarments);fillExtractedGarment(result.garments[0]);}catch(err){$("#ai-status").textContent=err.message}finally{btn.disabled=!pendingImage;$("#analyze-item").disabled=!pendingImage}
});
$("#analyze-item").addEventListener("click",async()=>{
 if(!pendingImage){toast("Choose a clothing photo first");return}
 const btn=$("#analyze-item");btn.disabled=true;btn.textContent="Analysing…";$("#ai-status").textContent="Looking at category, colours, pattern and style…";
 try{
  const fd=new FormData();fd.append("file",pendingImage);
  const result=await request("/ai/analyze",{method:"POST",body:fd});
  $("#item-name").value=result.name||"";
  $("#item-category").value=result.category||"Other";
  $("#item-subcategory").value=result.subcategory||"";
  $("#item-colour").value=result.colour||"";
  $("#item-secondary-colour").value=result.secondary_colour||"";
  $("#item-pattern").value=result.pattern||"";
  $("#item-material").value=result.material||"";
  $("#item-occasion").value=result.occasion||"";
  const styleOptions=[...$("#item-style").options];
  const styleMatch=styleOptions.find(o=>o.value.toLowerCase()===String(result.style||"").toLowerCase()) ||
    styleOptions.find(o=>String(result.style||"").toLowerCase().includes(o.value.toLowerCase()));
  if(styleMatch)$("#item-style").value=styleMatch.value;
  aiNotes=result.description||result.notes||"";
  aiConfidence=typeof result.confidence==="number"?result.confidence:null;
  const pct=Math.round((result.confidence||0)*100);
  const providerLabel=activeAIConfig?`${activeAIConfig.provider.toUpperCase()} · ${activeAIConfig.model}`:"AI";
  $("#ai-status").innerHTML=`Suggestions ready <span class="ai-confidence">AI estimate: ${pct}%</span> · ${esc(providerLabel)} · Review before saving`;
  btn.textContent="✳ Analyse again";toast("AI suggestions added — please review them");
 }catch(err){
  $("#ai-status").textContent=err.message;
  btn.textContent="✳ Try AI again";
 }finally{btn.disabled=!pendingImage}
});
$("#add-form").addEventListener("submit",async e=>{
 e.preventDefault();const name=$("#item-name").value.trim();if(!name)return;
 const submit=e.submitter; if(submit)submit.disabled=true;
 try{
  let image_url=extractedImageUrl;
  if(!image_url&&pendingImage){const fd=new FormData();fd.append("file",pendingImage);const uploaded=await request("/uploads",{method:"POST",body:fd});image_url=uploaded.image_url}
  const payload={name,category:$("#item-category").value,subcategory:$("#item-subcategory").value.trim()||null,colour:$("#item-colour").value.trim()||null,secondary_colour:$("#item-secondary-colour").value.trim()||null,pattern:$("#item-pattern").value.trim()||null,material:$("#item-material").value.trim()||null,occasion:$("#item-occasion").value.trim()||null,ai_confidence:aiConfidence,purchase_price:$("#item-price").value?Number($("#item-price").value):null,brand:$("#item-brand").value.trim()||null,style:$("#item-style").value,product_code:$("#item-code").value.trim()||null,image_url,notes:aiNotes||null};
  await request("/items",{method:"POST",body:JSON.stringify(payload)});addDialog.close();await loadState();go("wardrobe");toast("Added to your wardrobe");
 }catch(err){toast(err.message)}finally{if(submit)submit.disabled=false}
});


let detailItemId=null, detailPendingImage=null;
const detailDialog=$("#detail-dialog");
function openItemDetail(id){
 const item=state.items.find(x=>x.id===id);if(!item)return;
 detailItemId=id;detailPendingImage=null;$("#detail-form").reset();$("#detail-title").textContent=item.name;
 const fields={"name":"name","category":"category","subcategory":"subcategory","colour":"colour","secondary-colour":"secondary_colour","pattern":"pattern","material":"material","occasion":"occasion","brand":"brand","style":"style","product-code":"product_code","purchase-price":"purchase_price","notes":"notes"};
 Object.entries(fields).forEach(([field,key])=>{const el=$("#edit-"+field);if(el)el.value=item[key]||""});
 $("#detail-image-preview").src=item.image_url?apiImage(item.image_url):"";
 $("#detail-image").value="";
 detailDialog.showModal();
}
$("#detail-image").addEventListener("change",e=>{
 const file=e.target.files[0];if(!file)return;
 if(file.size>5*1024*1024||!["image/jpeg","image/png","image/webp"].includes(file.type)){toast("Choose a JPG, PNG or WEBP image under 5 MB");e.target.value="";return}
 detailPendingImage=file;const reader=new FileReader();reader.onload=()=>$("#detail-image-preview").src=reader.result;reader.readAsDataURL(file);
});
$("#detail-form").addEventListener("submit",async e=>{
 e.preventDefault();if(!detailItemId)return;
 const submit=e.submitter;if(submit)submit.disabled=true;
 try{
   const current=state.items.find(i=>i.id===detailItemId);
   let image_url=current?.image_url||null;
   if(detailPendingImage){const fd=new FormData();fd.append("file",detailPendingImage);const uploaded=await request("/uploads",{method:"POST",body:fd});image_url=uploaded.image_url}
   const val=id=>$("#edit-"+id).value.trim()||null;
   const payload={name:val("name"),category:val("category"),subcategory:val("subcategory"),colour:val("colour"),secondary_colour:val("secondary-colour"),pattern:val("pattern"),material:val("material"),occasion:val("occasion"),brand:val("brand"),style:val("style"),product_code:val("product-code"),purchase_price:val("purchase-price")===null?null:Number(val("purchase-price")),notes:val("notes"),image_url};
   await request(`/items/${detailItemId}`,{method:"PATCH",body:JSON.stringify(payload)});
   detailDialog.close();await loadState();toast("Wardrobe piece updated");
 }catch(err){toast(err.message)}finally{if(submit)submit.disabled=false}
});
$("#delete-detail").addEventListener("click",async()=>{
 if(!detailItemId||!confirm("Delete this piece from your wardrobe? This also removes it from saved outfits."))return;
 try{await request(`/items/${detailItemId}`,{method:"DELETE"});selected.delete(String(detailItemId));detailDialog.close();await loadState();toast("Piece deleted")}catch(err){toast(err.message)}
});

function addToCanvas(id){
 id=String(id);
 if(selected.has(id)){selected.delete(id)}
 else if(selected.size<6){selected.add(id)}
 else{toast("The canvas holds up to six pieces");return}
 renderStudio();
}
function renderStudio(){
 const host=$("#studio-items");if(!host)return;
 host.innerHTML=state.items.length?state.items.map(i=>`<button draggable="true" class="studio-piece ${selected.has(String(i.id))?"selected":""}" data-pick="${i.id}">${img(i)}<span>${esc(i.name)}</span><small>${esc(i.category)}</small></button>`).join(""):'<div class="empty-inline">Add pieces to your wardrobe first.</div>';
 $$("[data-pick]").forEach(b=>{
   b.addEventListener("click",()=>addToCanvas(b.dataset.pick));
   b.addEventListener("dragstart",e=>{e.dataTransfer.setData("text/plain",b.dataset.pick);e.dataTransfer.effectAllowed="copy";});
 });
 const canvas=$("#outfit-canvas");
 canvas.ondragover=e=>{e.preventDefault();canvas.classList.add("drag-over");e.dataTransfer.dropEffect="copy"};
 canvas.ondragleave=e=>{if(!canvas.contains(e.relatedTarget))canvas.classList.remove("drag-over")};
 canvas.ondrop=e=>{e.preventDefault();canvas.classList.remove("drag-over");const id=e.dataTransfer.getData("text/plain");if(id)addToCanvas(id)};
 const chosen=state.items.filter(i=>selected.has(String(i.id)));
 $("#selected-outfit").innerHTML=chosen.length?chosen.map(i=>`<div class="selected-piece" draggable="true" data-canvas-piece="${i.id}">${img(i)}<small>${esc(i.name)}</small><button type="button" class="canvas-remove" data-remove-canvas="${i.id}" aria-label="Remove ${esc(i.name)}">×</button></div>`).join(""):'<div class="preview-empty">Your canvas is waiting.<br>Choose or drag pieces from your wardrobe.</div>';
 $$("[data-remove-canvas]").forEach(b=>b.addEventListener("click",()=>{selected.delete(String(b.dataset.removeCanvas));renderStudio()}));
 $("#saved-outfits").innerHTML=state.outfits.length?state.outfits.slice().reverse().map(o=>`<article class="saved-card"><button class="outfit-favorite ${o.is_favorite?"active":""}" data-fav-outfit="${o.id}" title="Toggle favourite">${o.is_favorite?"♥":"♡"}</button><div class="saved-thumbs">${o.items.map(i=>img(i)).slice(0,3).join("")}</div><h4>${esc(o.name)}</h4><p>${o.items.length} pieces · ${new Date(o.created_at).toLocaleDateString()}</p></article>`).join(""):'<div class="empty-inline">Your lookbook is waiting for its first outfit.</div>';
 $$("[data-fav-outfit]").forEach(b=>b.addEventListener("click",async()=>{const outfit=state.outfits.find(o=>o.id===Number(b.dataset.favOutfit));try{await request(`/outfits/${outfit.id}`,{method:"PATCH",body:JSON.stringify({is_favorite:!outfit.is_favorite})});await loadState()}catch(err){toast(err.message)}}));
}

$("#save-outfit").addEventListener("click",async()=>{if(!selected.size){toast("Choose at least one piece first");return}const name=$("#outfit-name").value.trim()||"Untitled look";try{await request("/outfits",{method:"POST",body:JSON.stringify({name,item_ids:[...selected].map(Number)})});selected.clear();$("#outfit-name").value="";await loadState();toast("Outfit saved to your lookbook")}catch(err){toast(err.message)}});


function renderRecommendations(data){
 const host=$("#recommendation-grid");
 if(!data.recommendations?.length){host.innerHTML="";$("#recommend-message").textContent=data.message||"No suggestions yet.";return}
 $("#recommend-message").textContent=`${data.recommendations.length} combinations from your wardrobe. Scores are heuristic styling estimates, not AI ratings.`;
 host.innerHTML=data.recommendations.map((r,n)=>`<article class="recommend-card">
   <div class="recommend-items">${r.items.map(i=>`<div class="recommend-piece">${i.image_url?`<img src="${esc(apiImage(i.image_url))}" alt="${esc(i.name)}">`:'<div class="recommend-placeholder">cloth(ed)</div>'}<small>${esc(i.name)}</small></div>`).join("")}</div>
   <div class="recommend-card-meta"><div><strong>Look ${n+1}</strong><small>${Math.round(r.score*100)}% compatibility · ${r.items.length} pieces</small></div><button class="text-button" data-save-recommend="${n}">Save look ↗</button></div>
   <p>${r.reasons.map(esc).join(" · ")}</p>
 </article>`).join("");
 $$("[data-save-recommend]").forEach(btn=>btn.addEventListener("click",async()=>{
   const r=data.recommendations[Number(btn.dataset.saveRecommend)];
   btn.disabled=true;
   try{await request("/outfits",{method:"POST",body:JSON.stringify({name:`Suggested look ${new Date().toLocaleDateString()}`,item_ids:r.item_ids})});await loadState();toast("Suggested look saved to your lookbook");}
   catch(err){toast(err.message);btn.disabled=false}
 }));
}
$("#generate-recommendations").addEventListener("click",async()=>{
 const btn=$("#generate-recommendations");btn.disabled=true;btn.textContent="Styling…";
 $("#recommend-message").textContent="Finding combinations and checking your recent wear history…";
 try{
   const occasion=encodeURIComponent($("#recommend-occasion").value);
   const weather=encodeURIComponent($("#recommend-weather").value);
   const data=await request(`/outfits/recommendations?limit=6${occasion?`&occasion=${occasion}`:""}${weather?`&weather=${weather}`:""}`);
   renderRecommendations(data);
 }catch(err){$("#recommend-message").textContent=err.message}
 finally{btn.disabled=false;btn.textContent="✳ Style me"}
});
async function loadAIConfig(){
 try{
   activeAIConfig=await request("/ai/config");
   $("#ai-provider-label").textContent=`AI · ${activeAIConfig.provider.toUpperCase()}`;
   $("#ai-provider-label").title=`${activeAIConfig.mode} · ${activeAIConfig.model}`;
 }catch(_){$("#ai-provider-label").textContent="AI · UNAVAILABLE"}
}

const wearDialog=$("#wear-dialog");
$("#log-wear").addEventListener("click",()=>{if(!state.outfits.length){toast("Save an outfit in Outfit Studio first");go("outfits");return}$("#wear-date").value=new Date().toISOString().slice(0,10);$("#wear-outfit").innerHTML='<option value="">Choose a saved outfit</option>'+state.outfits.map(o=>`<option value="${o.id}">${esc(o.name)}</option>`).join("");$("#wear-note").value="";$("#wear-repeat-hint").textContent="Choose an outfit to check its wear history.";$("#wear-repeat-hint").classList.remove("repeat-warning");wearDialog.showModal()});
$("#wear-outfit").addEventListener("change",async()=>{
 const id=$("#wear-outfit").value, hint=$("#wear-repeat-hint");
 if(!id){hint.textContent="Choose an outfit to check its wear history.";return}
 hint.textContent="Checking wear history…";
 try{const info=await request(`/outfits/${id}/repeat-check`);hint.textContent=info.wear_count?`Worn ${info.wear_count} time(s). Last worn: ${info.last_worn}${info.repeat_warning?" · Recently worn — consider a different look.":""}`:"This outfit hasn't been logged yet.";hint.classList.toggle("repeat-warning",info.repeat_warning)}
 catch(err){hint.textContent=err.message}
});
$("#wear-form").addEventListener("submit",async e=>{e.preventDefault();const outfitId=$("#wear-outfit").value;const date=$("#wear-date").value;if(!date){toast("Choose a date");return}try{await request("/wears",{method:"POST",body:JSON.stringify({worn_on:date,outfit_id:outfitId?Number(outfitId):null,note:$("#wear-note").value.trim()||null})});wearDialog.close();await loadState();toast("Added to your wear diary")}catch(err){toast(err.message)}});

function renderCalendar(){
 const y=monthCursor.getFullYear(),m=monthCursor.getMonth();$("#month-title").textContent=new Intl.DateTimeFormat("en",{month:"long",year:"numeric"}).format(monthCursor);
 const first=new Date(y,m,1).getDay(),days=new Date(y,m+1,0).getDate(),today=new Date();let html=["S","M","T","W","T","F","S"].map(d=>`<div class="day-name">${d}</div>`).join("");
 for(let i=0;i<first;i++)html+='<div class="day blank"></div>';
 for(let d=1;d<=days;d++){const date=`${y}-${String(m+1).padStart(2,"0")}-${String(d).padStart(2,"0")}`,wear=state.wears.filter(w=>w.worn_on===date);html+=`<div class="day ${wear.length?"has-wear":""} ${today.getFullYear()===y&&today.getMonth()===m&&today.getDate()===d?"today":""}">${d}${wear.length?`<small>${wear.length} look${wear.length>1?"s":""}</small>`:""}</div>`}
 $("#calendar-grid").innerHTML=html;
 const recent=state.wears.slice().sort((a,b)=>b.worn_on.localeCompare(a.worn_on)).slice(0,8);
 $("#wear-list").innerHTML=recent.map(w=>`<div class="wear-entry"><strong>${esc(w.note||w.outfit?.name||"Outfit logged")}</strong><small>${new Date(w.worn_on+"T00:00:00").toLocaleDateString("en",{weekday:"short",day:"numeric",month:"short",year:"numeric"})}</small></div>`).join("");
 const counts={};state.wears.forEach(w=>(w.outfit?.items||[]).forEach(i=>counts[i.id]=(counts[i.id]||0)+1));
 const top=Object.entries(counts).sort((a,b)=>b[1]-a[1]).slice(0,6);
 $("#most-worn").innerHTML=top.length?top.map(([id,n])=>{const i=state.items.find(x=>String(x.id)===String(id));return i?`<div class="worn-piece">${img(i)}<strong>${esc(i.name)}</strong><small>${n} wear${n===1?"":"s"}</small></div>`:""}).join(""):'<div class="empty-inline">Log outfits to see your most-loved pieces here.</div>';
}
$("#prev-month").addEventListener("click",()=>{monthCursor.setMonth(monthCursor.getMonth()-1);renderCalendar()});
$("#next-month").addEventListener("click",()=>{monthCursor.setMonth(monthCursor.getMonth()+1);renderCalendar()});

async function boot(){
 try{currentUser=await request("/auth/me");$("#account-email").textContent=currentUser.email;await loadAIConfig();await loadState()}
 catch(err){if(token){localStorage.removeItem("clothed.token");token=""}showAuth("login")}
}
boot();
