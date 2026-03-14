ubuntu
```
# 如果没有pip，先安装
sudo apt update
sudo apt install python3-pip python3-venv -y
python3 -m venv venv
source venv/bin/activate
#在虚拟环境中运行
pip install --upgrade pip
pip install -r fastapi/requirements.txt
#最后运行
python3 fastapi/main.py
```

windows
```
python -m venv venv
.\venv\Scripts\activate.bat
pip install -r fastapi/requirements.txt
#最后在虚拟环境中运行
python3 fastapi/main.py
```
