// playoff.js - Zachování pozice horizontálního scrollu pro všechny .bracket bloky v playoff

document.addEventListener('htmx:configRequest', function(evt) {
    // Uložíme pozice všech .bracket prvků na stránce do objektu podle jejich indexu
    const brackets = document.querySelectorAll('.bracket');
    window.savedBracketScrolls = [];
    brackets.forEach(bracket => {
        window.savedBracketScrolls.push(bracket.scrollLeft);
    });
});

document.addEventListener('htmx:afterSettle', function(evt) {
    // Vrátíme pozice zpět na své místo pro každý .bracket prvek
    const brackets = document.querySelectorAll('.bracket');
    if (window.savedBracketScrolls) {
        brackets.forEach((bracket, index) => {
            if (window.savedBracketScrolls[index] !== undefined) {
                bracket.scrollLeft = window.savedBracketScrolls[index];
            }
        });
    }
});