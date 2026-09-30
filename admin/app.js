(function () {
  'use strict';

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  var KIND_LABEL = { essay: 'Essay', note: 'Note', journal: 'Journal', photo: 'Photo' };
  var editing = null;   // { id, kind, title } while editing an existing item
  var items = [];

  // ---- helpers ---------------------------------------------------------

  function api(method, url, body) {
    var opts = { method: method, headers: {} };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    return fetch(url, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (!r.ok || data.ok === false) throw new Error(data.error || ('Request failed (' + r.status + ')'));
        return data;
      });
    });
  }

  function say(msg, kind) {
    var el = $('#message');
    el.textContent = msg || '';
    el.className = kind || '';
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function button(label, cls, onClick) {
    var b = el('button', cls, label);
    b.type = 'button';
    b.addEventListener('click', onClick);
    return b;
  }

  function fileToBase64(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () { resolve(String(reader.result).split(',')[1]); };
      reader.onerror = function () { reject(new Error('Couldn’t read that image file.')); };
      reader.readAsDataURL(file);
    });
  }

  function autoPublish() { return $('#auto-publish').checked; }

  try {
    var saved = localStorage.getItem('quiddity-auto-publish');
    if (saved !== null) $('#auto-publish').checked = saved === '1';
  } catch (e) {}
  $('#auto-publish').addEventListener('change', function (e) {
    try { localStorage.setItem('quiddity-auto-publish', e.target.checked ? '1' : '0'); } catch (err) {}
  });

  // After any change: say what happened, including a failed publish, then refresh the status bar.
  function report(res, done) {
    if (res.publish_error) {
      say(done + ' — saved on this computer, but publishing failed:\n' + res.publish_error, 'err');
    } else if (res.published) {
      say(done + ' — published. The live site updates in a minute or two.', 'ok');
    } else {
      say(done + ' — saved on this computer. Press “Publish now” when you want it live.', 'ok');
    }
    refreshStatus();
  }

  // ---- publish status ----------------------------------------------------

  function refreshStatus() {
    return api('GET', '/api/status').then(function (s) {
      var n = s.pending.length, ahead = s.ahead;
      var box = $('#status');
      $('#pending-list').replaceChildren.apply($('#pending-list'), s.pending.map(function (p) { return el('li', '', p); }));
      if (!n && !ahead) {
        $('#status-text').textContent = 'Everything is published.';
        $('#publish-now').hidden = true;
        box.className = 'status is-clean';
      } else {
        var parts = [];
        if (n) parts.push(n + (n === 1 ? ' change' : ' changes') + ' not published yet');
        if (ahead) parts.push(ahead + (ahead === 1 ? ' saved update' : ' saved updates') + ' waiting to upload');
        $('#status-text').textContent = parts.join(' · ');
        $('#publish-now').hidden = false;
        box.className = 'status is-dirty';
      }
      var warn = $('#identity-warning');
      warn.hidden = s.identity_ok;
      if (!s.identity_ok) {
        warn.textContent = 'Publishing won’t work yet: Git doesn’t know who you are on this computer. ' +
          'Run these two commands once in a terminal (use the email on your GitHub account), then press Publish now:\n' +
          'git config --global user.name "vent"\n' +
          'git config --global user.email "you@example.com"';
      }
    }).catch(function (e) {
      $('#status-text').textContent = 'Couldn’t check what’s published: ' + e.message;
    });
  }

  $('#publish-now').addEventListener('click', function () {
    var btn = $('#publish-now');
    btn.disabled = true;
    say('Publishing…');
    api('POST', '/api/publish', {})
      .then(function (r) { say(r.message, 'ok'); })
      .catch(function (e) { say('Publishing failed:\n' + e.message, 'err'); })
      .then(function () { btn.disabled = false; refreshStatus(); });
  });

  window.addEventListener('focus', refreshStatus);

  // ---- tabs --------------------------------------------------------------

  function showView(name) {
    $$('.view').forEach(function (v) { v.hidden = v.dataset.view !== name; });
    var radio = $('input[name=tab][value=' + name + ']');
    if (radio) radio.checked = true;
    if (name === 'manage') loadItems();
    if (name === 'site') loadSite();
  }
  $$('input[name=tab]').forEach(function (r) {
    r.addEventListener('change', function () { say(''); showView(r.value); });
  });

  // ---- write / edit -----------------------------------------------------

  function currentType() { return $('input[name=type]:checked').value; }

  function showPanel(type) {
    $$('.panel').forEach(function (p) { p.classList.toggle('active', p.dataset.panel === type); });
  }
  $$('input[name=type]').forEach(function (r) {
    r.addEventListener('change', function () { showPanel(r.value); });
  });

  function panelFields(type) {
    var data = {};
    $$('.panel[data-panel=' + type + '] input:not([type=file]), .panel[data-panel=' + type + '] textarea')
      .forEach(function (input) { data[input.name] = input.value; });
    return data;
  }

  function startEdit(id) {
    say('Opening…');
    api('GET', '/api/item?id=' + encodeURIComponent(id)).then(function (item) {
      $('#form').reset();
      editing = { id: item.id, kind: item.kind, title: item.fields.title };
      $('input[name=type][value=' + item.kind + ']').checked = true;
      showPanel(item.kind);
      $$('.panel[data-panel=' + item.kind + '] input:not([type=file]), .panel[data-panel=' + item.kind + '] textarea')
        .forEach(function (input) { input.value = item.fields[input.name] || ''; });

      var current = $('#photo-current');
      current.hidden = item.kind !== 'photo';
      current.textContent = item.fields.image
        ? 'Current image: ' + item.fields.image + ' — choose a file above only if you want to replace it.'
        : 'This photo has no image yet — choose one above to add it.';

      $('#type-switch').hidden = true;
      $('#edit-banner').hidden = false;
      $('#edit-title').textContent = item.fields.title || (KIND_LABEL[item.kind] + ' from ' + item.id.split('/').pop().slice(0, 10));
      $('#delete-btn').hidden = false;
      $('#save-btn').textContent = 'Save changes';
      showView('write');
      say('');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }).catch(function (e) { say('Couldn’t open that: ' + e.message, 'err'); });
  }

  function stopEdit() {
    editing = null;
    $('#form').reset();
    $('#type-switch').hidden = false;
    $('#edit-banner').hidden = true;
    $('#delete-btn').hidden = true;
    $('#photo-current').hidden = true;
    $('#save-btn').textContent = 'Save';
    showPanel(currentType());
  }
  $('#cancel-edit').addEventListener('click', function () { stopEdit(); say(''); });

  $('#form').addEventListener('submit', function (e) {
    e.preventDefault();
    var type = editing ? editing.kind : currentType();
    var data = panelFields(type);
    var file = type === 'photo' ? $('#p-image').files[0] : null;

    if (type === 'essay' && !data.title.trim()) return say('An essay needs a title.', 'err');
    if (type === 'photo' && !data.caption.trim()) return say('A photo needs a caption.', 'err');
    if (type === 'photo' && !editing && !file) return say('Choose a photo first.', 'err');

    var btn = $('#save-btn');
    btn.disabled = true;
    say(autoPublish() ? 'Saving and publishing…' : 'Saving…');

    (file ? fileToBase64(file) : Promise.resolve(null)).then(function (b64) {
      if (b64) { data.image_name = file.name; data.image_data = b64; }
      data.publish = autoPublish();
      if (editing) {
        data.id = editing.id;
        return api('POST', '/api/item/update', data).then(function (res) {
          report(res, 'Saved your changes');
          stopEdit();
        });
      }
      return api('POST', '/api/' + type, data).then(function (res) {
        report(res, 'Saved ' + KIND_LABEL[type].toLowerCase());
        $('#form').reset();
        showPanel(type);
      });
    }).catch(function (err) {
      say(err.message, 'err');
    }).then(function () { btn.disabled = false; });
  });

  function deleteItem(id, label, kind) {
    var extra = kind === 'photo' ? ' and its image file' : '';
    if (!window.confirm('Delete “' + label + '”' + extra + '? It will be removed from the site.')) return;
    say(autoPublish() ? 'Deleting and publishing…' : 'Deleting…');
    api('POST', '/api/item/delete', { id: id, publish: autoPublish() }).then(function (res) {
      report(res, 'Deleted “' + label + '”');
      if (editing && editing.id === id) stopEdit();
      if (!$('[data-view=manage]').hidden) loadItems();
    }).catch(function (e) { say('Couldn’t delete: ' + e.message, 'err'); });
  }
  $('#delete-btn').addEventListener('click', function () {
    if (editing) deleteItem(editing.id, editing.title || 'this ' + KIND_LABEL[editing.kind].toLowerCase(), editing.kind);
  });

  // ---- manage ------------------------------------------------------------

  function loadItems() {
    return api('GET', '/api/items').then(function (res) {
      items = res.items;
      renderItems();
    }).catch(function (e) { say('Couldn’t load your posts: ' + e.message, 'err'); });
  }

  function renderItems() {
    var filter = $('input[name=filter]:checked').value;
    var list = $('#items');
    var shown = items.filter(function (i) { return filter === 'all' || i.kind === filter; });
    if (!shown.length) {
      list.replaceChildren(el('li', 'item-empty', 'Nothing here yet.'));
      return;
    }
    list.replaceChildren.apply(list, shown.map(function (i) {
      var label = i.title || i.excerpt || '(empty)';
      var li = el('li', 'item');
      if (i.kind === 'photo') {
        var thumb;
        if (i.image) {
          thumb = el('img', 'item-thumb');
          thumb.src = i.image;
          thumb.alt = '';
          thumb.loading = 'lazy';
        } else {
          thumb = el('div', 'item-thumb');
        }
        li.appendChild(thumb);
      }
      var main = el('div', 'item-main');
      var top = el('div', 'item-top');
      top.append(el('span', 'tag tag-accent', KIND_LABEL[i.kind]), el('span', '', i.date));
      main.append(top, el('div', 'item-title', label));
      if (i.title && i.excerpt) main.appendChild(el('div', 'item-excerpt', i.excerpt));
      var actions = el('div', 'item-actions');
      actions.append(
        button('Edit', 'btn btn-secondary', function () { startEdit(i.id); }),
        button('Delete', 'btn btn-ghost danger', function () { deleteItem(i.id, label, i.kind); })
      );
      li.append(main, actions);
      return li;
    }));
  }
  $$('input[name=filter]').forEach(function (r) { r.addEventListener('change', renderItems); });

  // ---- site text ---------------------------------------------------------

  function loadSite() {
    return api('GET', '/api/site').then(function (s) {
      $$('#site-form [name]').forEach(function (input) { input.value = s[input.name] != null ? s[input.name] : ''; });
    }).catch(function (e) { say('Couldn’t load the site text: ' + e.message, 'err'); });
  }

  $('#site-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var data = {};
    $$('#site-form [name]').forEach(function (input) { data[input.name] = input.value; });
    if (!data.tagline.trim()) return say('The tagline can’t be empty.', 'err');
    if (!data.about_title.trim()) return say('The About page needs a title.', 'err');
    data.publish = autoPublish();
    var btn = $('#site-save');
    btn.disabled = true;
    say(data.publish ? 'Saving and publishing…' : 'Saving…');
    api('POST', '/api/site', data)
      .then(function (res) { report(res, 'Saved the site text'); })
      .catch(function (err) { say(err.message, 'err'); })
      .then(function () { btn.disabled = false; });
  });

  // ---- start -------------------------------------------------------------

  showPanel(currentType());
  refreshStatus();
})();
