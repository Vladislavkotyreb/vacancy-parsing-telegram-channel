// Рендер превью: 2x с последующим уменьшением — сдвиги текста получаются субпиксельными, без дрожания
const {chromium}=require('playwright');
(async()=>{const fps=60, dur=12.6; const b=await chromium.launch();const p=await b.newPage({viewport:{width:1080,height:1350},deviceScaleFactor:2});
await p.goto('file://'+process.argv[2]); await p.waitForTimeout(300); await p.evaluate(()=>window.ready); /* прогрев: первый снимок после загрузки теряет слои с will-change */ for(const w of [0.5,3,6]){await p.evaluate(x=>render(x),w);await p.screenshot();}
for(let i=0;i<Math.round(fps*dur);i++){await p.evaluate(x=>render(x),i/fps);await p.screenshot({path:`frames/f${String(i).padStart(4,'0')}.png`});}
await b.close()})();
