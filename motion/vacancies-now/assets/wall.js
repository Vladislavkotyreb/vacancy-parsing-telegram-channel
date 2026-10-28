const {chromium}=require('playwright');
(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:1206,height:2622}});
await p.goto('file://'+process.argv[2]);await p.waitForFunction(()=>document.title==='ready');await p.waitForTimeout(300);
await p.locator('#w').screenshot({path:process.argv[3]});await b.close()})();
