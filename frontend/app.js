// State Management
let currentOrgId = localStorage.getItem('currentOrgId') || null;
let trafficChart = null;

// Selectors
const viewTitle = document.getElementById('view-title');
const contentArea = document.getElementById('content-area');
const orgSelector = document.getElementById('org-selector');
const modalContainer = document.getElementById('modal-container');
const revealModal = document.getElementById('reveal-modal');

// API Base
const API_BASE = '/api/v1';

// Initialization
document.addEventListener('DOMContentLoaded', async () => {
    setupNavigation();
    await loadOrganizations();
    await refreshStats();
    initChart();
    
    // Auto-refresh stats every 30s
    setInterval(refreshStats, 30000);
});

// Navigation Handling
function setupNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const view = item.getAttribute('data-view');
            
            // UI Toggle
            navItems.forEach(nav => nav.classList.remove('active'));
            item.classList.add('active');
            
            // View Toggle
            document.querySelectorAll('.view-panel').forEach(panel => panel.classList.remove('active'));
            const targetPanel = document.getElementById(`${view}-view`);
            if (targetPanel) {
                targetPanel.classList.add('active');
                viewTitle.innerText = item.querySelector('span').innerText;
                
                if (view === 'keys') loadKeys();
                if (view === 'dashboard') refreshStats();
            }
        });
    });

    // Close Modals
    document.querySelector('.close-modal').addEventListener('click', closeModal);
    document.getElementById('modal-cancel').addEventListener('click', closeModal);
    document.getElementById('btn-close-reveal').addEventListener('click', () => {
        revealModal.classList.remove('active');
    });

    // Create Actions
    document.getElementById('btn-create-key')?.addEventListener('click', showCreateKeyModal);
    document.getElementById('btn-create-key-quick')?.addEventListener('click', showCreateKeyModal);
    document.getElementById('btn-create-org-quick')?.addEventListener('click', showCreateOrgModal);
}

// Data Fetching
async function loadOrganizations() {
    try {
        const response = await fetch(`${API_BASE}/admin/organizations`);
        const orgs = await response.json();
        
        orgSelector.innerHTML = '<option value="">Select Organization</option>';
        orgs.forEach(org => {
            const option = document.createElement('option');
            option.value = org.id;
            option.textContent = org.name;
            if (org.id === currentOrgId) option.selected = true;
            orgSelector.appendChild(option);
        });

        orgSelector.addEventListener('change', (e) => {
            currentOrgId = e.target.value;
            localStorage.setItem('currentOrgId', currentOrgId);
            if (document.getElementById('keys-view').classList.contains('active')) {
                loadKeys();
            }
        });
    } catch (error) {
        console.error('Failed to load orgs:', error);
    }
}

async function refreshStats() {
    try {
        const response = await fetch(`${API_BASE}/admin/stats`);
        const stats = await response.json();
        
        document.getElementById('stat-requests').textContent = stats.total_requests.toLocaleString();
        document.getElementById('stat-keys').textContent = stats.total_keys;
        document.getElementById('stat-latency').textContent = `${stats.avg_latency_ms}ms`;
    } catch (error) {
        console.error('Failed to fetch stats:', error);
    }
}

async function loadKeys() {
    if (!currentOrgId) {
        document.querySelector('#keys-table tbody').innerHTML = '<tr><td colspan="6" style="text-align:center">Please select an organization first.</td></tr>';
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/admin/keys/${currentOrgId}`);
        const keys = await response.json();
        const tbody = document.querySelector('#keys-table tbody');
        
        tbody.innerHTML = '';
        keys.forEach(key => {
            const row = document.createElement('tr');
            const created = new Date(key.created_at).toLocaleDateString();
            row.innerHTML = `
                <td>${key.label}</td>
                <td>${key.prefix}***</td>
                <td><span class="status-badge ${key.is_active ? 'active' : 'revoked'}">${key.is_active ? 'Active' : 'Revoked'}</span></td>
                <td>${created}</td>
                <td>
                    <button class="btn btn-sm btn-outline" onclick="revokeKey('${key.id}')" ${!key.is_active ? 'disabled' : ''}>
                        <i class="fas fa-ban"></i> Revoke
                    </button>
                </td>
            `;
            tbody.appendChild(row);
        });
    } catch (error) {
        console.error('Failed to load keys:', error);
    }
}

// Mutations
async function createOrg(name) {
    const response = await fetch(`${API_BASE}/admin/organizations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
    });
    await loadOrganizations();
    closeModal();
}

async function createKey(label, rateLimit) {
    if (!currentOrgId) return alert('Select an organization first');
    
    const response = await fetch(`${API_BASE}/admin/keys`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            org_id: currentOrgId, 
            label, 
            rate_limit_per_minute: rateLimit,
            scopes: ["read", "write"]
        })
    });
    
    if (response.ok) {
        const data = await response.json();
        showRevealModal(data.raw_key);
        loadKeys();
        closeModal();
        refreshStats();
    }
}

window.revokeKey = async (keyId) => {
    if (!confirm('Are you sure you want to revoke this key? This action is permanent.')) return;
    
    const response = await fetch(`${API_BASE}/admin/keys/${keyId}`, { method: 'DELETE' });
    if (response.ok) {
        loadKeys();
    }
};

// Modal Logic
function showCreateKeyModal() {
    const body = document.getElementById('modal-body');
    document.getElementById('modal-title').textContent = 'Create New API Key';
    
    body.innerHTML = `
        <div class="input-group">
            <label class="input-label">Key Label</label>
            <input type="text" id="new-key-label" class="input-field" placeholder="e.g. Production Mobile App">
        </div>
        <div class="input-group">
            <label class="input-label">Rate Limit (req/min)</label>
            <input type="number" id="new-key-limit" class="input-field" value="60">
        </div>
    `;
    
    document.getElementById('modal-confirm').onclick = () => {
        const label = document.getElementById('new-key-label').value;
        const limit = document.getElementById('new-key-limit').value;
        createKey(label, limit);
    };
    
    modalContainer.classList.add('active');
}

function showCreateOrgModal() {
    const body = document.getElementById('modal-body');
    document.getElementById('modal-title').textContent = 'Register New Organization';
    
    body.innerHTML = `
        <div class="input-group">
            <label class="input-label">Organization Name</label>
            <input type="text" id="new-org-name" class="input-field" placeholder="e.g. Pied Piper">
        </div>
    `;
    
    document.getElementById('modal-confirm').onclick = () => {
        const name = document.getElementById('new-org-name').value;
        createOrg(name);
    };
    
    modalContainer.classList.add('active');
}

function closeModal() {
    modalContainer.classList.remove('active');
}

function showRevealModal(key) {
    document.getElementById('raw-key-value').textContent = key;
    revealModal.classList.add('active');
    
    document.getElementById('btn-copy-key').onclick = () => {
        navigator.clipboard.writeText(key);
        alert('Key copied to clipboard');
    };
}

// Chart Initialization
function initChart() {
    const ctx = document.getElementById('traffic-chart').getContext('2d');
    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, 'rgba(139, 92, 246, 0.4)');
    gradient.addColorStop(1, 'rgba(139, 92, 246, 0)');

    trafficChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: Array.from({length: 24}, (_, i) => `${i}:00`),
            datasets: [{
                label: 'Requests/sec',
                data: Array.from({length: 24}, () => Math.floor(Math.random() * 50) + 10),
                borderColor: '#8B5CF6',
                backgroundGradient: gradient,
                fill: true,
                backgroundColor: gradient,
                tension: 0.4,
                pointRadius: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { display: false }, ticks: { color: '#94A3B8' } },
                y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94A3B8' } }
            }
        }
    });
}
