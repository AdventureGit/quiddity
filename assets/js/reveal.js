(function () {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  if (!('IntersectionObserver' in window)) return;

  var els = document.querySelectorAll(
    '.entry, .note, .journal-entry, .figure, .photo-card, .influences li'
  );
  if (!els.length) return;

  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) {
        entry.target.classList.add('reveal-in');
        io.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12, rootMargin: '0px 0px -10% 0px' });

  els.forEach(function (el, i) {
    el.classList.add('reveal');
    el.style.transitionDelay = Math.min(i % 6, 5) * 0.06 + 's';
    io.observe(el);
  });
})();
