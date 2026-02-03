/**
 * Health Dashboard - Auto-refreshing dashboard for system health monitoring
 * 
 * Fetches data from GET /health/dashboard endpoint every 30 seconds
 * and updates the UI with server and VM health information.
 */

(function() {
    'use strict';

    // Configuration
    const REFRESH_INTERVAL = 30000; // 30 seconds
    const API_ENDPOINT = '/health/dashboard';

    // State
    let refreshInterval = null;
    let isRefreshing = false;

    // DOM Elements
    const loadingState = document.getElementById('loadingState');
    const errorState = document.getElementById('errorState');
    const dashboardContent = document.getElementById('dashboardContent');
    const emptyState = document.getElementById('emptyState');
    const statusBanner = document.getElementById('statusBanner');
    const overallStatusText = document.getElementById('overallStatusText');
    const lastUpdated = document.getElementById('lastUpdated');
    const refreshSpinner = document.getElementById('refreshSpinner');
    const statsSection = document.getElementById('statsSection');
    const serversGrid = document.getElementById('serversGrid');
    const serversCount = document.getElementById('serversCount');

    /**
     * Initialize the dashboard
     */
    function initDashboard() {
        // Fetch data immediately
        fetchDashboardData();

        // Set up auto-refresh
        refreshInterval = setInterval(() => {
            if (!isRefreshing) {
                fetchDashboardData();
            }
        }, REFRESH_INTERVAL);

        // Cleanup on page unload
        window.addEventListener('beforeunload', () => {
            if (refreshInterval) {
                clearInterval(refreshInterval);
            }
        });
    }

    /**
     * Fetch dashboard data from API
     */
    async function fetchDashboardData() {
        if (isRefreshing) {
            return; // Prevent concurrent requests
        }

        isRefreshing = true;
        refreshSpinner.classList.remove('hidden');

        try {
            const response = await fetch(API_ENDPOINT, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                },
                cache: 'no-cache',
                credentials: 'same-origin' // Include cookies for session auth
            });

            // Check if response is HTML (redirect to login)
            const contentType = response.headers.get('content-type') || '';
            if (contentType.includes('text/html')) {
                // Got HTML instead of JSON - likely redirected to login
                if (response.status === 303 || response.status === 401) {
                    window.location.href = '/login';
                    return;
                }
                throw new Error('Received HTML instead of JSON. Please refresh the page.');
            }

            if (!response.ok) {
                if (response.status === 401 || response.status === 303) {
                    // Redirect to login if not authenticated
                    window.location.href = '/login';
                    return;
                }
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            // Parse JSON response
            const text = await response.text();
            let data;
            try {
                data = JSON.parse(text);
            } catch (parseError) {
                // If it's HTML, redirect to login
                if (text.trim().startsWith('<!DOCTYPE') || text.trim().startsWith('<html')) {
                    window.location.href = '/login';
                    return;
                }
                throw new Error('Invalid JSON response from server');
            }

            updateDashboard(data);
            hideError();

        } catch (error) {
            console.error('Error fetching dashboard data:', error);
            showError(`Failed to load dashboard: ${error.message}`);
        } finally {
            isRefreshing = false;
            refreshSpinner.classList.add('hidden');
        }
    }

    /**
     * Update dashboard with new data
     */
    function updateDashboard(data) {
        // Hide loading state
        loadingState.style.display = 'none';
        dashboardContent.style.display = 'block';

        // Update overall status
        updateOverallStatus(data.overallStatus, data.lastUpdated);

        // Update statistics
        updateStatistics(data.statistics);

        // Update servers
        updateServers(data.servers);

        // Show/hide empty state
        if (!data.servers || data.servers.length === 0) {
            emptyState.style.display = 'block';
            serversGrid.style.display = 'none';
        } else {
            emptyState.style.display = 'none';
            serversGrid.style.display = 'grid';
        }
    }

    /**
     * Update overall status banner
     */
    function updateOverallStatus(status, lastUpdatedTime) {
        // Update status text
        const statusText = status.charAt(0).toUpperCase() + status.slice(1);
        overallStatusText.textContent = `System Status: ${statusText}`;

        // Update banner class
        statusBanner.className = `status-banner ${status}`;

        // Update last updated time
        if (lastUpdatedTime) {
            const date = new Date(lastUpdatedTime);
            const formatted = date.toLocaleString();
            lastUpdated.textContent = formatted;
        }
    }

    /**
     * Update statistics cards - Grouped design
     */
    function updateStatistics(stats) {
        if (!stats) return;

        const totalServers = stats.totalServers || 0;
        const healthyServers = stats.healthyServers || 0;
        const unhealthyServers = stats.unhealthyServers || 0;
        const downServers = stats.downServers || 0;

        const totalVms = stats.totalVms || 0;
        const healthyVms = stats.healthyVms || 0;
        const unhealthyVms = stats.unhealthyVms || 0;
        const idleVms = stats.idleVms || 0;

        const vmsProcessing = stats.vmsProcessing || 0;
        const workflowRunning = stats.vmsWithWorkflowRunning || 0;
        const workflowStopped = stats.vmsWithWorkflowStopped || 0;

        // Calculate percentages for trends
        const serverHealthPercent = totalServers > 0 ? Math.round((healthyServers / totalServers) * 100) : 0;
        const vmHealthPercent = totalVms > 0 ? Math.round((healthyVms / totalVms) * 100) : 0;
        const processingPercent = totalVms > 0 ? Math.round((vmsProcessing / totalVms) * 100) : 0;

        statsSection.innerHTML = `
            <div class="stats-group">
                <!-- Servers Group -->
                <div class="stats-group-card servers">
                    <div class="stats-group-header">
                        <div class="stats-group-icon">🖥️</div>
                        <div>
                            <div class="stats-group-title">Servers</div>
                            <div class="stats-group-subtitle">${totalServers} total • ${serverHealthPercent}% healthy</div>
                        </div>
                    </div>
                    <div class="stats-items">
                        <div class="stat-item">
                            <div class="stat-item-label">
                                <span class="stat-item-icon">📊</span>
                                <span>Total</span>
                            </div>
                            <div class="stat-item-value neutral">${totalServers}</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-item-label">
                                <span class="stat-item-icon">✅</span>
                                <span>Healthy</span>
                            </div>
                            <div class="stat-item-value healthy">${healthyServers}</div>
                            ${totalServers > 0 ? `<div class="stat-item-trend">${serverHealthPercent}% of total</div>` : ''}
                        </div>
                        <div class="stat-item">
                            <div class="stat-item-label">
                                <span class="stat-item-icon">⚠️</span>
                                <span>Unhealthy</span>
                            </div>
                            <div class="stat-item-value ${unhealthyServers > 0 ? 'danger' : 'neutral'}">${unhealthyServers}</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-item-label">
                                <span class="stat-item-icon">🔴</span>
                                <span>Down</span>
                            </div>
                            <div class="stat-item-value ${downServers > 0 ? 'danger' : 'neutral'}">${downServers}</div>
                        </div>
                    </div>
                </div>

                <!-- VMs Group -->
                <div class="stats-group-card vms">
                    <div class="stats-group-header">
                        <div class="stats-group-icon">💻</div>
                        <div>
                            <div class="stats-group-title">Virtual Machines</div>
                            <div class="stats-group-subtitle">${totalVms} total • ${vmHealthPercent}% healthy</div>
                        </div>
                    </div>
                    <div class="stats-items">
                        <div class="stat-item">
                            <div class="stat-item-label">
                                <span class="stat-item-icon">📊</span>
                                <span>Total</span>
                            </div>
                            <div class="stat-item-value neutral">${totalVms}</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-item-label">
                                <span class="stat-item-icon">✅</span>
                                <span>Healthy</span>
                            </div>
                            <div class="stat-item-value healthy">${healthyVms}</div>
                            ${totalVms > 0 ? `<div class="stat-item-trend">${vmHealthPercent}% of total</div>` : ''}
                        </div>
                        <div class="stat-item">
                            <div class="stat-item-label">
                                <span class="stat-item-icon">⚠️</span>
                                <span>Unhealthy</span>
                            </div>
                            <div class="stat-item-value ${unhealthyVms > 0 ? 'danger' : 'neutral'}">${unhealthyVms}</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-item-label">
                                <span class="stat-item-icon">😴</span>
                                <span>Idle</span>
                            </div>
                            <div class="stat-item-value ${idleVms > 0 ? 'warning' : 'neutral'}">${idleVms}</div>
                        </div>
                    </div>
                </div>

                <!-- Processing Group -->
                <div class="stats-group-card processing">
                    <div class="stats-group-header">
                        <div class="stats-group-icon">⚙️</div>
                        <div>
                            <div class="stats-group-title">Processing Status</div>
                            <div class="stats-group-subtitle">${processingPercent}% active • ${workflowRunning} AI Agent Workflow running</div>
                        </div>
                    </div>
                    <div class="stats-items">
                        <div class="stat-item">
                            <div class="stat-item-label">
                                <span class="stat-item-icon">🔄</span>
                                <span>Processing</span>
                            </div>
                            <div class="stat-item-value healthy">${vmsProcessing}</div>
                            ${totalVms > 0 ? `<div class="stat-item-trend">${processingPercent}% active</div>` : ''}
                        </div>
                        <div class="stat-item">
                            <div class="stat-item-label">
                                <span class="stat-item-icon">▶️</span>
                                <span>AI Agent Workflow Running</span>
                            </div>
                            <div class="stat-item-value healthy">${workflowRunning}</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-item-label">
                                <span class="stat-item-icon">⏸️</span>
                                <span>AI Agent Workflow Stopped</span>
                            </div>
                            <div class="stat-item-value ${workflowStopped > 0 ? 'warning' : 'neutral'}">${workflowStopped}</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-item-label">
                                <span class="stat-item-icon">📈</span>
                                <span>Health Rate</span>
                            </div>
                            <div class="stat-item-value ${vmHealthPercent >= 90 ? 'healthy' : vmHealthPercent >= 70 ? 'warning' : 'danger'}">${vmHealthPercent}%</div>
                            <div class="stat-item-trend">Overall system health</div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Update servers list
     */
    function updateServers(servers) {
        if (!servers || servers.length === 0) {
            serversGrid.innerHTML = '';
            serversCount.textContent = '(0)';
            return;
        }

        serversCount.textContent = `(${servers.length})`;

        serversGrid.innerHTML = servers.map((server, index) => {
            const serverClass = server.status || 'unknown';
            const vmCount = server.vmCount || 0;
            const healthyVmCount = server.healthyVmCount || 0;
            const cpuUsage = server.cpuUsage !== null && server.cpuUsage !== undefined ? server.cpuUsage.toFixed(1) : 'N/A';
            const memoryUsage = server.memoryUsage !== null && server.memoryUsage !== undefined ? server.memoryUsage.toFixed(1) : 'N/A';
            const diskUsage = server.diskUsage !== null && server.diskUsage !== undefined ? server.diskUsage.toFixed(1) : 'N/A';
            const lastHeartbeat = server.lastHeartbeat ? formatDate(server.lastHeartbeat) : 'Never';

            const vmsHtml = (server.vms || []).map(vm => {
                const vmStatusClass = vm.status || 'unknown';
                const workflowStatus = vm.workflowStatus || 'N/A';
                const processingQueue = vm.processingQueueId ? 'Yes' : 'No';

                return `
                    <div class="vm-item">
                        <div class="vm-info">
                            <div class="vm-id">${escapeHtml(vm.vmId)}</div>
                            <div class="vm-details">
                                <span class="vm-status-badge ${vmStatusClass}">${escapeHtml(vm.status || 'unknown')}</span>
                                <span>AI Agent Workflow: ${escapeHtml(workflowStatus)}</span>
                                ${vm.processingQueueId ? `<span>Processing: ${escapeHtml(processingQueue)}</span>` : ''}
                            </div>
                        </div>
                    </div>
                `;
            }).join('');

            return `
                <div class="server-card ${serverClass}" data-server-index="${index}">
                    <div class="server-header" onclick="toggleServer(${index})">
                        <div class="server-info">
                            <div class="server-id">${escapeHtml(server.serverId)}</div>
                            <div class="server-meta">
                                <span>${vmCount} VMs</span>
                                <span>${healthyVmCount} healthy</span>
                                <span>Last: ${lastHeartbeat}</span>
                            </div>
                        </div>
                        <div>
                            <span class="server-status-badge ${serverClass}">${escapeHtml(server.status || 'unknown')}</span>
                            <span class="server-toggle">▼</span>
                        </div>
                    </div>
                    <div class="server-body">
                        <div class="server-metrics">
                            <div class="metric-item">
                                <div class="metric-label">CPU</div>
                                <div class="metric-value">${cpuUsage}%</div>
                            </div>
                            <div class="metric-item">
                                <div class="metric-label">Memory</div>
                                <div class="metric-value">${memoryUsage}%</div>
                            </div>
                            <div class="metric-item">
                                <div class="metric-label">Disk</div>
                                <div class="metric-value">${diskUsage}%</div>
                            </div>
                        </div>
                        ${vmsHtml ? `
                            <div class="vms-section">
                                <div class="vms-title">Virtual Machines (${vmCount})</div>
                                <div class="vm-list">
                                    ${vmsHtml}
                                </div>
                            </div>
                        ` : ''}
                    </div>
                </div>
            `;
        }).join('');
    }

    /**
     * Toggle server card expansion
     */
    window.toggleServer = function(index) {
        const serverCard = document.querySelector(`[data-server-index="${index}"]`);
        if (serverCard) {
            serverCard.classList.toggle('expanded');
        }
    };

    /**
     * Show error message
     */
    function showError(message) {
        errorState.textContent = message;
        errorState.style.display = 'block';
        loadingState.style.display = 'none';
        dashboardContent.style.display = 'none';
    }

    /**
     * Hide error message
     */
    function hideError() {
        errorState.style.display = 'none';
    }

    /**
     * Format date string
     */
    function formatDate(dateString) {
        try {
            const date = new Date(dateString);
            const now = new Date();
            const diffMs = now - date;
            const diffSecs = Math.floor(diffMs / 1000);
            const diffMins = Math.floor(diffSecs / 60);

            if (diffSecs < 60) {
                return `${diffSecs}s ago`;
            } else if (diffMins < 60) {
                return `${diffMins}m ago`;
            } else {
                return date.toLocaleString();
            }
        } catch (e) {
            return dateString;
        }
    }

    /**
     * Escape HTML to prevent XSS
     */
    function escapeHtml(text) {
        if (text === null || text === undefined) {
            return '';
        }
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initDashboard);
    } else {
        initDashboard();
    }
})();
