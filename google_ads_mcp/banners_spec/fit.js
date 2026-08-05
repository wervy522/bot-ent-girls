/* Движок резиновости.
   320x480 в Google Ads — это ДЕКЛАРАЦИЯ ориентации, а не размер вьюпорта:
   реальный слот интерстишла почти всегда другой. Поэтому баннер верстается
   в фиксированной сетке DW x DH, а здесь масштабируется под фактический экран.

   Ключевое: масштаб берётся по ШИРИНЕ (не min по двум осям) — иначе по краям
   появляются мёртвые поля и креатив выглядит дёшево. Высота сцены тянется
   в пределах [DHMIN, DHMAX], под сценой лежит full-bleed фон #bleed. */
(function () {
  var stage = document.getElementById('stage');
  var bleed = document.getElementById('bleed');
  if (!stage) return;

  function clamp(lo, v, hi) { return Math.max(lo, Math.min(v, hi)); }

  function fit() {
    var vw = window.innerWidth || document.documentElement.clientWidth;
    var vh = window.innerHeight || document.documentElement.clientHeight;
    if (!vw || !vh) return;

    var s = vw / window.__DW;
    var dh = clamp(window.__DHMIN, vh / s, window.__DHMAX);

    stage.style.width = window.__DW + 'px';
    stage.style.height = dh + 'px';
    stage.style.transform = 'scale(' + s + ')';

    // сцена короче экрана — центрируем по вертикали, фон закрывает остаток
    var used = dh * s;
    stage.style.top = (vh > used ? (vh - used) / 2 : 0) + 'px';
    if (bleed) { bleed.style.width = vw + 'px'; bleed.style.height = vh + 'px'; }

    document.documentElement.style.setProperty('--stage-h', dh + 'px');
  }

  fit();
  window.addEventListener('resize', fit, false);
  window.addEventListener('orientationchange', fit, false);
  // слот иногда меняет размер уже после load
  setTimeout(fit, 60);
  setTimeout(fit, 300);
})();
