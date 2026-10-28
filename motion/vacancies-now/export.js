// Экспорт элементов экрана картинками (2x) + их координаты — для сборки в After Effects
const {chromium}=require('playwright'); const fs=require('fs');
(async()=>{const OUT=process.argv[3]; fs.mkdirSync(OUT,{recursive:true});
const b=await chromium.launch(); const p=await b.newPage({viewport:{width:1080,height:4200},deviceScaleFactor:2});
await p.goto('file://'+process.argv[2]); await p.waitForTimeout(300); await p.evaluate(()=>window.ready); /* прогрев */ await p.evaluate(()=>render(3)); await p.screenshot();
const meta=await p.evaluate(()=>{
  window.render(T.end);
  const $=id=>document.getElementById(id);
  $('frame').style.top='1500px'; $('frame').style.background='transparent'; document.body.style.background='transparent'; document.documentElement.style.background='transparent';
  $('feed').style.transform='none'; $('phone').style.transform='none'; for(const id of ['outRow','digestRow','searchBubble']){$(id).style.transform='none';$(id).style.opacity=1}
  const k=$('kNow'); k.style.transform='none'; k.style.boxShadow='0 1px 0 rgba(0,0,0,.28)'; k.style.background='#fff';
  for(const id of ['viewport','screen']) $(id).style.overflow='visible';
  $('screen').style.background='transparent';
  for(const id of ['wall','device','tap','headline','topfade','bottomfade']) $(id).style.display='none'; for(const g of document.querySelectorAll('.mag .glint,.mag .spark')) g.style.display='none';
  const feedRows=[...$('feed').children]; feedRows.forEach((el,i)=>{ if(!el.id) el.id='feedItem'+i });
  const sr=$('screen').getBoundingClientRect();
  const glass=[...document.querySelectorAll('.glass')].map(e=>{const r=e.getBoundingClientRect();return [r.left-sr.left,r.top-sr.top,r.width,r.height,parseFloat(getComputedStyle(e).borderTopLeftRadius)*SC]});
  const mags=[...document.querySelectorAll('.mag')].map(e=>{const r=e.getBoundingClientRect();return [r.left-sr.left,r.top-sr.top,r.width,r.height]});
  const pieces=[...feedRows.map(e=>e.id).filter(id=>id!=='searchRow'),'searchBubble','back','title','status','composer','kb','kNow','home'];
  return {SC, outH, digH, scrollMax, KX, KY, T, searchH, mags, glass, screen:{x:sr.left,y:sr.top,w:sr.width,h:sr.height}, pieces, feedIds:feedRows.map(e=>e.id).filter(id=>!['outRow','digestRow','searchRow'].includes(id)),
    avatar:(r=>({x:r.left-sr.left,y:r.top-sr.top,w:r.width,h:r.height}))($('avatar').getBoundingClientRect()),
    viewport:(r=>({h:r.height}))($('viewport').getBoundingClientRect())};
});
const all=['feed',...meta.pieces,'avatar','viewport','screen','status','header','composer','kb','home','kNow'];
meta.rects={};
for(const id of meta.pieces){
  await p.evaluate(({id,pieces})=>{
    // показываем только нужный элемент (и его родителей), остальное прячем
    for(const pid of pieces){const el=document.getElementById(pid);el.style.visibility=(pid===id)?'visible':'hidden'}
    const kb=document.getElementById('kb'); if(id==='kb'){kb.style.visibility='visible';document.getElementById('kNow').style.visibility='hidden'}
    if(id==='kNow'){kb.style.visibility='hidden';kb.style.background='transparent';document.getElementById('kNow').style.visibility='visible'} else kb.style.background='';
    document.getElementById('avatar').style.visibility='hidden';
  },{id,pieces:meta.pieces});
  const r=await p.evaluate(id=>{const sr=document.getElementById('screen').getBoundingClientRect();
    const el=document.getElementById(id); let r=el.getBoundingClientRect(); let pad=id==='kNow'?6:(id==='kb'?0:4);
    if(id==='status'){r={left:sr.left,top:sr.top,width:sr.width,height:r.height}}
    return {x:r.left-pad,y:r.top-pad,w:r.width+2*pad,h:r.height+2*pad,sx:sr.left,sy:sr.top}},id);
  await p.screenshot({path:`${OUT}/${id}.png`,clip:{x:r.x,y:r.y,width:r.w,height:r.h},omitBackground:true});
  meta.rects[id]={x:r.x-r.sx,y:r.y-r.sy,w:r.w,h:r.h};
}
fs.writeFileSync(`${OUT}/layout.json`,JSON.stringify(meta,null,1)); console.log(JSON.stringify(meta.rects,null,0)); await b.close()})();
