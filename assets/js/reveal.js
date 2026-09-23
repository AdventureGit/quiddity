(function () {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  if (!('IntersectionObserver' in window)) return;

  function watch(selector, activeClass, setup, options) {
    var els = document.querySelectorAll(selector);
    if (!els.length) return;

    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add(activeClass);
          io.unobserve(entry.target);
        }
      });
    }, options);

    els.forEach(function (el, i) {
      setup(el, i);
      io.observe(el);
    });
  }

  watch('.entry, .note, .journal-entry, .figure, .photo-card, .influences li', 'reveal-in',
    function (el, i) {
      el.classList.add('reveal');
      el.style.transitionDelay = Math.min(i % 6, 5) * 0.06 + 's';
    },
    { threshold: 0.12, rootMargin: '0px 0px -10% 0px' }
  );

  watch('.section-icon', 'is-drawn',
    function (el) {
      el.classList.add('icon-ready');
      el.addEventListener('mouseenter', function () {
        el.classList.remove('is-drawn');
        void el.getBoundingClientRect(); // force style recalc so the animation restarts (offsetWidth is undefined on SVG)
        el.classList.add('is-drawn');
      });
    },
    { threshold: 0.4 }
  );
})();
