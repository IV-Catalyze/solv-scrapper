/**
 * Common UI Components - Reusable across all pages
 * User menu dropdown functionality
 */

(function() {
    'use strict';

    // User menu dropdown toggle
    function toggleUserMenu() {
        const dropdown = document.getElementById('userDropdown');
        if (dropdown) {
            dropdown.classList.toggle('show');
        }
    }

    // Make toggleUserMenu globally available
    window.toggleUserMenu = toggleUserMenu;

    // Close user menu when clicking outside
    document.addEventListener('click', function(event) {
        const userMenu = document.querySelector('.user-menu');
        const dropdown = document.getElementById('userDropdown');
        if (userMenu && dropdown && !userMenu.contains(event.target)) {
            dropdown.classList.remove('show');
        }
    });

    // Close user menu on escape key
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape') {
            const dropdown = document.getElementById('userDropdown');
            if (dropdown) {
                dropdown.classList.remove('show');
            }
        }
    });
})();

