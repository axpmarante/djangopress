/**
 * Quick edit or three directions? A guess shown under the Chat input; the
 * server makes the same call (editor_v2/chat.py classify_intent — keep the two
 * lists in step) and asks the router when neither matches.
 */
const EXPLORE_RE = /eleg|redesenh|redesign|refaz|rethink|repens|modern|ideia|idea|\bopc|option|proposta|direc|direction|diferente|different|inspir|surpreend|surprise|criativ|creative|premium|sofistic|sophistic|luxo|luxur|layout|\b3\b|\btres\b|\bthree\b|variac|variation|alternativ/;
const QUICK_RE = /\bcor\b|\bcores\b|colou?r|dourad|\bgold|vermelh|\bred\b|azul|\bblue|verde|green|\bpret|black|branc|white|maior|menor|bigger|smaller|larger|tamanho|\bsize|padding|margin|espac|spacing|negrito|\bbold\b|italic|sublinh|underline|centr|center|alinh|align|arredond|rounded|sombra|shadow|fonte|\bfont|esconde|\bhide|\btexto\b|\btext\b|troca|replace/;

function plain(text) {
    return (text || '').toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '');
}

/** 'explore' | 'quick' | null — explore wins when both match. */
export function classifyIntent(text) {
    const t = plain(text);
    if (EXPLORE_RE.test(t)) return 'explore';
    if (QUICK_RE.test(t)) return 'quick';
    return null;
}

export function intentLabel(mode, guess) {
    if (mode === 'quick') return 'Quick edit';
    if (mode === 'explore') return '3 directions';
    if (guess === 'explore') return 'Auto · 3 directions';
    if (guess === 'quick') return 'Auto · quick edit';
    return 'Auto';
}
