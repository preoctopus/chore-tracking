// ChoreTracker Pro - Core Client Application

class ChoreTrackerApp {
    constructor() {
        this.user = null;
        this.currentView = 'loginSection';
        
        // Calendar State
        const today = new Date();
        this.currentMonth = today.getMonth();
        this.currentYear = today.getFullYear();
        
        // Kid Dashboard State
        this.kidSelectedDate = this.getLocalDateString();
        
        // Cached data
        this.children = [];
        this.chores = [];
        this.parents = [];

        // MAC editing state (for parent router integration modal)
        this.editingMacUsername = null;
        this.editingMacList = [];
    }

    // --- Utility Methods ---
    getLocalDateString(date = new Date()) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    formatReadableDate(dateStr) {
        if (!dateStr) return '';
        const parts = dateStr.split('-');
        if (parts.length !== 3) return dateStr;
        const d = new Date(parts[0], parts[1] - 1, parts[2]);
        return d.toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
    }

    showView(viewId) {
        document.querySelectorAll('.view-panel').forEach(panel => {
            panel.classList.add('hidden');
        });
        const view = document.getElementById(viewId);
        if (view) {
            view.classList.remove('hidden');
            this.currentView = viewId;
        }

        // Header visibility logic
        const header = document.getElementById('appHeader');
        if (this.user) {
            header.classList.remove('hidden');
            document.getElementById('currentUsername').textContent = this.user.username;
            
            // Set role badge styles
            const badge = document.getElementById('roleBadge');
            badge.textContent = this.user.role;
            badge.className = `badge badge-${this.user.role}`;
        } else {
            header.classList.add('hidden');
        }
    }

    // Show API / UI alerts
    showAlert(elementId, text, type = 'danger') {
        const alertEl = document.getElementById(elementId);
        if (alertEl) {
            alertEl.textContent = text;
            alertEl.className = `alert alert-${type}`;
            alertEl.classList.remove('hidden');
        }
    }

    hideAlert(elementId) {
        const alertEl = document.getElementById(elementId);
        if (alertEl) {
            alertEl.classList.add('hidden');
        }
    }

    // Copy to clipboard helper
    copyToClipboard(text, element) {
        navigator.clipboard.writeText(text).then(() => {
            const originalText = element.textContent;
            element.textContent = "Copied!";
            element.style.borderColor = "#10b981";
            element.style.color = "#34d399";
            
            setTimeout(() => {
                element.textContent = originalText;
                element.style.borderColor = "";
                element.style.color = "";
            }, 1500);
        });
    }

    // --- Authentication Flows ---
    async checkSession() {
        try {
            const response = await fetch('/api/auth/session');
            const data = await response.json();
            if (data.logged_in) {
                this.user = data.user;
                this.routeUserDashboard();
            } else {
                this.user = null;
                this.showView('loginSection');
            }
        } catch (error) {
            console.error('Session check failed:', error);
            this.showView('loginSection');
        }
    }

    async handleLogin(event) {
        event.preventDefault();
        this.hideAlert('loginError');
        
        const usernameInput = document.getElementById('loginUsername');
        const passwordInput = document.getElementById('loginPassword');
        
        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    username: usernameInput.value,
                    password: passwordInput.value
                })
            });
            
            const data = await response.json();
            
            if (response.ok) {
                this.user = data.user;
                usernameInput.value = '';
                passwordInput.value = '';
                
                this.routeUserDashboard();
            } else {
                this.showAlert('loginError', data.error || 'Login failed. Please check credentials.');
            }
        } catch (error) {
            this.showAlert('loginError', 'Failed to connect to server.');
        }
    }

    async logout() {
        try {
            await fetch('/api/auth/logout', { method: 'POST' });
            this.user = null;
            this.showView('loginSection');
        } catch (error) {
            console.error('Logout failed:', error);
        }
    }

    routeUserDashboard() {
        if (this.user.is_temp_password) {
            // Force password change
            const modal = document.getElementById('changePasswordModal');
            this.hideAlert('passwordChangeError');
            document.getElementById('newPassword').value = '';
            
            // Prevent close on escape or clicking outside
            modal.addEventListener('cancel', (e) => e.preventDefault());
            modal.showModal();
            return;
        }

        if (this.user.role === 'admin') {
            this.showView('adminSection');
            this.loadAdminDashboard();
        } else if (this.user.role === 'parent') {
            this.showView('parentSection');
            this.switchParentTab('calendar');
            this.loadParentDashboard();
        } else if (this.user.role === 'child') {
            this.showView('kidSection');
            this.loadKidDashboard();
        }
    }

    async handleFirstPasswordChange(event) {
        event.preventDefault();
        this.hideAlert('passwordChangeError');
        
        const newPassword = document.getElementById('newPassword').value;
        
        try {
            const response = await fetch('/api/auth/change-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_password: newPassword })
            });
            const data = await response.json();
            
            if (response.ok) {
                this.user.is_temp_password = false;
                document.getElementById('changePasswordModal').close();
                this.routeUserDashboard();
            } else {
                this.showAlert('passwordChangeError', data.error || 'Password update failed.');
            }
        } catch (error) {
            this.showAlert('passwordChangeError', 'Connection error.');
        }
    }

    // --- Admin Dashboard (Parent Management) ---
    async loadAdminDashboard(keepMessage = false) {
        if (!keepMessage) {
            this.hideAlert('parentActionMessage');
        }
        const parentsTable = document.getElementById('parentsTableBody');
        const emptyState = document.getElementById('parentsEmptyState');
        parentsTable.innerHTML = '';
        
        try {
            const response = await fetch('/api/parents');
            const parents = await response.json();
            this.parents = parents;
            
            if (parents.length === 0) {
                emptyState.classList.remove('hidden');
                return;
            }
            emptyState.classList.add('hidden');
            
            parents.forEach(p => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${escapeHTML(p.username)}</strong></td>
                    <td><span class="badge badge-parent">Parent</span></td>
                    <td class="text-right">
                        <button type="button" class="btn btn-danger btn-sm btn-icon" onclick="event.preventDefault(); event.stopPropagation(); app.deleteParent('${escapeHTML(p.username)}')">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
                        </button>
                    </td>
                `;
                parentsTable.appendChild(tr);
            });
        } catch (error) {
            console.error('Failed to load parents:', error);
        }
    }

    async handleAddParent(event) {
        event.preventDefault();
        this.hideAlert('parentActionMessage');
        const usernameInput = document.getElementById('parentUsername');
        const username = usernameInput.value.trim();
        
        if (!username) return;
        
        try {
            const response = await fetch('/api/parents', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username })
            });
            const data = await response.json();
            
            if (response.ok) {
                usernameInput.value = '';
                
                // Show generated password badge
                const parentMsg = document.getElementById('parentActionMessage');
                parentMsg.className = 'alert alert-success';
                parentMsg.innerHTML = `
                    Parent <strong>${escapeHTML(data.username)}</strong> created successfully! 
                    <br>Copy this temporary password for first login:
                    <div class="password-box" onclick="app.copyToClipboard('${data.password}', this)">${escapeHTML(data.password)}</div>
                `;
                parentMsg.classList.remove('hidden');
                
                this.loadAdminDashboard(true);
            } else {
                this.showAlert('parentActionMessage', data.error || 'Failed to add parent.');
            }
        } catch (error) {
            this.showAlert('parentActionMessage', 'Failed to communicate with server.');
        }
    }

    async deleteParent(username) {
        if (!confirm(`Are you sure you want to remove parent '${username}'?`)) return;
        
        try {
            const response = await fetch(`/api/parents/${encodeURIComponent(username)}`, {
                method: 'DELETE'
            });
            const data = await response.json();
            
            if (response.ok) {
                this.loadAdminDashboard();
            } else {
                alert(data.error || 'Failed to remove parent.');
            }
        } catch (error) {
            alert('Failed to connect to server.');
        }
    }

    // --- Parent Dashboard Tabs & Loads ---
    switchParentTab(tabName) {
        document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(content => content.classList.add('hidden'));
        
        if (tabName === 'calendar') {
            document.getElementById('tabBtnCalendar').classList.add('active');
            document.getElementById('parentTabCalendar').classList.remove('hidden');
            this.renderCalendar();
        } else if (tabName === 'chores') {
            document.getElementById('tabBtnChores').classList.add('active');
            document.getElementById('parentTabChores').classList.remove('hidden');
            this.loadChoresList();
        } else if (tabName === 'children') {
            document.getElementById('tabBtnChildren').classList.add('active');
            document.getElementById('parentTabChildren').classList.remove('hidden');
            this.loadChildrenList();
            this.loadRouterLogs();
        }
    }

    async loadParentDashboard() {
        // Fetch children, chores, and completions for local state caches
        try {
            await this.fetchLocalChildren();
            await this.fetchLocalChores();
        } catch (error) {
            console.error('Error loading parent resources:', error);
        }
    }

    async fetchLocalChildren() {
        const response = await fetch('/api/children');
        this.children = await response.json();
    }

    async fetchLocalChores() {
        const response = await fetch('/api/chores');
        this.chores = await response.json();
    }

    // --- Parent: Kids management ---
    async loadChildrenList(keepMessage = false) {
        if (!keepMessage) {
            this.hideAlert('childActionMessage');
        }
        const childTable = document.getElementById('childrenTableBody');
        const emptyState = document.getElementById('childrenEmptyState');
        childTable.innerHTML = '';
        
        try {
            await this.fetchLocalChildren();
            
            if (this.children.length === 0) {
                emptyState.classList.remove('hidden');
                return;
            }
            emptyState.classList.add('hidden');
            
            this.children.forEach(c => {
                const macs = c.mac_addresses || [];
                let macDisplay = '';
                if (macs.length === 0) {
                    macDisplay = '<span style="opacity:0.6; font-size:0.8rem;">None</span>';
                } else {
                    const display = macs.length > 2 
                        ? macs.slice(0, 2).join(', ') + ` +${macs.length - 2}` 
                        : macs.join(', ');
                    macDisplay = `<span title="${escapeHTML(macs.join(', '))}" style="font-family: monospace; font-size: 0.8rem;">${escapeHTML(display)}</span>`;
                }

                const isBlocked = !!c.router_blacklisted;
                const internetBadge = isBlocked 
                    ? `<span class="badge" style="background:#ef4444; color:white;">Blocked</span>`
                    : `<span class="badge" style="background:#10b981; color:white;">Allowed</span>`;

                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${escapeHTML(c.username)}</strong></td>
                    <td>
                        ${macDisplay}
                    </td>
                    <td>
                        ${internetBadge}
                    </td>
                    <td><span class="badge badge-child">Child</span></td>
                    <td class="text-right">
                        <button type="button" class="btn btn-secondary btn-sm btn-icon" style="margin-right: 0.25rem;" title="Edit MAC Addresses (Router)" onclick="event.preventDefault(); event.stopPropagation(); app.openEditChildMacModal('${escapeHTML(c.username)}')">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>
                        </button>
                        <button type="button" class="btn btn-sm" style="margin-right: 0.25rem; ${isBlocked ? '' : 'opacity:0.5;'}" title="Block Internet (add to blacklist)" onclick="event.preventDefault(); event.stopPropagation(); app.blockChildInternet('${escapeHTML(c.username)}')">
                            Block
                        </button>
                        <button type="button" class="btn btn-sm" style="margin-right: 0.5rem; ${isBlocked ? 'opacity:0.5;' : ''}" title="Allow Internet (remove from blacklist)" onclick="event.preventDefault(); event.stopPropagation(); app.allowChildInternet('${escapeHTML(c.username)}')">
                            Allow
                        </button>
                        <button type="button" class="btn btn-secondary btn-sm btn-icon" style="margin-right: 0.5rem;" title="Change Password" onclick="event.preventDefault(); event.stopPropagation(); app.openChangeChildPasswordModal('${escapeHTML(c.username)}')">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                        </button>
                        <button type="button" class="btn btn-danger btn-sm btn-icon" onclick="event.preventDefault(); event.stopPropagation(); app.deleteChild('${escapeHTML(c.username)}')">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
                        </button>
                    </td>
                `;
                childTable.appendChild(tr);
            });
        } catch (error) {
            console.error('Failed to load children list:', error);
        }
    }

    async handleAddChild(event) {
        event.preventDefault();
        this.hideAlert('childActionMessage');
        const usernameInput = document.getElementById('childUsername');
        const macInput = document.getElementById('childMacAddresses');
        const username = usernameInput.value.trim();
        
        if (!username) return;
        
        // Parse optional MAC addresses (support newlines or commas)
        let macAddresses = [];
        if (macInput && macInput.value.trim()) {
            const lines = macInput.value.replace(/,/g, '\n').split('\n');
            macAddresses = lines.map(l => l.trim()).filter(Boolean);
        }
        
        const payload = { username };
        if (macAddresses.length > 0) {
            payload.mac_addresses = macAddresses;
        }
        
        try {
            const response = await fetch('/api/children', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await response.json();
            
            if (response.ok) {
                usernameInput.value = '';
                if (macInput) macInput.value = '';
                
                const childMsg = document.getElementById('childActionMessage');
                childMsg.className = 'alert alert-success';
                childMsg.innerHTML = `
                    Child <strong>${escapeHTML(data.username)}</strong> added successfully!
                    <br>Copy this temporary password for their first login:
                    <div class="password-box" onclick="app.copyToClipboard('${data.password}', this)">${escapeHTML(data.password)}</div>
                `;
                childMsg.classList.remove('hidden');
                
                this.loadChildrenList(true);
            } else {
                this.showAlert('childActionMessage', data.error || 'Failed to add child.');
            }
        } catch (error) {
            this.showAlert('childActionMessage', 'Failed to communicate with server.');
        }
    }

    async deleteChild(username) {
        if (!confirm(`Are you sure you want to remove child '${username}'? This deletes all their assigned chores and progress files.`)) return;
        
        try {
            const response = await fetch(`/api/children/${encodeURIComponent(username)}`, {
                method: 'DELETE'
            });
            const data = await response.json();
            if (response.ok) {
                this.loadChildrenList();
            } else {
                alert(data.error || 'Failed to delete child.');
            }
        } catch (error) {
            alert('Failed to connect to server.');
        }
    }

    // --- Parent: Chore manager ---
    async loadChoresList() {
        const choresTable = document.getElementById('choresTableBody');
        const emptyState = document.getElementById('choresEmptyState');
        choresTable.innerHTML = '';
        
        try {
            await this.fetchLocalChores();
            
            if (this.chores.length === 0) {
                emptyState.classList.remove('hidden');
                return;
            }
            emptyState.classList.add('hidden');
            
            this.chores.forEach(c => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${escapeHTML(c.title)}</strong></td>
                    <td class="text-secondary">${escapeHTML(c.description || 'No description')}</td>
                    <td><span class="badge badge-child">${escapeHTML(c.assigned_to)}</span></td>
                    <td class="text-right">
                        <button type="button" class="btn btn-secondary btn-sm btn-icon" onclick="event.preventDefault(); event.stopPropagation(); app.openEditChoreModal('${c.id}', '${escapeJS(c.title)}', '${escapeJS(c.description || '')}', '${escapeJS(c.assigned_to)}')">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                        </button>
                        <button type="button" class="btn btn-danger btn-sm btn-icon" onclick="event.preventDefault(); event.stopPropagation(); app.deleteChore('${c.id}')">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>
                        </button>
                    </td>
                `;
                choresTable.appendChild(tr);
            });
        } catch (error) {
            console.error('Failed to load chores:', error);
        }
    }

    populateAssigneeSelect(selectedAssignee = '') {
        const select = document.getElementById('choreAssignee');
        select.innerHTML = '<option value="" disabled selected>Select child</option>';
        this.children.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.username;
            opt.textContent = c.username;
            if (c.username === selectedAssignee) opt.selected = true;
            select.appendChild(opt);
        });
    }

    async openAddChoreModal() {
        this.hideAlert('choreFormError');
        document.getElementById('choreForm').reset();
        document.getElementById('editChoreId').value = '';
        document.getElementById('choreModalTitle').textContent = 'Add New Chore';
        document.getElementById('choreSubmitBtn').textContent = 'Create Chore';
        
        await this.fetchLocalChildren();
        this.populateAssigneeSelect();
        
        document.getElementById('choreModal').showModal();
    }

    async openEditChoreModal(id, title, desc, assignee) {
        this.hideAlert('choreFormError');
        document.getElementById('editChoreId').value = id;
        document.getElementById('choreTitle').value = title;
        document.getElementById('choreDescription').value = desc;
        document.getElementById('choreModalTitle').textContent = 'Edit Chore';
        document.getElementById('choreSubmitBtn').textContent = 'Save Changes';
        
        await this.fetchLocalChildren();
        this.populateAssigneeSelect(assignee);
        
        document.getElementById('choreModal').showModal();
    }

    async handleChoreSubmit(event) {
        event.preventDefault();
        this.hideAlert('choreFormError');
        
        const id = document.getElementById('editChoreId').value;
        const title = document.getElementById('choreTitle').value.trim();
        const description = document.getElementById('choreDescription').value.trim();
        const assigned_to = document.getElementById('choreAssignee').value;
        
        if (!title || !assigned_to) {
            this.showAlert('choreFormError', 'Title and Assignee are required.');
            return;
        }
        
        const payload = { title, description, assigned_to };
        const url = id ? `/api/chores/${id}` : '/api/chores';
        const method = id ? 'PUT' : 'POST';
        
        try {
            const response = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await response.json();
            
            if (response.ok) {
                document.getElementById('choreModal').close();
                this.loadChoresList();
            } else {
                this.showAlert('choreFormError', data.error || 'Failed to save chore.');
            }
        } catch (error) {
            this.showAlert('choreFormError', 'Connection failed.');
        }
    }

    async deleteChore(id) {
        if (!confirm('Are you sure you want to delete this chore and all its completion proofs?')) return;
        
        try {
            const response = await fetch(`/api/chores/${id}`, { method: 'DELETE' });
            if (response.ok) {
                this.loadChoresList();
            } else {
                const data = await response.json();
                alert(data.error || 'Failed to delete chore.');
            }
        } catch (error) {
            alert('Failed to connect to server.');
        }
    }

    // --- Parent: Calendar Progress Grid ---
    async renderCalendar() {
        const monthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
        document.getElementById('currentMonthYear').textContent = `${monthNames[this.currentMonth]} ${this.currentYear}`;
        
        const grid = document.getElementById('calendarGrid');
        grid.innerHTML = '';
        
        // Calculate days metrics
        const firstDay = new Date(this.currentYear, this.currentMonth, 1).getDay();
        const daysInMonth = new Date(this.currentYear, this.currentMonth + 1, 0).getDate();
        
        // Query start and end strings
        const pad = (n) => String(n).padStart(2, '0');
        const startDateStr = `${this.currentYear}-${pad(this.currentMonth + 1)}-01`;
        const endDateStr = `${this.currentYear}-${pad(this.currentMonth + 1)}-${pad(daysInMonth)}`;
        
        // Fetch completions cache for this month and local list of chores/children
        let completions = [];
        try {
            const response = await fetch(`/api/completions?start_date=${startDateStr}&end_date=${endDateStr}`);
            completions = await response.json();
            await this.fetchLocalChildren();
            await this.fetchLocalChores();
        } catch (error) {
            console.error('Failed to load calendar records:', error);
        }

        // Fill leading empty calendar slots
        for (let i = 0; i < firstDay; i++) {
            const emptyDiv = document.createElement('div');
            emptyDiv.className = 'calendar-day empty-day';
            grid.appendChild(emptyDiv);
        }
        
        const todayStr = this.getLocalDateString();
        
        // Populate days
        for (let day = 1; day <= daysInMonth; day++) {
            const dateStr = `${this.currentYear}-${pad(this.currentMonth + 1)}-${pad(day)}`;
            const isToday = (dateStr === todayStr);
            
            const dayDiv = document.createElement('div');
            dayDiv.className = `calendar-day ${isToday ? 'today' : ''}`;
            
            dayDiv.innerHTML = `
                <span class="day-number">${day}</span>
                <div class="calendar-day-chores"></div>
            `;
            
            const choresContainer = dayDiv.querySelector('.calendar-day-chores');
            
            // Loop through all chores to check status for this day
            this.chores.forEach(chore => {
                const isCompleted = completions.some(comp => 
                    comp.chore_id === chore.id && 
                    comp.completed_by === chore.assigned_to && 
                    comp.date === dateStr
                );
                
                const itemDiv = document.createElement('div');
                itemDiv.className = 'calendar-day-chore-item';
                itemDiv.title = `${chore.assigned_to}: ${chore.title} (${isCompleted ? 'Completed' : 'Pending'})`;
                
                const dot = document.createElement('span');
                dot.className = `status-indicator-dot ${isCompleted ? 'complete' : 'incomplete'}`;
                
                const textSpan = document.createElement('span');
                textSpan.className = 'chore-detail-text';
                textSpan.innerHTML = `<strong>${escapeHTML(chore.assigned_to)}</strong>: ${escapeHTML(chore.title)}`;
                
                itemDiv.appendChild(dot);
                itemDiv.appendChild(textSpan);
                choresContainer.appendChild(itemDiv);
            });
            
            // Add click detailed event
            dayDiv.onclick = () => this.openDayDetails(dateStr, completions);
            grid.appendChild(dayDiv);
        }
    }

    changeMonth(direction) {
        this.currentMonth += direction;
        if (this.currentMonth < 0) {
            this.currentMonth = 11;
            this.currentYear -= 1;
        } else if (this.currentMonth > 11) {
            this.currentMonth = 0;
            this.currentYear += 1;
        }
        this.renderCalendar();
    }

    openDayDetails(dateStr, completions) {
        const dialog = document.getElementById('dayDetailsModal');
        document.getElementById('dayDetailsDate').textContent = this.formatReadableDate(dateStr);
        
        const content = document.getElementById('dayDetailsContent');
        content.innerHTML = '';
        
        if (this.children.length === 0) {
            content.innerHTML = '<p class="empty-state">No children registered yet.</p>';
            dialog.showModal();
            return;
        }
        
        this.children.forEach(child => {
            const childDiv = document.createElement('div');
            childDiv.className = 'day-child-status';
            
            const childChores = this.chores.filter(c => c.assigned_to === child.username);
            
            let choresListHtml = '';
            if (childChores.length === 0) {
                choresListHtml = '<p class="text-secondary text-sm">No chores assigned for this kid.</p>';
            } else {
                childChores.forEach(chore => {
                    const comp = completions.find(c => c.chore_id === chore.id && c.completed_by === child.username && c.date === dateStr);
                    
                    if (comp) {
                        choresListHtml += `
                            <div class="day-child-chore-row">
                                <span>🟢 <strong>${escapeHTML(chore.title)}</strong></span>
                                <div class="completed-badge-area">
                                    <span class="text-success">Done</span>
                                    ${comp.image_path ? `<img src="${comp.image_path}" class="proof-thumbnail" onclick="event.stopPropagation(); app.viewImageProof('${comp.image_path}')" alt="proof">` : ''}
                                </div>
                            </div>
                        `;
                    } else {
                        choresListHtml += `
                            <div class="day-child-chore-row">
                                <span>🔴 <span style="text-decoration: line-through; opacity: 0.6;">${escapeHTML(chore.title)}</span></span>
                                <span class="badge" style="background: rgba(239, 68, 68, 0.1); color: #f87171; border-color: rgba(239,68,68,0.2);">Missed</span>
                            </div>
                        `;
                    }
                });
            }
            
            childDiv.innerHTML = `
                <h4>${escapeHTML(child.username)}</h4>
                <div class="child-chores-status-list">
                    ${choresListHtml}
                </div>
            `;
            content.appendChild(childDiv);
        });
        
        dialog.showModal();
    }

    // --- Kid Dashboard Actions ---
    loadKidDashboard() {
        document.getElementById('kidGreeting').textContent = `Hello, ${this.user.username}! 🌟`;
        
        const picker = document.getElementById('kidDatePicker');
        picker.value = this.kidSelectedDate;
        
        // Prevent selecting future dates via date input picker limit
        const todayStr = this.getLocalDateString();
        picker.max = todayStr;
        
        this.loadKidChores();
    }

    handleKidDateChange() {
        const picker = document.getElementById('kidDatePicker');
        const selected = picker.value;
        const todayStr = this.getLocalDateString();
        
        if (selected > todayStr) {
            alert("Cannot select future dates!");
            picker.value = todayStr;
            this.kidSelectedDate = todayStr;
        } else {
            this.kidSelectedDate = selected;
        }
        
        this.loadKidChores();
    }

    changeKidDate(direction) {
        const currentParts = this.kidSelectedDate.split('-');
        const date = new Date(currentParts[0], currentParts[1] - 1, currentParts[2]);
        date.setDate(date.getDate() + direction);
        
        const dateStr = this.getLocalDateString(date);
        const todayStr = this.getLocalDateString();
        
        if (dateStr > todayStr) {
            // Future dates are blocked
            return;
        }
        
        this.kidSelectedDate = dateStr;
        document.getElementById('kidDatePicker').value = dateStr;
        this.loadKidChores();
    }

    async loadKidChores() {
        const grid = document.getElementById('kidChoreGrid');
        const emptyState = document.getElementById('kidChoreEmptyState');
        const label = document.getElementById('selectedDateLabel');
        
        const todayStr = this.getLocalDateString();
        const nextDateBtn = document.getElementById('kidNextDateBtn');
        
        if (this.kidSelectedDate === todayStr) {
            label.textContent = "Today";
            nextDateBtn.disabled = true;
            nextDateBtn.style.opacity = '0.3';
            nextDateBtn.style.cursor = 'not-allowed';
        } else {
            label.textContent = this.formatReadableDate(this.kidSelectedDate);
            nextDateBtn.disabled = false;
            nextDateBtn.style.opacity = '';
            nextDateBtn.style.cursor = '';
        }
        
        grid.innerHTML = '';
        
        try {
            const response = await fetch(`/api/chores?date=${this.kidSelectedDate}`);
            const chores = await response.json();
            
            if (chores.length === 0) {
                emptyState.classList.remove('hidden');
                return;
            }
            emptyState.classList.add('hidden');
            
            chores.forEach(c => {
                const card = document.createElement('div');
                card.className = `chore-card ${c.completed ? 'completed' : ''}`;
                
                let actionHtml = '';
                if (c.completed) {
                    actionHtml = `
                        <div class="completed-badge-area">
                            <span class="text-success">✓ Completed</span>
                            ${c.image_path ? `<img src="${c.image_path}" class="proof-thumbnail" onclick="app.viewImageProof('${c.image_path}')" alt="proof preview">` : ''}
                        </div>
                    `;
                } else if (this.kidSelectedDate < todayStr) {
                    actionHtml = `
                        <span class="badge" style="background: rgba(239, 68, 68, 0.1); color: #f87171; border-color: rgba(239,68,68,0.2);">Missed</span>
                    `;
                } else {
                    actionHtml = `
                        <button type="button" class="btn btn-primary btn-sm" onclick="event.preventDefault(); event.stopPropagation(); app.openCompleteChoreModal('${c.id}', '${escapeJS(c.title)}')">
                            Mark Complete
                        </button>
                    `;
                }
                
                card.innerHTML = `
                    <div class="chore-card-content">
                        <h3>${escapeHTML(c.title)}</h3>
                        <p>${escapeHTML(c.description || 'No special instructions.')}</p>
                    </div>
                    <div class="chore-card-footer">
                        <span class="badge" style="opacity: 0.6;">Daily</span>
                        ${actionHtml}
                    </div>
                `;
                grid.appendChild(card);
            });
        } catch (error) {
            console.error('Failed to load chores for child:', error);
        }
    }

    openCompleteChoreModal(choreId, choreTitle) {
        this.hideAlert('completeChoreError');
        document.getElementById('completeChoreForm').reset();
        document.getElementById('completeChoreId').value = choreId;
        document.getElementById('completeChoreTitle').textContent = choreTitle;
        
        document.getElementById('completeChoreModal').showModal();
    }

    async handleCompleteChoreSubmit(event) {
        event.preventDefault();
        this.hideAlert('completeChoreError');
        
        const submitBtn = document.getElementById('completeSubmitBtn');
        submitBtn.disabled = true;
        submitBtn.textContent = 'Saving...';
        
        const id = document.getElementById('completeChoreId').value;
        const fileInput = document.getElementById('choreProofImage');
        
        const formData = new FormData();
        formData.append('chore_id', id);
        formData.append('date', this.kidSelectedDate);
        formData.append('client_today', this.getLocalDateString()); // Client context check
        
        if (fileInput.files.length > 0) {
            formData.append('image', fileInput.files[0]);
        }
        
        try {
            const response = await fetch('/api/completions', {
                method: 'POST',
                body: formData
            });
            const data = await response.json();
            
            if (response.ok) {
                document.getElementById('completeChoreModal').close();
                this.loadKidChores();
            } else {
                this.showAlert('completeChoreError', data.error || 'Failed to complete chore.');
            }
        } catch (error) {
            this.showAlert('completeChoreError', 'Network or server error.');
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Complete Chore';
        }
    }

    viewImageProof(imagePath) {
        const lightbox = document.getElementById('imageLightboxModal');
        const img = document.getElementById('lightboxImage');
        img.src = imagePath;
        lightbox.showModal();
    }

    openChangeOwnPasswordModal() {
        this.hideAlert('ownPasswordChangeAlert');
        document.getElementById('changeOwnPasswordForm').reset();
        document.getElementById('changeOwnPasswordModal').showModal();
    }

    async handleChangeOwnPassword(event) {
        event.preventDefault();
        this.hideAlert('ownPasswordChangeAlert');
        
        const newPassword = document.getElementById('ownNewPassword').value;
        if (!newPassword || newPassword.length < 4) {
            this.showAlert('ownPasswordChangeAlert', 'Password must be at least 4 characters long.', 'danger');
            return;
        }
        
        try {
            const response = await fetch('/api/auth/change-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_password: newPassword })
            });
            const data = await response.json();
            
            if (response.ok) {
                this.showAlert('ownPasswordChangeAlert', 'Password updated successfully!', 'success');
                setTimeout(() => {
                    document.getElementById('changeOwnPasswordModal').close();
                }, 1500);
            } else {
                this.showAlert('ownPasswordChangeAlert', data.error || 'Failed to update password.', 'danger');
            }
        } catch (error) {
            this.showAlert('ownPasswordChangeAlert', 'Failed to communicate with server.', 'danger');
        }
    }

    openChangeChildPasswordModal(username) {
        this.hideAlert('childPasswordChangeAlert');
        document.getElementById('changeChildPasswordForm').reset();
        document.getElementById('changeChildPasswordUsername').value = username;
        document.getElementById('changeChildPasswordTarget').textContent = username;
        document.getElementById('changeChildPasswordModal').showModal();
    }

    async handleChangeChildPassword(event) {
        event.preventDefault();
        this.hideAlert('childPasswordChangeAlert');
        
        const username = document.getElementById('changeChildPasswordUsername').value;
        const newPassword = document.getElementById('childNewPassword').value;
        
        if (!newPassword || newPassword.length < 4) {
            this.showAlert('childPasswordChangeAlert', 'Password must be at least 4 characters long.', 'danger');
            return;
        }
        
        try {
            const response = await fetch(`/api/children/${encodeURIComponent(username)}/change-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_password: newPassword })
            });
            const data = await response.json();
            
            if (response.ok) {
                this.showAlert('childPasswordChangeAlert', 'Child password updated successfully!', 'success');
                setTimeout(() => {
                    document.getElementById('changeChildPasswordModal').close();
                }, 1500);
            } else {
                this.showAlert('childPasswordChangeAlert', data.error || 'Failed to update child password.', 'danger');
            }
        } catch (error) {
            this.showAlert('childPasswordChangeAlert', 'Failed to communicate with server.', 'danger');
        }
    }

    // --- Parent: Child MAC Address Management (Router Integration) ---
    async openEditChildMacModal(username) {
        this.editingMacUsername = username;
        this.editingMacList = [];

        // Prefer fresh data from server for this child
        try {
            const res = await fetch(`/api/children/${encodeURIComponent(username)}/mac-addresses`);
            if (res.ok) {
                const data = await res.json();
                if (Array.isArray(data.mac_addresses)) {
                    this.editingMacList = [...data.mac_addresses];
                }
            }
        } catch (e) {
            // Fallback to cache
            const child = this.children.find(c => c.username === username);
            if (child && Array.isArray(child.mac_addresses)) {
                this.editingMacList = [...child.mac_addresses];
            }
        }

        document.getElementById('editMacChildUsername').textContent = username;
        this.hideAlert('editMacAlert');
        this.renderMacListInModal();

        const modal = document.getElementById('editChildMacModal');
        modal.showModal();
    }

    renderMacListInModal() {
        const container = document.getElementById('macListContainer');
        container.innerHTML = '';

        if (this.editingMacList.length === 0) {
            const empty = document.createElement('div');
            empty.style.cssText = 'opacity:0.6; font-size:0.85rem; padding: 4px 6px;';
            empty.textContent = 'No MAC addresses added yet.';
            container.appendChild(empty);
            return;
        }

        this.editingMacList.forEach((mac, index) => {
            const chip = document.createElement('span');
            chip.style.cssText = `
                display: inline-flex; align-items: center; gap: 6px;
                background: rgba(16, 185, 129, 0.15); color: #10b981;
                font-family: monospace; font-size: 0.8rem;
                padding: 2px 8px; border-radius: 999px; margin: 3px;
                border: 1px solid rgba(16, 185, 129, 0.3);
            `;
            chip.innerHTML = `
                ${escapeHTML(mac)}
                <button type="button" style="background:none; border:none; color:#10b981; cursor:pointer; font-size:14px; line-height:1;" title="Remove">×</button>
            `;
            const removeBtn = chip.querySelector('button');
            removeBtn.onclick = (e) => {
                e.stopPropagation();
                this.removeMacFromEditList(index);
            };
            container.appendChild(chip);
        });
    }

    addMacToEditList() {
        const input = document.getElementById('newMacInput');
        if (!input) return;
        const value = input.value.trim();
        if (!value) return;

        // Basic client normalization attempt
        let normalized = value.replace(/[^0-9a-fA-F]/g, '').toUpperCase();
        if (normalized.length === 12) {
            normalized = normalized.match(/.{1,2}/g).join(':');
        } else {
            // Let the server do full validation; allow user to try anyway
            normalized = value.toUpperCase().replace(/[^0-9A-F:]/g, '').replace(/:/g, '').match(/.{1,2}/g)?.join(':') || value;
        }

        if (!this.editingMacList.includes(normalized)) {
            this.editingMacList.push(normalized);
        }
        input.value = '';
        this.renderMacListInModal();
    }

    removeMacFromEditList(index) {
        this.editingMacList.splice(index, 1);
        this.renderMacListInModal();
    }

    async saveChildMacAddresses() {
        if (!this.editingMacUsername) return;
        this.hideAlert('editMacAlert');

        try {
            const response = await fetch(`/api/children/${encodeURIComponent(this.editingMacUsername)}/mac-addresses`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mac_addresses: this.editingMacList })
            });
            const data = await response.json();

            if (response.ok) {
                const alertBox = document.getElementById('editMacAlert');
                alertBox.className = 'alert alert-success';
                alertBox.textContent = 'MAC addresses saved successfully!';
                alertBox.classList.remove('hidden');

                // Refresh the children list (which includes MACs)
                await this.loadChildrenList(true);

                setTimeout(() => {
                    document.getElementById('editChildMacModal').close();
                }, 900);
            } else {
                this.showAlert('editMacAlert', data.error || 'Failed to save MAC addresses.', 'danger');
            }
        } catch (error) {
            this.showAlert('editMacAlert', 'Failed to communicate with server.', 'danger');
        }
    }

    // --- Manual Internet Access Overrides (parent only) ---
    async blockChildInternet(username) {
        if (!confirm(`Block internet access for ${username} by adding their MACs to the router blacklist?`)) {
            return;
        }
        try {
            const response = await fetch(`/api/children/${encodeURIComponent(username)}/router/block`, {
                method: 'POST'
            });
            const data = await response.json();
            if (response.ok) {
                this.loadChildrenList(true);
                this.loadRouterLogs();
            } else {
                alert(data.message || data.error || 'Failed to block internet.');
            }
        } catch (err) {
            alert('Failed to communicate with server.');
        }
    }

    async allowChildInternet(username) {
        if (!confirm(`Allow internet access for ${username} by removing their MACs from the router blacklist?`)) {
            return;
        }
        try {
            const response = await fetch(`/api/children/${encodeURIComponent(username)}/router/allow`, {
                method: 'POST'
            });
            const data = await response.json();
            if (response.ok) {
                this.loadChildrenList(true);
                this.loadRouterLogs();
            } else {
                alert(data.message || data.error || 'Failed to allow internet.');
            }
        } catch (err) {
            alert('Failed to communicate with server.');
        }
    }

    async loadRouterLogs() {
        const tbody = document.getElementById('routerLogsBody');
        const empty = document.getElementById('routerLogsEmpty');
        if (!tbody || !empty) return;

        tbody.innerHTML = '';
        empty.classList.add('hidden');

        try {
            const res = await fetch('/api/router/logs');
            if (!res.ok) throw new Error('Failed to load logs');
            const logs = await res.json();

            if (!logs || logs.length === 0) {
                empty.classList.remove('hidden');
                return;
            }

            logs.forEach(log => {
                const tr = document.createElement('tr');
                const time = log.timestamp ? log.timestamp.replace('T', ' ').substring(0, 19) : '';
                const actionLabel = log.action === 'add_to_blacklist' ? 'Blocked (added to blacklist)' : 'Allowed (removed from blacklist)';
                const successLabel = log.success ? 
                    '<span style="color:#10b981;">Success</span>' : 
                    `<span style="color:#ef4444;">Failed${log.error ? ': ' + escapeHTML(log.error) : ''}</span>`;
                const actor = log.actor || 'system';
                const macCount = (log.mac_addresses || []).length;

                tr.innerHTML = `
                    <td style="font-size:0.75rem; font-family:monospace;">${escapeHTML(time)}</td>
                    <td><strong>${escapeHTML(log.child_username || '')}</strong> <span style="opacity:0.6;">(${macCount} MACs)</span></td>
                    <td style="font-size:0.8rem;">${escapeHTML(actionLabel)}</td>
                    <td style="font-size:0.75rem;">${escapeHTML(actor)}</td>
                    <td>${successLabel}</td>
                `;
                tbody.appendChild(tr);
            });
        } catch (e) {
            console.error('Failed to load router logs', e);
            empty.classList.remove('hidden');
        }
    }

    async refreshRouterStatus() {
        const contentDiv = document.getElementById('routerRefreshReportContent');
        const modal = document.getElementById('routerRefreshReportModal');
        if (!contentDiv || !modal) return;

        contentDiv.innerHTML = '<p style="opacity:0.7;">Contacting router and computing required changes...</p>';
        modal.showModal();

        try {
            const res = await fetch('/api/router/refresh', { method: 'POST' });
            const data = await res.json();

            if (!res.ok) {
                contentDiv.innerHTML = `<p style="color:#ef4444;">Error: ${escapeHTML(data.error || 'Refresh failed')}</p>`;
                return;
            }

            let html = `<p><strong>${escapeHTML(data.message || 'Sync complete.')}</strong></p>`;

            // Initial
            html += '<h4 style="margin-top:1rem; margin-bottom:0.25rem;">Initial Blacklist (from router)</h4>';
            if (data.initial_blacklist && data.initial_blacklist.length) {
                html += `<pre style="background:rgba(0,0,0,0.3); padding:8px; border-radius:6px; font-size:0.8rem; white-space:pre-wrap;">${escapeHTML(data.initial_blacklist.join('\n'))}</pre>`;
            } else {
                html += '<p style="opacity:0.7;">(empty)</p>';
            }

            // Changes
            html += '<h4 style="margin-top:1rem; margin-bottom:0.25rem;">Changes to be made</h4>';
            const toBlock = data.changes && data.changes.to_block ? data.changes.to_block : [];
            const toUnblock = data.changes && data.changes.to_unblock ? data.changes.to_unblock : [];

            if (toBlock.length === 0 && toUnblock.length === 0) {
                html += '<p style="opacity:0.7;">No changes needed — router already in sync with desired state.</p>';
            } else {
                if (toBlock.length) {
                    html += '<div style="margin-bottom:0.5rem;"><strong>To Block (add to blacklist):</strong></div><ul style="margin:0 0 0.75rem 1.2rem; padding:0;">';
                    toBlock.forEach(item => {
                        html += `<li style="font-family:monospace;">${escapeHTML(item.mac)} <span style="opacity:0.6;">(${escapeHTML(item.child)})</span></li>`;
                    });
                    html += '</ul>';
                }
                if (toUnblock.length) {
                    html += '<div style="margin-bottom:0.5rem;"><strong>To Unblock (remove from blacklist):</strong></div><ul style="margin:0 0 0.75rem 1.2rem; padding:0;">';
                    toUnblock.forEach(item => {
                        html += `<li style="font-family:monospace;">${escapeHTML(item.mac)} <span style="opacity:0.6;">(${escapeHTML(item.child)})</span></li>`;
                    });
                    html += '</ul>';
                }
            }

            // Resultant
            html += '<h4 style="margin-top:1rem; margin-bottom:0.25rem;">Resultant Blacklist (from router)</h4>';
            if (data.resultant_blacklist && data.resultant_blacklist.length) {
                html += `<pre style="background:rgba(0,0,0,0.3); padding:8px; border-radius:6px; font-size:0.8rem; white-space:pre-wrap;">${escapeHTML(data.resultant_blacklist.join('\n'))}</pre>`;
            } else {
                html += '<p style="opacity:0.7;">(empty)</p>';
            }

            contentDiv.innerHTML = html;

            // Refresh the main lists and logs so badges and activity table update
            this.loadChildrenList(true);
            this.loadRouterLogs();

        } catch (err) {
            contentDiv.innerHTML = `<p style="color:#ef4444;">Network error during refresh: ${escapeHTML(err.message || err)}</p>`;
        }
    }
}

// --- Dynamic Helper Functions to prevent HTML and Script Injection ---
function escapeHTML(str) {
    if (!str) return '';
    return str.replace(/[&<>'"]/g, 
        tag => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            "'": '&#39;',
            '"': '&quot;'
        }[tag] || tag)
    );
}

function escapeJS(str) {
    if (!str) return '';
    return str.replace(/['"\\\n\r]/g, 
        char => ({
            "'": "\\'",
            '"': '\\"',
            '\\': '\\\\',
            '\n': '\\n',
            '\r': '\\r'
        }[char] || char)
    );
}

// Global initialization
const app = new ChoreTrackerApp();
window.addEventListener('DOMContentLoaded', () => {
    app.checkSession();
});
