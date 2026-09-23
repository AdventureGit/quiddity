(function () {
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  document.querySelectorAll('[data-carousel]').forEach(function (root) {
    var slides = root.querySelectorAll('.carousel-slide');
    var dots = root.querySelectorAll('.carousel-dot');
    if (slides.length < 2) return;

    var index = 0;

    function show(i) {
      slides[index].classList.remove('is-active');
      if (dots[index]) dots[index].classList.remove('is-active');
      index = (i + slides.length) % slides.length;
      slides[index].classList.add('is-active');
      if (dots[index]) dots[index].classList.add('is-active');
    }

    var prev = root.querySelector('.carousel-prev');
    var next = root.querySelector('.carousel-next');
    if (prev) prev.addEventListener('click', function () { stop(); show(index - 1); });
    if (next) next.addEventListener('click', function () { stop(); show(index + 1); });
    dots.forEach(function (dot, i) {
      dot.addEventListener('click', function () { stop(); show(i); });
    });

    var timer = null;
    function start() {
      if (reduceMotion) return;
      stop();
      timer = setInterval(function () { show(index + 1); }, 6000);
    }
    function stop() {
      if (timer) clearInterval(timer);
      timer = null;
    }

    root.addEventListener('mouseenter', stop);
    root.addEventListener('mouseleave', start);
    root.addEventListener('focusin', stop);
    root.addEventListener('focusout', start);

    start();
  });
})();
