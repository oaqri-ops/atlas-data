/* Composants communs : menu « Villes » de l'en-tête et formulaire de demande d'accès Pro.
 *
 * Réglages du contact Pro (laisser vide pour désactiver) :
 *   whatsapp : numéro au format international sans « + » ni espaces, ex. "212600000000"
 *   endpoint : URL d'un service de formulaire qui accepte un POST (Formspree, Getform…)
 * Sans endpoint, le formulaire ouvre la messagerie avec un email prérempli,
 * et affiche l'adresse à copier si la messagerie ne s'ouvre pas.
 */
(function(){
  'use strict';
  var PRO = {email: 'othman@atlas-data.fr', whatsapp: '', endpoint: ''};

  // Menu « Villes » : fermé au clic extérieur et à Échap
  var menus = document.querySelectorAll('.nav-cities');
  document.addEventListener('click', function(e){
    menus.forEach(function(m){ if (m.open && !m.contains(e.target)) m.open = false; });
  });
  document.addEventListener('keydown', function(e){
    if (e.key !== 'Escape') return;
    menus.forEach(function(m){ if (m.open){ m.open = false; m.querySelector('summary').focus(); } });
  });

  // Formulaire Pro : les liens [data-pro-contact] gardent leur mailto en repli sans JavaScript
  var links = document.querySelectorAll('[data-pro-contact]');
  if (!links.length || typeof HTMLDialogElement === 'undefined') return;

  var cities = [];
  document.querySelectorAll('.nav-cities li a[href^="/"] span').forEach(function(s){ cities.push(s.textContent); });
  if (!cities.length) cities = ['Marrakech', 'Casablanca', 'Rabat', 'Tanger'];

  function esc(s){ return String(s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }

  var d = document.createElement('dialog');
  d.className = 'pro-dialog';
  d.setAttribute('aria-labelledby', 'pro-dialog-title');
  d.innerHTML =
    '<form method="dialog" novalidate>' +
      '<button type="button" class="pro-dialog-close" aria-label="Fermer">×</button>' +
      '<div class="pro-step">' +
        '<h2 id="pro-dialog-title">Demander l\'accès Pro</h2>' +
        '<p class="pro-dialog-lede">29 € HT par mois, sans engagement. Réponse sous 24 h avec un premier fichier de votre ville.</p>' +
        '<label class="pro-field"><span>Ville à suivre</span><select name="ville" required>' +
          cities.map(function(c){ return '<option>' + esc(c) + '</option>'; }).join('') + '</select></label>' +
        '<label class="pro-field"><span>Agence</span><input name="agence" required autocomplete="organization"></label>' +
        '<label class="pro-field"><span>Email ou téléphone</span><input name="contact" required autocomplete="email"></label>' +
        '<label class="pro-field"><span>Message <small>(facultatif)</small></span><textarea name="message"></textarea></label>' +
        '<div class="pro-actions-row">' +
          '<button type="submit" class="btn btn-primary">Envoyer la demande</button>' +
          (PRO.whatsapp ? '<button type="button" class="btn btn-whatsapp" data-wa>Écrire sur WhatsApp</button>' : '') +
        '</div>' +
        '<div class="pro-fallback" hidden><strong>Dernière étape : envoyez l\'email préparé dans votre messagerie.</strong> ' +
          'Rien ne s\'est ouvert&nbsp;? Envoyez votre demande à cette adresse :' +
          '<div class="pro-copy"><code>' + esc(PRO.email) + '</code><button type="button" data-copy>Copier</button></div></div>' +
      '</div>' +
      '<div class="pro-done" hidden><h2>Demande envoyée</h2><p>Merci, nous revenons vers vous sous 24 h.</p></div>' +
    '</form>';
  document.body.appendChild(d);

  var form = d.querySelector('form'), fallback = d.querySelector('.pro-fallback');
  function field(n){ return form.elements[n].value.trim(); }
  function text(){
    return 'Bonjour,\n\nJe souhaite l\'accès Atlas Data Pro.\n\nVille : ' + field('ville') + '\nAgence : ' + field('agence') +
      '\nContact : ' + field('contact') + (field('message') ? '\n\n' + field('message') : '') + '\n';
  }
  function valid(){
    var bad = ['agence', 'contact'].filter(function(n){ return !field(n); });
    if (bad.length){ form.elements[bad[0]].focus(); form.elements[bad[0]].setAttribute('aria-invalid', 'true'); return false; }
    return true;
  }

  links.forEach(function(a){
    a.addEventListener('click', function(e){
      e.preventDefault();
      var v = a.getAttribute('data-ville');
      var sel = form.elements.ville;
      if (v){
        // Ville absente de la liste (page sans menu « Villes ») : on l'ajoute plutôt que de laisser le choix vide
        if (!Array.prototype.some.call(sel.options, function(o){ return o.value === v; })) sel.add(new Option(v, v));
        sel.value = v;
      }
      d.querySelector('.pro-step').hidden = false; d.querySelector('.pro-done').hidden = true; fallback.hidden = true;
      d.showModal();
      form.elements.agence.focus();
    });
  });
  d.querySelector('.pro-dialog-close').addEventListener('click', function(){ d.close(); });
  d.addEventListener('click', function(e){ if (e.target === d) d.close(); });
  form.addEventListener('input', function(e){ e.target.removeAttribute('aria-invalid'); });

  form.addEventListener('submit', function(e){
    e.preventDefault();
    if (!valid()) return;
    if (PRO.endpoint){
      var data = new FormData(form);
      fetch(PRO.endpoint, {method: 'POST', body: data, headers: {Accept: 'application/json'}})
        .then(function(r){ if (!r.ok) throw r; d.querySelector('.pro-step').hidden = true; d.querySelector('.pro-done').hidden = false; })
        .catch(function(){
          fallback.querySelector('strong').textContent = 'L\'envoi a échoué.';
          fallback.hidden = false;
        });
      return;
    }
    location.href = 'mailto:' + PRO.email + '?subject=' + encodeURIComponent('Accès Pro Atlas Data - ' + field('ville')) +
      '&body=' + encodeURIComponent(text());
    fallback.hidden = false;
  });
  var wa = d.querySelector('[data-wa]');
  if (wa) wa.addEventListener('click', function(){
    if (!valid()) return;
    window.open('https://wa.me/' + PRO.whatsapp + '?text=' + encodeURIComponent(text()), '_blank', 'noopener');
  });
  d.querySelector('[data-copy]').addEventListener('click', function(e){
    var b = e.currentTarget;
    (navigator.clipboard ? navigator.clipboard.writeText(PRO.email) : Promise.reject()).then(function(){ b.textContent = 'Copié'; },
      function(){ b.textContent = 'Sélectionnez l\'adresse'; });
  });
})();
