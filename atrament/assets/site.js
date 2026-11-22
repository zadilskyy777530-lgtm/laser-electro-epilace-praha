/* Shared: data, language, header/footer, page wipe, cursor ring. Each page defines window.renderPage(t, lang). */
(function(){
  var DATA={
    artists:[
      {id:"alex",name:"Alex Horák",motif:"moth",since:"2012",needles:"9RL · 15M1 · 23M1",works:["sleeve","cat","wave","flower"]},
      {id:"nina",name:"Nina Vlková",motif:"peony",since:"2017",needles:"1RL · 3RL · 5RS",works:["peony","peonyd","botanic","peony2"]},
      {id:"kris",name:"Kris Malý",motif:"swallow",since:"2015",needles:"9RL · 7M1 · 11RS",works:["floral","dragon","hands","process"]}
    ],
    works:[
      {id:"sleeve",img:"w-sleeve.jpg",style:"jp",artist:"alex"},
      {id:"peony",img:"w-peony.jpg",style:"fine",artist:"nina"},
      {id:"floral",img:"w-floral.jpg",style:"bg",artist:"kris"},
      {id:"cat",img:"d-cat.jpg",style:"jp",artist:"alex"},
      {id:"botanic",img:"w-botanic.jpg",style:"fine",artist:"nina"},
      {id:"dragon",img:"d-dragon.jpg",style:"bg",artist:"kris"},
      {id:"wave",img:"d-wave.jpg",style:"jp",artist:"alex"},
      {id:"peonyd",img:"d-peony.jpg",style:"fine",artist:"nina"},
      {id:"process",img:"w-process.jpg",style:"proc",artist:null},
      {id:"flower",img:"d-flower.jpg",style:"jp",artist:"alex"},
      {id:"peony2",img:"d-peony2.jpg",style:"bg",artist:"kris"},
      {id:"hands",img:"d-hands.jpg",style:"proc",artist:null}
    ],
    flash:[
      {id:"rose",price:2400,size:"8 × 12",artist:"nina",free:true},
      {id:"snake",price:2800,size:"6 × 16",artist:"kris",free:true},
      {id:"dagger",price:2200,size:"5 × 14",artist:"kris",free:false},
      {id:"moth",price:2900,size:"10 × 9",artist:"alex",free:true},
      {id:"eye",price:2500,size:"9 × 9",artist:"kris",free:true},
      {id:"bfly",price:2300,size:"9 × 8",artist:"nina",free:false},
      {id:"swallow",price:1900,size:"9 × 6",artist:"kris",free:true},
      {id:"anchor",price:1800,size:"6 × 10",artist:"kris",free:true},
      {id:"heart",price:2400,size:"8 × 9",artist:"alex",free:true},
      {id:"peony",price:2600,size:"8 × 13",artist:"nina",free:true}
    ]
  };
  var LANGS=["cs","ru","en"];
  var PAGES=[["home","index.html"],["works","prace.html"],["artists","mistri.html"],["flash","flash.html"],["care","pece.html"],["studio","studio.html"]];

  function store(k,v){try{if(v===undefined)return localStorage.getItem(k);localStorage.setItem(k,v);}catch(e){return null;}}
  function initialLang(){var s=store("atrament-lang");if(LANGS.indexOf(s)>-1)return s;var n=(navigator.language||"cs").slice(0,2).toLowerCase();return (n==="ru"||n==="uk"||n==="be")?"ru":(n==="en"?"en":"cs");}
  var lang=initialLang();
  function dict(){return window.I18N[lang];}
  function get(path){return path.split(".").reduce(function(o,k){return o==null?o:o[k];},dict());}
  function fmt(n){return new Intl.NumberFormat(lang==="en"?"en-GB":"cs-CZ").format(n)+" "+dict().cur;}
  function esc(s){return String(s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c];});}
  function artistById(id){for(var i=0;i<DATA.artists.length;i++)if(DATA.artists[i].id===id)return DATA.artists[i];return null;}

  var page=document.body.getAttribute("data-page");

  function header(){
    var t=dict(),links="";
    PAGES.forEach(function(p){links+='<a href="'+p[1]+'"'+(p[0]===page?' aria-current="page"':'')+'>'+t.nav[p[0]]+'</a>';});
    var langs=LANGS.map(function(l){return '<button type="button" data-lang="'+l+'" aria-pressed="'+(l===lang)+'">'+l.toUpperCase()+'</button>';}).join("");
    return '<header class="hdr"><div class="wrap hdr-in">'+
      '<a class="logo" href="index.html" aria-label="Dubai Tattoo">DUBAI TATTOO<i></i></a>'+
      '<nav class="nav" aria-label="Menu">'+links+'</nav>'+
      '<div class="hdr-tools"><div class="lang" role="group" aria-label="Language">'+langs+'</div>'+
      '<a class="btn small" href="rezervace.html">'+t.nav.book+'</a>'+
      '<button class="menu-btn" type="button" aria-expanded="false" aria-controls="mnav">'+t.nav.menu+'</button></div></div></header>'+
      '<div class="mnav" id="mnav" hidden><div class="wrap mnav-in">'+links+'<a href="rezervace.html" class="mnav-book">'+t.nav.book+' →</a><div class="lang mnav-lang" role="group" aria-label="Language">'+langs+'</div></div></div>';
  }
  function footer(){
    var t=dict(),f=t.ftr,links="";
    PAGES.concat([["book","rezervace.html"]]).forEach(function(p){links+='<a href="'+p[1]+'">'+t.nav[p[0]]+'</a>';});
    return '<footer class="ftr"><div class="wrap"><div class="ftr-word" aria-hidden="true">Dubai <em>Tattoo</em></div>'+
      '<div class="ftr-grid"><div><p>'+f.tag+'</p></div>'+
      '<div><h4>'+f.pages+'</h4>'+links+'</div>'+
      '<div><h4>'+f.follow+'</h4><a href="https://www.instagram.com/" target="_blank" rel="noopener">Instagram</a><a href="https://www.tiktok.com/" target="_blank" rel="noopener">TikTok</a></div>'+
      '<div><h4>'+f.visit+'</h4><p>'+f.address+'</p><p style="margin-top:8px"><span class="mono">'+f.hours_l+'</span><br>'+f.hours+'</p></div></div>'+
      '<div class="demo-note">'+f.demo+'</div><p class="mono" style="margin-top:22px;color:var(--ink-2)">'+f.rights+'</p></div></footer>';
  }

  function applyStatic(){
    document.documentElement.lang=lang;
    document.querySelectorAll("[data-i]").forEach(function(el){var v=get(el.getAttribute("data-i"));if(v!=null)el.innerHTML=v;});
    document.querySelectorAll("[data-i-ph]").forEach(function(el){var v=get(el.getAttribute("data-i-ph"));if(v!=null)el.setAttribute("placeholder",v);});
    document.querySelectorAll("[data-i-label]").forEach(function(el){var v=get(el.getAttribute("data-i-label"));if(v!=null)el.setAttribute("aria-label",v);});
  }
  function renderChrome(){
    var h=document.getElementById("hdr"),f=document.getElementById("ftr");
    if(h)h.innerHTML=header();
    if(f)f.innerHTML=footer();
    var mb=document.querySelector(".menu-btn"),mn=document.getElementById("mnav");
    if(mb&&mn)mb.addEventListener("click",function(){var open=mn.hidden;mn.hidden=!open;mb.setAttribute("aria-expanded",String(open));mb.textContent=open?dict().nav.close:dict().nav.menu;document.body.classList.toggle("menu-open",open);});
    document.querySelectorAll(".lang button").forEach(function(b){b.addEventListener("click",function(){setLang(b.getAttribute("data-lang"));});});
  }
  function render(){
    renderChrome();applyStatic();
    if(typeof window.renderPage==="function")window.renderPage(dict(),lang);
  }
  function setLang(l){if(LANGS.indexOf(l)<0||l===lang)return;lang=l;store("atrament-lang",l);render();}

  /* page wipe on internal navigation */
  var reduce=window.matchMedia&&matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.addEventListener("click",function(e){
    var a=e.target.closest&&e.target.closest("a[href]");
    if(!a||reduce||e.defaultPrevented||e.button!==0||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return;
    var href=a.getAttribute("href");
    if(a.target||!/^[a-z-]+\.html(#[\w-]+)?$/i.test(href))return;
    var here=location.pathname.split("/").pop()||"index.html";
    if(href.split("#")[0]===here)return;
    e.preventDefault();
    document.documentElement.classList.add("leaving");
    setTimeout(function(){location.href=href;},430);
  });
  window.addEventListener("pageshow",function(){document.documentElement.classList.remove("leaving");});

  /* cursor ring: a stencil circle that fills when over something clickable */
  if(window.matchMedia&&matchMedia("(pointer:fine)").matches&&!reduce){
    var ring=document.createElement("div");ring.className="ring";ring.setAttribute("aria-hidden","true");document.body.appendChild(ring);
    window.addEventListener("pointermove",function(e){ring.style.transform="translate("+e.clientX+"px,"+e.clientY+"px)";ring.classList.add("on");var hot=e.target.closest&&e.target.closest("a,button,.zone,.work,label,input,select,textarea,summary");ring.classList.toggle("hot",!!hot);},{passive:true});
    document.addEventListener("pointerleave",function(){ring.classList.remove("on");});
  }

  window.ATR={data:DATA,get:get,dict:dict,fmt:fmt,esc:esc,artist:artistById,lang:function(){return lang;},store:store};
  if(!document.querySelector(".wipe")){var w=document.createElement("div");w.className="wipe";w.setAttribute("aria-hidden","true");document.body.appendChild(w);}
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",render);else render();
})();
