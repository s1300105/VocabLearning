// グローバル変数でチャートインスタンスを保持
let wordFrequencyChart = null;

document.addEventListener('DOMContentLoaded', function() {
    initializeWordFrequencyChart();
    initializeAccordion();
});

function initializeWordFrequencyChart() {
    const canvas = document.getElementById('wordFrequencyChart');
    if (!canvas) return;

    // 既存のチャートがある場合は破棄
    if (wordFrequencyChart) {
        wordFrequencyChart.destroy();
    }

    const ctx = canvas.getContext('2d');
    
    // データの取得
    const words = Array.from(document.querySelectorAll('.frequency-table tbody tr')).map(
        row => row.cells[0].textContent
    );
    const counts = Array.from(document.querySelectorAll('.frequency-table tbody tr')).map(
        row => parseInt(row.cells[1].textContent)
    );

    // チャートの色設定
    const colors = [
        'rgba(255, 99, 132, 0.8)',
        'rgba(54, 162, 235, 0.8)',
        'rgba(255, 206, 86, 0.8)',
        'rgba(75, 192, 192, 0.8)',
        'rgba(153, 102, 255, 0.8)'
    ];

    // チャートの作成
    wordFrequencyChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: words,
            datasets: [{
                label: 'Word Frequency',
                data: counts,
                backgroundColor: colors,
                borderColor: colors.map(color => color.replace('0.8', '1')),
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `Frequency: ${context.raw}`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1
                    }
                }
            },
            animation: {
                duration: 1500,
                easing: 'easeInOutQuart'
            }
        }
    });
}

function initializeAccordion() {
    // アコーディオンの動作をカスタマイズ
    const accordionItems = document.querySelectorAll('.accordion-item');
    
    accordionItems.forEach(item => {
        const header = item.querySelector('.accordion-button');
        const content = item.querySelector('.accordion-collapse');
        
        header.addEventListener('click', () => {
            // コンテンツの表示/非表示時のアニメーション
            if (content.classList.contains('show')) {
                content.style.maxHeight = content.scrollHeight + 'px';
                setTimeout(() => {
                    content.style.maxHeight = '0px';
                }, 0);
            } else {
                content.style.maxHeight = content.scrollHeight + 'px';
            }
        });
    });
}

// テーブルのソート機能
function initializeTableSort() {
    const tables = document.querySelectorAll('.pos-table, .frequency-table, .pos-ranking-table');
    
    tables.forEach(table => {
        const headers = table.querySelectorAll('th');
        headers.forEach((header, index) => {
            header.addEventListener('click', () => {
                sortTable(table, index);
            });
            header.style.cursor = 'pointer';
        });
    });
}

function sortTable(table, column) {
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const isNumeric = column === 1; // Count列は数値でソート
    
    rows.sort((a, b) => {
        const aValue = a.cells[column].textContent;
        const bValue = b.cells[column].textContent;
        
        if (isNumeric) {
            return parseInt(bValue) - parseInt(aValue);
        }
        return aValue.localeCompare(bValue);
    });
    
    // ソート後のテーブルを再構築
    rows.forEach(row => tbody.appendChild(row));
}

// 検索機能
function initializeSearch() {
    const searchInputs = document.querySelectorAll('.search-input');
    
    searchInputs.forEach(input => {
        input.addEventListener('input', (e) => {
            const searchTerm = e.target.value.toLowerCase();
            const table = input.closest('.card').querySelector('table');
            const rows = table.querySelectorAll('tbody tr');
            
            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(searchTerm) ? '' : 'none';
            });
        });
    });
}