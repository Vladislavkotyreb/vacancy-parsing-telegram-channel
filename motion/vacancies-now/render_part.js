const {chromium}=require('playwright');
(async()=>{const [,,file,a,b]=process.argv; const br=await chromium.launch();const p=await br.newPage({viewport:{width:1080,height:1350},deviceScaleFactor:2});
await p.goto('file://'+file); await p.waitForTimeout(300); await p.evaluate(()=>window.ready); /* прогрев: первый снимок после загрузки теряет слои с will-change */ for(const w of [0.5,3,6]){await p.evaluate(x=>render(x),w);await p.screenshot();}
for(let i=+a;i<+b;i++){await p.evaluate(x=>render(x),i/60);await p.screenshot({path:`frames/f${String(i).padStart(4,'0')}.png`});}
await br.close(); console.log('PART_DONE',a,b)})();
