// Polish address formatting, shared by both company cards.
const STREET_PREFIXES = { 'UL.': 'ul.', 'UL': 'ul.', 'AL.': 'al.', 'PL.': 'pl.', 'OS.': 'os.' };
const LOWERCASE_WORDS = new Set(['NAD', 'POD', 'PRZY', 'KOŁO', 'K.', 'W', 'NA']);

// KRS writes places in capitals: only all-caps words change, so house numbers and mixed-case names stay as they are
function nicePlace(text) {
    return String(text || '').trim().split(/\s+/).map((word, i) => {
        const upper = word.toUpperCase();
        if (STREET_PREFIXES[upper]) return STREET_PREFIXES[upper];
        if (word !== upper || /^\d/.test(word) || /^[IVX]+$/.test(word) || !/\p{L}{2}/u.test(word)) return word;
        if (i > 0 && LOWERCASE_WORDS.has(upper)) return word.toLowerCase();
        return word.toLowerCase().replace(/(^|[-(])(\p{L})/gu, (match, before, letter) => before + letter.toUpperCase());
    }).join(' ');
}

// Villages have no street, so the address is "Miejscowość 12". Their post office is often in another town:
// repeating the village after the postal code could name the wrong one, so it shows only when the data has it.
function formatAddress({ street, city, postalCode, postOffice }) {
    const place = nicePlace(city);
    const road = nicePlace(street);
    const houseOnly = /^\d+\p{L}?(\/\S+)?$/u.test(road); // not "3 Maja 5" or "900-lecia 36", which are streets
    const firstLine = houseOnly && place ? `${place} ${road}` : road;
    const isVillage = houseOnly || (place && road.toLowerCase().startsWith(place.toLowerCase()));
    const town = nicePlace(postOffice) || (isVillage ? '' : place);
    const secondLine = [String(postalCode || '').trim(), town].filter(Boolean).join(' ');
    return [firstLine, secondLine].filter(Boolean).join(', ');
}

if (typeof module !== 'undefined') module.exports = { nicePlace, formatAddress };
