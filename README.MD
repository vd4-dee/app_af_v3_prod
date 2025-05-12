# Tao du an
mkdir ten_du_an
cd ten_du_an

# Tao va vao moi truong ao
python -m venv venv
.\venv\Scripts\activate

# Tao file requirements.txt
# -r là viết tắt của --requirement, cho biết bạn muốn pip cài đặt các gói được liệt kê trong file requirements.txt
pip install -r requierments.txt
requirements.txt
    pandas==1.5.3
    selenium==4.11.2
    numpy==1.23.5

# Tao file requierments.txt tu nhung thu vien da cai san
pip freeze > requierments.txt

Cờ / Flag	Ý nghĩa	Ví dụ
-m	Chạy một module như một script	python -m pip install pandas
-V hoặc --version	In ra phiên bản Python đang dùng	python -V
-c	Chạy một đoạn mã Python ngắn trực tiếp trong command line	python -c "print('Hello')"
-i	Mở Python interactive shell, có thể tùy chỉnh file đầu vào	python -i script.py
--help	Hiển thị tất cả các tùy chọn dòng lệnh	python --help
install	Cài đặt một package	pip install pandas
uninstall	Gỡ cài đặt một package	pip uninstall numpy
-r	Cài đặt từ file yêu cầu (requirement file)	pip install -r requirements.txt
--upgrade	Cập nhật lên phiên bản mới nhất	pip install --upgrade pandas
--user	Cài đặt vào thư mục riêng của user, không cần quyền admin	pip install --user matplotlib
list	Liệt kê tất cả các package đã cài	pip list
freeze	Liệt kê package + phiên bản, dùng để tạo requirements.txt	pip freeze > requirements.txt
show	Hiển thị thông tin chi tiết của 1 package	pip show pandas
search (ít dùng)	Tìm kiếm gói trên PyPI (đã bị gỡ bỏ từ pip 21.1 trở lên)	pip search flask (KHÔNG còn dùng được nữa)


# Cap nhat pip 
python -m pip install --upgrade pip
