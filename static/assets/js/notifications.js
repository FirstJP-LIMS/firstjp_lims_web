// static/assets/js/notifications.js

class NotificationManager {
    constructor() {
        this.socket = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 3000;
        this.init();
    }

    init() {
        this.connect();
        this.setupEventHandlers();
    }

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/notifications/`;

        console.log('Connecting to WebSocket:', wsUrl);

        this.socket = new WebSocket(wsUrl);

        this.socket.onopen = () => {
            console.log('✅ WebSocket connected');
            this.reconnectAttempts = 0;
            this.showConnectionStatus('connected');
        };

        this.socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('📬 Notification received:', data);
            this.handleNotification(data);
        };

        this.socket.onerror = (error) => {
            console.error('❌ WebSocket error:', error);
            this.showConnectionStatus('error');
        };

        this.socket.onclose = (event) => {
            console.log('WebSocket closed:', event.code, event.reason);
            this.showConnectionStatus('disconnected');
            this.attemptReconnect();
        };
    }

    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            console.log(`Reconnecting... Attempt ${this.reconnectAttempts}`);
            setTimeout(() => this.connect(), this.reconnectDelay);
        } else {
            console.error('Max reconnection attempts reached');
            this.showConnectionStatus('failed');
        }
    }

    handleNotification(data) {
        // Update notification badge
        this.updateBadge();

        // Add notification to dropdown
        this.addNotificationToList(data);

        // Show toast notification
        this.showToast(data);

        // Play sound (optional)
        this.playNotificationSound();
    }

    updateBadge() {
        fetch('/notification/get/?limit=1')
            .then(response => response.json())
            .then(data => {
                const badge = document.getElementById('notification-badge');
                const count = data.unread_count;

                if (count > 0) {
                    badge.textContent = count > 99 ? '99+' : count;
                    badge.style.display = 'inline-block';
                } else {
                    badge.style.display = 'none';
                }
            })
            .catch(error => console.error('Error updating badge:', error));
    }

    addNotificationToList(data) {
        const dropdown = document.getElementById('notification-dropdown');
        if (!dropdown) return;

        const notificationHtml = `
            <a href="${data.action_url || '#'}" 
               class="dropdown-item notification-item unread" 
               data-notification-id="${data.id}">
                <div class="notification-content">
                    <div class="notification-icon ${data.level || 'info'}">
                        <i class="fas fa-bell"></i>
                    </div>
                    <div class="notification-text">
                        <p class="notification-message">${data.message}</p>
                        <small class="text-muted">Just now</small>
                    </div>
                </div>
            </a>
        `;

        const emptyState = dropdown.querySelector('.empty-notifications');
        if (emptyState) {
            emptyState.remove();
        }

        dropdown.insertAdjacentHTML('afterbegin', notificationHtml);

        // Limit to 10 notifications in dropdown
        const items = dropdown.querySelectorAll('.notification-item');
        if (items.length > 10) {
            items[items.length - 1].remove();
        }
    }

    showToast(data) {
        // Create toast notification
        const toast = document.createElement('div');
        toast.className = `toast-notification ${data.level || 'info'}`;
        toast.innerHTML = `
            <div class="toast-icon">
                <i class="fas fa-bell"></i>
            </div>
            <div class="toast-content">
                <strong>New Notification</strong>
                <p>${data.message}</p>
            </div>
            <button class="toast-close" onclick="this.parentElement.remove()">
                <i class="fas fa-times"></i>
            </button>
        `;

        document.body.appendChild(toast);

        // Auto remove after 5 seconds
        setTimeout(() => {
            toast.classList.add('fade-out');
            setTimeout(() => toast.remove(), 300);
        }, 5000);
    }

    playNotificationSound() {
        // Optional: Add notification sound
        const audio = new Audio('/static/sounds/notification.mp3');
        audio.volume = 0.3;
        audio.play().catch(e => console.log('Could not play sound:', e));
    }

    showConnectionStatus(status) {
        const statusEl = document.getElementById('ws-status');
        if (!statusEl) return;

        statusEl.className = `ws-status ${status}`;
        statusEl.textContent = {
            'connected': '🟢 Connected',
            'disconnected': '🟡 Reconnecting...',
            'error': '🔴 Connection Error',
            'failed': '🔴 Connection Failed'
        }[status] || '';
    }

    setupEventHandlers() {
        // Mark notification as read when clicked
        document.addEventListener('click', (e) => {
            const notificationItem = e.target.closest('.notification-item.unread');
            if (notificationItem) {
                const notificationId = notificationItem.dataset.notificationId;
                this.markAsRead(notificationId);
            }
        });

        // Mark all as read button
        const markAllBtn = document.getElementById('mark-all-read');
        if (markAllBtn) {
            markAllBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.markAllAsRead();
            });
        }
    }

    markAsRead(notificationId) {
        fetch(`/notification/mark-read/${notificationId}/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': this.getCsrfToken(),
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const item = document.querySelector(`[data-notification-id="${notificationId}"]`);
                if (item) {
                    item.classList.remove('unread');
                }
                this.updateBadge();
            }
        })
        .catch(error => console.error('Error marking as read:', error));
    }

    markAllAsRead() {
        fetch('/notification/mark-all-read/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': this.getCsrfToken(),
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                document.querySelectorAll('.notification-item.unread').forEach(item => {
                    item.classList.remove('unread');
                });
                this.updateBadge();
            }
        })
        .catch(error => console.error('Error marking all as read:', error));
    }

    getCsrfToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    if (document.body.dataset.userAuthenticated === 'true') {
        window.notificationManager = new NotificationManager();
    }
});

