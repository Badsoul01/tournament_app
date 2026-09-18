// Funkce pro zobrazení svitku (s podporou pro 'success' i 'error')
function showScrollToast(message, type = 'success') {
    const container = document.getElementById('scroll-toast-container');
    if (!container) return;

    let borderColor = 'var(--winner-color)';
    if (type === 'error') borderColor = 'var(--danger-color)';
    else if (type === 'info') borderColor = 'var(--accent-silver)';

    const toast = document.createElement('div');
    toast.style.cssText = `
        background-color: var(--bg-card);
        border: 1px solid var(--border-color);
        color: var(--text-main);
        padding: 12px 18px;
        border-radius: 6px;
        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.7);
        font-size: 0.95em;
        display: flex;
        align-items: center;
        gap: 10px;
        opacity: 0;
        transform: translateY(20px);
        transition: all 0.35s cubic-bezier(0.16, 1, 0.3, 1);
        pointer-events: auto;
        max-width: 320px;
        border-left: 3px solid ${borderColor};
    `;

    toast.innerHTML = `
        <span style="font-size: 1.2em;">${type === 'error' ? '⚠️' : '📜'}</span>
        <span style="flex-grow: 1;">${message}</span>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '1';
        toast.style.transform = 'translateY(0)';
    }, 10);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(15px)';
        setTimeout(() => toast.remove(), 350);
    }, 4000);
}

// Naslouchání na HTMX událost z Flasku s dekódováním diakritiky
document.body.addEventListener('showToast', function(evt) {
    const decodedMessage = decodeURIComponent(evt.detail.value);
    showScrollToast(decodedMessage, 'success');
});

// Funkce pro kontrolu playoff zápasu (zákaz remízy pro HTMX)
function validatePlayoffMatch(formElement) {
    const gameAInputs = formElement.querySelectorAll('input[name="game_a[]"]');
    const gameBInputs = formElement.querySelectorAll('input[name="game_b[]"]');

    let setsA = 0;
    let setsB = 0;
    let filledSets = 0;

    for (let i = 0; i < gameAInputs.length; i++) {
        const valA = parseInt(gameAInputs[i].value);
        const valB = parseInt(gameBInputs[i].value);

        if (!isNaN(valA) && !isNaN(valB) && gameAInputs[i].value !== '' && gameBInputs[i].value !== '') {
            filledSets++;
            if (valA > valB) setsA++;
            else if (valB > valA) setsB++;
        }
    }

    if (filledSets > 0 && setsA === setsB) {
        showScrollToast("V playoff nemůže zápas skončit remízou!", "error");
        return false; // Neplatné
    }

    return true; // Platné
}