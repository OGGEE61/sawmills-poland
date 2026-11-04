const FIT_LABELS = { A: 'Bardzo dobre', B: 'Dobre', C: 'Średnie', D: 'Słabe', X: 'Odrzucona' };
const PAGE_SIZE = 50;
const today = new Date().toISOString().slice(0, 10);

let leads = [];
let filtered = [];
let page = 0;
let activeView = 'call';

const VIEWS = {
    call: { title: 'Dzwoń teraz', hint: 'Bardzo dobre i dobre, z telefonem', test: l => isTop(l) && l.phone },
    write: { title: 'Napisz', hint: 'Bardzo dobre i dobre, z e-mailem, bez telefonu', test: l => isTop(l) && !l.phone && l.email },
    waste: { title: 'Projekty o odpadach', hint: 'Świeże projekty UE: odpady, biomasa, GOZ', test: l => l.timing >= 95 && l.tier !== 'X' },
    grants: { title: 'Projekty na maszyny', hint: 'Świeże projekty UE: więcej produkcji, więcej odpadu', test: l => l.timing === 75 && l.tier !== 'X' },
    changes: { title: 'Zmiany', hint: 'Nowe od ostatniej aktualizacji danych', test: l => !!l.changes && l.tier !== 'X' },
    big: { title: 'Duże firmy', hint: 'Za duże na tę linię: do przekazania głównej linii Weima', test: l => l.size_band === 'duża' && l.tier !== 'X' },
    research: { title: 'Do zbadania', hint: 'Bardzo dobre i dobre, bez telefonu i e-maila', test: l => isTop(l) && l.action === 'Znajdź kontakt' },
    all: { title: 'Wszystkie', hint: 'Bez odrzuconych', test: l => l.tier !== 'X' }
};

function isTop(l) { return l.tier === 'A' || l.tier === 'B'; }

function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function safeUrl(url) { return /^https?:\/\//i.test(url || '') ? url : ''; }

function parseJson(text) {
    try { return JSON.parse(text || '[]'); } catch (e) { return []; }
}

function money(value) {
    const n = Number(value) || 0;
    if (n >= 1e6) return (n / 1e6).toLocaleString('pl-PL', { maximumFractionDigits: 1 }) + ' mln zł';
    if (n >= 1e3) return Math.round(n / 1e3).toLocaleString('pl-PL') + ' tys. zł';
    return n ? n.toLocaleString('pl-PL') + ' zł' : '';
}

function personLabel(l) {
    if (l.contact_person) return `<strong>${esc(l.contact_person)}</strong><div class="sub">${esc(l.contact_role)}</div>`;
    if (l.contact_role) return `<span>${esc(l.contact_role)}</span>${l.contact_initials ? `<div class="sub">${esc(l.contact_initials)} (KRS ukrywa nazwisko)</div>` : ''}`;
    return '<span class="sub">brak danych</span>';
}

function init(text) {
    leads = Papa.parse(text, { header: true, skipEmptyLines: true }).data;
    leads.forEach(l => {
        ['priority', 'fit', 'capacity', 'timing', 'reach', 'eu_count'].forEach(k => { l[k] = Number(l[k]) || 0; });
        l.search = [l.name, l.nip, l.contact_person, l.city, l.municipality, l.email].join(' ').toLowerCase();
        l.tagList = (l.all_tags || '').split('; ').filter(Boolean);
    });
    fillSelect('fVoiv', uniqueOf(l => (l.voivodeship || '').toUpperCase()));
    fillSelect('fTag', uniqueOf(l => l.tagList));
    const live = leads.filter(l => l.tier !== 'X').length;
    document.getElementById('dataNote').textContent = `${live.toLocaleString('pl-PL')} firm aktywnych, ${(leads.length - live).toLocaleString('pl-PL')} odrzuconych (likwidacja, upadłość, wykreślenie z VAT)`;
    apply();
    if (location.hash.length > 1) openPanel(location.hash.slice(1)); // link from the main dashboard's company card
}

function uniqueOf(getter) {
    const set = new Set();
    leads.forEach(l => [].concat(getter(l)).forEach(v => { if (v && v !== 'NAN') set.add(v); }));
    return [...set].sort((a, b) => a.localeCompare(b, 'pl'));
}

function fillSelect(id, values) {
    const select = document.getElementById(id);
    values.forEach(v => select.add(new Option(v, v)));
}

function renderViews() {
    document.getElementById('views').innerHTML = Object.entries(VIEWS).map(([key, v]) => `
        <button class="view-btn" data-view="${key}" aria-pressed="${key === activeView}">
            <b>${leads.filter(v.test).length.toLocaleString('pl-PL')}</b>
            <span>${esc(v.title)}</span>
            <small>${esc(v.hint)}</small>
        </button>`).join('');
}

function value(id) { return document.getElementById(id).value; }

function apply() {
    const term = value('q').trim().toLowerCase();
    const voiv = value('fVoiv'), tier = value('fTier'), action = value('fAction'), tag = value('fTag'), product = value('fProduct');
    const source = value('fSource'), euOnly = document.getElementById('fEu').checked;
    // an explicit "X" filter shows rejected firms; a view would otherwise hide them
    const base = tier === 'X' ? (l => l.tier === 'X') : VIEWS[activeView].test;
    filtered = leads.filter(l => base(l)
        && (!term || l.search.includes(term))
        && (!voiv || (l.voivodeship || '').toUpperCase() === voiv)
        && (!tier || l.tier === tier)
        && (!action || l.action === action)
        && (!tag || l.tagList.includes(tag))
        && (!product || l.product === product)
        && (!source || l.source === source)
        && (!euOnly || l.eu_count > 0));
    page = 0;
    renderViews();
    renderRows();
}

function reasonChips(l) {
    const reasons = (l.reasons || '').split('; ').filter(Boolean);
    const hot = reasons.filter(r => r.includes('projekt UE') || r.includes('Projekty UE'));
    const rest = reasons.filter(r => !hot.includes(r));
    let html = (l.changes || '').split('; ').filter(Boolean).map(c => `<span class="chip chip-hot">${esc(c)}</span>`).join('');
    html += hot.map(r => `<span class="chip chip-hot">${esc(r)}</span>`).join('');
    html += rest.slice(0, 3).map(r => `<span class="chip">${esc(r)}</span>`).join('');
    (l.warnings || '').split('; ').filter(Boolean).forEach(w => { html += `<span class="chip chip-warn">${esc(w)}</span>`; });
    (l.blockers || '').split('; ').filter(Boolean).forEach(b => { html += `<span class="chip chip-warn">${esc(b)}</span>`; });
    return html;
}

function renderRows() {
    const body = document.getElementById('rows');
    const maxPage = Math.max(Math.ceil(filtered.length / PAGE_SIZE) - 1, 0);
    page = Math.min(page, maxPage);
    const slice = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
    document.getElementById('listTitle').textContent = value('fTier') === 'X' ? 'Odrzucone' : VIEWS[activeView].title;
    document.getElementById('listCount').textContent = `${filtered.length.toLocaleString('pl-PL')} firm, najlepiej dopasowane na górze`;
    document.getElementById('pageInput').value = page + 1;
    document.getElementById('pageInput').max = maxPage + 1;
    document.getElementById('maxPageLabel').textContent = maxPage + 1;
    document.getElementById('first').disabled = page === 0;
    document.getElementById('prev').disabled = page === 0;
    document.getElementById('next').disabled = page >= maxPage;
    document.getElementById('last').disabled = page >= maxPage;
    if (!slice.length) {
        body.innerHTML = '<tr><td colspan="6" class="empty">Nic nie pasuje do tych filtrów.</td></tr>';
        return;
    }
    body.innerHTML = slice.map(l => {
        const tags = l.tagList.slice(0, 4).map(t => `<span class="chip">${esc(t)}</span>`).join('');
        return `<tr data-nip="${esc(l.nip)}">
            <td><span class="fit fit-${esc(l.tier)}" title="Wynik ${l.priority}/100. Szczegóły na karcie firmy.">${esc(FIT_LABELS[l.tier] || l.tier)}</span></td>
            <td><div class="firm-name">${esc(l.name)}</div><div class="sub">${esc(l.city)}${l.voivodeship ? ', ' + esc(l.voivodeship.toLowerCase()) : ''} · ${esc(l.source)}</div>${tags}</td>
            <td class="stage-pill">${esc(l.product) || '<span class="sub">-</span>'}</td>
            <td>${personLabel(l)}</td>
            <td>${l.phone ? `<a class="phone" href="tel:${esc(l.phone.replace(/\s/g, ''))}">${esc(l.phone)}</a>` : ''}
                ${l.email ? `<div class="sub">${esc(l.email)}</div>` : ''}
                ${!l.phone && !l.email ? '<span class="sub">do znalezienia</span>' : ''}</td>
            <td class="col-why">${reasonChips(l)}</td>
        </tr>`;
    }).join('');
}

// renderRows caps the page at the last one
function goToPage(target) {
    page = Math.max(target, 0);
    renderRows();
    window.scrollTo(0, 0);
}

function bar(label, score) {
    return `<span>${esc(label)}</span><div class="bar"><i style="width:${Number(score)}%"></i></div><span>${Number(score)}</span>`;
}

function openPanel(nip) {
    const l = leads.find(x => x.nip === nip);
    if (!l) return;
    const people = parseJson(l.people_json);
    const projects = parseJson(l.eu_json);
    const panel = document.getElementById('panel');
    const site = safeUrl(l.website), contactPage = safeUrl(l.contact_url);
    const contactLine = (href, text, source) => `<div class="contact-line"><a class="phone" href="${esc(href)}">${esc(text)}</a>${source ? `<small>${esc(source)}</small>` : ''}</div>`;
    const extra = (text, sources, prefix) => {
        const labels = (sources || '').split('; ');
        return (text || '').split('; ').filter(Boolean).map((v, i) => contactLine(prefix + v.replace(prefix === 'tel:' ? /\s/g : '', ''), v, labels[i])).join('');
    };

    panel.innerHTML = `
        <button class="panel-close" id="panelClose" aria-label="Zamknij">✕</button>
        <h2>${esc(l.name)}</h2>
        <div class="sub">${esc(formatAddress({ street: l.street, city: l.city, postalCode: l.postal_code, postOffice: l.post_office }) || 'brak adresu')} · ${esc((l.voivodeship || '').toLowerCase())} · ${esc(l.source)} · NIP ${esc(l.nip)}</div>
        <div class="opening"><small>Oferta: ${esc(l.product || 'do ustalenia')}. Pierwsze zdanie do rozmowy:</small>${esc(l.opening)}</div>
        <div class="sub" style="margin-top:6px">Ustal w rozmowie: ile odpadu dziennie (maszyna 0,5-2 t/h), jaki rodzaj (trociny, wióry, zrzyny), co dziś z nim robią.</div>

        <div class="panel-sec">
            <h3>Kontakt</h3>
            ${l.phone ? contactLine('tel:' + l.phone.replace(/\s/g, ''), l.phone, l.phone_source) : ''}
            ${extra(l.other_phones, l.other_phone_sources, 'tel:')}
            ${l.email ? contactLine('mailto:' + l.email, l.email, l.email_source) : ''}
            ${extra(l.other_emails, l.other_email_sources, 'mailto:')}
            ${!l.phone && !l.email ? '<p class="sub">Brak telefonu i e-maila w naszych źródłach.</p>' : ''}
            <div class="link-row">
                ${site ? `<a href="${esc(site)}" target="_blank" rel="noopener noreferrer">Strona firmy</a>` : ''}
                ${contactPage ? `<a href="${esc(contactPage)}" target="_blank" rel="noopener noreferrer">Podstrona kontaktu</a>` : ''}
                ${safeUrl(l.maps_url) ? `<a href="${esc(l.maps_url)}" target="_blank" rel="noopener noreferrer">Mapy</a>` : ''}
            </div>
            <div class="link-row" style="margin-top:8px">
                <button id="copyNip" class="btn btn-secondary btn-sm">Kopiuj NIP</button>
            </div>
        </div>

        <div class="panel-sec">
            <h3>Ludzie</h3>
            ${people.length ? people.slice(0, 6).map(p => `<div class="person"><strong>${esc(p.name || p.initials || 'Nazwisko ukryte w KRS')}</strong>${p.role ? ' · ' + esc(p.role.toLowerCase()) : ''}${p.name_source ? ` <span class="sub">[${esc(p.name_source)}]</span>` : ''}${p.note ? ` <span class="sub">(${esc(p.note)})</span>` : ''}</div>`).join('') : '<p class="sub">Brak danych.</p>'}
        </div>

        <div class="panel-sec">
            <h3>Skąd ta ocena: ${esc(FIT_LABELS[l.tier] || l.tier)} (${l.priority}/100)</h3>
            <div class="bars">${bar('Odpad drzewny', l.fit)}${bar('Wielkość firmy', l.capacity)}${bar('Moment zakupu', l.timing)}${bar('Dostępność kontaktu', l.reach)}</div>
            <div style="margin-top:8px">${reasonChips(l)}</div>
        </div>

        ${projects.length ? `<div class="panel-sec">
            <h3>Projekty UE (${l.eu_count}, razem ${esc(money(l.eu_value))})</h3>
            ${projects.map(p => `<div class="project"><b>${esc(p.title)}</b><div class="sub">${esc((p.start || '').slice(0, 4))}-${esc((p.end || '').slice(0, 4))} · ${esc(money(p.value))} · ${esc(p.kind_label)}${p.match !== 'exact' ? ' · dopasowanie po nazwie, sprawdź' : ''}</div></div>`).join('')}
        </div>` : ''}

        <div class="panel-sec">
            <h3>Dane firmy</h3>
            <div class="sub">PKD główne ${esc(l.main_pkd || 'brak')} (kodów: ${esc(l.pkd_count)}) · start ${esc(l.started)}${Number(l.share_capital) ? ' · kapitał ' + esc(money(l.share_capital)) : ''}${Number(l.latest_filing_year) ? ' · sprawozdanie za ' + esc(l.latest_filing_year) : ''} · VAT: ${esc(l.verification || 'brak')}</div>
        </div>`;

    panel.hidden = false;
    document.body.classList.add('modal-open');
    document.getElementById('panelShade').hidden = false;
    document.getElementById('panelClose').addEventListener('click', closePanel);
    document.getElementById('copyNip').addEventListener('click', e => {
        navigator.clipboard.writeText(l.nip).then(() => { e.target.textContent = 'Skopiowano'; });
    });
}

function closePanel() {
    document.getElementById('panel').hidden = true;
    document.body.classList.remove('modal-open');
    document.getElementById('panelShade').hidden = true;
}

// Spreadsheet apps run cells starting with these characters as formulas
function csvCell(text) {
    let cell = String(text == null ? '' : text);
    if (/^[=+\-@]/.test(cell)) cell = "'" + cell;
    return `"${cell.replace(/"/g, '""')}"`;
}

function download(name, content, type) {
    const url = URL.createObjectURL(new Blob([content], { type }));
    const link = Object.assign(document.createElement('a'), { href: url, download: name });
    link.click();
    URL.revokeObjectURL(url);
}

function exportList() {
    const columns = [['Dopasowanie', l => FIT_LABELS[l.tier] || l.tier], ['Wynik', l => l.priority], ['Firma', l => l.name], ['NIP', l => l.nip], ['Województwo', l => l.voivodeship],
        ['Miasto', l => l.city], ['Adres', l => l.street], ['Kod', l => l.postal_code], ['Osoba', l => l.contact_person], ['Funkcja', l => l.contact_role],
        ['Telefon', l => l.phone], ['E-mail', l => l.email], ['Strona', l => l.website], ['Oferta', l => l.product], ['Profil', l => l.all_tags], ['Dlaczego', l => l.reasons],
        ['Ostrzeżenia', l => l.warnings], ['Pierwsze zdanie', l => l.opening]];
    const lines = [columns.map(c => csvCell(c[0])).join(';')].concat(filtered.map(l => columns.map(c => csvCell(c[1](l))).join(';')));
    download(`lista-sprzedazowa-${today}.csv`, '﻿' + lines.join('\r\n'), 'text/csv;charset=utf-8');
}

document.addEventListener('DOMContentLoaded', () => {
    ['q', 'fVoiv', 'fTier', 'fAction', 'fProduct', 'fTag', 'fSource', 'fEu'].forEach(id => {
        document.getElementById(id).addEventListener(id === 'q' ? 'input' : 'change', apply);
    });
    document.getElementById('views').addEventListener('click', e => {
        const btn = e.target.closest('.view-btn');
        if (!btn) return;
        activeView = btn.dataset.view;
        document.getElementById('fTier').value = document.getElementById('fTier').value === 'X' ? '' : document.getElementById('fTier').value;
        apply();
    });
    document.getElementById('rows').addEventListener('click', e => {
        if (e.target.closest('a')) return;
        const row = e.target.closest('tr[data-nip]');
        if (row) openPanel(row.dataset.nip);
    });
    document.getElementById('first').addEventListener('click', () => goToPage(0));
    document.getElementById('prev').addEventListener('click', () => goToPage(page - 1));
    document.getElementById('next').addEventListener('click', () => goToPage(page + 1));
    document.getElementById('last').addEventListener('click', () => goToPage(filtered.length));
    document.getElementById('pageInput').addEventListener('change', e => goToPage((parseInt(e.target.value, 10) || 1) - 1));
    document.getElementById('resetBtn').addEventListener('click', () => {
        ['q', 'fVoiv', 'fTier', 'fAction', 'fProduct', 'fTag', 'fSource'].forEach(id => { document.getElementById(id).value = ''; });
        document.getElementById('fEu').checked = false;
        activeView = 'call';
        apply();
    });
    document.getElementById('panelShade').addEventListener('click', closePanel);
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closePanel(); });
    document.getElementById('exportBtn').addEventListener('click', exportList);

    if (window.top !== window) document.getElementById('backLink').hidden = true; // shown as a tab of the main dashboard

    fetch('../../data/processed/leads.csv')
        // the host answers a missing file with its HTML page and status 200
        .then(res => { if (!res.ok || (res.headers.get('content-type') || '').includes('html')) throw new Error(res.status); return res.text(); })
        .then(init)
        .catch(() => {
            document.getElementById('dataNote').textContent = 'Brak pliku leads.csv. Lista zawiera dane osobowe, więc nie ma jej w repozytorium: uruchom lokalnie src/enrichment/build_leads.py.';
            document.getElementById('dataNote').style.color = 'var(--danger)';
        });
});
