// Имитация After Effects для прогона .jsx: ссылки на свойства устаревают после addProperty в том же слое (как в AE)
const fs=require('fs'), vm=require('vm');
const SCRIPT=process.argv[2], ASSETS_DIR=require('path').dirname(SCRIPT);
const exprs=[]; let errors=0;
function Prop(layer,name,depth){this.layer=layer;this.name=name;this.gen=layer.gen;this.kids={};this.depth=depth;this._v=null}
Prop.prototype.chk=function(){if(this.gen!==this.layer.gen)throw new Error('Недопустимый объект: '+this.name)};
Prop.prototype.property=function(n){this.chk();if(typeof n==='number'){const k=Object.keys(this.kids)[n-1];if(!k)throw new Error('нет свойства #'+n+' в '+this.name);return this.kids[k].fresh()}
  if(!this.kids[n])this.kids[n]=new Prop(this.layer,n,this.depth+1);return this.kids[n].fresh()};
Prop.prototype.fresh=function(){this.gen=this.layer.gen;return this};
Prop.prototype.addProperty=function(n){this.chk();this.layer.gen++;const key=n+'#'+Object.keys(this.kids).length;const p=new Prop(this.layer,n,this.depth+1);this.kids[key]=p;this.gen=this.layer.gen;return p};
Prop.prototype.setValue=function(v){this.chk();this._v=v};
Object.defineProperty(Prop.prototype,'value',{get(){this.chk();if(this.name==='ADBE Text Document')return new TextDocument();return this._v||[0,0]}});
Object.defineProperty(Prop.prototype,'expression',{set(e){this.chk();exprs.push({where:this.layer.name+' / '+this.name,e})},get(){return''}});
function TextDocument(){this.resetCharStyle=()=>{};this.resetParagraphStyle=()=>{}}
let layerId=0;
function Layer(name){this.name=name||'layer'+(++layerId);this.gen=0;this.root=new Prop(this,'root',0);this.parent=null;this.timeRemapEnabled=false;this.outPoint=0}
Layer.prototype.property=function(n){return this.root.fresh().property(n)};
Layer.prototype.sourceRectAtTime=function(){return{left:0,top:-12,width:120,height:20}};
Layer.prototype.moveBefore=function(){};
function Layers(){this.list=[]}
Layers.prototype._mk=function(n){const l=new Layer(n);this.list.push(l);return l};
Layers.prototype.addShape=function(){return this._mk()};
Layers.prototype.addText=function(t){return this._mk('text:'+t)};
Layers.prototype.addNull=function(){return this._mk('null')};
Layers.prototype.addSolid=function(c,n,w,h){if(!Array.isArray(c)||c.length!==3)throw new Error('addSolid: цвет должен быть [r,g,b]');return this._mk(n)};
Layers.prototype.add=function(item){if(!item)throw new Error('layers.add(undefined)');return this._mk(item.name)};
function Comp(n){this.name=n;this.layers=new Layers();this.openInViewer=()=>{}}
const project={items:{addFolder:n=>({name:n}),addComp:(n)=>new Comp(n)},
  importFile:o=>{if(!fs.existsSync(o.file.fsName))throw new Error('importFile: нет файла '+o.file.fsName);return{name:require('path').basename(o.file.fsName),duration:2.0667,frameDuration:1/30}}};
const ctx={app:{project,beginUndoGroup(){},endUndoGroup(){}},alert:m=>console.log('ALERT:',m),
  $:{fileName:SCRIPT},
  File:function(p){this.fsName=p;Object.defineProperty(this,'exists',{get:()=>fs.existsSync(p)});this.parent={fsName:require('path').dirname(p)}},
  Folder:function(p){this.fsName=p},
  ImportOptions:function(f){this.file=f},
  Shape:function(){},
  ParagraphJustification:{CENTER_JUSTIFY:1,LEFT_JUSTIFY:2},Math,console};
vm.createContext(ctx);
try{vm.runInContext(fs.readFileSync(SCRIPT,'utf8'),ctx,{filename:SCRIPT})}catch(e){errors++;console.log('SCRIPT ERROR:',e.message,e.stack.split('\n')[1])}
// прогон выражений на нескольких моментах времени
for(const {where,e} of exprs){for(const t of [0,0.9,1.2,2,4,6.95,8.4]){
  try{const f=new Function('time','value','add','thisLayer','return eval('+JSON.stringify(e)+')');
    const r=f(t,[100,100],(a,b)=>a.map((x,i)=>x+b[i]),{source:{duration:2.0667,frameDuration:1/30}});
    const bad=[].concat(r).some(x=>typeof x!=='number'||!isFinite(x));if(bad)throw new Error('нечисловой результат '+JSON.stringify(r))}
  catch(err){errors++;console.log('EXPR ERROR',where,'t='+t,err.message);break}}}
console.log('выражений:',exprs.length,'ошибок:',errors);
