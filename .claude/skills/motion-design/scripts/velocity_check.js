// Пример: скорость ленты по формуле сцены (подставь свои T и формулу y(t)). Запуск: node velocity_check.js
// проверка скорости ленты по формуле сцены: нет скачков скорости между кадрами
const T={outMsg:1.7,digest:2.45,scrollA:3.9,scrollB:5.5};const outH=39,digH=629,scrollMax=181;
const cl=x=>Math.min(1,Math.max(0,x)),prog=(t,a,d)=>cl((t-a)/d),eIO=p=>p<.5?4*p*p*p:1-Math.pow(-2*p+2,3)/2,glide=p=>{if(p<=0)return 0;if(p>=1)return 1;const f=x=>1-Math.exp(-10*x)*(1+10*x);return f(p)/f(1)};
const y=t=>{const pof=glide(prog(t,T.outMsg,.7)),pf=glide(prog(t,T.digest,1.4));return (1-pof)*outH+(1-pf)*digH+pf*scrollMax*(1-eIO(prog(t,T.scrollA,T.scrollB-T.scrollA)))};
let prev=null,maxJ=0,at=0;for(let i=1;i<432;i++){const v=(y(i/60)-y((i-1)/60))*1.92;if(prev!==null){const j=Math.abs(v-prev);if(j>maxJ){maxJ=j;at=i}}prev=v}
console.log('макс. скачок скорости между кадрами:',maxJ.toFixed(2),'px/кадр на кадре',at);
const v=i=>((y(i/60)-y((i-1)/60))*1.92).toFixed(2);
console.log('скорость (px/кадр), кадры 140-160:',[...Array(20)].map((_,k)=>v(140+k)).join(' '));
console.log('кадры 215-250 (стык толчка и свайпа):',[...Array(35)].map((_,k)=>v(215+k)).join(' '));
