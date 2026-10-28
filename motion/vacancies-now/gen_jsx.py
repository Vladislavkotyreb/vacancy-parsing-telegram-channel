import json
m=json.load(open('ae_pack2/assets/ui/layout.json'))
R=m['rects']; T=m['T']; S=m['SC']
def r4(v): return round(v,3)
rects=",\n    ".join(f'"{k}": [{r4(v["x"])}, {r4(v["y"])}, {r4(v["w"])}, {r4(v["h"])}]' for k,v in R.items())
feed_ids=json.dumps(m['feedIds'])
K=0.48
JSX=r'''/*
  «🔎 Вакансии сейчас» — анонс в стиле Telegram-роликов Миши Наера (mishanaer.com).
  Запуск: Файл → Сценарии → Запустить файл сценария… → этот файл.
  Рядом со скриптом должна лежать папка assets — скрипт берёт картинки оттуда.

  Что строится (1080×1350, 60 fps, 12.6 с):
    • заголовок «Выводите новые вакансии когда удобно» — живой текст, редактируется;
    • мокап iPhone 17 из Figma (iOS 27 UI Kit), обои Telegram по умолчанию, аватар бота,
      капсулы Liquid Glass (iOS 26) без цветных подложек;
    • элементы чата — картинки из превью (эмодзи Apple, шрифт SF), поэтому выглядят 1:1;
    • телефон выезжает → блик на лупе → нажатие «🔎 Вакансии сейчас» → «Ищу новые вакансии…» (блики) →
      подборка → свайп вниз →
      лента наверх → телефон уезжает, заголовок гаснет. Первый и последний кадр — пустой фон:
      ролик зацикливается без шва.
  Тайминг — блок T ниже: поменяйте числа и перезапустите скрипт. Движение — выражения
  на слоях «⏱ …».
  Шрифт заголовка — FONT_HEADLINE (нужен SF Pro Display; без него AE подставит другой).
*/
(function () {
  var FONT_HEADLINE = "SFProDisplay-Bold";
  var HEADLINE = "Выводите новые\rвакансии когда удобно";

  // Тайминг, сек — синхронно с превью
  var T = __T__;

  var W = 1080, H = 1350, FPS = 60;   // 4:5 — Телеграм показывает в чате без обрезки
  var S = __S__;                       // pt iOS → px экрана
  var K = __K__;                       // масштаб мокапа (экспорт Figma 3x)
  var SCR_W = 579, SCR_H = 1259;       // экран в px
  var VIEW_H = 896;                    // лента до клавиатуры бота — уходит под поле ввода, как в Telegram, px
  var PHONE_CX = 540, PHONE_CY = __PCY__;
  // Элементы экрана: [x, y, w, h] в px экрана (картинки — 2x)
  var UI = {
    __RECTS__
  };
  var FEED_IDS = __FEED__;
  var AVATAR = __AVATAR__;
  var OUT_H = __OUTH__, DIG_H = __DIGH__, SCROLL_MAX = __SCROLL__, SEARCH_H = __SEARCHH__; // pt
  var KX = __KX__, KY = __KY__;        // центр кнопки, pt
  var GLASS = __GLASS__;                // капсулы Liquid Glass [x, y, w, h, радиус] px
  var MAGS = __MAGS__;                 // лупы 🔎 [x, y, w, h] px: 0 — в «Ищу…», 1 — на кнопке

  function rgb(hex, a) {
    var n = parseInt(hex.replace("#", ""), 16);
    return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255].concat(a === undefined ? [] : [a]);
  }
  function tr(l) { return l.property("ADBE Transform Group"); }

  app.beginUndoGroup("Vacancies Now — Telegram announce");
  var folder = app.project.items.addFolder("Vacancies Now announce");
  var ASSETS = new File($.fileName).parent.fsName + "/assets";
  function importAsset(name) {
    var f = new File(ASSETS + "/" + name);
    if (!f.exists) throw new Error("Не найден файл " + f.fsName + "\nПоложите папку assets рядом со скриптом.");
    var it = app.project.importFile(new ImportOptions(f));
    it.parentFolder = folder;
    return it;
  }
  // картинка элемента интерфейса на своём месте
  function uiLayer(comp, id, label) {
    var r = UI[id];
    var l = comp.layers.add(importAsset("ui/" + id + ".png"), T.end);
    l.name = label || id;
    tr(l).property("ADBE Scale").setValue([50, 50]);
    tr(l).property("ADBE Position").setValue([r[0] + r[2] / 2, r[1] + r[3] / 2]);
    return l;
  }
  function nullAt(comp, name, x, y) {
    var n = comp.layers.addNull(T.end);
    n.name = name;
    tr(n).property("ADBE Anchor Point").setValue([50, 50]);
    tr(n).property("ADBE Position").setValue([x, y]);
    return n;
  }
  function rectMask(layer, x0, y0, x1, y1, featherY) {
    var m = layer.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
    var sh = new Shape();
    sh.vertices = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]; sh.closed = true;
    m.property("ADBE Mask Shape").setValue(sh);
    if (featherY) m.property("ADBE Mask Feather").setValue([0, featherY]);
  }
  function roundMask(layer, w, h, R) {
    var m = layer.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
    var rs = new Shape(), k = 0.5523 * R;
    rs.vertices = [[R, 0], [w - R, 0], [w, R], [w, h - R], [w - R, h], [R, h], [0, h - R], [0, R]];
    rs.inTangents = [[-k, 0], [0, 0], [0, -k], [0, 0], [k, 0], [0, 0], [0, k], [0, 0]];
    rs.outTangents = [[0, 0], [k, 0], [0, 0], [0, k], [0, 0], [-k, 0], [0, 0], [0, -k]];
    rs.closed = true;
    m.property("ADBE Mask Shape").setValue(rs);
  }

  // Общие функции выражений — те же, что в превью
  var tKeys = [];
  for (var key in T) if (T.hasOwnProperty(key)) tKeys.push(key + ":" + T[key]);
  var LIB =
    "var T={" + tKeys.join(",") + "};\n" +
    "function cl(x,a,b){a=(a===undefined)?0:a;b=(b===undefined)?1:b;return Math.min(b,Math.max(a,x));}\n" +
    "function prog(t,a,d){return cl((t-a)/d);}\n" +
    "function eOut(p){return 1-Math.pow(1-p,3);}\n" +
    "function eIO(p){return p<.5?4*p*p*p:1-Math.pow(-2*p+2,3)/2;}\n" +
    "function spring(p){return p<=0?0:(p>=1?1:1-Math.exp(-8*p)*Math.cos(7*p));}\n" +
    "function glide(p){if(p<=0)return 0;if(p>=1)return 1;function f(x){return 1-Math.exp(-10*x)*(1+10*x);}return f(p)/f(1);}\n";

  // ---------- Блик на лупе 🔎: полоса света по стеклу + искра на ободке ----------
  // Стекло — круг радиусом 27% ширины эмодзи с центром в (64%, 34%), как в превью.
  function lensGlint(comp, mag, keys, parentLayer, fadeExpr, label) {
    var x = mag[0], y = mag[1], w = mag[2], h = mag[3];
    var times = [];
    for (var k = 0; k < keys.length; k++) times.push("T." + keys[k]);
    var SWEEP = LIB + "var L=[" + times.join(",") + "],x=-1.5,sp=0;" +
      "for(var i=0;i<L.length;i++){var p=prog(time,L[i],0.55);if(p>0&&p<1)x=-1.2+eIO(p)*3.6;" +
      "sp=Math.max(sp,Math.sin(Math.PI*prog(time,L[i]+0.2,0.55)));}";
    var gc = app.project.items.addComp("Lens glint — " + label, Math.ceil(w), Math.ceil(h), 1, T.end, FPS);
    gc.parentFolder = folder;
    var bands = [["#78AAEB", 0.34, 0.12, 45], ["#FFFFFF", 0.16, 0.06, 100]]; // голубая кайма и белая сердцевина
    for (var b = 0; b < bands.length; b++) {
      var bw = Math.ceil(w * bands[b][1]), bh = Math.ceil(h * 2.2);
      var band = gc.layers.addSolid(rgb(bands[b][0]), "⏱ Band " + (b + 1), bw, bh, 1, T.end);
      rectMask(band, 0, 0, bw, bh, 0);
      band.property("ADBE Mask Parade").property(1).property("ADBE Mask Feather").setValue([w * bands[b][2], 0]);
      tr(band).property("ADBE Rotate Z").setValue(25);
      tr(band).property("ADBE Opacity").setValue(bands[b][3]);
      tr(band).property("ADBE Position").expression = SWEEP + "[" + (w * 0.17) + "+x*" + (w * 0.34) + "," + (h * 0.5) + "];";
    }
    var gl = comp.layers.add(gc);
    gl.name = "⏱ Glint — " + label;
    tr(gl).property("ADBE Position").setValue([x + w / 2, y + h / 2]);
    var gm = gl.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
    var cs = new Shape(), cr = w * 0.27, ck = 0.5523 * cr, ccx = w * 0.64, ccy = h * 0.34;
    cs.vertices = [[ccx, ccy - cr], [ccx + cr, ccy], [ccx, ccy + cr], [ccx - cr, ccy]];
    cs.inTangents = [[-ck, 0], [0, -ck], [ck, 0], [0, ck]];
    cs.outTangents = [[ck, 0], [0, ck], [-ck, 0], [0, -ck]];
    cs.closed = true;
    gm.property("ADBE Mask Shape").setValue(cs);
    tr(gl).property("ADBE Opacity").expression = LIB + "100*(" + fadeExpr + ");";

    var sp = comp.layers.addShape(); sp.name = "⏱ Sparkle — " + label;
    var sg = sp.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group").property("ADBE Vectors Group");
    sg.addProperty("ADBE Vector Shape - Star");
    sg.addProperty("ADBE Vector Graphic - Fill");
    var star = sg.property(1), fill = sg.property(2);
    star.property("ADBE Vector Star Type").setValue(1);
    star.property("ADBE Vector Star Points").setValue(4);
    star.property("ADBE Vector Star Outer Radius").setValue(w * 0.42);
    star.property("ADBE Vector Star Inner Radius").setValue(w * 0.07);
    fill.property("ADBE Vector Fill Color").setValue(rgb("#FFFFFF"));
    tr(sp).property("ADBE Position").setValue([x + w * 0.56, y + h * 0.16]);
    var glow = sp.property("ADBE Effect Parade").addProperty("ADBE Drop Shadow");
    glow = sp.property("ADBE Effect Parade").property(1);
    glow.property("ADBE Drop Shadow-0001").setValue(rgb("#96C8FF", 1));
    glow.property("ADBE Drop Shadow-0002").setValue(0.95 * 255);
    glow.property("ADBE Drop Shadow-0004").setValue(0);
    glow.property("ADBE Drop Shadow-0005").setValue(5);
    tr(sp).property("ADBE Scale").expression = SWEEP + "var s=20+80*sp;[s,s];";
    tr(sp).property("ADBE Rotate Z").expression = SWEEP + "sp*60;";
    tr(sp).property("ADBE Opacity").expression = SWEEP + "100*sp*(" + fadeExpr + ");";
    gl.parent = parentLayer; sp.parent = parentLayer;
  }

  // ---------- Лента (прекомп, обрезана по полю ввода) ----------
  var feedComp = app.project.items.addComp("Feed — сообщения", SCR_W, VIEW_H, 1, T.end, FPS);
  feedComp.parentFolder = folder;
  var feed = nullAt(feedComp, "⏱ Feed (сдвиг ленты)", 0, 0);
  feed.property("ADBE Transform Group").property("ADBE Position").expression = LIB +
    "var S=" + S + ",outH=" + OUT_H + ",digH=" + DIG_H + ",scrollMax=" + SCROLL_MAX + ";\n" +
    "var t=time, pof=glide(prog(t,T.outMsg,0.7)), pf=glide(prog(t,T.digest,1.4));\n" +
    "var top=scrollMax*(1-eIO(prog(t,T.scrollA,T.scrollB-T.scrollA))+eIO(prog(t,T.upA,T.upB-T.upA)));\n" +
    "add(value,[0,((1-pof)*outH+(1-pf)*digH+pf*top)*S]);";
  // всё, что выше «Ищу…», поднимается, пока «Ищу…» на экране, и опускается, когда его удаляют
  var above = nullAt(feedComp, "⏱ Above «Ищу…»", 0, 0);
  above.parent = feed;
  var SEARCH_VIS = "var sv=glide(prog(time,T.search,0.7))-glide(prog(time,T.digest,1.4));";
  tr(above).property("ADBE Position").expression = LIB + SEARCH_VIS + "add(value,[0,-" + SEARCH_H + "*sv*" + S + "]);";
  var i, l;
  for (i = 0; i < FEED_IDS.length; i++) { l = uiLayer(feedComp, FEED_IDS[i], "History " + (i + 1)); l.parent = above; }

  // исходящее «🔎 Вакансии сейчас»: пружина от правого нижнего угла
  var ro = UI.outRow;
  var outNull = nullAt(feedComp, "⏱ Out message", ro[0] + ro[2] - 4, ro[1] + ro[3] - 4);
  outNull.parent = above;
  var outL = uiLayer(feedComp, "outRow", "Out message «Вакансии сейчас»"); outL.parent = outNull;
  tr(outNull).property("ADBE Position").expression = LIB + "var p=spring(prog(time,T.outMsg,0.6)); add(value,[0,(1-p)*22*" + S + "]);";
  tr(outNull).property("ADBE Scale").expression = LIB + "var p=spring(prog(time,T.outMsg,0.6)); var s=95+5*p; [s,s];";
  tr(outL).property("ADBE Opacity").expression = LIB + "100*prog(time,T.outMsg,0.15);";

  // «Ищу новые вакансии…»: приходит как входящее, удаляется вместе с приходом подборки
  var rsb = UI.searchBubble;
  var searchNull = nullAt(feedComp, "⏱ Searching message", rsb[0] + 4, rsb[1] + rsb[3] - 4);
  searchNull.parent = feed;
  var searchL = uiLayer(feedComp, "searchBubble", "«Ищу новые вакансии…»"); searchL.parent = searchNull;
  tr(searchNull).property("ADBE Position").expression = LIB + "var p=spring(prog(time,T.search,0.6)); add(value,[0,(1-p)*22*" + S + "]);";
  tr(searchNull).property("ADBE Scale").expression = LIB + "var p=spring(prog(time,T.search,0.6)); var s=95+5*p; [s,s];";
  tr(searchL).property("ADBE Opacity").expression = LIB + "100*prog(time,T.search,0.15)*(1-prog(time,T.digest-0.05,0.2));";
  lensGlint(feedComp, MAGS[0], ["glintA", "glintB"], searchNull, "prog(time,T.search,0.15)*(1-prog(time,T.digest-0.05,0.2))", "Ищу");

  // подборка: пружина от левого нижнего угла
  var rd = UI.digestRow;
  var digNull = nullAt(feedComp, "⏱ Digest", rd[0] + 4, rd[1] + rd[3] - 4);
  digNull.parent = feed;
  var digL = uiLayer(feedComp, "digestRow", "Digest — подборка"); digL.parent = digNull;
  tr(digNull).property("ADBE Position").expression = LIB + "var p=spring(prog(time,T.digest,0.7)); add(value,[0,(1-p)*30*" + S + "]);";
  tr(digNull).property("ADBE Scale").expression = LIB + "var p=spring(prog(time,T.digest,0.7)); var s=97+3*p; [s,s];";
  tr(digL).property("ADBE Opacity").expression = LIB + "100*prog(time,T.digest,0.18);";

  // ---------- Экран телефона (прекомп) ----------
  var scr = app.project.items.addComp("Screen — Telegram chat", SCR_W, SCR_H, 1, T.end, FPS);
  scr.parentFolder = folder;
  scr.bgColor = rgb("#FFFFFF");

  // обои Telegram по умолчанию (градиент #DBDDBB/#6BA587/#D5D88D/#88B884 + узор 50%)
  var wall = scr.layers.add(importAsset("tg_wallpaper.png"), T.end);
  wall.name = "Wallpaper — Telegram default";
  tr(wall).property("ADBE Scale").setValue([SCR_W / 1206 * 100, SCR_H / 2622 * 100]);
  tr(wall).property("ADBE Position").setValue([SCR_W / 2, SCR_H / 2]);

  var feedLayer = scr.layers.add(feedComp);
  feedLayer.name = "Feed";
  tr(feedLayer).property("ADBE Position").setValue([SCR_W / 2, VIEW_H / 2]);

  // край ленты под шапкой — только мягкое размытие (scroll edge effect iOS 26) и лёгкая светлая дымка под часами
  var FH = Math.round(118 * S);
  var blur = scr.layers.addSolid(rgb("#FFFFFF"), "Header edge blur", SCR_W, FH, 1, T.end);
  blur.adjustmentLayer = true;
  tr(blur).property("ADBE Position").setValue([SCR_W / 2, FH / 2]);
  blur.property("ADBE Effect Parade").addProperty("ADBE Gaussian Blur 2").property("ADBE Gaussian Blur 2-0001").setValue(14);
  rectMask(blur, -50, -50, SCR_W + 50, FH * 0.45, FH * 0.55);
  var haze = scr.layers.addSolid(rgb("#FFFFFF"), "Header haze", SCR_W, FH, 1, T.end);
  tr(haze).property("ADBE Position").setValue([SCR_W / 2, FH / 2]);
  tr(haze).property("ADBE Opacity").setValue(28);
  rectMask(haze, -50, -50, SCR_W + 50, FH * 0.3, FH * 0.7);

  // Liquid Glass: под каждой капсулой (назад, заголовок, скрепка, поле ввода, микрофон) — размытая лента;
  // сама капсула (полупрозрачная заливка, блик по краю, тень) — картинка поверх
  var glassBlur = scr.layers.addSolid(rgb("#FFFFFF"), "Glass blur (под капсулами)", SCR_W, SCR_H, 1, T.end);
  glassBlur.adjustmentLayer = true;
  tr(glassBlur).property("ADBE Position").setValue([SCR_W / 2, SCR_H / 2]);
  for (var gi = 0; gi < GLASS.length; gi++) {
    var gr = GLASS[gi], gm2 = glassBlur.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
    var gx = gr[0], gy = gr[1], gw = gr[2], gh = gr[3], R = Math.min(gr[4], gh / 2, gw / 2), kk = 0.5523 * R;
    var shp = new Shape();
    shp.vertices = [[gx + R, gy], [gx + gw - R, gy], [gx + gw, gy + R], [gx + gw, gy + gh - R], [gx + gw - R, gy + gh], [gx + R, gy + gh], [gx, gy + gh - R], [gx, gy + R]];
    shp.inTangents = [[-kk, 0], [0, 0], [0, -kk], [0, 0], [kk, 0], [0, 0], [0, kk], [0, 0]];
    shp.outTangents = [[0, 0], [kk, 0], [0, 0], [0, kk], [0, 0], [-kk, 0], [0, 0], [0, -kk]];
    shp.closed = true;
    glassBlur.property("ADBE Mask Parade").property(gi + 1).property("ADBE Mask Shape").setValue(shp);
  }
  glassBlur.property("ADBE Effect Parade").addProperty("ADBE Gaussian Blur 2").property("ADBE Gaussian Blur 2-0001").setValue(9);

  uiLayer(scr, "status", "Status bar");
  uiLayer(scr, "back", "Back");
  uiLayer(scr, "title", "Title — IT vacancies daily");

  // аватар бота — анимация с сайта (96×96, 30 fps), зациклена, круглая маска
  var ava = scr.layers.add(importAsset("bot_avatar.mp4"));
  ava.name = "Bot avatar (loop)";
  ava.timeRemapEnabled = true;
  ava.property("ADBE Time Remapping").expression = "var d=thisLayer.source.duration-thisLayer.source.frameDuration; time%d;";
  ava.outPoint = T.end;
  var avaScale = AVATAR[2] / 96 * 106;
  tr(ava).property("ADBE Scale").setValue([avaScale, avaScale]);
  tr(ava).property("ADBE Position").setValue([AVATAR[0] + AVATAR[2] / 2, AVATAR[1] + AVATAR[3] / 2]);
  var am = ava.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
  var ac = new Shape(), ar = 48 / 1.06, ak = 0.5523 * ar;
  ac.vertices = [[48, 48 - ar], [48 + ar, 48], [48, 48 + ar], [48 - ar, 48]];
  ac.inTangents = [[-ak, 0], [0, -ak], [ak, 0], [0, ak]];
  ac.outTangents = [[ak, 0], [0, ak], [-ak, 0], [0, -ak]];
  ac.closed = true;
  am.property("ADBE Mask Shape").setValue(ac);

  // край ленты над полем ввода — мягкое размытие без подложки
  var BF_TOP = Math.round((874 - 252 - 70) * S), BF_H = Math.round(70 * S);
  var bblur = scr.layers.addSolid(rgb("#FFFFFF"), "Composer edge blur", SCR_W, BF_H, 1, T.end);
  bblur.adjustmentLayer = true;
  tr(bblur).property("ADBE Position").setValue([SCR_W / 2, BF_TOP + BF_H / 2]);
  bblur.property("ADBE Effect Parade").addProperty("ADBE Gaussian Blur 2").property("ADBE Gaussian Blur 2-0001").setValue(14);
  rectMask(bblur, -50, BF_H * 0.55, SCR_W + 50, BF_H + 50, BF_H * 0.55);

  uiLayer(scr, "composer", "Composer");
  uiLayer(scr, "kb", "Bot keyboard");

  // кнопка «🔎 Вакансии сейчас»: приподнимается, пока нажата, и пружиной возвращается
  var key = uiLayer(scr, "kNow", "Key — Вакансии сейчас");
  var PRESS = LIB + "var d=eOut(prog(time,T.pressDown,0.18)),u=spring(prog(time,T.pressUp,0.55));var k=d*(1-u);";
  tr(key).property("ADBE Scale").expression = PRESS + "var s=50*(1+0.045*k);[s,s];";
  var sh = key.property("ADBE Effect Parade").addProperty("ADBE Drop Shadow");
  sh = key.property("ADBE Effect Parade").property(1);
  sh.property("ADBE Drop Shadow-0001").setValue([0, 0, 0, 1]);
  sh.property("ADBE Drop Shadow-0003").setValue(180);
  sh.property("ADBE Drop Shadow-0002").expression = PRESS + "0.18*255*k;";
  sh.property("ADBE Drop Shadow-0004").expression = PRESS + "10*k*" + S * 2 + ";";   // слой в 50%, поэтому ×2
  sh.property("ADBE Drop Shadow-0005").expression = PRESS + "24*k*" + S * 2 + ";";
  lensGlint(scr, MAGS[1], ["btnGlint"], key, "1", "кнопка");

  uiLayer(scr, "home", "Home indicator");

  // кольцо-касание: опускается на кнопку, держится, пока палец нажат, гаснет после отпускания
  var ring = scr.layers.addShape(); ring.name = "⏱ Tap ring";
  var g = ring.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group").property("ADBE Vectors Group");
  g.addProperty("ADBE Vector Shape - Ellipse");
  g.addProperty("ADBE Vector Graphic - Stroke");
  // после addProperty старые ссылки в группе недействительны — берём заново по индексу
  var el = g.property(1), st = g.property(2);
  st.property("ADBE Vector Stroke Color").setValue(rgb("#96CDF5"));
  var RING = LIB + "var pr=eOut(prog(time,T.pressDown-0.14,0.34)),on=prog(time,T.pressDown-0.14,0.1),off=eOut(prog(time,T.pressUp,0.35));" +
    "var r=58-26*pr,w=17-5*pr;";
  el = ring.property("ADBE Root Vectors Group").property(1).property("ADBE Vectors Group").property(1);
  st = ring.property("ADBE Root Vectors Group").property(1).property("ADBE Vectors Group").property(2);
  el.property("ADBE Vector Ellipse Size").expression = RING + "var d=(2*r-w)*" + S + ";[d,d];";
  st.property("ADBE Vector Stroke Width").expression = RING + "w*" + S + ";";
  st.property("ADBE Vector Stroke Opacity").expression = RING + "70*on*(1-off);";
  tr(ring).property("ADBE Position").setValue([KX * S, KY * S]);

  // ---------- Главная композиция ----------
  var main = app.project.items.addComp("Vacancies Now — Telegram announce", W, H, 1, T.end, FPS);
  main.parentFolder = folder;
  var bg = main.layers.addSolid(rgb("#AACC7C"), "Background", W, H, 1, T.end);
  var r2 = bg.property("ADBE Effect Parade").addProperty("ADBE Ramp");
  r2.property("ADBE Ramp-0001").setValue([W / 2, 0]); r2.property("ADBE Ramp-0002").setValue(rgb("#C9D172"));
  r2.property("ADBE Ramp-0003").setValue([W / 2, H]); r2.property("ADBE Ramp-0004").setValue(rgb("#86C281"));

  // телефон целиком (экран + рамка) ездит на этом нуле: выезжает снизу и уезжает вниз
  var phoneNull = main.layers.addNull(T.end);
  phoneNull.name = "⏱ Phone (въезд и уезд)";
  tr(phoneNull).property("ADBE Anchor Point").setValue([50, 50]);
  tr(phoneNull).property("ADBE Position").setValue([PHONE_CX, PHONE_CY]);
  tr(phoneNull).property("ADBE Position").expression = LIB +
    "var pin=1-Math.pow(1-prog(time,T.phoneIn,1.0),5), pout=eIO(prog(time,T.phoneOut,0.8));\n" +
    "add(value,[0,((1-pin)+pout)*1200]);";

  var screenLayer = main.layers.add(scr);
  screenLayer.name = "Screen";
  tr(screenLayer).property("ADBE Position").setValue([PHONE_CX, PHONE_CY]);
  roundMask(screenLayer, SCR_W, SCR_H, Math.round(190 * K));

  // мокап iPhone 17 из Figma (iOS 27 UI Kit): рамка с прозрачным экраном и Dynamic Island
  var phone = main.layers.add(importAsset("iphone17_frame.png"), T.end);
  phone.name = "iPhone 17 — Figma mockup";
  tr(phone).property("ADBE Scale").setValue([K * 100, K * 100]);
  tr(phone).property("ADBE Position").setValue([PHONE_CX, PHONE_CY]);
  screenLayer.parent = phoneNull; phone.parent = phoneNull;
  var psh = phone.property("ADBE Effect Parade").addProperty("ADBE Drop Shadow");
  psh.property("ADBE Drop Shadow-0001").setValue(rgb("#284614", 1));
  psh.property("ADBE Drop Shadow-0002").setValue(0.28 * 255);
  psh.property("ADBE Drop Shadow-0003").setValue(180);
  psh.property("ADBE Drop Shadow-0004").setValue(40 / K);
  psh.property("ADBE Drop Shadow-0005").setValue(120 / K);

  // заголовок — живой текст
  var hl = main.layers.addText(HEADLINE);
  hl.name = "Headline";
  var tp = hl.property("ADBE Text Properties").property("ADBE Text Document");
  var d = tp.value;
  d.resetCharStyle(); d.resetParagraphStyle();
  d.font = FONT_HEADLINE; d.fontSize = 64; d.fillColor = rgb("#1E2B12"); d.applyFill = true; d.applyStroke = false;
  d.autoLeading = false; d.leading = 70; d.tracking = -28;
  d.justification = ParagraphJustification.CENTER_JUSTIFY;
  tp.setValue(d);
  var hr = hl.sourceRectAtTime(0, false);
  tr(hl).property("ADBE Anchor Point").setValue([hr.left + hr.width / 2, hr.top + hr.height / 2]);
  tr(hl).property("ADBE Position").setValue([540, 132]);
  tr(hl).property("ADBE Opacity").expression = LIB + "100*eOut(prog(time,T.headIn,0.8))*(1-eIO(prog(time,T.headOut,0.6)));";
  tr(hl).property("ADBE Position").expression = LIB + "var p=eOut(prog(time,T.headIn,0.8)); add(value,[0,(1-p)*28]);";

  main.openInViewer();
  app.endUndoGroup();
  alert("Готово: «Vacancies Now — Telegram announce», 1080×1350, 60 fps, 12.6 с.\n" +
        "Заголовок — слой Headline (двойной клик по тексту). Тайминг — блок T в начале скрипта.");
})();
'''
JSX=(JSX.replace('__T__',json.dumps(T)).replace('__S__',str(S)).replace('__K__',str(K))
 .replace('__PCY__',str(round(260+2760*K/2,2))).replace('__RECTS__',rects).replace('__FEED__',feed_ids)
 .replace('__AVATAR__',json.dumps([r4(m['avatar'][k]) for k in 'xywh'])).replace('__OUTH__',str(r4(m['outH'])))
 .replace('__DIGH__',str(r4(m['digH']))).replace('__SEARCHH__',str(r4(m['searchH']))).replace('__SCROLL__',str(r4(m['scrollMax']))).replace('__KX__',str(r4(m['KX']))).replace('__GLASS__',json.dumps([[r4(v) for v in r] for r in m['glass']])).replace('__MAGS__',json.dumps([[r4(v) for v in r] for r in m['mags']])).replace('__KY__',str(r4(m['KY']))))
open('ae_pack2/VacanciesNow_TelegramAnnounce.jsx','w',encoding='utf-8').write(JSX)
