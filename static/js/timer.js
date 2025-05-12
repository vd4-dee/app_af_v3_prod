// Hiển thị bộ đếm thời gian tải báo cáo ở giữa trên cùng (center top of page)
let timerInterval = null;
let timerStartTime = null;

function showDownloadTimer() {
    let timerDiv = document.getElementById('download-timer');
    if (!timerDiv) {
        timerDiv = document.createElement('div');
        timerDiv.id = 'download-timer';
        document.body.appendChild(timerDiv);
    }
    timerDiv.style.display = 'block';
    timerStartTime = Date.now();
    updateTimerDisplay();
    timerInterval = setInterval(updateTimerDisplay, 1000);
}

function updateTimerDisplay() {
    const timerDiv = document.getElementById('download-timer');
    if (!timerDiv || timerStartTime === null) return;
    const elapsed = Math.floor((Date.now() - timerStartTime) / 1000);
    const min = Math.floor(elapsed / 60).toString().padStart(2, '0');
    const sec = (elapsed % 60).toString().padStart(2, '0');
    const hour = Math.floor(elapsed / 3600).toString().padStart(2, '0');
    timerDiv.textContent = `⏱️ !-----------------------------Đang tải mà, chờ xíu-----------------------------!: ${hour}:${min}:${sec}`;
}

function hideDownloadTimer() {
    const timerDiv = document.getElementById('download-timer');
    if (timerDiv) timerDiv.style.display = 'none';
    if (timerInterval) clearInterval(timerInterval);
    timerInterval = null;
    timerStartTime = null;
}

// Để sử dụng: gọi showDownloadTimer() khi bắt đầu tải, hideDownloadTimer() khi xong hoặc lỗi.
