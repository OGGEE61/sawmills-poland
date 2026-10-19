let allData = [];
let filteredData = [];
let currentPage = 1;
let rowsPerPage = 50;

let contactedFirms = JSON.parse(localStorage.getItem('contactedFirms')) || {};

// Chart instances
let regionChartInst = null;
let yearChartInst = null;
let selectedYearFilter = null;

// DOM Elements
const wojewodztwoFilter = document.getElementById('wojewodztwoFilter');
const statusFilter = document.getElementById('statusFilter');
const miastoFilter = document.getElementById('miastoFilter');
const kodFilter = document.getElementById('kodFilter');
const searchFilter = document.getElementById('searchFilter');
const contactedFilter = document.getElementById('contactedFilter');
const vatFilter = document.getElementById('vatFilter');
const pkdFilter = document.getElementById('pkdFilter');
const hideNanRegion = document.getElementById('hideNanRegion');
const resetFilters = document.getElementById('resetFilters');
const clearYearFilterBtn = document.getElementById('clearYearFilter');
const yearFilterContainer = document.getElementById('yearFilterContainer');
const selectedYearText = document.getElementById('selectedYearText');
const tableBody = document.getElementById('tableBody');
const rowsPerPageSelect = document.getElementById('rowsPerPageSelect');
const recordCountLabel = document.getElementById('recordCount');
const totalFirmsLabel = document.getElementById('totalFirms');
const topRegionLabel = document.getElementById('topRegion');
const prevPageBtn = document.getElementById('prevPage');
const nextPageBtn = document.getElementById('nextPage');
const firstPageBtn = document.getElementById('firstPage');
const lastPageBtn = document.getElementById('lastPage');
const pageInput = document.getElementById('pageInput');
const maxPageLabel = document.getElementById('maxPageLabel');
const pageInfoLabel = document.getElementById('pageInfo');

function extractYear(dateStr) {
    if(!dateStr || typeof dateStr !== 'string') return null;
    const str = dateStr.trim();
    if(str.length < 4) return null;
    let year = str.substring(0, 4);
    if(str.includes('.')) {
        const parts = str.split('.');
        if(parts.length === 3) year = parts[2];
    }
    const parsed = parseInt(year, 10);
    return (!isNaN(parsed) && parsed >= 1900 && parsed <= 2030) ? String(parsed) : null;
}

function updateYearFilterUI() {
    if(yearFilterContainer && selectedYearText) {
        if(selectedYearFilter) {
            yearFilterContainer.style.display = 'inline-flex';
            selectedYearText.textContent = selectedYearFilter;
        } else {
            yearFilterContainer.style.display = 'none';
        }
    }
}

// Setup Chart Defaults for Warm Sawmill Theme
Chart.defaults.color = '#796b5e';
Chart.defaults.borderColor = '#e6dfd3';

// Initialization
document.addEventListener('DOMContentLoaded', () => {
    loadData();
    
    // Event listeners
    wojewodztwoFilter.addEventListener('change', applyFilters);
    statusFilter.addEventListener('change', applyFilters);
    hideNanRegion.addEventListener('change', applyFilters);
    contactedFilter.addEventListener('change', applyFilters);
    vatFilter.addEventListener('change', applyFilters);
    pkdFilter.addEventListener('change', applyFilters);
    miastoFilter.addEventListener('input', applyFilters);
    kodFilter.addEventListener('input', applyFilters);
    searchFilter.addEventListener('input', applyFilters);
    
    if(clearYearFilterBtn) {
        clearYearFilterBtn.addEventListener('click', (e) => {
            e.preventDefault();
            selectedYearFilter = null;
            updateYearFilterUI();
            applyFilters();
        });
    }

    // Modal close listeners
    const modalCloseBtn = document.getElementById('modalCloseBtn');
    const companyModal = document.getElementById('companyModal');
    if (modalCloseBtn) modalCloseBtn.addEventListener('click', closeCompanyModal);
    if (companyModal) {
        companyModal.addEventListener('click', (e) => {
            if (e.target === companyModal) closeCompanyModal();
        });
    }
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeCompanyModal();
    });

    resetFilters.addEventListener('click', () => {
        wojewodztwoFilter.value = '';
        statusFilter.value = (currentRejestrTab === 'KRS') ? 'AKTYWNY' : 'ALL';
        miastoFilter.value = '';
        kodFilter.value = '';
        searchFilter.value = '';
        contactedFilter.value = 'ALL';
        vatFilter.value = 'ALL';
        pkdFilter.value = '';
        selectedYearFilter = null;
        updateYearFilterUI();
        hideNanRegion.checked = true;
        applyFilters();
    });
    
    rowsPerPageSelect.addEventListener('change', (e) => {
        rowsPerPage = parseInt(e.target.value);
        currentPage = 1;
        updateDashboard();
    });

    prevPageBtn.addEventListener('click', () => {
        if(currentPage > 1) {
            currentPage--;
            renderTable();
        }
    });
    
    nextPageBtn.addEventListener('click', () => {
        const maxPage = Math.ceil(filteredData.length / rowsPerPage);
        if(currentPage < maxPage) {
            currentPage++;
            renderTable();
        }
    });

    firstPageBtn.addEventListener('click', () => {
        currentPage = 1;
        renderTable();
    });

    lastPageBtn.addEventListener('click', () => {
        const maxPage = Math.ceil(filteredData.length / rowsPerPage) || 1;
        currentPage = maxPage;
        renderTable();
    });

    pageInput.addEventListener('change', (e) => {
        let page = parseInt(e.target.value);
        const maxPage = Math.ceil(filteredData.length / rowsPerPage) || 1;
        if(isNaN(page) || page < 1) page = 1;
        if(page > maxPage) page = maxPage;
        currentPage = page;
        renderTable();
    });
    
    // Tabs setup
    const tabBtns = document.querySelectorAll('.tab-btn');
    tabBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            currentRejestrTab = e.target.getAttribute('data-rejestr');
            updateTabStyles();
            if (currentRejestrTab === 'KRS') {
                statusFilter.value = 'AKTYWNY';
            }
            applyFilters();
        });
    });
});

let currentRejestrTab = 'ALL';

function updateTabStyles() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        if(btn.getAttribute('data-rejestr') === currentRejestrTab) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });
}

// Load CSV Data
function loadData() {
    Promise.all([
        fetch('../../data/processed/tartaki_ceidg.csv').then(res => res.ok ? res.text() : null).catch(() => null),
        fetch('../../data/processed/tartaki_full.csv').then(res => res.ok ? res.text() : null).catch(() => null),
        fetch('../../data/processed/verification.csv').then(res => res.ok ? res.text() : null).catch(() => null)
    ]).then(([ceidgText, krsText, verifText]) => {
        let tempData = [];
        
        if (ceidgText) {
            const parsed = Papa.parse(ceidgText, { header: true, skipEmptyLines: true });
            parsed.data.forEach(row => { if(!row.REJESTR) row.REJESTR = "CEIDG"; });
            tempData = tempData.concat(parsed.data);
        }
        
        if (krsText) {
            const parsed = Papa.parse(krsText, { header: true, skipEmptyLines: true });
            parsed.data.forEach(row => { 
                row['REJESTR'] = "KRS"; 
                row['NAZWA'] = row['name'];
                row['NIP'] = row['nip'];
                row['REGON'] = row['regon'];
                
                let status = 'WYKREŚLONY';
                if(row['status_from_discovery'] === 'ACTIVE') status = 'AKTYWNY';
                else if(row['status_from_discovery'] === 'SUSPENDED') status = 'ZAWIESZONY';
                else if(row['status_from_discovery'] === 'LIQUIDATION') status = 'W LIKWIDACJI';
                row['STATUS'] = status;
                
                row['PKD_GLOWNE_KOD'] = row['pkd_main'];
                row['detail.adresDzialalnosci.wojewodztwo'] = row['voivodeship'];
                row['detail.adresDzialalnosci.powiat'] = row['county'];
                row['detail.adresDzialalnosci.gmina'] = row['municipality'];
                row['detail.adresDzialalnosci.miasto'] = row['city'];
                row['detail.adresDzialalnosci.ulica'] = row['street'];
                row['detail.adresDzialalnosci.budynek'] = row['building_no'];
                row['detail.adresDzialalnosci.lokal'] = row['unit_no'];
                row['detail.adresDzialalnosci.kod'] = row['postal_code'];
                row['detail.dataRozpoczecia'] = row['registration_date'];
                row['CEIDG_ID'] = row['krs'];
                row['KAPITAL'] = row['share_capital'] || '-';
                row['PKD_MATCH_TYPE'] = row['pkd_match_types'];
            });
            tempData = tempData.concat(parsed.data);
        }
        
        const verification = {};
        if (verifText) {
            Papa.parse(verifText, { header: true, skipEmptyLines: true }).data.forEach(v => { verification[v.nip] = v; });
        }
        tempData.forEach(row => {
            const raw = row['detail.wlasciciel.nip'] || row['NIP'] || '';
            const nip = raw.split('.')[0].replace(/\D/g, '').padStart(10, '0');
            row.VER = verification[nip] || null;
        });

        allData = tempData;
        filteredData = [...allData];
        
        populateFilters();
        applyFilters();
        
        if(allData.length > 0) {
            recordCountLabel.textContent = "Dane załadowane. Połączono.";
            document.querySelector('.dot').classList.remove('pulse');
        } else {
            recordCountLabel.textContent = "Brak danych (CSV).";
            recordCountLabel.style.color = "var(--danger)";
        }
    }).catch(err => {
        console.error(err);
        recordCountLabel.textContent = "Błąd ładowania danych.";
        recordCountLabel.style.color = "var(--danger)";
        document.querySelector('.dot').style.backgroundColor = "var(--danger)";
    });
}

function populateFilters() {
    const wojewodztwa = new Set();
    const statusy = new Set();
    const pkds = new Set();
    
    allData.forEach(row => {
        if(row['detail.adresDzialalnosci.wojewodztwo']) wojewodztwa.add(row['detail.adresDzialalnosci.wojewodztwo'].toUpperCase());
        if(row['STATUS']) statusy.add(row['STATUS'].toUpperCase());
        if(row['PKD_GLOWNE_KOD']) pkds.add(row['PKD_GLOWNE_KOD'].toUpperCase());
    });
    
    Array.from(wojewodztwa).sort().forEach(w => {
        const opt = document.createElement('option');
        opt.value = w;
        opt.textContent = w;
        wojewodztwoFilter.appendChild(opt);
    });

    Array.from(pkds).sort().forEach(p => {
        const opt = document.createElement('option');
        opt.value = p;
        opt.textContent = p;
        pkdFilter.appendChild(opt);
    });
    
    // Statuses are hardcoded in HTML, so we don't need to auto-populate them.
}

const VER_BADGES = {
    CZYNNY: ['badge-active', 'Czynny'],
    ZWOLNIONY: ['badge-suspended', 'Zwolniony'],
    NIEZAREJESTROWANY: ['badge-liquidation', 'Niezarejestr.'],
    WYKRESLONY: ['badge-deleted', 'Wykreślony'],
    BRAK: ['badge-suspended', 'Brak w rejestrze']
};

function verificationOf(row) {
    return row.VER ? row.VER.verification : '';
}

function applyFilters() {
    const wFilter = wojewodztwoFilter.value.toLowerCase();
    const sFilter = statusFilter.value.toLowerCase();
    const mFilter = miastoFilter.value.toLowerCase();
    const kFilter = kodFilter.value.toLowerCase();
    const term = searchFilter.value.toLowerCase();
    const cFilter = contactedFilter.value;
    const vFilter = vatFilter.value;
    const rFilter = currentRejestrTab;
    const pkdVal = pkdFilter.value.toLowerCase();
    const hideNan = hideNanRegion.checked;
    
    filteredData = allData.filter(row => {
        const woj = (row['detail.adresDzialalnosci.wojewodztwo'] || '').toLowerCase();
        const stat = (row['STATUS'] || '').toLowerCase();
        const miasto = (row['detail.adresDzialalnosci.miasto'] || '').toLowerCase();
        const kod = (row['detail.adresDzialalnosci.kod'] || '').toLowerCase();
        const nazwa = (row['NAZWA'] || '').toLowerCase();
        const nip = (row['NIP'] || '').toLowerCase();
        const ceidgId = row['CEIDG_ID'] || row['id'] || nip;
        const rowPkd = (row['PKD_GLOWNE_KOD'] || '').toLowerCase();
        const rejestr = (row['REJESTR'] || 'CEIDG').toUpperCase();
        const rowYear = extractYear(row['detail.dataRozpoczecia']);
        
        const matchWoj = !wFilter || woj === wFilter;
        const matchStat = sFilter === 'all' || !sFilter || stat === sFilter;
        const matchMiasto = !mFilter || miasto.includes(mFilter);
        const matchKod = !kFilter || kod.includes(kFilter);
        const matchSearch = !term || nazwa.includes(term) || nip.includes(term);
        const matchNan = !hideNan || (woj !== 'nan' && woj !== '');
        const matchPkd = !pkdVal || rowPkd === pkdVal;
        const matchYear = !selectedYearFilter || rowYear === selectedYearFilter;
        
        const matchRejestr = rFilter === 'ALL' || rejestr === rFilter;
        
        const isContacted = !!contactedFirms[ceidgId];
        const matchContacted = cFilter === 'ALL' || (cFilter === 'YES' && isContacted) || (cFilter === 'NO' && !isContacted);
        const matchVat = vFilter === 'ALL' || verificationOf(row) === vFilter;
        
        return matchWoj && matchStat && matchMiasto && matchKod && matchSearch && matchNan && matchContacted && matchPkd && matchRejestr && matchYear && matchVat;
    });
    
    currentPage = 1;
    updateDashboard();
}

function updateDashboard() {
    totalFirmsLabel.textContent = filteredData.length.toLocaleString('pl-PL');
    
    renderTable();
    renderCharts();
    updateTopRegion();
    renderMap();
}

function updateTopRegion() {
    const counts = {};
    filteredData.forEach(row => {
        const w = (row['detail.adresDzialalnosci.wojewodztwo'] || 'BRAK').toUpperCase();
        counts[w] = (counts[w] || 0) + 1;
    });
    
    let max = 0;
    let top = "-";
    for(const [k, v] of Object.entries(counts)) {
        if(v > max && k !== 'BRAK' && k !== 'NAN') {
            max = v;
            top = k;
        }
    }
    
    topRegionLabel.textContent = top;
}

function renderTable() {
    tableBody.innerHTML = '';
    
    const start = (currentPage - 1) * rowsPerPage;
    const end = start + rowsPerPage;
    const pageData = filteredData.slice(start, end);
    
    pageData.forEach(row => {
        const tr = document.createElement('tr');
        tr.className = 'row-clickable';
        
        // Extract values handling potential missing keys
        const nazwa = row['NAZWA'] || '-';
        const nip = row['detail.wlasciciel.nip'] || row['summary.wlasciciel.nip'] || row['NIP'] || row['nip'] || '-';
        const regon = row['detail.wlasciciel.regon'] || row['summary.wlasciciel.regon'] || row['REGON'] || row['regon'] || '-';
        const pkd = row['PKD_GLOWNE_KOD'] || row['pkd_main'] || '-';
        const woj = row['detail.adresDzialalnosci.wojewodztwo'] || row['voivodeship'] || '-';
        const miasto = row['detail.adresDzialalnosci.miasto'] || row['city'] || '-';
        const ulica = (row['detail.adresDzialalnosci.ulica'] && row['detail.adresDzialalnosci.ulica'] !== 'nan') ? row['detail.adresDzialalnosci.ulica'] : (row['street'] || '');
        const budynek = (row['detail.adresDzialalnosci.budynek'] && row['detail.adresDzialalnosci.budynek'] !== 'nan') ? row['detail.adresDzialalnosci.budynek'] : (row['building_no'] || '');
        const lokal = (row['detail.adresDzialalnosci.lokal'] && row['detail.adresDzialalnosci.lokal'] !== 'nan') ? row['detail.adresDzialalnosci.lokal'] : (row['unit_no'] || '');
        const kod = row['detail.adresDzialalnosci.kod'] || row['postal_code'] || '-';
        const email = row['EMAIL'] && row['EMAIL'] !== 'nan' ? row['EMAIL'] : '-';
        const telefon = row['TELEFON'] && row['TELEFON'] !== 'nan' ? row['TELEFON'] : '-';
        const www = row['WWW'] && row['WWW'] !== 'nan' ? row['WWW'] : '-';
        const status = row['STATUS'] || '-';
        const dataRozp = row['detail.dataRozpoczecia'] || row['registration_date'] || '-';

        let fullAdres = miasto;
        let ulicaPart = '';
        if (ulica) ulicaPart += ulica + ' ';
        if (budynek) ulicaPart += budynek;
        if (lokal) ulicaPart += '/' + lokal;
        
        if(ulicaPart.trim()) {
            fullAdres += `<br><span style="font-size: 0.85em; color: var(--text-muted);">${ulicaPart.trim()}</span>`;
        }
        
        const ceidgId = row['CEIDG_ID'] || row['id'] || nip;
        const isContacted = !!contactedFirms[ceidgId];
        const rejestr = (row['REJESTR'] || 'CEIDG').toUpperCase();
        const rejestrBadgeClass = rejestr === 'KRS' ? 'badge-rejestr-krs' : 'badge-rejestr-ceidg';
        const statusBadgeClass = status === 'AKTYWNY' ? 'badge-active' : (status === 'W LIKWIDACJI' ? 'badge-liquidation' : (status === 'ZAWIESZONY' ? 'badge-suspended' : 'badge-deleted'));
        
        let pkdLabel = pkd;
        if (rejestr === 'KRS' && row['PKD_MATCH_TYPE'] && row['PKD_MATCH_TYPE'].includes('pozostałe')) {
            pkdLabel += '<br><small style="color: #c2410c; font-weight: 600;">(Poboczne)</small>';
        } else if (rejestr === 'KRS' && row['PKD_MATCH_TYPE'] && row['PKD_MATCH_TYPE'].includes('przeważające')) {
            pkdLabel += '<br><small style="color: #15803d; font-weight: 600;">(Główne)</small>';
        }
        
        const ver = verificationOf(row);
        const verBadge = ver ? `<span class="badge ${VER_BADGES[ver][0]}">${VER_BADGES[ver][1]}</span>` : '-';

        tr.innerHTML = `
            <td style="text-align: center;"><input type="checkbox" class="contact-checkbox" data-id="${ceidgId}" ${isContacted ? 'checked' : ''} title="Oznacz jako skontaktowane"></td>
            <td class="col-nazwa"><strong>${nazwa}</strong></td>
            <td>${nip}</td>
            <td>${regon}</td>
            <td>${pkdLabel}</td>
            <td><span class="badge ${rejestrBadgeClass}">${rejestr}</span></td>
            <td>${woj}</td>
            <td>${fullAdres}</td>
            <td>${kod}</td>
            <td>${email}</td>
            <td>${telefon}</td>
            <td>${www}</td>
            <td><span class="badge ${statusBadgeClass}">${status}</span></td>
            <td>${verBadge}</td>
            <td>${dataRozp}</td>
        `;

        // Click row to open modal
        tr.addEventListener('click', (e) => {
            if (e.target.closest('.contact-checkbox') || e.target.closest('a')) return;
            openCompanyModal(row);
        });

        tableBody.appendChild(tr);
    });
    
    // Update pagination controls
    const maxPage = Math.ceil(filteredData.length / rowsPerPage) || 1;
    
    pageInput.value = currentPage;
    maxPageLabel.textContent = maxPage;
    
    firstPageBtn.disabled = currentPage === 1;
    prevPageBtn.disabled = currentPage === 1;
    nextPageBtn.disabled = currentPage === maxPage;
    lastPageBtn.disabled = currentPage === maxPage;

    // Add event listeners to checkboxes
    document.querySelectorAll('.contact-checkbox').forEach(cb => {
        cb.addEventListener('click', (e) => {
            e.stopPropagation();
        });
        cb.addEventListener('change', (e) => {
            const id = e.target.getAttribute('data-id');
            if (e.target.checked) {
                contactedFirms[id] = true;
            } else {
                delete contactedFirms[id];
            }
            localStorage.setItem('contactedFirms', JSON.stringify(contactedFirms));
        });
    });
}

function openCompanyModal(row) {
    const modal = document.getElementById('companyModal');
    const modalFirmName = document.getElementById('modalFirmName');
    const modalRejestrBadge = document.getElementById('modalRejestrBadge');
    const modalStatusBadge = document.getElementById('modalStatusBadge');
    const modalBody = document.getElementById('modalBody');

    const nazwa = row['NAZWA'] || row['name'] || '-';
    const nip = row['detail.wlasciciel.nip'] || row['summary.wlasciciel.nip'] || row['NIP'] || row['nip'] || '-';
    const regon = row['detail.wlasciciel.regon'] || row['summary.wlasciciel.regon'] || row['REGON'] || row['regon'] || '-';
    const krs = row['krs'] || row['CEIDG_ID'] || '-';
    const legalForm = row['legal_form'] || (row['REJESTR'] === 'KRS' ? 'Spółka prawa handlowego' : 'Jednoosobowa działalność gospodarcza (JDG)');
    const rejestr = (row['REJESTR'] || 'CEIDG').toUpperCase();
    const status = row['STATUS'] || '-';
    const dataRozp = row['detail.dataRozpoczecia'] || row['registration_date'] || '-';
    const dataOstatniegoWpisu = row['last_entry_date'] || '-';
    const stanZDnia = row['as_of'] || '-';
    
    // Format capital
    let kapital = row['KAPITAL'] || row['share_capital'] || '-';
    if (kapital !== '-' && typeof kapital === 'string' && kapital.includes('wartosc')) {
        try {
            const kObj = JSON.parse(kapital.replace(/'/g, '"'));
            kapital = Number(kObj.wartosc.replace(',', '.')).toLocaleString('pl-PL') + ' ' + (kObj.waluta || 'PLN');
        } catch(e) {}
    } else if (kapital !== '-' && !isNaN(Number(kapital))) {
        kapital = Number(kapital).toLocaleString('pl-PL') + ' ' + (row['share_capital_currency'] || 'PLN');
    }

    // Address
    const woj = row['detail.adresDzialalnosci.wojewodztwo'] || row['voivodeship'] || '-';
    const powiat = row['detail.adresDzialalnosci.powiat'] || row['county'] || '-';
    const gmina = row['detail.adresDzialalnosci.gmina'] || row['municipality'] || '-';
    const miasto = row['detail.adresDzialalnosci.miasto'] || row['city'] || '-';
    const ulica = row['detail.adresDzialalnosci.ulica'] || row['street'] || '';
    const nrDomu = row['detail.adresDzialalnosci.budynek'] || row['building_no'] || '';
    const nrLokalu = row['detail.adresDzialalnosci.lokal'] || row['unit_no'] || '';
    const kodPoczt = row['detail.adresDzialalnosci.kod'] || row['postal_code'] || '-';
    const poczta = row['post_office'] || miasto;

    let adresWiersz = miasto;
    if (ulica) adresWiersz = `${ulica} ${nrDomu}${nrLokalu ? '/' + nrLokalu : ''}, ${kodPoczt} ${miasto}`;

    // Contact
    const email = row['EMAIL'] && row['EMAIL'] !== 'nan' ? row['EMAIL'] : '-';
    const telefon = row['TELEFON'] && row['TELEFON'] !== 'nan' ? row['TELEFON'] : '-';
    const www = row['WWW'] && row['WWW'] !== 'nan' ? row['WWW'] : '-';
    const ceidgId = row['CEIDG_ID'] || row['id'] || nip;
    const isContacted = !!contactedFirms[ceidgId];

    // PKD
    const pkdMain = row['PKD_GLOWNE_KOD'] || row['pkd_main'] || '-';
    const pkdMatchTypes = row['PKD_MATCH_TYPE'] || row['pkd_match_types'] || '';
    const pkdOtherStr = row['pkd_other'] || row['detail.pkd'] || '';
    const pkdOtherList = pkdOtherStr ? pkdOtherStr.split(/[;,]/).map(s => s.trim()).filter(Boolean) : [];
    const pkdDesc = row['pkd_descriptions'] || (pkdMain === '16.10.Z' ? 'Produkcja wyrobów tartacznych' : '');

    // Header updates
    modalFirmName.textContent = nazwa;
    modalRejestrBadge.textContent = rejestr;
    modalRejestrBadge.className = `badge ${rejestr === 'KRS' ? 'badge-rejestr-krs' : 'badge-rejestr-ceidg'}`;
    modalStatusBadge.textContent = status;
    modalStatusBadge.className = `badge ${status === 'AKTYWNY' ? 'badge-active' : (status === 'W LIKWIDACJI' ? 'badge-liquidation' : (status === 'ZAWIESZONY' ? 'badge-suspended' : 'badge-deleted'))}`;

    // Registry links
    let rejestrLinkHtml = '';
    if (rejestr === 'KRS' && krs && krs !== '-') {
        rejestrLinkHtml = `<a href="https://wyszukiwarka-krs.ms.gov.pl/" target="_blank" rel="noopener noreferrer" style="color: var(--accent); font-weight: 600; text-decoration: underline;">Wyszukaj w Portalu Rejestrów Sądowych eKRS &rarr;</a>`;
    } else if (rejestr === 'CEIDG' && nip && nip !== '-') {
        rejestrLinkHtml = `<a href="https://aplikacja.ceidg.gov.pl/ceidg/ceidg.here.public.ui/Search.aspx" target="_blank" rel="noopener noreferrer" style="color: var(--accent); font-weight: 600; text-decoration: underline;">Wyszukaj wpis w Portalu Biznes.gov.pl (CEIDG) &rarr;</a>`;
    }

    modalBody.innerHTML = `
        <!-- Identyfikacja i Podstawowe dane -->
        <div class="modal-section">
            <div class="modal-section-title">🏢 Identyfikacja Podmiotu</div>
            <div class="modal-grid-2">
                <div class="modal-detail-item">
                    <span class="detail-label">Forma prawna</span>
                    <span class="detail-value">${legalForm}</span>
                </div>
                <div class="modal-detail-item">
                    <span class="detail-label">${rejestr === 'KRS' ? 'Numer KRS' : 'Identyfikator CEIDG'}</span>
                    <span class="detail-value" style="font-family: monospace; font-size: 15px;">${krs}</span>
                </div>
                <div class="modal-detail-item">
                    <span class="detail-label">NIP</span>
                    <span class="detail-value" style="font-family: monospace;">${nip}</span>
                </div>
                <div class="modal-detail-item">
                    <span class="detail-label">REGON</span>
                    <span class="detail-value" style="font-family: monospace;">${regon}</span>
                </div>
            </div>
        </div>

        <!-- Kapitał i Daty rejestracyjne -->
        <div class="modal-section">
            <div class="modal-section-title">💰 Kapitał i Rejestracja</div>
            <div class="modal-grid-2">
                ${rejestr === 'KRS' ? `
                <div class="modal-detail-item">
                    <span class="detail-label">Kapitał Zakładowy</span>
                    <span class="detail-value" style="color: var(--accent); font-size: 16px;">${kapital}</span>
                </div>` : ''}
                <div class="modal-detail-item">
                    <span class="detail-label">Data rozpoczęcia / rejestracji</span>
                    <span class="detail-value">${dataRozp}</span>
                </div>
                ${rejestr === 'KRS' && dataOstatniegoWpisu !== '-' ? `
                <div class="modal-detail-item">
                    <span class="detail-label">Data ostatniego wpisu w KRS</span>
                    <span class="detail-value">${dataOstatniegoWpisu}</span>
                </div>` : ''}
                ${rejestr === 'KRS' && stanZDnia !== '-' ? `
                <div class="modal-detail-item">
                    <span class="detail-label">Stan odpisu z dnia</span>
                    <span class="detail-value">${stanZDnia}</span>
                </div>` : ''}
            </div>
        </div>

        <!-- Adres i Siedziba -->
        <div class="modal-section">
            <div class="modal-section-title">📍 Siedziba i Adres</div>
            <div class="modal-grid-2">
                <div class="modal-detail-item" style="grid-column: 1 / -1;">
                    <span class="detail-label">Adres prowadzenia działalności</span>
                    <span class="detail-value">${adresWiersz}</span>
                </div>
                <div class="modal-detail-item">
                    <span class="detail-label">Województwo</span>
                    <span class="detail-value">${woj}</span>
                </div>
                <div class="modal-detail-item">
                    <span class="detail-label">Powiat</span>
                    <span class="detail-value">${powiat}</span>
                </div>
                <div class="modal-detail-item">
                    <span class="detail-label">Gmina</span>
                    <span class="detail-value">${gmina}</span>
                </div>
                <div class="modal-detail-item">
                    <span class="detail-label">Poczta / Kod pocztowy</span>
                    <span class="detail-value">${kodPoczt} ${poczta}</span>
                </div>
            </div>
        </div>

        ${verificationSectionHtml(row)}

        <!-- Działalność gospodarcza (PKD) -->
        <div class="modal-section">
            <div class="modal-section-title">🪵 Działalność Tartaczna i Kody PKD</div>
            <div style="margin-bottom: 12px;">
                <span class="detail-label">Główny kod działalności (PKD)</span>
                <div style="margin-top: 4px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                    <span style="font-weight: 700; font-size: 15px; color: var(--accent);">${pkdMain}</span>
                    ${pkdMatchTypes.includes('przeważające') ? '<span class="badge badge-active">Tartacznictwo (Główne)</span>' : ''}
                    ${pkdMatchTypes.includes('pozostałe') ? '<span class="badge badge-liquidation">Tartacznictwo (Poboczne)</span>' : ''}
                    ${pkdDesc ? `<span style="color: var(--text-muted);">(${pkdDesc})</span>` : ''}
                </div>
            </div>
            ${pkdOtherList.length > 0 ? `
            <div>
                <span class="detail-label">Pozostałe kody PKD w odpisie (${pkdOtherList.length})</span>
                <div style="margin-top: 6px; max-height: 120px; overflow-y: auto;">
                    ${pkdOtherList.map(code => `<span class="pkd-pill">${code}</span>`).join('')}
                </div>
            </div>` : ''}
        </div>

        <!-- Kontakt i status CRM -->
        <div class="modal-section">
            <div class="modal-section-title">📞 Kontakt i Status Lead CRM</div>
            <div class="modal-grid-2">
                <div class="modal-detail-item">
                    <span class="detail-label">Telefon</span>
                    <span class="detail-value">${telefon !== '-' ? `<a href="tel:${telefon}" style="color: inherit;">${telefon}</a>` : '-'}</span>
                </div>
                <div class="modal-detail-item">
                    <span class="detail-label">E-mail</span>
                    <span class="detail-value">${email !== '-' ? `<a href="mailto:${email}" style="color: var(--accent); font-weight: 600;">${email}</a>` : '-'}</span>
                </div>
                <div class="modal-detail-item">
                    <span class="detail-label">Strona WWW</span>
                    <span class="detail-value">${www !== '-' ? `<a href="${www.startsWith('http') ? www : 'http://' + www}" target="_blank" rel="noopener noreferrer" style="color: var(--accent);">${www}</a>` : '-'}</span>
                </div>
                <div class="modal-detail-item">
                    <span class="detail-label">Status kontaktu</span>
                    <label style="display: flex; align-items: center; gap: 8px; margin-top: 4px; cursor: pointer;">
                        <input type="checkbox" id="modalContactCheckbox" data-id="${ceidgId}" ${isContacted ? 'checked' : ''} class="contact-checkbox">
                        <span style="font-weight: 600; color: ${isContacted ? 'var(--success)' : 'var(--text-muted)'};">
                            ${isContacted ? '✓ Oznaczono jako skontaktowane' : 'Oznacz jako skontaktowane'}
                        </span>
                    </label>
                </div>
            </div>
            ${rejestrLinkHtml ? `<div style="margin-top: 14px; padding-top: 10px; border-top: 1px solid var(--border);">${rejestrLinkHtml}</div>` : ''}
        </div>
    `;

    modal.style.display = 'flex';

    // Hook up modal contact checkbox
    const modalCb = document.getElementById('modalContactCheckbox');
    if (modalCb) {
        modalCb.addEventListener('change', (e) => {
            const id = e.target.getAttribute('data-id');
            if (e.target.checked) {
                contactedFirms[id] = true;
            } else {
                delete contactedFirms[id];
            }
            localStorage.setItem('contactedFirms', JSON.stringify(contactedFirms));
            renderTable(); // Update checkbox in table
        });
    }
}

function closeCompanyModal() {
    const modal = document.getElementById('companyModal');
    if (modal) modal.style.display = 'none';
}

function renderCharts() {
    // 1. Prepare Data for Region Chart (based on filteredData)
    const regionCounts = {};
    filteredData.forEach(row => {
        let w = (row['detail.adresDzialalnosci.wojewodztwo'] || 'Inne').toUpperCase();
        if (w === 'NAN') w = 'INNE';
        regionCounts[w] = (regionCounts[w] || 0) + 1;
    });
    
    // Sort regions by count
    const sortedRegions = Object.entries(regionCounts).sort((a,b) => b[1] - a[1]).slice(0, 10);
    
    // Draw Region Chart
    const rCtx = document.getElementById('regionChart').getContext('2d');
    if(regionChartInst) regionChartInst.destroy();
    
    const currentW = (wojewodztwoFilter.value || '').toUpperCase();
    const regionBarColors = sortedRegions.map(i => (currentW && i[0] === currentW) ? '#d97706' : '#b45309');

    regionChartInst = new Chart(rCtx, {
        type: 'bar',
        data: {
            labels: sortedRegions.map(i => i[0]),
            datasets: [{
                label: 'Liczba firm',
                data: sortedRegions.map(i => i[1]),
                backgroundColor: regionBarColors,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            onHover: (event, chartElement) => {
                event.native.target.style.cursor = chartElement[0] ? 'pointer' : 'default';
            },
            onClick: (event, elements) => {
                if (elements && elements.length > 0) {
                    const index = elements[0].index;
                    const clickedRegion = sortedRegions[index][0];
                    if (clickedRegion !== 'INNE') {
                        wojewodztwoFilter.value = (wojewodztwoFilter.value.toUpperCase() === clickedRegion) ? '' : clickedRegion;
                        applyFilters();
                    }
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        footer: () => '💡 Kliknij słupek, aby filtrować województwo'
                    }
                }
            }
        }
    });
    
    // 2. Prepare Data for Year Chart
    // (compute over data matching all filters EXCEPT year filter, so full historical timeline is available to explore)
    const wFilter = wojewodztwoFilter.value.toLowerCase();
    const sFilter = statusFilter.value.toLowerCase();
    const mFilter = miastoFilter.value.toLowerCase();
    const kFilter = kodFilter.value.toLowerCase();
    const term = searchFilter.value.toLowerCase();
    const cFilter = contactedFilter.value;
    const vFilter = vatFilter.value;
    const rFilter = currentRejestrTab;
    const pkdVal = pkdFilter.value.toLowerCase();
    const hideNan = hideNanRegion.checked;

    const yearCounts = {};
    allData.forEach(row => {
        const woj = (row['detail.adresDzialalnosci.wojewodztwo'] || '').toLowerCase();
        const stat = (row['STATUS'] || '').toLowerCase();
        const miasto = (row['detail.adresDzialalnosci.miasto'] || '').toLowerCase();
        const kod = (row['detail.adresDzialalnosci.kod'] || '').toLowerCase();
        const nazwa = (row['NAZWA'] || '').toLowerCase();
        const nip = (row['NIP'] || '').toLowerCase();
        const ceidgId = row['CEIDG_ID'] || row['id'] || nip;
        const rowPkd = (row['PKD_GLOWNE_KOD'] || '').toLowerCase();
        const rejestr = (row['REJESTR'] || 'CEIDG').toUpperCase();
        
        const matchWoj = !wFilter || woj === wFilter;
        const matchStat = sFilter === 'all' || !sFilter || stat === sFilter;
        const matchMiasto = !mFilter || miasto.includes(mFilter);
        const matchKod = !kFilter || kod.includes(kFilter);
        const matchSearch = !term || nazwa.includes(term) || nip.includes(term);
        const matchNan = !hideNan || (woj !== 'nan' && woj !== '');
        const matchPkd = !pkdVal || rowPkd === pkdVal;
        const matchRejestr = rFilter === 'ALL' || rejestr === rFilter;
        const isContacted = !!contactedFirms[ceidgId];
        const matchContacted = cFilter === 'ALL' || (cFilter === 'YES' && isContacted) || (cFilter === 'NO' && !isContacted);
        const matchVat = vFilter === 'ALL' || verificationOf(row) === vFilter;
        
        if (matchWoj && matchStat && matchMiasto && matchKod && matchSearch && matchNan && matchContacted && matchPkd && matchRejestr && matchVat) {
            const y = extractYear(row['detail.dataRozpoczecia']);
            if (y) {
                yearCounts[y] = (yearCounts[y] || 0) + 1;
            }
        }
    });

    const sortedYears = Object.keys(yearCounts).sort();
    const yearData = sortedYears.map(y => yearCounts[y]);

    // Bar colors highlighting selected year
    const yearBarColors = sortedYears.map(y => {
        if (!selectedYearFilter) return 'rgba(16, 185, 129, 0.8)';
        return y === selectedYearFilter ? '#f59e0b' : 'rgba(16, 185, 129, 0.25)';
    });

    const yCtx = document.getElementById('yearChart').getContext('2d');
    if(yearChartInst) yearChartInst.destroy();
    
    yearChartInst = new Chart(yCtx, {
        type: 'bar',
        data: {
            labels: sortedYears,
            datasets: [{
                label: 'Nowe firmy',
                data: yearData,
                backgroundColor: yearBarColors,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            onHover: (event, chartElement) => {
                event.native.target.style.cursor = chartElement[0] ? 'pointer' : 'default';
            },
            onClick: (event, elements) => {
                if (elements && elements.length > 0) {
                    const index = elements[0].index;
                    const clickedYear = sortedYears[index];
                    selectedYearFilter = (selectedYearFilter === clickedYear) ? null : clickedYear;
                    updateYearFilterUI();
                    applyFilters();
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        footer: () => '💡 Kliknij słupek, aby filtrować ten rok'
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false }
                },
                y: {
                    beginAtZero: true
                }
            }
        }
    });
}

// Map Logic
let geoData = null;

function renderMap() {
    if (!geoData) {
        fetch('https://raw.githubusercontent.com/codeforamerica/click_that_hood/master/public/data/poland.geojson')
            .then(res => res.json())
            .then(data => {
                geoData = data;
                drawMap();
            }).catch(err => console.error("Map load error:", err));
    } else {
        drawMap();
    }
}

function drawMap() {
    const container = document.getElementById('map-container');
    const width = container.clientWidth || 600;
    const height = container.clientHeight || 350;
    
    let svg = d3.select('#map-container svg');
    let isNew = false;
    
    if (svg.empty()) {
        svg = d3.select('#map-container')
            .append('svg')
            .attr('width', width)
            .attr('height', height);
        isNew = true;
    }

    const projection = d3.geoMercator()
        .center([19.1451, 52.1]) // Poland center
        .scale(height * 4.8)
        .translate([width / 2, height / 2]);

    const path = d3.geoPath().projection(projection);

    const regionCounts = {};
    filteredData.forEach(row => {
        let w = (row['detail.adresDzialalnosci.wojewodztwo'] || '').toLowerCase();
        if (w && w !== 'nan') {
            w = w.trim();
            regionCounts[w] = (regionCounts[w] || 0) + 1;
        }
    });

    const maxCount = d3.max(Object.values(regionCounts)) || 1;
    
    const colorScale = d3.scaleSequential()
        .interpolator(d3.interpolateYlOrBr)
        .domain([0, maxCount]);

    if (isNew) {
        svg.selectAll('path')
            .data(geoData.features)
            .enter()
            .append('path')
            .attr('d', path)
            .attr('class', 'voivodeship')
            .attr('fill', d => getFillColor(d, regionCounts, colorScale))
            .on('click', (event, d) => {
                const propName = d.properties.name.toUpperCase();
                document.getElementById('wojewodztwoFilter').value = propName;
                applyFilters();
            })
            .append('title')
            .text(d => getTitleText(d, regionCounts));
    } else {
        svg.selectAll('path')
            .transition().duration(300)
            .attr('fill', d => getFillColor(d, regionCounts, colorScale));
            
        svg.selectAll('path title')
            .text(d => getTitleText(d, regionCounts));
    }
}

function getFillColor(d, regionCounts, colorScale) {
    // GeoJSON has properties.name like "Mazowieckie"
    const name = d.properties.name.toLowerCase();
    const count = regionCounts[name] || 0;
    return count > 0 ? colorScale(count) : '#ede5d8';
}

function getTitleText(d, regionCounts) {
    const name = d.properties.name.toLowerCase();
    const count = regionCounts[name] || 0;
    return `${d.properties.name}: ${count} firm`;
}



function verificationSectionHtml(row) {
    const v = row.VER;
    if (!v) return '';
    const item = (label, value) => value ? `
                <div class="modal-detail-item">
                    <span class="detail-label">${label}</span>
                    <span class="detail-value">${value}</span>
                </div>` : '';
    const [badgeClass, badgeText] = VER_BADGES[v.verification];
    return `
        <div class="modal-section">
            <div class="modal-section-title">✅ Weryfikacja (Biała Lista VAT, ${v.checked_on})</div>
            <div class="modal-grid-2">
                ${item('Wynik', `<span class="badge ${badgeClass}">${badgeText}</span>${v.possibly_closed ? ' możliwe zamknięcie działalności' : ''}`)}
                ${item('Status VAT', v.vat_status)}
                ${item('Adres w rejestrze VAT', v.working_address || v.residence_address)}
                ${item('Data rejestracji VAT', v.registration_date)}
                ${item('Data wykreślenia z VAT', v.removal_date)}
                ${item('Podstawa wykreślenia', v.removal_basis)}
                ${item('Data przywrócenia', v.restoration_date)}
                ${item('Reprezentanci', v.representatives)}
                ${item('Wspólnicy', v.partners)}
                ${item('Prokurenci', v.authorized_clerks)}
            </div>
        </div>
    `;
}
