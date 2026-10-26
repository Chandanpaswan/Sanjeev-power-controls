/* ==========================================================================
   Sanjeev Power Controls — dashboard interactions
   ========================================================================== */
(function () {
  'use strict';

  var $ = function (selector, scope) {
    return (scope || document).querySelector(selector);
  };
  var $$ = function (selector, scope) {
    return Array.prototype.slice.call((scope || document).querySelectorAll(selector));
  };

  function initSidebar() {
    var shell = $('[data-dash-shell]');
    var open = $('[data-dash-open]');
    var close = $('[data-dash-close]');
    var overlay = $('[data-dash-overlay]');
    if (!shell || !open) return;

    function openSidebar() {
      shell.classList.add('is-nav-open');
      open.setAttribute('aria-expanded', 'true');
      document.body.classList.add('is-locked');
      var first = $('a[href]', $('#dash-sidebar'));
      if (first) first.focus();
    }

    function closeSidebar() {
      shell.classList.remove('is-nav-open');
      open.setAttribute('aria-expanded', 'false');
      document.body.classList.remove('is-locked');
    }

    open.addEventListener('click', openSidebar);
    if (close) close.addEventListener('click', closeSidebar);
    if (overlay) overlay.addEventListener('click', closeSidebar);

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') closeSidebar();
    });

    window.matchMedia('(min-width: 1025px)').addEventListener('change', function (event) {
      if (event.matches) closeSidebar();
    });
  }

  function initImagePreview() {
    var input = $('input[type="file"][name="image"]');
    if (!input) return;

    var preview = $('[data-image-preview]');
    var target = preview ? $('[data-image-target]', preview) : null;
    var empty = preview ? $('[data-image-empty]', preview) : null;
    if (!preview || !target) return;

    function setPreview(file) {
      if (!file || !file.type || file.type.indexOf('image/') !== 0) return;
      var reader = new FileReader();
      reader.onload = function (event) {
        target.src = event.target.result;
        target.hidden = false;
        if (empty) empty.hidden = true;
      };
      reader.readAsDataURL(file);
    }

    input.addEventListener('change', function () {
      setPreview(input.files && input.files[0]);
    });
  }

  function initAutoDismiss() {
    $$('.dash-messages .alert, .site-messages .alert').forEach(function (alert) {
      window.setTimeout(function () {
        if (window.bootstrap && window.bootstrap.Alert) {
          window.bootstrap.Alert.getOrCreateInstance(alert).close();
        }
      }, 8000);
    });
  }

  function initPermissionGroups() {
    $$('[data-toggle-group]').forEach(function (button) {
      var group = button.closest('.permission-group');
      if (!group) return;

      var checks = $$('input[type="checkbox"]', group);
      if (!checks.length) return;

      function allChecked() {
        return checks.every(function (check) { return check.checked; });
      }

      function sync() {
        var all = allChecked();
        button.textContent = all ? 'Clear all' : 'Select all';
        button.setAttribute('aria-pressed', all ? 'true' : 'false');
      }

      button.addEventListener('click', function () {
        var target = !allChecked();
        checks.forEach(function (check) {
          check.checked = target;
          check.dispatchEvent(new Event('change', { bubbles: true }));
        });
        sync();
      });

      checks.forEach(function (check) {
        check.addEventListener('change', sync);
      });

      sync();
    });
  }

  function initFormsets() {
    $$('[data-formset]').forEach(function (list) {
      $$('.formset-row', list).forEach(function (row) {
        var remove = $('input[name$="-DELETE"]', row);
        if (!remove) return;

        function sync() {
          row.classList.toggle('is-deleted', remove.checked);
          $$('input, select, textarea', row).forEach(function (field) {
            if (field === remove) return;
            field.disabled = remove.checked;
          });
        }

        remove.addEventListener('change', sync);
        sync();
      });
    });
  }

  function boot() {
    initSidebar();
    initImagePreview();
    initPermissionGroups();
    initFormsets();
    initAutoDismiss();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
