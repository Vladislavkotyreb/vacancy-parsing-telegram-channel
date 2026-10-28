// Рендер превью: 2x с последующим уменьшением — сдвиги текста получаются субпиксельными, без дрожания
const {chromium}=require('playwright');
(async()=>{const fps=60, dur=8.6; const b=await chromium.launch();const p=await b.newPage({viewport:{width:1080,height:1920},deviceScaleFactor:2});
await p.goto('file://'+process.argv[2]); await p.waitForTimeout(300); await p.evaluate(()=>window.ready);
for(let i=0;i<Math.round(fps*dur);i++){await p.evaluate(x=>render(x),i/fps);await p.screenshot({path:`frames/f${String(i).padStart(4,'0')}.png`});}
await b.close()})();
