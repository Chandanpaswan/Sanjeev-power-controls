/* ==========================================================================
   Sanjeev Power Controls — public site interactions
   Vanilla JavaScript only. Progressive enhancement: every page works
   without this file except the mobile menu and reveal animations.
   ========================================================================== */
(function () {
  'use strict';

  var $ = function (selector, scope) {
    return (scope || document).querySelector(selector);
  };
  var $$ = function (selector, scope) {
    return Array.prototype.slice.call((scope || document).querySelectorAll(selector));
  };
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function scrollLock(on) {
    document.body.classList.toggle('is-locked', !!on);
  }

  /* ------------------------------------------------------------------ */
  /* Header scroll state                                                */
  /* ------------------------------------------------------------------ */
  function initHeaderScroll() {
    var header = $('.site-header');
    if (!header) return;

    var lastState = null;
    function onScroll() {
      var scrolled = window.scrollY > 8;
      if (scrolled !== lastState) {
        header.classList.toggle('is-scrolled', scrolled);
        lastState = scrolled;
      }
    }
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
  }

  /* ------------------------------------------------------------------ */
  /* Mobile navigation                                                  */
  /* ------------------------------------------------------------------ */
  function initMobileNav() {
    var toggle = $('[data-menu-toggle]');
    var nav = $('#primary-nav');
    var overlay = $('[data-nav-overlay]');
    if (!toggle || !nav) return;

    var mq = window.matchMedia('(max-width: 1200px)');

    function focusables() {
      return $$('a[href], button:not([disabled]), input, select, textarea', nav)
        .filter(function (el) { return el.offsetParent !== null; });
    }

    function openNav() {
      nav.classList.add('is-open');
      if (overlay) overlay.classList.add('is-visible');
      toggle.setAttribute('aria-expanded', 'true');
      toggle.setAttribute('aria-label', 'Close navigation menu');
      scrollLock(true);
      var items = focusables();
      if (items.length) items[0].focus();
    }

    function closeNav(returnFocus) {
      if (!nav.classList.contains('is-open')) return;
      nav.classList.remove('is-open');
      if (overlay) overlay.classList.remove('is-visible');
      toggle.setAttribute('aria-expanded', 'false');
      toggle.setAttribute('aria-label', 'Open navigation menu');
      scrollLock(false);
      if (returnFocus !== false) toggle.focus();
    }

    toggle.addEventListener('click', function () {
      if (nav.classList.contains('is-open')) {
        closeNav();
      } else {
        openNav();
      }
    });

    if (overlay) overlay.addEventListener('click', function () { closeNav(); });

    $$('a', nav).forEach(function (link) {
      if (link.hasAttribute('data-account-toggle')) return;
      link.addEventListener('click', function () { closeNav(false); });
    });

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') closeNav();
      if (event.key !== 'Tab' || !nav.classList.contains('is-open')) return;
      var items = focusables();
      if (!items.length) return;
      var first = items[0];
      var last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });

    function onChange() {
      if (!mq.matches) closeNav(false);
    }
    if (mq.addEventListener) {
      mq.addEventListener('change', onChange);
    } else if (mq.addListener) {
      mq.addListener(onChange);
    }
  }

  /* ------------------------------------------------------------------ */
  /* Account dropdown                                                   */
  /* ------------------------------------------------------------------ */
  function initAccountDropdown() {
    var wrap = $('[data-account-dropdown]');
    var toggle = $('[data-account-toggle]');
    var menu = $('[data-account-menu]');
    if (!wrap || !toggle || !menu) return;

    function close() {
      wrap.classList.remove('is-open');
      menu.classList.remove('is-open');
      toggle.setAttribute('aria-expanded', 'false');
    }

    toggle.addEventListener('click', function (event) {
      event.preventDefault();
      var open = menu.classList.toggle('is-open');
      wrap.classList.toggle('is-open', open);
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });

    document.addEventListener('click', function (event) {
      if (!wrap.contains(event.target)) close();
    });

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') close();
    });

    $$('a, button', menu).forEach(function (el) {
      el.addEventListener('click', close);
    });
  }

  /* ------------------------------------------------------------------ */
  /* Demonstration notice                                               */
  /* ------------------------------------------------------------------ */
  var DEMO_KEY = 'spc-demo-bar-dismissed';

  function initDemoBar() {
    var bar = $('[data-demo-bar]');
    if (!bar) return;

    var dismissed = false;
    try {
      dismissed = window.localStorage.getItem(DEMO_KEY) === '1';
    } catch (error) {
      dismissed = false;
    }

    if (dismissed) {
      bar.remove();
      return;
    }

    var close = $('[data-demo-close]', bar);
    if (!close) return;
    close.addEventListener('click', function () {
      try {
        window.localStorage.setItem(DEMO_KEY, '1');
      } catch (error) {
        /* storage may be unavailable in private mode */
      }
      bar.classList.add('is-hiding');
      window.setTimeout(function () { bar.remove(); }, 220);
    });
  }

  /* ------------------------------------------------------------------ */
  /* Reveal on scroll                                                   */
  /* ------------------------------------------------------------------ */
  function initReveal() {
    var items = $$('[data-reveal]');
    if (!items.length) return;

    if (reduceMotion || !('IntersectionObserver' in window)) {
      items.forEach(function (item) { item.classList.add('is-visible'); });
      return;
    }

    items.forEach(function (item) {
      var delay = item.getAttribute('data-reveal-delay');
      if (delay) item.style.transitionDelay = (parseInt(delay, 10) * 80) + 'ms';
    });

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });

    items.forEach(function (item) { observer.observe(item); });
  }

  /* ------------------------------------------------------------------ */
  /* Back to top                                                        */
  /* ------------------------------------------------------------------ */
  function initBackToTop() {
    var button = $('.to-top');
    if (!button) return;

    var lastState = null;
    function onScroll() {
      var show = window.scrollY > 520;
      if (show !== lastState) {
        button.classList.toggle('is-visible', show);
        lastState = show;
      }
    }
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    button.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: reduceMotion ? 'auto' : 'smooth' });
    });
  }

  /* ------------------------------------------------------------------ */
  /* Floating WhatsApp button                                            */
  /* ------------------------------------------------------------------ */
  function initWhatsAppFloat() {
    var button = $('.whatsapp-float');
    var footer = $('.site-footer');
    if (!button || !footer) return;

    // Tuck the fixed button away while the footer is on screen so it never
    // covers contact details or legal links.
    if ('IntersectionObserver' in window) {
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          button.classList.toggle('is-hidden', entry.isIntersecting);
        });
      }, { rootMargin: '0px 0px -24px 0px', threshold: 0.01 });
      observer.observe(footer);
      return;
    }

    var lastState = null;
    function onScroll() {
      var rect = footer.getBoundingClientRect();
      var hide = rect.top < window.innerHeight - 24;
      if (hide !== lastState) {
        button.classList.toggle('is-hidden', hide);
        lastState = hide;
      }
    }
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
  }

  /* ------------------------------------------------------------------ */
  /* Banner slider                                                      */
  /* ------------------------------------------------------------------ */
  function initBannerSlider() {
    $$('[data-banner-slider]').forEach(function (slider) {
      var slides = $$('[data-banner-slide]', slider);
      if (slides.length < 2) return;

      var controls = slider.parentElement;
      var dots = $$('[data-banner-dot]', controls);
      var prev = $('[data-banner-prev]', controls);
      var next = $('[data-banner-next]', controls);
      var index = 0;
      var timer = null;
      var paused = false;

      function show(target, moveFocus) {
        index = (target + slides.length) % slides.length;

        slides.forEach(function (slide, position) {
          var current = position === index;
          slide.hidden = !current;
          slide.classList.toggle('is-active', current);
          if (current) {
            slide.removeAttribute('aria-hidden');
          } else {
            slide.setAttribute('aria-hidden', 'true');
          }
        });

        dots.forEach(function (dot, position) {
          var current = position === index;
          dot.classList.toggle('is-active', current);
          dot.setAttribute('aria-selected', current ? 'true' : 'false');
          dot.tabIndex = current ? 0 : -1;
          if (current && moveFocus) dot.focus();
        });
      }

      function stop() {
        if (timer) {
          window.clearInterval(timer);
          timer = null;
        }
      }

      function play() {
        stop();
        if (reduceMotion || document.hidden) return;
        timer = window.setInterval(function () {
          if (!paused) show(index + 1, false);
        }, 6500);
      }

      function step(direction, moveFocus) {
        show(index + direction, moveFocus);
        play();
      }

      if (prev) prev.addEventListener('click', function () { step(-1, false); });
      if (next) next.addEventListener('click', function () { step(1, false); });

      dots.forEach(function (dot, position) {
        dot.addEventListener('click', function () {
          show(position, false);
          play();
        });
      });

      slider.addEventListener('keydown', function (event) {
        if (event.key === 'ArrowLeft') {
          event.preventDefault();
          step(-1, false);
        } else if (event.key === 'ArrowRight') {
          event.preventDefault();
          step(1, false);
        }
      });

      slider.addEventListener('mouseenter', function () { paused = true; });
      slider.addEventListener('mouseleave', function () { paused = false; });
      slider.addEventListener('focusin', function () { paused = true; });
      slider.addEventListener('focusout', function () { paused = false; });
      document.addEventListener('visibilitychange', function () {
        if (document.hidden) stop(); else play();
      });

      show(0, false);
      play();
    });
  }

  /* ------------------------------------------------------------------ */
  /* Catalogue search clear                                             */
  /* ------------------------------------------------------------------ */
  function initSearchClear() {
    $$('[data-search-clear]').forEach(function (button) {
      var wrapper = button.closest('.search');
      var input = wrapper ? $('input', wrapper) : null;
      if (!input) return;

      function sync() {
        if (wrapper) wrapper.classList.toggle('has-value', input.value.length > 0);
        button.hidden = input.value.length === 0;
      }
      sync();
      input.addEventListener('input', sync);
      button.addEventListener('click', function () {
        input.value = '';
        sync();
        input.focus();
      });
    });
  }

  /* ------------------------------------------------------------------ */
  /* Form submit feedback                                               */
  /* ------------------------------------------------------------------ */
  function initFormStates() {
    $$('form[data-submit-state]').forEach(function (form) {
      form.addEventListener('submit', function () {
        var button = form.querySelector('[type="submit"]');
        if (!button || button.disabled) return;
        if (!form.checkValidity()) return;
        var label = button.getAttribute('data-submitting-label') || 'Sending…';
        button.disabled = true;
        button.classList.add('is-loading');
        button.innerHTML = label;
      });
    });
  }

  /* ------------------------------------------------------------------ */
  /* Boot                                                               */
  /* ------------------------------------------------------------------ */
  function boot() {
    initHeaderScroll();
    initMobileNav();
    initAccountDropdown();
    initDemoBar();
    initBannerSlider();
    initReveal();
    initBackToTop();
    initWhatsAppFloat();
    initSearchClear();
    initFormStates();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
