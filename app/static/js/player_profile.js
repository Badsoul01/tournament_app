document.addEventListener("DOMContentLoaded", function() {
    const rankCanvas = document.getElementById('rankChart');
    const pointsCanvas = document.getElementById('pointsChart');

    // Zkontrolujeme, jestli jsme na záložce s grafy a jestli máme k dispozici data
    if (rankCanvas && pointsCanvas && window.playerChartData) {
        const data = window.playerChartData;

        new Chart(rankCanvas, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [{
                    label: 'Konečné umístění v turnaji',
                    data: data.ranks,
                    borderColor: '#1976d2',
                    backgroundColor: 'rgba(25, 118, 210, 0.1)',
                    borderWidth: 2,
                    pointRadius: 4,
                    fill: 'start',
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        reverse: true, // 1. místo je nahoře
                        min: 1,        // Zruší nulu, osa začne natvrdo od 1
                        suggestedMax: 5, // Vytvoří vizuální prostor dolů (dno grafu)
                        title: { display: true, text: 'Umístění' },
                        ticks: { stepSize: 1, precision: 0 }
                    }
                },
                plugins: {
                    title: { display: true, text: 'Vývoj umístění' }
                }
            }
        });

        // Výpočet celkových (kumulativních) a průměrných bodů v JS
        let cumulativePoints = [];
        let averagePoints = [];
        let runningTotal = 0;

        data.points.forEach((pts, index) => {
            runningTotal += pts;
            cumulativePoints.push(runningTotal);
            // Zaokrouhlení průměru na 1 desetinné místo
            averagePoints.push(+(runningTotal / (index + 1)).toFixed(1));
        });

        // 2. GRAF: Bodový vývoj (Čárový - více os)
        new Chart(pointsCanvas, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [
                    {
                        label: 'Celkový počet bodů',
                        data: cumulativePoints,
                        borderColor: '#2e7d32', // Zelená
                        backgroundColor: 'rgba(46, 125, 50, 0.1)',
                        borderWidth: 2,
                        pointRadius: 4,
                        fill: 'start', // Výplň pod čarou celkových bodů
                        tension: 0.1,
                        yAxisID: 'y' // Přiřazeno k levé ose
                    },
                    {
                        label: 'Průměr bodů na turnaj',
                        data: averagePoints,
                        borderColor: '#f57c00', // Oranžová
                        borderDash: [5, 5], // Přerušovaná čára pro odlišení
                        borderWidth: 2,
                        pointRadius: 3,
                        fill: false,
                        tension: 0.1,
                        yAxisID: 'y1' // Přiřazeno k pravé ose
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        title: { display: true, text: 'Celkové body' },
                        beginAtZero: true
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        title: { display: true, text: 'Průměr bodů' },
                        beginAtZero: true,
                        grid: { drawOnChartArea: false } // Vypne mřížku pro pravou osu, aby se nekřížila s levou
                    }
                },
                plugins: {
                    title: { display: true, text: 'Bodový vývoj' }
                }
            }
        });
    }
});

// 3. H2H GRAF: Porovnání umístění na společných turnajích
    const h2hCanvas = document.getElementById('h2hRankChart');
    if (h2hCanvas && window.h2hChartData) {
        const h2hData = window.h2hChartData;

        new Chart(h2hCanvas, {
            type: 'line',
            data: {
                labels: h2hData.labels,
                datasets: [
                    {
                        label: h2hData.playerName,
                        data: h2hData.playerRanks,
                        borderColor: '#1976d2', // Modrá
                        backgroundColor: '#1976d2',
                        borderWidth: 2,
                        tension: 0.1
                    },
                    {
                        label: h2hData.opponentName,
                        data: h2hData.oppRanks,
                        borderColor: '#d32f2f', // Červená
                        backgroundColor: '#d32f2f',
                        borderWidth: 2,
                        tension: 0.1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        reverse: true, // 1. místo je nahoře
                        min: 1,
                        suggestedMax: 5,
                        title: { display: true, text: 'Umístění' },
                        ticks: { stepSize: 1, precision: 0 }
                    }
                },
                plugins: {
                    title: { display: false }
                }
            }
        });
    }