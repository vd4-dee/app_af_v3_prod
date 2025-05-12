from cx_Freeze import setup, Executable
import sys

# Dependencies are automatically detected, but it might need fine tuning.
build_exe_options = {
    "packages": ["os", "flask", "selenium", "pyotp", "schedule", "pandas", "numpy"],
    "include_files": [("templates", "templates"), ("static", "static"), ("config.py", "config.py")],
}

base = None
if sys.platform == "win32":
    base = "Console"

setup(
    name="report_downloader",
    version="1.0",
    description="Report Downloader App",
    options={"build_exe": build_exe_options},
    executables=[Executable("app.py", base=base, target_name="report_downloader.exe")]
)
