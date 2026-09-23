(function () {
  var radios = document.querySelectorAll('input[name="type"]');
  var panels = document.querySelectorAll('.panel');
  var form = document.getElementById('form');
  var status = document.getElementById('status');

  function currentType() {
    return form.querySelector('input[name="type"]:checked').value;
  }

  function show(type) {
    panels.forEach(function (p) {
      p.classList.toggle('active', p.dataset.panel === type);
    });
  }

  radios.forEach(function (r) {
    r.addEventListener('change', function () {
      show(r.value);
      setStatus('', null);
    });
  });

  function setStatus(msg, ok) {
    status.textContent = msg;
    status.className = ok === null ? '' : (ok ? 'ok' : 'err');
  }

  function fileToBase64(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () { resolve(reader.result.split(',')[1]); };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var type = currentType();
    var panel = document.querySelector('.panel[data-panel="' + type + '"]');
    var fd = new FormData();
    panel.querySelectorAll('input, textarea').forEach(function (el) {
      if (el.type !== 'file') fd.set(el.name, el.value);
    });

    var payload = {
      title: fd.get('title') || '',
      description: fd.get('description') || '',
      tags: fd.get('tags') || '',
      body: fd.get('body') || '',
      publish: !!form.querySelector('input[name="publish"]').checked,
      caption: fd.get('caption') || '',
      place: fd.get('place') || '',
      camera: fd.get('camera') || '',
      alt: fd.get('alt') || ''
    };

    if (type === 'essay' && !payload.title) {
      setStatus('An essay needs a title.', false);
      return;
    }

    var proceed = Promise.resolve();

    if (type === 'photo') {
      var fileInput = document.getElementById('p-image');
      var file = fileInput.files[0];
      if (!file) {
        setStatus('Choose a photo first.', false);
        return;
      }
      if (!payload.caption) {
        setStatus('A photo needs a caption.', false);
        return;
      }
      proceed = fileToBase64(file).then(function (b64) {
        payload.image_name = file.name;
        payload.image_data = b64;
      });
    }

    setStatus('Saving…', null);
    var submitBtn = form.querySelector('button[type="submit"]');
    submitBtn.disabled = true;

    proceed
      .then(function () {
        return fetch('/api/' + type, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
      })
      .then(function (r) {
        return r.json().then(function (data) { return { status: r.status, data: data }; });
      })
      .then(function (res) {
        if (res.status === 200 && res.data.ok) {
          var msg = 'Saved: ' + res.data.path;
          msg += res.data.published ? ' — published, live in a minute or two.' : ' (saved locally, not pushed).';
          setStatus(msg, true);
          form.reset();
          show(type);
        } else {
          setStatus('Error: ' + (res.data && res.data.error ? res.data.error : 'unknown'), false);
        }
      })
      .catch(function (err) {
        setStatus('Error: ' + err, false);
      })
      .finally(function () {
        submitBtn.disabled = false;
      });
  });
})();
