from fastapi import File, UploadFile
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from datetime import datetime
from auth import oauth2, schemas
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi import BackgroundTasks
from database import get_db
from sqlalchemy.orm import Session
from models.user import User #, Permission, AccountType, AccountTypePermission
# from auth import utils
# from sqlalchemy import or_
from global_log import glogger
from config import Settings, settings
from dotenv import set_key
import subprocess
import os
import zipfile
import shutil
import psutil
router = APIRouter()


@router.get("/version")
async def software_version():
    return {"software version": "1.0.5"}

@router.get("/log")
async def log_print(path:str):
    try:
        file_path = path  # Path to your text file
        return FileResponse(file_path, media_type="text/plain")
    except Exception as e:
        return {"error": str(e)}

@router.get("/list")
async def list_filefolder(dir:str):
    # dir = "C:/gyro5"  # Path to your text file
    file_path = "flist.txt"
    try:
        # List all files and folders in the directory
        items = os.listdir(dir)
        # Separate files and folders
        files = [item for item in items if os.path.isfile(os.path.join(dir, item))]
        folders = [item for item in items if os.path.isdir(os.path.join(dir, item))]
        
        with open(file_path, "w") as file:
            file.write("Files:\n")
            file.write("----------\n")
            file.write("\n".join(files))
            file.write("\n\n")
            file.write("Folders:\n")
            file.write("----------\n")
            file.write("\n".join(folders))
        
        # return {"files": files, "folders": folders}
        return FileResponse(file_path, media_type="text/plain")
    
    except Exception as e:
        return {"error": str(e)}

def terminate_server2():
    # Get the process ID of the current process
    pid = os.getpid()
    # Terminate the process
    os.kill(pid, 9)

@router.get("/exit")
async def terminate_server(task: BackgroundTasks):
# async def terminate_server():
    def _terminate():
        # Execute the termination process
        terminate_server2()
        # pid = os.getpid()
        # # Terminate the process
        # os.kill(pid, 9)
    
    try:
        # Add a background task to run the termination process
        task.add_task(_terminate)
        
        # Return a message to the client
        return {"message": "Termination process initiated. Server will be terminated shortly."}
    except Exception as e:
        return {"error": str(e)}

@router.get("/run")
# async def run_program(apps:str)
# async def run_program(program:str, option:str, path:str, cwd:str):
async def run_cmd(cmd:str, cwd:str):
    # try:
    #     # Replace "update.exe" with the actual path to your executable
    #     subprocess.run(["run.cmd"], check=True)
    #     return {"message": "Update process started successfully."}
    # except Exception as e:
    #     return {"error": str(e)}
    
    try:
        # stdout_file = "C:\\path_to_log\\stdout_log.txt"
        # stderr_file = "C:\\path_to_log\\stderr_log.txt"
        
        # stdout_file = os.path.join(os.getcwd(), 'run_cmd_stdout.txt')
        # stderr_file = os.path.join(os.getcwd(), 'run_cmd_stderr.txt')
        
        file_path = os.path.join(os.getcwd(), 'run.txt')
        print(file_path)
        
        # with open(stdout_file, "w") as stdout, open(stderr_file, "w") as stderr:
        with open(file_path, "w") as file:
            pstime = datetime.now().strftime('%Y-%m-%d %H:%M:%S %f')[:-3]
            file.write(f"run_cmd : {cmd} {pstime}\n")
            file.write(f"{file_path}\n")
            file.write("--------------------\n")
            # Replace "your_program.exe" with the path to your .exe program
            # subprocess.Popen(["C:/Program Files (x86)/teraterm5/ttermpro.exe"])
            # C:\Windows\System32\cmd.exe
            # C:\Windows\System32\calc.exe
            # subprocess.Popen([apps])
            # subprocess.Popen([program, option, path], cwd=cwd, close_fds=True, start_new_session=False)
            # subprocess.Popen(["cmd.exe", "/C", "C:/abcd/ftp_svc_20240328/start_ipc.cmd"], cwd="C:/abcd/ftp_svc_20240328")
            subprocess.Popen(cmd, cwd=cwd, shell=True, close_fds=True, start_new_session=True, stdout=file, stderr=file)
            return {"message": f"New process started successfully to run {cmd}"}
    except Exception as e:
        return {"error": str(e)}
    
@router.post("/upload")
async def upload_file(dir:str, file: UploadFile = File(...)):
    try:
        if not os.path.isdir(dir):
            return JSONResponse(content={"error": f"Folder {dir} does not exist."}, status_code=500)
        # Save the uploaded file to a directory
        # with open(f"uploaded_files/{file.filename}", "wb") as buffer:
        path = os.path.join(dir, file.filename)
        # print("######## ",path)
        # with open(f"C:/abcd/{file.filename}", "wb") as buffer:
        with open(path, "wb") as buffer:
            buffer.write(await file.read())
        
        return JSONResponse(content={"message": "File uploaded successfully", "filename": file.filename})
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@router.get("/unzip")
async def unzip_file(zip:str, dir:str):
    try:
        zip_file = zip
        extract_to = dir
        # Create the extraction directory if it doesn't exist
        os.makedirs(extract_to, exist_ok=True)
        
        # Open the zip file for reading
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            # Extract all the contents into the specified directory
            zip_ref.extractall(extract_to)
        
        return {"message": f"File '{zip_file}' successfully extracted to '{extract_to}'."}
    except Exception as e:
        return {"error": str(e)}

@router.get("/rename")
async def rename_filefolder(old:str, new:str):
    try:
        old_name = old
        new_name = new
        
        type = ''
        if os.path.isfile(old_name):
            type = 'File'
        elif os.path.isdir(old_name):
            type = 'Folder'
        # Rename the folder
        os.rename(old_name, new_name)
        return {"message": f"{type} '{old_name}' successfully renamed to '{new_name}'."}
    except Exception as e:
        return {"error": str(e)}
    
@router.get("/copy")
async def copy_filefolder(src:str, to:str):
    try:
        source_filefolder = src
        destination_folder = to
        
        if os.path.exists(destination_folder):
            delete_filefolder(destination_folder)
        
        type = ''
        if os.path.isfile(source_filefolder):
            type = 'File'
            # Copy the file to the destination folder
            shutil.copy(source_filefolder, destination_folder)
        elif os.path.isdir(source_filefolder):
            type = 'Folder'
            # Copy the folder and its contents to the destination folder
            # shutil.copytree(source_filefolder, destination_folder, dirs_exist_ok=True)
            shutil.copytree(source_filefolder, destination_folder)
        
        return {"message": f"{type} '{source_filefolder}' successfully copied to '{destination_folder}'."}
    except Exception as e:
        return {"error": str(e)}
    
@router.get("/delete")
async def delete_filefolder(path:str):
    try:
        filefolder = path
        
        type = ''
        if os.path.isfile(filefolder):
            type = 'File'
            # Remove the file
            os.remove(filefolder)
        elif os.path.isdir(filefolder):
            type = 'Folder'
            # Remove the folder and its contents
            # os.rmdir(filefolder) # only can delete empty folder
            shutil.rmtree(filefolder)
        
        return {"message": f"{type} '{filefolder}' successfully deleted."}
    except Exception as e:
        return {"error": str(e)}
    
@router.get("/pslist")
async def process_list():
    # dir = "C:/gyro5"  # Path to your text file
    file_path = "pslist.txt"
    
    running_apps = []
    # Iterate over all running processes
    for proc in psutil.process_iter(['pid', 'name', 'username', 'exe']):
        try:
            # Get process information
            process_info = proc.info
            running_apps.append(process_info)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError) as e:
            if isinstance(e, OSError) and e.winerror == 15100:
                # Handle the specific OSError related to MUI files (typically not applicable for processes)
                print(f"Warning: Failed to retrieve process information due to missing MUI file for process: {proc.name()}")
            else:
                # Handle other exceptions
                print(f"Warning: Failed to retrieve process information: {e}")
                
    try:
        with open(file_path, "w") as file:
            pstime = datetime.now().strftime('%Y-%m-%d %H:%M:%S %f')[:-3]
            file.write(f"running processes: {pstime}\n")
            file.write("--------------------\n")
            for app in running_apps:
                file.write(str(app))
                file.write("\n")
            file.write("--------------------\n")
            # file.write("\n".join(files))
            # file.write("\n\n")
            # file.write("Folders:\n")
            # file.write("----------\n")
            # file.write("\n".join(folders))
        
        # return {"files": files, "folders": folders}
        return FileResponse(file_path, media_type="text/plain")
    
    except Exception as e:
        return {"error": str(e)}

@router.get("/psfind")
async def process_find(name:str=''):

    if not name:
        return {"error": "Do not provide process name."}

    file_path = "psfind.txt"
    
    running_apps = []
    # Iterate over all running processes
    for proc in psutil.process_iter(['pid', 'name', 'username', 'exe']):
        try:
            # Get process information
            process_info = proc.info
            # print(process_info)
            if process_info['name']:
                if len(process_info['name']) > 0:
                    if process_info['name'].find(name) >= 0:
                        running_apps.append(process_info)
                        continue
            if process_info['exe']:
                if len(process_info['exe']) > 0:
                    if process_info['exe'].find(name) >= 0:
                        running_apps.append(process_info)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError) as e:
            if isinstance(e, OSError) and e.winerror == 15100:
                # Handle the specific OSError related to MUI files (typically not applicable for processes)
                print(f"Warning: Failed to retrieve process information due to missing MUI file for process: {proc.name()}")
            else:
                # Handle other exceptions
                print(f"Warning: Failed to retrieve process information: {e}")

    try:
        with open(file_path, "w") as file:
            pstime = datetime.now().strftime('%Y-%m-%d %H:%M:%S %f')[:-3]
            file.write(f"find {name} processes: {pstime}\n")
            file.write("--------------------\n")
            for app in running_apps:
                file.write(str(app))
                file.write("\n")
            file.write("--------------------\n")
        
        # return {"files": files, "folders": folders}
        return FileResponse(file_path, media_type="text/plain")
    
    except Exception as e:
        return {"error": str(e)}

@router.get("/pskill")
async def process_kill(name:str=''):

    if not name:
        return {"error": "Do not provide process name."}

    file_path = "pskill.txt"
    
    running_apps = []
    # Iterate over all running processes
    # for proc in psutil.process_iter(['pid', 'name', 'username', 'exe']):
    #     try:
    #         # Get process information
    #         process_info = proc.info
    #         # print(process_info)
            
    #         if process_info['name']:
    #             if len(process_info['name']) > 0:
    #                 if process_info['name'].find(name) >= 0:
    #                     running_apps.append(process_info)
    #                     os.kill(process_info['pid'], 9)
    #                     continue
    #         if process_info['exe']:
    #             if len(process_info['exe']) > 0:
    #                 if process_info['exe'].find(name) >= 0:
    #                     running_apps.append(process_info)
    #                     os.kill(process_info['pid'], 9)
                        
    #     except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError) as e:
    #         if isinstance(e, OSError) and e.winerror == 15100:
    #             # Handle the specific OSError related to MUI files (typically not applicable for processes)
    #             print(f"Warning: Failed to retrieve process information due to missing MUI file for process: {proc.name()}")
    #         else:
    #             # Handle other exceptions
    #             print(f"Warning: Failed to retrieve process information: {e}")

    # Iterate over all running processes
    for proc in psutil.process_iter(['pid', 'name', 'username', 'exe', 'cmdline']):
        try:
            # Get process information
            # print(f"{proc.pid}, {proc.name()}, {proc.username()}, {proc.exe()}, [{' '.join(proc.cmdline())}]")
            
            proc_info = proc.info
            cmdline = ' '.join(proc.cmdline())
            # print(f"{proc_info['pid']}, {proc_info['name']}, {proc_info['username']}, {proc_info['exe']}, [{cmdline}]")
            print(f"{proc_info['pid']}, {proc_info['name']}, {proc_info['username']}, {proc_info['exe']}")
            
            if proc_info['name']:
                if len(proc_info['name']) > 0:
                    if proc_info['name'].find(name) >= 0:
                        running_apps.append(proc_info)
                        os.kill(proc_info['pid'], 9)
                        continue
            if proc_info['exe']:
                if len(proc_info['exe']) > 0:
                    if proc_info['exe'].find(name) >= 0:
                        running_apps.append(proc_info)
                        os.kill(proc_info['pid'], 9)
                        
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError) as e:
            if isinstance(e, OSError) and e.winerror == 15100:
                # Handle the specific OSError related to MUI files (typically not applicable for processes)
                print(f"Warning: Failed to retrieve process information due to missing MUI file for process: {proc.name()}")
            else:
                # Handle other exceptions
                print(f"Warning: Failed to retrieve process information: {e}")

    try:
        with open(file_path, "w") as file:
            pstime = datetime.now().strftime('%Y-%m-%d %H:%M:%S %f')[:-3]
            file.write(f"kill {name} processes: {pstime}\n")
            file.write("--------------------\n")
            for app in running_apps:
                file.write(str(app))
                file.write("\n")
            file.write("--------------------\n")
        
        # return {"files": files, "folders": folders}
        return FileResponse(file_path, media_type="text/plain")
    
    except Exception as e:
        return {"error": str(e)}