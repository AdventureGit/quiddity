(function () {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  if (!window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;

  var el = document.createElement('div');
  el.className = 'cursor-spotlight';
  el.setAttribute('aria-hidden', 'true');
  document.body.appendChild(el);

  var pos = { x: 0, y: 0 };
  var ticking = false;
  var hideTimer = null;

  function apply() {
    el.style.setProperty('--mx', pos.x + 'px');
    el.style.setProperty('--my', pos.y + 'px');
    ticking = false;
  }

  document.addEventListener('mousemove', function (e) {
    pos.x = e.clientX;
    pos.y = e.clientY;
    el.classList.add('is-active');
    clearTimeout(hideTimer);
    hideTimer = setTimeout(function () { el.classList.remove('is-active'); }, 4000);
    if (!ticking) {
      ticking = true;
      requestAnimationFrame(apply);
    }
  }, { passive: true });

  document.addEventListener('mouseleave', function () {
    el.classList.remove('is-active');
  });
})();
