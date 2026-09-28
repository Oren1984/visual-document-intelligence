(function () {
  'use strict';
  var navbar = document.getElementById('navbar');
  var toggle = document.getElementById('navToggle');
  var links = document.getElementById('navLinks');
  if (navbar) {
    window.addEventListener('scroll', function () { navbar.classList.toggle('scrolled', window.scrollY > 40); }, { passive: true });
  }
  if (toggle && links) {
    toggle.addEventListener('click', function () {
      var open = links.classList.toggle('open');
      toggle.setAttribute('aria-expanded', String(open));
    });
    links.querySelectorAll('a').forEach(function (a) {
      a.addEventListener('click', function () { links.classList.remove('open'); toggle.setAttribute('aria-expanded', 'false'); });
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && links.classList.contains('open')) { links.classList.remove('open'); toggle.setAttribute('aria-expanded', 'false'); toggle.focus(); }
    });
  }
  // Highlight the nav link of the section in view
  var navAnchors = document.querySelectorAll('.nav-links a[href^="#"]');
  if ('IntersectionObserver' in window && navAnchors.length) {
    var byId = {};
    navAnchors.forEach(function (a) { byId[a.getAttribute('href').slice(1)] = a; });
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting && byId[en.target.id]) {
          navAnchors.forEach(function (a) { a.classList.remove('active'); });
          byId[en.target.id].classList.add('active');
        }
      });
    }, { rootMargin: '-45% 0px -50% 0px' });
    document.querySelectorAll('section[id]').forEach(function (s) { obs.observe(s); });
  }
})();
