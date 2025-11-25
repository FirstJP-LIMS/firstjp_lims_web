// Single Page Application Navigation
class LIMSApp {
    constructor() {
        this.currentPage = 'dashboard';
        this.sidebarCollapsed = false;
        this.init();
    }

    init() {
        this.setupNavigation();
        this.setupEventListeners();
        this.setupSidebarCollapse();
        this.loadSidebarState();
    }

    setupSidebarCollapse() {
        // Create and add toggle button
        const toggleBtn = document.createElement('button');
        toggleBtn.className = 'sidebar-toggle';
        toggleBtn.innerHTML = '<i class="bi bi-chevron-left"></i>';
        toggleBtn.setAttribute('title', 'Collapse sidebar');
        
        const sidebar = document.querySelector('.sidebar');
        sidebar.appendChild(toggleBtn);

        // Add tooltip data to nav links
        document.querySelectorAll('.nav-link[data-page]').forEach(link => {
            const page = link.getAttribute('data-page');
            const tooltipText = this.getTooltipText(page);
            link.setAttribute('data-tooltip', tooltipText);
        });
    }

    getTooltipText(page) {
        const tooltips = {
            'dashboard': 'Dashboard',
            'patients': 'Patients',
            'samples': 'Samples',
            'reports': 'Reports',
            'settings': 'Settings'
        };
        return tooltips[page] || page;
    }

    setupEventListeners() {
        // Navigation click events
        document.querySelectorAll('.nav-link[data-page]').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = link.getAttribute('data-page');
                this.navigateTo(page);
            });
        });

        // Sidebar toggle event
        document.querySelector('.sidebar-toggle').addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggleSidebar();
        });

        // Handle browser back/forward buttons
        window.addEventListener('popstate', (e) => {
            const page = window.location.hash.replace('#', '') || 'dashboard';
            this.showPage(page);
        });

        // Close sidebar when clicking on content on mobile
        document.querySelector('.main-content').addEventListener('click', () => {
            if (window.innerWidth < 768) {
                this.closeMobileSidebar();
            }
        });
    }

    toggleSidebar() {
        const sidebar = document.querySelector('.sidebar');
        const mainContent = document.querySelector('.main-content');
        
        this.sidebarCollapsed = !this.sidebarCollapsed;
        
        sidebar.classList.toggle('collapsed');
        mainContent.classList.toggle('expanded');
        
        // Update toggle button icon
        const toggleIcon = document.querySelector('.sidebar-toggle i');
        if (this.sidebarCollapsed) {
            toggleIcon.className = 'bi bi-chevron-right';
            toggleIcon.setAttribute('title', 'Expand sidebar');
        } else {
            toggleIcon.className = 'bi bi-chevron-left';
            toggleIcon.setAttribute('title', 'Collapse sidebar');
        }
        
        // Save state to localStorage
        this.saveSidebarState();
    }

    closeMobileSidebar() {
        const sidebar = document.querySelector('.sidebar');
        sidebar.classList.remove('mobile-open');
    }

    saveSidebarState() {
        localStorage.setItem('sidebarCollapsed', this.sidebarCollapsed);
    }

    loadSidebarState() {
        const savedState = localStorage.getItem('sidebarCollapsed');
        if (savedState === 'true' && window.innerWidth >= 768) {
            this.sidebarCollapsed = true;
            document.querySelector('.sidebar').classList.add('collapsed');
            document.querySelector('.main-content').classList.add('expanded');
            
            const toggleIcon = document.querySelector('.sidebar-toggle i');
            toggleIcon.className = 'bi bi-chevron-right';
            toggleIcon.setAttribute('title', 'Expand sidebar');
        }
    }

    navigateTo(page) {
        // Update URL without reload
        window.history.pushState({}, '', `#${page}`);
        
        // Show the selected page
        this.showPage(page);
        
        // Close mobile sidebar after navigation
        if (window.innerWidth < 768) {
            this.closeMobileSidebar();
        }
    }

    async showPage(page) {
        // Hide all pages
        document.querySelectorAll('.page-content').forEach(content => {
            content.classList.remove('active');
        });

        // Remove active class from all nav links
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.remove('active');
        });

        // Show selected page
        if (page === 'dashboard') {
            // Dashboard is already in the main file
            document.getElementById('dashboard').classList.add('active');
        } else {
            // Load external page content
            await this.loadExternalPage(page);
        }

        // Activate corresponding nav link
        const activeLink = document.querySelector(`.nav-link[data-page="${page}"]`);
        if (activeLink) {
            activeLink.classList.add('active');
        }

        this.currentPage = page;
        
        // Update page title
        this.updatePageTitle(page);
    }

    async loadExternalPage(page) {
        const pageContainer = document.getElementById('page-container');
        
        try {
            // Show loading state
            pageContainer.innerHTML = '<div class="text-center p-5"><div class="spinner-border text-red"></div><p class="mt-2">Loading...</p></div>';
            
            // Fetch the page content
            const response = await fetch(`pages/${page}.html`);
            if (!response.ok) {
                throw new Error('Page not found');
            }
            
            const html = await response.text();
            pageContainer.innerHTML = html;
            pageContainer.classList.add('active');
            
        } catch (error) {
            pageContainer.innerHTML = `
                <div class="alert alert-danger">
                    <h4>Error Loading Page</h4>
                    <p>Could not load the ${page} page. Please try again.</p>
                    <button class="btn btn-red" onclick="limsApp.navigateTo('dashboard')">Return to Dashboard</button>
                </div>
            `;
            pageContainer.classList.add('active');
        }
    }

    updatePageTitle(page) {
        const titles = {
            'dashboard': 'Dashboard - FirstJP LIMS',
            'patients': 'Patients - FirstJP LIMS', 
            'samples': 'Samples - FirstJP LIMS',
            'reports': 'Reports - FirstJP LIMS',
            'settings': 'Settings - FirstJP LIMS'
        };
        
        document.title = titles[page] || 'FirstJP LIMS';
    }
}

// Initialize the application when DOM is loaded
let limsApp;

document.addEventListener('DOMContentLoaded', function() {
    limsApp = new LIMSApp();
    
    // Handle initial page load with hash
    const initialPage = window.location.hash.replace('#', '') || 'dashboard';
    document.querySelector(`.nav-link[data-page="${initialPage}"]`).click();
    
    // Add mobile menu toggle if needed
    setupMobileMenu();
});

function setupMobileMenu() {
    // You can add a mobile menu toggle button in your header if needed
    const mobileMenuBtn = document.createElement('button');
    mobileMenuBtn.className = 'btn btn-red d-md-none';
    mobileMenuBtn.innerHTML = '<i class="bi bi-list"></i>';
    mobileMenuBtn.style.marginLeft = 'auto';
    
    mobileMenuBtn.addEventListener('click', function() {
        document.querySelector('.sidebar').classList.toggle('mobile-open');
    });
    
    // Add to header if you want mobile menu control
    const header = document.querySelector('.top-header .d-flex');
    if (header && window.innerWidth < 768) {
        header.appendChild(mobileMenuBtn);
    }
}

// Quick action handlers
document.addEventListener('DOMContentLoaded', function() {
    // Sample quick action handlers
    document.addEventListener('click', function(e) {
        if (e.target.closest('.quick-actions .btn')) {
            const btn = e.target.closest('.quick-actions .btn');
            const action = btn.textContent.trim();
            alert(`Action: ${action} - This would open the appropriate form/modal.`);
        }
    });

    // Table action buttons
    document.addEventListener('click', function(e) {
        if (e.target.closest('.btn-sm')) {
            const btn = e.target.closest('.btn-sm');
            // Handle table actions - in real app, this would open modals or navigate
            console.log('Table action clicked:', btn.textContent);
        }
    });
});
