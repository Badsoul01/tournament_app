// Globální proměnné pro uložení instancí grafů (abychom je mohli mazat při přenačtení)
let rankChartInstance = null;
let pointsChartInstance = null;
let h2hChartInstance = null;

function initPlayerCharts() {
    // 1. GRAFY PRO VÝVOJ UMÍSTĚNÍ A BODŮ (Obecné informace)
    const rankCanvas = document.getElementById('rankChart');
    const pointsCanvas = document.getElementById('pointsChart');

    if (rankCanvas && pointsCanvas && window.playerChartData) {
        const data = window.playerChartData;

        // Pokud už graf existuje, zničíme ho, než vytvoříme nový
        if (rankChartInstance) rankChartInstance.destroy();
        rankChartInstance = new Chart(rankCanvas, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [
                    {
                        label: 'Umístění v turnaji',
                        data: data.ranks,
                        borderColor: '#1976d2',
                        backgroundColor: 'rgba(25, 118, 210, 0.1)',
                        borderWidth: 2,
                        pointRadius: 4,
                        fill: 'start',
                        tension: 0.1
                    },
                    {
                        label: 'Celkové umístění v žebříčku',
                        data: data.globalRanks,
                        borderColor: '#e91e63',
                        borderWidth: 2,
                        borderDash: [5, 5],
                        pointRadius: 3,
                        fill: false,
                        tension: 0.1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        reverse: true,
                        min: 1,
                        suggestedMax: 5,
                        title: { display: true, text: 'Pozice / Rank' },
                        ticks: { stepSize: 1, precision: 0 }
                    }
                },
                plugins: {
                    title: { display: true, text: 'Vývoj umístění' },
                    tooltip: {
                        callbacks: {
                            title: function(tooltipItems) {
                                const item = tooltipItems[0];
                                if (item.datasetIndex === 1) return '';
                                return item.label;
                            }
                        }
                    }
                }
            }
        });

        let cumulativePoints = [];
        let averagePoints = [];
        let runningTotal = 0;

        data.points.forEach((pts, index) => {
            runningTotal += pts;
            cumulativePoints.push(runningTotal);
            averagePoints.push(+(runningTotal / (index + 1)).toFixed(1));
        });

        if (pointsChartInstance) pointsChartInstance.destroy();
        pointsChartInstance = new Chart(pointsCanvas, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [
                    {
                        label: 'Celkový počet bodů',
                        data: cumulativePoints,
                        borderColor: '#2e7d32',
                        backgroundColor: 'rgba(46, 125, 50, 0.1)',
                        borderWidth: 2,
                        pointRadius: 4,
                        fill: 'start',
                        tension: 0.1,
                        yAxisID: 'y'
                    },
                    {
                        label: 'Průměr bodů na turnaj',
                        data: averagePoints,
                        borderColor: '#f57c00',
                        borderDash: [5, 5],
                        borderWidth: 2,
                        pointRadius: 3,
                        fill: false,
                        tension: 0.1,
                        yAxisID: 'y1'
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
                        grid: { drawOnChartArea: false }
                    }
                },
                plugins: {
                    title: { display: true, text: 'Bodový vývoj' }
                }
            }
        });
    }

    // 2. H2H GRAF: Porovnání umístění na společných turnajích
    const h2hCanvas = document.getElementById('h2hRankChart');
    if (h2hCanvas && window.h2hChartData) {
        const h2hData = window.h2hChartData;

        if (h2hChartInstance) h2hChartInstance.destroy();
        h2hChartInstance = new Chart(h2hCanvas, {
            type: 'line',
            data: {
                labels: h2hData.labels,
                datasets: [
                    {
                        label: h2hData.playerName,
                        data: h2hData.playerRanks,
                        borderColor: '#1976d2',
                        backgroundColor: '#1976d2',
                        borderWidth: 2,
                        tension: 0.1
                    },
                    {
                        label: h2hData.opponentName,
                        data: h2hData.oppRanks,
                        borderColor: '#d32f2f',
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
                        reverse: true,
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
}

// Spustit při klasickém načtení stránky
document.addEventListener("DOMContentLoaded", initPlayerCharts);

// Spustit pokaždé, když HTMX vymění část obsahu (např. po přepnutí záložky nebo výběru soupeře v H2H)
document.addEventListener("htmx:afterSettle", initPlayerCharts);