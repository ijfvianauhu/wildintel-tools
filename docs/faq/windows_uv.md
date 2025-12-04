# FAQ: How do I install **wildintel-tools** on Windows using **uv**?

Follow the steps below to correctly install **wildintel-tools** on a Windows system using **uv**.

---

## **1. Install Python**

1. Visit the official Python website:  
   [https://www.python.org/downloads/](https://www.python.org/downloads/windows/)
2. Download the latest Windows installer.
3. Run the installer and **enable the option “Add Python to PATH”**.
4. Complete the installation.

---

## **2. Open PowerShell**

Open a **new PowerShell** window (no admin privileges required).

---

## **3. Install the required tools using `winget`**

Use the following commands to install Git, ExifTool, and uv:

### **Install Git**
```powershell
winget install -e --id Git.Git
```

### Install ExifTool

```powershell
winget install -e --id OliverBetz.ExifTool
```

### Install uv

``` powershell
winget install -e --id astral-sh.uv
```

## 4. Close the terminal

After installing the tools, close PowerShell completely. This ensures that PATH updates take effect.

## 5. Reopen PowerShell

Open a new PowerShell session.

## 6. Go to your Documents folder

``` powershell
cd $HOME\Documents
```

## 7. Clone the wildintel-tools repository

``` powershell
git clone https://github.com/ijfvianauhu/wildintel-tools.git
```

## 8. Enter the repository

``` powershell
cd wildintel-tools
```

## 9. Checkout the correct version (v0.1.0)

``` powershell
git checkout v0.1.0
```

## 10. Run wildintel-tools using uv

``` powershell
uv run wildintel-tools
```
