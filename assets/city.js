/* Pages villes : calculateur de surface selon le budget et graphique médianes / dispersion.
 * Les données viennent du bloc <script type="application/json" id="calc-data"> écrit par build_site.py.
 * Le HTML est déjà rendu pour 1 000 000 MAD et le premier quartier : ce script ne fait que le mettre à jour. */
(function(){
  'use strict';
  var $ = function(id){ return document.getElementById(id); };

  // Graphique : bascule médianes / dispersion
  var chart = $('chart');
  if (chart) chart.querySelectorAll('.switch button').forEach(function(b){
    b.addEventListener('click', function(){
      chart.dataset.mode = b.dataset.mode;
      chart.querySelectorAll('.switch button').forEach(function(x){ x.setAttribute('aria-pressed', String(x === b)); });
    });
  });

  var src = $('calc-data'), input = $('budget-input');
  if (!src || !input) return;
  var C = JSON.parse(src.textContent);
  var nf = new Intl.NumberFormat('fr-FR', {maximumFractionDigits: 0});
  var fmt = function(n){ return nf.format(n).replace(/ | /g, ' '); };
  var budget = 1000000;

  function el(tag, cls, text){ var x = document.createElement(tag); if (cls) x.className = cls; if (text != null) x.textContent = text; return x; }
  function parse(v){ var n = Number(String(v).replace(/[^\d]/g, '')); return Number.isFinite(n) ? n : 0; }
  var sel = $('quartier-select');
  function selected(){
    var r = document.querySelector('input[name="quartier"]:checked');
    return r && Object.prototype.hasOwnProperty.call(C.data, r.value) ? r.value : C.quartiers[0] || '__all';
  }
  function select(q){
    var r = document.querySelector('input[name="quartier"][value="' + CSS.escape(q) + '"]');
    if (r){ r.checked = true; update(true); }
  }
  // Le menu déroulant (mobile, villes à nombreux quartiers) pilote les mêmes boutons radio.
  if (sel) sel.addEventListener('change', function(){ select(sel.value); });

  function update(animate){
    var q = selected(), d = C.data[q], all = q === '__all';
    var valid = budget >= 50000;
    $('result-lead').textContent = d.prep + ', ce budget correspond à environ';
    var m = $('result-m2');
    m.innerHTML = (valid ? fmt(Math.round(budget / d.median)) : '-') + '<small>&nbsp;m²</small>';
    if (animate){ m.classList.remove('tick'); void m.offsetWidth; m.classList.add('tick'); }
    $('result-basis').textContent = 'au prix médian demandé de ' + fmt(d.median) + ' MAD/m², calculé sur ' + d.n + ' annonces.';
    var count = d.prices.filter(function(p){ return p <= budget; }).length;
    var where = all ? '' : ' dans ce quartier';
    var params = new URLSearchParams({ville: C.slug}); if (!all) params.set('quartier', q);
    var link = el('a');
    var real = $('result-real'); real.replaceChildren();
    real.className = 'result-real' + (!valid ? '' : count === 0 ? ' is-none' : ' is-some');
    if (!valid){ real.textContent = 'Entrez un budget pour lancer le calcul.'; }
    else if (count === 0){
      real.appendChild(el('strong', null, 'Aucune annonce à ce prix. '));
      real.appendChild(document.createTextNode('Ce chiffre est théorique : la moins chère' + where + ' demandait ' + fmt(d.prices[0]) + ' MAD le ' + C.short + '. '));
      link.textContent = all ? 'Voir toutes les annonces' : 'Voir les annonces de ce quartier';
      link.href = '/dashboard.html?' + params; real.appendChild(link);
    } else {
      real.appendChild(el('strong', null, count + (count > 1 ? ' annonces' : ' annonce') + ' à ce prix. '));
      real.appendChild(document.createTextNode('Sur les ' + d.n + ' annonces' + (all ? ' de la ville' : ' de ce quartier') + ', ' + count + ' ' +
        (count > 1 ? 'demandaient' : 'demandait') + ' ' + fmt(budget) + ' MAD ou moins le ' + C.short + '. '));
      params.set('prixmax', String(budget));
      link.textContent = count > 1 ? 'Voir ces annonces dans le dashboard' : 'Voir cette annonce dans le dashboard';
      link.href = '/dashboard.html?' + params; real.appendChild(link);
    }
    var max = 0; C.quartiers.forEach(function(k){ max = Math.max(max, budget / C.data[k].median); });
    if (sel) sel.value = q;
    document.querySelectorAll('.cmp button').forEach(function(b){
      var k = b.dataset.q, v = valid ? budget / C.data[k].median : 0;
      b.setAttribute('aria-pressed', String(k === q));
      b.querySelector('i').style.width = (max ? v / max * 100 : 0).toFixed(1) + '%';
      b.querySelector('.cmp-val').textContent = valid ? fmt(Math.round(v)) + ' m²' : '-';
      b.setAttribute('aria-label', k + ' : environ ' + fmt(Math.round(v)) + ' m²');
    });
    document.querySelectorAll('.presets button').forEach(function(b){ b.setAttribute('aria-pressed', String(Number(b.dataset.budget) === budget)); });
  }

  input.addEventListener('input', function(){ budget = Math.min(parse(input.value), 100000000); update(false); });
  input.addEventListener('blur', function(){ if (budget) input.value = fmt(budget); });
  document.querySelectorAll('.presets button').forEach(function(b){
    b.addEventListener('click', function(){ budget = Number(b.dataset.budget); input.value = fmt(budget); update(true); });
  });
  document.querySelectorAll('input[name="quartier"]').forEach(function(r){ r.addEventListener('change', function(){ update(true); }); });
  document.querySelectorAll('.cmp button').forEach(function(b){ b.addEventListener('click', function(){ select(b.dataset.q); }); });
  update(false);
})();
