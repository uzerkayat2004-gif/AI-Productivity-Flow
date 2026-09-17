/* ================================================================
   AI Productivity Flow — marketing site behaviour
   Mirrors the desktop app: dark (warm charcoal) / light (parchment)
   No dependencies. Degrades gracefully if JS is disabled.
   ================================================================ */
(function () {
  'use strict';

  var root = document.documentElement;
  var STORE_KEY = 'flow-site-theme';

  /* ---------------------------------------------------------------
     1. Theme
     The inline <head> script already applied the stored theme so
     there is no flash. Here we only wire the toggle and keep the
     browser chrome colour in sync with the canvas token.
     --------------------------------------------------------------- */
  var CHROME = { dark: '#20211f', light: '#ebe0cc' };

  function currentTheme() {
    return root.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
  }

  function applyTheme(theme, persist) {
    root.setAttribute('data-theme', theme);

    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', CHROME[theme]);

    var btn = document.getElementById('themeBtn');
    if (btn) {
      var next = theme === 'dark' ? 'light' : 'dark';
      btn.setAttribute('aria-label', 'Switch to ' + next + ' theme');
      btn.setAttribute('title', 'Switch to ' + next + ' theme');
      btn.setAttribute('aria-pressed', theme === 'light' ? 'true' : 'false');
    }

    if (persist) {
      try { localStorage.setItem(STORE_KEY, theme); } catch (e) { /* private mode */ }
    }
  }

  applyTheme(currentTheme() || 'light', false);

  var themeBtn = document.getElementById('themeBtn');
  if (themeBtn) {
    themeBtn.addEventListener('click', function () {
      applyTheme(currentTheme() === 'dark' ? 'light' : 'dark', true);
    });
  }

  /* ---------------------------------------------------------------
     2. Sticky nav shadow & dynamic brand morph (AI Productivity Flow -> AF)
     --------------------------------------------------------------- */
  var nav = document.getElementById('nav');
  var isScrolled = false;
  var ticking = false;

  function onScroll() {
    if (nav) {
      var y = window.scrollY || window.pageYOffset || document.documentElement.scrollTop || 0;
      if (!isScrolled && y > 28) {
        isScrolled = true;
        nav.classList.add('is-stuck');
        nav.classList.add('is-scrolled');
      } else if (isScrolled && y <= 14) {
        isScrolled = false;
        nav.classList.remove('is-stuck');
        nav.classList.remove('is-scrolled');
      }
    }
    ticking = false;
  }

  window.addEventListener('scroll', function () {
    if (!ticking) { ticking = true; window.requestAnimationFrame(onScroll); }
  }, { passive: true });
  onScroll();

  /* ---------------------------------------------------------------
     3. Scroll reveal
     Elements marked .rv start transparent (only while html.js is set),
     so a failure here would hide real content. Belt and braces:
     an IntersectionObserver plus a scroll-driven sweep, so a visitor
     who flings the page to the bottom never lands on blank space.
     --------------------------------------------------------------- */
  var revealables = Array.prototype.slice.call(document.querySelectorAll('.rv'));

  function showAll() {
    revealables.forEach(function (el) { el.classList.add('in'); });
    revealables.length = 0;
  }

  /* Reveal anything currently inside (or just past) the viewport. */
  function sweep() {
    if (!revealables.length) return;
    var limit = window.innerHeight + 120;
    for (var i = revealables.length - 1; i >= 0; i--) {
      var box = revealables[i].getBoundingClientRect();
      if (box.top < limit && box.bottom > -200) {
        revealables[i].classList.add('in');
        revealables.splice(i, 1);
      }
    }
  }

  if (!('IntersectionObserver' in window)) {
    showAll();
  } else {
    try {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          entry.target.classList.add('in');
          var at = revealables.indexOf(entry.target);
          if (at > -1) revealables.splice(at, 1);
          io.unobserve(entry.target);
        });
      }, { rootMargin: '0px 0px -6% 0px', threshold: 0.05 });

      document.querySelectorAll('.rv').forEach(function (el) { io.observe(el); });

      /* The sweep also runs on scroll, which covers fast scrolling and
         any element the observer has not reported on yet. */
      var sweeping = false;
      window.addEventListener('scroll', function () {
        if (sweeping) return;
        sweeping = true;
        window.requestAnimationFrame(function () { sweep(); sweeping = false; });
      }, { passive: true });
      window.addEventListener('resize', sweep, { passive: true });

      sweep();
      window.setTimeout(sweep, 400);
      /* Last resort: never leave anything invisible for long. */
      window.setTimeout(showAll, 6000);
    } catch (e) {
      showAll();
    }
  }

  /* ---------------------------------------------------------------
     4. Copy the install commands
     The <pre> mixes comments (.c) and shell prompts (.p). Comments
     stay, prompts are stripped so the text pastes straight into
     PowerShell.
     --------------------------------------------------------------- */
  var copyBtn = document.getElementById('copyBtn');
  var codeBlock = document.getElementById('codeBlock');

  function commandText(pre) {
    var clone = pre.cloneNode(true);
    Array.prototype.slice.call(clone.querySelectorAll('.p')).forEach(function (p) {
      if (/^[\s\$>%\#]+$/.test(p.textContent)) {
        p.parentNode.removeChild(p);
      }
    });
    return clone.textContent.replace(/[ \t]+$/gm, '').trim() + '\n';
  }

  function flash(btn, msg, ok) {
    var original = btn.getAttribute('data-label') || btn.textContent;
    btn.setAttribute('data-label', original);
    btn.textContent = msg;
    btn.classList.remove('is-done', 'is-fail');
    btn.classList.add(ok ? 'is-done' : 'is-fail');
    window.clearTimeout(btn._t);
    btn._t = window.setTimeout(function () {
      btn.textContent = original;
      btn.classList.remove('is-done', 'is-fail');
    }, ok ? 1600 : 2600);
  }

  function legacyCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.top = '-1000px';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    document.body.removeChild(ta);
    return ok;
  }

  /* When no clipboard is reachable, select the block so the visitor's own
     Ctrl+C still works instead of leaving them stuck. */
  function selectBlock(pre) {
    try {
      var range = document.createRange();
      range.selectNodeContents(pre);
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      return true;
    } catch (e) {
      return false;
    }
  }

  /* Generic copy handler for all code blocks */
  document.querySelectorAll('.code__copy').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var text = btn.getAttribute('data-copy');
      var container = btn.closest('.code');
      var pre = container ? container.querySelector('pre') : null;
      if (!text && pre) {
        text = pre.getAttribute('data-copy') || commandText(pre);
      }
      if (!text) return;

      var fallback = function () {
        if (legacyCopy(text)) {
          flash(btn, 'Copied', true);
        } else {
          selectBlock(pre);
          flash(btn, 'Selected — press Ctrl+C', false);
        }
      };

      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(
          function () { flash(btn, 'Copied', true); },
          fallback
        );
      } else {
        fallback();
      }
    });
  });

  /* OS Tab Switcher for Download Section */
  var osTabs = document.querySelectorAll('.os-tab-btn');
  var osPanels = document.querySelectorAll('.os-panel');
  if (osTabs.length) {
    osTabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        var targetId = tab.getAttribute('data-target');
        osTabs.forEach(function (t) { t.classList.remove('is-active'); });
        osPanels.forEach(function (p) { p.classList.add('is-hidden'); });
        tab.classList.add('is-active');
        var panel = document.getElementById(targetId);
        if (panel) panel.classList.remove('is-hidden');
      });
    });
  }

  /* ---------------------------------------------------------------
     5. Mobile menu
     --------------------------------------------------------------- */
  var burger = document.getElementById('burger');
  var links = document.querySelector('.nav__links');

  function setMenu(open) {
    if (!nav || !burger) return;
    nav.classList.toggle('menu-open', open);
    burger.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  if (burger && links) {
    burger.addEventListener('click', function () {
      setMenu(!nav.classList.contains('menu-open'));
    });

    links.addEventListener('click', function (e) {
      if (e.target.tagName === 'A') setMenu(false);
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') setMenu(false);
    });

    window.addEventListener('resize', function () {
      if (window.innerWidth > 760) setMenu(false);
    });
  }

  /* ---------------------------------------------------------------
     6. Active section in the nav
     --------------------------------------------------------------- */
  var navLinks = Array.prototype.slice.call(
    document.querySelectorAll('.nav__links a[href^="#"]')
  );
  var sections = navLinks
    .map(function (a) { return document.querySelector(a.getAttribute('href')); })
    .filter(Boolean);

  if (sections.length && 'IntersectionObserver' in window) {
    var spy = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var id = '#' + entry.target.id;
        navLinks.forEach(function (a) {
          a.classList.toggle('is-active', a.getAttribute('href') === id);
        });
      });
    }, { rootMargin: '-45% 0px -50% 0px' });

    sections.forEach(function (s) { spy.observe(s); });
  }

  /* ---------------------------------------------------------------
     7. Year in the footer
     --------------------------------------------------------------- */
  var year = document.getElementById('year');
  if (year) year.textContent = String(new Date().getFullYear());

  /* ---------------------------------------------------------------
     8. Hero Desktop Studio Tab Switcher
     --------------------------------------------------------------- */
  var tabVideo = document.getElementById('tabVideo');
  var tabAudio = document.getElementById('tabAudio');
  var panelVideo = document.getElementById('panelVideo');
  var panelAudio = document.getElementById('panelAudio');
  var capVideo = document.getElementById('capVideo');
  var capAudio = document.getElementById('capAudio');

  if (tabVideo && tabAudio && panelVideo && panelAudio) {
    var vidVideo = panelVideo.querySelector('video');
    var vidAudio = panelAudio.querySelector('video');

    function setTab(tab) {
      var isVideo = tab === 'video';
      tabVideo.classList.toggle('is-active', isVideo);
      tabAudio.classList.toggle('is-active', !isVideo);
      tabVideo.setAttribute('aria-selected', isVideo ? 'true' : 'false');
      tabAudio.setAttribute('aria-selected', !isVideo ? 'true' : 'false');
      panelVideo.classList.toggle('is-active', isVideo);
      panelAudio.classList.toggle('is-active', !isVideo);

      if (capVideo) capVideo.classList.toggle('is-active', isVideo);
      if (capAudio) capAudio.classList.toggle('is-active', !isVideo);

      if (isVideo) {
        if (vidVideo) { vidVideo.play().catch(function () {}); }
        if (vidAudio) { vidAudio.pause(); }
      } else {
        if (vidAudio) { vidAudio.play().catch(function () {}); }
        if (vidVideo) { vidVideo.pause(); }
      }
    }

    tabVideo.addEventListener('click', function () { setTab('video'); });
    tabAudio.addEventListener('click', function () { setTab('audio'); });
    if (capVideo) capVideo.addEventListener('click', function () { setTab('video'); });
    if (capAudio) capAudio.addEventListener('click', function () { setTab('audio'); });
  }

  /* ---------------------------------------------------------------
     9. Scroll-Driven Hero Demo Showcase Zoom-In, Hold & Zoom-Out
     --------------------------------------------------------------- */
  // Managed inline in index.html (#hero-showcase-zoom-controller) for zero-latency execution and cache immunity
})();

