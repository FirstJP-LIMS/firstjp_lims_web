// static/js/dashboard.js

class MEDVUNOApp {
    constructor() {
        this.currentPage = 'dashboard';
        this.isSidebarOpen = window.innerWidth >= 1024;
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.setupNavigation();
        this.initializeComponents();
        this.setupServiceWorker();
    }

    // 🎯 Event Listeners with Modern Patterns
    setupEventListeners() {
        // Delegated event handling for better performance
        document.addEventListener('click', this.handleGlobalClick.bind(this));
        document.addEventListener('keydown', this.handleKeyboardShortcuts.bind(this));
        
        // Responsive sidebar handling
        window.addEventListener('resize', this.handleResize.bind(this));
        
        // Online/offline detection
        window.addEventListener('online', this.handleOnlineStatus.bind(this));
        window.addEventListener('offline', this.handleOfflineStatus.bind(this));
    }

    // 🧭 Navigation System
    setupNavigation() {
        // Update active states
        this.updateActiveNavigation();
        
        // Handle initial page load
        this.handleInitialPageLoad();
    }

    // ⚡ Component Initialization
    initializeComponents() {
        this.initializeCharts();
        this.initializeNotifications();
        this.initializeQuickActions();
    }

    // 🎮 Global Click Handler
    handleGlobalClick(event) {
        const target = event.target;
        
        // Navigation clicks
        if (target.closest('[data-page]')) {
            event.preventDefault();
            const page = target.closest('[data-page]').dataset.page;
            this.navigateTo(page);
        }

        // Quick actions
        if (target.closest('.quick-actions button')) {
            this.handleQuickAction(target.closest('.quick-actions button'));
        }

        // Table actions
        if (target.closest('[data-action]')) {
            this.handleTableAction(target.closest('[data-action]'));
        }
    }

    // ⌨️ Keyboard Shortcuts
    handleKeyboardShortcuts(event) {
        // Ctrl/Cmd + K for global search
        if ((event.ctrlKey || event.metaKey) && event.key === 'k') {
            event.preventDefault();
            this.openGlobalSearch();
        }

        // Escape to close modals
        if (event.key === 'Escape') {
            this.closeAllModals();
        }

        // Sidebar toggle (Ctrl/Cmd + B)
        if ((event.ctrlKey || event.metaKey) && event.key === 'b') {
            event.preventDefault();
            this.toggleSidebar();
        }
    }

    // 📱 Responsive Handling
    handleResize = () => {
        const wasSidebarOpen = this.isSidebarOpen;
        this.isSidebarOpen = window.innerWidth >= 1024;
        
        if (wasSidebarOpen !== this.isSidebarOpen) {
            this.updateSidebarState();
        }
    }

    // 🌐 Online/Offline Status
    handleOnlineStatus() {
        this.showNotification('Connection restored', 'success');
        this.syncPendingActions();
    }

    handleOfflineStatus() {
        this.showNotification('You are currently offline', 'warning');
    }

    // 🧭 Navigation Methods
    async navigateTo(page, data = {}) {
        // Show loading state
        this.showLoadingState();
        
        try {
            // Update URL
            const url = this.generatePageURL(page, data);
            window.history.pushState({ page, data }, '', url);
            
            // Load page content
            await this.loadPageContent(page, data);
            
            // Update UI state
            this.updateActiveNavigation();
            this.updateDocumentTitle(page);
            
        } catch (error) {
            this.handleNavigationError(error, page);
        } finally {
            this.hideLoadingState();
        }
    }

    async loadPageContent(page, data) {
        if (page === 'dashboard') {
            // Dashboard is already loaded
            this.showDashboard();
            return;
        }

        // Fetch external page content
        const response = await fetch(`/api/pages/${page}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken()
            },
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            throw new Error(`Failed to load ${page}`);
        }

        const html = await response.text();
        this.renderPageContent(html, page);
    }

    // 🎨 UI Components
    initializeCharts() {
        // Initialize any charts on the dashboard
        const chartElements = document.querySelectorAll('[data-chart]');
        chartElements.forEach(element => {
            this.initializeChart(element);
        });
    }

    initializeChart(element) {
        // Chart.js initialization with modern features
        const ctx = element.getContext('2d');
        const chartType = element.dataset.chartType || 'line';
        const chartData = JSON.parse(element.dataset.chartData || '{}');
        
        new Chart(ctx, {
            type: chartType,
            data: chartData,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                    }
                },
                animation: {
                    duration: 1000,
                    easing: 'easeInOutQuart'
                }
            }
        });
    }

    // 🔔 Notification System
    initializeNotifications() {
        this.notificationContainer = document.createElement('div');
        this.notificationContainer.className = 'fixed top-4 right-4 z-50 space-y-2 max-w-sm';
        document.body.appendChild(this.notificationContainer);
    }

    showNotification(message, type = 'info', duration = 5000) {
        const notification = document.createElement('div');
        notification.className = `alert alert-${type} shadow-lg transform transition-all duration-300 translate-x-full`;
        notification.innerHTML = `
            <div>
                <i class="bi bi-${this.getNotificationIcon(type)}"></i>
                <span>${message}</span>
            </div>
            <button class="btn btn-sm btn-ghost" onclick="this.parentElement.remove()">
                <i class="bi bi-x"></i>
            </button>
        `;

        this.notificationContainer.appendChild(notification);
        
        // Animate in
        requestAnimationFrame(() => {
            notification.classList.remove('translate-x-full');
        });

        // Auto remove
        if (duration > 0) {
            setTimeout(() => {
                notification.style.transform = 'translateX(100%)';
                setTimeout(() => notification.remove(), 300);
            }, duration);
        }
    }

    getNotificationIcon(type) {
        const icons = {
            success: 'check-circle',
            error: 'exclamation-circle',
            warning: 'exclamation-triangle',
            info: 'info-circle'
        };
        return icons[type] || 'info-circle';
    }

    // ⚡ Quick Actions
    initializeQuickActions() {
        // Preload quick action modals for better performance
        this.preloadQuickActionModals();
    }

    async handleQuickAction(button) {
        const action = button.textContent.trim();
        const actionType = button.dataset.action;
        
        this.showLoadingState();
        
        try {
            switch (actionType) {
                case 'new-sample':
                    await this.openNewSampleModal();
                    break;
                case 'generate-report':
                    await this.generateReport();
                    break;
                case 'add-assistant':
                    await this.openAddAssistantModal();
                    break;
                case 'view-analytics':
                    await this.openAnalyticsDashboard();
                    break;
                default:
                    await this.handleCustomQuickAction(actionType);
            }
        } catch (error) {
            this.showNotification(`Failed to perform action: ${error.message}`, 'error');
        } finally {
            this.hideLoadingState();
        }
    }

    // 📊 Table Actions
    handleTableAction(button) {
        const action = button.dataset.action;
        const sampleId = button.dataset.sampleId;
        
        switch (action) {
            case 'view':
                this.viewSampleDetails(sampleId);
                break;
            case 'edit':
                this.editSample(sampleId);
                break;
            case 'process':
                this.processSample(sampleId);
                break;
        }
    }

    // 🔧 Utility Methods
    showLoadingState() {
        // Show elegant loading indicator
        document.body.classList.add('loading');
    }

    hideLoadingState() {
        document.body.classList.remove('loading');
    }

    getCSRFToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value;
    }

    updateActiveNavigation() {
        // Remove active class from all nav items
        document.querySelectorAll('[data-page]').forEach(item => {
            item.classList.remove('active', 'bg-medvuno-red', 'text-white');
            item.classList.add('hover:bg-white/10');
        });

        // Add active class to current page
        const currentNavItem = document.querySelector(`[data-page="${this.currentPage}"]`);
        if (currentNavItem) {
            currentNavItem.classList.add('active', 'bg-medvuno-red', 'text-white');
            currentNavItem.classList.remove('hover:bg-white/10');
        }
    }

    // 🛠 Service Worker for Offline Capability
    async setupServiceWorker() {
        if ('serviceWorker' in navigator) {
            try {
                await navigator.serviceWorker.register('/sw.js');
                console.log('Service Worker registered');
            } catch (error) {
                console.log('Service Worker registration failed:', error);
            }
        }
    }

    // 🎯 Error Handling
    handleNavigationError(error, page) {
        console.error(`Navigation error for ${page}:`, error);
        this.showNotification(
            `Failed to load ${page}. Please try again.`,
            'error'
        );
        
        // Fallback to dashboard
        if (page !== 'dashboard') {
            this.navigateTo('dashboard');
        }
    }

    // 📱 Mobile-Specific Features
    setupMobileFeatures() {
        // Touch gestures for mobile
        this.setupTouchGestures();
        
        // PWA features
        this.setupPWA();
    }

    setupTouchGestures() {
        let startX = 0;
        let endX = 0;

        document.addEventListener('touchstart', e => {
            startX = e.changedTouches[0].screenX;
        });

        document.addEventListener('touchend', e => {
            endX = e.changedTouches[0].screenX;
            this.handleSwipe(startX, endX);
        });
    }

    handleSwipe(startX, endX) {
        const diff = startX - endX;
        
        if (Math.abs(diff) > 50) { // Minimum swipe distance
            if (diff > 0 && window.innerWidth < 1024) {
                // Swipe left - close sidebar
                this.closeSidebar();
            } else if (diff < 0 && window.innerWidth < 1024) {
                // Swipe right - open sidebar
                this.openSidebar();
            }
        }
    }
}

// 🚀 Application Initialization
let medvunoApp;

document.addEventListener('DOMContentLoaded', () => {
    medvunoApp = new MEDVUNOApp();
});

// 📚 Export for module usage (if needed)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MEDVUNOApp;
}// static/js/dashboard.js

class MEDVUNOApp {
    constructor() {
        this.currentPage = 'dashboard';
        this.isSidebarOpen = window.innerWidth >= 1024;
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.setupNavigation();
        this.initializeComponents();
        this.setupServiceWorker();
    }

    // 🎯 Event Listeners with Modern Patterns
    setupEventListeners() {
        // Delegated event handling for better performance
        document.addEventListener('click', this.handleGlobalClick.bind(this));
        document.addEventListener('keydown', this.handleKeyboardShortcuts.bind(this));
        
        // Responsive sidebar handling
        window.addEventListener('resize', this.handleResize.bind(this));
        
        // Online/offline detection
        window.addEventListener('online', this.handleOnlineStatus.bind(this));
        window.addEventListener('offline', this.handleOfflineStatus.bind(this));
    }

    // 🧭 Navigation System
    setupNavigation() {
        // Update active states
        this.updateActiveNavigation();
        
        // Handle initial page load
        this.handleInitialPageLoad();
    }

    // ⚡ Component Initialization
    initializeComponents() {
        this.initializeCharts();
        this.initializeNotifications();
        this.initializeQuickActions();
    }

    // 🎮 Global Click Handler
    handleGlobalClick(event) {
        const target = event.target;
        
        // Navigation clicks
        if (target.closest('[data-page]')) {
            event.preventDefault();
            const page = target.closest('[data-page]').dataset.page;
            this.navigateTo(page);
        }

        // Quick actions
        if (target.closest('.quick-actions button')) {
            this.handleQuickAction(target.closest('.quick-actions button'));
        }

        // Table actions
        if (target.closest('[data-action]')) {
            this.handleTableAction(target.closest('[data-action]'));
        }
    }

    // ⌨️ Keyboard Shortcuts
    handleKeyboardShortcuts(event) {
        // Ctrl/Cmd + K for global search
        if ((event.ctrlKey || event.metaKey) && event.key === 'k') {
            event.preventDefault();
            this.openGlobalSearch();
        }

        // Escape to close modals
        if (event.key === 'Escape') {
            this.closeAllModals();
        }

        // Sidebar toggle (Ctrl/Cmd + B)
        if ((event.ctrlKey || event.metaKey) && event.key === 'b') {
            event.preventDefault();
            this.toggleSidebar();
        }
    }

    // 📱 Responsive Handling
    handleResize = () => {
        const wasSidebarOpen = this.isSidebarOpen;
        this.isSidebarOpen = window.innerWidth >= 1024;
        
        if (wasSidebarOpen !== this.isSidebarOpen) {
            this.updateSidebarState();
        }
    }

    // 🌐 Online/Offline Status
    handleOnlineStatus() {
        this.showNotification('Connection restored', 'success');
        this.syncPendingActions();
    }

    handleOfflineStatus() {
        this.showNotification('You are currently offline', 'warning');
    }

    // 🧭 Navigation Methods
    async navigateTo(page, data = {}) {
        // Show loading state
        this.showLoadingState();
        
        try {
            // Update URL
            const url = this.generatePageURL(page, data);
            window.history.pushState({ page, data }, '', url);
            
            // Load page content
            await this.loadPageContent(page, data);
            
            // Update UI state
            this.updateActiveNavigation();
            this.updateDocumentTitle(page);
            
        } catch (error) {
            this.handleNavigationError(error, page);
        } finally {
            this.hideLoadingState();
        }
    }

    async loadPageContent(page, data) {
        if (page === 'dashboard') {
            // Dashboard is already loaded
            this.showDashboard();
            return;
        }

        // Fetch external page content
        const response = await fetch(`/api/pages/${page}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken()
            },
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            throw new Error(`Failed to load ${page}`);
        }

        const html = await response.text();
        this.renderPageContent(html, page);
    }

    // 🎨 UI Components
    initializeCharts() {
        // Initialize any charts on the dashboard
        const chartElements = document.querySelectorAll('[data-chart]');
        chartElements.forEach(element => {
            this.initializeChart(element);
        });
    }

    initializeChart(element) {
        // Chart.js initialization with modern features
        const ctx = element.getContext('2d');
        const chartType = element.dataset.chartType || 'line';
        const chartData = JSON.parse(element.dataset.chartData || '{}');
        
        new Chart(ctx, {
            type: chartType,
            data: chartData,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                    }
                },
                animation: {
                    duration: 1000,
                    easing: 'easeInOutQuart'
                }
            }
        });
    }

    // 🔔 Notification System
    initializeNotifications() {
        this.notificationContainer = document.createElement('div');
        this.notificationContainer.className = 'fixed top-4 right-4 z-50 space-y-2 max-w-sm';
        document.body.appendChild(this.notificationContainer);
    }

    showNotification(message, type = 'info', duration = 5000) {
        const notification = document.createElement('div');
        notification.className = `alert alert-${type} shadow-lg transform transition-all duration-300 translate-x-full`;
        notification.innerHTML = `
            <div>
                <i class="bi bi-${this.getNotificationIcon(type)}"></i>
                <span>${message}</span>
            </div>
            <button class="btn btn-sm btn-ghost" onclick="this.parentElement.remove()">
                <i class="bi bi-x"></i>
            </button>
        `;

        this.notificationContainer.appendChild(notification);
        
        // Animate in
        requestAnimationFrame(() => {
            notification.classList.remove('translate-x-full');
        });

        // Auto remove
        if (duration > 0) {
            setTimeout(() => {
                notification.style.transform = 'translateX(100%)';
                setTimeout(() => notification.remove(), 300);
            }, duration);
        }
    }

    getNotificationIcon(type) {
        const icons = {
            success: 'check-circle',
            error: 'exclamation-circle',
            warning: 'exclamation-triangle',
            info: 'info-circle'
        };
        return icons[type] || 'info-circle';
    }

    // ⚡ Quick Actions
    initializeQuickActions() {
        // Preload quick action modals for better performance
        this.preloadQuickActionModals();
    }

    async handleQuickAction(button) {
        const action = button.textContent.trim();
        const actionType = button.dataset.action;
        
        this.showLoadingState();
        
        try {
            switch (actionType) {
                case 'new-sample':
                    await this.openNewSampleModal();
                    break;
                case 'generate-report':
                    await this.generateReport();
                    break;
                case 'add-assistant':
                    await this.openAddAssistantModal();
                    break;
                case 'view-analytics':
                    await this.openAnalyticsDashboard();
                    break;
                default:
                    await this.handleCustomQuickAction(actionType);
            }
        } catch (error) {
            this.showNotification(`Failed to perform action: ${error.message}`, 'error');
        } finally {
            this.hideLoadingState();
        }
    }

    // 📊 Table Actions
    handleTableAction(button) {
        const action = button.dataset.action;
        const sampleId = button.dataset.sampleId;
        
        switch (action) {
            case 'view':
                this.viewSampleDetails(sampleId);
                break;
            case 'edit':
                this.editSample(sampleId);
                break;
            case 'process':
                this.processSample(sampleId);
                break;
        }
    }

    // 🔧 Utility Methods
    showLoadingState() {
        // Show elegant loading indicator
        document.body.classList.add('loading');
    }

    hideLoadingState() {
        document.body.classList.remove('loading');
    }

    getCSRFToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value;
    }

    updateActiveNavigation() {
        // Remove active class from all nav items
        document.querySelectorAll('[data-page]').forEach(item => {
            item.classList.remove('active', 'bg-medvuno-red', 'text-white');
            item.classList.add('hover:bg-white/10');
        });

        // Add active class to current page
        const currentNavItem = document.querySelector(`[data-page="${this.currentPage}"]`);
        if (currentNavItem) {
            currentNavItem.classList.add('active', 'bg-medvuno-red', 'text-white');
            currentNavItem.classList.remove('hover:bg-white/10');
        }
    }

    // 🛠 Service Worker for Offline Capability
    async setupServiceWorker() {
        if ('serviceWorker' in navigator) {
            try {
                await navigator.serviceWorker.register('/sw.js');
                console.log('Service Worker registered');
            } catch (error) {
                console.log('Service Worker registration failed:', error);
            }
        }
    }

    // 🎯 Error Handling
    handleNavigationError(error, page) {
        console.error(`Navigation error for ${page}:`, error);
        this.showNotification(
            `Failed to load ${page}. Please try again.`,
            'error'
        );
        
        // Fallback to dashboard
        if (page !== 'dashboard') {
            this.navigateTo('dashboard');
        }
    }

    // 📱 Mobile-Specific Features
    setupMobileFeatures() {
        // Touch gestures for mobile
        this.setupTouchGestures();
        
        // PWA features
        this.setupPWA();
    }

    setupTouchGestures() {
        let startX = 0;
        let endX = 0;

        document.addEventListener('touchstart', e => {
            startX = e.changedTouches[0].screenX;
        });

        document.addEventListener('touchend', e => {
            endX = e.changedTouches[0].screenX;
            this.handleSwipe(startX, endX);
        });
    }

    handleSwipe(startX, endX) {
        const diff = startX - endX;
        
        if (Math.abs(diff) > 50) { // Minimum swipe distance
            if (diff > 0 && window.innerWidth < 1024) {
                // Swipe left - close sidebar
                this.closeSidebar();
            } else if (diff < 0 && window.innerWidth < 1024) {
                // Swipe right - open sidebar
                this.openSidebar();
            }
        }
    }
}

// 🚀 Application Initialization
let medvunoApp;

document.addEventListener('DOMContentLoaded', () => {
    medvunoApp = new MEDVUNOApp();
});

// 📚 Export for module usage (if needed)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MEDVUNOApp;
}