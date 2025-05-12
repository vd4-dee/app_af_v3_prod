// Xử lý toggle sidebar và card cài đặt nâng cao
document.addEventListener('DOMContentLoaded', () => {
  // Khi DOM đã load xong

  // Lấy phần tử card cài đặt nâng cao và panel cài đặt nâng cao
  const advCard = document.getElementById('advanced-settings-card');
  const advPanel = document.getElementById('advanced-settings');
  // Nếu cả hai phần tử đều tồn tại
  if (advCard && advPanel) {
    // Thêm sự kiện click cho card cài đặt nâng cao
    advCard.addEventListener('click', function(e) {
      e.preventDefault(); // Ngăn chặn hành vi mặc định
      // Nếu panel đang ẩn thì hiển thị, ngược lại thì ẩn đi
      if (advPanel.style.display === 'none' || advPanel.style.display === '') {
        advPanel.style.display = 'block';
        advPanel.scrollIntoView({behavior:'smooth', block:'center'}); // Cuộn đến panel
      } else {
        advPanel.style.display = 'none';
      }
    });
  }

  // Lấy các phần tử sidebar, nút toggle và nội dung chính
  const sidebar = document.getElementById('sidebar');
  const toggle = document.getElementById('sidebar-toggle');
  const mainContent = document.getElementById('main-content');
  // Thêm sự kiện click cho nút toggle sidebar
  toggle.addEventListener('click', () => {
    document.body.classList.toggle('collapsed'); // Thu gọn/mở rộng body
    sidebar.classList.toggle('collapsed'); // Thu gọn/mở rộng sidebar
    mainContent.classList.toggle('collapsed'); // Thu gọn/mở rộng nội dung chính
  });
});
