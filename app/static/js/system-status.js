/**
 * System Status Badge - Reusable Component
 * 
 * This script initializes and manages the system status badge that appears
 * in the header of all pages. It polls the /vm/health endpoint every 30 seconds
 * and updates the badge display accordingly.
 * 
 * Usage:
 * 1. Include this script in your HTML: <script src="/static/js/system-status.js"></script>
 * 2. Add the HTML structure with IDs: systemStatusIndicator, systemStatusText, systemStatusTooltip
 * 3. Add the CSS styles for .system-status-indicator and related classes
 */

(function() {
    'use strict';

    // Wait for DOM to be ready
    function initSystemStatus() {
        const statusIndicator = document.getElementById('systemStatusIndicator');
        const statusText = document.getElementById('systemStatusText');
        const statusTooltip = document.getElementById('systemStatusTooltip');
        
        // If elements don't exist, exit silently (page might not have the badge)
        if (!statusIndicator || !statusText || !statusTooltip) {
            return;
        }

        let statusPollInterval = null;

        async function fetchSystemStatus() {
            try {
                const response = await fetch('/vm/health');
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                const data = await response.json();
                updateSystemStatus(data);
            } catch (error) {
                console.error('Error fetching system status:', error);
                updateSystemStatus({
                    systemStatus: 'unknown',
                    vmId: null,
                    lastHeartbeat: null,
                    status: null,
                    processingQueueId: null
                });
            }
        }

        function updateSystemStatus(data) {
            if (!statusIndicator || !statusText || !statusTooltip) {
                return;
            }

            const systemStatus = data.systemStatus || 'unknown';
            const vmId = data.vmId || 'N/A';
            const lastHeartbeat = data.lastHeartbeat || null;
            const vmStatus = data.status || 'N/A';
            const processingQueueId = data.processingQueueId || null;

            // Update indicator class
            statusIndicator.className = `system-status-indicator ${systemStatus}`;

            // Update status text
            if (systemStatus === 'up') {
                statusText.textContent = 'System Up';
            } else if (systemStatus === 'down') {
                statusText.textContent = 'System in Sleep Mode';
            } else {
                statusText.textContent = 'Unknown';
            }

            // Build tooltip content
            let tooltipContent = '';
            if (systemStatus === 'up') {
                tooltipContent = `<strong>System Status:</strong> Up and Running<br>`;
            } else if (systemStatus === 'down') {
                tooltipContent = `<strong>System Status:</strong> System in Sleep Mode<br>`;
            } else {
                tooltipContent = `<strong>System Status:</strong> Unknown<br>`;
            }
            tooltipContent += `<strong>VM ID:</strong> ${vmId}<br>`;
            tooltipContent += `<strong>VM Status:</strong> ${vmStatus}<br>`;
            if (lastHeartbeat) {
                const heartbeatDate = new Date(lastHeartbeat);
                const formattedDate = heartbeatDate.toLocaleString();
                tooltipContent += `<strong>Last Heartbeat:</strong> ${formattedDate}<br>`;
                const secondsAgo = Math.floor((Date.now() - heartbeatDate.getTime()) / 1000);
                tooltipContent += `<strong>Time Ago:</strong> ${secondsAgo} second${secondsAgo !== 1 ? 's' : ''} ago`;
            } else {
                tooltipContent += `<strong>Last Heartbeat:</strong> Never`;
            }
            if (processingQueueId) {
                tooltipContent += `<br><strong>Processing Queue:</strong> ${processingQueueId}`;
            }
            statusTooltip.innerHTML = tooltipContent;
        }

        // Fetch status immediately on page load
        fetchSystemStatus();

        // Poll every 30 seconds
        statusPollInterval = setInterval(fetchSystemStatus, 30000);

        // Cleanup on page unload
        window.addEventListener('beforeunload', () => {
            if (statusPollInterval) {
                clearInterval(statusPollInterval);
            }
        });
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initSystemStatus);
    } else {
        // DOM is already ready
        initSystemStatus();
    }
})();

