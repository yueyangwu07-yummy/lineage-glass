# 激活虚拟环境指南

## 虚拟环境位置
```
D:\CodeTry\lineage-glass\lineage-glass
```

## 激活方法

### Windows PowerShell
```powershell
# 方法 1：使用完整路径
.\lineage-glass\Scripts\Activate.ps1

# 方法 2：如果遇到执行策略限制，先运行：
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\lineage-glass\Scripts\Activate.ps1
```

### Windows CMD (命令提示符)
```cmd
lineage-glass\Scripts\activate.bat
```

### Git Bash / WSL
```bash
source lineage-glass/Scripts/activate
```

## 验证激活
激活成功后，命令提示符前会显示 `(lineage-glass)`：
```
(lineage-glass) PS D:\CodeTry\lineage-glass>
```

## 退出虚拟环境
```powershell
deactivate
```

## 安装依赖
激活虚拟环境后，安装项目依赖：
```powershell
pip install -e .
```

## 常见问题

### PowerShell 执行策略错误
如果遇到 "无法加载文件，因为在此系统上禁止运行脚本" 错误：

1. 以管理员身份运行 PowerShell
2. 执行：`Set-ExecutionPolicy RemoteSigned`
3. 或者使用 CMD 激活虚拟环境

### 找不到 activate 脚本
确保虚拟环境已正确创建：
```powershell
python -m venv lineage-glass
```

