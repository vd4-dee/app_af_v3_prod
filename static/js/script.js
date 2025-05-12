// Import timer.js
const timerScript = document.createElement('script');
timerScript.src = 'static/js/timer.js';
document.head.appendChild(timerScript);

// Hide the download timer element if it exists
function hideDownloadTimer() {
    const timer = document.getElementById('download-timer');
    if (timer) timer.style.display = 'none';
}

document.addEventListener('DOMContentLoaded', () => {
    console.log("DOM fully loaded and parsed.");

    // --- Element References ---
    const sidebarLinks = document.querySelectorAll('#sidebar .sidebar-link');
    const mainPanels = document.querySelectorAll('#main-content .main-panel');
    const suggestionCards = document.querySelectorAll('.suggestion-cards .card');
    const sectionTitleElement = document.getElementById('section-title');
    const notificationPopup = document.getElementById('notification');
    const notificationMessage = document.getElementById('notification-message');
    const notificationCloseBtn = document.getElementById('notification-close');

    // Report Download Elements
    const form = document.getElementById('download-form');
    const emailInput = document.getElementById('email');
    const passwordInput = document.getElementById('password');
    const reportTableBody = document.querySelector("#report-table tbody");
    const addRowButton = document.getElementById('add-row-button');
    const reportTable = document.getElementById("report-table");
    const regionSelectionDiv = document.getElementById('region-selection');
    const downloadButton = document.getElementById('download-button');
    const loadingIndicator = document.getElementById('loading-indicator');
    const statusMessagesDiv = document.getElementById('status-messages');
    const reportTableSearchInput = document.getElementById('report-table-search');
    // Ensure search box is enabled
    if (reportTableSearchInput) reportTableSearchInput.disabled = false;

    // Config Management Elements
    const configNameInput = document.getElementById('config-name');
    const saveConfigButton = document.getElementById('save-config-button');
    const savedConfigsDropdown = document.getElementById('saved-configs-dropdown');
    const loadConfigButton = document.getElementById('load-config-button');
    const deleteConfigButton = document.getElementById('delete-config-button');

    // Scheduling Elements
    const scheduleConfigSelect = document.getElementById('schedule-config-select');
    const scheduleDateTimeInput = document.getElementById('schedule-datetime');
    const scheduleButton = document.getElementById('schedule-button');
    const schedulesListBody = document.getElementById('schedules-list');

    // Log Elements
    const logTableContainer = document.getElementById('log-table-container');
    const logDataTableBody = document.querySelector("#log-data-table tbody");
    const refreshLogButton = document.getElementById('refresh-log-button');
    const logTableSearchInput = document.getElementById('log-table-search');
    const totalCountSpan = document.getElementById('total-count');
    const successCountSpan = document.getElementById('success-count');
    const failedCountSpan = document.getElementById('failed-count');
    const statusChartCtx = document.getElementById('status-chart')?.getContext('2d');

    // Advanced Settings Elements
    const otpSecretInput = document.getElementById('otp-secret');
    const driverPathInput = document.getElementById('driver-path');
    const downloadBasePathInput = document.getElementById('download-base-path');
    const saveAdvancedSettingsButton = document.getElementById('save-advanced-settings');

    // Bulk Email Elements
    const bulkEmailForm = document.getElementById('bulk-email-form');
    const sendEmailButton = document.getElementById('send-email-button');
    const emailLoadingIndicator = document.getElementById('email-loading-indicator');
    const emailStatusMessagesDiv = document.getElementById('email-status-messages');

    // Debug DOM references
    console.log({
        sidebarLinks: sidebarLinks.length,
        suggestionCards: suggestionCards.length,
        form: !!form,
        reportTableBody: !!reportTableBody,
        addRowButton: !!addRowButton,
        downloadButton: !!downloadButton,
        savedConfigsDropdown: !!savedConfigsDropdown,
        scheduleConfigSelect: !!scheduleConfigSelect
    });

    // --- Global Variables ---
    let reportDataCache = null;
    let eventSource = null;
    let statusChart = null;
    let notificationTimeout = null;

    // --- Active Download Sessions ---
    let activeSessions = [];
    let activeSessionsTimer = null;

    function addActiveSession(sessionId, startTime, reports) {
        activeSessions.push({ sessionId, startTime, reports, expanded: false });
        renderActiveSessions();
        if (!activeSessionsTimer) {
            activeSessionsTimer = setInterval(renderActiveSessions, 1000);
        }
    }
    function removeActiveSession(sessionId) {
        activeSessions = activeSessions.filter(s => s.sessionId !== sessionId);
        renderActiveSessions();
        if (activeSessions.length === 0 && activeSessionsTimer) {
            clearInterval(activeSessionsTimer);
            activeSessionsTimer = null;
        }
    }
    function renderActiveSessions() {
        const list = document.getElementById('active-downloads-list');
        if (!list) return;
        if (activeSessions.length === 0) {
            list.innerHTML = '<tr><td colspan="4" class="subtext">No active downloads.</td></tr>';
            return;
        }
        list.innerHTML = '';
        activeSessions.forEach((session, idx) => {
            const elapsed = Math.floor((Date.now() - session.startTime) / 1000);
            const hour = Math.floor(elapsed / 3600).toString().padStart(2, '0');
            const min = Math.floor((elapsed % 3600) / 60).toString().padStart(2, '0');
            const sec = (elapsed % 60).toString().padStart(2, '0');
            const tr = document.createElement('tr');
            tr.className = 'session-row';
            tr.innerHTML = `
                <td><button class="expand-btn" data-idx="${idx}">${session.expanded ? '▼' : '▶'}</button></td>
                <td>${session.sessionId}</td>
                <td>${new Date(session.startTime).toLocaleString()}</td>
                <td>${hour}:${min}:${sec}</td>
            `;
            list.appendChild(tr);
            // Detail row
            const detailTr = document.createElement('tr');
            detailTr.className = 'session-detail-row';
            detailTr.style.display = session.expanded ? '' : 'none';
            detailTr.innerHTML = `<td colspan="4">
                <div class="report-list-detail">
                    <strong>Reports being downloaded:</strong>
                    <table class="data-table report-list-table">
                        <thead><tr><th>Report Name</th><th>From Date</th><th>To Date</th><th>Chunk Size</th></tr></thead>
                        <tbody>
                            ${session.reports && session.reports.length > 0 ? session.reports.map(r => `
                                <tr><td>${r.report_type}</td><td>${r.from_date}</td><td>${r.to_date}</td><td>${r.chunk_size}</td></tr>
                            `).join('') : '<tr><td colspan="4" class="subtext">No reports</td></tr>'}
                        </tbody>
                    </table>
                </div>
            </td>`;
            list.appendChild(detailTr);
        });
        // Add expand/collapse event listeners
        list.querySelectorAll('.expand-btn').forEach(btn => {
            btn.onclick = function() {
                const idx = parseInt(btn.getAttribute('data-idx'));
                activeSessions[idx].expanded = !activeSessions[idx].expanded;
                renderActiveSessions();
            };
        });
    }

    // --- Helper Functions ---

    function showNotification(message, type = 'info', duration = 4000) {
        if (!notificationPopup || !notificationMessage) return;
        if (notificationTimeout) clearTimeout(notificationTimeout);
        notificationMessage.textContent = message;
        notificationPopup.className = 'notification show';
        if (type === 'success') {
            notificationPopup.classList.add('success');
        } else if (type === 'error') {
            notificationPopup.classList.add('error');
        } else if (type === 'warning') {
            notificationPopup.classList.add('warning');
        }
        notificationTimeout = setTimeout(() => {
            notificationPopup.classList.remove('show');
        }, duration);
    }
    // Lưu/khôi phục trạng thái bảng report
    function saveReportTableState() {
        if (!reportTableBody) return;
        localStorage.setItem('reportTableHTML', reportTableBody.innerHTML);
    }
    function restoreReportTableState() {
        if (!reportTableBody) return false;
        const saved = localStorage.getItem('reportTableHTML');
        if (saved) {
            reportTableBody.innerHTML = saved;
            // Gắn lại event cho các select vừa được khôi phục
            const selects = document.querySelectorAll("select[name='report_type[]']");
            selects.forEach(sel => {
                if (!sel.dataset.listenerAttached) {
                    sel.addEventListener('change', updateRegionSelectionVisibilityBasedOnAllRows);
                    sel.dataset.listenerAttached = 'true';
                }
            });
            updateRegionSelectionVisibilityBasedOnAllRows && updateRegionSelectionVisibilityBasedOnAllRows();
            return true;
        }
        return false;
    }
    function hideNotification() {
        if (notificationPopup) {
            notificationPopup.classList.remove('show');
            if (notificationTimeout) clearTimeout(notificationTimeout);
        }
    }

    function addStatusMessage(targetDiv, message, type = 'log') {
        if (!targetDiv) return;
        const p = document.createElement('p');
        p.textContent = message;
        p.classList.add(`${type}-message`);
        const defaultMsg = targetDiv.querySelector('p.subtext');
        if (defaultMsg && targetDiv.children.length === 1 && defaultMsg.textContent.includes('No activity yet')) {
            targetDiv.innerHTML = '';
        }
        targetDiv.appendChild(p);
        targetDiv.scrollTop = targetDiv.scrollHeight;
    }

    function clearStatusMessages(targetDiv) {
        if (targetDiv) {
            targetDiv.innerHTML = '<p class="subtext">No activity yet.</p>';
        }
    }

    async function fetchData(url, options = {}) {
        try {
            console.log(`Sending request to ${url} with options:`, options);
            const response = await fetch(url, options);
            console.log(`Response status for ${url}: ${response.status}`);
            const responseData = await response.json();
            if (!response.ok) {
                const errorMessage = responseData.message || responseData.error || `HTTP error ${response.status}`;
                throw new Error(`${errorMessage} (URL: ${url})`);
            }
            console.log(`Data received from ${url}:`, responseData);
            return responseData;
        } catch (error) {
            console.error(`Fetch error for ${url}:`, error);
            const message = `Error fetching data from ${url}: ${error.message}`;
            addStatusMessage(statusMessagesDiv, message, 'error');
            showNotification(message, 'error');
            throw error;
        }
    }

    function fillSelectOptions(selectElement, optionsList, includeDefault = true, defaultText = "-- Select --", defaultVal = "") {
        if (!selectElement) {
            console.error("Select element not found for filling options.");
            return;
        }
        console.log(`Filling select options for ${selectElement.id || selectElement.name}:`, optionsList);
        const currentValue = selectElement.value;
        selectElement.innerHTML = '';
        if (includeDefault) {
            const defaultOption = document.createElement('option');
            defaultOption.value = defaultVal;
            defaultOption.textContent = defaultText;
            selectElement.appendChild(defaultOption);
        }
        optionsList.forEach(optionValue => {
            const option = document.createElement('option');
            if (typeof optionValue === 'object' && optionValue !== null && optionValue.value !== undefined) {
                option.value = optionValue.value;
                option.textContent = optionValue.text || optionValue.value;
            } else {
                option.value = String(optionValue);
                option.textContent = String(optionValue);
            }
            selectElement.appendChild(option);
        });
        const exists = optionsList.some(opt => (typeof opt === 'object' ? opt.value : String(opt)) === currentValue);
        if (currentValue && exists) {
            selectElement.value = currentValue;
        } else if (!includeDefault && optionsList.length > 0) {
            selectElement.selectedIndex = 0;
        }
        console.log(`Select ${selectElement.id || selectElement.name} populated with ${optionsList.length} options.`);
    }

    function formatDate(date) {
        if (!(date instanceof Date) || isNaN(date)) return "";
        try {
            return date.toISOString().split('T')[0];
        } catch (e) {
            console.error("Error formatting date:", e, date);
            return "";
        }
    }

    function setDefaultDates(rowElement) {
        if (!rowElement) return;
        const fromDateInput = rowElement.querySelector("input[name='from_date[]']");
        const toDateInput = rowElement.querySelector("input[name='to_date[]']");
        try {
            const now = new Date();
            const firstDayOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
            firstDayOfMonth.setHours(firstDayOfMonth.getHours() + 7);
            const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
            yesterday.setHours(yesterday.getHours() + 7);
            if (fromDateInput) fromDateInput.value = formatDate(firstDayOfMonth);
            if (toDateInput) toDateInput.value = formatDate(yesterday);
        } catch (e) {
            console.error("Error setting default dates:", e);
        }
    }

    function filterTable(inputElement, tableBodyElement) {
        const filter = inputElement.value.toUpperCase();
        const rows = tableBodyElement.getElementsByTagName('tr');
        for (let i = 0; i < rows.length; i++) {
            let visible = false;
            const cells = rows[i].getElementsByTagName('td');
            for (let j = 0; j < cells.length; j++) {
                if (cells[j]) {
                    const textValue = cells[j].textContent || cells[j].innerText;
                    const inputs = cells[j].querySelectorAll('input, select');
                    let controlValue = '';
                    if (inputs.length > 0) {
                        controlValue = inputs[0].value;
                    }
                    if (textValue.toUpperCase().indexOf(filter) > -1 || controlValue.toUpperCase().indexOf(filter) > -1) {
                        visible = true;
                        break;
                    }
                }
            }
            rows[i].style.display = visible ? '' : 'none';
        }
    }

    // --- Report Table Search Functionality ---
    if (reportTableSearchInput && reportTableBody) {
        reportTableSearchInput.disabled = false;
        reportTableSearchInput.addEventListener('input', function() {
            filterTable(reportTableSearchInput, reportTableBody);
        });
    }
    // --- Navigation & Panel Switching ---
    function resetBulkEmailPanel() {
        // Reset form fields and status messages
        const bulkEmailForm = document.getElementById('bulk-email-form');
        const sendEmailButton = document.getElementById('send-email-button');
        const emailLoadingIndicator = document.getElementById('email-loading-indicator');
        const emailStatusMessagesDiv = document.getElementById('email-status-messages');
        if (bulkEmailForm) bulkEmailForm.reset();
        if (sendEmailButton) sendEmailButton.disabled = false;
        if (emailLoadingIndicator) emailLoadingIndicator.style.display = 'none';
        if (emailStatusMessagesDiv) {
            emailStatusMessagesDiv.innerHTML = '<p class="subtext">No recent activity.</p>';
        }
    }

    async function fetchAndPopulateAdvancedSettings() {
        try {
            const data = await fetchData('/download/get-advanced-settings');
            if (data) {
                if (otpSecretInput) otpSecretInput.value = data.otp_secret || '';
                if (driverPathInput) driverPathInput.value = data.driver_path || '';
                if (downloadBasePathInput) downloadBasePathInput.value = data.download_base_path || '';
            }
        } catch (e) {
            showNotification('Failed to load advanced settings', 'error');
        }
    }

    function switchPanel(targetId) {
        console.log("Switching to panel:", targetId);
        if (!targetId) return;
        mainPanels.forEach(panel => panel.style.display = 'none');
        // If switching to active downloads panel, refresh its content immediately
        if (targetId === 'active-downloads-panel') {
            renderActiveSessions();
        }
        sidebarLinks.forEach(link => link.classList.remove('active'));
        const targetPanel = document.getElementById(targetId);
        if (targetPanel) {
            targetPanel.style.display = 'block';
            const activeLink = document.querySelector(`#sidebar .sidebar-link[data-target="${targetId}"]`);
            if (activeLink) {
                activeLink.classList.add('active');
                if (sectionTitleElement && activeLink.querySelector('span')) {
                    sectionTitleElement.textContent = activeLink.querySelector('span').textContent;
                }
            }
            if (document.getElementById('main-content')) {
                document.getElementById('main-content').scrollTop = 0;
            }
            if (targetId === 'log-panel') {
                fetchLogs();
            }
            if (targetId === 'scheduling-panel') {
                fetchAndPopulateConfigs(); // Load configs for scheduling
                fetchAndDisplaySchedules();
            }
            if (targetId === 'main-download-panel') {
                // Ưu tiên khôi phục trạng thái bảng report nếu có
                if (!restoreReportTableState()) {
                    fetchAndPopulateReportData();
                }
                fetchAndPopulateConfigs(); // Load configs for download panel
            }
            if (targetId === 'bulk-email-panel') {
                resetBulkEmailPanel();
            }
            if (targetId === 'advanced-settings-panel') {
                fetchAndPopulateAdvancedSettings();
            }
        } else {
            console.warn(`Panel with ID "${targetId}" not found.`);
            document.getElementById('main-download-panel').style.display = 'block';
            const defaultLink = document.querySelector(`#sidebar .sidebar-link[data-target="main-download-panel"]`);
            if (defaultLink) defaultLink.classList.add('active');
            if (sectionTitleElement && defaultLink.querySelector('span')) {
                sectionTitleElement.textContent = defaultLink.querySelector('span').textContent;
            }
            fetchAndPopulateReportData();
            fetchAndPopulateConfigs();
        }
    }

    sidebarLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            const targetId = link.getAttribute('data-target');
            // Only prevent default and switch panel if data-target exists
            if (targetId) { 
                e.preventDefault();
                console.log("Sidebar link clicked (panel switch), target:", targetId);
                switchPanel(targetId);
            } else {
                // Allow default link behavior (navigation) if no data-target
                console.log("Sidebar link clicked (navigation), href:", link.href);
            }
        });
    });

    // Lưu trạng thái bảng report mỗi khi có thay đổi
    if (reportTableBody) {
        reportTableBody.addEventListener('input', saveReportTableState);
        reportTableBody.addEventListener('change', saveReportTableState);
        reportTableBody.addEventListener('DOMSubtreeModified', saveReportTableState);
    }


    suggestionCards.forEach(card => {
        card.addEventListener('click', (e) => {
            if (e.target.classList.contains('card-button')) {
                e.preventDefault();
            }
            const targetId = card.getAttribute('data-target');
            console.log("Suggestion card clicked, target:", targetId);
            switchPanel(targetId);
            const targetPanel = document.getElementById(targetId);
            if (targetPanel) {
                targetPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    });

    // --- Report/Region Data ---
    async function fetchAndPopulateReportData() {
        console.log("Fetching report data from /download/get-reports-regions...");
        if (reportTableBody) {
            reportTableBody.innerHTML = '<tr><td colspan="5" class="subtext">Loading reports...</td></tr>';
        }
        try {
            const data = await fetchData('/download/get-reports-regions');
            console.log("Report data received:", data);
            if (data && Array.isArray(data.reports) && data.reports.length > 0) {
                reportDataCache = data;
                populateAllReportDropdowns(data.reports);
                const initialRow = reportTableBody?.querySelector("tr");
                if (initialRow) setDefaultDates(initialRow);
                console.log("Report dropdowns populated successfully.");
                if (reportTableBody) {
                    reportTableBody.innerHTML = '';
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td><select name="report_type[]" class="report-type-select" required></select></td>
                        <td><input type="date" name="from_date[]" required></td>
                        <td><input type="date" name="to_date[]" required></td>
                        <td><input type="text" name="chunk_size[]" value="5" placeholder="E.g.: 5 or month"></td>
                        <td><button type="button" class="remove-row-button" title="Remove this report row"><i class="fas fa-trash-alt"></i></button></td>
                    `;
                    reportTableBody.appendChild(row);
                    setDefaultDates(row); // Đặt giá trị mặc định cho ngày
                    populateAllReportDropdowns(data.reports);
                }
            } else {
                throw new Error("No reports found in response or invalid data structure.");
            }
        } catch (error) {
            console.error("Failed to load reports:", error);
            if (reportTableBody) {
                reportTableBody.innerHTML = `<tr><td colspan="5" class="error-message">Failed to load reports: ${error.message}</td></tr>`;
            }
            addStatusMessage(statusMessagesDiv, `Error loading reports: ${error.message}`, 'error');
        }
    }

    function populateAllReportDropdowns(reportNames) {
        console.log("Populating report dropdowns with:", reportNames);
        const selects = document.querySelectorAll("select[name='report_type[]']");
        console.log("Found report select elements:", selects.length);
        if (selects.length === 0) {
            console.warn("No report select elements found in DOM.");
            return;
        }
        selects.forEach(sel => {
            const currentValue = sel.value;
            fillSelectOptions(sel, reportNames, true, '-- Select Report --');
            if (reportNames.includes(currentValue)) sel.value = currentValue;
            if (!sel.dataset.listenerAttached) {
                sel.addEventListener('change', updateRegionSelectionVisibilityBasedOnAllRows);
                sel.dataset.listenerAttached = 'true';
            }
        });
        updateRegionSelectionVisibilityBasedOnAllRows();
    }

    function updateRegionSelectionVisibilityBasedOnAllRows() {
        if (!reportDataCache || !regionSelectionDiv) return;
        const reportSelects = document.querySelectorAll("select[name='report_type[]']");
        let requiresRegion = false;
        reportSelects.forEach(select => {
            const selectedReportKey = select.value;
            if (selectedReportKey && reportDataCache.report_urls_map && reportDataCache.region_required_urls && reportDataCache.regions) {
                const reportUrl = reportDataCache.report_urls_map[selectedReportKey];
                if (reportDataCache.region_required_urls.includes(reportUrl)) {
                    requiresRegion = true;
                }
            }
        });

        regionSelectionDiv.innerHTML = '';
        if (requiresRegion) {
            regionSelectionDiv.style.display = 'block';
            const mainLabel = document.createElement('label');
            mainLabel.textContent = 'Select Region(s) (required for some reports):';
            regionSelectionDiv.appendChild(mainLabel);
            regionSelectionDiv.appendChild(document.createElement('br'));
            if (reportDataCache.regions && Object.keys(reportDataCache.regions).length > 0) {
                for (const [index, name] of Object.entries(reportDataCache.regions)) {
                    const checkboxId = `region-${index}`;
                    const checkbox = document.createElement('input');
                    checkbox.type = 'checkbox';
                    checkbox.id = checkboxId;
                    checkbox.name = 'regions';
                    checkbox.value = index;
                    const checkLabel = document.createElement('label');
                    checkLabel.htmlFor = checkboxId;
                    checkLabel.textContent = name;
                    const div = document.createElement('div');
                    div.appendChild(checkbox);
                    div.appendChild(checkLabel);
                    regionSelectionDiv.appendChild(div);
                }
            } else {
                regionSelectionDiv.innerHTML += '<p class="subtext">No region data available.</p>';
            }
        } else {
            regionSelectionDiv.style.display = 'none';
        }
    }

    if (addRowButton && reportTableBody) {
        addRowButton.addEventListener("click", () => {
            console.log("Add report row clicked");
            const firstRow = reportTableBody.querySelector("tr");
            if (!firstRow) {
                console.error("Cannot add row: Template row not found.");
                return;
            }
            const newRow = firstRow.cloneNode(true);
            const reportSelect = newRow.querySelector("select[name='report_type[]']");
            const chunkSizeInput = newRow.querySelector("input[name='chunk_size[]']");
            if (reportSelect) {
                reportSelect.selectedIndex = 0;
                if (!reportSelect.dataset.listenerAttached) {
                    reportSelect.addEventListener('change', updateRegionSelectionVisibilityBasedOnAllRows);
                    reportSelect.dataset.listenerAttached = 'true';
                }
            }
            setDefaultDates(newRow);
            if (chunkSizeInput) chunkSizeInput.value = "5";
            reportTableBody.appendChild(newRow);
            updateRegionSelectionVisibilityBasedOnAllRows();
            console.log("Report row added.");
        });
    }

    if (reportTable) {
        reportTable.addEventListener("click", (event) => {
            if (event.target.closest(".remove-row-button")) {
                console.log("Remove row clicked");
                const row = event.target.closest("tr");
                if (reportTableBody && reportTableBody.querySelectorAll("tr").length > 1) {
                    row.remove();
                    updateRegionSelectionVisibilityBasedOnAllRows();
                    console.log("Report row removed.");
                } else {
                    showNotification("Cannot remove the last report row.", "warning");
                }
            }
        });
    }

    // --- Download Logic ---
    function getCurrentFormData() {
        const configData = {
            email: emailInput ? emailInput.value : '',
            password: passwordInput ? passwordInput.value : '',
            reports: [],
            regions: [],
            otp_secret: otpSecretInput ? otpSecretInput.value : '',
            driver_path: driverPathInput ? driverPathInput.value : '',
            download_base_path: downloadBasePathInput ? downloadBasePathInput.value : ''
        };

        if (reportTableBody) {
            const reportRows = reportTableBody.querySelectorAll('tr');
            reportRows.forEach(row => {
                const reportTypeSelect = row.querySelector('select[name="report_type[]"]');
                const fromDateInput = row.querySelector('input[name="from_date[]"]');
                const toDateInput = row.querySelector('input[name="to_date[]"]');
                const chunkSizeInput = row.querySelector('input[name="chunk_size[]"]');
                if (reportTypeSelect && reportTypeSelect.value) {
                    configData.reports.push({
                        report_type: reportTypeSelect.value,
                        from_date: fromDateInput ? fromDateInput.value : '',
                        to_date: toDateInput ? toDateInput.value : '',
                        chunk_size: chunkSizeInput ? (chunkSizeInput.value.trim() || '5') : '5',
                    });
                }
            });
        }

        if (regionSelectionDiv && regionSelectionDiv.style.display === 'block') {
            const selectedRegionCheckboxes = regionSelectionDiv.querySelectorAll('input[name="regions"]:checked');
            configData.regions = Array.from(selectedRegionCheckboxes).map(cb => cb.value);
        }
        return configData;
    }

    async function handleDownloadFormSubmit(event) {
        // Generate SessionID as timestamp
        const sessionId = Date.now().toString();
        const sessionStartTime = Date.now();
        event.preventDefault();
        console.log("Download form submitted");
        if (!form || !downloadButton || !loadingIndicator || !statusMessagesDiv) return;

        if (eventSource) eventSource.close();
        downloadButton.disabled = true;
        loadingIndicator.style.display = 'inline-block';
        clearStatusMessages(statusMessagesDiv);
        addStatusMessage(statusMessagesDiv, "Initiating download request...", 'info');

        const currentData = getCurrentFormData();
        let validationError = false;
        if (!currentData.email || !currentData.password) {
            addStatusMessage(statusMessagesDiv, "Error: Please enter Email and Password.", 'error');
            validationError = true;
        }
        if (!currentData.reports || currentData.reports.length === 0) {
            addStatusMessage(statusMessagesDiv, "Error: Please configure at least one valid report.", 'error');
            validationError = true;
        }
        let requiresRegion = false;
        if (reportDataCache && currentData.reports) {
            requiresRegion = currentData.reports.some(report => {
                const reportUrl = reportDataCache.report_urls_map?.[report.report_type];
                return reportUrl && reportDataCache.region_required_urls?.includes(reportUrl);
            });
        }
        if (requiresRegion && currentData.regions.length === 0) {
            addStatusMessage(statusMessagesDiv, "Error: Selected report(s) require region selection.", 'error');
            validationError = true;
        }

        if (validationError) {
            downloadButton.disabled = false;
            loadingIndicator.style.display = 'none';
            // Enable lại các input/select nếu có lỗi
            if (reportTableBody) {
                reportTableBody.querySelectorAll('input, select, button').forEach(el => {
                    el.disabled = false;
                    el.classList.remove('disabled-during-download');
                });
            }
            showNotification("Please fix the errors in the form.", "error");
            return;
        }

        try {
            showDownloadTimer && showDownloadTimer(); // Hiện timer khi bắt đầu tải
            // Add to active sessions
            addActiveSession(sessionId, sessionStartTime, currentData.reports);
            const result = await fetchData('/download/start-download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(currentData),
            });

            if (result && result.status === 'started' || result.status === 'success') {
                addStatusMessage(statusMessagesDiv, "Request accepted. Waiting for status updates...", 'info');
                setupEventSource(sessionId);
            } else {
                downloadButton.disabled = false;
                loadingIndicator.style.display = 'none';
                // Enable lại các input/select nếu không bắt đầu download
                if (reportTableBody) {
                    reportTableBody.querySelectorAll('input, select, button').forEach(el => {
                        el.disabled = false;
                        el.classList.remove('disabled-during-download');
                    });
                }
            }
        } catch (error) {
            hideDownloadTimer && hideDownloadTimer(); // Ẩn timer khi lỗi
            removeActiveSession(sessionId); // Remove from active sessions on error
            downloadButton.disabled = false;
            loadingIndicator.style.display = 'none';
            // Enable lại các input/select nếu có lỗi
            if (reportTableBody) {
                reportTableBody.querySelectorAll('input, select, button').forEach(el => {
                    el.disabled = false;
                    el.classList.remove('disabled-during-download');
                });
            }
        }
    }

    function setupEventSource(sessionId) {
        if (eventSource) eventSource.close();
        console.log("Setting up SSE connection to /download/stream-status");
        eventSource = new EventSource('/download/stream-status');

        eventSource.onopen = function() {
            console.log("SSE connection opened.");
            addStatusMessage(statusMessagesDiv, "Connected to status stream.", 'info');
        };

        eventSource.onmessage = function(event) {
            const message = event.data;
            console.log("SSE message received:", message);
            if (message === "FINISHED") {
                addStatusMessage(statusMessagesDiv, "--- PROCESS COMPLETED ---", 'success');
                hideDownloadTimer && hideDownloadTimer(); // Ẩn timer khi hoàn thành
                removeActiveSession(sessionId); // Remove from active sessions on finish
                if (eventSource) eventSource.close();
                eventSource = null;
                downloadButton.disabled = false;
                loadingIndicator.style.display = 'none';
                fetchLogs();
                showNotification("Download process finished.", "success");
            } else if (message.startsWith("ERROR:")) {
                addStatusMessage(statusMessagesDiv, message, 'error');
                removeActiveSession(sessionId); // Remove on error
            } else {
                addStatusMessage(statusMessagesDiv, message);
            }
        };

        eventSource.onerror = function(error) {
            console.error('SSE Error:', error);
            addStatusMessage(statusMessagesDiv, "Status stream connection error. Attempting to reconnect...", 'error');
            if (eventSource) eventSource.close();
            eventSource = null;
            downloadButton.disabled = false;
            loadingIndicator.style.display = 'none';
        };
    }

    // --- Log Handling ---
    async function fetchLogs() {
        if (!logDataTableBody || !logTableContainer) return;
        logDataTableBody.innerHTML = '<tr><td colspan="7" class="subtext">Loading logs...</td></tr>';
        try {
            const data = await fetchData('/download/get-logs');
            logDataTableBody.innerHTML = '';
            if (data && Array.isArray(data) && data.length > 0) {
                createLogTable(data);
                console.log("Logs loaded and table populated.");
            } else if (data && Array.isArray(data)) {
                logDataTableBody.innerHTML = '<tr><td colspan="7" class="subtext">No log entries found.</td></tr>';
            } else {
                throw new Error("Invalid log data structure received.");
            }
        } catch (error) {
            logDataTableBody.innerHTML = `<tr><td colspan="7" class="error-message">Failed to load logs: ${error.message}</td></tr>`;
        }
    }

    function createLogTable(logData) {
        if (!logDataTableBody) return;
        logDataTableBody.innerHTML = '';
        logData.sort((a, b) => new Date(b.Timestamp) - new Date(a.Timestamp));
        const headers = ['SessionID', 'Timestamp', 'File Name', 'Start Date', 'End Date', 'Status', 'Error Message'];

        logData.forEach(logEntry => {
            const row = logDataTableBody.insertRow();
            headers.forEach(header => {
                const cell = row.insertCell();
                const value = logEntry[header];
                cell.textContent = (value === null || value === undefined) ? '-' : String(value);
                if (header === 'Status') {
                    if (typeof value === 'string') {
                        if (value.toLowerCase().startsWith('success')) {
                            cell.classList.add('status-success');
                        } else if (value.toLowerCase().startsWith('fail')) {
                            cell.classList.add('status-failed');
                        }
                    }
                }
                if (header === 'Error Message' && value && String(value).length < 50) {
                    cell.classList.add('subtext');
                } else if (header === 'Error Message') {
                    cell.style.fontSize = '12px';
                }
            });
        });
        updateSummaryAndChart(logData);
    }

    function updateSummaryAndChart(logData) {
        const total = logData.length;
        const successCount = logData.filter(e => e['Status'] && String(e['Status']).toLowerCase().startsWith('success')).length;
        const failedCount = total - successCount;

        if (totalCountSpan) totalCountSpan.textContent = total;
        if (successCountSpan) successCountSpan.textContent = successCount;
        if (failedCountSpan) failedCountSpan.textContent = failedCount;

        if (statusChartCtx) {
            if (statusChart) statusChart.destroy();
            if (total > 0) {
                statusChart = new Chart(statusChartCtx, {
                    type: 'doughnut',
                    data: {
                        labels: ['Success', 'Failed'],
                        datasets: [{
                            data: [successCount, failedCount],
                            backgroundColor: ['#198754', '#dc3545'],
                            borderColor: '#ffffff',
                            borderWidth: 2
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    label: function(context) {
                                        let label = context.label || '';
                                        if (label) { label += ': '; }
                                        if (context.parsed !== null) {
                                            label += context.parsed;
                                        }
                                        return label;
                                    }
                                }
                            }
                        },
                        cutout: '65%'
                    }
                });
            } else {
                statusChartCtx.clearRect(0, 0, statusChartCtx.canvas.width, statusChartCtx.canvas.height);
            }
        } else {
            console.warn("Status chart canvas context not found.");
        }
    }

    // --- Configuration Management ---
    async function fetchAndPopulateConfigs() {
        console.log("Fetching configurations from /download/get-configs...");
        try {
            const configNames = await fetchData('/download/get-configs');
            console.log("Config data received:", configNames);
            if (Array.isArray(configNames)) {
                console.log("Populating config dropdowns with:", configNames);
                if (savedConfigsDropdown) {
                    fillSelectOptions(savedConfigsDropdown, configNames, true, '-- Select Configuration --');
                }
                if (scheduleConfigSelect) {
                    fillSelectOptions(scheduleConfigSelect, configNames, true, '-- Select Config to Schedule --');
                }
                console.log("Configurations populated successfully.");
                if (configNames.length === 0) {
                    // Removed notification for empty configs, maybe intended
                    // showNotification("No saved configurations found.", "warning");
                }
            } else {
                throw new Error("Invalid config data structure received (expected array).");
            }
        } catch (error) {
            console.error("Failed to load configurations:", error);
            if (savedConfigsDropdown) {
                savedConfigsDropdown.innerHTML = '<option value="">-- Select Configuration --</option><option value="" disabled>Failed to load configs</option>';
            }
            if (scheduleConfigSelect) {
                scheduleConfigSelect.innerHTML = '<option value="">-- Select Config to Schedule --</option><option value="" disabled>Failed to load configs</option>';
            }
            addStatusMessage(statusMessagesDiv, `Error loading configurations: ${error.message}`, 'error');
        }
    }

    function applyConfiguration(configData) {
        if (!configData || typeof configData !== 'object') {
            showNotification("Invalid configuration data.", "error");
            return;
        }
        console.log("Applying configuration:", configData);
        if (emailInput) emailInput.value = configData.email || '';
        if (passwordInput) passwordInput.value = configData.password || '';
        if (otpSecretInput && configData.otp_secret !== undefined) otpSecretInput.value = configData.otp_secret;
        if (driverPathInput && configData.driver_path !== undefined) driverPathInput.value = configData.driver_path;
        if (downloadBasePathInput && configData.download_base_path !== undefined) downloadBasePathInput.value = configData.download_base_path;

        if (!reportTableBody) return;
        while (reportTableBody.rows.length > 1) reportTableBody.deleteRow(1);
        const firstRow = reportTableBody.rows[0];
        if (!firstRow) return;

        const firstSelect = firstRow.querySelector('select[name="report_type[]"]');
        const firstChunk = firstRow.querySelector('input[name="chunk_size[]"]');
        if (firstSelect) firstSelect.value = '';
        setDefaultDates(firstRow);
        if (firstChunk) firstChunk.value = '5';

        if (configData.reports && Array.isArray(configData.reports) && configData.reports.length > 0) {
            configData.reports.forEach((reportInfo, index) => {
                let targetRow;
                if (index === 0) {
                    targetRow = firstRow;
                } else {
                    targetRow = firstRow.cloneNode(true);
                    reportTableBody.appendChild(targetRow);
                    const newSelect = targetRow.querySelector("select[name='report_type[]']");
                    if (newSelect && !newSelect.dataset.listenerAttached) {
                        newSelect.addEventListener('change', updateRegionSelectionVisibilityBasedOnAllRows);
                        newSelect.dataset.listenerAttached = 'true';
                    }
                    setDefaultDates(targetRow);
                }
                const typeSelect = targetRow.querySelector('select[name="report_type[]"]');
                const fromInput = targetRow.querySelector('input[name="from_date[]"]');
                const toInput = targetRow.querySelector('input[name="to_date[]"]');
                const chunkInput = targetRow.querySelector('input[name="chunk_size[]"]');
                if (typeSelect) typeSelect.value = reportInfo.report_type || '';
                if (fromInput) fromInput.value = reportInfo.from_date || '';
                if (toInput) toInput.value = reportInfo.to_date || '';
                if (chunkInput) chunkInput.value = reportInfo.chunk_size || '5';
            });
        }

        updateRegionSelectionVisibilityBasedOnAllRows();
        setTimeout(() => {
            if (regionSelectionDiv && regionSelectionDiv.style.display === 'block') {
                if (configData.regions && Array.isArray(configData.regions)) {
                    const regionCheckboxes = regionSelectionDiv.querySelectorAll('input[name="regions"]');
                    regionCheckboxes.forEach(checkbox => {
                        checkbox.checked = configData.regions.includes(checkbox.value);
                    });
                    console.log("Applied saved regions:", configData.regions);
                }
            }
        }, 50);
        showNotification("Configuration loaded successfully.", "success");
    }

    // --- Scheduling Logic ---
    async function fetchAndDisplaySchedules() {
        if (!schedulesListBody) return;
        schedulesListBody.innerHTML = '<tr><td colspan="3" class="subtext">Loading schedules...</td></tr>';
        try {
            const data = await fetchData('/download/get-schedules');
            schedulesListBody.innerHTML = '';
            if (data && Array.isArray(data) && data.length > 0) {
                data.forEach(job => {
                    const row = schedulesListBody.insertRow();
                    let nextRunText = 'N/A';
                    if (job.next_run_time) {
                        try {
                            nextRunText = new Date(job.next_run_time).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
                        } catch (e) {
                            nextRunText = job.next_run_time;
                        }
                    }
                    const configArg = job.args && job.args.length > 0 ? job.args[0] : 'Unknown Config';
                    const cellConfig = row.insertCell();
                    cellConfig.textContent = configArg;
                    cellConfig.className = 'schedule-config-name';
                    const cellTime = row.insertCell();
                    cellTime.textContent = nextRunText;
                    cellTime.className = 'schedule-time';
                    const cellAction = row.insertCell();
                    const cancelButton = document.createElement('button');
                    cancelButton.innerHTML = '<i class="fas fa-times"></i> Cancel';
                    cancelButton.className = 'cancel-schedule-button delete-button';
                    cancelButton.dataset.jobId = job.id;
                    cancelButton.title = `Cancel schedule ${job.id}`;
                    cellAction.appendChild(cancelButton);
                });
                console.log("Schedules loaded.");
            } else {
                schedulesListBody.innerHTML = '<tr><td colspan="3" class="subtext">No active schedules found.</td></tr>';
            }
        } catch (error) {
            schedulesListBody.innerHTML = `<tr><td colspan="3" class="error-message">Error loading schedules: ${error.message}</td></tr>`;
        }
    }

    // --- Event Listeners ---
    if (notificationCloseBtn) {
        notificationCloseBtn.addEventListener('click', hideNotification);
    }

    if (reportTableSearchInput && reportTableBody) {
        reportTableSearchInput.addEventListener('keyup', () => filterTable(reportTableSearchInput, reportTableBody));
    }
    if (logTableSearchInput && logDataTableBody) {
        logTableSearchInput.addEventListener('keyup', () => filterTable(logTableSearchInput, logDataTableBody));
    }

    if (form) {
        form.addEventListener('submit', event => {
            localStorage.removeItem('reportTableHTML'); // Xóa trạng thái khi nhấn Download
            // Disable và làm mờ các input/select trong bảng report
            if (reportTableBody) {
                reportTableBody.querySelectorAll('input, select, button').forEach(el => {
                    el.disabled = true;
                    el.classList.add('disabled-during-download');
                });
            }
            handleDownloadFormSubmit(event);
        });
    }

    if (refreshLogButton) {
        refreshLogButton.addEventListener('click', fetchLogs);
    }

    if (saveConfigButton && configNameInput) {
        saveConfigButton.addEventListener('click', async () => {
            const configName = configNameInput.value.trim();
            if (!configName) {
                showNotification("Please enter a configuration name.", "warning");
                return;
            }
            const configData = getCurrentFormData();
            if (!configData.reports || configData.reports.length === 0) {
                showNotification("Configure at least one report before saving.", "warning");
                return;
            }
            try {
                const result = await fetchData('/download/save-config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: configName, config: configData })
                });
                if (result.status === 'success') {
                    showNotification(result.message || `Configuration "${configName}" saved.`, 'success');
                    configNameInput.value = '';
                    fetchAndPopulateConfigs();
                }
            } catch (error) {}
        });
    }

    if (loadConfigButton && savedConfigsDropdown) {
        loadConfigButton.addEventListener('click', async () => {
            const selectedConfigName = savedConfigsDropdown.value;
            if (!selectedConfigName) {
                showNotification("Select a configuration to load.", "warning");
                return;
            }
            try {
                const config_data = await fetchData(`/download/load-config/${selectedConfigName}`);
                applyConfiguration(config_data);
            } catch (error) {}
        });
    }

    if (deleteConfigButton && savedConfigsDropdown) {
        deleteConfigButton.addEventListener('click', async () => {
            const selectedConfigName = savedConfigsDropdown.value;
            if (!selectedConfigName) {
                showNotification("Select a configuration to delete.", "warning");
                return;
            }
            if (!confirm(`Are you sure you want to delete configuration "${selectedConfigName}"? This cannot be undone.`)) return;
            try {
                const result = await fetchData(`/download/delete-config/${selectedConfigName}`, { method: 'DELETE' });
                if (result && result.status === 'success') {
                    showNotification(result.message || `Configuration "${selectedConfigName}" deleted.`, 'success');
                    fetchAndPopulateConfigs();
                }
            } catch (error) {}
        });
    }

    if (scheduleButton && scheduleConfigSelect && scheduleDateTimeInput) {
        scheduleButton.addEventListener('click', async () => {
            const configName = scheduleConfigSelect.value;
            const runDateTime = scheduleDateTimeInput.value;
            if (!configName) {
                showNotification("Select a configuration to schedule.", "warning");
                return;
            }
            if (!runDateTime) {
                showNotification("Select date and time to run.", "warning");
                return;
            }
            try {
                const selectedDate = new Date(runDateTime);
                const bufferMinutes = 1;
                const minDate = new Date(Date.now() + bufferMinutes * 60 * 1000);
                if (selectedDate <= minDate) {
                    showNotification(`Select a time at least ${bufferMinutes} minute(s) in the future.`, "warning");
                    return;
                }
            } catch (e) {
                showNotification("Invalid date/time format.", "error");
                return;
            }
            console.log(`Scheduling config: ${configName} at ${runDateTime}`);
            try {
                const result = await fetchData('/download/schedule-job', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        config_name: configName,
                        run_datetime: runDateTime
                    })
                });
                if (result.status === 'success') {
                    showNotification(result.message || `Job scheduled for ${configName}.`, 'success');
                    fetchAndDisplaySchedules();
                    scheduleConfigSelect.value = '';
                    scheduleDateTimeInput.value = '';
                }
            } catch (error) {}
        });
    }

    if (schedulesListBody) {
        schedulesListBody.addEventListener('click', async (event) => {
            const cancelButton = event.target.closest('.cancel-schedule-button');
            if (cancelButton) {
                const jobId = cancelButton.dataset.jobId;
                if (!jobId) {
                    console.error("Job ID missing on cancel button.");
                    return;
                }
                if (!confirm(`Are you sure you want to cancel schedule ${jobId}?`)) return;
                console.log(`Cancelling schedule: ${jobId}`);
                try {
                    const result = await fetchData(`/download/cancel-schedule/${jobId}`, { method: 'DELETE' });
                    if (result && result.status === 'success') {
                        showNotification(result.message || `Job ${jobId} cancelled.`, 'success');
                        fetchAndDisplaySchedules();
                    }
                } catch (error) {}
            }
        });
    }

    if (saveAdvancedSettingsButton) {
        saveAdvancedSettingsButton.addEventListener('click', async () => {
            const settings = {
                otp_secret: otpSecretInput ? otpSecretInput.value : undefined,
                driver_path: driverPathInput ? driverPathInput.value : undefined,
                download_base_path: downloadBasePathInput ? downloadBasePathInput.value : undefined
            };
            console.log("Saving advanced settings:", settings);
            showNotification("Advanced settings saved (simulation).", "success");
        });
    }

    if (bulkEmailForm && sendEmailButton && emailLoadingIndicator && emailStatusMessagesDiv) {
        bulkEmailForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            sendEmailButton.disabled = true;
            emailLoadingIndicator.style.display = 'inline-block';
            clearStatusMessages(emailStatusMessagesDiv);
            addStatusMessage(emailStatusMessagesDiv, "Preparing to send emails...", 'info');
            const formData = new FormData(bulkEmailForm);
            console.log("Bulk Email Form Data:", Object.fromEntries(formData));
            try {
                await new Promise(resolve => setTimeout(resolve, 1500));
                addStatusMessage(emailStatusMessagesDiv, "Emails sent successfully (simulation).", 'success');
                showNotification("Bulk emails sent.", "success");
                bulkEmailForm.reset();
            } catch (error) {
                console.error("Bulk Email Error:", error);
                const msg = `Error sending emails: ${error.message}`;
                addStatusMessage(emailStatusMessagesDiv, msg, 'error');
                showNotification(msg, "error");
            } finally {
                sendEmailButton.disabled = false;
                emailLoadingIndicator.style.display = 'none';
            }
        });
    }

    // --- Show/Hide Password and OTP Secret ---
    // Use already declared passwordInput and otpSecretInput from the top
    const togglePasswordBtn = document.getElementById('toggle-password-visibility');
    if (togglePasswordBtn && passwordInput) {
        togglePasswordBtn.addEventListener('click', function() {
            const isHidden = passwordInput.type === 'password';
            passwordInput.type = isHidden ? 'text' : 'password';
            togglePasswordBtn.innerHTML = `<i class=\"fas fa-${isHidden ? 'eye-slash' : 'eye'}\"></i>`;
        });
    }
    // Advanced Settings OTP Secret show/hide logic
    const otpSecretInputAdv = document.querySelector('#advanced-settings-panel #otp-secret');
    const toggleOtpBtnAdv = document.getElementById('toggle-otp-visibility-adv');
    if (toggleOtpBtnAdv && otpSecretInputAdv) {
        toggleOtpBtnAdv.addEventListener('click', function() {
            const isHidden = otpSecretInputAdv.type === 'password';
            otpSecretInputAdv.type = isHidden ? 'text' : 'password';
            toggleOtpBtnAdv.innerHTML = `<i class=\"fas fa-${isHidden ? 'eye-slash' : 'eye'}\"></i>`;
        });
    }

    // --- Initial Page Load Actions ---
    console.log("Running initial setup...");
    fetchAndPopulateReportData();
    fetchAndPopulateConfigs();
    switchPanel('main-download-panel');
    console.log("Initialization complete.");
});