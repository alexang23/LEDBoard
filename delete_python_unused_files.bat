@echo %cd%
@echo %1
for /R %1 %%i in (*.pyc) DO @echo %%i & del /F /Q %%i
for /R %1 %%i in (__pycache__) DO @echo %%i & rd /S /Q %%i
@pause

