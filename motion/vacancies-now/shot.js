const {chromium}=require('playwright');
(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:1080,height:1350}});
await p.goto('file://'+process.argv[2]); await p.waitForTimeout(300); await p.evaluate(()=>window.ready); /* прогрев: первый снимок после загрузки теряет слои с will-change */ for(const w of [0.5,3,6]){await p.evaluate(x=>render(x),w);await p.screenshot();}
for(const t of process.argv.slice(3)){await p.evaluate(x=>render(+x),t);await p.screenshot({path:`${process.argv[2].replace('scene.html','')}s_${t}.png`});}
await b.close()})();
