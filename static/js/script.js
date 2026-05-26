// Blood Management System - Helper Functions

// Initialize tooltips
document.addEventListener('DOMContentLoaded', function() {
    // Bootstrap tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
});

// Format blood requests with colors
function formatUrgency(urgency) {
    const urgencyMap = {
        'normal': { color: '#17A2B8', icon: 'circle', text: 'Normal' },
        'urgent': { color: '#FFC107', icon: 'exclamation-circle', text: 'Urgent' },
        'critical': { color: '#DC3545', icon: 'exclamation-triangle', text: 'Critical' }
    };
    
    return urgencyMap[urgency] || urgencyMap['normal'];
}

// Format status badges
function formatStatus(status) {
    const statusMap = {
        'pending': { class: 'status-pending', text: 'Pending' },
        'approved': { class: 'status-approved', text: 'Approved' },
        'rejected': { class: 'status-rejected', text: 'Rejected' }
    };
    
    return statusMap[status] || statusMap['pending'];
}

// Format blood group badges
function formatBloodGroup(group) {
    return `<span class="blood-group-badge">${group}</span>`;
}

// Display notification
function showNotification(message, type = 'success') {
    const alertHTML = `
        <div class="alert alert-${type} alert-dismissible fade show" role="alert" style="position: fixed; top: 20px; right: 20px; z-index: 9999; width: 300px;">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', alertHTML);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        const alert = document.querySelector('.alert');
        if (alert) {
            alert.remove();
        }
    }, 5000);
}

// Check blood availability
function checkBloodAvailability(bloodGroup) {
    // This would call an API endpoint in production
    const availability = {
        'O+': 45,
        'O-': 38,
        'A+': 52,
        'A-': 30,
        'B+': 48,
        'B-': 35,
        'AB+': 42,
        'AB-': 28
    };
    
    return availability[bloodGroup] || 0;
}

// Validate email
function validateEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
}

// Validate phone
function validatePhone(phone) {
    const re = /^[0-9]{10,}$/;
    return re.test(phone.replace(/\D/g, ''));
}

// Format date
function formatDate(date) {
    const options = { year: 'numeric', month: 'long', day: 'numeric' };
    return new Date(date).toLocaleDateString(undefined, options);
}

// Light/Dark mode toggle
function toggleTheme() {
    const currentTheme = localStorage.getItem('theme') || 'light';
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    localStorage.setItem('theme', newTheme);
    
    if (newTheme === 'dark') {
        document.body.style.backgroundColor = '#1a1a1a';
        document.body.style.color = '#ffffff';
    } else {
        document.body.style.backgroundColor = '#f8f9fa';
        document.body.style.color = '#343A40';
    }
}

// Export data to CSV
function exportToCSV(data, filename) {
    let csv = [];
    
    // Headers
    if (data.length > 0) {
        csv.push(Object.keys(data[0]).join(','));
    }
    
    // Data
    data.forEach(row => {
        csv.push(Object.values(row).join(','));
    });
    
    // Download
    const csvContent = csv.join('\n');
    const element = document.createElement('a');
    element.setAttribute('href', 'data:text/csv;charset=utf-8,' + encodeURIComponent(csvContent));
    element.setAttribute('download', filename);
    element.style.display = 'none';
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
}

// Print report
function printReport(element) {
    const printWindow = window.open('', '_blank');
    const content = document.querySelector(element).innerHTML;
    
    printWindow.document.write(`
        <html>
        <head>
            <title>Blood Management Report</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            <link rel="stylesheet" href="/static/css/style.css">
        </head>
        <body>
            ${content}
        </body>
        </html>
    `);
    
    printWindow.document.close();
    setTimeout(() => printWindow.print(), 250);
}

// Search filter
function filterTable(inputId, tableId) {
    const input = document.getElementById(inputId);
    const table = document.getElementById(tableId);
    const rows = table.querySelectorAll('tbody tr');
    const filter = input.value.toLowerCase();
    
    rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(filter) ? '' : 'none';
    });
}
