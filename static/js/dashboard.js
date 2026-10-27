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

  function initSmtpPresets() {
    var select = $('[data-smtp-preset]');
    if (!select) return;

    var presets = {
      gmail: { host: 'smtp.gmail.com', port: '587', tls: true, ssl: false },
      microsoft365: { host: 'smtp.office365.com', port: '587', tls: true, ssl: false },
      custom: null
    };

    var host = $('#id_host');
    var port = $('#id_port');
    var tls = $('#id_use_tls');
    var ssl = $('#id_use_ssl');
    var notes = $$('[data-preset-note]');

    function showNote(value) {
      notes.forEach(function (note) {
        note.classList.toggle('is-visible', note.getAttribute('data-preset-note') === value);
      });
    }

    select.addEventListener('change', function () {
      var preset = presets[select.value];
      showNote(select.value);
      if (!preset || !preset.host) return;
      if (host) host.value = preset.host;
      if (port) port.value = preset.port;
      if (tls) tls.checked = preset.tls;
      if (ssl) ssl.checked = preset.ssl;
    });

    function syncSecurity(changed, other) {
      if (changed && changed.checked && other) other.checked = false;
    }
    if (tls && ssl) {
      tls.addEventListener('change', function () { syncSecurity(tls, ssl); });
      ssl.addEventListener('change', function () { syncSecurity(ssl, tls); });
    }

    showNote(select.value);
  }

  function initPlaceholderCopy() {
    var buttons = $$('[data-copy-placeholder]');
    if (!buttons.length) return;

    function copy(value) {
      if (navigator.clipboard && window.isSecureContext) {
        return navigator.clipboard.writeText(value);
      }
      return new Promise(function (resolve, reject) {
        var area = document.createElement('textarea');
        area.value = value;
        area.setAttribute('readonly', '');
        area.style.position = 'fixed';
        area.style.opacity = '0';
        document.body.appendChild(area);
        area.select();
        try {
          document.execCommand('copy');
          resolve();
        } catch (error) {
          reject(error);
        } finally {
          document.body.removeChild(area);
        }
      });
    }

    buttons.forEach(function (button) {
      button.addEventListener('click', function () {
        var name = button.getAttribute('data-copy-placeholder');
        var token = '{{ ' + name + ' }}';
        copy(token).then(function () {
          var original = button.getAttribute('title') || '';
          button.classList.add('is-copied');
          button.setAttribute('title', 'Copied ' + token);
          window.setTimeout(function () {
            button.classList.remove('is-copied');
            button.setAttribute('title', original);
          }, 1500);
        }).catch(function () {
          button.setAttribute('title', 'Copy failed — select the placeholder manually.');
        });
      });
    });
  }

  function boot() {
    initSidebar();
    initImagePreview();
    initPermissionGroups();
    initFormsets();
    initAutoDismiss();
    initSmtpPresets();
    initPlaceholderCopy();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
