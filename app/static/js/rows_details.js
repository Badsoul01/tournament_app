function toggleTournamentDetails(button, tournamentId) {
    const row = document.getElementById(`detail-row-${tournamentId}`);

    // Pokud je řádek viditelný, tak ho zavřeme
    if (row.style.display !== "none" && row.innerHTML.trim() !== "") {
        row.style.display = "none";
        row.innerHTML = "";
        button.innerText = "Detaily ▼";
    } else {
        // Jinak ho otevřeme a stáhneme data přes HTMX
        htmx.ajax('GET', `/stats/tournament/${tournamentId}/details`, {target: `#detail-row-${tournamentId}`, swap: 'outerHTML'})
            .then(() => {
                button.innerText = "Zavřít ▴";
            });
    }
}

function toggleMatchDetails(button, matchId) {
    const row = document.getElementById(`match-detail-${matchId}`);
    const baseScore = button.innerText.replace(" ▼", "").replace(" ▴", "");

    if (row.style.display !== "none" && row.innerHTML.trim() !== "") {
        row.style.display = "none";
        row.innerHTML = "";
        button.innerText = baseScore + " ▼";
    } else {
        htmx.ajax('GET', `/stats/match/${matchId}`, {target: `#match-detail-${matchId}`, swap: 'outerHTML'})
            .then(() => {
                button.innerText = baseScore + " ▴";
            });
    }
}